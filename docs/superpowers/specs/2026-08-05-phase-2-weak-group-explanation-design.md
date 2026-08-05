# Фаза 2 (первый срез): LLM-объяснение слабой группы — дизайн

## Контекст

Фаза 1 (SGF viewer + KataGo-анализ) полностью реализована, принята пользователем и в `main`. Согласно `docs/ARCHITECTURE.md` → «Поэтапный MVP-roadmap», Фаза 2 — «LLM-объяснения поверх KataGo (без RAG)»: feature-extraction слой (детекторы + версионированный конфиг + calibration/backtesting harness + self-consistency проверка), LLM Orchestrator с provider-абстракцией (Claude/OpenAI/Ollama), объяснения тоном тренера строго на числах движка, без tool-use.

Этот объём — несколько связанных подсистем, а не одна фича. Пользователь явно попросил разбить Фазу 2 на под-этапы вместо одного большого захода. **Этот документ описывает только первый под-этап** — минимальный вертикальный срез: один детектор, один LLM-провайдер, объяснение по клику, полная anti-hallucination защита, без калибровки. Работа ведётся в ветке `phase-2-llm-explanations`.

## Scope этого среза

**Входит:**
- Детектор `weak_group` (единственный на этот срез).
- LLM-провайдер — Claude API (единственная реализация за интерфейсом-заглушкой).
- Триггер объяснения — по клику пользователя на текущую позицию (не автоматически на каждый ход стрима).
- Полная двухступенчатая anti-hallucination защита: structured `claims[]` + post-hoc numeric consistency checker с перегенерацией.
- Транспорт — синхронный `HTTP POST`.
- UI — переключатель «KataGo / LLM» в существующем блоке анализа; вкладка LLM показывает кнопку «Объяснить эту позицию» и результат.
- Язык объяснения — русский.

**Не входит (осознанно отложено на будущие под-этапы той же Фазы 2):**
- Детекторы `mistake`/`opening_loss`.
- Провайдеры OpenAI/Ollama.
- Версионированный JSON-конфиг детекторов и calibration/backtesting harness (self-consistency re-scan, tsumego-корпус, пользовательский фидбек).
- Свободный текстовый вопрос к LLM (чат) — привязка anti-hallucination к одному `finding_id` не покрывает произвольный вопрос; это отдельный будущий под-этап.
- Token-streaming текста объяснения.
- Подсветка камней слабой группы на доске.
- RAG (Фаза 3 целиком).

## Backend: восстановление доски и группировка камней

Backend сейчас не хранит и не вычисляет положение камней на доске — это делает только frontend (`@sabaki/go-board`), для рендера. `weak_group`-детектору для union-find по группам и подсчёта дыханий нужна доска на backend, поэтому backend **сам** восстанавливает её из `moves` (тех же данных, что уже уходят в KataGo через `/api/analyze`), а не доверяет вычисленному на frontend состоянию.

- `backend/src/baduk_backend/board/gtp_coords.py` — GTP-колонки (`ABCDEFGHJKLMNOPQRSTUVWXYZ`, без `I`), симметрично `frontend/src/renderer/src/board/gtpColumns.ts`; функции конвертации GTP-координаты (`"Q4"`, `"pass"`) в индексы сетки и обратно.
- `backend/src/baduk_backend/board/board_state.py` — `apply_moves(moves: list[list[str]], board_x_size: int, board_y_size: int) -> list[list[str | None]]`: проходит по ходам по порядку, расставляет камень, после каждого хода снимает группы противника с нулём дыханий (стандартное правило взятия). Легальность ходов **не перепроверяется** — этот же `moves` уже был принят KataGo в `/api/analyze` ранее в этой же партии, повторная валидация избыточна для этого среза.
- `backend/src/baduk_backend/board/groups.py` — `find_groups(board: list[list[str | None]]) -> list[Group]`: union-find по 4-связности одного цвета; `Group` — `stones: list[(x,y)]`, `color: str`, `liberties: int` (уникальные пустые соседние точки).

## Backend: feature-extraction (`weak_group`)

`backend/src/baduk_backend/feature_extraction/weak_group.py`, формулы из `docs/ARCHITECTURE.md` дословно:

- `own_certainty(G) = mean(|ownership[p]|` по всем точкам группы `G)`.
- `boundary_certainty(G) = mean(|ownership[p]|` по пустым точкам в радиусе 1 линии от `G)`.
- `pv_focus(G) = доля топ-K` ходов из `moveInfos`, чьи координаты лежат в пределах расстояния `D` от любого камня `G`.
- `weak_score(G) = w1·(1 − own_certainty(G)) + w2·(1 − boundary_certainty(G)) + w3·pv_focus(G) − w4·(liberties(G) / max_liberties_norm)`, результат зажимается в `[0, 1]`.
- Находка создаётся при `weak_score(G) > threshold_weak`; `confidence = min(rootInfo.visits / min_reliable_visits, 1.0)`; `severity` — `low` при `weak_score < 0.7`, `medium` при `< 0.85`, иначе `high` (границы — дословно из ARCHITECTURE.md).
- Если несколько групп проходят порог — берётся группа с максимальным `weak_score` (одна находка на запрос в этом срезе, не список).
- Ownership при `visits < min_reliable_visits` **не отбрасывается**, а даёт низкий `confidence` — как явно оговорено в ARCHITECTURE.md (находки с низкой confidence не отбрасываются детектором, а маркируются — итоговое решение показывать/скрывать их в тексте объяснения принимает промпт через hedging-язык).

`backend/src/baduk_backend/feature_extraction/config.py` — именованные константы (**не** JSON-файл, не версионировано — калибровка отложена, будет отдельным под-этапом):
```python
W1_OWN_CERTAINTY = 0.4
W2_BOUNDARY_CERTAINTY = 0.3
W3_PV_FOCUS = 0.2
W4_LIBERTIES = 0.1
MAX_LIBERTIES_NORM = 8
THRESHOLD_WEAK = 0.5
PV_FOCUS_TOP_K = 5
PV_FOCUS_DISTANCE_D = 2
MIN_RELIABLE_VISITS = 500
```
Эти значения — стартовая, неоткалиброванная оценка (веса подобраны так, чтобы `weak_score` в норме укладывался в `[0, 1]`), явно помечены комментарием как временные до calibration harness'а из будущего под-этапа.

`backend/src/baduk_backend/feature_extraction/schemas.py`:
```python
class Finding(BaseModel):
    finding_id: str
    type: Literal["weak_group"]
    turn_number: int
    stones: list[tuple[int, int]]
    weak_score: float
    own_certainty: float
    boundary_certainty: float
    liberties: int
    severity: Literal["low", "medium", "high"]
    confidence: float
```
`move_range` из общего примера в ARCHITECTURE.md заменён на `turn_number` — в этом срезе находка вычисляется заново для одной конкретной позиции по клику, а не отслеживается как персистентная сущность на протяжении нескольких ходов.

## Backend: LLM Orchestrator + Claude provider

- `backend/src/baduk_backend/llm/orchestrator.py` — минимальный протокол:
```python
class LLMProvider(Protocol):
    def complete(self, finding: Finding, analysis: AnalyzeResponse) -> Explanation: ...
```
Только один метод, нужный этому срезу — не заводится полноценная `messages`/`tools`-абстракция из ARCHITECTURE.md заранее, это было бы overengineering для одной реализации.

- `backend/src/baduk_backend/llm/providers/claude.py` — вызывает Claude API через официальный Python SDK (`anthropic`). Structured output достигается принудительным tool-use: модели передаётся один псевдо-инструмент `record_explanation(summary: str, claims: list[Claim])` с `tool_choice`, принудительно указывающим на него — модель обязана вернуть ответ в этой JSON-форме. **Это не то же самое, что tool-use в смысле ARCHITECTURE.md** (`retrieve_knowledge` и т.п., которых в Фазе 2 нет) — здесь инструмент используется исключительно как механизм принудительного структурирования ответа, LLM не получает возможности запрашивать что-либо дополнительно.
- System-промпт (на русском): объясняет находку тоном тренера для кю-игрока, обязан цитировать числа из переданного `Finding`/`AnalyzeResponse` через `claims[]`, обязан использовать hedging-язык при `confidence < 0.7` (например, «похоже», «вероятно»), не имеет права переоценивать позицию против чисел KataGo.

