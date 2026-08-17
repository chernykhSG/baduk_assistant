from pathlib import Path

from baduk_backend.feature_extraction.calibration.cache import fetch_analysis
from baduk_backend.feature_extraction.calibration.games import CalibrationGame


class _FakeEngineManager:
    def __init__(self, response: dict):
        self._response = response
        self.calls = 0

    def analyze(self, request: dict, timeout: float = 30.0) -> dict:
        self.calls += 1
        return {**self._response, "id": request["id"]}


def _fake_response() -> dict:
    return {
        "id": "x",
        "moveInfos": [],
        "rootInfo": {"winrate": 0.5, "scoreLead": 0.0, "visits": 100},
        "ownership": [0.0] * 81,
    }


def _game() -> CalibrationGame:
    return CalibrationGame(moves=[["B", "E5"]], board_size=9, rules="chinese", komi=7.5)


def test_fetch_analysis_calls_the_engine_on_a_fresh_position(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    response = fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)

    assert manager.calls == 1
    assert response.rootInfo.visits == 100


def test_fetch_analysis_reuses_the_cache_on_a_repeat_request(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)
    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)

    assert manager.calls == 1


def test_fetch_analysis_treats_different_visit_budgets_as_different_cache_entries(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)
    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 500, cache_dir=tmp_path)

    assert manager.calls == 2


def test_fetch_analysis_treats_different_turn_numbers_as_different_cache_entries(tmp_path):
    manager = _FakeEngineManager(_fake_response())

    fetch_analysis(manager, Path("game.sgf"), _game(), 1, 50, cache_dir=tmp_path)
    fetch_analysis(manager, Path("game.sgf"), _game(), 2, 50, cache_dir=tmp_path)

    assert manager.calls == 2


def test_fetch_analysis_sends_the_full_move_list_and_requested_turn(tmp_path):
    manager = _FakeEngineManager(_fake_response())
    game = CalibrationGame(moves=[["B", "E5"], ["W", "C3"]], board_size=9, rules="chinese", komi=7.5)
    captured: dict = {}

    class _CapturingManager(_FakeEngineManager):
        def analyze(self, request: dict, timeout: float = 30.0) -> dict:
            captured.update(request)
            return super().analyze(request, timeout)

    fetch_analysis(_CapturingManager(_fake_response()), Path("game.sgf"), game, 1, 50, cache_dir=tmp_path)

    assert captured["moves"] == [["B", "E5"], ["W", "C3"]]
    assert captured["analyzeTurns"] == [1]
    assert captured["maxVisits"] == 50
    assert captured["includeOwnership"] is True
    assert captured["boardXSize"] == 9
    assert captured["rules"] == "chinese"
