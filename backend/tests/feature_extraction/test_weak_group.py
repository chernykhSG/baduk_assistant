import pytest

from baduk_backend.api.schemas import AnalyzeResponse, MoveInfo, RootInfo
from baduk_backend.feature_extraction.weak_group import detect_weak_group


def _empty_board(size: int) -> list[list[str | None]]:
    return [[None] * size for _ in range(size)]


def test_detect_weak_group_computes_expected_score_and_confidence():
    board = _empty_board(9)
    board[4][4] = "B"  # одиночный камень E5, 4 дыхания

    move_infos = [
        MoveInfo(move=m, winrate=0.5, scoreLead=0.0, visits=100, prior=0.1, pv=[m])
        for m in ["D5", "F5", "E6", "E4", "C5"]
    ]
    analysis = AnalyzeResponse(
        id="test",
        moveInfos=move_infos,
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[0.0] * 81,
    )

    finding = detect_weak_group(board, 9, 9, analysis, turn_number=12)

    assert finding is not None
    assert finding.type == "weak_group"
    assert finding.turn_number == 12
    assert finding.stones == [(4, 4)]
    assert finding.own_certainty == pytest.approx(0.0)
    assert finding.boundary_certainty == pytest.approx(0.0)
    assert finding.liberties == 4
    assert finding.weak_score == pytest.approx(0.85)
    assert finding.severity == "high"
    assert finding.confidence == pytest.approx(0.5)


def test_detect_weak_group_returns_none_when_position_is_resolved():
    board = _empty_board(9)
    board[4][4] = "B"

    analysis = AnalyzeResponse(
        id="test",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[1.0] * 81,
    )

    assert detect_weak_group(board, 9, 9, analysis, turn_number=1) is None


def test_detect_weak_group_returns_none_without_ownership_data():
    board = _empty_board(9)
    board[4][4] = "B"

    analysis = AnalyzeResponse(
        id="test", moveInfos=[], rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=1), ownership=None
    )

    assert detect_weak_group(board, 9, 9, analysis, turn_number=1) is None
