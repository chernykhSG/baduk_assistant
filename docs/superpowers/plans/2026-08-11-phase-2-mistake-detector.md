# Mistake Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `mistake` detector (cost in points of the actually-played move) as a second, discriminated-union `Finding` type alongside the existing `weak_group` detector, wired end-to-end through `/api/explain` and the frontend.

**Architecture:** `Finding` becomes a pydantic discriminated union (`WeakGroupFinding | MistakeFinding`). A new pure function `detect_mistake()` computes point loss from `rootInfo.scoreLead` before/after the actually-played move (both already computed by the frontend for its winrate graph — no new KataGo calls). `/api/explain` runs both detectors and prefers `mistake` when both trigger. The LLM prompt/anti-hallucination checker generalize to branch on `finding.type`.

**Tech Stack:** Python 3.12 (backend, pydantic v2), Electron+TS+Preact (frontend), pytest/vitest.

## Global Constraints

- Branch `phase-2-mistake-detector`, forked from `main`. Never commit directly to `main`.
- Formula: `mover_favorability(pos) = scoreLead(pos) if mover == "B" else -scoreLead(pos)`; `Δ = mover_favorability(до) − mover_favorability(после)`. Relies on `reportAnalysisWinratesAs = BLACK` already set in `backend/src/baduk_backend/config/profile.py` — do not re-derive or change that assumption.
- `THRESHOLD_MISTAKE = 0.5`, `MISTAKE_SEVERITY_HIGH = 6.0`, `MISTAKE_SEVERITY_MEDIUM = 1.5` (severity: `high` if `Δ ≥ 6.0`, `medium` if `1.5 ≤ Δ < 6.0`, `low` if `0.5 ≤ Δ < 1.5`, no finding below `0.5`) — values sourced from KaTrain's `eval_thresholds`, not invented.
- `K_OPEN = 0.12`, `K_END = 0.15` for `stage` classification (informational field only, does not gate severity/threshold in this plan).
- `confidence = min(rootInfo.visits_до, rootInfo.visits_после) / MIN_RELIABLE_VISITS` (reuse the existing `MIN_RELIABLE_VISITS = 500` constant from `weak_group`'s config — do not redefine it).
- When both `weak_group` and `mistake` trigger on the same request, `mistake` wins — `ExplainResponse.finding` stays a single `Finding`, never a list.
- `detect_mistake()` receives the already-reconstructed `board` (the same one `explain.py` already builds via `apply_moves()` for `weak_group`) — it must NOT re-run `apply_moves()` or receive `moves` directly.
- Out of scope for this plan (do not implement): `opening_loss` detector, calibration/backtesting harness, versioned JSON detector config, free-form LLM chat, mistake-pattern taxonomy from `Baduk-knowledge-base`, manual live acceptance on a real game.
- Full spec: `docs/superpowers/specs/2026-08-11-phase-2-mistake-detector-design.md`.

---

### Task 1: `Finding` discriminated union

**Files:**
- Modify: `backend/src/baduk_backend/feature_extraction/schemas.py`
- Modify: `backend/src/baduk_backend/feature_extraction/weak_group.py`
- Create: `backend/tests/feature_extraction/test_schemas.py`

**Interfaces:**
- Produces: `WeakGroupFinding` (all fields identical to the current `Finding`), `MistakeFinding{finding_id: str, type: Literal["mistake"], turn_number: int, color: Literal["B","W"], move: str, delta_score: float, stage: Literal["opening","middlegame","endgame"], severity: Literal["low","medium","high"], confidence: float}`, `Finding = Annotated[Union[WeakGroupFinding, MistakeFinding], Field(discriminator="type")]` — all three names importable from `baduk_backend.feature_extraction.schemas`. Every later task imports `Finding` (and, where a specific variant is needed, `WeakGroupFinding`/`MistakeFinding`) from here.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/feature_extraction/test_schemas.py`:

```python
from pydantic import TypeAdapter

from baduk_backend.feature_extraction.schemas import Finding, MistakeFinding, WeakGroupFinding

_ADAPTER: TypeAdapter = TypeAdapter(Finding)


def test_finding_discriminates_weak_group():
    parsed = _ADAPTER.validate_python(
        {
            "finding_id": "f1",
            "type": "weak_group",
            "turn_number": 1,
            "stones": [[4, 4]],
            "color": "B",
            "weak_score": 0.8,
            "own_certainty": 0.1,
            "boundary_certainty": 0.2,
            "liberties": 3,
            "severity": "high",
            "confidence": 0.5,
        }
    )
    assert isinstance(parsed, WeakGroupFinding)


def test_finding_discriminates_mistake():
    parsed = _ADAPTER.validate_python(
        {
            "finding_id": "f2",
            "type": "mistake",
            "turn_number": 10,
            "color": "W",
            "move": "Q4",
            "delta_score": 3.0,
            "stage": "middlegame",
            "severity": "medium",
            "confidence": 0.6,
        }
    )
    assert isinstance(parsed, MistakeFinding)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_schemas.py -v`
Expected: FAIL (`ImportError: cannot import name 'MistakeFinding'` — the schema doesn't exist yet).

- [ ] **Step 3: Rewrite `feature_extraction/schemas.py`**

Replace the entire file content with:

```python
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


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
    move: str
    delta_score: float
    stage: Literal["opening", "middlegame", "endgame"]
    severity: Literal["low", "medium", "high"]
    confidence: float


Finding = Annotated[Union[WeakGroupFinding, MistakeFinding], Field(discriminator="type")]
```

- [ ] **Step 4: Update `feature_extraction/weak_group.py`**

Change the import (currently `from baduk_backend.feature_extraction.schemas import Finding`) to:

```python
from baduk_backend.feature_extraction.schemas import WeakGroupFinding
```

Change the function signature (currently `) -> Finding | None:`) to:

```python
) -> WeakGroupFinding | None:
```

Change the constructor call (currently `return Finding(`) to:

```python
return WeakGroupFinding(
```

No other line in `weak_group.py` changes — the `type="weak_group"` argument already present in the constructor call stays as-is.

- [ ] **Step 5: Run tests to verify everything passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/ -v`
Expected: PASS — the 2 new tests plus all existing `test_weak_group.py` tests (unchanged behavior, only the class name changed).

- [ ] **Step 6: Run the full backend suite to confirm no other regressions**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS — `api/schemas.py`, `llm/consistency.py`, `llm/prompts.py`, `llm/orchestrator.py`, `llm/providers/*.py` all import `Finding` by name only (as a type hint), which still resolves correctly now that it's a union alias instead of a class.

- [ ] **Step 7: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/schemas.py backend/src/baduk_backend/feature_extraction/weak_group.py backend/tests/feature_extraction/test_schemas.py
git commit -m "feat: turn Finding into a discriminated union (WeakGroupFinding | MistakeFinding)"
```

---

### Task 2: `mistake` detector

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/mistake.py`
- Modify: `backend/src/baduk_backend/feature_extraction/config.py`
- Create: `backend/tests/feature_extraction/test_mistake.py`

**Interfaces:**
- Consumes: `MistakeFinding` (Task 1), `MIN_RELIABLE_VISITS` (existing constant in `feature_extraction/config.py`), `AnalyzeResponse`/`RootInfo` (`baduk_backend.api.schemas`, unchanged).
- Produces: `detect_mistake(board: list[list[str | None]], analysis_before: AnalyzeResponse, analysis_after: AnalyzeResponse, next_move: tuple[str, str], board_x_size: int, board_y_size: int, turn_number: int) -> MistakeFinding | None` — the exact signature Task 4's `explain.py` wiring calls.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/feature_extraction/test_mistake.py`:

```python
import pytest

from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.mistake import detect_mistake


def _empty_board(size: int) -> list[list[str | None]]:
    return [[None] * size for _ in range(size)]


def _analysis(score_lead: float, visits: int) -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x", moveInfos=[], rootInfo=RootInfo(winrate=0.5, scoreLead=score_lead, visits=visits), ownership=None
    )


def test_detect_mistake_black_move_loses_points():
    board = _empty_board(9)
    before = _analysis(score_lead=5.0, visits=1000)
    after = _analysis(score_lead=2.0, visits=800)

    finding = detect_mistake(board, before, after, ("B", "Q4"), 9, 9, turn_number=30)

    assert finding is not None
    assert finding.type == "mistake"
    assert finding.color == "B"
    assert finding.move == "Q4"
    assert finding.delta_score == pytest.approx(3.0)
    assert finding.severity == "medium"
    assert finding.confidence == pytest.approx(1.0)  # min(1000,800)/500 clamped to 1.0


def test_detect_mistake_white_move_loses_points():
    board = _empty_board(9)
    before = _analysis(score_lead=-5.0, visits=600)
    after = _analysis(score_lead=-1.0, visits=1200)

    finding = detect_mistake(board, before, after, ("W", "D4"), 9, 9, turn_number=30)

    assert finding is not None
    assert finding.color == "W"
    assert finding.delta_score == pytest.approx(4.0)
    assert finding.severity == "medium"


def test_detect_mistake_white_good_move_returns_none():
    board = _empty_board(9)
    before = _analysis(score_lead=-5.0, visits=1000)
    after = _analysis(score_lead=-8.0, visits=1000)  # improves White's favorability

    assert detect_mistake(board, before, after, ("W", "D4"), 9, 9, turn_number=30) is None


def test_detect_mistake_threshold_boundary():
    board = _empty_board(9)
    at_threshold = detect_mistake(
        board, _analysis(1.0, 1000), _analysis(0.5, 1000), ("B", "Q4"), 9, 9, turn_number=30
    )
    below_threshold = detect_mistake(
        board, _analysis(1.0, 1000), _analysis(0.51, 1000), ("B", "Q4"), 9, 9, turn_number=30
    )

    assert at_threshold is not None
    assert at_threshold.severity == "low"
    assert below_threshold is None


def test_detect_mistake_high_severity_boundary():
    board = _empty_board(9)
    finding = detect_mistake(
        board, _analysis(6.0, 1000), _analysis(0.0, 1000), ("B", "Q4"), 9, 9, turn_number=30
    )

    assert finding is not None
    assert finding.delta_score == pytest.approx(6.0)
    assert finding.severity == "high"


def test_detect_mistake_confidence_uses_lower_visit_count():
    board = _empty_board(9)
    finding = detect_mistake(
        board, _analysis(5.0, 100), _analysis(0.0, 300), ("B", "Q4"), 9, 9, turn_number=30
    )

    assert finding is not None
    assert finding.confidence == pytest.approx(0.2)  # min(100, 300) / 500


def test_detect_mistake_stage_opening_by_move_number():
    board = _empty_board(9)  # 81 points, mostly empty
    finding = detect_mistake(
        board, _analysis(5.0, 1000), _analysis(0.0, 1000), ("B", "Q4"), 9, 9, turn_number=5
    )

    assert finding is not None
    assert finding.stage == "opening"  # 5 <= 81*0.12=9.72


def test_detect_mistake_stage_endgame_by_empty_points():
    board = _empty_board(9)
    # Fill all but 10 points (<= 81*0.15=12.15) so the position reads as endgame
    # regardless of a large move_number.
    filled = 0
    for y in range(9):
        for x in range(9):
            if filled >= 71:
                break
            board[y][x] = "B" if filled % 2 == 0 else "W"
            filled += 1
    finding = detect_mistake(
        board, _analysis(5.0, 1000), _analysis(0.0, 1000), ("B", "Q4"), 9, 9, turn_number=71
    )

    assert finding is not None
    assert finding.stage == "endgame"


def test_detect_mistake_stage_middlegame_otherwise():
    board = _empty_board(9)
    finding = detect_mistake(
        board, _analysis(5.0, 1000), _analysis(0.0, 1000), ("B", "Q4"), 9, 9, turn_number=40
    )

    assert finding is not None
    assert finding.stage == "middlegame"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_mistake.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.mistake'`).

- [ ] **Step 3: Add constants to `feature_extraction/config.py`**

Append to the end of the existing file (after the `weak_group` constants, do not remove or renumber those):

```python

# Константы детектора mistake.
# Лестница порогов и severity-границы взяты не из ARCHITECTURE.md (тот
# пример иллюстративный, не выведен из данных), а из реального, проверенного
# на практике инструмента обучения кю-игроков - KaTrain
# (katrain/config.json, trainer.eval_thresholds = [12, 6, 3, 1.5, 0.5, 0]
# очков, единая лестница без поправки на стадию игры). Стартовая,
# НЕоткалиброванная под этот проект оценка - подбор точных значений
# через backtesting harness запланирован отдельным будущим под-этапом.
THRESHOLD_MISTAKE = 0.5
MISTAKE_SEVERITY_HIGH = 6.0
MISTAKE_SEVERITY_MEDIUM = 1.5
K_OPEN = 0.12
K_END = 0.15
```

- [ ] **Step 4: Write `feature_extraction/mistake.py`**

```python
import uuid

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.config import (
    K_END,
    K_OPEN,
    MIN_RELIABLE_VISITS,
    MISTAKE_SEVERITY_HIGH,
    MISTAKE_SEVERITY_MEDIUM,
    THRESHOLD_MISTAKE,
)
from baduk_backend.feature_extraction.schemas import MistakeFinding


def _mover_favorability(analysis: AnalyzeResponse, mover: str) -> float:
    # rootInfo.scoreLead is always given from Black's perspective in this
    # project (reportAnalysisWinratesAs = BLACK, see config/profile.py) -
    # flip the sign to read it from the mover's own perspective.
    return analysis.rootInfo.scoreLead if mover == "B" else -analysis.rootInfo.scoreLead


def _empty_points(board: list[list[str | None]]) -> int:
    return sum(1 for row in board for cell in row if cell is None)


def _stage(board: list[list[str | None]], board_x_size: int, board_y_size: int, move_number: int) -> str:
    board_area = board_x_size * board_y_size
    if move_number <= board_area * K_OPEN:
        return "opening"
    if _empty_points(board) <= board_area * K_END:
        return "endgame"
    return "middlegame"


def _severity(delta: float) -> str:
    if delta >= MISTAKE_SEVERITY_HIGH:
        return "high"
    if delta >= MISTAKE_SEVERITY_MEDIUM:
        return "medium"
    return "low"


def detect_mistake(
    board: list[list[str | None]],
    analysis_before: AnalyzeResponse,
    analysis_after: AnalyzeResponse,
    next_move: tuple[str, str],
    board_x_size: int,
    board_y_size: int,
    turn_number: int,
) -> MistakeFinding | None:
    mover, move = next_move
    delta = _mover_favorability(analysis_before, mover) - _mover_favorability(analysis_after, mover)
    # Guard against IEEE-754 rounding noise before the threshold/severity
    # comparisons below, same precaution as weak_group's _weak_score().
    delta = round(delta, 9)
    if delta < THRESHOLD_MISTAKE:
        return None

    confidence = min(analysis_before.rootInfo.visits, analysis_after.rootInfo.visits) / MIN_RELIABLE_VISITS
    confidence = min(confidence, 1.0)

    return MistakeFinding(
        finding_id=f"f_{uuid.uuid4().hex[:8]}",
        turn_number=turn_number,
        color=mover,
        move=move,
        delta_score=delta,
        stage=_stage(board, board_x_size, board_y_size, turn_number),
        severity=_severity(delta),
        confidence=confidence,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_mistake.py -v`
Expected: PASS (all 9 tests).

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/mistake.py backend/src/baduk_backend/feature_extraction/config.py backend/tests/feature_extraction/test_mistake.py
git commit -m "feat: add mistake detector (point-loss of the actually-played move)"
```

---

### Task 3: Generalize the LLM prompt and anti-hallucination checker

**Files:**
- Modify: `backend/src/baduk_backend/llm/prompts.py`
- Modify: `backend/src/baduk_backend/llm/consistency.py`
- Create: `backend/tests/llm/test_prompts.py`
- Modify: `backend/tests/llm/test_consistency.py`

**Interfaces:**
- Consumes: `MistakeFinding`/`WeakGroupFinding`/`Finding` (Task 1).
- Produces: `build_user_prompt()` and `verify_and_retry()` keep their existing signatures (`Finding` is now the union — no signature change), but both now branch correctly on `finding.type`. Task 4's `explain.py` relies on this to pass either finding type through unchanged.

- [ ] **Step 1: Write the failing prompt tests**

Create `backend/tests/llm/test_prompts.py`:

```python
from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import MistakeFinding, WeakGroupFinding
from baduk_backend.llm.prompts import EXPLANATION_TOOL_PARAMETERS, build_user_prompt


def _analysis() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x", moveInfos=[], rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250), ownership=[0.0] * 81
    )