```python
class Claim(BaseModel):
    text: str
    finding_id: str
    cited_field: Literal["weak_score", "own_certainty", "boundary_certainty", "liberties", "visits", "winrate", "scoreLead"]
    cited_number: float

class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
```

## Backend: anti-hallucination (consistency checker)

`backend/src/baduk_backend/llm/consistency.py` — чистая функция, не LLM:
- Для каждого `Claim` берёт `cited_field`, ищет истинное значение в исходном `Finding` (`weak_score`/`own_certainty`/`boundary_certainty`/`liberties`) либо в `AnalyzeResponse.rootInfo` (`visits`/`winrate`/`scoreLead`).
- Сравнение: для `liberties`/`visits` (целые) — точное совпадение; для остальных (float) — расхождение `≤ 0.01` допустимо.
- Если хотя бы один `Claim` не совпал — перегенерация с уточняющим промптом («ты сослался на X для поля Y, но настоящее значение Z») — максимум 2 попытки (`MAX_CONSISTENCY_RETRIES = 2`).
- После исчерпания попыток — шаблонный fallback **без свободной генерации**: собирается прямо из чисел `Finding`, например: «Обнаружена слабая группа (ход {turn_number}): показатель уязвимости {weak_score:.2f}, уверенность {confidence:.2f}. Не удалось получить проверенное текстовое объяснение — эти числа стоит свериться с ходами-кандидатами вручную.»
- Ответ помечается `verified: true`, если хотя бы одна попытка прошла проверку без перегенерации fallback'а; `verified: false` — если сработал fallback.

## API: `POST /api/explain`

`backend/src/baduk_backend/api/explain.py`, аутентификация — тот же `X-Auth-Token`, что у `/api/analyze`. **Не использует `EngineManager`/`engine_lock`** — не вызывает KataGo заново, работает только с уже полученными клиентом числами.

```python
class ExplainRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse

class ExplainResponse(BaseModel):
    finding: Finding | None
    explanation: Explanation | None
    verified: bool | None
    message: str | None
```

Логика хендлера:
1. `apply_moves()` → доска → `find_groups()`.
2. Для каждой группы своего/чужого цвета — `weak_score`; если максимум `> THRESHOLD_WEAK` — строит `Finding`, иначе `ExplainResponse(finding=None, explanation=None, verified=None, message="Ничего заметного не найдено в этой позиции")`.
3. Иначе — `claude_provider.complete(finding, analysis)` → `consistency.verify_and_retry(...)` → `ExplainResponse(finding=..., explanation=..., verified=..., message=None)`.

## Frontend

- Новый компонент `frontend/src/renderer/src/analysis/AnalysisPanel.tsx` — оборачивает существующий `app-shell__chart`-блок, рендерит переключатель вкладок **«KataGo» / «LLM»** (локальный `useState`) и монтирует либо уже существующий `WinrateChart`, либо новый `LlmExplanationPanel` — сам `WinrateChart` не меняется.
- `frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx` — кнопка «Объяснить эту позицию» (активна только когда есть `analysisByTurn.get(currentNodeId)` для текущего хода); по клику — состояние загрузки → рендер `explanation.summary` (простой текст, без подсветки камней в этом срезе) либо `message`, либо баннер ошибки.
- `explainPosition()` в `frontend/src/renderer/src/ipc/client.ts` — `POST /api/explain` с `moves` (переиспользует сборку из `gameRequestBuilder.ts`, аналогично `gtpMoves()`), `boardXSize`/`boardYSize`, `analysis: analysisByTurn.value.get(currentNodeId.value)`.

## Совместимость с будущим ростом

`/api/explain` спроектирован так, чтобы дальнейшие под-этапы Фазы 2 и Фаза 3 добавлялись, а не переписывали этот эндпоинт заново — по тому же принципу, что уже применён в проекте для `/api/analyze` + `/api/analyze/stream` (два раздельных эндпоинта под разные сценарии одного и того же назначения):

