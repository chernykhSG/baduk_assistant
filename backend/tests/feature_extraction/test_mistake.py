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