def test_cited_field_enum_includes_delta_score_and_keeps_existing_fields():
    enum = EXPLANATION_TOOL_PARAMETERS["properties"]["claims"]["items"]["properties"]["cited_field"]["enum"]
    assert "delta_score" in enum
    assert "weak_score" in enum


def test_build_user_prompt_for_weak_group_mentions_group_fields():
    finding = WeakGroupFinding(
        finding_id="f1",
        turn_number=5,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.0,
        boundary_certainty=0.0,
        liberties=4,
        severity="high",
        confidence=0.5,
    )
    prompt = build_user_prompt(finding, _analysis(), 9)
    assert "weak_score=0.85" in prompt
    assert "f1" in prompt


def test_build_user_prompt_for_mistake_mentions_delta_move_and_stage():
    finding = MistakeFinding(
        finding_id="f2",
        turn_number=10,
        color="W",
        move="Q4",
        delta_score=3.0,
        stage="middlegame",
        severity="medium",
        confidence=0.6,
    )
    prompt = build_user_prompt(finding, _analysis(), 9)
    assert "delta_score=3.0" in prompt
    assert "Q4" in prompt
    assert "middlegame" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py -v`
Expected: FAIL (`"delta_score" in enum` is `False`; `build_user_prompt` raises `AttributeError` on `finding.delta_score` for the mistake case since the function doesn't branch yet).

- [ ] **Step 3: Update `llm/prompts.py`**

Change `SYSTEM_PROMPT` (currently mentions "слабой группы"/`weak_score, own_certainty, boundary_certainty, liberties, visits, winrate или scoreLead" explicitly) to:

