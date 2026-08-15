# Opening Loss Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third detector, `opening_loss` (cumulative points lost by one color over the first N moves of the opening), end-to-end: backend detector, a new `POST /api/explain/opening` endpoint, and a frontend UI block that lets the user pick a color and trigger the analysis.

**Architecture:** Mirrors the existing `weak_group`/`mistake` detector pattern — a pure, deterministic Python function produces a `Finding`, which the already-generic LLM prompt/consistency-check pipeline turns into a verified natural-language explanation. `opening_loss` differs from the other two in shape (a range of moves + an explicit color, not a single position), so it gets its own request schema and endpoint rather than reusing `/api/explain`.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 (backend), TypeScript / Preact / Vitest (frontend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-15-phase-2-opening-loss-detector-design.md`

## Global Constraints

- Reuse the existing `K_OPEN = 0.12` constant (`feature_extraction/config.py`) as the sole definition of "opening window" — `window_end = floor(boardXSize * boardYSize * K_OPEN)`, capped at the number of moves actually played. Do not introduce a second, independently-configurable N.
- New detector constants (`feature_extraction/config.py`): `THRESHOLD_OPENING_LOSS = 3.0`, `OPENING_LOSS_SEVERITY_MEDIUM = 5.0`, `OPENING_LOSS_SEVERITY_HIGH = 15.0` — illustrative, explicitly uncalibrated (no external reference exists for this metric, unlike `mistake`'s KaTrain-derived ladder). `THRESHOLD_OPENING_LOSS` must stay strictly below `OPENING_LOSS_SEVERITY_MEDIUM` so `severity="low"` remains reachable.
- `MIN_RELIABLE_VISITS = 500` (existing) is reused for `opening_loss`'s confidence calculation.
- `opening_loss` gets its own endpoint, `POST /api/explain/opening` — it is not folded into `/api/explain`, because its request shape (a range + an explicit color, no board/position) is fundamentally different from the other two detectors' single-position shape.
- Any place in `prompts.py`/`consistency.py` that dispatches on `finding.type` must use an exhaustive `match` with an explicit `case` per one of the three known types and a `case _: raise AssertionError(...)` catch-all — never a two-way `if/else` that silently mis-handles a third type (this already caused a Critical regression once when `mistake` was added; do not repeat it for `opening_loss`).
- The citation-enrichment block (after `verify_and_retry`, building `RagCitation` from `explanation.rag_doc_id`) in the new `explain_opening.py` is a literal copy of the block already in `explain.py`, not a shared abstraction — this is an explicit YAGNI choice made in the design spec, not an oversight to "fix" during implementation.
- `CitedField` (`llm/schemas.py`) is unchanged — `"delta_score"` is already a valid value and is simply reused by `opening_loss`.
- The frontend duplicates `K_OPEN = 0.12` as a local constant in `gameRequestBuilder.ts` (no shared config file crosses the backend/frontend boundary in this project) — the duplication must carry a comment stating it must match the backend value, since a drift would make every opening-analysis request fail its 422 validation.

---

### Task 1: `OpeningLossFinding` and the `Finding` union

**Files:**
- Modify: `backend/src/baduk_backend/feature_extraction/schemas.py`
- Test: `backend/tests/feature_extraction/test_schemas.py`

**Interfaces:**
- Consumes: nothing new — extends the existing `WeakGroupFinding`/`MistakeFinding`/`Finding` already in this file.
- Produces: `OpeningLossFinding` (fields: `finding_id: str`, `type: Literal["opening_loss"] = "opening_loss"`, `color: Literal["B", "W"]`, `move_range: tuple[int, int]`, `delta_score: float`, `severity: Literal["low", "medium", "high"]`, `confidence: float`) and the updated `Finding = Annotated[Union[WeakGroupFinding, MistakeFinding, OpeningLossFinding], Field(discriminator="type")]` — every later task imports `Finding`/`OpeningLossFinding` from `baduk_backend.feature_extraction.schemas`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/feature_extraction/test_schemas.py`:

```python
from baduk_backend.feature_extraction.schemas import OpeningLossFinding


def test_finding_discriminates_opening_loss():
    parsed = _ADAPTER.validate_python(
        {
            "finding_id": "f3",
            "type": "opening_loss",
            "color": "B",
            "move_range": [1, 9],
            "delta_score": 7.0,
            "severity": "medium",
            "confidence": 0.8,
        }
    )
    assert isinstance(parsed, OpeningLossFinding)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'OpeningLossFinding'`

- [ ] **Step 3: Add `OpeningLossFinding` and extend the union**

In `backend/src/baduk_backend/feature_extraction/schemas.py`, add after `MistakeFinding`:

```python
class OpeningLossFinding(BaseModel):
    finding_id: str
    type: Literal["opening_loss"] = "opening_loss"
    color: Literal["B", "W"]
    move_range: tuple[int, int]
    delta_score: float
    severity: Literal["low", "medium", "high"]
    confidence: float
```

Replace the existing `Finding = Annotated[Union[WeakGroupFinding, MistakeFinding], Field(discriminator="type")]` with:

```python
Finding = Annotated[
    Union[WeakGroupFinding, MistakeFinding, OpeningLossFinding], Field(discriminator="type")
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_schemas.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/schemas.py backend/tests/feature_extraction/test_schemas.py
git commit -m "feat: add OpeningLossFinding to the Finding discriminated union"
```

---

### Task 2: `opening_loss` detector

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/scoring.py`
- Modify: `backend/src/baduk_backend/feature_extraction/mistake.py`
- Modify: `backend/src/baduk_backend/feature_extraction/config.py`
- Create: `backend/src/baduk_backend/feature_extraction/opening_loss.py`
- Create: `backend/tests/feature_extraction/test_scoring.py`
- Create: `backend/tests/feature_extraction/test_opening_loss.py`
- Test (regression, do not change expected results): `backend/tests/feature_extraction/test_mistake.py`

**Interfaces:**
- Consumes: `OpeningLossFinding` from Task 1 (`baduk_backend.feature_extraction.schemas`); `K_OPEN`, `MIN_RELIABLE_VISITS` (existing, `feature_extraction/config.py`).
- Produces: `mover_favorability(score_lead: float, mover: str) -> float` (`feature_extraction/scoring.py`) — reused by Task 2 itself in `mistake.py` and by `opening_loss.py`. `detect_opening_loss(moves: list[list[str]], sequence: list[tuple[int, float, int]], color: str, board_x_size: int, board_y_size: int) -> OpeningLossFinding | None` (`feature_extraction/opening_loss.py`) — Task 4's endpoint calls this directly. `THRESHOLD_OPENING_LOSS`, `OPENING_LOSS_SEVERITY_MEDIUM`, `OPENING_LOSS_SEVERITY_HIGH` (new constants in `feature_extraction/config.py`).

- [ ] **Step 1: Write the failing tests for `mover_favorability`**

Create `backend/tests/feature_extraction/test_scoring.py`:

```python
from baduk_backend.feature_extraction.scoring import mover_favorability


def test_mover_favorability_black_reads_score_lead_directly():
    assert mover_favorability(5.0, "B") == 5.0


def test_mover_favorability_white_flips_the_sign():
    assert mover_favorability(5.0, "W") == -5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.scoring'`

- [ ] **Step 3: Create `scoring.py` and refactor `mistake.py` to use it**

Create `backend/src/baduk_backend/feature_extraction/scoring.py`:

```python
def mover_favorability(score_lead: float, mover: str) -> float:
    # rootInfo.scoreLead is always given from Black's perspective in this
    # project (reportAnalysisWinratesAs = BLACK, see config/profile.py) -
    # flip the sign to read it from the mover's own perspective.
    return score_lead if mover == "B" else -score_lead
```

In `backend/src/baduk_backend/feature_extraction/mistake.py`, remove the `_mover_favorability` function (lines 15-19) and replace its one call site. The file currently starts:

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
```

Replace with:

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
from baduk_backend.feature_extraction.scoring import mover_favorability
```

And in `detect_mistake`, replace:

```python
    delta = _mover_favorability(analysis_before, mover) - _mover_favorability(analysis_after, mover)
```

with:

```python
    delta = mover_favorability(analysis_before.rootInfo.scoreLead, mover) - mover_favorability(
        analysis_after.rootInfo.scoreLead, mover
    )
```

- [ ] **Step 4: Run test to verify it passes, plus the mistake regression suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_scoring.py tests/feature_extraction/test_mistake.py -v`
Expected: PASS — all `test_scoring.py` tests, and every pre-existing `test_mistake.py` test unchanged (same assertions, same expected values — this is a pure refactor, no behavior change).

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/scoring.py backend/src/baduk_backend/feature_extraction/mistake.py backend/tests/feature_extraction/test_scoring.py
git commit -m "refactor: extract mover_favorability() into a shared scoring module"
```

- [ ] **Step 6: Write the failing tests for `detect_opening_loss`**

Create `backend/tests/feature_extraction/test_opening_loss.py`:

```python
import pytest

from baduk_backend.feature_extraction.opening_loss import detect_opening_loss


def _moves(colors: list[str]) -> list[list[str]]:
    return [[c, f"m{i}"] for i, c in enumerate(colors)]


def test_detect_opening_loss_sums_only_the_requested_color_moves():
    # 9 moves, alternating starting with Black: B,W,B,W,B,W,B,W,B (5 Black, 4 White).
    moves = _moves(["B", "W", "B", "W", "B", "W", "B", "W", "B"])
    # score_lead per turn (Black's-perspective, straight from rootInfo):
    # 10 -> 9 -> 9 -> 7 -> 7 -> 6 -> 6 -> 3 -> 3 -> 3
    # Black's own deltas (turns 1,3,5,7,9): 1, 2, 1, 3, 0 -> total 7.0
    # White's own deltas (turns 2,4,6,8): 0, 0, 0, 0 -> total 0.0
    score_leads = [10.0, 9.0, 9.0, 7.0, 7.0, 6.0, 6.0, 3.0, 3.0, 3.0]
    sequence = [(turn, score_leads[turn], 1000) for turn in range(10)]

    black_finding = detect_opening_loss(moves, sequence, "B", 9, 9)
    assert black_finding is not None
    assert black_finding.type == "opening_loss"
    assert black_finding.color == "B"
    assert black_finding.move_range == (1, 9)
    assert black_finding.delta_score == pytest.approx(7.0)
    assert black_finding.severity == "medium"
    assert black_finding.confidence == pytest.approx(1.0)

    white_finding = detect_opening_loss(moves, sequence, "W", 9, 9)
    assert white_finding is None  # White's own moves never lose points in this sequence


def test_detect_opening_loss_threshold_boundary():
    moves = _moves(["B"])
    at_threshold = detect_opening_loss(moves, [(0, 3.0, 1000), (1, 0.0, 1000)], "B", 9, 9)
    below_threshold = detect_opening_loss(moves, [(0, 3.0, 1000), (1, 0.01, 1000)], "B", 9, 9)

    assert at_threshold is not None
    assert at_threshold.severity == "low"
    assert below_threshold is None


def test_detect_opening_loss_high_severity_boundary():
    moves = _moves(["B"])
    finding = detect_opening_loss(moves, [(0, 20.0, 1000), (1, 0.0, 1000)], "B", 9, 9)

    assert finding is not None
    assert finding.delta_score == pytest.approx(20.0)
    assert finding.severity == "high"


def test_detect_opening_loss_move_range_shrinks_to_a_short_game():
    # 9x9's opening window is 9 moves (81*0.12=9.72 -> floor 9), but the game
    # itself only has 2 moves - move_range must not claim a longer window
    # than the game actually has.
    moves = _moves(["B", "W"])
    sequence = [(0, 5.0, 1000), (1, 0.0, 1000), (2, 0.0, 1000)]

    finding = detect_opening_loss(moves, sequence, "B", 9, 9)

    assert finding is not None
    assert finding.move_range == (1, 2)


def test_detect_opening_loss_confidence_uses_the_weakest_visit_count_in_the_window():
    moves = _moves(["B", "W", "B"])
    # window_end = min(9, 3) = 3; Black moves at turns 1 and 3.
    sequence = [
        (0, 10.0, 1000),
        (1, 8.0, 100),  # weakest visit count anywhere in the window
        (2, 8.0, 1000),
        (3, 5.0, 1000),
    ]

    finding = detect_opening_loss(moves, sequence, "B", 9, 9)

    assert finding is not None
    assert finding.confidence == pytest.approx(0.2)  # 100 / 500
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_opening_loss.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.opening_loss'`

- [ ] **Step 8: Add the new config constants**

Append to `backend/src/baduk_backend/feature_extraction/config.py`:

```python

# Константы детектора opening_loss.
# Ни один внешний источник (в отличие от лестницы KaTrain у mistake) не даёт
# готового ориентира для НАКОПЛЕННОЙ дебютной потери - эти числа простая
# иллюстративная отправная точка, специально подобранная так, чтобы
# THRESHOLD_OPENING_LOSS < OPENING_LOSS_SEVERITY_MEDIUM (иначе severity="low"
# стал бы недостижимой веткой). Как и остальные пороги в этом файле, не
# откалиброваны под этот проект - подбор через backtesting harness
# запланирован отдельным будущим под-этапом.
THRESHOLD_OPENING_LOSS = 3.0
OPENING_LOSS_SEVERITY_MEDIUM = 5.0
OPENING_LOSS_SEVERITY_HIGH = 15.0
```

- [ ] **Step 9: Write `detect_opening_loss`**

Create `backend/src/baduk_backend/feature_extraction/opening_loss.py`:

```python
import uuid

from baduk_backend.feature_extraction.config import (
    K_OPEN,
    MIN_RELIABLE_VISITS,
    OPENING_LOSS_SEVERITY_HIGH,
    OPENING_LOSS_SEVERITY_MEDIUM,
    THRESHOLD_OPENING_LOSS,
)
from baduk_backend.feature_extraction.schemas import OpeningLossFinding
from baduk_backend.feature_extraction.scoring import mover_favorability


def _severity(delta: float) -> str:
    if delta >= OPENING_LOSS_SEVERITY_HIGH:
        return "high"
    if delta >= OPENING_LOSS_SEVERITY_MEDIUM:
        return "medium"
    return "low"


def detect_opening_loss(
    moves: list[list[str]],
    sequence: list[tuple[int, float, int]],
    color: str,
    board_x_size: int,
    board_y_size: int,
) -> OpeningLossFinding | None:
    """`sequence` is a list of (turn_number, score_lead, visits), one entry
    per turn 0..window_end, where turn 0 is the empty-board root position and
    turn k is the position after the k-th move. The caller (the API layer)
    is responsible for guaranteeing full coverage of the window - this
    function trusts it, the same way detect_mistake() trusts its board
    argument."""
    board_area = board_x_size * board_y_size
    window_end = min(int(board_area * K_OPEN), len(moves))
    by_turn = {turn: (score_lead, visits) for turn, score_lead, visits in sequence}

    total_delta = 0.0
    min_confidence_ratio = 1.0
    for turn in range(1, window_end + 1):
        mover = moves[turn - 1][0]
        if mover != color:
            continue
        score_before, visits_before = by_turn[turn - 1]
        score_after, visits_after = by_turn[turn]
        total_delta += mover_favorability(score_before, color) - mover_favorability(score_after, color)
        min_confidence_ratio = min(
            min_confidence_ratio, visits_before / MIN_RELIABLE_VISITS, visits_after / MIN_RELIABLE_VISITS
        )

    # Guard against IEEE-754 rounding noise, same precaution as weak_group/mistake.
    total_delta = round(total_delta, 9)
    if total_delta < THRESHOLD_OPENING_LOSS:
        return None

    return OpeningLossFinding(
        finding_id=f"f_{uuid.uuid4().hex[:8]}",
        type="opening_loss",
        color=color,
        move_range=(1, window_end),
        delta_score=total_delta,
        severity=_severity(total_delta),
        confidence=min(min_confidence_ratio, 1.0),
    )
```

- [ ] **Step 10: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_opening_loss.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 11: Run the full backend test suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS (all tests, including the untouched `test_mistake.py` and `test_weak_group.py`)

- [ ] **Step 12: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/config.py backend/src/baduk_backend/feature_extraction/opening_loss.py backend/tests/feature_extraction/test_opening_loss.py
git commit -m "feat: add opening_loss detector"
```

---

### Task 3: Generalize the LLM prompt and anti-hallucination checker for three finding types

**Files:**
- Modify: `backend/src/baduk_backend/llm/prompts.py`
- Modify: `backend/src/baduk_backend/llm/consistency.py`
- Test: `backend/tests/llm/test_prompts.py`
- Test: `backend/tests/llm/test_consistency.py`

**Interfaces:**
- Consumes: `Finding`/`OpeningLossFinding` from Task 1; nothing from Task 2 directly (this task only touches the LLM plumbing, not the detector).
- Produces: `build_rag_query`, `build_user_prompt` (`llm/prompts.py`) and `_FINDING_FIELDS`, `_fallback_explanation` (`llm/consistency.py`) all handle `opening_loss` — Task 4's endpoint relies on `verify_and_retry()` (unchanged signature) working correctly for `OpeningLossFinding` because of this task.

- [ ] **Step 1: Write the failing tests for `prompts.py`**

Append to `backend/tests/llm/test_prompts.py`:

```python
from baduk_backend.feature_extraction.schemas import OpeningLossFinding


def _opening_loss_finding() -> OpeningLossFinding:
    return OpeningLossFinding(
        finding_id="f3",
        type="opening_loss",
        color="B",
        move_range=(1, 9),
        delta_score=7.0,
        severity="medium",
        confidence=0.8,
    )


def test_build_user_prompt_for_opening_loss_mentions_range_color_and_delta():
    prompt = build_user_prompt(_opening_loss_finding(), _analysis(), 9)
    assert "delta_score=7.0" in prompt
    assert "1-9" in prompt
    assert "f3" in prompt


def test_build_rag_query_for_opening_loss():
    query = build_rag_query(_opening_loss_finding())
    assert query == "ошибки в дебюте, потеря очков в начале партии"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py -v`
Expected: FAIL — `AttributeError: 'OpeningLossFinding' object has no attribute 'stage'` (raised inside the current two-way `build_rag_query`'s `else` branch)

- [ ] **Step 3: Rewrite `build_rag_query` and `build_user_prompt` as exhaustive three-way dispatch**

In `backend/src/baduk_backend/llm/prompts.py`, replace the entire `build_rag_query` function:

```python
def build_rag_query(finding: Finding) -> str:
    match finding.type:
        case "weak_group":
            return "слабая группа камней с недостатком глаз и территории"
        case "mistake":
            return f"ошибка хода, потеря очков на стадии {finding.stage}"
        case "opening_loss":
            return "ошибки в дебюте, потеря очков в начале партии"
        case _:
            raise AssertionError(f"unhandled finding type: {finding.type}")
```

Replace the entire `build_user_prompt` function:

```python
def build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    root = (
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )
    match finding.type:
        case "weak_group":
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
        case "mistake":
            color_ru = "чёрных" if finding.color == "B" else "белых"
            return (
                f"Находка о ходе {color_ru} (finding_id={finding.finding_id}):\n"
                f"Сыгранный ход: {finding.move} (ход №{finding.turn_number}, стадия: {finding.stage})\n"
                f"delta_score={finding.delta_score}, confidence={finding.confidence}\n"
                "(scoreLead и winrate - всегда с точки зрения чёрных; delta_score - потеря очков "
                "для игрока, сделавшего ход)\n"
                f"{root}"
            )
        case "opening_loss":
            color_ru = "чёрных" if finding.color == "B" else "белых"
            return (
                f"Находка о накопленной потере очков {color_ru} в дебюте "
                f"(finding_id={finding.finding_id}):\n"
                f"Диапазон ходов: {finding.move_range[0]}-{finding.move_range[1]}\n"
                f"delta_score={finding.delta_score} (суммарная потеря очков за диапазон), "
                f"confidence={finding.confidence}\n"
                "(scoreLead и winrate - всегда с точки зрения чёрных; delta_score - суммарная "
                "потеря очков для игрока за диапазон ходов)\n"
                f"{root}"
            )
        case _:
            raise AssertionError(f"unhandled finding type: {finding.type}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py -v`
Expected: PASS (all tests, including the pre-existing `weak_group`/`mistake` ones — regression check)

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/llm/prompts.py backend/tests/llm/test_prompts.py
git commit -m "feat: generalize build_rag_query/build_user_prompt to opening_loss"
```

- [ ] **Step 6: Write the failing tests for `consistency.py`**

Append to `backend/tests/llm/test_consistency.py`:

```python
from baduk_backend.feature_extraction.schemas import OpeningLossFinding


def _opening_loss_finding() -> OpeningLossFinding:
    return OpeningLossFinding(
        finding_id="f_test",
        type="opening_loss",
        color="B",
        move_range=(1, 9),
        delta_score=7.0,
        severity="medium",
        confidence=0.8,
    )


def test_verify_and_retry_accepts_correct_opening_loss_claims():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=7.0)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _opening_loss_finding(), _analysis(), 9)

    assert verified is True
    assert result == explanation


