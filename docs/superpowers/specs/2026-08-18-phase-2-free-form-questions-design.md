# Свободные вопросы к LLM (последний под-этап остатка Фазы 2) — дизайн

## Контекст

Фаза 2 (LLM-объяснения поверх KataGo, без RAG) реализована для трёх детектор-инициированных сценариев: `weak_group`/`mistake` (`POST /api/explain`) и `opening_loss` (`POST /api/explain/opening`). Все три построены вокруг одного паттерна: детектор находит структурированную находку (`Finding`) → LLM объясняет её через forced structured-output (`claims[]`, каждый claim ссылается на `finding_id`+поле находки) → пост-хок consistency checker (`llm/consistency.py`) сверяет числа claim'ов с реальными данными → при расхождении — до 2 ретраев с уточняющим промптом → при исчерпании — безопасный шаблонный fallback-текст, собранный из полей находки напрямую (не сгенерирован LLM).

Пользователь явно попросил реализовать последний оставшийся под-этап «остатка Фазы 2» — свободные вопросы к LLM. В `docs/ARCHITECTURE.md` архитектурного видения под это название нет — оно введено пользователем при исходной декомпозиции Фазы 2 в более ранней сессии, без формализации. Брейнсторминг этой сессии установил точный scope и архитектуру с нуля, вопрос за вопросом (см. `task_plan.md` → decisions log за эту дату).

## Scope

- **Что это**: чат про текущую позицию/партию — пользователь печатает произвольный текстовый вопрос (не привязанный к конкретной находке детектора), LLM отвечает с опорой на данные KataGo текущей позиции и (опционально, по своему решению) RAG-базу знаний.
- **Многоходовость**: НЕ реализуется в этом срезе. Каждый вопрос обрабатывается независимо — без памяти о предыдущих репликах в рамках одной пользовательской сессии. Один запрос → один ответ.
- **LLM-провайдер**: только `llama` (дефолтный/локальный). Если активный провайдер — `claude`/`gemini`, эндпоинт возвращает `503` с понятным сообщением («доступно только с провайдером llama»). `LLMProvider`-протокол (`llm/orchestrator.py`) НЕ трогается — та же дисциплина минимального blast radius, что и у Фазы 3, второго под-этапа (RAG-LLM-wiring, тоже только `llama`).
- **RAG**: включён. LLM сама решает, стоит ли искать в базе знаний (тот же agentic-паттерн, что уже есть в `llama.py` для находок) — не принудительный поиск на каждый вопрос.
- **Anti-hallucination**: та же архитектурная гарантия, что и у существующих трёх сценариев — structured-output + claims + пост-хок числовая проверка + ретраи + безопасный fallback. НЕ переиспользует существующие `Claim`/`Explanation`/`consistency.py`'s finding-специфичную логику напрямую (там жёсткая привязка к `finding_id`) — заводится параллельный, изолированный набор типов/функций под открытый вопрос, во избежание риска тонкой регрессии в уже стабильном, хорошо покрытом тестами коде трёх существующих сценариев.
- **UI**: поле ввода вопроса — внутри существующей `LlmExplanationPanel.tsx`, между блоком «Объяснить эту позицию» и блоком «Дебют». Новая независимая вкладка/панель НЕ заводится.

## Backend: эндпоинт и схемы

Новый роутер `POST /api/ask` (`backend/src/baduk_backend/api/ask.py`, регистрируется в `main.py` рядом с `explain`/`explain_opening`) — не расширение `/api/explain` (другая форма входа: нет находки, есть открытый текст).

`api/schemas.py`:

```python
class AskRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse
    question: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _ownership_matches_board_size(self) -> "AskRequest":
        ownership = self.analysis.ownership
        if ownership is not None and len(ownership) != self.boardXSize * self.boardYSize:
            raise ValueError(
                "analysis.ownership length must equal boardXSize * boardYSize "
                f"({self.boardXSize * self.boardYSize}), got {len(ownership)}"
            )
        return self


class AskResponse(BaseModel):
    answer: str | None = None
    verified: bool | None = None
    message: str | None = None
    citation: RagCitation | None = None
```

