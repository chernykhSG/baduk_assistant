# Calibration/Backtesting Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline dev tool that calibrates the three existing detectors (`weak_group`/`mistake`/`opening_loss`) against real games, using a self-consistency proxy (fast-visits vs deep-visits KataGo passes) to compute precision/recall/F1 per detector type for any candidate `detector_config.v{N}.json`.

**Architecture:** Detector thresholds/weights move from Python constants to a versioned JSON config, loaded once as a module-level default but overridable per-call — zero changes to any already-merged call site. A new `calibration/` subpackage reads real `.sgf` files (via `sgfmill`, a new dependency — the backend has never parsed SGF before), runs two KataGo passes per sampled position (fast/deep `maxVisits`), caches raw results to disk, and reports how often a fast-pass finding survives the deep pass.

**Tech Stack:** Python 3.12 / Pydantic v2 (backend, unchanged), `sgfmill>=1.1.1` (new optional dependency). No frontend changes.

**Spec:** `docs/superpowers/specs/2026-08-15-phase-2-calibration-harness-design.md`

## Global Constraints

- `detect_weak_group`/`detect_mistake`/`detect_opening_loss` gain new **defaulted** parameters only — every existing call site (`api/explain.py`, `api/explain_opening.py`, and all of `backend/tests/feature_extraction/{test_weak_group,test_mistake,test_opening_loss}.py`) must keep working with **zero changes**. This is the hard constraint the whole config-migration task is judged against.
- `k_open`/`k_end` live at the top level of `DetectorConfig` (siblings of `min_reliable_visits`), not nested inside `mistake` — they are shared by `mistake.py`, `opening_loss.py`, and `api/schemas.py`'s `ExplainOpeningRequest` validator. Do not duplicate the value in more than one place.
- The calibration corpus path is `BADUK_CALIBRATION_GAMES_PATH` (env var) — never hardcode a real filesystem path anywhere in source, docs, or tests.
- `sgfmill` coordinates are `(row, col)` with row 0 at the board's bottom edge — this is numerically identical to "GTP row minus one". `sgfmill.common.format_vertex(move)` (no `board_size` argument) already returns a ready GTP-format string (`"A4"`, `"pass"` for `move=None`). Do not write custom coordinate arithmetic for this conversion, and do not use `board/gtp_coords.py` for it (that module solves a different, unrelated (x,y) system used elsewhere in this codebase).
- The disk cache directory (`backend/calibration_cache/`) is gitignored, same treatment as `backend/rag_store/`.
- The harness is an offline dev CLI (`python -m baduk_backend.feature_extraction.calibration.harness`), not a `[project.scripts]` entry point — same pattern as `python -m baduk_backend.rag.ingest`.

---

### Task 1: Versioned JSON detector config

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/detector_config.v1.json`
- Create: `backend/src/baduk_backend/feature_extraction/config_loader.py`
- Delete: `backend/src/baduk_backend/feature_extraction/config.py`
- Modify: `backend/src/baduk_backend/feature_extraction/weak_group.py`
- Modify: `backend/src/baduk_backend/feature_extraction/mistake.py`
- Modify: `backend/src/baduk_backend/feature_extraction/opening_loss.py`
- Modify: `backend/src/baduk_backend/api/schemas.py`
- Test: `backend/tests/feature_extraction/test_config_loader.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `WeakGroupConfig`, `MistakeConfig`, `OpeningLossConfig`, `DetectorConfig`, `load_detector_config(path: Path) -> DetectorConfig`, `DEFAULT_CONFIG: DetectorConfig`, `DEFAULT_CONFIG_PATH: Path` (all in `feature_extraction/config_loader.py`) — every later task in this plan imports `DEFAULT_CONFIG`/`DetectorConfig`/`load_detector_config` from here. `detect_weak_group`/`detect_mistake`/`detect_opening_loss` each gain `config`/`k_open`/`k_end`/`min_reliable_visits` defaulted parameters (exact set per function below) — Task 5's self-consistency evaluator calls all three with an explicit candidate `config`.

- [ ] **Step 1: Write the failing test for `config_loader.py`**

Create `backend/tests/feature_extraction/test_config_loader.py`:

```python
import json

import pytest

from baduk_backend.feature_extraction.config_loader import DetectorConfig, load_detector_config

_VALID_CONFIG = {
    "version": 1,
    "weak_group": {
        "w1_own_certainty": 0.4,
        "w2_boundary_certainty": 0.3,
        "w3_pv_focus": 0.2,
        "w4_liberties": 0.1,
        "max_liberties_norm": 8,
        "threshold_weak": 0.5,
        "pv_focus_top_k": 5,
        "pv_focus_distance_d": 2,
    },
    "mistake": {"threshold_mistake": 0.5, "severity_high": 6.0, "severity_medium": 1.5},
    "opening_loss": {"threshold_opening_loss": 3.0, "severity_medium": 5.0, "severity_high": 15.0},
    "k_open": 0.12,
    "k_end": 0.15,
    "min_reliable_visits": 500,
}


def test_load_detector_config_parses_valid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(_VALID_CONFIG), encoding="utf-8")

    config = load_detector_config(path)

    assert isinstance(config, DetectorConfig)
    assert config.weak_group.threshold_weak == 0.5
    assert config.mistake.severity_high == 6.0
    assert config.opening_loss.threshold_opening_loss == 3.0
    assert config.k_open == 0.12
    assert config.min_reliable_visits == 500


def test_load_detector_config_raises_on_missing_field(tmp_path):
    incomplete = dict(_VALID_CONFIG)
    del incomplete["k_open"]
    path = tmp_path / "bad-config.json"
    path.write_text(json.dumps(incomplete), encoding="utf-8")

    with pytest.raises(Exception):  # pydantic.ValidationError
        load_detector_config(path)


def test_default_config_path_is_the_bundled_v1_file():
    from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG, DEFAULT_CONFIG_PATH

    assert DEFAULT_CONFIG_PATH.name == "detector_config.v1.json"
    assert DEFAULT_CONFIG.version == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_config_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.config_loader'`

- [ ] **Step 3: Create `detector_config.v1.json`**

Create `backend/src/baduk_backend/feature_extraction/detector_config.v1.json` with the CURRENT values from `feature_extraction/config.py` (copied verbatim, nothing changed numerically):

```json
{
  "version": 1,
  "weak_group": {
    "w1_own_certainty": 0.4,
    "w2_boundary_certainty": 0.3,
    "w3_pv_focus": 0.2,
    "w4_liberties": 0.1,
    "max_liberties_norm": 8,
    "threshold_weak": 0.5,
    "pv_focus_top_k": 5,
    "pv_focus_distance_d": 2
  },
  "mistake": {
    "threshold_mistake": 0.5,
    "severity_high": 6.0,
    "severity_medium": 1.5
  },
  "opening_loss": {
    "threshold_opening_loss": 3.0,
    "severity_medium": 5.0,
    "severity_high": 15.0
  },
  "k_open": 0.12,
  "k_end": 0.15,
  "min_reliable_visits": 500
}
```

