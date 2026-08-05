from baduk_backend.board.groups import find_group_at, neighbors
from baduk_backend.board.gtp_coords import gtp_to_xy


def apply_moves(moves: list[list[str]], board_x_size: int, board_y_size: int) -> list[list[str | None]]:
    """Восстанавливает доску, повторяя `moves` (тот же формат, что уходит в
    KataGo через /api/analyze). Легальность ходов не перепроверяется - этот
    список уже был принят KataGo ранее в этой же партии; здесь только
    расстановка и взятие, чтобы downstream union-find видел реальные камни."""
    board: list[list[str | None]] = [[None] * board_x_size for _ in range(board_y_size)]
    for color, coord in moves:
        vertex = gtp_to_xy(coord, board_y_size)
        if vertex is None:
            continue
        x, y = vertex
        board[y][x] = color
        opponent = "W" if color == "B" else "B"
        for nx, ny in neighbors(x, y, board_x_size, board_y_size):
            if board[ny][nx] == opponent:
                group = find_group_at(board, nx, ny)
                if group is not None and group.liberties == 0:
                    for gx, gy in group.stones:
                        board[gy][gx] = None
    return board
