# Фаза 2 (второй под-этап): детектор `mistake` — дизайн

## Контекст

Первый срез Фазы 2 (`weak_group`-детектор, Claude-провайдер, `/api/explain`) реализован и в `main`. Пользователь явно попросил продолжить «остаток Фазы 2» и выбрал начать с дополнительных детекторов — `mistake`/`opening_loss` из `docs/ARCHITECTURE.md`. Этот документ описывает только `mistake` (детектор цены сыгранного хода в очках); `opening_loss` (накопленная `Δ` за первые N ходов дебюта) — намеренно отложен на следующий под-этап, он надстраивается над готовым `mistake` и имеет другую форму входа (диапазон ходов, а не одна позиция).

Работа ведётся в новой ветке `phase-2-mistake-detector` (от `main`).

**Важная ревизия по сравнению с ожиданием первого спека:** тот спек предполагал, что новые детекторы «не требуют смены формы запроса» к `/api/explain`. Это оказалось неверно для `mistake` — детектору нужна не только текущая позиция, но и позиция после реально сыгранного хода (см. ниже, почему). `ExplainRequest` меняется — это не ошибка первого среза, а не предвиденная на тот момент деталь.

## Scope этого под-этапа

**Входит:**
- Детектор `mistake` (`feature_extraction/mistake.py`).
- Discriminated-union `Finding` (`weak_group` | `mistake`) вместо плоской модели на один тип.
- Расширение `ExplainRequest` (`analysisAfter`, `nextMove`), обобщение `/api/explain` на выбор одной из нескольких находок.
- Обобщение LLM-промпта (`prompts.py`) и anti-hallucination проверки (`consistency.py`) на оба типа находок.
- Frontend: `analysisByTurn`-lookup следующего хода в `LlmExplanationPanel`, обновление TS-типа `Finding`.

**Не входит (осознанно отложено):**
- `opening_loss`-детектор — следующий под-этап.
- Версионированный JSON-конфиг детекторов и calibration/backtesting harness (self-consistency re-scan, tsumego-корпус, пользовательский фидбек) — отдельный под-этап «Калибровка/бэктестинг», по решению пользователя не начинается сейчас. Пороги этого детектора — стартовые, некалиброванные под этот проект (см. ниже источник).
- Свободные вопросы к LLM (чат) — отдельный, независимый под-этап.
- Классификация находки `mistake` по таксономии именованных паттернов ошибок (`Baduk-knowledge-base/knowledge-base/wiki/mistakes/`, 150+ карточек) — концептуально интересное будущее расширение (см. «Заметка на будущее» ниже), но требует RAG-retrieval слоя (Фаза 3), не относится к детерминированному детектору.
- Ручная сквозная приёмка на реальной партии — не обязательна для мержа (тот же паттерн, что и `weak_group`); `detect_mistake` полностью детерминированная и покрывается юнит-тестами.

## Откуда взяты пороги (вместо калибровки)

`docs/ARCHITECTURE.md` даёт только иллюстративный пример стадийной таблицы (`{opening: 3.0, middlegame: 2.0, endgame: 1.0}` очка) — не выведен из данных. Вместо изобретения новых чисел взята реальная, проверенная на практике лестница из **KaTrain** (открытый инструмент обучения кю-игроков, уже сравнивавшийся в `ARCHITECTURE.md` при выборе стека): `eval_thresholds = [12, 6, 3, 1.5, 0.5, 0]` очков, **без** поправки на стадию игры (KaTrain использует единую лестницу).

Источник: `katrain/config.json` (`sanderland/katrain`, MIT), раздел `trainer.eval_thresholds`.

Эти числа — стартовая, явно помеченная как некалиброванная под этот проект оценка (тот же паттерн честности, что уже в `feature_extraction/config.py` для `weak_group`). Настоящая калибровка (self-consistency proxy на корпусе реальных партий, самый практичный первый шаг из трёх источников ground truth, уже описанных в `ARCHITECTURE.md`) — работа будущего под-этапа «Калибровка/бэктестинг».

## Формула

`reportAnalysisWinratesAs = BLACK` уже зафиксировано в `backend/src/baduk_backend/config/profile.py` (решение из финального ревью Фазы 1) — `scoreLead` везде даётся с точки зрения чёрных, не «текущего игрока». Поэтому цена хода для игрока `mover`:

```
mover_favorability(pos) = scoreLead(pos) if mover == "B" else -scoreLead(pos)
Δ = mover_favorability(до хода) − mover_favorability(после хода)   # > 0 = потеря очков
```

`mover` — цвет хода, соединяющего позицию «до» с позицией «после» (`nextMove[0]`).