def test_verify_and_retry_falls_back_with_opening_loss_specific_summary():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=0.1)],
    )
    provider = _RecordingFakeProvider([bad, bad, bad])

    result, verified = verify_and_retry(provider, _opening_loss_finding(), _analysis(), 9)

    assert verified is False
    assert result.claims == []
    assert "7.00" in result.summary
    assert "1-9" in result.summary


def test_verify_and_retry_does_not_crash_on_cross_type_field_opening_loss_finding():
    # weak_score belongs to WeakGroupFinding, not OpeningLossFinding, and is
    # not a rootInfo attribute either - citing it against an opening_loss
    # finding must be treated as a mismatch (retry), never raise AttributeError.
    cross_type = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=7.0)],
    )
    provider = _RecordingFakeProvider([cross_type, good])

    result, verified = verify_and_retry(provider, _opening_loss_finding(), _analysis(), 9)

    assert verified is True
    assert result == good
    assert "не относится" in provider.calls[1][0]
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v`
Expected: FAIL — `KeyError: 'opening_loss'` from `_true_value`'s `_FINDING_FIELDS[finding.type]` lookup

- [ ] **Step 8: Extend `_FINDING_FIELDS` and rewrite `_fallback_explanation` as exhaustive three-way dispatch**

In `backend/src/baduk_backend/llm/consistency.py`, replace:

```python
_FINDING_FIELDS: dict[str, set[str]] = {
    "weak_group": {"weak_score", "own_certainty", "boundary_certainty", "liberties"},
    "mistake": {"delta_score"},
}
```

with:

```python
_FINDING_FIELDS: dict[str, set[str]] = {
    "weak_group": {"weak_score", "own_certainty", "boundary_certainty", "liberties"},
    "mistake": {"delta_score"},
    "opening_loss": {"delta_score"},
}
```

Replace the entire `_fallback_explanation` function:

```python
def _fallback_explanation(finding: Finding) -> Explanation:
    match finding.type:
        case "weak_group":
            summary = (
                f"Обнаружена слабая группа (ход {finding.turn_number}): "
                f"показатель уязвимости {finding.weak_score:.2f}, уверенность {finding.confidence:.2f}. "
                "Не удалось получить проверенное текстовое объяснение - "
                "эти числа стоит свериться с ходами-кандидатами вручную."
            )
        case "mistake":
            summary = (
                f"Обнаружена потеря очков на ходе {finding.turn_number}: "
                f"Δ={finding.delta_score:.2f}, уверенность {finding.confidence:.2f}. "
                "Не удалось получить проверенное текстовое объяснение - "
                "эти числа стоит свериться с ходами-кандидатами вручную."
            )
        case "opening_loss":
            summary = (
                f"Накопленная потеря очков в дебюте (ходы {finding.move_range[0]}-"
                f"{finding.move_range[1]}): Δ={finding.delta_score:.2f}, "
                f"уверенность {finding.confidence:.2f}. "
                "Не удалось получить проверенное текстовое объяснение - "
                "эти числа стоит свериться с ходами-кандидатами вручную."
            )
        case _:
            raise AssertionError(f"unhandled finding type: {finding.type}")
    return Explanation(summary=summary, claims=[])
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v`
Expected: PASS (all tests, including the pre-existing `weak_group`/`mistake`/RAG ones — regression check)

- [ ] **Step 10: Run the full backend test suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS (all tests)

- [ ] **Step 11: Commit**

```bash
git add backend/src/baduk_backend/llm/consistency.py backend/tests/llm/test_consistency.py
git commit -m "feat: generalize consistency checker to opening_loss"
```

---

### Task 4: Wire `opening_loss` into a new `POST /api/explain/opening` endpoint

**Files:**
- Modify: `backend/src/baduk_backend/api/schemas.py`
- Create: `backend/src/baduk_backend/api/explain_opening.py`
- Modify: `backend/src/baduk_backend/main.py`
- Create: `backend/tests/test_api_explain_opening.py`

**Interfaces:**
- Consumes: `detect_opening_loss` (Task 2, `baduk_backend.feature_extraction.opening_loss`); `verify_and_retry` (Task 3, unchanged signature, `baduk_backend.llm.consistency`); `get_llm_provider` (existing, `baduk_backend.api.explain`); `K_OPEN` (existing, `baduk_backend.feature_extraction.config`).
- Produces: `OpeningTurnEval`, `ExplainOpeningRequest` (`api/schemas.py`); the `POST /api/explain/opening` route (`api/explain_opening.py`) — Task 5's frontend `explainOpening()` calls this exact path and request shape.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api_explain_opening.py`:

