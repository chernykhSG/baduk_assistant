from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import Finding, MistakeFinding, WeakGroupFinding
from baduk_backend.llm.consistency import verify_and_retry
from baduk_backend.llm.schemas import Claim, Explanation


class _RecordingFakeProvider:
    def __init__(self, responses: list[Explanation]):
        self._responses = list(responses)
        self.calls: list[list[str] | None] = []

    def complete(self, finding, analysis, board_size, corrections=None):
        self.calls.append(corrections)
        return self._responses.pop(0)


def _finding() -> WeakGroupFinding:
    return WeakGroupFinding(
        finding_id="f_test",
        type="weak_group",
        turn_number=5,
        stones=[(4, 4)],
        color="B",
        weak_score=0.85,
        own_certainty=0.0,
        boundary_certainty=0.0,
        liberties=4,
        severity="high",
        confidence=0.5,
    )


def _mistake_finding() -> Finding:
    return MistakeFinding(
        finding_id="f_test",
        turn_number=5,
        color="W",
        move="Q4",
        delta_score=3.0,
        stage="middlegame",
        severity="medium",
        confidence=0.6,
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

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

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

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

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

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is False
    assert result.claims == []
    assert "0.85" in result.summary


def test_verify_and_retry_checks_claims_against_rootinfo_fields():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="visits", cited_number=250)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is True


def test_verify_and_retry_rejects_claim_with_wrong_finding_id():
    wrong_id = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_other", cited_field="weak_score", cited_number=0.85)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    provider = _RecordingFakeProvider([wrong_id, good])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is True
    assert result == good
    assert provider.calls[0] is None
    assert provider.calls[1] is not None
    assert "finding_id" in provider.calls[1][0]


def test_verify_and_retry_rejects_empty_claims_list():
    empty = Explanation(summary="...", claims=[])
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    provider = _RecordingFakeProvider([empty, good])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is True
    assert result == good
    assert provider.calls[0] is None
    assert provider.calls[1] is not None


def test_verify_and_retry_falls_back_when_claims_stay_empty_after_retries():
    empty = Explanation(summary="...", claims=[])
    provider = _RecordingFakeProvider([empty, empty, empty])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is False
    assert result.claims == []


def test_verify_and_retry_accepts_correct_mistake_claims():
    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=3.0)],
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _mistake_finding(), _analysis(), 9)

    assert verified is True
    assert result == explanation


def test_verify_and_retry_rejects_wrong_mistake_claim_then_retries():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=0.1)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=3.0)],
    )
    provider = _RecordingFakeProvider([bad, good])

    result, verified = verify_and_retry(provider, _mistake_finding(), _analysis(), 9)

    assert verified is True
    assert result == good
    assert "delta_score" in provider.calls[1][0]


def test_verify_and_retry_falls_back_with_mistake_specific_summary():
    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=0.1)],
    )
    provider = _RecordingFakeProvider([bad, bad, bad])

    result, verified = verify_and_retry(provider, _mistake_finding(), _analysis(), 9)

    assert verified is False
    assert result.claims == []
    assert "3.00" in result.summary
    assert "Δ" in result.summary


def test_verify_and_retry_does_not_crash_on_cross_type_field_weak_group_finding():
    # delta_score belongs to MistakeFinding, not WeakGroupFinding, and is not
    # a rootInfo attribute either - citing it against a weak_group finding
    # must be treated as a mismatch (retry), never raise AttributeError.
    cross_type = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=3.0)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    provider = _RecordingFakeProvider([cross_type, good])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is True
    assert result == good
    assert provider.calls[0] is None
    assert provider.calls[1] is not None
    assert "delta_score" in provider.calls[1][0]
    assert "не относится" in provider.calls[1][0]


def test_verify_and_retry_does_not_crash_on_cross_type_field_mistake_finding():
    # weak_score belongs to WeakGroupFinding, not MistakeFinding, and is not
    # a rootInfo attribute either - citing it against a mistake finding must
    # be treated as a mismatch (retry), never raise AttributeError.
    cross_type = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="delta_score", cited_number=3.0)],
    )
    provider = _RecordingFakeProvider([cross_type, good])

    result, verified = verify_and_retry(provider, _mistake_finding(), _analysis(), 9)

    assert verified is True
    assert result == good
    assert provider.calls[0] is None
    assert provider.calls[1] is not None
    assert "weak_score" in provider.calls[1][0]
    assert "не относится" in provider.calls[1][0]


def test_verify_and_retry_accepts_valid_rag_doc_id(monkeypatch):
    from baduk_backend.rag.schemas import RagSnippet

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        return [
            RagSnippet(
                doc_id="two-eyes-necessary",
                title="...",
                source="...",
                text_snippet="...",
                relevance_score=0.9,
            )
        ]

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    explanation = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
        rag_doc_id="two-eyes-necessary",
    )
    provider = _RecordingFakeProvider([explanation])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is True
    assert result.rag_doc_id == "two-eyes-necessary"
    assert provider.calls == [None]


def test_verify_and_retry_rejects_hallucinated_rag_doc_id_then_retries(monkeypatch):
    from baduk_backend.rag.schemas import RagSnippet

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        return [
            RagSnippet(
                doc_id="real-doc", title="...", source="...", text_snippet="...", relevance_score=0.9
            )
        ]

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
        rag_doc_id="made-up-doc",
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
        rag_doc_id="real-doc",
    )
    provider = _RecordingFakeProvider([bad, good])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is True
    assert result.rag_doc_id == "real-doc"
    assert provider.calls[0] is None
    assert provider.calls[1] is not None
    assert "made-up-doc" in provider.calls[1][0]


def test_verify_and_retry_treats_rag_store_unavailable_as_invalid_citation(monkeypatch):
    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        raise RuntimeError("RAG store not found")

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
        rag_doc_id="anything",
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
        rag_doc_id=None,
    )
    provider = _RecordingFakeProvider([bad, good])

    result, verified = verify_and_retry(provider, _finding(), _analysis(), 9)

    assert verified is True
    assert result.rag_doc_id is None


def test_verify_and_retry_correction_does_not_mention_empty_claims_when_only_rag_doc_id_is_wrong(monkeypatch):
    from baduk_backend.rag.schemas import RagSnippet

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        return [
            RagSnippet(
                doc_id="real-doc", title="...", source="...", text_snippet="...", relevance_score=0.9
            )
        ]

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    bad = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
        rag_doc_id="made-up-doc",
    )
    good = Explanation(
        summary="...",
        claims=[Claim(text="...", finding_id="f_test", cited_field="weak_score", cited_number=0.85)],
        rag_doc_id="real-doc",
    )
    provider = _RecordingFakeProvider([bad, good])

    verify_and_retry(provider, _finding(), _analysis(), 9)

    # the numeric claim was already correct - the only real problem is the
    # citation, so the correction message must not claim the claims list is
    # empty (it isn't).
    assert "ни одного утверждения" not in provider.calls[1][0]
