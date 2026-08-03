import json
import socket

from fastapi.testclient import TestClient

from baduk_backend.main import AUTH_TOKEN, _find_free_port, app, build_startup_message


def test_health_with_valid_token_returns_ok():
    client = TestClient(app)
    response = client.get("/health", headers={"X-Auth-Token": AUTH_TOKEN})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_with_invalid_token_returns_401():
    client = TestClient(app)
    response = client.get("/health", headers={"X-Auth-Token": "wrong-token"})
    assert response.status_code == 401


def test_health_without_token_returns_422():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 422


def test_build_startup_message_contains_port_and_token():
    message = build_startup_message(port=12345, token="abc123")
    assert json.loads(message) == {"port": 12345, "token": "abc123"}


def test_find_free_port_returns_bindable_port():
    port = _find_free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
