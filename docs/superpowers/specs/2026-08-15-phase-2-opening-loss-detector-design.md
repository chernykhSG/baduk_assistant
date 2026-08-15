# Фаза 2 (третий под-этап): детектор `opening_loss` — дизайн

## Контекст

`weak_group` и `mistake` реализованы и в `main` (`docs/superpowers/specs/2026-08-05-phase-2-weak-group-explanation-design.md`, `docs/superpowers/specs/2026-08-11-phase-2-mistake-detector-design.md`). Тот же спек `mistake` явно отложил `opening_loss` на следующий под-этап — «надстраивается над готовым `mistake` и имеет другую форму входа (диапазон ходов, а не одна позиция)». Пользователь явно попросил продолжить «остаток Фазы 2» и выбрал начать именно с `opening_loss` (а не с калибровки/backtesting harness или свободных вопросов к LLM — оба остаются отдельными, независимыми под-этапами).

`docs/ARCHITECTURE.md`: «**Opening loss detector**: накопленная `Δ` за первые N ходов (N конфигурируем) сверх табличного порога».

Работа ведётся в новой ветке `phase-2-opening-loss-detector` (от `main`).

## Scope этого под-этапа

**Входит:**
- Детектор `opening_loss` (`feature_extraction/opening_loss.py`), вынос общей формулы `mover_favorability()` в `feature_extraction/scoring.py` (и переключение `mistake.py` на неё).
- Третий тип находки в `Finding`-union (`OpeningLossFinding`).
- Новый эндпоинт `POST /api/explain/opening` (не переиспользует `/api/explain` — другая форма входа: диапазон + явный цвет, без доски/групп).
- Обобщение `prompts.py`/`consistency.py` на три типа находок вместо двух — включая устранение двухветочного `if/else`-паттерна, из-за которого уже была Critical-регрессия при добавлении `mistake` (см. «Anti-hallucination обвязка» ниже).
- Frontend: сбор компактной дебютной последовательности из уже закэшированного `analysisByTurn`, новый блок UI (переключатель цвета + кнопка «Проанализировать дебют») в `LlmExplanationPanel.tsx`.

**Не входит (осознанно отложено):**
- Версионированный JSON-конфиг детекторов и calibration/backtesting harness — отдельный, независимый под-этап «Калибровка/бэктестинг». Пороги `opening_loss` в этом под-этапе — иллюстративные, явно помеченные как некалиброванные (без готового внешнего ориентира вроде лестницы KaTrain у `mistake` — см. ниже).
- Свободные вопросы к LLM (чат) — отдельный, независимый под-этап.
- Ручная сквозная приёмка на реальной партии — не обязательна для мержа (тот же паттерн, что у `weak_group`/`mistake`); детектор полностью детерминированный, покрывается юнит-тестами.

## Формула

Δ на каждом ходе — та же формула, что у `mistake`, вынесенная в общий helper:

```python
# feature_extraction/scoring.py
def mover_favorability(score_lead: float, mover: str) -> float:
    # rootInfo.scoreLead всегда с точки зрения чёрных (reportAnalysisWinratesAs=BLACK,
    # config/profile.py) - разворачиваем на точку зрения того, кто ходил.
    return score_lead if mover == "B" else -score_lead
```

`mistake.py` переключается на этот helper вместо приватной `_mover_favorability(analysis, mover)` (сигнатура которой была завязана на полный `AnalyzeResponse` — здесь нужна версия на голом `float`, т.к. `opening_loss` получает от фронтенда только `scoreLead`, не полный `AnalyzeResponse` на каждый ход дебюта).

**Окно дебюта** переиспользует существующую `K_OPEN` (`feature_extraction/config.py`) — единое определение «дебюта» на весь проект, то же самое, что уже определяет `stage="opening"` у `mistake`:

```
window_end = floor(board_area * K_OPEN)   # board_area = boardXSize * boardYSize
```

**Накопление**: для выбранного `color`, по всем ходам `i` в диапазоне `1..window_end`, где `moves[i-1][0] == color`:

```
Δ_i = mover_favorability(score_lead[i-1], color) − mover_favorability(score_lead[i], color)
total_delta = Σ Δ_i     # НЕ клэмпится к 0 - "хороший" ход законно уменьшает сумму
```

`score_lead[k]` — `rootInfo.scoreLead` позиции после `k`-го хода (`score_lead[0]` — стартовая позиция, до первого хода).

- **`confidence`** = `min(visits[i-1], visits[i]) / MIN_RELIABLE_VISITS` по всем учтённым `i`, капается в `[0, 1]` — минимум по всей последовательности («слабое звено»), тот же принцип, что у `mistake`, только агрегированный по диапазону, а не по одной паре позиций.
- **Порог создания находки**: `total_delta ≥ THRESHOLD_OPENING_LOSS = 3.0` очка.
- **`severity`**: `high` при `total_delta ≥ OPENING_LOSS_SEVERITY_HIGH = 15.0`, `medium` при `5.0 ≤ total_delta < 15.0`, иначе `low` (порог создания `3.0` < границы `medium` `5.0` — намеренно, чтобы `low` оставался достижимым бакетом, а не мёртвой веткой; та же структура, что у `mistake`, где порог создания тоже строго ниже границы `medium`).

Эти числа **не выведены ни из какого внешнего источника** (в отличие от `mistake`, где границы взяты из реальной лестницы KaTrain) — простая иллюстративная отправная точка, явно помеченная в комментарии как некалиброванная, в том же духе, что стартовые веса `weak_group` в `feature_extraction/config.py`. Настоящая калибровка — работа будущего под-этапа «Калибровка/бэктестинг».

## Backend: `Finding` — третий тип

`feature_extraction/schemas.py`:

```python
class OpeningLossFinding(BaseModel):
    finding_id: str
    type: Literal["opening_loss"] = "opening_loss"
    color: Literal["B", "W"]
    move_range: tuple[int, int]      # (1, window_end) либо (1, len(moves)), если партия короче окна
    delta_score: float               # накопленная Δ (total_delta)
    severity: Literal["low", "medium", "high"]
    confidence: float

Finding = Annotated[
    Union[WeakGroupFinding, MistakeFinding, OpeningLossFinding], Field(discriminator="type")
]
```

## Backend: `feature_extraction/opening_loss.py`

```python
def detect_opening_loss(
    moves: list[list[str]],                       # [[color, gtp_coord], ...] - весь путь до текущего узла
    sequence: list[tuple[int, float, int]],        # (turn_number, score_lead, visits), покрывает 0..window_end
    color: str,
    board_x_size: int,
    board_y_size: int,
) -> OpeningLossFinding | None:
    ...
```

Возвращает `None`, если `total_delta < THRESHOLD_OPENING_LOSS`. `move_range` — `(1, min(window_end, len(moves)))`.

`feature_extraction/config.py` — новые константы рядом с существующими:
```python
THRESHOLD_OPENING_LOSS = 3.0
OPENING_LOSS_SEVERITY_HIGH = 15.0
OPENING_LOSS_SEVERITY_MEDIUM = 5.0
```

## Backend: новый эндпоинт `POST /api/explain/opening`

Отдельный эндпоинт, не расширение `/api/explain` — форма входа принципиально другая (диапазон + явный цвет, без доски вообще: находке не нужны камни/группы, в отличие от `weak_group`/`mistake`).

`api/schemas.py`:
```python
class OpeningTurnEval(BaseModel):
    turnNumber: int
    scoreLead: float
    visits: int

class ExplainOpeningRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    color: Literal["B", "W"]
    openingSequence: list[OpeningTurnEval]
    analysisAtEnd: AnalyzeResponse    # полный анализ позиции на границе дебюта -
                                       # контекст для LLM-промпта и rootInfo-фоллбек
                                       # в consistency.py (winrate/scoreLead/visits),
                                       # как analysis у /api/explain

    @model_validator(mode="after")
    def _sequence_matches_opening_window(self) -> "ExplainOpeningRequest":
        board_area = self.boardXSize * self.boardYSize
        window_end = min(int(board_area * K_OPEN), len(self.moves))
        expected_turns = list(range(0, window_end + 1))
        got_turns = [t.turnNumber for t in self.openingSequence]
        if got_turns != expected_turns:
            raise ValueError(
                f"openingSequence must cover turns {expected_turns}, got {got_turns}"
            )
        return self
```

