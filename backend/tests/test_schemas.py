import pytest
from pydantic import ValidationError

from baduk_backend.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DoneMessage,
    ErrorMessage,
    MoveInfo,
    ProgressMessage,
    RootInfo,
    StreamAnalyzeRequest,
)


def _base_fields() -> dict:
    return {
        "moves": [],
        "rules": "chinese",
        "komi": 7.5,
        "boardXSize": 19,
        "boardYSize": 19,
        "maxVisits": 50,
        "includeOwnership": True,
    }


def test_analyze_request_accepts_single_analyze_turn():
    request = AnalyzeRequest(analyzeTurns=[0], **_base_fields())
    assert request.analyzeTurns == [0]


def test_analyze_request_rejects_multiple_analyze_turns():
    with pytest.raises(ValidationError):
        AnalyzeRequest(analyzeTurns=[0, 1], **_base_fields())


def test_analyze_request_rejects_empty_analyze_turns():
    with pytest.raises(ValidationError):
        AnalyzeRequest(analyzeTurns=[], **_base_fields())


def test_stream_request_accepts_multiple_turn_numbers():
    request = StreamAnalyzeRequest(turnNumbers=[0, 1, 2], **_base_fields())
    assert request.turnNumbers == [0, 1, 2]


def test_stream_request_rejects_empty_turn_numbers():
    with pytest.raises(ValidationError):
        StreamAnalyzeRequest(turnNumbers=[], **_base_fields())


def test_analyze_response_parses_katago_style_payload():
    response = AnalyzeResponse.model_validate(
        {
            "id": "test-1",
            "turnNumber": 0,
            "moveInfos": [
                {
                    "move": "Q4",
                    "winrate": 0.55,
                    "scoreLead": 1.2,
                    "visits": 50,
                    "prior": 0.3,
                    "pv": ["Q4", "D4"],
                }
            ],
            "rootInfo": {"winrate": 0.55, "scoreLead": 1.2, "visits": 50},
            "ownership": [0.1, 0.2],
        }
    )
    assert response.moveInfos[0].move == "Q4"
    assert isinstance(response.moveInfos[0], MoveInfo)
    assert isinstance(response.rootInfo, RootInfo)


def test_progress_message_serializes_nested_result():
    message = ProgressMessage(
        turnNumber=0,
        total=3,
        result=AnalyzeResponse(
            id="test-1",
            moveInfos=[],
            rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=1),
        ),
    )
    dumped = message.model_dump()
    assert dumped["type"] == "progress"
    assert dumped["result"]["id"] == "test-1"


def test_done_message_has_fixed_type():
    assert DoneMessage().model_dump() == {"type": "done"}


def test_error_message_carries_detail():
    assert ErrorMessage(detail="boom").model_dump() == {"type": "error", "detail": "boom"}
