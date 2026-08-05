from baduk_backend.board.groups import Group, find_group_at, find_groups


def _empty_board(size: int) -> list[list[str | None]]:
    return [[None] * size for _ in range(size)]


def test_single_stone_has_four_liberties_in_open_board():
    board = _empty_board(5)
    board[2][2] = "B"

    groups = find_groups(board)

    assert groups == [Group(color="B", stones=[(2, 2)], liberties=4)]


def test_connected_stones_form_one_group_with_shared_liberties():
    board = _empty_board(5)
    board[2][2] = "B"
    board[2][3] = "B"

    groups = find_groups(board)

    assert len(groups) == 1
    group = groups[0]
    assert group.color == "B"
    assert set(group.stones) == {(2, 2), (3, 2)}
    assert group.liberties == 6


def test_diagonal_stones_are_separate_groups():
    board = _empty_board(5)
    board[2][2] = "B"
    board[3][3] = "B"

    groups = find_groups(board)

    assert len(groups) == 2


def test_find_group_at_returns_none_for_empty_point():
    board = _empty_board(5)
    assert find_group_at(board, 0, 0) is None


def test_find_group_at_reports_zero_liberties_when_fully_surrounded():
    board = _empty_board(5)
    board[0][0] = "B"
    board[0][1] = "W"  # (x=1, y=0)
    board[1][0] = "W"  # (x=0, y=1)

    group = find_group_at(board, 0, 0)

    assert group == Group(color="B", stones=[(0, 0)], liberties=0)
