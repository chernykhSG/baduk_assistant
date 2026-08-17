import pytest

from baduk_backend.feature_extraction.config_loader import OpeningLossConfig
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


def test_detect_opening_loss_explicit_config_overrides_default_threshold():
    # Same input as test_detect_opening_loss_sums_only_the_requested_color_moves's
    # White case: White's own moves never lose points (total delta == 0.0),
    # below the default threshold_opening_loss (3.0), so detect_opening_loss()
    # returns None for White with the default config. A candidate config with
    # a much lower threshold_opening_loss must make the SAME input fire instead.
    moves = _moves(["B", "W", "B", "W", "B", "W", "B", "W", "B"])
    score_leads = [10.0, 9.0, 9.0, 7.0, 7.0, 6.0, 6.0, 3.0, 3.0, 3.0]
    sequence = [(turn, score_leads[turn], 1000) for turn in range(10)]

    low_threshold_config = OpeningLossConfig(threshold_opening_loss=-1.0, severity_medium=5.0, severity_high=15.0)

    assert detect_opening_loss(moves, sequence, "W", 9, 9) is None
    finding = detect_opening_loss(moves, sequence, "W", 9, 9, config=low_threshold_config)

    assert finding is not None
    assert finding.delta_score == pytest.approx(0.0)


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
