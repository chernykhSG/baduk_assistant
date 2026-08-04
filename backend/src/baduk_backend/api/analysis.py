import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from baduk_backend.api.schemas import AnalyzeRequest, AnalyzeResponse
from baduk_backend.auth import require_valid_token
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
        except KataGoCrashError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return AnalyzeResponse.model_validate(response)