`moves` включён в запрос для консистентности с `ExplainRequest` и на будущее (симметрия с уже собираемым на фронтенде `gtpMoves(...)`) — **в этом срезе промпт-билдер его не рендерит** (см. ниже, «Провайдер»); используются только `analysis.rootInfo`/`analysis.moveInfos`. Это осознанное YAGNI-упрощение, не пробел: у существующего `build_user_prompt(finding, analysis, board_size)` тоже нет параметра `moves`, хотя `ExplainRequest` его содержит — та же асимметрия уже есть в коде и является установленным паттерном, не отклонением.

`api/ask.py` (эскиз, зеркалит структуру `api/explain.py`):

```python
router = APIRouter()

@router.post("/api/ask", response_model=AskResponse, dependencies=[Depends(require_valid_token)])
async def ask(body: AskRequest, provider: LLMProvider = Depends(get_llm_provider)) -> AskResponse:
    from baduk_backend.llm.providers.llama import LlamaProvider

    if not isinstance(provider, LlamaProvider):
        raise HTTPException(status_code=503, detail="/api/ask доступен только с провайдером llama")

    try:
        question_answer, verified = await asyncio.to_thread(
            verify_question_and_retry, provider, body.question, body.analysis, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citation = None
    if question_answer.rag_doc_id is not None:
        from baduk_backend.rag.retrieval import get_snippet_by_id
        try:
            snippet = await asyncio.to_thread(get_snippet_by_id, question_answer.rag_doc_id)
        except Exception:
            snippet = None
        if snippet is not None:
            citation = RagCitation(
                doc_id=snippet.doc_id, title=snippet.title,
                source=snippet.source, text_snippet=snippet.text_snippet,
            )

    return AskResponse(answer=question_answer.answer, verified=verified, citation=citation)
```

Нет ветки `message`-без-ответа (в отличие от `/api/explain`, где `message` используется, когда детектор ничего не нашёл) — свободный вопрос всегда получает попытку ответа; `message` в `AskResponse` зарезервирован на будущее (например, пустой/слишком длинный вопрос — но это уже покрыто pydantic-валидацией `Field(min_length=1, max_length=500)`, которая вернёт `422`, не `200` с `message`).

## Anti-hallucination: новые типы и проверка

`llm/schemas.py` — новые модели рядом с существующими `Claim`/`Explanation`:

Существующий `Claim.cited_field` типизирован как `Literal[...]`-алиас `CitedField` (не голый `str`) — тот же паттерн переносится сюда:

```python
QuestionCitedField = Literal["winrate", "scoreLead", "visits", "prior"]

class QuestionClaim(BaseModel):
    cited_field: QuestionCitedField
    cited_number: float
    cited_move: str | None = None   # None → цитата из analysis.rootInfo;
                                     # иначе → цитата из analysis.moveInfos,
                                     # где moveInfo.move == cited_move

class QuestionAnswer(BaseModel):
    answer: str
    claims: list[QuestionClaim]
    rag_doc_id: str | None = None
```

`llm/consistency.py` — новая функция `verify_question_and_retry`, зеркалит `verify_and_retry`, но:

