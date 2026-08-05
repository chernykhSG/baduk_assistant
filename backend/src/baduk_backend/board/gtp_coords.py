GTP_COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def gtp_to_xy(coord: str, board_size: int) -> tuple[int, int] | None:
    if coord == "pass":
        return None
    col = GTP_COLUMNS.index(coord[0].upper())
    row = int(coord[1:])
    return (col, board_size - row)
