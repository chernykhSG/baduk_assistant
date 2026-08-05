import uuid

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.board.groups import Group, find_groups
from baduk_backend.board.gtp_coords import gtp_to_xy
from baduk_backend.feature_extraction.config import (
    MAX_LIBERTIES_NORM,
    MIN_RELIABLE_VISITS,
    PV_FOCUS_DISTANCE_D,
    PV_FOCUS_TOP_K,
    THRESHOLD_WEAK,
    W1_OWN_CERTAINTY,
    W2_BOUNDARY_CERTAINTY,
    W3_PV_FOCUS,
    W4_LIBERTIES,
)
from baduk_backend.feature_extraction.schemas import Finding


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


def _pv_focus(group: Group, move_infos: list, board_y_size: int) -> float:
    top_moves = move_infos[:PV_FOCUS_TOP_K]
    if not top_moves:
        return 0.0
    hits = 0
    for move_info in top_moves:
        vertex = gtp_to_xy(move_info.move, board_y_size)
        if vertex is None:
            continue
        mx, my = vertex
        if any(abs(mx - sx) + abs(my - sy) <= PV_FOCUS_DISTANCE_D for sx, sy in group.stones):
            hits += 1
    return hits / len(top_moves)


def _weak_score(own_certainty: float, boundary_certainty: float, pv_focus: float, liberties: int) -> float:
    score = (
        W1_OWN_CERTAINTY * (1 - own_certainty)
        + W2_BOUNDARY_CERTAINTY * (1 - boundary_certainty)
        + W3_PV_FOCUS * pv_focus
        - W4_LIBERTIES * (liberties / MAX_LIBERTIES_NORM)
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
) -> Finding | None:
    if analysis.ownership is None:
        return None

    best: tuple[float, Group, float, float] | None = None
    for group in find_groups(board):
        own_cert = _own_certainty(group, analysis.ownership, board_x_size)
        boundary_cert = _boundary_certainty(group, analysis.ownership, board_x_size, board_y_size, board)
        pv_focus = _pv_focus(group, analysis.moveInfos, board_y_size)
        score = _weak_score(own_cert, boundary_cert, pv_focus, group.liberties)
        if score > THRESHOLD_WEAK and (best is None or score > best[0]):
            best = (score, group, own_cert, boundary_cert)

    if best is None:
        return None

    score, group, own_cert, boundary_cert = best
    confidence = min(analysis.rootInfo.visits / MIN_RELIABLE_VISITS, 1.0)
    return Finding(
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
