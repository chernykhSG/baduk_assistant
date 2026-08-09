import json
import threading

import pytest

pytest.importorskip("llama_cpp")

from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.providers.llama import LlamaProvider


class _FakeLlama:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _chat_completion_response(content: str | None):
    return {"choices": [{"message": {"content": content}}]}


def _json_response(summary: str, claims: list[dict]):
    return _chat_completion_response(json.dumps({"summary": summary, "claims": claims}))


def _finding() -> Finding:
    return Finding(
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