- [ ] **Step 4: Create `config_loader.py`**

Create `backend/src/baduk_backend/feature_extraction/config_loader.py`:

```python
import os
from pathlib import Path

from pydantic import BaseModel


class WeakGroupConfig(BaseModel):
    w1_own_certainty: float
    w2_boundary_certainty: float
    w3_pv_focus: float
    w4_liberties: float
    max_liberties_norm: int
    threshold_weak: float
    pv_focus_top_k: int
    pv_focus_distance_d: int


class MistakeConfig(BaseModel):
    threshold_mistake: float
    severity_high: float
    severity_medium: float


class OpeningLossConfig(BaseModel):
    threshold_opening_loss: float
    severity_medium: float
    severity_high: float


class DetectorConfig(BaseModel):
    version: int
    weak_group: WeakGroupConfig
    mistake: MistakeConfig
    opening_loss: OpeningLossConfig
    k_open: float
    k_end: float
    min_reliable_visits: int


DEFAULT_CONFIG_PATH = Path(__file__).parent / "detector_config.v1.json"


def load_detector_config(path: Path = DEFAULT_CONFIG_PATH) -> DetectorConfig:
    return DetectorConfig.model_validate_json(path.read_text(encoding="utf-8"))


DEFAULT_CONFIG: DetectorConfig = load_detector_config(
    Path(os.environ.get("BADUK_DETECTOR_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/test_config_loader.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 6: Delete `config.py` and refactor `weak_group.py`**

Delete `backend/src/baduk_backend/feature_extraction/config.py`.

Replace the entire contents of `backend/src/baduk_backend/feature_extraction/weak_group.py` with:

```python
import uuid

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.board.groups import Group, find_groups
from baduk_backend.board.gtp_coords import gtp_to_xy
from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG, WeakGroupConfig
from baduk_backend.feature_extraction.schemas import WeakGroupFinding


def _own_certainty(group: Group, ownership: list[float], board_x_size: int) -> float:
    values = [abs(ownership[y * board_x_size + x]) for x, y in group.stones]
    return sum(values) / len(values)


def _boundary_points(group: Group, board_x_size: int, board_y_size: int) -> set[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for x, y in group.stones:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < board_x_size and 0 <= ny < board_y_size:
                    points.add((nx, ny))
    return points - set(group.stones)


def _boundary_certainty(
    group: Group,
    ownership: list[float],
    board_x_size: int,
    board_y_size: int,
    board: list[list[str | None]],
) -> float:
    points = [
        (x, y) for x, y in _boundary_points(group, board_x_size, board_y_size) if board[y][x] is None
    ]
    if not points:
        return 1.0
    values = [abs(ownership[y * board_x_size + x]) for x, y in points]
    return sum(values) / len(values)


def _pv_focus(group: Group, move_infos: list, board_y_size: int, config: WeakGroupConfig) -> float:
    top_moves = move_infos[: config.pv_focus_top_k]
    if not top_moves:
        return 0.0
    hits = 0
    for move_info in top_moves:
        vertex = gtp_to_xy(move_info.move, board_y_size)
        if vertex is None:
            continue
        mx, my = vertex
        if any(abs(mx - sx) + abs(my - sy) <= config.pv_focus_distance_d for sx, sy in group.stones):
            hits += 1
    return hits / len(top_moves)


def _weak_score(
    own_certainty: float,
    boundary_certainty: float,
    pv_focus: float,
    liberties: int,
    config: WeakGroupConfig,
) -> float:
    score = (
        config.w1_own_certainty * (1 - own_certainty)
        + config.w2_boundary_certainty * (1 - boundary_certainty)
        + config.w3_pv_focus * pv_focus
        - config.w4_liberties * (liberties / config.max_liberties_norm)
    )
    # Guard against IEEE-754 rounding noise (e.g. 0.4+0.3+0.2-0.05 landing on
    # 0.8499999999999999 instead of 0.85) before the severity thresholds are
    # applied downstream.
    score = round(score, 9)
    return max(0.0, min(1.0, score))


def _severity(weak_score: float) -> str:
    if weak_score < 0.7:
        return "low"
    if weak_score < 0.85:
        return "medium"
    return "high"


def detect_weak_group(
    board: list[list[str | None]],
    board_x_size: int,
    board_y_size: int,
    analysis: AnalyzeResponse,
    turn_number: int,
    config: WeakGroupConfig = DEFAULT_CONFIG.weak_group,
    min_reliable_visits: int = DEFAULT_CONFIG.min_reliable_visits,
) -> WeakGroupFinding | None:
    if analysis.ownership is None:
        return None

    best: tuple[float, Group, float, float] | None = None
    for group in find_groups(board):
        own_cert = _own_certainty(group, analysis.ownership, board_x_size)
        boundary_cert = _boundary_certainty(group, analysis.ownership, board_x_size, board_y_size, board)
        pv_focus = _pv_focus(group, analysis.moveInfos, board_y_size, config)
        score = _weak_score(own_cert, boundary_cert, pv_focus, group.liberties, config)
        if score > config.threshold_weak and (best is None or score > best[0]):
            best = (score, group, own_cert, boundary_cert)

    if best is None:
        return None

    score, group, own_cert, boundary_cert = best
    confidence = min(analysis.rootInfo.visits / min_reliable_visits, 1.0)
    return WeakGroupFinding(
        finding_id=f"f_{uuid.uuid4().hex[:8]}",
        type="weak_group",
        turn_number=turn_number,
        stones=group.stones,
        color=group.color,
        weak_score=score,
        own_certainty=own_cert,
        boundary_certainty=boundary_cert,
        liberties=group.liberties,
        severity=_severity(score),
        confidence=confidence,
    )
```

- [ ] **Step 7: Refactor `mistake.py`**

Replace the entire contents of `backend/src/baduk_backend/feature_extraction/mistake.py` with:

```python
import uuid

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG, MistakeConfig
from baduk_backend.feature_extraction.schemas import MistakeFinding
from baduk_backend.feature_extraction.scoring import mover_favorability


def _empty_points(board: list[list[str | None]]) -> int:
    return sum(1 for row in board for cell in row if cell is None)


def _stage(
    board: list[list[str | None]],
    board_x_size: int,
    board_y_size: int,
    move_number: int,
    k_open: float,
    k_end: float,
) -> str:
    board_area = board_x_size * board_y_size
    if move_number <= board_area * k_open:
        return "opening"
    if _empty_points(board) <= board_area * k_end:
        return "endgame"
    return "middlegame"


def _severity(delta: float, config: MistakeConfig) -> str:
    if delta >= config.severity_high:
        return "high"
    if delta >= config.severity_medium:
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
    config: MistakeConfig = DEFAULT_CONFIG.mistake,
    k_open: float = DEFAULT_CONFIG.k_open,
    k_end: float = DEFAULT_CONFIG.k_end,
    min_reliable_visits: int = DEFAULT_CONFIG.min_reliable_visits,
) -> MistakeFinding | None:
    mover, move = next_move
    delta = mover_favorability(analysis_before.rootInfo.scoreLead, mover) - mover_favorability(
        analysis_after.rootInfo.scoreLead, mover
    )
    # Guard against IEEE-754 rounding noise before the threshold/severity
    # comparisons below, same precaution as weak_group's _weak_score().
    delta = round(delta, 9)
    if delta < config.threshold_mistake:
        return None

    confidence = min(analysis_before.rootInfo.visits, analysis_after.rootInfo.visits) / min_reliable_visits
    confidence = min(confidence, 1.0)

    return MistakeFinding(
        finding_id=f"f_{uuid.uuid4().hex[:8]}",
        turn_number=turn_number,
        color=mover,
        move=move,
        delta_score=delta,
        stage=_stage(board, board_x_size, board_y_size, turn_number, k_open, k_end),
        severity=_severity(delta, config),
        confidence=confidence,
    )