- **Порог создания находки:** `Δ ≥ THRESHOLD_MISTAKE = 0.5` (нижняя ненулевая граница лестницы KaTrain) — ниже это шум, находка не создаётся, как и у `weak_group`.
- **`severity`** (переиспользуется существующий `Literal["low","medium","high"]`, без нового 6-уровневого enum — YAGNI): `high` при `Δ ≥ 6.0`, `medium` при `1.5 ≤ Δ < 6.0`, `low` при `0.5 ≤ Δ < 1.5` — границы взяты из реальных отсечек KaTrain, не придуманы заново.
- **`stage`** (`opening`/`middlegame`/`endgame`) — из `ARCHITECTURE.md`: `stage = opening`, если `move_number ≤ board_area · k_open`; `endgame`, если `empty_points_left ≤ board_area · k_end`; иначе `middlegame` (`k_open = 0.12`, `k_end = 0.15`, конфигурируемые доли). Поле информативное (попадает в промпт и будущий Паспорт игрока), не влияет на порог/`severity` в этом под-этапе.
- **`confidence`** = `min(rootInfo.visits_до, rootInfo.visits_после) / MIN_RELIABLE_VISITS` — обе позиции должны быть надёжно посчитаны, иначе `Δ` шумит.

## Backend: `Finding` — discriminated union

`feature_extraction/schemas.py`, вместо плоской модели на один тип:

```python
class WeakGroupFinding(BaseModel):
    finding_id: str
    type: Literal["weak_group"] = "weak_group"
    turn_number: int
    stones: list[tuple[int, int]]
    color: Literal["B", "W"]
    weak_score: float
    own_certainty: float
    boundary_certainty: float
    liberties: int
    severity: Literal["low", "medium", "high"]
    confidence: float

class MistakeFinding(BaseModel):
    finding_id: str
    type: Literal["mistake"] = "mistake"
    turn_number: int
    color: Literal["B", "W"]
    move: str                      # GTP-координата сыгранного хода
    delta_score: float
    stage: Literal["opening", "middlegame", "endgame"]
    severity: Literal["low", "medium", "high"]
    confidence: float

Finding = Annotated[WeakGroupFinding | MistakeFinding, Field(discriminator="type")]
```

`WeakGroupFinding` — переименование текущего `Finding` без изменения полей (обратная совместимость сохраняется как тип, не как имя класса).

## Backend: `feature_extraction/mistake.py`

Новый файл, чистая функция, зеркалит стиль `weak_group.py`:

```python
def detect_mistake(
    board: list[list[str | None]],   # позиция ДО хода — та же доска, что уже
                                      # строит explain.py для weak_group
                                      # (apply_moves(body.moves, ...)), без
                                      # повторного пересчёта
    analysis_before: AnalyzeResponse,
    analysis_after: AnalyzeResponse,
    next_move: tuple[str, str],   # (color, gtp-coord)
    board_x_size: int,
    board_y_size: int,
    turn_number: int,
) -> MistakeFinding | None:
    ...
```

Считает `Δ` по формуле выше, `severity`/`confidence`. `stage` — по количеству пустых точек на переданной доске `board` (позиция до хода; сам ход её пренебрежимо не меняет для целей грубой классификации стадии — реконструкция отдельной "после"-доски не нужна) и `move_number = turn_number` относительно `board_area · k_open`/`k_end`. Возвращает `None`, если `Δ < THRESHOLD_MISTAKE`.

`feature_extraction/config.py` — новые константы рядом с существующими `weak_group`-константами:
```python
THRESHOLD_MISTAKE = 0.5
MISTAKE_SEVERITY_HIGH = 6.0
MISTAKE_SEVERITY_MEDIUM = 1.5
K_OPEN = 0.12
K_END = 0.15
```

## Backend: `ExplainRequest`/`/api/explain` — расширение и приоритет находок

`api/schemas.py`:
```python
class ExplainRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse                       # позиция ДО хода — как в первом срезе
    analysisAfter: AnalyzeResponse | None = None     # позиция ПОСЛЕ реально сыгранного хода
    nextMove: tuple[str, str] | None = None          # (color, gtp-coord) — сам этот ход

    @model_validator(mode="after")
    def _analysis_after_and_next_move_together(self) -> "ExplainRequest":
        if (self.analysisAfter is None) != (self.nextMove is None):
            raise ValueError("analysisAfter and nextMove must both be set or both be None")
        return self
```
`analysisAfter.ownership` не обязателен (`mistake` использует только `rootInfo`) — существующий валидатор `_ownership_matches_board_size` продолжает проверять только `analysis.ownership`, не `analysisAfter.ownership`.

`api/explain.py` — приоритет находок (по решению пользователя: при конфликте `mistake` приоритетнее, т.к. напрямую объясняет сделанный ход):
```python
board = apply_moves(body.moves, body.boardXSize, body.boardYSize)
weak_finding = detect_weak_group(board, body.boardXSize, body.boardYSize, body.analysis, turn_number)

mistake_finding = None
if body.analysisAfter is not None and body.nextMove is not None:
    mistake_finding = detect_mistake(
        board, body.analysis, body.analysisAfter, body.nextMove,
        body.boardXSize, body.boardYSize, turn_number
    )

finding = mistake_finding or weak_finding
if finding is None:
    return ExplainResponse(message="Ничего заметного не найдено в этой позиции")
```
Остальная логика хендлера (вызов `verify_and_retry`, обработка ошибок провайдера → `503`) не меняется.

