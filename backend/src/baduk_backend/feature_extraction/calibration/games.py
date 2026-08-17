import random
from pathlib import Path

from pydantic import BaseModel
from sgfmill import sgf, sgf_moves
from sgfmill.common import format_vertex

_KNOWN_RULES = {"chinese", "japanese", "korean", "aga", "nz", "tromp-taylor"}
_DEFAULT_RULES = "chinese"
_DEFAULT_KOMI = 7.5


class CalibrationGame(BaseModel):
    moves: list[list[str]]
    board_size: int
    rules: str
    komi: float


def _map_rules(raw: str | None) -> str:
    if raw is None:
        return _DEFAULT_RULES
    normalized = raw.lower().strip()
    return normalized if normalized in _KNOWN_RULES else _DEFAULT_RULES


def load_game(sgf_path: Path) -> CalibrationGame:
    game = sgf.Sgf_game.from_bytes(sgf_path.read_bytes())
    board_size = game.get_size()
    setup_board, plays = sgf_moves.get_setup_and_moves(game)
    if not setup_board.is_empty():
        raise ValueError(
            f"{sgf_path}: SGF has handicap/setup stones (AB/AW) before the first move - "
            "not supported by the calibration harness"
        )

    # format_vertex(None) already returns "pass" - no separate branch needed.
    moves = [[colour.upper(), format_vertex(move)] for colour, move in plays]

    root = game.get_root()
    raw_rules = root.get("RU") if root.has_property("RU") else None
    komi = game.get_komi() if root.has_property("KM") else _DEFAULT_KOMI

    return CalibrationGame(moves=moves, board_size=board_size, rules=_map_rules(raw_rules), komi=komi)


def sample_games(corpus_dir: Path, n: int, seed: int = 0) -> list[Path]:
    all_games = sorted(corpus_dir.rglob("*.sgf"))
    if not all_games:
        raise RuntimeError(f"no .sgf files found under {corpus_dir}")
    rng = random.Random(seed)
    return rng.sample(all_games, min(n, len(all_games)))


def sample_positions(num_moves: int, stride: int = 5) -> list[int]:
    return list(range(stride, num_moves + 1, stride))