```

- [ ] **Step 8: Refactor `opening_loss.py`**

Replace the entire contents of `backend/src/baduk_backend/feature_extraction/opening_loss.py` with:

```python
import uuid

from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG, OpeningLossConfig
from baduk_backend.feature_extraction.schemas import OpeningLossFinding
from baduk_backend.feature_extraction.scoring import mover_favorability


def _severity(delta: float, config: OpeningLossConfig) -> str:
    if delta >= config.severity_high:
        return "high"
    if delta >= config.severity_medium:
        return "medium"
    return "low"


def detect_opening_loss(
    moves: list[list[str]],
    sequence: list[tuple[int, float, int]],
    color: str,
    board_x_size: int,
    board_y_size: int,
    config: OpeningLossConfig = DEFAULT_CONFIG.opening_loss,
    k_open: float = DEFAULT_CONFIG.k_open,
    min_reliable_visits: int = DEFAULT_CONFIG.min_reliable_visits,
) -> OpeningLossFinding | None:
    """`sequence` is a list of (turn_number, score_lead, visits), one entry
    per turn 0..window_end, where turn 0 is the empty-board root position and
    turn k is the position after the k-th move. The caller (the API layer)
    is responsible for guaranteeing full coverage of the window - this
    function trusts it, the same way detect_mistake() trusts its board
    argument."""
    board_area = board_x_size * board_y_size
    window_end = min(int(board_area * k_open), len(moves))
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
            min_confidence_ratio, visits_before / min_reliable_visits, visits_after / min_reliable_visits
        )

    # Guard against IEEE-754 rounding noise, same precaution as weak_group/mistake.
    total_delta = round(total_delta, 9)
    if total_delta < config.threshold_opening_loss:
        return None

    return OpeningLossFinding(
        finding_id=f"f_{uuid.uuid4().hex[:8]}",
        type="opening_loss",
        color=color,
        move_range=(1, window_end),
        delta_score=total_delta,
        severity=_severity(total_delta, config),
        confidence=min(min_confidence_ratio, 1.0),
    )
```

- [ ] **Step 9: Update `api/schemas.py`'s import**

In `backend/src/baduk_backend/api/schemas.py`, replace the import line:

```python
from baduk_backend.feature_extraction.config import K_OPEN
```

with:

```python
from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG
```

And in `ExplainOpeningRequest._sequence_matches_opening_window`, replace:

```python
        window_end = min(int(board_area * K_OPEN), len(self.moves))
```

with:

```python
        window_end = min(int(board_area * DEFAULT_CONFIG.k_open), len(self.moves))
```

- [ ] **Step 10: Run the full backend test suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS — every pre-existing test in `test_weak_group.py`, `test_mistake.py`, `test_opening_loss.py`, `test_api_explain.py`, `test_api_explain_opening.py` passes UNCHANGED (same assertions, same expected values). This is the regression gate this task is judged against. If any of these files needed a single line changed to pass, that is a plan/global-constraint violation — stop and report it rather than editing a test to make it pass.

- [ ] **Step 11: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/detector_config.v1.json backend/src/baduk_backend/feature_extraction/config_loader.py backend/src/baduk_backend/feature_extraction/weak_group.py backend/src/baduk_backend/feature_extraction/mistake.py backend/src/baduk_backend/feature_extraction/opening_loss.py backend/src/baduk_backend/api/schemas.py backend/tests/feature_extraction/test_config_loader.py
git rm backend/src/baduk_backend/feature_extraction/config.py
git commit -m "feat: move detector thresholds to a versioned JSON config"
```

---

### Task 2: SGF corpus reading (`games.py`)

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/calibration/__init__.py`
- Create: `backend/src/baduk_backend/feature_extraction/calibration/games.py`
- Test: `backend/tests/feature_extraction/calibration/__init__.py`
- Test: `backend/tests/feature_extraction/calibration/test_games.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CalibrationGame` (fields: `moves: list[list[str]]`, `board_size: int`, `rules: str`, `komi: float`), `load_game(sgf_path: Path) -> CalibrationGame`, `sample_games(corpus_dir: Path, n: int, seed: int) -> list[Path]`, `sample_positions(num_moves: int, stride: int) -> list[int]` (all in `feature_extraction/calibration/games.py`) — Task 5's self-consistency evaluator and Task 6's harness both use all four names directly.

- [ ] **Step 1: Write the failing tests**

Create `backend/src/baduk_backend/feature_extraction/calibration/__init__.py` (empty file).

Create `backend/tests/feature_extraction/calibration/__init__.py` (empty file).

Create `backend/tests/feature_extraction/calibration/test_games.py`:

```python
import pytest

from baduk_backend.feature_extraction.calibration.games import load_game, sample_games, sample_positions

# Same fixture moves already verified against real GTP output in
# frontend/tests/renderer/board/gameRequestBuilder.test.ts's
# buildAnalyzeRequest test - qd->R16, dc->D17, oq->P3 on a 19x19 board -
# cross-checked against that already-passing test, not invented here.
_FIXTURE_SGF = "(;GM[1]FF[4]SZ[19]KM[7.5]RU[Chinese];B[qd];W[dc];B[oq])"


def test_load_game_parses_moves_board_size_rules_and_komi(tmp_path):
    sgf_path = tmp_path / "fixture.sgf"
    sgf_path.write_text(_FIXTURE_SGF, encoding="utf-8")

    game = load_game(sgf_path)

    assert game.board_size == 19
    assert game.rules == "chinese"
    assert game.komi == pytest.approx(7.5)
    assert game.moves == [["B", "R16"], ["W", "D17"], ["B", "P3"]]


def test_load_game_defaults_rules_and_komi_when_absent(tmp_path):
    sgf_path = tmp_path / "no-metadata.sgf"
    sgf_path.write_text("(;GM[1]FF[4]SZ[9];B[ee])", encoding="utf-8")

    game = load_game(sgf_path)

    assert game.rules == "chinese"
    assert game.komi == pytest.approx(7.5)