## Backend: обобщение промпта и anti-hallucination проверки

`llm/prompts.py`:
- `SYSTEM_PROMPT` — формулировки "слабой группы" обобщаются на "находку" (инструкции про запрет выдумывания чисел, hedging по `confidence`, запрет переоценки позиции — уже type-agnostic).
- `EXPLANATION_TOOL_PARAMETERS.cited_field.enum` — добавляется `"delta_score"`.
- `build_user_prompt()` — ветвление по `finding.type`: `weak_group` форматирует камни группы (как сейчас), `mistake` форматирует сыгранный ход, `delta_score`, `stage`.

`llm/consistency.py`:
```python
_FINDING_FIELDS: dict[str, set[str]] = {
    "weak_group": {"weak_score", "own_certainty", "boundary_certainty", "liberties"},
    "mistake": {"delta_score"},
}
```
`_true_value()` смотрит в `_FINDING_FIELDS[finding.type]`. `_fallback_explanation()` — ветка по `finding.type` с отдельным шаблонным текстом для `mistake` ("Обнаружена потеря очков на ходе {turn_number}: Δ={delta_score:.2f}..."). Остальное (`_claim_matches`, `_mismatches`, `verify_and_retry`) уже type-agnostic, работает через `finding.finding_id`/`_true_value()` — не меняется.

## Frontend

- `ipc/client.ts`: `Finding` → `WeakGroupFinding | MistakeFinding` (union по `type`), зеркалит backend-схему.
- `LlmExplanationPanel.tsx`: перед вызовом `explainPosition()` смотрит на первого ребёнка текущего узла дерева (реальное продолжение партии, не гипотетическая ветка пользователя). Если у `analysisByTurn` есть запись для этого ребёнка — передаёт её как `analysisAfter` и его SGF move-свойство (`B`/`W`) как `nextMove`. Если ребёнка нет (последний ход партии/ветки) — оба поля не передаются, проверяется только `weak_group`. Рендер результата не меняется — уже type-agnostic (`result.explanation.summary`), в коде фронтенда нет ни одного места, разбирающего `finding.type`/`weak_score`/др. специфичные поля.

## Ошибки

- `analysisAfter` без `nextMove` (или наоборот) — `422` от pydantic-валидатора, как и существующая проверка `ownership`-длины.
- Остальное — без изменений от первого среза (`503` на сбой провайдера, `message` при отсутствии находок, `verified: false` при исчерпанных retries).

## Тестирование

**Backend:**
- `tests/feature_extraction/test_mistake.py` (новый) — знак `Δ` корректен для **обоих** цветов (`mover="B"` и `mover="W"` отдельно проверены, самое рискованное место дизайна); границы `THRESHOLD_MISTAKE`/`severity`/`stage`; `confidence = min(visits_до, visits_после)`.
- `tests/llm/test_consistency.py` — расширить кейсами на `mistake`-находку (per-type `_FINDING_FIELDS`, fallback-текст).
- `tests/llm/test_prompts.py` — `cited_field` enum содержит `delta_score`; `build_user_prompt` ветвится по `type`.
- `tests/test_api_explain.py` — новые сценарии: только `weak_group` (без `analysisAfter`/`nextMove`, регрессия старого поведения); только `mistake`; оба сработали → побеждает `mistake`; `analysisAfter` без `nextMove` → `422`.

**Frontend:**
- `LlmExplanationPanel.test.tsx` — у текущего узла есть ребёнок в `analysisByTurn` → `explainPosition` вызван с `analysisAfter`/`nextMove`; ребёнка нет → вызван без них.
- Typecheck подтверждает union-тип `Finding` не ломает существующий рендер.

## Критерии готовности

- На фиксированной тестовой SGF с заранее известным дорогим ходом `/api/explain` (с переданными `analysisAfter`/`nextMove`) возвращает `MistakeFinding` с ожидаемым `delta_score`/`severity` и `verified: true`.
- Существующее поведение `weak_group` (без `analysisAfter`/`nextMove`) не сломано — регрессионные тесты первого среза остаются зелёными без изменений.
- Все существующие backend/frontend тесты остаются зелёными, typecheck проходит.

## Заметка на будущее (не в этом под-этапе)

`Baduk-knowledge-base` (`C:\GithubProject\Baduk-knowledge-base`) — отдельный репозиторий, 152 карточки принципов/ошибок Го на русском в формате LLM Wiki, готовые под RAG (Фаза 3). Таксономия `wiki/mistakes/*.md` (150+ именованных паттернов, например «выбран большой пункт вместо срочного») могла бы в будущем обогатить `MistakeFinding` классификацией *какого рода* ошибка произошла, а не только числом потерянных очков — но это требует RAG-retrieval слоя для сопоставления позиции с паттерном, не относится к детерминированному feature-extraction. Рассмотреть при проектировании Фазы 3 или как её ретроактивное расширение — аналогично уже зафиксированной в `task_plan.md` связи Фаза 2 ↔ Фаза 4.
