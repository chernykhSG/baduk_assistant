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
