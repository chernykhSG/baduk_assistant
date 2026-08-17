import argparse
import os
import tempfile
from pathlib import Path

from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command
from baduk_backend.feature_extraction.calibration.games import CalibrationGame, load_game, sample_games
from baduk_backend.feature_extraction.calibration.metrics import ConfusionCounts
from baduk_backend.feature_extraction.calibration.self_consistency import (
    evaluate_opening_loss,
    evaluate_weak_group_and_mistake,
)
from baduk_backend.feature_extraction.config_loader import DEFAULT_CONFIG_PATH, load_detector_config


def _load_games_skipping_errors(sgf_paths: list[Path]) -> list[tuple[Path, CalibrationGame]]:
    games: list[tuple[Path, CalibrationGame]] = []
    for path in sgf_paths:
        try:
            games.append((path, load_game(path)))
        except Exception as exc:
            print(f"WARNING: skipping unparseable SGF file {path}: {exc}")
    return games


def _build_engine_manager() -> tuple[EngineManager, str]:
    katago_binary = os.environ["BADUK_KATAGO_BINARY"]
    katago_model = os.environ["BADUK_KATAGO_MODEL"]
    profile = KataGoProfile(
        model_id="calibration-harness",
        display_name="Calibration harness profile",
        rules="chinese",
        board_size=19,
        komi=7.5,
        max_visits=500,
        num_analysis_threads=4,
    )
    home_data_dir = str(Path(katago_binary).parent)
    config_text = render_analysis_config(profile, home_data_dir_override=home_data_dir)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as config_file:
        config_file.write(config_text)
        config_path = config_file.name
    command = build_katago_command(katago_binary=katago_binary, config_path=config_path, model_path=katago_model)
    return EngineManager(command), config_path


def _format_number(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _format_row(name: str, counts: ConfusionCounts) -> str:
    return (
        f"{name:<15} TP={counts.tp:<4} FP={counts.fp:<4} FN={counts.fn:<4} TN={counts.tn:<4} "
        f"precision={_format_number(counts.precision())} recall={_format_number(counts.recall())} "
        f"F1={_format_number(counts.f1())}"
    )


def run_harness(
    games_dir: Path,
    config_paths: list[Path],
    games_sample: int,
    move_stride: int,
    seed: int,
    fast_visits: int,
    deep_visits: int,
) -> None:
    # Sample/load the corpus before starting KataGo, so a missing/empty
    # games_dir fails fast with a clear error instead of spinning up a
    # KataGo process for nothing.
    sgf_paths = sample_games(games_dir, n=games_sample, seed=seed)
    games = _load_games_skipping_errors(sgf_paths)
    print(f"Sampled {len(games)} games from {games_dir}")

    engine_manager, temp_config_path = _build_engine_manager()
    try:
        for config_path in config_paths or [DEFAULT_CONFIG_PATH]:
            config = load_detector_config(config_path)
            print(f"\n=== {config_path} ===")

            wg_and_mistake = evaluate_weak_group_and_mistake(
                games, fast_visits, deep_visits, config, engine_manager, stride=move_stride,
            )
            opening_loss_counts = evaluate_opening_loss(games, fast_visits, deep_visits, config, engine_manager)

            print(_format_row("weak_group", wg_and_mistake["weak_group"]))
            print(_format_row("mistake", wg_and_mistake["mistake"]))
            print(_format_row("opening_loss", opening_loss_counts))
    finally:
        engine_manager.stop()
        try:
            os.remove(temp_config_path)
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibration/backtesting harness for the feature-extraction detectors"
    )
    parser.add_argument("--games-sample", type=int, default=20)
    parser.add_argument("--move-stride", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--fast-visits", type=int, default=50)
    parser.add_argument("--deep-visits", type=int, default=500)
    parser.add_argument(
        "--config", action="append", type=Path, default=None,
        help="candidate detector_config.v{N}.json to evaluate (repeatable); defaults to the bundled v1 config",
    )
    args = parser.parse_args()

    raw_games_path = os.environ.get("BADUK_CALIBRATION_GAMES_PATH")
    if not raw_games_path:
        raise RuntimeError("BADUK_CALIBRATION_GAMES_PATH env var must be set to run the calibration harness")

    run_harness(
        Path(raw_games_path),
        args.config or [],
        args.games_sample,
        args.move_stride,
        args.seed,
        args.fast_visits,
        args.deep_visits,
    )


if __name__ == "__main__":
    main()
