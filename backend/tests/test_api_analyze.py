from baduk_backend.auth import AUTH_TOKEN


def _payload(analyze_turns=None):
    return {
        "moves": [],
        "rules": "chinese",
        "komi": 7.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "analyzeTurns": analyze_turns if analyze_turns is not None else [0],
        "maxVisits": 50,
        "includeOwnership": True,
    }


def test_analyze_returns_move_infos_and_ownership(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["moveInfos"][0]["move"] == "Q4"
    assert body["rootInfo"]["winrate"] == 0.55
    assert len(body["ownership"]) == 361


def test_analyze_without_token_returns_401(fake_engine_client):
    response = fake_engine_client.post("/api/analyze", json=_payload())
    assert response.status_code == 401


def test_analyze_with_wrong_token_returns_401(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": "wrong-token"},
        json=_payload(),
    )
    assert response.status_code == 401


def test_analyze_rejects_multiple_analyze_turns(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(analyze_turns=[0, 1]),
    )
    assert response.status_code == 422


def test_analyze_rejects_empty_analyze_turns(fake_engine_client):
    response = fake_engine_client.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(analyze_turns=[]),
    )
    assert response.status_code == 422


def test_analyze_returns_503_when_katago_process_crashes(fake_engine_client_crash):
    response = fake_engine_client_crash.post(
        "/api/analyze",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(),
    )
    assert response.status_code == 503
