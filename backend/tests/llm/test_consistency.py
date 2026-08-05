from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.schemas import Claim, Explanation


class _RecordingFakeProvider:
    def __init__(self, responses: list[Explanation]):
        self._responses = list(responses)
        self.calls: list[list[str] | None] = []

    def complete(self, finding, analysis, corrections=None):
        self.calls.append(corrections)
        return self._responses.pop(0)


def _finding() -> Finding:
    return Finding(
        finding_id="f_test",
        type="weak_group",
        turn_number=5,
        stones=[(4, 4)],
        weak_score=0.85,
        own_certainty=0.0,
        boundary_certainty=0.0,
        liberties=4,
        severity="high",
        confidence=0.5,
    )


def _analysis() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[0.0] * 81,
    )


def test_verify_and_retry_accepts_correct_claims_on_first_try():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is True
    assert result == explanation
    assert provider.calls == [None]


def test_verify_and_retry_retries_once_then_succeeds():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.5)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    provider = _RecordingFakeProvider([bad, good])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is True
    assert result == good
    assert provider.calls[0] is None
    assert provider.calls[1] is not None
    assert "weak_score" in provider.calls[1][0]


def test_verify_and_retry_falls_back_after_exhausting_retries():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.1)],
    )
    provider = _RecordingFakeProvider([bad, bad, bad])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is False
    assert result.claims == []
    assert "0.85" in result.summary


def test_verify_and_retry_checks_claims_against_rootinfo_fields():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="visits", cited_number=250)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _finding(), _analysis())

    assert verified is True
