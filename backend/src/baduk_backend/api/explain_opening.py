import asyncio

from fastapi import APIRouter, Depends, HTTPException

from baduk_backend.api.explain import get_llm_provider
from baduk_backend.api.schemas import ExplainOpeningRequest, ExplainResponse, RagCitation
from baduk_backend.auth import require_valid_token
from baduk_backend.feature_extraction.opening_loss import detect_opening_loss
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.orchestrator import LLMProvider

router = APIRouter()


@router.post(
    "/api/explain/opening",
    response_model=ExplainResponse,
    dependencies=[Depends(require_valid_token)],
)
async def explain_opening(
    body: ExplainOpeningRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> ExplainResponse:
    sequence = [(t.turnNumber, t.scoreLead, t.visits) for t in body.openingSequence]
    finding = detect_opening_loss(body.moves, sequence, body.color, body.boardXSize, body.boardYSize)
    if finding is None:
        return ExplainResponse(message="Существенной потери очков в дебюте не найдено")

    # verify_and_retry() itself never raises on a mismatch (falls back to a
    # templated response instead) - an exception here means the provider call
    # itself failed (network/timeout/auth), same 503 treatment as /api/explain.
    try:
        explanation, verified = await asyncio.to_thread(
            verify_and_retry, provider, finding, body.analysisAtEnd, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citation = None
    if explanation.rag_doc_id is not None:
        from baduk_backend.rag.retrieval import get_snippet_by_id

        try:
            snippet = await asyncio.to_thread(get_snippet_by_id, explanation.rag_doc_id)
        except Exception:
            snippet = None
        if snippet is not None:
            citation = RagCitation(
                doc_id=snippet.doc_id,
                title=snippet.title,
                source=snippet.source,
                text_snippet=snippet.text_snippet,
            )

    return ExplainResponse(finding=finding, explanation=explanation, verified=verified, citation=citation)