def test_load_game_falls_back_to_chinese_for_unrecognized_rules(tmp_path):
    sgf_path = tmp_path / "weird-rules.sgf"
    sgf_path.write_text("(;GM[1]FF[4]SZ[9]RU[NotARuleset];B[ee])", encoding="utf-8")

    game = load_game(sgf_path)

    assert game.rules == "chinese"


def test_load_game_includes_pass_moves(tmp_path):
    sgf_path = tmp_path / "with-pass.sgf"
    sgf_path.write_text("(;GM[1]FF[4]SZ[9];B[ee];W[])", encoding="utf-8")

    game = load_game(sgf_path)

    assert game.moves == [["B", "E5"], ["W", "pass"]]


def test_sample_games_is_deterministic_with_the_same_seed(tmp_path):
    for i in range(5):
        (tmp_path / f"game{i}.sgf").write_text(_FIXTURE_SGF, encoding="utf-8")

    first = sample_games(tmp_path, n=3, seed=42)
    second = sample_games(tmp_path, n=3, seed=42)

    assert first == second
    assert len(first) == 3


def test_sample_games_caps_at_the_corpus_size(tmp_path):
    (tmp_path / "only-game.sgf").write_text(_FIXTURE_SGF, encoding="utf-8")

    result = sample_games(tmp_path, n=20, seed=0)

    assert len(result) == 1


def test_sample_games_raises_on_an_empty_corpus(tmp_path):
    with pytest.raises(RuntimeError, match="no .sgf files"):
        sample_games(tmp_path, n=3, seed=0)


def test_sample_positions_returns_turns_by_stride():
    assert sample_positions(num_moves=23, stride=5) == [5, 10, 15, 20]


def test_sample_positions_returns_empty_for_a_short_game():
    assert sample_positions(num_moves=3, stride=5) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_games.py -v`
Expected: FAIL — `ModuleNotFoundError` (module doesn't exist yet) or `ImportError: sgfmill` if the dependency isn't installed yet (see Step 3).

- [ ] **Step 3: Add the `sgfmill` dependency**

In `backend/pyproject.toml`, add a new entry to `[project.optional-dependencies]` (alongside the existing `llama`/`rag` entries):

```toml
calibration = ["sgfmill>=1.1.1"]
```

Install it into the local dev environment: `cd backend && .venv\Scripts\pip.exe install sgfmill>=1.1.1` (or `.venv\Scripts\uv.exe pip install -e ".[calibration]"` if `uv` is available in PATH on this machine — see `backend/README.md` for the documented `.venv`-direct fallback).

- [ ] **Step 4: Write `games.py`**

Create `backend/src/baduk_backend/feature_extraction/calibration/games.py`:

```python
import random
from pathlib import Path

from pydantic import BaseModel
from sgfmill import sgf, sgf_moves
from sgfmill.common import format_vertex

_KNOWN_RULES = {"chinese", "japanese", "korean", "aga", "nz", "tromp-taylor"}
_DEFAULT_RULES = "chinese"
_DEFAULT_KOMI = 7.5


class CalibrationGame(BaseModel):
    moves: list[list[str]]
    board_size: int
    rules: str
    komi: float


def _map_rules(raw: str | None) -> str:
    if raw is None:
        return _DEFAULT_RULES
    normalized = raw.lower().strip()
    return normalized if normalized in _KNOWN_RULES else _DEFAULT_RULES


def load_game(sgf_path: Path) -> CalibrationGame:
    game = sgf.Sgf_game.from_bytes(sgf_path.read_bytes())
    board_size = game.get_size()
    _, plays = sgf_moves.get_setup_and_moves(game)

    # format_vertex(None) already returns "pass" - no separate branch needed.
    moves = [[colour.upper(), format_vertex(move)] for colour, move in plays]

    root = game.get_root()
    raw_rules = root.get("RU") if root.has_property("RU") else None
    komi = game.get_komi() if root.has_property("KM") else _DEFAULT_KOMI

    return CalibrationGame(moves=moves, board_size=board_size, rules=_map_rules(raw_rules), komi=komi)


def sample_games(corpus_dir: Path, n: int, seed: int = 0) -> list[Path]:
    all_games = sorted(corpus_dir.rglob("*.sgf"))
    if not all_games:
        raise RuntimeError(f"no .sgf files found under {corpus_dir}")
    rng = random.Random(seed)
    return rng.sample(all_games, min(n, len(all_games)))


def sample_positions(num_moves: int, stride: int = 5) -> list[int]:
    return list(range(stride, num_moves + 1, stride))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_games.py -v`
Expected: PASS (all 9 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/src/baduk_backend/feature_extraction/calibration/__init__.py backend/src/baduk_backend/feature_extraction/calibration/games.py backend/tests/feature_extraction/calibration/__init__.py backend/tests/feature_extraction/calibration/test_games.py
git commit -m "feat: add SGF corpus reading for the calibration harness"
```

---

### Task 3: Disk-cached KataGo analysis (`cache.py`)

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/calibration/cache.py`
- Modify: `backend/.gitignore`
- Test: `backend/tests/feature_extraction/calibration/test_cache.py`

**Interfaces:**
- Consumes: `CalibrationGame` (Task 2, `feature_extraction.calibration.games`).
- Produces: `DEFAULT_CACHE_DIR: Path`, `fetch_analysis(engine_manager, sgf_path: Path, game: CalibrationGame, turn_number: int, max_visits: int, cache_dir: Path = DEFAULT_CACHE_DIR) -> AnalyzeResponse` (`feature_extraction/calibration/cache.py`) — Task 5's self-consistency evaluator calls this for every sampled position, at both the fast and deep visit budgets.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/feature_extraction/calibration/test_cache.py`:

