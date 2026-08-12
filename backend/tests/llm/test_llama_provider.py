import json
import threading

import pytest

pytest.importorskip("llama_cpp")

from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import WeakGroupFinding
from baduk_backend.llm.providers.llama import LlamaProvider


@pytest.fixture(autouse=True)
def _no_rag_by_default(monkeypatch):
    # Without this, `_rag_available()` would do a REAL check against this
    # dev machine's actual chromadb/sentence_transformers install and
    # backend/rag_store/ directory - both of which may genuinely exist here
    # (installed/ingested for the RAG ingestion slice's own tests), making
    # every pre-existing test in this file non-deterministic depending on
    # local machine state. Force the RAG-unavailable path by default; the
    # new RAG-specific tests below override this within their own body.
    monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", lambda: False)


class _FakeLlama:
    def __init__(self, response):
        # `response` may be a single response dict (returned for every call -
        # the shape every pre-existing single-call test in this file uses)
        # or a list of response dicts, returned one per call in order - the
        # two-call agentic RAG flow needs a different response for its
        # decision call vs. its finalize call.
        self._sequence = response if isinstance(response, list) else None
        self._response = None if isinstance(response, list) else response
        self.calls: list[dict] = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if self._sequence is not None:
            return self._sequence[len(self.calls) - 1]
        return self._response


def _chat_completion_response(content: str | None):
    return {"choices": [{"message": {"content": content}}]}


def _json_response(summary: str, claims: list[dict]):
    return _chat_completion_response(json.dumps({"summary": summary, "claims": claims}))


def _finding() -> WeakGroupFinding:
    return WeakGroupFinding(
        finding_id="f_1",
        type="weak_group",
        turn_number=1,
        stones=[(0, 0)],
        color="B",
        weak_score=0.85,
        own_certainty=0.1,
        boundary_certainty=0.1,
        liberties=2,
        severity="high",
        confidence=1.0,
    )


def _analysis() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x", moveInfos=[], rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=500), ownership=[0.0]
    )


def test_llama_provider_parses_json_response_into_explanation():
    response = _json_response(
        "Слабая группа найдена.",
        [{"text": "...", "finding_id": "f_1", "cited_field": "weak_score", "cited_number": 0.85}],
    )
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    explanation = provider.complete(_finding(), _analysis(), board_size=9)

    assert explanation.summary == "Слабая группа найдена."
    assert explanation.claims[0].cited_field == "weak_score"


def test_llama_provider_uses_json_object_response_format_with_schema():
    from baduk_backend.llm.prompts import EXPLANATION_TOOL_PARAMETERS

    response = _json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    provider.complete(_finding(), _analysis(), board_size=9)

    call = llm.calls[0]
    assert call["response_format"] == {"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS}
    assert call["max_tokens"] == 2048


def test_llama_provider_prompt_uses_gtp_coords_and_color_not_raw_json():
    response = _json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    provider.complete(_finding(), _analysis(), board_size=9)

    sent_messages = llm.calls[0]["messages"]
    user_content = next(m["content"] for m in sent_messages if m["role"] == "user")
    # stones=[(0, 0)] on a 9x9 board is GTP "A9" - a human-readable
    # coordinate, not the raw grid-index tuple [0, 0] that model_dump_json()
    # would have produced.
    assert "A9" in user_content
    assert "[0, 0]" not in user_content
    assert "чёрных" in user_content
    assert "f_1" in user_content
    assert "0.85" in user_content  # weak_score
    assert "2" in user_content  # liberties


def test_llama_provider_appends_corrections_to_prompt():
    response = _json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    provider.complete(_finding(), _analysis(), board_size=9, corrections=["ты ошибся про X"])

    sent_messages = llm.calls[0]["messages"]
    user_content = next(m["content"] for m in sent_messages if m["role"] == "user")
    assert "ты ошибся про X" in user_content


def test_llama_provider_raises_if_content_is_none():
    response = _chat_completion_response(None)
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    with pytest.raises(RuntimeError, match="did not produce"):
        provider.complete(_finding(), _analysis(), board_size=9)


def test_llama_provider_raises_if_content_is_invalid_json():
    response = _chat_completion_response("not valid json{{{")
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    with pytest.raises(RuntimeError, match="did not produce"):
        provider.complete(_finding(), _analysis(), board_size=9)


def test_llama_provider_raises_with_finish_reason_if_content_fails_schema_validation():
    # Syntactically valid JSON that fails Explanation's schema validation
    # (missing the required "claims" field) - this exercises
    # _validate_explanation's ValidationError branch, which must still
    # surface finish_reason (e.g. to diagnose truncation by max_tokens)
    # just like the JSONDecodeError and empty-content branches do.
    response = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": json.dumps({"summary": "ok"})},
            }
        ]
    }
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    with pytest.raises(RuntimeError, match="finish_reason='length'"):
        provider.complete(_finding(), _analysis(), board_size=9)