```python
from baduk_backend.auth import AUTH_TOKEN


def _payload(color="B", moves=None, opening_sequence=None):
    moves = (
        moves
        if moves is not None
        else [
            ["B", "E5"],
            ["W", "C3"],
            ["B", "G7"],
            ["W", "C7"],
            ["B", "E3"],
            ["W", "G3"],
            ["B", "C5"],
            ["W", "E7"],
            ["B", "G5"],
        ]
    )
    if opening_sequence is None:
        # 9 alternating moves on a 9x9 board -> window_end = min(9, 9) = 9.
        # scoreLead drifts down by 1 on each Black move (turns 1,3,5,7,9) and
        # stays flat on each White move (turns 2,4,6,8) - Black's cumulative
        # loss is 5.0 (clears THRESHOLD_OPENING_LOSS=3.0), White's is 0.0.
        score_leads = [10.0, 9.0, 9.0, 8.0, 8.0, 7.0, 7.0, 6.0, 6.0, 5.0]
        opening_sequence = [
            {"turnNumber": t, "scoreLead": score_leads[t], "visits": 1000} for t in range(10)
        ]
    return {
        "moves": moves,
        "boardXSize": 9,
        "boardYSize": 9,
        "color": color,
        "openingSequence": opening_sequence,
        "analysisAtEnd": {
            "id": "x",
            "turnNumber": 9,
            "moveInfos": [],
            "rootInfo": {"winrate": 0.5, "scoreLead": 5.0, "visits": 1000},
            "ownership": None,
        },
    }


def test_explain_opening_returns_finding_and_verified_explanation(explain_client):
    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "opening_loss"
    assert body["finding"]["color"] == "B"
    assert body["verified"] is True
    assert body["explanation"]["summary"] == "Тестовое объяснение"


def test_explain_opening_returns_message_when_below_threshold(explain_client):
    # White's own moves never change scoreLead in the default fixture
    # sequence, so requesting color="W" finds nothing.
    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload(color="W")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"] is None
    assert "не найдено" in body["message"]


def test_explain_opening_without_token_returns_401(explain_client):
    response = explain_client.post("/api/explain/opening", json=_payload())
    assert response.status_code == 401


def test_explain_opening_returns_422_when_sequence_length_mismatches_window(explain_client):
    payload = _payload()
    payload["openingSequence"] = payload["openingSequence"][:-1]  # drop turn 9

    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=payload
    )

    assert response.status_code == 422


def test_explain_opening_returns_422_when_sequence_turn_numbers_are_out_of_order(explain_client):
    payload = _payload()
    payload["openingSequence"][0], payload["openingSequence"][1] = (
        payload["openingSequence"][1],
        payload["openingSequence"][0],
    )

    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=payload
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_explain_opening.py -v`
Expected: FAIL — `404 Not Found` (route does not exist yet)

