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
