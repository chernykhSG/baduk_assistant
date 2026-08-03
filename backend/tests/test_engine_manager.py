import sys
from pathlib import Path

from baduk_backend.engine_manager import EngineManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def fake_katago_command() -> list[str]:
    return [sys.executable, str(FIXTURES_DIR / "fake_katago.py")]


def test_analyze_sends_request_and_parses_response():
    manager = EngineManager(fake_katago_command())
    try:
        response = manager.analyze({"id": "test-1", "moves": []})
        assert response["id"] == "test-1"
        assert "moveInfos" in response
        assert "rootInfo" in response
        assert "ownership" in response
    finally:
        manager.stop()


def test_analyze_auto_starts_process_if_not_running():
    manager = EngineManager(fake_katago_command())
    assert not manager.is_running()
    try:
        response = manager.analyze({"id": "test-2", "moves": []})
        assert response["id"] == "test-2"
        assert manager.is_running()
    finally:
        manager.stop()