```python
from pathlib import Path

from baduk_backend.feature_extraction.calibration.cache import fetch_analysis
from baduk_backend.feature_extraction.calibration.games import CalibrationGame


class _FakeEngineManager:
    def __init__(self, response: dict):
        self._response = response
        self.calls = 0

    def analyze(self, request: dict, timeout: float = 30.0) -> dict:
        self.calls += 1
        return {**self._response, "id": request["id"]}


def _fake_response() -> dict:
    return {
        "id": "x",
        "moveInfos": [],
        "rootInfo": {"winrate": 0.5, "scoreLead": 0.0, "visits": 100},
        "ownership": [0.0] * 81,
    }


def _game() -> CalibrationGame:
    return CalibrationGame(moves=[["B", "E5"]], board_size=9, rules="chinese", komi=7.5)


def test_fetch_analysis_calls_the_engine_on_a_fresh_position(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    response = fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)

    assert manager.calls == 1
    assert response.rootInfo.visits == 100


def test_fetch_analysis_reuses_the_cache_on_a_repeat_request(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)
    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)

    assert manager.calls == 1


def test_fetch_analysis_treats_different_visit_budgets_as_different_cache_entries(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)
    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 500, cache_dir=tmp_path)

    assert manager.calls == 2


def test_fetch_analysis_treats_different_turn_numbers_as_different_cache_entries(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)
    fetch_analysis(manager, Path("game.sgf"), _game(), 2, 50, cache_dir=tmp_path)

    assert manager.calls == 2


def test_fetch_analysis_sends_the_full_move_list_and_requested_turn(tmp_path):
    manager = _FakeEngineManager(_fake_response())
    game = CalibrationGame(moves=[["B", "E5"], ["W", "C3"]], board_size=9, rules="chinese", komi=7.5)
    captured: dict = {}

    class _CapturingManager(_FakeEngineManager):
        def analyze(self, request: dict, timeout: float = 30.0) -> dict:
            captured.update(request)
            return super().analyze(request, timeout)

    fetch_analysis(_CapturingManager(_fake_response()), Path("game.sgf"), game, 1, 50, cache_dir=tmp_path)

    assert captured["moves"] == [["B", "E5"], ["W", "C3"]]
    assert captured["analyzeTurns"] == [1]
    assert captured["maxVisits"] == 50
    assert captured["includeOwnership"] is True
    assert captured["boardXSize"] == 9
    assert captured["rules"] == "chinese"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.calibration.cache'`

- [ ] **Step 3: Write `cache.py`**

Create `backend/src/baduk_backend/feature_extraction/calibration/cache.py`:

```python
import hashlib
import uuid
from pathlib import Path

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.calibration.games import CalibrationGame

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[4] / "calibration_cache"


def _cache_key(sgf_path: Path, turn_number: int, max_visits: int) -> str:
    raw = f"{sgf_path.resolve()}|{turn_number}|{max_visits}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_analysis(
    engine_manager,
    sgf_path: Path,
    game: CalibrationGame,
    turn_number: int,
    max_visits: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> AnalyzeResponse:
    cache_file = cache_dir / f"{_cache_key(sgf_path, turn_number, max_visits)}.json"
    if cache_file.exists():
        return AnalyzeResponse.model_validate_json(cache_file.read_text(encoding="utf-8"))

    request = {
        "id": str(uuid.uuid4()),
        "moves": game.moves,
        "rules": game.rules,
        "komi": game.komi,
        "boardXSize": game.board_size,
        "boardYSize": game.board_size,
        "analyzeTurns": [turn_number],
        "maxVisits": max_visits,
        "includeOwnership": True,
    }
    raw_response = engine_manager.analyze(request)
    response = AnalyzeResponse.model_validate(raw_response)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(response.model_dump_json(), encoding="utf-8")
    return response
```

`DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[4] / "calibration_cache"` resolves to `backend/calibration_cache` — verify this by checking `Path(__file__).resolve()` from `backend/src/baduk_backend/feature_extraction/calibration/cache.py`: `.parents[0]` is `calibration/`, `[1]` is `feature_extraction/`, `[2]` is `baduk_backend/`, `[3]` is `src/`, `[4]` is `backend/`. This mirrors the existing pattern in `backend/src/baduk_backend/rag/store.py`'s `DEFAULT_STORE_PATH = Path(__file__).resolve().parents[3] / "rag_store"` (one fewer `parents` level there because `store.py` sits one directory shallower, directly in `rag/`, not in a nested `calibration/` subpackage).

- [ ] **Step 4: Gitignore the cache directory**

In `backend/.gitignore`, add a new line alongside the existing `rag_store/` entry:

```
calibration_cache/
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_cache.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/calibration/cache.py backend/.gitignore backend/tests/feature_extraction/calibration/test_cache.py
git commit -m "feat: add disk-cached KataGo analysis for the calibration harness"
```

---

### Task 4: Precision/recall/F1 (`metrics.py`)

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/calibration/metrics.py`
- Test: `backend/tests/feature_extraction/calibration/test_metrics.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ConfusionCounts` (fields `tp: int`, `fp: int`, `fn: int`, `tn: int`, all defaulting to `0`; methods `precision() -> float | None`, `recall() -> float | None`, `f1() -> float | None`) — Task 5's self-consistency evaluator and Task 6's harness report formatter both use this type.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/feature_extraction/calibration/test_metrics.py`:

```python
import pytest

from baduk_backend.feature_extraction.calibration.metrics import ConfusionCounts


def test_precision_recall_f1_on_typical_counts():
    counts = ConfusionCounts(tp=8, fp=2, fn=2, tn=18)

    assert counts.precision() == pytest.approx(0.8)  # 8 / (8+2)
    assert counts.recall() == pytest.approx(0.8)  # 8 / (8+2)
    assert counts.f1() == pytest.approx(0.8)


def test_precision_is_none_when_nothing_was_flagged():
    counts = ConfusionCounts(tp=0, fp=0, fn=3, tn=10)

    assert counts.precision() is None
    assert counts.recall() == pytest.approx(0.0)  # 0 / (0+3)


def test_recall_is_none_when_nothing_should_have_been_flagged():
    counts = ConfusionCounts(tp=0, fp=3, fn=0, tn=10)

    assert counts.recall() is None
    assert counts.precision() == pytest.approx(0.0)  # 0 / (0+3)


def test_f1_is_none_when_precision_or_recall_is_none():
    counts = ConfusionCounts(tp=0, fp=0, fn=0, tn=20)

    assert counts.precision() is None
    assert counts.recall() is None
    assert counts.f1() is None


def test_confusion_counts_defaults_to_all_zero():
    counts = ConfusionCounts()

    assert (counts.tp, counts.fp, counts.fn, counts.tn) == (0, 0, 0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.calibration.metrics'`

- [ ] **Step 3: Write `metrics.py`**

Create `backend/src/baduk_backend/feature_extraction/calibration/metrics.py`:

```python
from dataclasses import dataclass


@dataclass
class ConfusionCounts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    def precision(self) -> float | None:
        denom = self.tp + self.fp
        return self.tp / denom if denom else None

    def recall(self) -> float | None:
        denom = self.tp + self.fn
        return self.tp / denom if denom else None

    def f1(self) -> float | None:
        precision = self.precision()
        recall = self.recall()
        if precision is None or recall is None or (precision + recall) == 0:
            return None
        return 2 * precision * recall / (precision + recall)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_metrics.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/calibration/metrics.py backend/tests/feature_extraction/calibration/test_metrics.py
git commit -m "feat: add precision/recall/F1 counting for the calibration harness"
```

---