- [ ] **Step 3: Add `OpeningTurnEval`/`ExplainOpeningRequest` to `api/schemas.py`**

In `backend/src/baduk_backend/api/schemas.py`, add the import:

```python
from baduk_backend.feature_extraction.config import K_OPEN
```

Then append, after `ExplainRequest`'s existing validators:

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
    analysisAtEnd: AnalyzeResponse

    @model_validator(mode="after")
    def _sequence_matches_opening_window(self) -> "ExplainOpeningRequest":
        board_area = self.boardXSize * self.boardYSize
        window_end = min(int(board_area * K_OPEN), len(self.moves))
        expected_turns = list(range(window_end + 1))
        got_turns = [t.turnNumber for t in self.openingSequence]
        if got_turns != expected_turns:
            raise ValueError(f"openingSequence must cover turns {expected_turns}, got {got_turns}")
        return self
```

- [ ] **Step 4: Create the `explain_opening` router**

Create `backend/src/baduk_backend/api/explain_opening.py`:

```python
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from baduk_backend.api.explain import get_llm_provider
from baduk_backend.api.schemas import ExplainOpeningRequest, ExplainResponse, RagCitation
from baduk_backend.auth import require_valid_token
from baduk_backend.feature_extraction.opening_loss import detect_opening_loss
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.orchestrator import LLMProvider

