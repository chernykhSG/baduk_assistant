from types import SimpleNamespace

import pytest

from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import WeakGroupFinding
from baduk_backend.llm.providers.gemini import GeminiProvider


class _FakeModels:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.models = _FakeModels(response)


def _function_call_response(summary: str, claims: list[dict]):
    call = SimpleNamespace(
        name="record_explanation", args={"summary": summary, "claims": claims}
    )
    return SimpleNamespace(function_calls=[call])


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


def test_gemini_provider_parses_function_call_response_into_explanation():
    response = _function_call_response(
        "Слабая группа найдена.",
        [{"text": "...", "finding_id": "f_1", "cited_field": "weak_score", "cited_number": 0.85}],
    )
    client = _FakeClient(response)
    provider = GeminiProvider(client=client, model="gemini-test")

    explanation = provider.complete(_finding(), _analysis(), board_size=9)

    assert explanation.summary == "Слабая группа найдена."
    assert explanation.claims[0].cited_field == "weak_score"
    assert client.models.calls[0]["model"] == "gemini-test"


def test_gemini_provider_forces_function_call_with_any_mode():
    response = _function_call_response("ok", [])
    client = _FakeClient(response)
    provider = GeminiProvider(client=client, model="gemini-test")

    provider.complete(_finding(), _analysis(), board_size=9)

    config = client.models.calls[0]["config"]
    assert config.tool_config.function_calling_config.mode == "ANY"
    assert config.tool_config.function_calling_config.allowed_function_names == [
        "record_explanation"
    ]
    assert config.thinking_config.thinking_level == "MINIMAL"


def test_gemini_provider_prompt_uses_gtp_coords_and_color_not_raw_json():
    response = _function_call_response("ok", [])
    client = _FakeClient(response)
    provider = GeminiProvider(client=client, model="gemini-test")

    provider.complete(_finding(), _analysis(), board_size=9)

    sent_content = client.models.calls[0]["contents"]
    # stones=[(0, 0)] on a 9x9 board is GTP "A9" - a human-readable
    # coordinate, not the raw grid-index tuple [0, 0] that model_dump_json()
    # would have produced.
    assert "A9" in sent_content
    assert "[0, 0]" not in sent_content
    assert "чёрных" in sent_content
    assert "f_1" in sent_content
    assert "0.85" in sent_content  # weak_score
    assert "2" in sent_content  # liberties


def test_gemini_provider_client_uses_60s_timeout(monkeypatch):
    captured: dict = {}

    class _FakeGenaiClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("google.genai.Client", _FakeGenaiClient)
    monkeypatch.setenv("BADUK_GEMINI_API_KEY", "test-key")

    GeminiProvider()

    assert captured["api_key"] == "test-key"
    assert captured["http_options"].timeout == 60_000


def test_gemini_provider_appends_corrections_to_prompt():
    response = _function_call_response("ok", [])
    client = _FakeClient(response)
    provider = GeminiProvider(client=client, model="gemini-test")

    provider.complete(_finding(), _analysis(), board_size=9, corrections=["ты ошибся про X"])

    sent_content = client.models.calls[0]["contents"]
    assert "ты ошибся про X" in sent_content


def test_gemini_provider_raises_if_function_not_called():
    response = SimpleNamespace(function_calls=None)
    client = _FakeClient(response)
    provider = GeminiProvider(client=client, model="gemini-test")

    with pytest.raises(RuntimeError, match="did not call"):
        provider.complete(_finding(), _analysis(), board_size=9)


def test_gemini_provider_raises_if_matched_call_has_no_args():
    call = SimpleNamespace(name="record_explanation", args=None)
    response = SimpleNamespace(function_calls=[call])
    client = _FakeClient(response)
    provider = GeminiProvider(client=client, model="gemini-test")

    with pytest.raises(RuntimeError, match="did not call"):
        provider.complete(_finding(), _analysis(), board_size=9)