```python
SYSTEM_PROMPT = """\
Ты - тренер по игре в го, объясняющий позицию игроку кю-уровня на русском языке.
Тебе дана находка о позиции и числа из анализа KataGo. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_explanation - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле находки \
и точное число из данных.
3. Если уверенность (confidence) находки ниже 0.7, используй смягчающий \
язык ("похоже", "вероятно", "возможно").
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""
```

Change `EXPLANATION_TOOL_PARAMETERS["properties"]["claims"]["items"]["properties"]["cited_field"]["enum"]` (currently `["weak_score", "own_certainty", "boundary_certainty", "liberties", "visits", "winrate", "scoreLead"]`) to add `"delta_score"`:

```python
                    "enum": [
                        "weak_score",
                        "own_certainty",
                        "boundary_certainty",
                        "liberties",
                        "delta_score",
                        "visits",
                        "winrate",
                        "scoreLead",
                    ],
```

Replace `build_user_prompt()` entirely:

```python
def build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    root = (
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )
    if finding.type == "weak_group":
        color_ru = "чёрных" if finding.color == "B" else "белых"
        coords = ", ".join(xy_to_gtp(x, y, board_size) for x, y in finding.stones)
        return (
            f"Находка о слабой группе {color_ru} (finding_id={finding.finding_id}):\n"
            f"Камни группы: {coords}\n"
            f"weak_score={finding.weak_score}, own_certainty={finding.own_certainty}, "
            f"boundary_certainty={finding.boundary_certainty}, liberties={finding.liberties}, "
            f"confidence={finding.confidence}, turn_number={finding.turn_number}\n"
            f"{root}"
        )
    color_ru = "чёрных" if finding.color == "B" else "белых"
    return (
        f"Находка о ходе {color_ru} (finding_id={finding.finding_id}):\n"
        f"Сыгранный ход: {finding.move} (ход №{finding.turn_number}, стадия: {finding.stage})\n"
        f"delta_score={finding.delta_score}, confidence={finding.confidence}\n"
        f"{root}"
    )
```

