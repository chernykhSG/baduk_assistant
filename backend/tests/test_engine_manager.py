import sys
import time
from pathlib import Path

import pytest

from baduk_backend.engine_manager import EngineManager, KataGoCrashError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def fake_katago_command() -> list[str]:
    return [sys.executable, str(FIXTURES_DIR / "fake_katago.py")]


def noisy_stderr_katago_command() -> list[str]:
    return [sys.executable, str(FIXTURES_DIR / "noisy_stderr_katago.py")]


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


def test_analyze_does_not_deadlock_on_heavy_stderr_output():
    # Regression test: if stderr isn't drained continuously, a process that
    # logs heavily at startup (like real KataGo) fills the OS pipe buffer,
    # blocks on its own stderr write, and analyze() hangs until `timeout`
    # elapses instead of returning promptly.
    manager = EngineManager(noisy_stderr_katago_command())
    try:
        start = time.time()
        response = manager.analyze({"id": "test-3"}, timeout=10.0)
        elapsed = time.time() - start
        assert response["id"] == "test-3"
        assert elapsed < 5.0, f"analyze() took {elapsed:.2f}s, suggests stderr pipe deadlock"

        # Give the stderr reader thread a moment to finish draining, then
        # confirm the captured output is actually observable.
        deadline = time.time() + 2.0
        while "handling request test-3" not in manager.stderr_output() and time.time() < deadline:
            time.sleep(0.05)
        stderr_text = manager.stderr_output()
        assert "startup log line 2999" in stderr_text
        assert "handling request test-3" in stderr_text
    finally:
        manager.stop()


def fake_katago_crash_command() -> list[str]:
    return [sys.executable, str(FIXTURES_DIR / "fake_katago_crash.py")]


def test_analyze_raises_crash_error_when_process_exits_immediately():
    manager = EngineManager(fake_katago_crash_command())
    with pytest.raises(KataGoCrashError):
        manager.analyze({"id": "test-3", "moves": []}, timeout=2.0)
    assert not manager.is_running()


def test_manager_recovers_after_crash_with_working_command():
    manager = EngineManager(fake_katago_crash_command())
    with pytest.raises(KataGoCrashError):
        manager.analyze({"id": "test-4", "moves": []}, timeout=2.0)

    manager.command = fake_katago_command()
    try:
        response = manager.analyze({"id": "test-5", "moves": []})
        assert response["id"] == "test-5"
    finally:
        manager.stop()