router = APIRouter()


@router.post(
    "/api/explain/opening",
    response_model=ExplainResponse,
    dependencies=[Depends(require_valid_token)],
)
async def explain_opening(
    body: ExplainOpeningRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExplainResponse:
    sequence = [(t.turnNumber, t.scoreLead, t.visits) for t in body.openingSequence]
    finding = detect_opening_loss(body.moves, sequence, body.color, body.boardXSize, body.boardYSize)
    if finding is None:
        return ExplainResponse(message="Существенной потери очков в дебюте не найдено")

    # verify_and_retry() itself never raises on a mismatch (falls back to a
    # templated response instead) - an exception here means the provider call
    # itself failed (network/timeout/auth), same 503 treatment as /api/explain.
    try:
        explanation, verified = await asyncio.to_thread(
            verify_and_retry, provider, finding, body.analysisAtEnd, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citation = None
    if explanation.rag_doc_id is not None:
        from baduk_backend.rag.retrieval import get_snippet_by_id

        try:
            snippet = await asyncio.to_thread(get_snippet_by_id, explanation.rag_doc_id)
        except Exception:
            snippet = None
        if snippet is not None:
            citation = RagCitation(
                doc_id=snippet.doc_id,
                title=snippet.title,
                source=snippet.source,
                text_snippet=snippet.text_snippet,
            )

    return ExplainResponse(finding=finding, explanation=explanation, verified=verified, citation=citation)
```

- [ ] **Step 5: Register the router**

In `backend/src/baduk_backend/main.py`, replace:

```python
from baduk_backend.api import analysis, explain
```

with:

```python
from baduk_backend.api import analysis, explain, explain_opening
```

And replace:

```python
app.include_router(analysis.router)
app.include_router(explain.router)
```

with:

```python
app.include_router(analysis.router)
app.include_router(explain.router)
app.include_router(explain_opening.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_explain_opening.py -v`
Expected: PASS (all 5 tests)

Note: `backend/tests/conftest.py`'s `_StubLLMProvider.complete()` already handles `opening_loss` correctly without any change — its `if finding.type == "weak_group": ... else: (delta_score)` branch's `else` covers both `mistake` and `opening_loss`, since both expose a `delta_score` field. Verify this by reading `conftest.py:68-84` before writing Step 1's tests; do not modify it.

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS (all tests)

- [ ] **Step 8: Commit**

```bash
git add backend/src/baduk_backend/api/schemas.py backend/src/baduk_backend/api/explain_opening.py backend/src/baduk_backend/main.py backend/tests/test_api_explain_opening.py
git commit -m "feat: add POST /api/explain/opening endpoint"
```

---

### Task 5: Frontend — collect the opening sequence

**Files:**
- Modify: `frontend/src/renderer/src/board/sgfLoader.ts`
- Modify: `frontend/src/renderer/src/board/gameRequestBuilder.ts`
- Modify: `frontend/src/renderer/src/ipc/client.ts`
- Modify: `frontend/tests/renderer/board/sgfLoader.test.ts`
- Modify: `frontend/tests/renderer/board/gameRequestBuilder.test.ts`

**Interfaces:**
- Consumes: `analysisByTurn` (existing signal, `state/appState.ts`, keyed by tree node id); `AnalyzeResponse` (existing, `ipc/client.ts`).
- Produces: `nodeIdsFromRootToNode(tree: GameTree, nodeId: number): number[]` (`board/sgfLoader.ts`); `buildOpeningSequence(tree: GameTree, nodeId: number, boardSize: number): OpeningTurnEval[] | null` (`board/gameRequestBuilder.ts`); `OpeningTurnEval`, `ExplainOpeningRequest`, `explainOpening(request: ExplainOpeningRequest): Promise<ExplainResponse>`, and `OpeningLossFinding` added to the `Finding` union (`ipc/client.ts`) — Task 6's UI component calls `buildOpeningSequence` and `explainOpening` directly.

- [ ] **Step 1: Write the failing tests for `nodeIdsFromRootToNode`**

Append to `frontend/tests/renderer/board/sgfLoader.test.ts` (add `nodeIdsFromRootToNode` to the existing import from `@renderer/board/sgfLoader`):

```ts
describe('nodeIdsFromRootToNode', () => {
  it('returns node ids along the path from root to the given node, root first', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const child = tree.root.children[0]
    const grandchild = child.children[0]

    expect(nodeIdsFromRootToNode(tree, grandchild.id)).toEqual([tree.root.id, child.id, grandchild.id])
  })

  it('follows a variation branch, not the main line', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee](;W[gg])(;W[cc]))')
    const child = tree.root.children[0]
    const variation = child.children[1] // W[cc], the second branch

    expect(nodeIdsFromRootToNode(tree, variation.id)).toEqual([tree.root.id, child.id, variation.id])
  })

  it('returns just the root when nodeId is the root', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9])')

    expect(nodeIdsFromRootToNode(tree, tree.root.id)).toEqual([tree.root.id])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/sgfLoader.test.ts`
Expected: FAIL — `nodeIdsFromRootToNode is not exported`

- [ ] **Step 3: Add `nodeIdsFromRootToNode`**

Append to `frontend/src/renderer/src/board/sgfLoader.ts`:

```ts
/** Node ids along the path from root (index 0) to `nodeId` (last index) — index i is the node at turn i. Unlike mainLineNodeIds, this follows the actual path to `nodeId`, which may sit on a variation branch. */
export function nodeIdsFromRootToNode(tree: GameTree, nodeId: number): number[] {
  const path: NodeObject[] = []
  let current: NodeObject | null = tree.get(nodeId)
  while (current) {
    path.unshift(current)
    current =
      current.parentId === null || current.parentId === undefined
        ? null
        : tree.get(current.parentId)
  }
  return path.map((node) => node.id)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/sgfLoader.test.ts`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/renderer/src/board/sgfLoader.ts frontend/tests/renderer/board/sgfLoader.test.ts
git commit -m "feat: add nodeIdsFromRootToNode to sgfLoader"
```

- [ ] **Step 6: Add the new types to `ipc/client.ts`**

In `frontend/src/renderer/src/ipc/client.ts`, add after the existing `MistakeFinding` interface:

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
```

Replace the existing `export type Finding = WeakGroupFinding | MistakeFinding` with:

```ts
export type Finding = WeakGroupFinding | MistakeFinding | OpeningLossFinding
```

Add after the existing `ExplainRequest` interface (before `RagCitation`):

```ts
export interface OpeningTurnEval {
  turnNumber: number
  scoreLead: number
  visits: number
}

export interface ExplainOpeningRequest {
  moves: [string, string][]
  boardXSize: number
  boardYSize: number
  color: 'B' | 'W'
  openingSequence: OpeningTurnEval[]
  analysisAtEnd: AnalyzeResponse
}
```

Add after the existing `explainPosition` function, at the end of the file:

```ts
export async function explainOpening(request: ExplainOpeningRequest): Promise<ExplainResponse> {
  const { port, token } = await getConnection()
  const response = await fetch(`http://127.0.0.1:${port}/api/explain/opening`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Auth-Token': token },
    body: JSON.stringify(request)
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(
      `explainOpening failed (${response.status}): ${body.detail ?? response.statusText}`
    )
  }
  return response.json()
}
```

- [ ] **Step 7: Write the failing tests for `buildOpeningSequence`**

Append to `frontend/tests/renderer/board/gameRequestBuilder.test.ts`. Add `afterEach` to the existing `vitest` import, add these imports:

```ts
import { afterEach, describe, it, expect } from 'vitest'
import { parseSgf, findMainLineLeaf, nodeIdsFromRootToNode } from '@renderer/board/sgfLoader'
import {
  sgfCoordToGtp,
  mapSgfRules,
  buildAnalyzeRequest,
  buildStreamRequest,
  buildOpeningSequence
} from '@renderer/board/gameRequestBuilder'
import { analysisByTurn } from '@renderer/state/appState'
import type { AnalyzeResponse } from '@renderer/ipc/client'
```

Append:

```ts
function fakeAnalysis(scoreLead: number, visits: number): AnalyzeResponse {
  return { id: 'x', moveInfos: [], rootInfo: { winrate: 0.5, scoreLead, visits }, ownership: undefined }
}

describe('buildOpeningSequence', () => {
  afterEach(() => {
    analysisByTurn.value = new Map()
  })

  it('collects a compact sequence for every turn in the opening window on a 9x9 board', () => {
    // 9x9 board -> window = floor(81 * 0.12) = 9 turns; the fixture has
    // exactly 9 moves.
    const movesText = 'B[aa];W[bb];B[cc];W[dd];B[ee];W[ff];B[gg];W[hh];B[ia]'
    const tree = parseSgf(`(;GM[1]FF[4]SZ[9];${movesText})`)
    const leaf = findMainLineLeaf(tree)
    const nodeIds = nodeIdsFromRootToNode(tree, leaf.id)
    const map = new Map<number, AnalyzeResponse>()
    nodeIds.forEach((id, turn) => map.set(id, fakeAnalysis(10 - turn, 1000)))
    analysisByTurn.value = map

    const sequence = buildOpeningSequence(tree, leaf.id, 9)

    expect(sequence).toHaveLength(10) // turns 0..9
    expect(sequence?.[0]).toEqual({ turnNumber: 0, scoreLead: 10, visits: 1000 })
    expect(sequence?.[9]).toEqual({ turnNumber: 9, scoreLead: 1, visits: 1000 })
  })

  it('shrinks to the actual game length when the game is shorter than the opening window', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[aa];W[bb])')
    const leaf = findMainLineLeaf(tree)
    const nodeIds = nodeIdsFromRootToNode(tree, leaf.id)
    const map = new Map<number, AnalyzeResponse>()
    nodeIds.forEach((id, turn) => map.set(id, fakeAnalysis(5 - turn, 1000)))
    analysisByTurn.value = map

    const sequence = buildOpeningSequence(tree, leaf.id, 9)

    expect(sequence).toHaveLength(3) // turns 0,1,2 - the game only has 2 moves
  })

  it('follows the path to the given node, not the main line', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[aa](;W[bb])(;W[cc]))')
    const child = tree.root.children[0]
    const variation = child.children[1]
    analysisByTurn.value = new Map<number, AnalyzeResponse>([
      [tree.root.id, fakeAnalysis(5, 1000)],
      [child.id, fakeAnalysis(4, 1000)],
      [variation.id, fakeAnalysis(3, 1000)]
    ])

    const sequence = buildOpeningSequence(tree, variation.id, 9)

    expect(sequence).toEqual([
      { turnNumber: 0, scoreLead: 5, visits: 1000 },
      { turnNumber: 1, scoreLead: 4, visits: 1000 },
      { turnNumber: 2, scoreLead: 3, visits: 1000 }
    ])
  })

  it('returns null when analysis is missing for a node inside the window', () => {
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[aa];W[bb])')
    const leaf = findMainLineLeaf(tree)
    analysisByTurn.value = new Map<number, AnalyzeResponse>([[tree.root.id, fakeAnalysis(5, 1000)]]) // missing turns 1,2

    expect(buildOpeningSequence(tree, leaf.id, 9)).toBeNull()
  })
})
```

- [ ] **Step 8: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/gameRequestBuilder.test.ts`
Expected: FAIL — `buildOpeningSequence is not exported`

