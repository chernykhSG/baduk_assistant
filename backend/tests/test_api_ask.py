from fastapi.testclient import TestClient
import pytest

from baduk_backend.auth import AUTH_TOKEN
from baduk_backend.llm.schemas import QuestionAnswer, QuestionClaim
from baduk_backend.main import app


class _StubAskProvider:
    def answer_question(self, question, analysis, board_size, corrections=None):
        return QuestionAnswer(
            answer="Тестовый ответ",
            claims=[QuestionClaim(cited_field="winrate", cited_number=analysis.rootInfo.winrate)],
        )


class _NonAskProvider:
    """A provider that only implements the Finding-based flow, like ClaudeProvider/GeminiProvider -
    used to prove /api/ask gates on capability, not on being told the provider name."""

    def complete(self, finding, analysis, board_size, corrections=None):
        raise AssertionError("should never be called by /api/ask")


class _FailingAskProvider:
    def answer_question(self, question, analysis, board_size, corrections=None):
        raise RuntimeError("model process crashed")


@pytest.fixture
def ask_client():
    app.state.llm_provider = _StubAskProvider()
    try:
        yield TestClient(app)
    finally:
        del app.state.llm_provider


def _payload(question="почему белые слабы?"):
    return {
        "moves": [["B", "E5"]],
        "boardXSize": 9,
        "boardYSize": 9,
        "analysis": {
            "id": "x",
            "turnNumber": 1,
            "moveInfos": [],
            "rootInfo": {"winrate": 0.5, "scoreLead": 0.0, "visits": 250},
            "ownership": [0.0] * 81,
        },
        "question": question,
    }


def test_ask_returns_verified_answer(ask_client):
    response = ask_client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Тестовый ответ"
    assert body["verified"] is True


def test_ask_without_token_returns_401(ask_client):
    response = ask_client.post("/api/ask", json=_payload())
    assert response.status_code == 401


def test_ask_returns_422_on_empty_question(ask_client):
    response = ask_client.post(
        "/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload(question="")
    )
    assert response.status_code == 422


def test_ask_returns_422_on_too_long_question(ask_client):
    response = ask_client.post(
        "/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload(question="я" * 501)
    )
    assert response.status_code == 422


def test_ask_returns_422_when_ownership_length_mismatches_board_size(ask_client):
    payload = _payload()
    payload["analysis"]["ownership"] = [0.0] * 80
    response = ask_client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=payload)
    assert response.status_code == 422


def test_ask_returns_503_when_provider_cannot_answer_questions():
    app.state.llm_provider = _NonAskProvider()
    try:
        client = TestClient(app)
        response = client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload())
    finally:
        del app.state.llm_provider

    assert response.status_code == 503
    assert "llama" in response.json()["detail"]


def test_ask_returns_503_when_provider_raises():
    app.state.llm_provider = _FailingAskProvider()
    try:
        client = TestClient(app)
        response = client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload())
    finally:
        del app.state.llm_provider

    assert response.status_code == 503
    assert "model process crashed" in response.json()["detail"]
