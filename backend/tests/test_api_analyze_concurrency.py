import asyncio
import time

import httpx
import pytest

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


@pytest.mark.anyio
async def test_concurrent_requests_are_serialized_by_the_engine_lock(slow_fake_engine_app):
    transport = httpx.ASGITransport(app=slow_fake_engine_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.monotonic()
        responses = await asyncio.gather(
            client.post("/api/analyze", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()),
            client.post("/api/analyze", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()),
            client.post("/api/analyze", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()),
        )
        elapsed = time.monotonic() - start

    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert body["moveInfos"][0]["move"] == "Q4"

    # The fake engine sleeps 0.3s per request; if the lock truly serializes
    # access to the (single-threaded) KataGo subprocess, 3 requests take
    # close to 3 * 0.3s = 0.9s. Without the lock they'd race through in
    # close to 0.3s. Use a generous floor to avoid flakiness while still
    # clearly distinguishing "serialized" from "parallel".
    assert elapsed > 0.7
