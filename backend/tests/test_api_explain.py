from baduk_backend.auth import AUTH_TOKEN


def _payload(moves=None, ownership=None, move_infos=None):
    return {
        "moves": moves if moves is not None else [["B", "E5"]],
        "boardXSize": 9,
        "boardYSize": 9,
        "analysis": {
            "id": "x",
            "turnNumber": 1,
            "moveInfos": move_infos if move_infos is not None else [],
            "rootInfo": {"winrate": 0.5, "scoreLead": 0.0, "visits": 250},
            "ownership": ownership if ownership is not None else [0.0] * 81,
        },
    }


def test_explain_returns_finding_and_verified_explanation(explain_client):
    response = explain_client.post(
        "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "weak_group"
    assert body["verified"] is True
    assert body["explanation"]["summary"] == "Тестовое объяснение"


def test_explain_returns_message_when_nothing_found(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(ownership=[1.0] * 81),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"] is None
    assert "Ничего заметного" in body["message"]


def test_explain_without_token_returns_401(explain_client):
    response = explain_client.post("/api/explain", json=_payload())
    assert response.status_code == 401


def test_explain_returns_422_when_ownership_length_mismatches_board_size(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(ownership=[0.0] * 80),
    )
    assert response.status_code == 422


def test_explain_returns_503_when_llm_provider_fails():
    from fastapi.testclient import TestClient

    from baduk_backend.main import app

    class _FailingProvider:
        def complete(self, finding, analysis, board_size, corrections=None):
            raise RuntimeError("claude api unavailable")

    app.state.llm_provider = _FailingProvider()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
        )
        assert response.status_code == 503
    finally:
        del app.state.llm_provider