- [ ] **Step 4: Run prompt tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing consistency tests**

In `backend/tests/llm/test_consistency.py`, change the import line (currently `from baduk_backend.feature_extraction.schemas import Finding`) to:

```python
from baduk_backend.feature_extraction.schemas import Finding, MistakeFinding
```

Add this helper next to the existing `_finding()`:

```python
def _mistake_finding() -> Finding:
    return MistakeFinding(
        finding_id="f_test",
        turn_number=5,
        color="W",
        move="Q4",
        delta_score=3.0,
        stage="middlegame",
        severity="medium",
        confidence=0.6,
    )
```

Append these tests at the end of the file:

```python
def test_verify_and_retry_accepts_correct_mistake_claims():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=3.0)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _mistake_finding(), _analysis(), 9)

    assert verified is True
    assert result == explanation


def test_verify_and_retry_rejects_wrong_mistake_claim_then_retries():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=0.1)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=3.0)],
    )
    provider = _RecordingFakeProvider([bad, good])

    result, verified = verify_and_retry(provider, _mistake_finding(), _analysis(), 9)

    assert verified is True
    assert result == good
    assert "delta_score" in provider.calls[1][0]


def test_verify_and_retry_falls_back_with_mistake_specific_summary():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=0.1)],
    )
    provider = _RecordingFakeProvider([bad, bad, bad])

    result, verified = verify_and_retry(provider, _mistake_finding(), _analysis(), 9)

    assert verified is False
    assert result.claims == []
    assert "3.00" in result.summary
    assert "Δ" in result.summary
```

