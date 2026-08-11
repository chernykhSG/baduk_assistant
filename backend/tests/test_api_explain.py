from baduk_backend.auth import AUTH_TOKEN


def _payload(moves=None, ownership=None, move_infos=None, analysis_after=None, next_move=None):
    payload = {
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
    if analysis_after is not None:
        payload["analysisAfter"] = analysis_after
    if next_move is not None:
        payload["nextMove"] = next_move
    return payload


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


def test_explain_returns_mistake_finding_when_only_mistake_triggers(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(
            ownership=[1.0] * 81,  # resolved position - weak_group does not trigger
            analysis_after={
                "id": "y",
                "turnNumber": 2,
                "moveInfos": [],
                # scoreLead is always Black's-perspective; mover is White (see
                # next_move below), so going from 0.0 to +3.0 here is a 3-point
                # favorability drop for White - i.e. a mistake by White. See
                # tests/feature_extraction/test_mistake.py for the sign convention.
                "rootInfo": {"winrate": 0.2, "scoreLead": 3.0, "visits": 250},
                "ownership": None,
            },
            next_move=["W", "F5"],
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "mistake"
    assert body["finding"]["delta_score"] == 3.0
    assert body["verified"] is True


def test_explain_prefers_mistake_when_both_detectors_trigger(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(
            # default ownership/moves from _payload() already trigger weak_group
            # (see test_explain_returns_finding_and_verified_explanation)
            analysis_after={
                "id": "y",
                "turnNumber": 2,
                "moveInfos": [],
                # see comment in test_explain_returns_mistake_finding_when_only_mistake_triggers
                "rootInfo": {"winrate": 0.2, "scoreLead": 3.0, "visits": 250},
                "ownership": None,
            },
            next_move=["W", "F5"],
        ),
    )
    assert response.status_code == 200
    assert response.json()["finding"]["type"] == "mistake"


def test_explain_returns_422_when_analysis_after_given_without_next_move(explain_client):
    response = explain_client.post(
        "/api/explain",
        headers={"X-Auth-Token": AUTH_TOKEN},
        json=_payload(
            analysis_after={
                "id": "y",
                "turnNumber": 2,
                "moveInfos": [],
                "rootInfo": {"winrate": 0.2, "scoreLead": -3.0, "visits": 250},
                "ownership": None,
            }
        ),
    )
    assert response.status_code == 422


def test_explain_weak_group_path_unaffected_without_analysis_after(explain_client):
    # Regression: the exact payload/assertions from
    # test_explain_returns_finding_and_verified_explanation, unchanged.
    response = explain_client.post(
        "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "weak_group"
    assert body["verified"] is True


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
