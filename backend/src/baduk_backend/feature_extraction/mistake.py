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
    delta = mover_favorability(analysis_before.rootInfo.scoreLead, mover) - mover_favorability(
        analysis_after.rootInfo.scoreLead, mover
    )
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
