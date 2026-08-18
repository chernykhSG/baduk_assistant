import asyncio

from fastapi import APIRouter, Depends, HTTPException

from baduk_backend.api.explain import get_llm_provider
from baduk_backend.api.schemas import AskRequest, AskResponse, RagCitation
from baduk_backend.auth import require_valid_token
from baduk_backend.llm.consistency import verify_question_and_retry
from baduk_backend.llm.orchestrator import LLMProvider

router = APIRouter()


@router.post(
    "/api/ask",
    response_model=AskResponse,
    dependencies=[Depends(require_valid_token)],
)
async def ask(
    body: AskRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> AskResponse:
    # Structural check, not isinstance(provider, LlamaProvider) - importing
    # the concrete class here would force an unconditional `import llama_cpp`
    # into a module that must keep working when the active provider is
    # claude/gemini and llama_cpp isn't installed at all.
    if not hasattr(provider, "answer_question"):
        raise HTTPException(status_code=503, detail="/api/ask доступен только с провайдером llama")

    try:
        question_answer, verified = await asyncio.to_thread(
            verify_question_and_retry, provider, body.question, body.analysis, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citation = None
    if question_answer.rag_doc_id is not None:
        from baduk_backend.rag.retrieval import get_snippet_by_id

        try:
            snippet = await asyncio.to_thread(get_snippet_by_id, question_answer.rag_doc_id)
        except Exception:
            snippet = None
        if snippet is not None:
            citation = RagCitation(
                doc_id=snippet.doc_id,
                title=snippet.title,
                source=snippet.source,
                text_snippet=snippet.text_snippet,
            )

    return AskResponse(answer=question_answer.answer, verified=verified, citation=citation)
