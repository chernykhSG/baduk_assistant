from baduk_backend.auth import AUTH_TOKEN


def _payload(color="B", moves=None, opening_sequence=None):
    moves = (
        moves
        if moves is not None
        else [
            ["B", "E5"],
            ["W", "C3"],
            ["B", "G7"],
            ["W", "C7"],
            ["B", "E3"],
            ["W", "G3"],
            ["B", "C5"],
            ["W", "E7"],
            ["B", "G5"],
        ]
    )
    if opening_sequence is None:
        # 9 alternating moves on a 9x9 board -> window_end = min(9, 9) = 9.
        # scoreLead drifts down by 1 on each Black move (turns 1,3,5,7,9) and
        # stays flat on each White move (turns 2,4,6,8) - Black's cumulative
        # loss is 5.0 (clears THRESHOLD_OPENING_LOSS=3.0), White's is 0.0.
        score_leads = [10.0, 9.0, 9.0, 8.0, 8.0, 7.0, 7.0, 6.0, 6.0, 5.0]
        opening_sequence = [
            {"turnNumber": t, "scoreLead": score_leads[t], "visits": 1000} for t in range(10)
        ]
    return {
        "moves": moves,
        "boardXSize": 9,
        "boardYSize": 9,
        "color": color,
        "openingSequence": opening_sequence,
        "analysisAtEnd": {
            "id": "x",
            "turnNumber": 9,
            "moveInfos": [],
            "rootInfo": {"winrate": 0.5, "scoreLead": 5.0, "visits": 1000},
            "ownership": None,
        },
    }


def test_explain_opening_returns_finding_and_verified_explanation(explain_client):
    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"]["type"] == "opening_loss"
    assert body["finding"]["color"] == "B"
    assert body["verified"] is True
    assert body["explanation"]["summary"] == "Тестовое объяснение"


def test_explain_opening_returns_message_when_below_threshold(explain_client):
    # White's own moves never change scoreLead in the default fixture
    # sequence, so requesting color="W" finds nothing.
    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload(color="W")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["finding"] is None
    assert "не найдено" in body["message"]


def test_explain_opening_without_token_returns_401(explain_client):
    response = explain_client.post("/api/explain/opening", json=_payload())
    assert response.status_code == 401


def test_explain_opening_returns_422_when_sequence_length_mismatches_window(explain_client):
    payload = _payload()
    payload["openingSequence"] = payload["openingSequence"][:-1]  # drop turn 9

    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=payload
    )

    assert response.status_code == 422


def test_explain_opening_returns_422_when_sequence_turn_numbers_are_out_of_order(explain_client):
    payload = _payload()
    payload["openingSequence"][0], payload["openingSequence"][1] = (
        payload["openingSequence"][1],
        payload["openingSequence"][0],
    )

    response = explain_client.post(
        "/api/explain/opening", headers={"X-Auth-Token": AUTH_TOKEN}, json=payload
    )

    assert response.status_code == 422
