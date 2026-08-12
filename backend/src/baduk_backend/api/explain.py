import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from baduk_backend.api.schemas import ExplainRequest, ExplainResponse, RagCitation
from baduk_backend.auth import require_valid_token
from baduk_backend.board.board_state import apply_moves
from baduk_backend.feature_extraction.mistake import detect_mistake
from baduk_backend.feature_extraction.weak_group import detect_weak_group
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.orchestrator import LLMProvider

router = APIRouter()


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider


@router.post(
    "/api/explain",
    response_model=ExplainResponse,
    dependencies=[Depends(require_valid_token)],
)
async def explain(
    body: ExplainRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExplainResponse:
    turn_number = body.analysis.turnNumber if body.analysis.turnNumber is not None else len(body.moves)
    board = apply_moves(body.moves, body.boardXSize, body.boardYSize)
    weak_finding = detect_weak_group(board, body.boardXSize, body.boardYSize, body.analysis, turn_number)

    mistake_finding = None
    if body.analysisAfter is not None and body.nextMove is not None:
        mistake_finding = detect_mistake(
            board, body.analysis, body.analysisAfter, body.nextMove,
            body.boardXSize, body.boardYSize, turn_number + 1,
        )

    finding = mistake_finding or weak_finding
    if finding is None:
        return ExplainResponse(message="Ничего заметного не найдено в этой позиции")

    # verify_and_retry() itself never raises on a mismatch (falls back to a
    # templated response instead) - an exception here means the provider call
    # itself failed (network/timeout/auth), which the design spec treats as a
    # 503, the same way /api/analyze does for KataGo engine failures.
    try:
        explanation, verified = await asyncio.to_thread(
            verify_and_retry, provider, finding, body.analysis, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citation = None
    if explanation.rag_doc_id is not None:
        from baduk_backend.rag.retrieval import get_snippet_by_id

        snippet = await asyncio.to_thread(get_snippet_by_id, explanation.rag_doc_id)
        if snippet is not None:
            citation = RagCitation(
                doc_id=snippet.doc_id,
                title=snippet.title,
                source=snippet.source,
                text_snippet=snippet.text_snippet,
            )

    return ExplainResponse(finding=finding, explanation=explanation, verified=verified, citation=citation)
