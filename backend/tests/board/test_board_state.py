from baduk_backend.board.board_state import apply_moves
from baduk_backend.board.gtp_coords import gtp_to_xy


def test_gtp_to_xy_converts_coordinate_to_grid_indices():
    assert gtp_to_xy("C3", 9) == (2, 6)
    assert gtp_to_xy("D4", 9) == (3, 5)


def test_gtp_to_xy_maps_pass_to_none():
    assert gtp_to_xy("pass", 9) is None


def test_apply_moves_places_stones_at_expected_grid_positions():
    board = apply_moves([["B", "C3"], ["W", "D4"]], 9, 9)

    assert board[6][2] == "B"
    assert board[5][3] == "W"


def test_apply_moves_ignores_pass():
    board = apply_moves([["B", "pass"]], 9, 9)

    assert all(cell is None for row in board for cell in row)


def test_apply_moves_captures_surrounded_stone():
    moves = [
        ["W", "A1"],
        ["B", "A2"],
        ["B", "B1"],
    ]

    board = apply_moves(moves, 9, 9)

    assert board[8][0] is None  # белый камень A1 взят
    assert board[7][0] == "B"  # A2
    assert board[8][1] == "B"  # B1
