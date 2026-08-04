import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from baduk_backend.auth import AUTH_TOKEN
from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command
from baduk_backend.main import app

pytestmark = pytest.mark.integration


def test_real_katago_analyze_endpoint_returns_winrate_and_ownership(local_katago_config, tmp_path):
    profile = KataGoProfile(
        model_id="integration-test",
        display_name="Integration test profile",
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
    app.state.engine_manager = manager
    app.state.engine_lock = asyncio.Lock()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/analyze",
            headers={"X-Auth-Token": AUTH_TOKEN},
            json={
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
        del app.state.engine_manager
        del app.state.engine_lock

    assert response.status_code == 200
    body = response.json()
    assert len(body["moveInfos"]) > 0
    assert "winrate" in body["moveInfos"][0]
    assert "pv" in body["moveInfos"][0]
    assert body["ownership"] is not None
    assert len(body["ownership"]) == profile.board_size * profile.board_size