- [ ] **Step 6: Run consistency tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v`
Expected: FAIL — `_true_value()` looks up `"delta_score"` in the still-flat `_FINDING_FIELDS` set, doesn't find it there (it's not a `weak_group` field), falls through to `getattr(analysis.rootInfo, "delta_score")`, and raises `AttributeError` since `RootInfo` has no such field.

- [ ] **Step 7: Update `llm/consistency.py`**

Change `_FINDING_FIELDS` (currently `_FINDING_FIELDS = {"weak_score", "own_certainty", "boundary_certainty", "liberties"}`) to:

```python
_FINDING_FIELDS: dict[str, set[str]] = {
    "weak_group": {"weak_score", "own_certainty", "boundary_certainty", "liberties"},
    "mistake": {"delta_score"},
}
```

Change `_true_value()`:

```python
def _true_value(field: str, finding: Finding, analysis: AnalyzeResponse) -> float:
    if field in _FINDING_FIELDS[finding.type]:
        return getattr(finding, field)
    return getattr(analysis.rootInfo, field)
```

Change `_fallback_explanation()`:

```python
def _fallback_explanation(finding: Finding) -> Explanation:
    if finding.type == "weak_group":
        summary = (
            f"Обнаружена слабая группа (ход {finding.turn_number}): "
            f"показатель уязвимости {finding.weak_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        )
    else:
        summary = (
            f"Обнаружена потеря очков на ходе {finding.turn_number}: "
            f"Δ={finding.delta_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        )
    return Explanation(summary=summary, claims=[])
```

- [ ] **Step 8: Run consistency tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v`
Expected: PASS (all existing `weak_group`-based tests unchanged and passing, plus the 3 new `mistake` tests).

- [ ] **Step 9: Run the full backend suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 10: Commit**

```bash
git add backend/src/baduk_backend/llm/prompts.py backend/src/baduk_backend/llm/consistency.py backend/tests/llm/test_prompts.py backend/tests/llm/test_consistency.py
git commit -m "feat: generalize LLM prompt and consistency checker for the mistake finding type"
```

---

### Task 4: Wire `mistake` into `/api/explain`

**Files:**
- Modify: `backend/src/baduk_backend/api/schemas.py`
- Modify: `backend/src/baduk_backend/api/explain.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_api_explain.py`

**Interfaces:**
- Consumes: `detect_mistake()` (Task 2), the generalized `verify_and_retry()`/`build_user_prompt()` (Task 3).
- Produces: `ExplainRequest` gains `analysisAfter: AnalyzeResponse | None = None` and `nextMove: tuple[str, str] | None = None` — the exact field names Task 5's frontend request payload must match.

- [ ] **Step 1: Fix the shared test stub to be type-aware**

In `backend/tests/conftest.py`, replace `_StubLLMProvider.complete()` (currently hardcodes `cited_field="weak_score"`/`finding.weak_score`, which would crash with `AttributeError` on a `MistakeFinding`):

```python
class _StubLLMProvider:
    def complete(self, finding, analysis, board_size, corrections=None):
        if finding.type == "weak_group":
            cited_field, cited_number = "weak_score", finding.weak_score
        else:
            cited_field, cited_number = "delta_score", finding.delta_score
        return Explanation(
            summary="Тестовое объяснение",
            claims=[
                Claim(
                    text="...",
                    finding_id=finding.finding_id,
                    cited_field=cited_field,
                    cited_number=cited_number,
                )
            ],
        )
```

- [ ] **Step 2: Write the failing API tests**

In `backend/tests/test_api_explain.py`, extend `_payload()` to optionally carry the new fields (replace the existing function):

```python
def _payload(moves=None, ownership=None, move_infos=None, analysis_after=None, next_move=None):
    payload = {
        "moves": moves if moves is not None else [["B", "E5"]],
        "boardXSize": 9,
        "boardYSize": 9,
        "analysis": {
            "id": "x",
            "turnNumber": 1,
            "moveInfos": move_infos if move_infos is not None else [],
            "rootInfo": {"winrate": 0.5, "scoreLead": 0.0, "visits": 250},
            "ownership": ownership if ownership is not None else [0.0] * 81,
        },
    }
    if analysis_after is not None:
        payload["analysisAfter"] = analysis_after
    if next_move is not None:
        payload["nextMove"] = next_move
    return payload
```

Append these tests:

```python
def test_explain_returns_mistake_finding_when_only_mistake_triggers(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(
            ownership=[1.0] * 81,  # resolved position - weak_group does not trigger
            analysis_after={
                "id": "y",
                "turnNumber": 2,
                "moveInfos": [],
                "rootInfo": {"winrate": 0.2, "scoreLead": -3.0, "visits": 250},
                "ownership": None,
            },
            next_move=["W", "F5"],
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "mistake"
    assert body["finding"]["delta_score"] == 3.0
    assert body["verified"] is True


def test_explain_prefers_mistake_when_both_detectors_trigger(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(
            # default ownership/moves from _payload() already trigger weak_group
            # (see test_explain_returns_finding_and_verified_explanation)
            analysis_after={
                "id": "y",
                "turnNumber": 2,
                "moveInfos": [],
                "rootInfo": {"winrate": 0.2, "scoreLead": -3.0, "visits": 250},
                "ownership": None,
            },
            next_move=["W", "F5"],
        ),
    )
    assert response.status_code == 200
    assert response.json()["finding"]["type"] == "mistake"


def test_explain_returns_422_when_analysis_after_given_without_next_move(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(
            analysis_after={
                "id": "y",
                "turnNumber": 2,
                "moveInfos": [],
                "rootInfo": {"winrate": 0.2, "scoreLead": -3.0, "visits": 250},
                "ownership": None,
            }
        ),
    )
    assert response.status_code == 422


def test_explain_weak_group_path_unaffected_without_analysis_after(explain_client):
    # Regression: the exact payload/assertions from
    # test_explain_returns_finding_and_verified_explanation, unchanged.
    response = explain_client.post(
        "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "weak_group"
    assert body["verified"] is True
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_explain.py -v`
Expected: FAIL on the 3 new mistake/validation tests (`ExplainRequest` has no `analysisAfter`/`nextMove` fields yet, so pydantic silently ignores the extra JSON keys and `/api/explain` falls back to the `weak_group`-only path or returns the "nothing found" message instead of `422`/`mistake`).

- [ ] **Step 4: Update `api/schemas.py`**

Add two fields and a validator to `ExplainRequest` (currently ends after the existing `_ownership_matches_board_size` validator):

```python
class ExplainRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse
    analysisAfter: AnalyzeResponse | None = None
    nextMove: tuple[str, str] | None = None

    @model_validator(mode="after")
    def _ownership_matches_board_size(self) -> "ExplainRequest":
        ownership = self.analysis.ownership
        if ownership is not None and len(ownership) != self.boardXSize * self.boardYSize:
            raise ValueError(
                "analysis.ownership length must equal boardXSize * boardYSize "
                f"({self.boardXSize * self.boardYSize}), got {len(ownership)}"
            )
        return self

    @model_validator(mode="after")
    def _analysis_after_and_next_move_together(self) -> "ExplainRequest":
        if (self.analysisAfter is None) != (self.nextMove is None):
            raise ValueError("analysisAfter and nextMove must both be set or both be None")
        return self
```

(Only the two new fields and the new validator are added — the existing `_ownership_matches_board_size` validator body is unchanged, shown here for placement context only.)

- [ ] **Step 5: Update `api/explain.py`**

Replace the whole file:

```python
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from baduk_backend.api.schemas import ExplainRequest, ExplainResponse
from baduk_backend.auth import require_valid_token
from baduk_backend.board.board_state import apply_moves
from baduk_backend.feature_extraction.mistake import detect_mistake
from baduk_backend.feature_extraction.weak_group import detect_weak_group
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.orchestrator import LLMProvider

router = APIRouter()


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider


@router.post(
    "/api/explain",
    response_model=ExplainResponse,
    dependencies=[Depends(require_valid_token)],
)
async def explain(
    body: ExplainRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExplainResponse:
    turn_number = body.analysis.turnNumber if body.analysis.turnNumber is not None else len(body.moves)
    board = apply_moves(body.moves, body.boardXSize, body.boardYSize)
    weak_finding = detect_weak_group(board, body.boardXSize, body.boardYSize, body.analysis, turn_number)

    mistake_finding = None
    if body.analysisAfter is not None and body.nextMove is not None:
        mistake_finding = detect_mistake(
            board, body.analysis, body.analysisAfter, body.nextMove,
            body.boardXSize, body.boardYSize, turn_number,
        )

    finding = mistake_finding or weak_finding
    if finding is None:
        return ExplainResponse(message="Ничего заметного не найдено в этой позиции")

    # verify_and_retry() itself never raises on a mismatch (falls back to a
    # templated response instead) - an exception here means the provider call
    # itself failed (network/timeout/auth), which the design spec treats as a
    # 503, the same way /api/analyze does for KataGo engine failures.
    try:
        explanation, verified = await asyncio.to_thread(
            verify_and_retry, provider, finding, body.analysis, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ExplainResponse(finding=finding, explanation=explanation, verified=verified)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_explain.py -v`
Expected: PASS (all 8 tests — 4 existing regression + 4 new).

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/src/baduk_backend/api/schemas.py backend/src/baduk_backend/api/explain.py backend/tests/conftest.py backend/tests/test_api_explain.py
git commit -m "feat: wire the mistake detector into POST /api/explain"
```

---

### Task 5: Frontend — request the mistake detector and update types

**Files:**
- Modify: `frontend/src/renderer/src/ipc/client.ts`
- Modify: `frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx`
- Modify: `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`

**Interfaces:**
- Consumes: `analysisByTurn: Map<number, AnalyzeResponse>` (existing, keyed by tree `nodeId` — not turn number), `NodeObject`/`sgfCoordToGtp`/`getBoardSize` (existing).
- Produces: no new exports — this is the leaf task in the dependency chain.

- [ ] **Step 1: Update `ipc/client.ts` types**

Replace the existing `Finding` interface (currently a single flat interface with `type: 'weak_group'`) with:

```typescript
export interface WeakGroupFinding {
  finding_id: string
  type: 'weak_group'
  turn_number: number
  stones: [number, number][]
  color: 'B' | 'W'
  weak_score: number
  own_certainty: number
  boundary_certainty: number
  liberties: number
  severity: 'low' | 'medium' | 'high'
  confidence: number
}

export interface MistakeFinding {
  finding_id: string
  type: 'mistake'
  turn_number: number
  color: 'B' | 'W'
  move: string
  delta_score: number
  stage: 'opening' | 'middlegame' | 'endgame'
  severity: 'low' | 'medium' | 'high'
  confidence: number
}

export type Finding = WeakGroupFinding | MistakeFinding
```

Update the `ExplainRequest` interface (currently `moves`/`boardXSize`/`boardYSize`/`analysis` only) to add the two new optional fields:

```typescript
export interface ExplainRequest {
  moves: [string, string][]
  boardXSize: number
  boardYSize: number
  analysis: AnalyzeResponse
  analysisAfter?: AnalyzeResponse
  nextMove?: [string, string]
}
```

- [ ] **Step 2: Run typecheck to confirm the type change alone doesn't break anything**

Run: `cd frontend && pnpm run typecheck:web`
Expected: PASS (no code currently constructs a `Finding` object directly or narrows on `finding.type`/reads `weak_score` outside the union — confirmed earlier in this session by searching the frontend source).

- [ ] **Step 3: Write the failing panel tests**

In `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`, append these two tests at the end of the `describe` block:

```typescript
  it('includes analysisAfter and nextMove when the current node has a main-line child', async () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const [, nodeA, nodeB] = mainLineNodeIds(tree)
    currentTree.value = tree
    currentNodeId.value = nodeA
    const analysisA = {
      id: 'a',
      moveInfos: [],
      rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 },
      ownership: new Array(81).fill(0)
    }
    const analysisB = {
      id: 'b',
      moveInfos: [],
      rootInfo: { winrate: 0.4, scoreLead: -1, visits: 100 },
      ownership: new Array(81).fill(0)
    }
    analysisByTurn.value = new Map([
      [nodeA, analysisA],
      [nodeB, analysisB]
    ])
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'ok', claims: [] },
      verified: true,
      message: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(mockExplainPosition).toHaveBeenCalledWith(
        expect.objectContaining({
          analysisAfter: analysisB,
          nextMove: ['W', 'G3']
        })
      )
    })
  })

  it('omits analysisAfter and nextMove when the current node is the last move', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'ok', claims: [] },
      verified: true,
      message: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(mockExplainPosition).toHaveBeenCalledWith(
        expect.objectContaining({
          analysisAfter: undefined,
          nextMove: undefined
        })
      )
    })
  })
