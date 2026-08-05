from dataclasses import dataclass


@dataclass(frozen=True)
class Group:
    color: str
    stones: list[tuple[int, int]]
    liberties: int


def find_groups(board: list[list[str | None]]) -> list[Group]:
    board_y_size = len(board)
    board_x_size = len(board[0]) if board_y_size > 0 else 0
    visited: set[tuple[int, int]] = set()
    groups: list[Group] = []

    for y in range(board_y_size):
        for x in range(board_x_size):
            color = board[y][x]
            if color is None or (x, y) in visited:
                continue
            stones, liberty_points = _flood_fill(board, x, y, color, board_x_size, board_y_size)
            visited.update(stones)
            groups.append(Group(color=color, stones=sorted(stones), liberties=len(liberty_points)))
    return groups


def find_group_at(board: list[list[str | None]], x: int, y: int) -> Group | None:
    board_y_size = len(board)
    board_x_size = len(board[0]) if board_y_size > 0 else 0
    color = board[y][x]
    if color is None:
        return None
    stones, liberty_points = _flood_fill(board, x, y, color, board_x_size, board_y_size)
    return Group(color=color, stones=sorted(stones), liberties=len(liberty_points))


def neighbors(x: int, y: int, board_x_size: int, board_y_size: int) -> list[tuple[int, int]]:
    candidates = [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
    return [(nx, ny) for nx, ny in candidates if 0 <= nx < board_x_size and 0 <= ny < board_y_size]


def _flood_fill(
    board: list[list[str | None]],
    x: int,
    y: int,
    color: str,
    board_x_size: int,
    board_y_size: int,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    stones: set[tuple[int, int]] = {(x, y)}
    liberty_points: set[tuple[int, int]] = set()
    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        for nx, ny in neighbors(cx, cy, board_x_size, board_y_size):
            neighbor = board[ny][nx]
            if neighbor is None:
                liberty_points.add((nx, ny))
            elif neighbor == color and (nx, ny) not in stones:
                stones.add((nx, ny))
                stack.append((nx, ny))
    return stones, liberty_points
