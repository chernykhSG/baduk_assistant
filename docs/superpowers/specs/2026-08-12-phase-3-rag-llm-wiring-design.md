# Фаза 3 (второй под-этап): подключение RAG к LLM-пайплайну — дизайн

## Контекст

Первый под-этап Фазы 3 (`docs/superpowers/specs/2026-08-11-phase-3-rag-ingestion-design.md`) реализован, смёржен в `main`, живьём проверен: `retrieve_knowledge(query, top_k) -> list[RagSnippet]` работает поверх реального Chroma-индекса из 452 карточек `Baduk-knowledge-base`. Этот срез не был подключён ни к LLM-пайплайну, ни к frontend — намеренно, по решению пользователя, зафиксированному в «Заметке на будущее» того спека.

Пользователь явно попросил начать следующий под-этап: подключить `retrieve_knowledge` к генерации объяснений (`/api/explain`). Брейнсторминг конкретизировал объём и архитектуру существенно иначе, чем исходный эскиз «Заметки на будущее» и исходное видение `docs/ARCHITECTURE.md` (§ «LLM + RAG reasoning pipeline»):

- **Только backend.** Секция цитат в `LlmExplanationPanel` (frontend) — не в этом срезе, как и в первом под-этапе.
- **Только `llama-cpp-python`-провайдер.** `claude.py`/`gemini.py` не трогаем совсем — RAG-поиск как tool для них не реализуется в этом срезе. Причина: у Claude/Gemini уже есть родной forced tool-use API, но именно поэтому расширение под них — отдельная, архитектурно более простая задача на будущее; сейчас фокус — на дефолтном провайдере проекта (`BADUK_LLM_PROVIDER=llama`), для которого до этого среза концепции tool-вызова не существовало вообще (только grammar-constrained JSON под фиксированную схему).
- **Agentic-решение, детерминированный query.** Модель сама решает, нужен ли поиск (агентно, как и задумывал `ARCHITECTURE.md`), но не сочиняет сам текст поискового запроса — он строится нами детерминированно из полей `Finding`. Это сознательный гибрид: полная агентность в формулировке запроса потребовала бы доверять малой локальной модели ещё и в этом, а её решение «искать/не искать» — достаточно, чтобы называться agentic tool-use, и не рискует качеством самого запроса.
- **`rag_doc_id` с проверкой сразу**, не отложено на будущее — anti-hallucination гарантия для RAG-цитат нужна с первого дня той же природы, что уже есть для числовых `claims` (см. `docs/superpowers/specs/2026-08-05-phase-2-weak-group-explanation-design.md` → «Совместимость с будущим ростом», где это уже было предусмотрено как аддитивное расширение `Claim`/`Explanation`).

Технический риск главной идеи (заставить модель одним structured-output-вызовом выбрать между «искать» и «финализировать» через `oneOf`-JSON-схему) снят: проверено напрямую в исходниках `llama.cpp`/`llama-cpp-python` (`json_schema_to_grammar`/`llama_grammar.py`, метод `visit()`) — оба поддерживают `oneOf`/`anyOf` и `const` на любом уровне схемы, включая корневой.

## Поток вызовов

`LlamaProvider.complete()` делает **до двух** вызовов модели вместо одного (только когда RAG доступен — см. «Доступность и деградация»):

1. **Решающий вызов.** Grammar форсит `oneOf` из двух веток:
   - `{"tool": "retrieve_knowledge"}` — модель решила искать;
   - `{"tool": "record_explanation", "summary": ..., "claims": [...], "rag_doc_id": ...}` — модель сразу финализирует, `rag_doc_id` опционален (обычно `null`, если поиска не было).