- [ ] **Step 9: Add `buildOpeningSequence`**

In `frontend/src/renderer/src/board/gameRequestBuilder.ts`, update the imports at the top:

```ts
import type GameTree from '@sabaki/immutable-gametree'
import { getBoardSize, findMainLineLeaf, movesFromRootToNode, nodeIdsFromRootToNode } from './sgfLoader'
import { GTP_COLUMNS } from './gtpColumns'
import { analysisByTurn } from '../state/appState'
import type { AnalyzeRequest, StreamAnalyzeRequest, OpeningTurnEval } from '../ipc/client'
```

Append at the end of the file:

```ts
// Must match feature_extraction/config.py's K_OPEN exactly - the backend
// validates that the opening sequence covers precisely this window and
// rejects the request (422) otherwise, so any drift here makes the
// "Проанализировать дебют" button unusable rather than silently wrong.
const K_OPEN = 0.12

export function buildOpeningSequence(
  tree: GameTree,
  nodeId: number,
  boardSize: number
): OpeningTurnEval[] | null {
  const windowEnd = Math.floor(boardSize * boardSize * K_OPEN)
  const nodeIds = nodeIdsFromRootToNode(tree, nodeId)
  const windowLength = Math.min(windowEnd, nodeIds.length - 1) + 1

  const sequence: OpeningTurnEval[] = []
  for (let turnNumber = 0; turnNumber < windowLength; turnNumber++) {
    const analysis = analysisByTurn.value.get(nodeIds[turnNumber])
    if (!analysis) return null
    sequence.push({
      turnNumber,
      scoreLead: analysis.rootInfo.scoreLead,
      visits: analysis.rootInfo.visits
    })
  }
  return sequence
}
```