Несовпадающая по длине/номерам последовательность отклоняется `422`, а не тихо считается на частичных данных.

`api/explain_opening.py` (новый роутер-модуль, рядом с `explain.py`):
```python
@router.post("/api/explain/opening", response_model=ExplainResponse, dependencies=[...])
async def explain_opening(
    body: ExplainOpeningRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExplainResponse:
    sequence = [(t.turnNumber, t.scoreLead, t.visits) for t in body.openingSequence]
    finding = detect_opening_loss(body.moves, sequence, body.color, body.boardXSize, body.boardYSize)
    if finding is None:
        return ExplainResponse(message="Существенной потери очков в дебюте не найдено")

    try:
        explanation, verified = await asyncio.to_thread(
            verify_and_retry, provider, finding, body.analysisAtEnd, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # citation-обогащение - идентично explain.py (copy, не abstraction через shared
    # helper: два места, ~12 строк, дублирование дешевле преждевременной абстракции)
    ...
    return ExplainResponse(finding=finding, explanation=explanation, verified=verified, citation=citation)
```

`verify_and_retry`/`_rag_doc_id_valid`/`get_snippet_by_id`-обвязка переиспользуются без изменений — уже дженерик по `Finding`.

## Backend: обобщение промпта и anti-hallucination проверки на три типа

Три места сейчас построены как двухветочный `if finding.type == "weak_group": ... else: (мистейк)` — это тот самый паттерн, что уже приводил к Critical-регрессии (`weak_group` ломался при добавлении `mistake` из-за общего вместо per-type кода). `build_rag_query()` прямо пострадал бы: его `else`-ветка читает `finding.stage`, которого у `OpeningLossFinding` не будет — `AttributeError`. Переписываю все три на явную трёхветочную диспетчеризацию без «удобного» финального `else`:

```python
# prompts.py
def build_rag_query(finding: Finding) -> str:
    match finding.type:
        case "weak_group":
            return "слабая группа камней с недостатком глаз и территории"
        case "mistake":
            return f"ошибка хода, потеря очков на стадии {finding.stage}"
        case "opening_loss":
            return "ошибки в дебюте, потеря очков в начале партии"
```

Аналогично `build_user_prompt()` (третья ветка форматирует `color`/`move_range`/`delta_score`) и `consistency.py::_fallback_explanation()` (третий шаблонный текст: `"Накопленная потеря очков в дебюте (ходы {move_range[0]}-{move_range[1]}): Δ={delta_score:.2f}..."`).

`llm/consistency.py`:
```python
_FINDING_FIELDS: dict[str, set[str]] = {
    "weak_group": {"weak_score", "own_certainty", "boundary_certainty", "liberties"},
    "mistake": {"delta_score"},
    "opening_loss": {"delta_score"},
}
```
`llm/schemas.py::CitedField` не меняется — `"delta_score"` уже есть в enum, просто становится валидным и для третьего типа.

## Frontend

**Сбор данных** — `board/gameRequestBuilder.ts`, новая функция рядом с `gtpMoves`:

```ts
export function buildOpeningSequence(
  tree: GameTree,
  nodeId: number,
  boardSize: number
): OpeningTurnEval[] | null
```

Идёт по пути от корня до `nodeId`, для каждого узла с `turnNumber ≤ boardSize² · K_OPEN` (константа `K_OPEN = 0.12` дублируется на фронте — задокументирована как обязанная совпадать с бэкендовой) достаёт `analysisByTurn.value.get(node.id)` и берёт `{turnNumber, scoreLead: rootInfo.scoreLead, visits: rootInfo.visits}`. Возвращает `null`, если для какого-то узла окна анализа ещё нет (партия не полностью проанализирована) — кнопка в этом случае недоступна с подсказкой.