```

- [ ] **Step 4: Run tests to verify the new ones fail**

Run: `cd frontend && pnpm exec vitest run LlmExplanationPanel`
Expected: FAIL — `explainPosition` is currently called without `analysisAfter`/`nextMove` at all in either case, so the first new test's `toHaveBeenCalledWith` assertion fails (missing `analysisAfter`/`nextMove` keys with real values).

- [ ] **Step 5: Update `LlmExplanationPanel.tsx`**

Add `analysisByTurn` to the existing `appState` import (currently `currentTree, currentNodeId, currentMoveAnalysis`) and `NodeObject` to the existing `sgfLoader` import (currently only `getBoardSize`):

```typescript
import { currentTree, currentNodeId, currentMoveAnalysis, analysisByTurn } from '../state/appState'
import { getBoardSize } from '../board/sgfLoader'
import type { NodeObject } from '../board/sgfLoader'
import { gtpMoves, sgfCoordToGtp } from '../board/gameRequestBuilder'
```

Replace the body of `handleExplain()` (currently builds `moves`/`boardSize` and calls `explainPosition` with just `moves`/`boardXSize`/`boardYSize`/`analysis`):

```typescript
  async function handleExplain(): Promise<void> {
    if (!tree || nodeId === null || !analysis) return
    const requestedNodeId = nodeId
    setStatus('loading')
    setErrorMessage(null)
    try {
      const boardSize = getBoardSize(tree)
      const moves = gtpMoves(tree, requestedNodeId, boardSize)

      const node = tree.get(requestedNodeId) as NodeObject
      const child = node.children[0] as NodeObject | undefined
      let analysisAfter: typeof analysis | undefined
      let nextMove: [string, string] | undefined
      if (child) {
        const childAnalysis = analysisByTurn.value.get(child.id)
        const color = child.data.B ? 'B' : child.data.W ? 'W' : null
        const sgfCoord = child.data.B?.[0] ?? child.data.W?.[0] ?? null
        if (childAnalysis && color) {
          analysisAfter = childAnalysis
          nextMove = [color, sgfCoordToGtp(sgfCoord, boardSize)]
        }
      }

      const response = await explainPosition({
        moves,
        boardXSize: boardSize,
        boardYSize: boardSize,
        analysis,
        analysisAfter,
        nextMove
      })
      if (currentNodeId.value !== requestedNodeId) return
      setResult(response)
      setStatus('done')
    } catch (err) {
      if (currentNodeId.value !== requestedNodeId) return
      setErrorMessage(err instanceof Error ? err.message : 'Не удалось получить объяснение')
      setStatus('error')
    }
  }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run LlmExplanationPanel`
Expected: PASS (all tests, including the 2 new ones and the 6 pre-existing ones).

- [ ] **Step 7: Run the full frontend suite and typecheck**

Run: `cd frontend && pnpm exec vitest run && pnpm run typecheck:web && pnpm run typecheck:node`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/renderer/src/ipc/client.ts frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx frontend/tests/renderer/components/LlmExplanationPanel.test.tsx
git commit -m "feat: request the mistake detector from LlmExplanationPanel"
```

---

## Manual verification (optional — not required for merge per the spec)

Not required: `detect_mistake` is fully deterministic and covered by unit tests, mirroring the `weak_group` precedent. If you want to sanity-check it on a real game anyway: load an SGF with a known blunder in Electron, click "Объяснить эту позицию" on the position right before that move, and confirm the returned `finding.type` is `"mistake"` with a plausible `delta_score`.
