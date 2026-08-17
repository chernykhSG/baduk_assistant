from pathlib import Path

import pytest

pytest.importorskip("sgfmill")

from baduk_backend.feature_extraction.calibration.games import CalibrationGame  # noqa: E402
from baduk_backend.feature_extraction.calibration.self_consistency import (  # noqa: E402
    classify_finding,
    evaluate_opening_loss,
    evaluate_weak_group_and_mistake,
)
from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG  # noqa: E402
from baduk_backend.feature_extraction.schemas import MistakeFinding, WeakGroupFinding  # noqa: E402


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


class _FlakyEngineManager:
    """Like _FakeEngineManager, but raises RuntimeError on the Nth call
    (1-indexed) to analyze() and succeeds on every other call - simulates
    one bad/timed-out KataGo response amid otherwise-successful calls."""

    def __init__(self, fail_on_call: int, score_lead: float = 0.0, visits: int = 1000):
        self.fail_on_call = fail_on_call
        self.score_lead = score_lead
        self.visits = visits
        self.calls = 0

    def analyze(self, request: dict, timeout: float = 30.0) -> dict:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("simulated KataGo failure")
        board_area = request["boardXSize"] * request["boardYSize"]
        return {
            "id": request["id"],
            "moveInfos": [],
            "rootInfo": {"winrate": 0.5, "scoreLead": self.score_lead, "visits": self.visits},
            "ownership": [1.0] * board_area,
        }


def test_evaluate_weak_group_and_mistake_skips_a_failing_position_and_keeps_going(tmp_path, capsys):
    bad_game = CalibrationGame(
        moves=[["B", "E5"], ["W", "C3"], ["B", "G7"], ["W", "C7"], ["B", "E3"], ["W", "G3"]],
        board_size=9,
        rules="chinese",
        komi=7.5,
    )
    good_game = CalibrationGame(
        moves=[["B", "E5"], ["W", "C3"], ["B", "G7"], ["W", "C7"], ["B", "E3"], ["W", "G3"]],
        board_size=9,
        rules="chinese",
        komi=7.5,
    )
    # Fails on the very first engine call, i.e. bad_game's single sampled
    # position (turn 5); every later call (including all of good_game's)
    # succeeds.
    manager = _FlakyEngineManager(fail_on_call=1)

    result = evaluate_weak_group_and_mistake(
        [(Path("bad.sgf"), bad_game), (Path("good.sgf"), good_game)],
        fast_visits=50, deep_visits=500,
        config=DEFAULT_CONFIG, engine_manager=manager, stride=5, cache_dir=tmp_path,
    )

    # The evaluator must not crash or propagate the exception - it should
    # skip bad_game's failing position and still count good_game's position
    # normally (a clean TN for both detectors, same as the flat-scoreLead/
    # fully-resolved-ownership case in the test above).
    assert (result["weak_group"].tp, result["weak_group"].fp, result["weak_group"].fn) == (0, 0, 0)
    assert result["weak_group"].tn == 1
    assert (result["mistake"].tp, result["mistake"].fp, result["mistake"].fn) == (0, 0, 0)
    assert result["mistake"].tn == 1
    assert "bad.sgf" in capsys.readouterr().out


def test_evaluate_opening_loss_skips_a_failing_game_color_and_keeps_going(tmp_path, capsys):
    bad_game = CalibrationGame(
        moves=[["B", "E5"], ["W", "C3"], ["B", "G7"], ["W", "C7"]],
        board_size=9,
        rules="chinese",
        komi=7.5,
    )
    good_game = CalibrationGame(
        moves=[["B", "E5"], ["W", "C3"], ["B", "G7"], ["W", "C7"]],
        board_size=9,
        rules="chinese",
        komi=7.5,
    )
    # Fails on the very first engine call, i.e. bad_game's color="B" pass at
    # turn 0; bad_game's color="W" pass and all of good_game's calls succeed.
    manager = _FlakyEngineManager(fail_on_call=1)

    result = evaluate_opening_loss(
        [(Path("bad.sgf"), bad_game), (Path("good.sgf"), good_game)],
        fast_visits=50, deep_visits=500,
        config=DEFAULT_CONFIG, engine_manager=manager, cache_dir=tmp_path,
    )

    # The evaluator must not crash or propagate the exception - the
    # remaining (sgf_path, color) combinations must still be counted.
    assert (result.tp, result.fp, result.fn, result.tn) != (0, 0, 0, 0)
    assert "bad.sgf" in capsys.readouterr().out


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