- [ ] **Step 10: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run tests/renderer/board/gameRequestBuilder.test.ts`
Expected: PASS (all tests)

- [ ] **Step 11: Run the full frontend test suite and typecheck**

Run: `cd frontend && pnpm exec vitest run && pnpm run typecheck:web && pnpm run typecheck:node`
Expected: PASS (all tests, both typechecks clean)

- [ ] **Step 12: Commit**

```bash
git add frontend/src/renderer/src/board/gameRequestBuilder.ts frontend/src/renderer/src/ipc/client.ts frontend/tests/renderer/board/gameRequestBuilder.test.ts
git commit -m "feat: add buildOpeningSequence and explainOpening client"
```

---

### Task 6: Frontend — "Проанализировать дебют" UI block

**Files:**
- Modify: `frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx`
- Modify: `frontend/src/renderer/assets/main.css`
- Modify: `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`

**Interfaces:**
- Consumes: `buildOpeningSequence` (Task 5, `board/gameRequestBuilder`); `explainOpening` (Task 5, `ipc/client`); `currentTree`, `currentNodeId`, `analysisByTurn` (existing, `state/appState`).
- Produces: nothing consumed by a later task — this is the final task.

- [ ] **Step 1: Write the failing tests**

In `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`, update the mock at the top of the file:

```ts
vi.mock('@renderer/ipc/client', () => ({
  explainPosition: vi.fn(),
  explainOpening: vi.fn()
}))

const mockExplainPosition = vi.mocked(explainPosition)
const mockExplainOpening = vi.mocked(explainOpening)
```

Add `explainOpening` to the existing `import { explainPosition } from '@renderer/ipc/client'` line, and add `nodeIdsFromRootToNode` to the existing `import { parseSgf, findMainLineLeaf, mainLineNodeIds } from '@renderer/board/sgfLoader'` line.

Add this helper near the existing `loadPosition()` helper:

```ts
function loadOpeningReadyPosition(): void {
  const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
  const leaf = findMainLineLeaf(tree)
  const nodeIds = nodeIdsFromRootToNode(tree, leaf.id)
  currentTree.value = tree
  currentNodeId.value = leaf.id
  analysisByTurn.value = new Map(
    nodeIds.map((id, turn) => [
      id,
      {
        id: String(turn),
        moveInfos: [],
        rootInfo: { winrate: 0.5, scoreLead: 5 - turn, visits: 1000 },
        ownership: undefined
      }
    ])
  )
}
```

Append these tests inside the `describe('LlmExplanationPanel', ...)` block:

```ts
  it('disables the opening button when opening-window analysis is incomplete', () => {
    const { getByText } = render(<LlmExplanationPanel />)

    expect((getByText('Проанализировать дебют') as HTMLButtonElement).disabled).toBe(true)
  })

  it('calls explainOpening with the selected color and shows the result', async () => {
    loadOpeningReadyPosition()
    mockExplainOpening.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Разбор дебюта', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText, getByLabelText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByLabelText('Белые'))
    fireEvent.click(getByText('Проанализировать дебют'))

    await waitFor(() => {
      expect(getByText('Разбор дебюта')).toBeTruthy()
    })
    expect(mockExplainOpening).toHaveBeenCalledWith(expect.objectContaining({ color: 'W' }))
  })

  it('keeps the opening result when the current board position changes', async () => {
    loadOpeningReadyPosition()
    mockExplainOpening.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Разбор дебюта', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Проанализировать дебют'))
    await waitFor(() => {
      expect(getByText('Разбор дебюта')).toBeTruthy()
    })

    const nodeIds = nodeIdsFromRootToNode(currentTree.value!, currentNodeId.value!)
    currentNodeId.value = nodeIds[1] // navigate elsewhere - the per-move panel resets, the opening block must not

    expect(getByText('Разбор дебюта')).toBeTruthy()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: FAIL — `Unable to find an element with the text: Проанализировать дебют`

