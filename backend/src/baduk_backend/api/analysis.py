import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from baduk_backend.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DoneMessage,
    ErrorMessage,
    ProgressMessage,
    StreamAnalyzeRequest,
)
from baduk_backend.auth import require_valid_token, token_matches
from baduk_backend.engine_manager import EngineManager, KataGoCrashError

router = APIRouter()


def get_engine_manager(request: Request) -> EngineManager:
    return request.app.state.engine_manager


def get_engine_lock(request: Request) -> asyncio.Lock:
    return request.app.state.engine_lock


@router.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
    dependencies=[Depends(require_valid_token)],
)
async def analyze(
    body: AnalyzeRequest,
    engine_manager: EngineManager = Depends(get_engine_manager),
    lock: asyncio.Lock = Depends(get_engine_lock),
) -> AnalyzeResponse:
    request_dict = body.model_dump()
    request_dict["id"] = str(uuid.uuid4())
    async with lock:
        try:
            response = await asyncio.to_thread(engine_manager.analyze, request_dict)
        except (KataGoCrashError, TimeoutError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if "error" in response:
            raise HTTPException(status_code=502, detail=response["error"])
    return AnalyzeResponse.model_validate(response)


@router.websocket("/api/analyze/stream")
async def analyze_stream(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    await websocket.accept()
    if not token_matches(token):
        await websocket.close(code=1008)
        return

    engine_manager: EngineManager = websocket.app.state.engine_manager
    lock: asyncio.Lock = websocket.app.state.engine_lock

    # The client can disconnect at any point in this multi-turn stream (a
    # long-running KataGo analysis makes this the normal case, not an edge
    # case) - every receive/send below can raise WebSocketDisconnect, so wrap
    # the whole exchange rather than each call individually.
    try:
        try:
            raw = await websocket.receive_json()
            stream_request = StreamAnalyzeRequest.model_validate(raw)
        except (ValidationError, ValueError):
            await websocket.send_json(ErrorMessage(detail="invalid request").model_dump())
            await websocket.close()
            return

        base_request = stream_request.model_dump(exclude={"turnNumbers"})
        total = len(stream_request.turnNumbers)

        for turn_number in stream_request.turnNumbers:
            request_dict = dict(base_request)
            request_dict["id"] = str(uuid.uuid4())
            request_dict["analyzeTurns"] = [turn_number]
            try:
                async with lock:
                    response = await asyncio.to_thread(engine_manager.analyze, request_dict)
            except (KataGoCrashError, TimeoutError, ValueError) as exc:
                await websocket.send_json(ErrorMessage(detail=str(exc)).model_dump())
                await websocket.close()
                return
            if "error" in response:
                await websocket.send_json(ErrorMessage(detail=response["error"]).model_dump())
                await websocket.close()
                return
            message = ProgressMessage(
                turnNumber=turn_number,
                total=total,
                result=AnalyzeResponse.model_validate(response),
            )
            await websocket.send_json(message.model_dump())

        await websocket.send_json(DoneMessage().model_dump())
        await websocket.close()
    except WebSocketDisconnect:
        return
