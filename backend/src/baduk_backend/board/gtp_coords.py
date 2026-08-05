GTP_COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def gtp_to_xy(coord: str, board_size: int) -> tuple[int, int] | None:
    if coord == "pass":
        return None
    col = GTP_COLUMNS.index(coord[0].upper())
    row = int(coord[1:])
    return (col, board_size - row)


def xy_to_gtp(x: int, y: int, board_size: int) -> str:
    return f"{GTP_COLUMNS[x]}{board_size - y}"
