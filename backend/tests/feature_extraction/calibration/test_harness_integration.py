import os

import pytest

pytest.importorskip("sgfmill")

pytestmark = pytest.mark.integration


def test_harness_runs_end_to_end_on_a_small_real_sample(capsys, tmp_path):
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    games_path = os.environ.get("BADUK_CALIBRATION_GAMES_PATH")
    if not katago_binary or not katago_model or not games_path:
        pytest.skip(
            "BADUK_KATAGO_BINARY, BADUK_KATAGO_MODEL, and BADUK_CALIBRATION_GAMES_PATH "
            "must all be set to run this test"
        )

    from pathlib import Path

    from baduk_backend.feature_extraction.calibration.harness import run_harness

    run_harness(
        games_dir=Path(games_path),
        config_paths=[],
        games_sample=1,
        move_stride=10,
        seed=0,
        fast_visits=5,
        deep_visits=20,
    )

    output = capsys.readouterr().out
    assert "weak_group" in output
    assert "mistake" in output
    assert "opening_loss" in output
