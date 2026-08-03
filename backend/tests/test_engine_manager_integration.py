from pathlib import Path

import pytest

from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command

pytestmark = pytest.mark.integration


def test_real_katago_returns_winrate_ownership_and_pv(local_katago_config, tmp_path):
    profile = KataGoProfile(
        model_id="dev-local",
        display_name="Dev local profile",
        rules="chinese",
        board_size=19,
        komi=7.5,
        max_visits=50,
        num_analysis_threads=2,
    )
    katago_binary_dir = str(Path(local_katago_config["katago_binary"]).parent)
    config_path = tmp_path / "analysis_config.cfg"
    config_path.write_text(render_analysis_config(profile, home_data_dir_override=katago_binary_dir))

    command = build_katago_command(
        katago_binary=local_katago_config["katago_binary"],
        config_path=str(config_path),
        model_path=local_katago_config["katago_model"],
    )
    manager = EngineManager(command)
    try:
        response = manager.analyze(
            {
                "id": "smoke-test-1",
                "moves": [],
                "rules": profile.rules,
                "komi": profile.komi,
                "boardXSize": profile.board_size,
                "boardYSize": profile.board_size,
                "analyzeTurns": [0],
                "maxVisits": profile.max_visits,
                "includeOwnership": True,
            },
            timeout=60.0,
        )
    finally:
        manager.stop()

    assert response["id"] == "smoke-test-1"
    assert len(response["moveInfos"]) > 0
    first_move = response["moveInfos"][0]
    assert "winrate" in first_move
    assert "pv" in first_move
    assert "ownership" in response
    assert len(response["ownership"]) == profile.board_size * profile.board_size