- Проверка claim'а: `cited_move is None` → `getattr(analysis.rootInfo, cited_field, None)`; иначе ищем первый `moveInfo` в `analysis.moveInfos` с `.move == cited_move`, берём `getattr(moveInfo, cited_field, None)`. Ход не найден/поле не существует у найденного объекта → `None` → claim засчитывается как mismatch (то же поведение, что у `_true_value`, только источник — `moveInfos`, не поля находки).
- Допуск на числа — тот же `FLOAT_TOLERANCE = 0.01`, `visits` — целочисленное сравнение (переиспользуются существующие константы модуля).
- Пустой `claims[]` = не verified — та же защита от «прошёл проверку просто ничего не процитировав» (`_is_verified`'s текущая логика).
- RAG-проверка: `_rag_doc_id_valid`-аналог, но `query = question` (сам текст вопроса пользователя), а не `build_rag_query(finding)` — согласовано с тем, что модель сама решает искать, а бэкенд детерминированно строит query из того, что и так уже есть под рукой (вопрос), без нового способа его синтезировать.
- Фолбэк при исчерпании ретраев — НЕ шаблонный текст, построенный из полей находки (для открытого вопроса нет такой структуры), а **безопасный дословный дамп `rootInfo`**, корректный по построению:

```python
def _fallback_answer(analysis: AnalyzeResponse) -> QuestionAnswer:
    answer = (
        "Не удалось получить проверенный ответ на этот вопрос. "
        f"Точные данные текущей позиции: winrate={analysis.rootInfo.winrate:.2f}, "
        f"scoreLead={analysis.rootInfo.scoreLead:.2f}, visits={analysis.rootInfo.visits}. "
        "Эти числа — напрямую из анализа KataGo; содержательный текстовый ответ "
        "на ваш вопрос проверить не удалось."
    )
    return QuestionAnswer(answer=answer, claims=[])
```

Сигнатура: `verify_question_and_retry(provider: LlamaProvider, question: str, analysis: AnalyzeResponse, board_size: int) -> tuple[QuestionAnswer, bool]` — принимает `LlamaProvider`, не абстрактный `LLMProvider` (единственный вызывающий уже проверил `isinstance` на уровне эндпоинта).

## Провайдер: `llama.py` + `prompts.py`

`prompts.py` — новые константы/функции рядом с существующими:

- `ASK_SYSTEM_PROMPT` — вариант `SYSTEM_PROMPT` под открытый вопрос: тренер отвечает на вопрос игрока про текущую позицию, обязательно цитирует числа только из переданных данных через `record_answer`, никогда не выдумывает числа.
- `ANSWER_TOOL_PARAMETERS` / `ANSWER_WITH_RAG_TOOL_PARAMETERS` — JSON-схемы под `QuestionAnswer`, зеркалят `EXPLANATION_TOOL_PARAMETERS`/`EXPLANATION_WITH_RAG_TOOL_PARAMETERS`, но `claims[].items` без `finding_id`/`text`, зато с `cited_move: {"type": ["string", "null"]}`.
- `ASK_DECISION_TOOL_PARAMETERS` — `oneOf` (`retrieve_knowledge` / `record_answer`), зеркалит `RAG_DECISION_TOOL_PARAMETERS`.
- `build_ask_user_prompt(question: str, analysis: AnalyzeResponse, board_size: int) -> str` — включает `rootInfo` (как у `build_user_prompt`) **и** топ-кандидатов из `analysis.moveInfos` (координаты через уже существующий `xy_to_gtp`, board_size), т.к. вопрос может быть про конкретный ход-кандидат, а не только про текущую агрегированную оценку; плюс сам текст вопроса.

`llama.py` — новый метод `LlamaProvider.answer_question`, структурно идентичен `complete()` (тот же цикл: без RAG — прямой вызов; с RAG — `oneOf`-решение → при `retrieve_knowledge` поиск с `query=question` → финализация с `ANSWER_WITH_RAG_TOOL_PARAMETERS`), только использует новые промпт/схема-константы и возвращает `QuestionAnswer` вместо `Explanation` (через новый `_validate_question_answer(data, finish_reason) -> QuestionAnswer`, аналог `_validate_explanation`). Метод НЕ входит в `LLMProvider`-протокол.

## Frontend

- `ipc/client.ts`: `AskRequest`/`AskResponse` (зеркалят backend-схемы), `askQuestion(request: AskRequest): Promise<AskResponse>` (тот же паттерн ошибок, что у `explainPosition`/`explainOpening` — `${response.status}`+`body.detail`).
- `LlmExplanationPanel.tsx`: новый независимый блок состояния — `question` (текст инпута, `useState<string>('')`), `askStatus`/`askResult`/`askErrorMessage` (тот же `'idle'|'loading'|'done'|'error'` паттерн). Сброс — по смене `nodeId` (как у существующего `handleExplain`-блока, НЕ `gameLoadSequence`, т.к. вопрос привязан к конкретной позиции, а не к «сессии партии» вроде дебюта). Кнопка «Спросить» задизейблена без `currentMoveAnalysis.value`, при пустом вопросе или на активном запросе. Если бэкенд вернул `503` (провайдер не `llama`) — тот же `askErrorMessage`-блок показывает текст ошибки; поле ввода не скрывается заранее (фронтенд не знает активного провайдера).
- Секция рендерится в `LlmExplanationPanel.tsx` между существующими блоками «Объяснить эту позицию» и «Дебют».

## Ошибки

- Пустой/слишком длинный вопрос → `422` (pydantic-валидация `AskRequest.question`, `min_length=1`/`max_length=500`).
- Активный провайдер не `llama` → `503`, понятный `detail`.
- Провайдер упал (сеть/таймаут/битый JSON от модели) → `503` (тот же паттерн, что у `/api/explain`).
- Численное расхождение в claim'ах → НЕ ошибка, а внутренний ретрай-цикл (до 2 попыток) с fallback на верифицированный дамп `rootInfo` при исчерпании — тот же паттерн, что у трёх существующих сценариев, `200` в любом случае (кроме превышения запроса к самому провайдеру).
- RAG недоступен (`chromadb`/`sentence_transformers` не установлены или `rag_store/` не существует) → та же деградация, что уже есть у `_rag_available()` — эндпоинт работает без RAG, `rag_doc_id` всегда `None`.

## Тестирование

- `test_ask.py` (эндпоинт, мокает `LlamaProvider`): 200 с verified-ответом; 200 с fallback-ответом после исчерпания ретраев; 503 при не-`llama` провайдере; 503 при падении провайдера; 422 на пустой/слишком длинный `question`; 422 на несовпадение длины `ownership`.
- `test_consistency.py` (расширение существующего файла новыми тестами, не изменение существующих): `verify_question_and_retry` — claim совпадает с `rootInfo` → verified; claim совпадает с конкретным `moveInfo` через `cited_move` → verified; claim не совпадает ни с чем → ретрай → fallback; пустой `claims[]` → не verified; RAG doc_id не найден среди снипетов → не verified.
- `test_llama_provider.py` (расширение): `answer_question` без RAG — прямой вызов; с RAG — `retrieve_knowledge` вызывается с `query=question`, не с чем-то другим.
- Frontend: `LlmExplanationPanel.test.tsx` (расширение) — рендер поля ввода, дизейбл-состояния, успешный ответ, `503`-ошибка отображается, сброс по смене `nodeId`.
- Интеграционный тест (реальный `llama-cpp-python`, `BADUK_LLAMA_MODEL_PATH`) — по аналогии с уже существующими трёмя сценариями, самоскипается без модели.

## Критерии готовности

- Все текущие backend/frontend тесты остаются зелёными без изменений (кроме явно расширяемых `test_consistency.py`/`test_llama_provider.py`/`LlmExplanationPanel.test.tsx` — новые тесты добавляются, существующие не трогаются).
- `POST /api/ask` с реальным `llama-cpp-python` (живой прогон, по аналогии с уже подтверждённым живым прогоном других LLM-фич) даёт `200` с непустым `answer` и `verified` (`true` либо `false` с безопасным fallback-текстом), а не падение.
- UI показывает поле ввода вопроса в `LlmExplanationPanel`, ответ рендерится с тем же индикатором «Проверено»/«Не удалось проверить численно», что и у двух существующих сценариев.
