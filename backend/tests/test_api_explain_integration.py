import os

import pytest

pytestmark = pytest.mark.integration


def test_explain_with_real_claude_api():
    if not os.environ.get("BADUK_CLAUDE_API_KEY"):
        pytest.skip("BADUK_CLAUDE_API_KEY not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import WeakGroupFinding
    from baduk_backend.llm.providers.claude import ClaudeProvider

    provider = ClaudeProvider()
    finding = WeakGroupFinding(
        finding_id="f_test",
        type="weak_group",
        turn_number=10,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.1,
        boundary_certainty=0.2,
        liberties=2,
        severity="high",
        confidence=0.9,
    )
    analysis = AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.4, scoreLead=-3.0, visits=800),
        ownership=[0.1] * 81,
    )

    explanation = provider.complete(finding, analysis, board_size=9)

    assert explanation.summary
    assert len(explanation.claims) > 0


def test_explain_with_real_gemini_api():
    if not os.environ.get("BADUK_GEMINI_API_KEY"):
        pytest.skip("BADUK_GEMINI_API_KEY not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import WeakGroupFinding
    from baduk_backend.llm.providers.gemini import GeminiProvider

    provider = GeminiProvider()
    finding = WeakGroupFinding(
        finding_id="f_test",
        type="weak_group",
        turn_number=10,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.1,
        boundary_certainty=0.2,
        liberties=2,
        severity="high",
        confidence=0.9,
    )
    analysis = AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.4, scoreLead=-3.0, visits=800),
        ownership=[0.1] * 81,
    )

    explanation = provider.complete(finding, analysis, board_size=9)

    assert explanation.summary
    assert len(explanation.claims) > 0


def test_explain_with_real_llama():
    if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
        pytest.skip("BADUK_LLAMA_MODEL_PATH not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import WeakGroupFinding
    from baduk_backend.llm.providers.llama import LlamaProvider

    provider = LlamaProvider()
    finding = WeakGroupFinding(
        finding_id="f_test",
        type="weak_group",
        turn_number=10,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.1,
        boundary_certainty=0.2,
        liberties=2,
        severity="high",
        confidence=0.9,
    )
    analysis = AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.4, scoreLead=-3.0, visits=800),
        ownership=[0.1] * 81,
    )

    explanation = provider.complete(finding, analysis, board_size=9)

    assert explanation.summary
    assert len(explanation.claims) > 0


def test_explain_with_real_llama_and_rag():
    if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
        pytest.skip("BADUK_LLAMA_MODEL_PATH not set")

    from baduk_backend.rag.store import DEFAULT_STORE_PATH

    if not DEFAULT_STORE_PATH.exists():
        pytest.skip(
            "backend/rag_store/ not found - run ingestion first: python -m baduk_backend.rag.ingest"
        )

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import WeakGroupFinding
    from baduk_backend.llm.providers.llama import LlamaProvider

    provider = LlamaProvider()
    finding = WeakGroupFinding(
        finding_id="f_test",
        turn_number=10,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.1,
        boundary_certainty=0.2,
        liberties=2,
        severity="high",
        confidence=0.9,
    )
    analysis = AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.4, scoreLead=-3.0, visits=800),
        ownership=[0.1] * 81,
    )

    explanation = provider.complete(finding, analysis, board_size=9)

    assert explanation.summary
    # The model may legitimately decide this specific finding doesn't need a
    # search - only assert the citation is well-formed when one was made.
    if explanation.rag_doc_id is not None:
        assert isinstance(explanation.rag_doc_id, str)
        assert explanation.rag_doc_id != ""
