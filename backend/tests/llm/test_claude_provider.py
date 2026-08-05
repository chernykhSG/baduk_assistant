from types import SimpleNamespace

import pytest

from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.providers.claude import ClaudeProvider


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _tool_use_response(summary: str, claims: list[dict]):
    block = SimpleNamespace(
        type="tool_use", name="record_explanation", input={"summary": summary, "claims": claims}
    )
    return SimpleNamespace(content=[block])


def _finding() -> Finding:
    return Finding(
        finding_id="f_1",
        type="weak_group",
        turn_number=1,
        stones=[(0, 0)],
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


def test_claude_provider_parses_tool_use_response_into_explanation():
    response = _tool_use_response(
        "Слабая группа найдена.",
        [{"text": "...", "finding_id": "f_1", "cited_field": "weak_score", "cited_number": 0.85}],
    )
    client = _FakeClient(response)
    provider = ClaudeProvider(client=client, model="claude-test")

    explanation = provider.complete(_finding(), _analysis())

    assert explanation.summary == "Слабая группа найдена."
    assert explanation.claims[0].cited_field == "weak_score"
    assert client.messages.calls[0]["tool_choice"] == {"type": "tool", "name": "record_explanation"}
    assert client.messages.calls[0]["model"] == "claude-test"


def test_claude_provider_appends_corrections_to_prompt():
    response = _tool_use_response("ok", [])
    client = _FakeClient(response)
    provider = ClaudeProvider(client=client, model="claude-test")

    provider.complete(_finding(), _analysis(), corrections=["ты ошибся про X"])

    sent_content = client.messages.calls[0]["messages"][0]["content"]
    assert "ты ошибся про X" in sent_content


def test_claude_provider_raises_if_tool_not_called():
    response = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])
    client = _FakeClient(response)
    provider = ClaudeProvider(client=client, model="claude-test")

    with pytest.raises(RuntimeError, match="did not call"):
        provider.complete(_finding(), _analysis())