def test_llama_provider_constructs_llama_with_env_config(monkeypatch):
    captured: dict = {}

    class _FakeLlamaClass:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("llama_cpp.Llama", _FakeLlamaClass)
    monkeypatch.setenv("BADUK_LLAMA_MODEL_PATH", "/path/to/model.gguf")
    monkeypatch.delenv("BADUK_LLAMA_N_GPU_LAYERS", raising=False)

    LlamaProvider()

    assert captured["model_path"] == "/path/to/model.gguf"
    assert captured["n_gpu_layers"] == -1
    assert captured["n_ctx"] == 8192
    assert captured["verbose"] is False


def test_llama_provider_reads_n_gpu_layers_override(monkeypatch):
    captured: dict = {}

    class _FakeLlamaClass:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("llama_cpp.Llama", _FakeLlamaClass)
    monkeypatch.setenv("BADUK_LLAMA_MODEL_PATH", "/path/to/model.gguf")
    monkeypatch.setenv("BADUK_LLAMA_N_GPU_LAYERS", "20")

    LlamaProvider()

    assert captured["n_gpu_layers"] == 20


def test_llama_provider_raises_clear_error_for_invalid_n_gpu_layers(monkeypatch):
    class _FakeLlamaClass:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr("llama_cpp.Llama", _FakeLlamaClass)
    monkeypatch.setenv("BADUK_LLAMA_MODEL_PATH", "/path/to/model.gguf")
    monkeypatch.setenv("BADUK_LLAMA_N_GPU_LAYERS", "not-a-number")

    with pytest.raises(ValueError, match="BADUK_LLAMA_N_GPU_LAYERS"):
        LlamaProvider()


def test_llama_provider_has_a_lock_guarding_the_shared_llama_instance():
    response = _json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    assert isinstance(provider._lock, type(threading.Lock()))


