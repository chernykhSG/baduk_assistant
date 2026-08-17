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
