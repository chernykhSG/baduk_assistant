from pathlib import Path

from baduk_backend.board.board_state import apply_moves
from baduk_backend.feature_extraction.calibration.cache import DEFAULT_CACHE_DIR, fetch_analysis
from baduk_backend.feature_extraction.calibration.games import CalibrationGame, sample_positions
from baduk_backend.feature_extraction.calibration.metrics import ConfusionCounts
from baduk_backend.feature_extraction.config_loader import DetectorConfig
from baduk_backend.feature_extraction.mistake import detect_mistake
from baduk_backend.feature_extraction.opening_loss import detect_opening_loss
from baduk_backend.feature_extraction.schemas import WeakGroupFinding
from baduk_backend.feature_extraction.weak_group import detect_weak_group


def classify_finding(candidate, reference) -> str:
    """Classifies one sampled position's self-consistency outcome.
    `candidate` is the finding from the fast-budget pass, `reference` from
    the deep-budget pass - both computed with the SAME candidate detector
    config, so this measures the candidate config's robustness to KataGo's
    own visit-budget noise, not a different scoring methodology."""
    same = candidate is not None and reference is not None and _same_finding(candidate, reference)
    if same:
        return "tp"
    if candidate is not None:
        return "fp"
    if reference is not None:
        return "fn"
    return "tn"


def _same_finding(a, b) -> bool:
    if isinstance(a, WeakGroupFinding):
        return set(a.stones) == set(b.stones)
    return True  # mistake/opening_loss: presence alone is the signal


def _accumulate(counts: ConfusionCounts, label: str) -> None:
    if label == "tp":
        counts.tp += 1
    elif label == "fp":
        counts.fp += 1
    elif label == "fn":
        counts.fn += 1
    else:
        counts.tn += 1


def evaluate_weak_group_and_mistake(
    games: list[tuple[Path, CalibrationGame]],
    fast_visits: int,
    deep_visits: int,
    config: DetectorConfig,
    engine_manager,
    stride: int = 5,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> dict[str, ConfusionCounts]:
    weak_group_counts = ConfusionCounts()
    mistake_counts = ConfusionCounts()

    for sgf_path, game in games:
        for turn in sample_positions(len(game.moves), stride):
            try:
                fast_after = fetch_analysis(engine_manager, sgf_path, game, turn, fast_visits, cache_dir)
                deep_after = fetch_analysis(engine_manager, sgf_path, game, turn, deep_visits, cache_dir)
                board_after = apply_moves(game.moves[:turn], game.board_size, game.board_size)

                candidate_wg = detect_weak_group(
                    board_after, game.board_size, game.board_size, fast_after, turn,
                    config.weak_group, config.min_reliable_visits,
                )
                reference_wg = detect_weak_group(
                    board_after, game.board_size, game.board_size, deep_after, turn,
                    config.weak_group, config.min_reliable_visits,
                )
                weak_group_label = classify_finding(candidate_wg, reference_wg)

                fast_before = fetch_analysis(engine_manager, sgf_path, game, turn - 1, fast_visits, cache_dir)
                deep_before = fetch_analysis(engine_manager, sgf_path, game, turn - 1, deep_visits, cache_dir)
                board_before = apply_moves(game.moves[: turn - 1], game.board_size, game.board_size)
                next_move = (game.moves[turn - 1][0], game.moves[turn - 1][1])

                candidate_mistake = detect_mistake(
                    board_before, fast_before, fast_after, next_move, game.board_size, game.board_size, turn,
                    config.mistake, config.k_open, config.k_end, config.min_reliable_visits,
                )
                reference_mistake = detect_mistake(
                    board_before, deep_before, deep_after, next_move, game.board_size, game.board_size, turn,
                    config.mistake, config.k_open, config.k_end, config.min_reliable_visits,
                )
                mistake_label = classify_finding(candidate_mistake, reference_mistake)
            except Exception as exc:
                print(f"WARNING: skipping position sgf_path={sgf_path} turn={turn}: {exc}")
                continue

            _accumulate(weak_group_counts, weak_group_label)
            _accumulate(mistake_counts, mistake_label)

    return {"weak_group": weak_group_counts, "mistake": mistake_counts}


def evaluate_opening_loss(
    games: list[tuple[Path, CalibrationGame]],
    fast_visits: int,
    deep_visits: int,
    config: DetectorConfig,
    engine_manager,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> ConfusionCounts:
    counts = ConfusionCounts()

    for sgf_path, game in games:
        board_area = game.board_size * game.board_size
        window_end = min(int(board_area * config.k_open), len(game.moves))

        for color in ("B", "W"):
            try:
                fast_sequence = []
                deep_sequence = []
                for turn in range(window_end + 1):
                    fast = fetch_analysis(engine_manager, sgf_path, game, turn, fast_visits, cache_dir)
                    deep = fetch_analysis(engine_manager, sgf_path, game, turn, deep_visits, cache_dir)
                    fast_sequence.append((turn, fast.rootInfo.scoreLead, fast.rootInfo.visits))
                    deep_sequence.append((turn, deep.rootInfo.scoreLead, deep.rootInfo.visits))

                candidate = detect_opening_loss(
                    game.moves, fast_sequence, color, game.board_size, game.board_size,
                    config.opening_loss, config.k_open, config.min_reliable_visits,
                )
                reference = detect_opening_loss(
                    game.moves, deep_sequence, color, game.board_size, game.board_size,
                    config.opening_loss, config.k_open, config.min_reliable_visits,
                )
                label = classify_finding(candidate, reference)
            except Exception as exc:
                print(f"WARNING: skipping opening_loss evaluation for sgf_path={sgf_path} color={color}: {exc}")
                continue

            _accumulate(counts, label)

    return counts