**UI** — `LlmExplanationPanel.tsx`, второй независимый блок под уже существующей кнопкой «Объяснить эту позицию»: заголовок «Дебют», переключатель Чёрные/Белые, кнопка «Проанализировать дебют» (задизейблена, если `buildOpeningSequence()` вернул `null`, или пока идёт запрос). Свой независимый `status`/`result` state — не смешивается с пер-ходовым объяснением, не привязан к текущей позиции на доске (в отличие от первой кнопки, которая сбрасывается при смене узла). Дергает новую `explainOpening()` → `POST /api/explain/opening`, рендерит результат тем же вёрсточным блоком (`summary`/`verified`/`citation`), что уже есть — переиспользуется без изменений, там нет ни одного места, разбирающего специфичные поля `finding.type`.

**Типы** (`ipc/client.ts`):
```ts
export interface OpeningLossFinding {
  finding_id: string
  type: 'opening_loss'
  color: 'B' | 'W'
  move_range: [number, number]
  delta_score: number
  severity: 'low' | 'medium' | 'high'
  confidence: number
}
export type Finding = WeakGroupFinding | MistakeFinding | OpeningLossFinding

export interface OpeningTurnEval { turnNumber: number; scoreLead: number; visits: number }
export interface ExplainOpeningRequest {
  moves: [string, string][]
  boardXSize: number
  boardYSize: number
  color: 'B' | 'W'
  openingSequence: OpeningTurnEval[]
  analysisAtEnd: AnalyzeResponse
}
export async function explainOpening(request: ExplainOpeningRequest): Promise<ExplainResponse>
```

## Ошибки

- `openingSequence` не покрывает ожидаемое окно (длина/номера ходов не совпадают с `0..window_end`) — `422` от pydantic-валидатора.
- Ниже порога — `message: "Существенной потери очков в дебюте не найдено"` (тот же паттерн, что у `/api/explain`).
- Сбой LLM-провайдера — `503`, как у `/api/explain`.
- На фронте — кнопка недоступна, если `buildOpeningSequence()` вернул `null` (партия не полностью проанализирована в пределах окна дебюта).

## Тестирование

**Backend:**
- `tests/feature_extraction/test_scoring.py` (новый, после выноса `mover_favorability`) + `tests/feature_extraction/test_mistake.py` не меняются по ожидаемому поведению (regression).
- `tests/feature_extraction/test_opening_loss.py` (новый): накопление Δ только по ходам заданного цвета (ходы другого цвета не попадают в сумму); порог/severity границы; `confidence` = минимум по всей последовательности; `move_range` для партии короче окна.
- `tests/test_api_explain_opening.py` (новый): 422 на несовпадающую последовательность; happy-path с моком провайдера; `message` при сумме ниже порога.
- `tests/llm/test_consistency.py`, `tests/llm/test_prompts.py`: по одному кейсу на каждый из трёх типов через `match`-диспетчеризацию — включая регрессионные проверки, что `weak_group`/`mistake` не сломались от рефакторинга (`else`→явные ветки).

**Frontend:**
- `gameRequestBuilder.test.ts`: `buildOpeningSequence()` на дереве с ветвлением (берёт путь до текущего узла, не всё дерево целиком) и на неполном анализе (возвращает `null`).
- `LlmExplanationPanel.test.tsx`: новый блок рендерится и независим от первого (навигация по позиции не сбрасывает его state); переключатель цвета передаётся в `explainOpening()`.

## Критерии готовности

- На фиксированной тестовой SGF с заранее известной дорогой последовательностью ходов в дебюте `POST /api/explain/opening` возвращает `OpeningLossFinding` с ожидаемым `delta_score`/`severity` и `verified: true`.
- Существующее поведение `weak_group`/`mistake` и `/api/explain` не сломано — регрессионные тесты предыдущих под-этапов остаются зелёными без изменений в ожидаемых результатах.
- Все существующие backend/frontend тесты остаются зелёными, оба typecheck проходят.