### Task 5: Self-consistency evaluation (`self_consistency.py`)

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/calibration/self_consistency.py`
- Test: `backend/tests/feature_extraction/calibration/test_self_consistency.py`

**Interfaces:**
- Consumes: `CalibrationGame`, `sample_positions` (Task 2, `feature_extraction.calibration.games`); `fetch_analysis`, `DEFAULT_CACHE_DIR` (Task 3, `feature_extraction.calibration.cache`); `ConfusionCounts` (Task 4, `feature_extraction.calibration.metrics`); `DetectorConfig` (Task 1, `feature_extraction.config_loader`); `detect_weak_group`/`detect_mistake`/`detect_opening_loss` (existing, now config-aware per Task 1); `apply_moves` (existing, `board.board_state`); `WeakGroupFinding` (existing, `feature_extraction.schemas`).
- Produces: `classify_finding(candidate, reference) -> str` (returns `"tp"`/`"fp"`/`"fn"`/`"tn"`), `evaluate_weak_group_and_mistake(games, fast_visits, deep_visits, config, engine_manager, stride=5, cache_dir=DEFAULT_CACHE_DIR) -> dict[str, ConfusionCounts]` (keys `"weak_group"`/`"mistake"`), `evaluate_opening_loss(games, fast_visits, deep_visits, config, engine_manager, cache_dir=DEFAULT_CACHE_DIR) -> ConfusionCounts` — Task 6's harness calls both evaluator functions directly.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/feature_extraction/calibration/test_self_consistency.py`:

```python
from pathlib import Path

import pytest

from baduk_backend.feature_extraction.calibration.games import CalibrationGame
from baduk_backend.feature_extraction.calibration.self_consistency import (
    classify_finding,
    evaluate_opening_loss,
    evaluate_weak_group_and_mistake,
)
from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG
from baduk_backend.feature_extraction.schemas import MistakeFinding, WeakGroupFinding


def _weak_group_finding(stones):
    return WeakGroupFinding(
        finding_id="f1",
        type="weak_group",
        turn_number=1,
        stones=stones,
        color="B",
        weak_score=0.9,
        own_certainty=0.1,
        boundary_certainty=0.1,
        liberties=2,
        severity="high",
        confidence=1.0,
    )


def _mistake_finding():
    return MistakeFinding(
        finding_id="f2",
        turn_number=1,
        color="B",
        move="Q4",
        delta_score=3.0,
        stage="middlegame",
        severity="medium",
        confidence=1.0,
    )


def test_classify_finding_both_present_and_matching_is_tp():
    a = _weak_group_finding([(4, 4)])
    b = _weak_group_finding([(4, 4)])

    assert classify_finding(a, b) == "tp"


def test_classify_finding_both_present_but_different_groups_is_fp_not_tp():
    a = _weak_group_finding([(4, 4)])
    b = _weak_group_finding([(2, 2)])

    assert classify_finding(a, b) == "fp"


def test_classify_finding_only_candidate_present_is_fp():
    assert classify_finding(_mistake_finding(), None) == "fp"


def test_classify_finding_only_reference_present_is_fn():
    assert classify_finding(None, _mistake_finding()) == "fn"


def test_classify_finding_neither_present_is_tn():
    assert classify_finding(None, None) == "tn"


def test_classify_finding_non_weak_group_findings_match_on_presence_alone():
    assert classify_finding(_mistake_finding(), _mistake_finding()) == "tp"


class _FakeEngineManager:
    """Returns a fixed rootInfo/ownership regardless of the request, so every
    detector is deterministic and the test never talks to a real KataGo."""

    def __init__(self, score_lead: float = 0.0, visits: int = 1000):
        self.score_lead = score_lead
        self.visits = visits
        self.calls = 0

    def analyze(self, request: dict, timeout: float = 30.0) -> dict:
        self.calls += 1
        board_area = request["boardXSize"] * request["boardYSize"]
        return {
            "id": request["id"],
            "moveInfos": [],
            "rootInfo": {"winrate": 0.5, "scoreLead": self.score_lead, "visits": self.visits},
            "ownership": [1.0] * board_area,  # fully resolved - weak_group never fires
        }


def test_evaluate_weak_group_and_mistake_returns_both_keys(tmp_path):
    game = CalibrationGame(
        moves=[["B", "E5"], ["W", "C3"], ["B", "G7"], ["W", "C7"], ["B", "E3"], ["W", "G3"]],
        board_size=9,
        rules="chinese",
        komi=7.5,
    )
    manager = _FakeEngineManager()

    result = evaluate_weak_group_and_mistake(
        [(Path("game.sgf"), game)], fast_visits=50, deep_visits=500,
        config=DEFAULT_CONFIG, engine_manager=manager, stride=5, cache_dir=tmp_path,
    )

    assert set(result.keys()) == {"weak_group", "mistake"}
    # A flat scoreLead across every sampled position means no mistake ever
    # fires (Δ=0 < THRESHOLD_MISTAKE) on either pass - a clean TN, not a
    # crash, is the behavior under test here.
    assert result["mistake"].tp == 0
    assert result["mistake"].fp == 0


def test_evaluate_opening_loss_runs_for_both_colors(tmp_path):
    game = CalibrationGame(
        moves=[["B", "E5"], ["W", "C3"], ["B", "G7"], ["W", "C7"]],
        board_size=9,
        rules="chinese",
        komi=7.5,
    )
    manager = _FakeEngineManager()

    result = evaluate_opening_loss(
        [(Path("game.sgf"), game)], fast_visits=50, deep_visits=500,
        config=DEFAULT_CONFIG, engine_manager=manager, cache_dir=tmp_path,
    )

    assert (result.tp, result.fp, result.fn, result.tn) != (0, 0, 0, 0)


def test_evaluate_opening_loss_reuses_cache_across_fast_and_deep_calls_of_the_same_budget(tmp_path):
    game = CalibrationGame(moves=[["B", "E5"], ["W", "C3"]], board_size=9, rules="chinese", komi=7.5)
    manager = _FakeEngineManager()

    evaluate_opening_loss(
        [(Path("game.sgf"), game)], fast_visits=50, deep_visits=500,
        config=DEFAULT_CONFIG, engine_manager=manager, cache_dir=tmp_path,
    )
    calls_after_first_run = manager.calls
    evaluate_opening_loss(
        [(Path("game.sgf"), game)], fast_visits=50, deep_visits=500,
        config=DEFAULT_CONFIG, engine_manager=manager, cache_dir=tmp_path,
    )

    assert manager.calls == calls_after_first_run  # second run is fully cached
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_self_consistency.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.calibration.self_consistency'`

- [ ] **Step 3: Write `self_consistency.py`**

Create `backend/src/baduk_backend/feature_extraction/calibration/self_consistency.py`:

```python
from pathlib import Path

from baduk_backend.board.board_state import apply_moves
from baduk_backend.feature_extraction.calibration.cache import DEFAULT_CACHE_DIR, fetch_analysis
from baduk_backend.feature_extraction.calibration.games import CalibrationGame, sample_positions
from baduk_backend.feature_extraction.calibration.metrics import ConfusionCounts
from baduk_backend.feature_extraction.config_loader import DetectorConfig
from baduk_backend.feature_extraction.mistake import detect_mistake
from baduk_backend.feature_extraction.opening_loss import detect_opening_loss
from baduk_backend.feature_extraction.schemas import WeakGroupFinding
from baduk_backend.feature_extraction.weak_group import detect_weak_group


def classify_finding(candidate, reference) -> str:
    """Classifies one sampled position's self-consistency outcome.
    `candidate` is the finding from the fast-budget pass, `reference` from
    the deep-budget pass - both computed with the SAME candidate detector
    config, so this measures the candidate config's robustness to KataGo's
    own visit-budget noise, not a different scoring methodology."""
    same = candidate is not None and reference is not None and _same_finding(candidate, reference)
    if same:
        return "tp"
    if candidate is not None:
        return "fp"
    if reference is not None:
        return "fn"
    return "tn"


def _same_finding(a, b) -> bool:
    if isinstance(a, WeakGroupFinding):
        return set(a.stones) == set(b.stones)
    return True  # mistake/opening_loss: presence alone is the signal


def _accumulate(counts: ConfusionCounts, label: str) -> None:
    if label == "tp":
        counts.tp += 1
    elif label == "fp":
        counts.fp += 1
    elif label == "fn":
        counts.fn += 1
    else:
        counts.tn += 1


def evaluate_weak_group_and_mistake(
    games: list[tuple[Path, CalibrationGame]],
    fast_visits: int,
    deep_visits: int,
    config: DetectorConfig,
    engine_manager,
    stride: int = 5,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> dict[str, ConfusionCounts]:
    weak_group_counts = ConfusionCounts()
    mistake_counts = ConfusionCounts()

    for sgf_path, game in games:
        for turn in sample_positions(len(game.moves), stride):
            fast_after = fetch_analysis(engine_manager, sgf_path, game, turn, fast_visits, cache_dir)
            deep_after = fetch_analysis(engine_manager, sgf_path, game, turn, deep_visits, cache_dir)
            board_after = apply_moves(game.moves[:turn], game.board_size, game.board_size)

            candidate_wg = detect_weak_group(
                board_after, game.board_size, game.board_size, fast_after, turn,
                config.weak_group, config.min_reliable_visits,
            )
            reference_wg = detect_weak_group(
                board_after, game.board_size, game.board_size, deep_after, turn,
                config.weak_group, config.min_reliable_visits,
            )
            _accumulate(weak_group_counts, classify_finding(candidate_wg, reference_wg))

            fast_before = fetch_analysis(engine_manager, sgf_path, game, turn - 1, fast_visits, cache_dir)
            deep_before = fetch_analysis(engine_manager, sgf_path, game, turn - 1, deep_visits, cache_dir)
            board_before = apply_moves(game.moves[: turn - 1], game.board_size, game.board_size)
            next_move = (game.moves[turn - 1][0], game.moves[turn - 1][1])

            candidate_mistake = detect_mistake(
                board_before, fast_before, fast_after, next_move, game.board_size, game.board_size, turn,
                config.mistake, config.k_open, config.k_end, config.min_reliable_visits,
            )
            reference_mistake = detect_mistake(
                board_before, deep_before, deep_after, next_move, game.board_size, game.board_size, turn,
                config.mistake, config.k_open, config.k_end, config.min_reliable_visits,
            )
            _accumulate(mistake_counts, classify_finding(candidate_mistake, reference_mistake))

    return {"weak_group": weak_group_counts, "mistake": mistake_counts}


def evaluate_opening_loss(
    games: list[tuple[Path, CalibrationGame]],
    fast_visits: int,
    deep_visits: int,
    config: DetectorConfig,
    engine_manager,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> ConfusionCounts:
    counts = ConfusionCounts()

    for sgf_path, game in games:
        board_area = game.board_size * game.board_size
        window_end = min(int(board_area * config.k_open), len(game.moves))

        for color in ("B", "W"):
            fast_sequence = []
            deep_sequence = []
            for turn in range(window_end + 1):
                fast = fetch_analysis(engine_manager, sgf_path, game, turn, fast_visits, cache_dir)
                deep = fetch_analysis(engine_manager, sgf_path, game, turn, deep_visits, cache_dir)
                fast_sequence.append((turn, fast.rootInfo.scoreLead, fast.rootInfo.visits))
                deep_sequence.append((turn, deep.rootInfo.scoreLead, deep.rootInfo.visits))

            candidate = detect_opening_loss(
                game.moves, fast_sequence, color, game.board_size, game.board_size,
                config.opening_loss, config.k_open, config.min_reliable_visits,
            )
            reference = detect_opening_loss(
                game.moves, deep_sequence, color, game.board_size, game.board_size,
                config.opening_loss, config.k_open, config.min_reliable_visits,
            )
            _accumulate(counts, classify_finding(candidate, reference))

    return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_self_consistency.py -v`