- **Свободные вопросы** — добавится опциональное поле `question: str | None` в `ExplainRequest`; при его наличии — отдельная, более мягкая ветка LLM-логики вместо привязки к одному `finding_id`. Эндпоинт не переписывается, только ветвится.
- **RAG (Фаза 3)** — `retrieve_knowledge` как инструмент живёт целиком внутри `llm/providers/claude.py`, наружу через контракт эндпоинта не просачивается. Единственное упреждающее расширение — `Claim.cited_field`/`finding_id` в схеме уже сделаны отдельными именованными полями (не хардкод внутри текста), так что добавление опционального `doc_id` для RAG-цитат позже — аддитивное расширение `Claim`, не breaking change.
- **Token-streaming** — потребует WS, а не HTTP POST; появится `/api/explain/stream` рядом с текущим `/api/explain`, как уже сделано для анализа. Синхронный эндпоинт никуда не девается.
- **Другие LLM-провайдеры** (OpenAI/Ollama) — реализуют тот же `LLMProvider`-протокол, контракт эндпоинта не затрагивают вообще.
- **Другие детекторы (`mistake`/`opening_loss`)** — добавляются в `feature_extraction/`, хендлер `/api/explain` начинает перебирать несколько типов находок вместо одной — не требует смены формы запроса, только внутренней логики выбора находки.

## Конфигурация

Тот же паттерн, что уже используется для KataGo (`BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL`) — никаких ключей/путей в исходниках:
- `BADUK_CLAUDE_API_KEY` — обязателен; при отсутствии backend падает при старте с понятной ошибкой (аналогично `_build_engine_manager()`).
- `BADUK_CLAUDE_MODEL` — опционален, дефолт — актуальная модель Claude на момент реализации (конкретное значение фиксируется в implementation-плане, не хардкодится здесь).

## Ошибки

- `BADUK_CLAUDE_API_KEY` не задан — явная ошибка при старте backend, тем же способом, что и отсутствие `BADUK_KATAGO_BINARY`.
- Таймаут/ошибка Claude API — `503`, frontend показывает баннер ошибки (тот же визуальный паттерн, что уже есть для `streamError`).
- Ни одна группа не проходит порог — не ошибка, а `message: "Ничего заметного не найдено..."`.
- Consistency checker исчерпал попытки — не ошибка, а `verified: false` + шаблонный `explanation.summary`.

## Тестирование

**Backend:**
- `board_state.py`/`groups.py` — юнит-тесты на заранее известных позициях (расстановка, взятие, подсчёт дыханий групп) — без обращения к KataGo.
- `weak_group.py` — юнит-тесты формулы на синтетическом `ownership`/`moveInfos` с точно посчитанным вручную ожидаемым `weak_score`.
- `consistency.py` — юнит-тесты на модельных `Claim`-наборах (совпадение/расхождение/перегенерация/fallback) с fake `LLMProvider` (аналог `fake_katago.py` — не настоящий Claude в юнит-тестах).
- Один реальный integration-тест `/api/explain` через настоящий Claude API, гейтится через `BADUK_CLAUDE_API_KEY`, аналогично существующему `-m integration`/`BADUK_KATAGO_BINARY` паттерну.

**Frontend:**
- `LlmExplanationPanel`/`AnalysisPanel` — рендер вкладок, состояние загрузки, рендер `explanation`/`message`/ошибки (мок `explainPosition`).
- `explainPosition()` в `client.ts` — юнит-тест на форму запроса/ответа (мок `fetch`, аналогично существующим тестам `analyzePosition`).

## Критерии готовности

- На фиксированной тестовой SGF с заранее известной слабой группой `/api/explain` возвращает `Finding` с ожидаемым диапазоном `weak_score` и `verified: true`.
- Юнит-тест consistency checker'а подтверждает: LLM-объяснение цитирует именно те числа, что в `Finding`/`AnalyzeResponse` (соответствует критерию Фазы 2 из ARCHITECTURE.md → «Проверка»).
- Переключатель «KataGo/LLM» в интерфейсе визуально протестирован (аналог ручной приёмки Фазы 1) — обе вкладки корректно переключаются и не ломают уже работающий `WinrateChart`.
- Все существующие backend/frontend тесты остаются зелёными.
