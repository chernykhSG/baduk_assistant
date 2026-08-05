import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from baduk_backend.engine_manager import EngineManager
from baduk_backend.llm.schemas import Claim, Explanation
from baduk_backend.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def local_katago_config():
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    if not katago_binary or not katago_model:
        pytest.skip(
            "BADUK_KATAGO_BINARY and BADUK_KATAGO_MODEL env vars not set; "
            "see tests/local_config.json.example"
        )
    return {"katago_binary": katago_binary, "katago_model": katago_model}


def _wire_app_state(command: list[str]):
    manager = EngineManager(command)
    app.state.engine_manager = manager
    app.state.engine_lock = asyncio.Lock()
    return manager


@pytest.fixture
def fake_engine_client():
    manager = _wire_app_state([sys.executable, str(FIXTURES_DIR / "fake_katago.py")])
    try:
        yield TestClient(app)
    finally:
        manager.stop()
        del app.state.engine_manager
        del app.state.engine_lock


@pytest.fixture
def fake_engine_client_crash():
    manager = _wire_app_state([sys.executable, str(FIXTURES_DIR / "fake_katago_crash.py")])
    try:
        yield TestClient(app)
    finally:
        manager.stop()
        del app.state.engine_manager
        del app.state.engine_lock


@pytest.fixture
def slow_fake_engine_app():
    manager = _wire_app_state([sys.executable, str(FIXTURES_DIR / "slow_fake_katago.py")])
    try:
        yield app
    finally:
        manager.stop()
        del app.state.engine_manager
        del app.state.engine_lock


class _StubLLMProvider:
    def complete(self, finding, analysis, board_size, corrections=None):
        return Explanation(
            summary="Тестовое объяснение",
            claims=[
                Claim(
                    text="...",
                    finding_id=finding.finding_id,
                    cited_field="weak_score",
                    cited_number=finding.weak_score,
                )
            ],
        )


@pytest.fixture
def explain_client():
    app.state.llm_provider = _StubLLMProvider()
    try:
        yield TestClient(app)
    finally:
        del app.state.llm_provider
