import pytest
from starlette.websockets import WebSocketDisconnect

from baduk_backend.auth import AUTH_TOKEN


def _stream_payload(turn_numbers):
    return {
        "moves": [],
        "rules": "chinese",
        "komi": 7.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "turnNumbers": turn_numbers,
        "maxVisits": 50,
        "includeOwnership": True,
    }


def test_stream_rejects_missing_token(fake_engine_client):
    with fake_engine_client.websocket_connect("/api/analyze/stream") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_stream_rejects_wrong_token(fake_engine_client):
    with fake_engine_client.websocket_connect("/api/analyze/stream?token=wrong") as ws:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
    assert exc_info.value.code == 1008


def test_stream_sends_progress_per_turn_then_done(fake_engine_client):
    with fake_engine_client.websocket_connect(f"/api/analyze/stream?token={AUTH_TOKEN}") as ws:
        ws.send_json(_stream_payload([0, 1]))

        first = ws.receive_json()
        assert first["type"] == "progress"
        assert first["turnNumber"] == 0
        assert first["total"] == 2
        assert first["result"]["moveInfos"][0]["move"] == "Q4"

        second = ws.receive_json()
        assert second["type"] == "progress"
        assert second["turnNumber"] == 1
        assert second["total"] == 2

        done = ws.receive_json()
        assert done == {"type": "done"}


def test_stream_sends_error_for_invalid_message(fake_engine_client):
    with fake_engine_client.websocket_connect(f"/api/analyze/stream?token={AUTH_TOKEN}") as ws:
        ws.send_json({"not": "a valid stream request"})
        message = ws.receive_json()
        assert message == {"type": "error", "detail": "invalid request"}


def test_stream_sends_error_when_katago_crashes(fake_engine_client_crash):
    with fake_engine_client_crash.websocket_connect(f"/api/analyze/stream?token={AUTH_TOKEN}") as ws:
        ws.send_json(_stream_payload([0]))
        message = ws.receive_json()
        assert message["type"] == "error"