- [ ] **Step 3: Add the opening block to `LlmExplanationPanel.tsx`**

In `frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx`, the imports block currently reads:

```tsx
import { useEffect, useState } from 'preact/hooks'
import type { JSX } from 'preact'
import { currentTree, currentNodeId, currentMoveAnalysis, analysisByTurn } from '../state/appState'
import { getBoardSize } from '../board/sgfLoader'
import type { NodeObject } from '../board/sgfLoader'
import { gtpMoves, sgfCoordToGtp } from '../board/gameRequestBuilder'
import { explainPosition } from '../ipc/client'
import type { ExplainResponse } from '../ipc/client'
```

Change the two `gameRequestBuilder`/`ipc/client` import lines to:

```tsx
import { gtpMoves, sgfCoordToGtp, buildOpeningSequence } from '../board/gameRequestBuilder'
import { explainPosition, explainOpening } from '../ipc/client'
```

(The `preact/hooks`, `preact`, and `state/appState` import lines stay exactly as they already are.)

Inside the `LlmExplanationPanel` function, after the existing `handleExplain` function, add the opening-analysis state and handler:

```tsx
  const [openingColor, setOpeningColor] = useState<'B' | 'W'>('B')
  const [openingStatus, setOpeningStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [openingResult, setOpeningResult] = useState<ExplainResponse | null>(null)
  const [openingErrorMessage, setOpeningErrorMessage] = useState<string | null>(null)

  const openingSequence = tree && nodeId !== null ? buildOpeningSequence(tree, nodeId, getBoardSize(tree)) : null

  async function handleExplainOpening(): Promise<void> {
    if (!tree || nodeId === null || !openingSequence) return
    const boardSize = getBoardSize(tree)
    const analysisAtEnd = analysisByTurn.value.get(nodeId)
    if (!analysisAtEnd) return
    setOpeningStatus('loading')
    setOpeningErrorMessage(null)
    try {
      const response = await explainOpening({
        moves: gtpMoves(tree, nodeId, boardSize),
        boardXSize: boardSize,
        boardYSize: boardSize,
        color: openingColor,
        openingSequence,
        analysisAtEnd
      })
      setOpeningResult(response)
      setOpeningStatus('done')
    } catch (err) {
      setOpeningErrorMessage(err instanceof Error ? err.message : 'Не удалось получить объяснение')
      setOpeningStatus('error')
    }
  }
```

Add the opening block at the end of the returned JSX, just before the closing `</div>` of `llm-explanation-panel`:

```tsx
      <div class="llm-explanation-panel__opening">
        <h3>Дебют</h3>
        <label>
          <input
            type="radio"
            name="opening-color"
            checked={openingColor === 'B'}
            onChange={() => setOpeningColor('B')}
          />
          Чёрные
        </label>
        <label>
          <input
            type="radio"
            name="opening-color"
            checked={openingColor === 'W'}
            onChange={() => setOpeningColor('W')}
          />
          Белые
        </label>
        <button
          type="button"
          disabled={!openingSequence || openingStatus === 'loading'}
          onClick={handleExplainOpening}
        >
          {openingStatus === 'loading' ? 'Анализирую...' : 'Проанализировать дебют'}
        </button>
        {openingStatus === 'error' && (
          <div class="llm-explanation-panel__error">{openingErrorMessage}</div>
        )}
        {openingStatus === 'done' && openingResult?.message && (
          <div class="llm-explanation-panel__message">{openingResult.message}</div>
        )}
        {openingStatus === 'done' && openingResult?.explanation && (
          <>
            <div
              class={
                openingResult.verified
                  ? 'llm-explanation-panel__verified llm-explanation-panel__verified--true'
                  : 'llm-explanation-panel__verified llm-explanation-panel__verified--false'
              }
            >
              {openingResult.verified ? 'Проверено' : 'Не удалось проверить численно'}
            </div>
            <div class="llm-explanation-panel__summary">{openingResult.explanation.summary}</div>
            {openingResult.citation && (
              <details class="llm-explanation-panel__citation">
                <summary>
                  {openingResult.citation.title}{' '}
                  <span class="llm-explanation-panel__citation-source">
                    ({openingResult.citation.source})
                  </span>
                </summary>
                <div class="llm-explanation-panel__citation-text">
                  {openingResult.citation.text_snippet}
                </div>
              </details>
            )}
          </>
        )}
      </div>
```

Note this block deliberately has **no** `useEffect` resetting it on `nodeId` change (unlike the per-move block above it) — the design requires the opening result to survive board navigation.

- [ ] **Step 4: Add CSS**

Append to `frontend/src/renderer/assets/main.css`, after the existing `.llm-explanation-panel__citation-text` rule:

```css
.llm-explanation-panel__opening {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--ev-c-text-2, #888);
}
.llm-explanation-panel__opening h3 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
}
.llm-explanation-panel__opening label {
  margin-right: 12px;
  cursor: pointer;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: PASS (all tests, including every pre-existing test in this file — regression check)

- [ ] **Step 6: Run the full frontend test suite and both typechecks**

Run: `cd frontend && pnpm exec vitest run && pnpm run typecheck:web && pnpm run typecheck:node`
Expected: PASS (all tests, both typechecks clean)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx frontend/src/renderer/assets/main.css frontend/tests/renderer/components/LlmExplanationPanel.test.tsx
git commit -m "feat: add opening-analysis UI block to LlmExplanationPanel"
```