Expected: PASS (all 9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/calibration/self_consistency.py backend/tests/feature_extraction/calibration/test_self_consistency.py
git commit -m "feat: add self-consistency evaluation for the calibration harness"
```

---

### Task 6: Harness CLI

**Files:**
- Create: `backend/src/baduk_backend/feature_extraction/calibration/harness.py`
- Test: `backend/tests/feature_extraction/calibration/test_harness_integration.py`

**Interfaces:**
- Consumes: `load_game`, `sample_games` (Task 2); `evaluate_weak_group_and_mistake`, `evaluate_opening_loss` (Task 5); `ConfusionCounts` (Task 4); `DEFAULT_CONFIG_PATH`, `load_detector_config` (Task 1); `KataGoProfile`, `render_analysis_config` (existing, `config.profile`); `EngineManager`, `build_katago_command` (existing, `engine_manager`).
- Produces: `run_harness(games_dir, config_paths, games_sample, move_stride, seed, fast_visits, deep_visits) -> None` and a `main()` CLI entry point — nothing later in this plan depends on this task; it is the final integration point.

- [ ] **Step 1: Write `harness.py`**

This task has one small isolated unit worth TDD-ing on its own before the rest of the wiring: the corpus must tolerate a malformed `.sgf` file by skipping it with a warning, per the spec's Ошибки section — not crash the whole harness run. Write that as a failing test first.

- [ ] **Step 1a: Write the failing test for skip-on-malformed-SGF**

Create `backend/tests/feature_extraction/calibration/test_harness.py`:

```python
from pathlib import Path

from baduk_backend.feature_extraction.calibration.harness import _load_games_skipping_errors


def test_load_games_skipping_errors_skips_a_malformed_file_and_keeps_the_rest(tmp_path, capsys):
    good = tmp_path / "good.sgf"
    good.write_text("(;GM[1]FF[4]SZ[9];B[ee])", encoding="utf-8")
    bad = tmp_path / "bad.sgf"
    bad.write_text("this is not valid SGF at all {{{", encoding="utf-8")

    games = _load_games_skipping_errors([bad, good])

    assert len(games) == 1
    assert games[0][0] == good
    assert "bad.sgf" in capsys.readouterr().out


def test_load_games_skipping_errors_returns_everything_when_all_files_are_valid(tmp_path):
    good = tmp_path / "good.sgf"
    good.write_text("(;GM[1]FF[4]SZ[9];B[ee])", encoding="utf-8")

    games = _load_games_skipping_errors([good])

    assert len(games) == 1
```

- [ ] **Step 1b: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.feature_extraction.calibration.harness'`

- [ ] **Step 1c: Write the rest of `harness.py`**

The remaining wiring in this file (CLI argument parsing, `EngineManager` lifecycle, calling the Task 5 evaluators) has no isolated unit to TDD — it's verified by the integration test in Step 2 instead (this mirrors how `rag/ingest.py`'s `main()` and `llm/providers/llama.py` were verified in this project's history — a thin orchestration layer whose correctness is checked by the integration test, not a unit test of the wiring itself). Write it directly, alongside `_load_games_skipping_errors` from Step 1a.

Create `backend/src/baduk_backend/feature_extraction/calibration/harness.py`:

```python
import argparse
import os
import tempfile
from pathlib import Path

from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command
from baduk_backend.feature_extraction.calibration.games import CalibrationGame, load_game, sample_games
from baduk_backend.feature_extraction.calibration.metrics import ConfusionCounts
from baduk_backend.feature_extraction.calibration.self_consistency import (
    evaluate_opening_loss,
    evaluate_weak_group_and_mistake,
)
from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG_PATH, load_detector_config


def _load_games_skipping_errors(sgf_paths: list[Path]) -> list[tuple[Path, CalibrationGame]]:
    games: list[tuple[Path, CalibrationGame]] = []
    for path in sgf_paths:
        try:
            games.append((path, load_game(path)))
        except Exception as exc:
            print(f"WARNING: skipping unparseable SGF file {path}: {exc}")
    return games


def _build_engine_manager() -> tuple[EngineManager, str]:
    katago_binary = os.environ["BADUK_KATAGO_BINARY"]
    katago_model = os.environ["BADUK_KATAGO_MODEL"]
    profile = KataGoProfile(
        model_id="calibration-harness",
        display_name="Calibration harness profile",
        rules="chinese",
        board_size=19,
        komi=7.5,
        max_visits=500,
        num_analysis_threads=4,
    )
    home_data_dir = str(Path(katago_binary).parent)
    config_text = render_analysis_config(profile, home_data_dir_override=home_data_dir)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as config_file:
        config_file.write(config_text)
        config_path = config_file.name
    command = build_katago_command(katago_binary=katago_binary, config_path=config_path, model_path=katago_model)
    return EngineManager(command), config_path


def _format_number(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _format_row(name: str, counts: ConfusionCounts) -> str:
    return (
        f"{name:<15} TP={counts.tp:<4} FP={counts.fp:<4} FN={counts.fn:<4} TN={counts.tn:<4} "
        f"precision={_format_number(counts.precision())} recall={_format_number(counts.recall())} "
        f"F1={_format_number(counts.f1())}"
    )


def run_harness(
    games_dir: Path,
    config_paths: list[Path],
    games_sample: int,
    move_stride: int,
    seed: int,
    fast_visits: int,
    deep_visits: int,
) -> None:
    engine_manager, temp_config_path = _build_engine_manager()
    try:
        sgf_paths = sample_games(games_dir, n=games_sample, seed=seed)
        games = _load_games_skipping_errors(sgf_paths)
        print(f"Sampled {len(games)} games from {games_dir}")

        for config_path in config_paths or [DEFAULT_CONFIG_PATH]:
            config = load_detector_config(config_path)
            print(f"\n=== {config_path} ===")

            wg_and_mistake = evaluate_weak_group_and_mistake(
                games, fast_visits, deep_visits, config, engine_manager, stride=move_stride,
            )
            opening_loss_counts = evaluate_opening_loss(games, fast_visits, deep_visits, config, engine_manager)

            print(_format_row("weak_group", wg_and_mistake["weak_group"]))
            print(_format_row("mistake", wg_and_mistake["mistake"]))
            print(_format_row("opening_loss", opening_loss_counts))
    finally:
        engine_manager.stop()
        try:
            os.remove(temp_config_path)
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibration/backtesting harness for the feature-extraction detectors"
    )
    parser.add_argument("--games-sample", type=int, default=20)
    parser.add_argument("--move-stride", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--fast-visits", type=int, default=50)
    parser.add_argument("--deep-visits", type=int, default=500)
    parser.add_argument(
        "--config", action="append", type=Path, default=None,
        help="candidate detector_config.v{N}.json to evaluate (repeatable); defaults to the bundled v1 config",
    )
    args = parser.parse_args()

    raw_games_path = os.environ.get("BADUK_CALIBRATION_GAMES_PATH")
    if not raw_games_path:
        raise RuntimeError("BADUK_CALIBRATION_GAMES_PATH env var must be set to run the calibration harness")

    run_harness(
        Path(raw_games_path),
        args.config or [],
        args.games_sample,
        args.move_stride,
        args.seed,
        args.fast_visits,
        args.deep_visits,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the integration test**

Create `backend/tests/feature_extraction/calibration/test_harness_integration.py`:

```python
import os

import pytest

pytestmark = pytest.mark.integration


def test_harness_runs_end_to_end_on_a_small_real_sample(capsys, tmp_path):
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    games_path = os.environ.get("BADUK_CALIBRATION_GAMES_PATH")
    if not katago_binary or not katago_model or not games_path:
        pytest.skip(
            "BADUK_KATAGO_BINARY, BADUK_KATAGO_MODEL, and BADUK_CALIBRATION_GAMES_PATH "
            "must all be set to run this test"
        )

    from pathlib import Path

    from baduk_backend.feature_extraction.calibration.harness import run_harness

    run_harness(
        games_dir=Path(games_path),
        config_paths=[],
        games_sample=1,
        move_stride=10,
        seed=0,
        fast_visits=5,
        deep_visits=20,
    )

    output = capsys.readouterr().out
    assert "weak_group" in output
    assert "mistake" in output
    assert "opening_loss" in output
```

- [ ] **Step 3: Run the integration test if credentials are available, otherwise confirm it skips cleanly**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/feature_extraction/calibration/test_harness_integration.py -v -m integration`
Expected: PASS if `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL`/`BADUK_CALIBRATION_GAMES_PATH` are set on this machine (they are, per this project's established local setup — see `backend/README.md`); otherwise SKIPPED with the message from Step 2's `pytest.skip(...)`. Either outcome is acceptable; a hard FAIL is not.

- [ ] **Step 4: Run `test_harness.py` and the full backend test suite (non-integration)**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS — every test in the repository, including `test_harness.py`'s 2 new tests, all of Tasks 1-5's new tests, and every pre-existing test.

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/feature_extraction/calibration/harness.py backend/tests/feature_extraction/calibration/test_harness.py backend/tests/feature_extraction/calibration/test_harness_integration.py
git commit -m "feat: add calibration harness CLI"
```
