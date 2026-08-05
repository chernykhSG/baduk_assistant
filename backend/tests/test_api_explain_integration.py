import os

import pytest

pytestmark = pytest.mark.integration


def test_explain_with_real_claude_api():
    if not os.environ.get("BADUK_CLAUDE_API_KEY"):
        pytest.skip("BADUK_CLAUDE_API_KEY not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import Finding
    from baduk_backend.llm.providers.claude import ClaudeProvider

    provider = ClaudeProvider()
    finding = Finding(
        finding_id="f_test",
        type="weak_group",
        turn_number=10,
        stones=[(4, 4)],
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

    explanation = provider.complete(finding, analysis)

    assert explanation.summary
    assert len(explanation.claims) > 0
