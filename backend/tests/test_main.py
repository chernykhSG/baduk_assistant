import json
import socket

import pytest
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


def test_health_without_token_returns_401():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 401


def test_build_startup_message_contains_port_and_token():
    message = build_startup_message(port=12345, token="abc123")
    assert json.loads(message) == {"port": 12345, "token": "abc123"}


def test_find_free_port_returns_bindable_port():
    port = _find_free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_select_llm_provider_claude_requires_key(monkeypatch):
    monkeypatch.delenv("BADUK_CLAUDE_API_KEY", raising=False)

    from baduk_backend.main import _select_llm_provider

    with pytest.raises(RuntimeError, match="BADUK_CLAUDE_API_KEY"):
        _select_llm_provider("claude")


def test_select_llm_provider_claude_builds_claude_provider(monkeypatch):
    from baduk_backend.llm.providers.claude import ClaudeProvider
    from baduk_backend.main import _select_llm_provider

    monkeypatch.setenv("BADUK_CLAUDE_API_KEY", "test-key")
    provider = _select_llm_provider("claude")

    assert isinstance(provider, ClaudeProvider)


def test_select_llm_provider_gemini_requires_key(monkeypatch):
    monkeypatch.delenv("BADUK_GEMINI_API_KEY", raising=False)

    from baduk_backend.main import _select_llm_provider

    with pytest.raises(RuntimeError, match="BADUK_GEMINI_API_KEY"):
        _select_llm_provider("gemini")


def test_select_llm_provider_gemini_builds_gemini_provider(monkeypatch):
    from baduk_backend.llm.providers.gemini import GeminiProvider
    from baduk_backend.main import _select_llm_provider

    monkeypatch.setenv("BADUK_GEMINI_API_KEY", "test-key")
    provider = _select_llm_provider("gemini")

    assert isinstance(provider, GeminiProvider)


def test_select_llm_provider_rejects_unknown_value():
    from baduk_backend.main import _select_llm_provider

    with pytest.raises(RuntimeError, match="Unknown BADUK_LLM_PROVIDER"):
        _select_llm_provider("not-a-real-provider")