def test_llama_provider_without_rag_available_uses_original_single_call_schema():
    from baduk_backend.llm.prompts import EXPLANATION_TOOL_PARAMETERS

    response = _json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    explanation = provider.complete(_finding(), _analysis(), board_size=9)

    assert len(llm.calls) == 1
    assert llm.calls[0]["response_format"] == {"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS}
    assert explanation.rag_doc_id is None


def test_llama_provider_with_rag_available_can_decide_not_to_search(monkeypatch):
    from baduk_backend.llm.prompts import RAG_DECISION_TOOL_PARAMETERS

    monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", lambda: True)
    response = _chat_completion_response(
        json.dumps({"tool": "record_explanation", "summary": "ok", "claims": []})
    )
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    explanation = provider.complete(_finding(), _analysis(), board_size=9)

    assert len(llm.calls) == 1
    assert llm.calls[0]["response_format"] == {"type": "json_object", "schema": RAG_DECISION_TOOL_PARAMETERS}
    assert explanation.summary == "ok"
    assert explanation.rag_doc_id is None


def test_llama_provider_with_rag_available_searches_then_finalizes(monkeypatch):
    from baduk_backend.llm.prompts import EXPLANATION_WITH_RAG_TOOL_PARAMETERS, RAG_DECISION_TOOL_PARAMETERS
    from baduk_backend.rag.schemas import RagSnippet

    monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", lambda: True)

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        assert top_k == 3
        return [
            RagSnippet(
                doc_id="two-eyes-necessary",
                title="Два глаза",
                source="principles/two-eyes.md",
                text_snippet="Группа с двумя глазами не может быть захвачена.",
                relevance_score=0.9,
            )
        ]

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    decision_response = _chat_completion_response(json.dumps({"tool": "retrieve_knowledge"}))
    final_response = _chat_completion_response(
        json.dumps(
            {"summary": "Найдена слабая группа.", "claims": [], "rag_doc_id": "two-eyes-necessary"}
        )
    )
    llm = _FakeLlama([decision_response, final_response])
    provider = LlamaProvider(llm=llm)

    explanation = provider.complete(_finding(), _analysis(), board_size=9)

    assert len(llm.calls) == 2
    assert llm.calls[0]["response_format"] == {"type": "json_object", "schema": RAG_DECISION_TOOL_PARAMETERS}
    assert llm.calls[1]["response_format"] == {
        "type": "json_object",
        "schema": EXPLANATION_WITH_RAG_TOOL_PARAMETERS,
    }
    final_user_content = next(m["content"] for m in llm.calls[1]["messages"] if m["role"] == "user")
    assert "two-eyes-necessary" in final_user_content
    assert "Группа с двумя глазами" in final_user_content
    assert explanation.rag_doc_id == "two-eyes-necessary"
    assert explanation.summary == "Найдена слабая группа."


def test_llama_provider_degrades_gracefully_when_search_fails_mid_flow(monkeypatch):
    monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", lambda: True)

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        raise RuntimeError("RAG store not found")

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    decision_response = _chat_completion_response(json.dumps({"tool": "retrieve_knowledge"}))
    final_response = _chat_completion_response(json.dumps({"summary": "ok", "claims": [], "rag_doc_id": None}))
    llm = _FakeLlama([decision_response, final_response])
    provider = LlamaProvider(llm=llm)

    explanation = provider.complete(_finding(), _analysis(), board_size=9)

    assert len(llm.calls) == 2
    final_user_content = next(m["content"] for m in llm.calls[1]["messages"] if m["role"] == "user")
    assert "не дал результатов" in final_user_content
    assert explanation.rag_doc_id is None


def test_format_snippets_lists_doc_id_title_and_text():
    from baduk_backend.llm.providers.llama import _format_snippets
    from baduk_backend.rag.schemas import RagSnippet

    snippets = [
        RagSnippet(
            doc_id="d1",
            title="Заголовок",
            source="principles/d1.md",
            text_snippet="Текст карточки.",
            relevance_score=0.8,
        )
    ]
    formatted = _format_snippets(snippets)
    assert "d1" in formatted
    assert "Заголовок" in formatted
    assert "Текст карточки." in formatted


def test_format_snippets_handles_empty_list():
    from baduk_backend.llm.providers.llama import _format_snippets

    assert "не дал результатов" in _format_snippets([])


def test_rag_available_returns_false_when_store_missing(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    pytest.importorskip("sentence_transformers")
    # Restore the real `_rag_available` that the autouse `_no_rag_by_default`
    # fixture patched away before this test body runs - otherwise the
    # `from ... import _rag_available` below would capture that fixture's
    # fake `lambda: False` instead of the real implementation this test
    # means to exercise.
    monkeypatch.undo()
    from baduk_backend.llm.providers.llama import _rag_available

    monkeypatch.setattr("baduk_backend.rag.store.DEFAULT_STORE_PATH", tmp_path / "does_not_exist")

    assert _rag_available() is False


def test_rag_available_returns_true_when_installed_and_store_exists(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    pytest.importorskip("sentence_transformers")
    # See test_rag_available_returns_false_when_store_missing above: undo the
    # autouse fixture's patch first so this imports the real `_rag_available`.
    monkeypatch.undo()
    from baduk_backend.llm.providers.llama import _rag_available

    store_path = tmp_path / "rag_store"
    store_path.mkdir()
    monkeypatch.setattr("baduk_backend.rag.store.DEFAULT_STORE_PATH", store_path)

    assert _rag_available() is True