2. Если выбран `retrieve_knowledge` — мы (не модель) считаем `query` детерминированно из `Finding` (см. «Query»), реально вызываем `retrieve_knowledge(query, top_k=3)`, подмешиваем найденные фрагменты (`title`/`source`/`doc_id`/`text_snippet`) в промпт как дополнительный блок контекста и делаем **второй, финальный** вызов — grammar форсит **только** ветку `record_explanation` (не весь `oneOf` заново). Это гарантирует, что поиск не может зациклиться: максимум одна попытка поиска на один вызов `complete()`.

Если модель сразу выбрала `record_explanation` — второго вызова нет, поведение неотличимо от текущего однопроходного вызова.

**Второй вызов — независимый однопроходный, не продолжение диалога.** Не пытаемся собрать multi-turn `messages` с «эхом» ответа модели на решающем шаге (это зависело бы от конкретного chat-шаблона GGUF-модели и было бы хрупко — в проекте и так нет обёртки над `llama_cpp`'s нативным tool-calling API, только grammar-constrained JSON). Вместо этого второй вызов — свежий `create_chat_completion` с тем же `system`-сообщением (+ `RAG_SEARCH_INSTRUCTIONS`) и **новым** `user`-сообщением, собранным заново: исходный контекст находки (`build_user_prompt`) + `corrections`, если это retry, + найденные фрагменты одним блоком в конце. Модель не видит своего собственного решающего ответа как часть истории — только итоговый расширенный промпт.

`corrections` (если `complete()` вызван как retry из `verify_and_retry`) добавляются к **обоим** возможным финальным промптам — и к решающему вызову (на случай, если модель на этот раз решит не искать), и к промпту второго вызова, если поиск всё же произошёл (собирается заново вместе с фрагментами, не наследуется от решающего вызова).

`claude.py`/`gemini.py` не изменяются вообще.

## Схема и данные

**`Explanation` (`backend/src/baduk_backend/llm/schemas.py`) — новое опциональное поле:**

```python
class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
    rag_doc_id: str | None = None
```

На уровне `Explanation`, не `Claim` — цитата на карточку базы знаний одна на всё объяснение, не привязана к конкретному числовому утверждению.

**Решающая схема (`backend/src/baduk_backend/llm/prompts.py`, новая — используется только `llama.py`):**

```python
RAG_DECISION_TOOL_PARAMETERS = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"tool": {"const": "retrieve_knowledge"}},
            "required": ["tool"],
        },
        {
            "type": "object",
            "properties": {
                "tool": {"const": "record_explanation"},
                **EXPLANATION_TOOL_PARAMETERS["properties"],  # summary, claims
                "rag_doc_id": {"type": ["string", "null"]},
            },
            "required": ["tool", "summary", "claims"],
        },
    ]
}
```

Второй (форс-финализирующий) вызов после поиска использует ту же вторую ветку схемы напрямую — без `oneOf`, без `tool`-обёртки. Эта расширенная схема — отдельная именованная константа, от которой решающая обёртка производна (не дублирование):

```python
EXPLANATION_WITH_RAG_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        **EXPLANATION_TOOL_PARAMETERS["properties"],  # summary, claims
        "rag_doc_id": {"type": ["string", "null"]},
    },
    "required": ["summary", "claims"],
}

RAG_DECISION_TOOL_PARAMETERS = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"tool": {"const": "retrieve_knowledge"}},
            "required": ["tool"],
        },
        {
            "type": "object",
            "properties": {
                "tool": {"const": "record_explanation"},
                **EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"],
            },
            "required": ["tool", "summary", "claims"],
        },
    ]
}
```

`llama.py`'s форс-финализирующий вызов (после поиска, и обычный однопроходный вызов, когда RAG вообще недоступен — с той лишь разницей, что во втором случае используется `EXPLANATION_TOOL_PARAMETERS` без `rag_doc_id`, а не `EXPLANATION_WITH_RAG_TOOL_PARAMETERS`) использует `EXPLANATION_WITH_RAG_TOOL_PARAMETERS` как `response_format`'s `schema`, без `tool`-обёртки.

## Query

Строится нами, не моделью — новая функция `build_rag_query(finding: Finding) -> str` в `backend/src/baduk_backend/llm/prompts.py`. Естественный текст на русском под стиль карточек базы (семантический поиск через BGE-M3), не дамп полей находки:

- `weak_group`: `"слабая группа камней с недостатком глаз и территории"` — без конкретных чисел.
- `mistake`: `"ошибка хода, потеря очков на стадии {stage}"`, где `stage` — `opening`/`middlegame`/`endgame`.

Применяется к обоим типам находок единообразно — `build_rag_query()` ветвится по `finding.type`, как уже делает `build_user_prompt()`.

Эта функция переиспользуется в двух местах: `llama.py` (реальный вызов `retrieve_knowledge` при поиске) и `consistency.py` (независимый пересчёт валидного набора `doc_id` для проверки цитаты — см. «Anti-hallucination проверка»).

## Доступность и деградация

`LlamaProvider` должен молча работать без RAG в трёх случаях: `[rag]`-экстра не установлена, `backend/rag_store/` не существует (ingestion не запускался), или оба сразу.

```python
def _rag_available(store_path: Path = DEFAULT_STORE_PATH) -> bool:
    try:
        from baduk_backend.rag.retrieval import retrieve_knowledge  # noqa: F401
    except ImportError:
        return False
    return store_path.exists()
```

Вызывается **на каждый запрос** (не кэшируется в `__init__`) — дёшево, и не требует перезапуска backend после ручного `python -m baduk_backend.rag.ingest`.

- Если `_rag_available()` вернул `False` — решающий вызов не делается вообще: `complete()` сразу форсит сегодняшнюю единственную схему `EXPLANATION_TOOL_PARAMETERS`, без `oneOf`, без `rag_doc_id`-инструкций в промпте. Полностью совпадает с сегодняшним поведением — ноль риска регрессии для тех, кто не поставил `[rag]` или не запускал ingestion.
- Если `_rag_available()` вернул `True`, но сам вызов `retrieve_knowledge()` внутри `complete()` неожиданно упал (гонка: store удалили между проверкой и вызовом, повреждённый файл и т.п.) — не роняем `/api/explain` в 503, а трактуем как «поиск не дал результатов» и продолжаем на форс-финализирующем вызове без RAG-контекста.

## Anti-hallucination проверка `rag_doc_id`

`consistency.py` не доверяет провайдеру — как и для числовых `claims`, независимо пересчитывает истину:

```python
def _rag_doc_id_valid(rag_doc_id: str | None, finding: Finding) -> bool:
    if rag_doc_id is None:
        return True  # ничего не процитировано - нечего проверять
    query = build_rag_query(finding)
    try:
        snippets = retrieve_knowledge(query, top_k=3)
    except RuntimeError:
        return False  # store недоступен - модель не могла легитимно его процитировать
    return rag_doc_id in {s.doc_id for s in snippets}
```

Встраивается в существующий `_is_verified`/`_mismatches`-цикл `verify_and_retry` наравне с числовыми claims — если `rag_doc_id` не входит в реально доступный (пересчитанный нами) набор, это попадает в `corrections` тем же способом, что и неверное число:

> `Ты сослался на doc_id="{rag_doc_id}", которого не было среди найденных материалов - убери цитату или используй настоящий doc_id.`

Модель получает шанс исправиться в рамках уже существующего `MAX_CONSISTENCY_RETRIES=2`. `retrieve_knowledge` детерминирован для одного и того же `query` и неизменного индекса внутри одного запроса — повторный пересчёт в `consistency.py` даёт тот же набор, что видела модель при поиске.

## Системный промпт

`llama.py` получает собственную добавку к промпту (общий `SYSTEM_PROMPT` из `prompts.py`, которым пользуются и Claude/Gemini, не трогаем — им это неприменимо):

```python
RAG_SEARCH_INSTRUCTIONS = """
У тебя есть доступ к базе знаний Го через retrieve_knowledge. Если находка \
напоминает известный принцип или распространённую ошибку, поиск поможет дать \
более обоснованное объяснение. Если сомневаешься - лучше поискать. Если явной \
связи с базой знаний нет - отвечай record_explanation сразу, без поиска.
"""
```

Добавляется к `system`-сообщению **только когда `_rag_available()` истинно** — иначе модель увидит инструкцию про инструмент, которого нет в схеме.

## Тестирование

- **Юнит-тесты `llama.py`** на fake `llama_cpp.Llama` (как уже есть): (1) RAG недоступен → один вызов, схема без `oneOf`, поведение = сегодняшнее; (2) RAG доступен, модель выбирает `record_explanation` сразу → один вызов; (3) RAG доступен, модель выбирает `retrieve_knowledge` → два вызова, второй содержит найденные фрагменты в промпте, итоговый `Explanation.rag_doc_id` заполнен.
- **Юнит-тесты `consistency.py`**: `rag_doc_id=None` проходит без проверки; валидный `rag_doc_id` (входит в пересчитанный набор) проходит; галлюцинированный `rag_doc_id` (не входит) даёт `corrections` и триггерит retry-цикл, как для числовых claims.
- **Реальный integration-тест** (`@pytest.mark.integration`) — требует одновременно `BADUK_LLAMA_MODEL_PATH` **и** реально собранный `backend/rag_store/` (предварительно прогнанный `python -m baduk_backend.rag.ingest`) — самоскипается, если хоть одного нет. Прогоняется на позиции, где в базе точно есть похожая карточка (например, находка `weak_group` про недостаток глаз), проверяет, что `rag_doc_id` заполнен и прошёл верификацию.

## Не входит (осознанно отложено на будущие под-этапы)

- Секция цитат в `LlmExplanationPanel` (frontend).
- RAG-поиск как tool для Claude/Gemini.
- Полностью агентная формулировка query самой моделью.
- `category`-фильтр и `board_context` в `retrieve_knowledge` (не появился и в первом под-этапе).
- Свободные вопросы к LLM без привязки к `finding_id` (отдельный под-этап Фазы 2, независимо от RAG).

## Известные компромиссы

- **Латентность.** При выборе поиска `complete()` делает 2 вызова модели вместо 1; при retry-цикле `verify_and_retry` (до `MAX_CONSISTENCY_RETRIES=2` дополнительных попыток) в худшем случае это может дать до 6 вызовов модели на один `/api/explain`-запрос. Приемлемо для локальной модели без API-стоимости за токен, но заметно на CPU-инференсе.
- **Двойной вызов `retrieve_knowledge`** на один успешный поиск: один раз реально в `llama.py` (получить фрагменты для промпта), второй раз в `consistency.py` (пересчитать валидный набор для проверки цитаты) — по одному и тому же детерминированному `query`. Дублирование сознательное (та же анти-hallucination философия, что уже применена к числовым `claims`: не доверять провайдеру, пересчитывать независимо) — не вызов модели, а операция эмбеддинга+Chroma. **Исправлено при финальном ревью реализации (2026-08-12): здесь была ошибочная оценка стоимости — «миллисекунды».** Замер на реальном железе показал, что `SentenceTransformer("BAAI/bge-m3")` без кэширования конструируется заново на каждый вызов `get_embedding_model()` и стоит **7.5–14.4 секунды** (не миллисекунды) — при отсутствии кэша это давало на один `/api/explain`-запрос до 8 полных загрузок модели (~60с) поверх инференса самого llama.cpp. Исправлено кэшированием через `functools.lru_cache(maxsize=1)` в `backend/src/baduk_backend/rag/store.py::get_embedding_model()` — модель теперь грузится один раз за время жизни процесса backend'а, а не на каждый RAG-вызов. Урок для будущих спеков в этом проекте: не оценивать стоимость операций с ML-моделями (даже эмбеддинг-моделей, не только LLM) на глаз — замерять или явно помечать оценку как неподтверждённую.
