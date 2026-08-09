# Gemini LLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Google Gemini as a second, selectable LLM provider for `/api/explain`, alongside the existing Claude provider, chosen at backend startup via a new `BADUK_LLM_PROVIDER` env var (default `"gemini"`).

**Architecture:** `backend/src/baduk_backend/llm/orchestrator.py`'s existing `LLMProvider` Protocol (`complete(finding, analysis, board_size, corrections=None) -> Explanation`) is already provider-agnostic — a new `GeminiProvider` class implements it using the official `google-genai` SDK's forced function-calling (`tool_config.mode="ANY"`), the Gemini equivalent of `ClaudeProvider`'s Anthropic `tool_choice`. The system prompt, user-prompt builder, and tool schema — currently private to `claude.py` — move to a new shared `llm/prompts.py` so both providers read from one source instead of duplicating the anti-hallucination instructions. `main.py::run()` gains a small, independently testable provider-selection function reading `BADUK_LLM_PROVIDER`.

**Tech Stack:** Python 3.12, FastAPI backend (`backend/`), `google-genai>=1.0.0` (official Gemini SDK, replaces deprecated `google-generativeai`), existing `anthropic>=0.40.0`, `pytest`.

## Global Constraints

- Work happens only on branch `phase-2-gemini-provider`, forked from `main`. Never commit directly to `main`.
- TDD discipline: Task 1 is a refactor — the existing `test_claude_provider.py` suite is the regression net (must stay green, unmodified) rather than new failing tests. Tasks 2-3 follow standard write-failing-test-first TDD.
- No hardcoded API keys or file paths in source code. Placeholder key strings (e.g. `"AIzaSy..."`) may appear only in README command examples, never in `.py` files.
- This machine's `uv` is sometimes missing from `PATH` (a known, already-documented environment issue — see `backend/README.md`/`task_plan.md` backlog). Every dependency-install step shows both `uv add <pkg>` and the direct `.venv\Scripts\python.exe -m pip install <pkg>` fallback.
- `google-genai` is already installed in this machine's `backend/.venv` (version 2.17.0, installed during design research) — implementers on this machine can skip straight to verifying `import google.genai` works; the pip/uv install step is still required in the plan for reproducibility on a fresh checkout.
- Do not modify `llm/orchestrator.py` or `llm/consistency.py` — both are already provider-agnostic and correctly out of scope per the design spec.

---

## Context for every task

**Current `backend/src/baduk_backend/llm/providers/claude.py`** (full file, 109 lines — read before starting Task 1):

```python
import os

import anthropic

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.board.gtp_coords import xy_to_gtp
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.schemas import Explanation

DEFAULT_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = """\
Ты - тренер по игре в го, объясняющий позицию игроку кю-уровня на русском языке.
Тебе дана находка о слабой группе камней и числа из анализа KataGo. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_explanation - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле \
(weak_score, own_certainty, boundary_certainty, liberties, visits, winrate \
или scoreLead) и точное число из данных.
3. Если уверенность (confidence) находки ниже 0.7, используй смягчающий \
язык ("похоже", "вероятно", "возможно").
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""

_TOOL_SCHEMA = {
    "name": "record_explanation",
    "description": "Записывает структурированное объяснение слабой группы для игрока.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Объяснение на русском для игрока."},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "finding_id": {"type": "string"},
                        "cited_field": {
                            "type": "string",
                            "enum": [
                                "weak_score",
                                "own_certainty",
                                "boundary_certainty",
                                "liberties",
                                "visits",
                                "winrate",
                                "scoreLead",
                            ],
                        },
                        "cited_number": {"type": "number"},
                    },
                    "required": ["text", "finding_id", "cited_field", "cited_number"],
                },
            },
        },
        "required": ["summary", "claims"],
    },
}


def _user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    color_ru = "чёрных" if finding.color == "B" else "белых"
    coords = ", ".join(xy_to_gtp(x, y, board_size) for x, y in finding.stones)
    return (
        f"Находка о слабой группе {color_ru} (finding_id={finding.finding_id}):\n"
        f"Камни группы: {coords}\n"
        f"weak_score={finding.weak_score}, own_certainty={finding.own_certainty}, "
        f"boundary_certainty={finding.boundary_certainty}, liberties={finding.liberties}, "
        f"confidence={finding.confidence}, turn_number={finding.turn_number}\n"
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )


class ClaudeProvider:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None):
        self._client = client or anthropic.Anthropic(
            api_key=os.environ["BADUK_CLAUDE_API_KEY"], timeout=60.0
        )
        self._model = model or os.environ.get("BADUK_CLAUDE_MODEL", DEFAULT_MODEL)

    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> Explanation:
        user_content = _user_prompt(finding, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            thinking={"type": "disabled"},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_explanation"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_explanation":
                return Explanation.model_validate(block.input)
        raise RuntimeError("Claude did not call record_explanation")
```

**`LLMProvider` Protocol** (`backend/src/baduk_backend/llm/orchestrator.py`, unchanged by this plan):

```python
class LLMProvider(Protocol):
    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> Explanation: ...
```

**`Explanation`/`Claim` schemas** (`backend/src/baduk_backend/llm/schemas.py`, unchanged, for reference):

```python
class Claim(BaseModel):
    text: str
    finding_id: str
    cited_field: CitedField
    cited_number: float


class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
```

**Verified `google-genai` v2.17.0 API** (introspected directly against the installed package — do not rely on memory or older docs for this SDK, its API has changed across major versions):
- `genai.Client(api_key=str, http_options=types.HttpOptions(timeout=<milliseconds:int>))` — `timeout` is in **milliseconds**, not seconds. Omitting `vertexai=True` uses Google AI Studio mode (not Vertex AI), which is what this project needs.
- `client.models.generate_content(model=str, contents=str, config=types.GenerateContentConfig) -> types.GenerateContentResponse` — `contents` accepts a plain string directly.
- `types.GenerateContentConfig(system_instruction=str, tools=list[types.Tool], tool_config=types.ToolConfig, thinking_config=types.ThinkingConfig)`.
- `types.Tool(function_declarations=list[types.FunctionDeclaration])`.
- `types.FunctionDeclaration(name=str, description=str, parameters=<dict>)` — `parameters` accepts a plain JSON-schema-shaped `dict` (with `type`/`properties`/`items`/`enum`/`required` keys); pydantic validates and converts it to `types.Schema` internally. Verified live: the exact same schema shape already used for Claude's `input_schema` validates cleanly here too.
- `types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=list[str]))` — `mode` accepts the plain string `"ANY"` (forces a function call every time, the Gemini equivalent of Claude's `tool_choice={"type": "tool", "name": ...}`).
- `types.ThinkingConfig(thinking_budget=0)` — disables extended "thinking", mirroring Claude's `thinking={"type": "disabled"}` (same rationale: predictable latency, no risk of the final answer being truncated by an unbounded thinking phase).
- Response parsing: `response.function_calls` is a ready-made SDK property returning `list[types.FunctionCall] | None` (drawn from `response.candidates[0].content.parts`, `None` if there's nothing there). `FunctionCall.name: str`, `FunctionCall.args: dict[str, Any] | None` — `args` is already a plain `dict`, no unwrapping needed.

---

### Task 1: Extract shared prompts/schema into `llm/prompts.py`, refactor `claude.py` to use them

**Files:**
- Create: `backend/src/baduk_backend/llm/prompts.py`
- Modify: `backend/src/baduk_backend/llm/providers/claude.py`
- Test: `backend/tests/llm/test_claude_provider.py` (regression net — read only, must not need edits)

**Interfaces:**
- Produces (for Task 2's `GeminiProvider` to consume): `backend/src/baduk_backend/llm/prompts.py` exports:
  - `SYSTEM_PROMPT: str`
  - `EXPLANATION_TOOL_NAME: str` (value `"record_explanation"`)
  - `EXPLANATION_TOOL_DESCRIPTION: str` (value `"Записывает структурированное объяснение слабой группы для игрока."`)
  - `EXPLANATION_TOOL_PARAMETERS: dict` (the JSON-schema-shaped dict currently nested under `_TOOL_SCHEMA["input_schema"]`)
  - `build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str`

- [ ] **Step 1: Create `backend/src/baduk_backend/llm/prompts.py`**

```python
from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.board.gtp_coords import xy_to_gtp
from baduk_backend.feature_extraction.schemas import Finding

SYSTEM_PROMPT = """\
Ты - тренер по игре в го, объясняющий позицию игроку кю-уровня на русском языке.
Тебе дана находка о слабой группе камней и числа из анализа KataGo. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_explanation - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле \
(weak_score, own_certainty, boundary_certainty, liberties, visits, winrate \
или scoreLead) и точное число из данных.
3. Если уверенность (confidence) находки ниже 0.7, используй смягчающий \
язык ("похоже", "вероятно", "возможно").
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""

EXPLANATION_TOOL_NAME = "record_explanation"
EXPLANATION_TOOL_DESCRIPTION = "Записывает структурированное объяснение слабой группы для игрока."
EXPLANATION_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Объяснение на русском для игрока."},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "finding_id": {"type": "string"},
                    "cited_field": {
                        "type": "string",
                        "enum": [
                            "weak_score",
                            "own_certainty",
                            "boundary_certainty",
                            "liberties",
                            "visits",
                            "winrate",
                            "scoreLead",
                        ],
                    },
                    "cited_number": {"type": "number"},
                },
                "required": ["text", "finding_id", "cited_field", "cited_number"],
            },
        },
    },
    "required": ["summary", "claims"],
}


def build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str:
    color_ru = "чёрных" if finding.color == "B" else "белых"
    coords = ", ".join(xy_to_gtp(x, y, board_size) for x, y in finding.stones)
    return (
        f"Находка о слабой группе {color_ru} (finding_id={finding.finding_id}):\n"
        f"Камни группы: {coords}\n"
        f"weak_score={finding.weak_score}, own_certainty={finding.own_certainty}, "
        f"boundary_certainty={finding.boundary_certainty}, liberties={finding.liberties}, "
        f"confidence={finding.confidence}, turn_number={finding.turn_number}\n"
        f"rootInfo: winrate={analysis.rootInfo.winrate}, scoreLead={analysis.rootInfo.scoreLead}, "
        f"visits={analysis.rootInfo.visits}\n"
        "Объясни эту находку игроку через record_explanation."
    )
```

- [ ] **Step 2: Replace the moved code in `claude.py`, wiring it to the new module**

Replace the full contents of `backend/src/baduk_backend/llm/providers/claude.py` with:

```python
import os

import anthropic

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.prompts import (
    EXPLANATION_TOOL_DESCRIPTION,
    EXPLANATION_TOOL_NAME,
    EXPLANATION_TOOL_PARAMETERS,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from baduk_backend.llm.schemas import Explanation

DEFAULT_MODEL = "claude-sonnet-5"

_TOOL_SCHEMA = {
    "name": EXPLANATION_TOOL_NAME,
    "description": EXPLANATION_TOOL_DESCRIPTION,
    "input_schema": EXPLANATION_TOOL_PARAMETERS,
}


class ClaudeProvider:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None):
        self._client = client or anthropic.Anthropic(
            api_key=os.environ["BADUK_CLAUDE_API_KEY"], timeout=60.0
        )
        self._model = model or os.environ.get("BADUK_CLAUDE_MODEL", DEFAULT_MODEL)

    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> Explanation:
        user_content = build_user_prompt(finding, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            thinking={"type": "disabled"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": EXPLANATION_TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == EXPLANATION_TOOL_NAME:
                return Explanation.model_validate(block.input)
        raise RuntimeError("Claude did not call record_explanation")
```

Note: this is a pure refactor — external behavior (prompt text, schema shape, tool name) is byte-identical to before, only the source of truth moved. `xy_to_gtp` is no longer imported directly in `claude.py` since `build_user_prompt` (in `prompts.py`) now owns that call.

- [ ] **Step 3: Run the existing Claude provider tests to confirm the refactor didn't change behavior**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_claude_provider.py -v`
Expected: all 6 tests PASS, unchanged (this file is not edited in this task — it's the regression net proving the refactor preserved behavior byte-for-byte).

- [ ] **Step 4: Run the full non-integration suite to catch any other regression**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: all tests PASS (same count as before this task).

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/llm/prompts.py backend/src/baduk_backend/llm/providers/claude.py
git commit -m "refactor: extract shared LLM prompts/schema into llm/prompts.py"
```

---

### Task 2: `GeminiProvider` implementation + tests

**Files:**
- Create: `backend/src/baduk_backend/llm/providers/gemini.py`
- Create: `backend/tests/llm/test_gemini_provider.py`
- Modify: `backend/tests/test_api_explain_integration.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: `SYSTEM_PROMPT`, `EXPLANATION_TOOL_NAME`, `EXPLANATION_TOOL_DESCRIPTION`, `EXPLANATION_TOOL_PARAMETERS`, `build_user_prompt(...)` from `backend/src/baduk_backend/llm/prompts.py` (Task 1). `LLMProvider` Protocol shape from `backend/src/baduk_backend/llm/orchestrator.py` (unchanged, pre-existing).
- Produces (for Task 3 to consume): `backend/src/baduk_backend/llm/providers/gemini.py` exports a `GeminiProvider` class with the same public shape as `ClaudeProvider`: `__init__(self, client=None, model=None)`, `complete(self, finding, analysis, board_size, corrections=None) -> Explanation`. Also exports `DEFAULT_MODEL = "gemini-3.6-flash"`.

- [ ] **Step 1: Install `google-genai`**

```bash
cd backend
uv add google-genai
```

If `uv` isn't on `PATH` (known issue on this machine — see `README.md`), install directly into the venv instead and add the dependency line to `pyproject.toml` by hand in Step 2:

```powershell
.venv\Scripts\python.exe -m pip install google-genai
```

Verify either way with: `.venv\Scripts\python.exe -c "import google.genai; print('ok')"` — expect `ok` printed, no `ModuleNotFoundError`.

- [ ] **Step 2: Add the dependency to `pyproject.toml`**

In `backend/pyproject.toml`, add `"google-genai>=1.0.0",` to the `dependencies` list (after `"anthropic>=0.40.0",`):

```toml
dependencies = [
    "fastapi>=0.141.1",
    "uvicorn[standard]>=0.52.1",
    "anthropic>=0.40.0",
    "google-genai>=1.0.0",
]
```

(If `uv add` in Step 1 already added this line automatically, verify it matches this floor and move on — don't duplicate the entry.)

- [ ] **Step 3: Write the failing unit tests**

Create `backend/tests/llm/test_gemini_provider.py`:

```python
from types import SimpleNamespace

import pytest

from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
from baduk_backend.feature_extraction.schemas import Finding
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
    assert config.thinking_config.thinking_budget == 0


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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_gemini_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'baduk_backend.llm.providers.gemini'` (the module doesn't exist yet).

- [ ] **Step 5: Implement `GeminiProvider`**

Create `backend/src/baduk_backend/llm/providers/gemini.py`:

```python
import os

from google import genai
from google.genai import types

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.prompts import (
    EXPLANATION_TOOL_DESCRIPTION,
    EXPLANATION_TOOL_NAME,
    EXPLANATION_TOOL_PARAMETERS,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from baduk_backend.llm.schemas import Explanation

DEFAULT_MODEL = "gemini-3.6-flash"

_FUNCTION_DECLARATION = types.FunctionDeclaration(
    name=EXPLANATION_TOOL_NAME,
    description=EXPLANATION_TOOL_DESCRIPTION,
    parameters=EXPLANATION_TOOL_PARAMETERS,
)


class GeminiProvider:
    def __init__(self, client: genai.Client | None = None, model: str | None = None):
        self._client = client or genai.Client(
            api_key=os.environ["BADUK_GEMINI_API_KEY"],
            http_options=types.HttpOptions(timeout=60_000),
        )
        self._model = model or os.environ.get("BADUK_GEMINI_MODEL", DEFAULT_MODEL)

    def complete(
        self,
        finding: Finding,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> Explanation:
        user_content = build_user_prompt(finding, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        response = self._client.models.generate_content(
            model=self._model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(function_declarations=[_FUNCTION_DECLARATION])],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="ANY", allowed_function_names=[EXPLANATION_TOOL_NAME]
                    )
                ),
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        for call in response.function_calls or []:
            if call.name == EXPLANATION_TOOL_NAME:
                return Explanation.model_validate(call.args)
        raise RuntimeError("Gemini did not call record_explanation")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_gemini_provider.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 7: Add the self-skipping real-API integration test**

In `backend/tests/test_api_explain_integration.py`, add a second test after the existing `test_explain_with_real_claude_api` (keep `pytestmark = pytest.mark.integration` at module level as-is — it already covers both tests):

```python
def test_explain_with_real_gemini_api():
    if not os.environ.get("BADUK_GEMINI_API_KEY"):
        pytest.skip("BADUK_GEMINI_API_KEY not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import Finding
    from baduk_backend.llm.providers.gemini import GeminiProvider

    provider = GeminiProvider()
    finding = Finding(
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
```

- [ ] **Step 8: Run the full non-integration suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: all tests PASS (integration-marked tests are excluded by default per `pyproject.toml`'s `addopts = "-m \"not integration\""`, so the new Gemini integration test does not run here — that's expected, it's covered manually in Task 3's final check if a real key is available).

- [ ] **Step 9: Commit**

```bash
git add backend/src/baduk_backend/llm/providers/gemini.py backend/tests/llm/test_gemini_provider.py backend/tests/test_api_explain_integration.py backend/pyproject.toml
git commit -m "feat: add GeminiProvider implementing LLMProvider via google-genai"
```

---

### Task 3: Provider selection in `main.py`, docs, backlog note

**Files:**
- Modify: `backend/src/baduk_backend/main.py`
- Test: `backend/tests/test_main.py`
- Modify: `backend/README.md`
- Modify: `task_plan.md` (backlog section)

**Interfaces:**
- Consumes: `ClaudeProvider` (`backend/src/baduk_backend/llm/providers/claude.py`, pre-existing), `GeminiProvider` (`backend/src/baduk_backend/llm/providers/gemini.py`, Task 2).
- Produces: `_select_llm_provider(provider_name: str) -> LLMProvider` in `backend/src/baduk_backend/main.py` — a standalone, directly-testable function (extracted from `run()`, which itself is not unit-tested since it blocks on `uvicorn.run`). `LLMProvider` is imported at module level in `main.py` (it's a lightweight `Protocol` with no heavy dependencies, unlike the provider classes themselves — see Step 3, which keeps those imports deferred).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_main.py` (after the existing imports and tests — add `pytest` to the imports at the top: `import pytest` alongside the existing `import json` / `import socket`):

```python
def test_select_llm_provider_claude_requires_key(monkeypatch):
    monkeypatch.delenv("BADUK_CLAUDE_API_KEY", raising=False)

    from baduk_backend.main import _select_llm_provider

    with pytest.raises(RuntimeError, match="BADUK_CLAUDE_API_KEY"):
        _select_llm_provider("claude")


def test_select_llm_provider_claude_builds_claude_provider(monkeypatch):
    from baduk_backend.llm.providers.claude import ClaudeProvider
    from baduk_backend.main import _select_llm_provider

    monkeypatch.setenv("BADUK_CLAUDE_API_KEY", "test-key")
    provider = _select_llm_provider("claude")

    assert isinstance(provider, ClaudeProvider)


def test_select_llm_provider_gemini_requires_key(monkeypatch):
    monkeypatch.delenv("BADUK_GEMINI_API_KEY", raising=False)

    from baduk_backend.main import _select_llm_provider

    with pytest.raises(RuntimeError, match="BADUK_GEMINI_API_KEY"):
        _select_llm_provider("gemini")


def test_select_llm_provider_gemini_builds_gemini_provider(monkeypatch):
    from baduk_backend.llm.providers.gemini import GeminiProvider
    from baduk_backend.main import _select_llm_provider

    monkeypatch.setenv("BADUK_GEMINI_API_KEY", "test-key")
    provider = _select_llm_provider("gemini")

    assert isinstance(provider, GeminiProvider)


def test_select_llm_provider_rejects_unknown_value():
    from baduk_backend.main import _select_llm_provider

    with pytest.raises(RuntimeError, match="Unknown BADUK_LLM_PROVIDER"):
        _select_llm_provider("not-a-real-provider")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: all 5 new tests FAIL with `ImportError`/`AttributeError` (`_select_llm_provider` does not exist in `main.py` yet).

- [ ] **Step 3: Implement `_select_llm_provider` and wire it into `run()`**

In `backend/src/baduk_backend/main.py`, add `from baduk_backend.llm.orchestrator import LLMProvider` to the top-level imports (alongside the existing `from baduk_backend.engine_manager import EngineManager, build_katago_command`), then replace lines 66-90 (the current `run()` function) with:

```python
def _select_llm_provider(provider_name: str) -> LLMProvider:
    if provider_name == "claude":
        from baduk_backend.llm.providers.claude import ClaudeProvider

        if not os.environ.get("BADUK_CLAUDE_API_KEY"):
            raise RuntimeError(
                "BADUK_CLAUDE_API_KEY env var must be set when BADUK_LLM_PROVIDER=claude"
            )
        return ClaudeProvider()
    elif provider_name == "gemini":
        from baduk_backend.llm.providers.gemini import GeminiProvider

        if not os.environ.get("BADUK_GEMINI_API_KEY"):
            raise RuntimeError(
                "BADUK_GEMINI_API_KEY env var must be set when BADUK_LLM_PROVIDER=gemini "
                "(or unset BADUK_LLM_PROVIDER)"
            )
        return GeminiProvider()
    else:
        raise RuntimeError(
            f"Unknown BADUK_LLM_PROVIDER={provider_name!r}, expected 'claude' or 'gemini'"
        )


def run() -> None:
    import uvicorn

    llm_provider = _select_llm_provider(os.environ.get("BADUK_LLM_PROVIDER", "gemini"))

    engine_manager, config_path = _build_engine_manager()
    try:
        app.state.engine_manager = engine_manager
        app.state.engine_lock = asyncio.Lock()
        app.state.llm_provider = llm_provider

        port = _find_free_port()
        print(build_startup_message(port, AUTH_TOKEN), flush=True)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        engine_manager.stop()
        try:
            os.remove(config_path)
        except OSError:
            pass
```

Note: `_select_llm_provider` is called *before* `_build_engine_manager()` now (previously the Claude-key check ran before engine-manager construction too — this preserves that same fail-fast-before-spawning-KataGo ordering, just via the new function). The `from baduk_backend.llm.providers.claude import ClaudeProvider` top-level import that used to sit right before `run()`'s body is removed — both provider imports are now deferred inside `_select_llm_provider`'s branches, matching the existing lazy-import style already used for `uvicorn`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: all tests PASS, including the 5 new ones and the pre-existing 5.

- [ ] **Step 5: Run the full non-integration suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Update `backend/README.md`**

Replace the `## Running the real Claude API integration test` section through the end of `## Running the backend service` (currently lines 37-53) with:

```markdown
## Running the real LLM provider integration tests

`tests/test_api_explain_integration.py` (also gated by `-m integration`) calls
the real Claude and/or Gemini APIs. Each test self-skips if its provider's
API key isn't set:

```powershell
$env:BADUK_CLAUDE_API_KEY = "sk-ant-..."
$env:BADUK_GEMINI_API_KEY = "AIzaSy..."
uv run pytest -v -m integration
```

## Running the backend service

`baduk-backend` (the `run()` entry point in `main.py`) requires
`BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` (see above) plus an API key for
whichever LLM provider is active — it fails fast at startup if either is
missing, since `/api/explain` calls that provider's API.

`BADUK_LLM_PROVIDER` selects the active provider: `"claude"` or `"gemini"`
(defaults to `"gemini"` if unset). Depending on the value:
- `claude` — requires `BADUK_CLAUDE_API_KEY`. `BADUK_CLAUDE_MODEL` is
  optional and overrides the default model.
- `gemini` — requires `BADUK_GEMINI_API_KEY`. `BADUK_GEMINI_MODEL` is
  optional and overrides the default model.

Any other `BADUK_LLM_PROVIDER` value fails fast at startup with an error
naming the invalid value.
```

Also update the `## API` section's `/api/explain` bullet (currently ends with `Требует заголовок X-Auth-Token. 503, если вызов Claude API завершился ошибкой.`) to not name Claude unconditionally:

```markdown
- `POST /api/explain` — LLM-объяснение находки (`weak_group`) через активный
  провайдер (`BADUK_LLM_PROVIDER` — `claude` или `gemini`). Тело запроса и
  ответ — см. `ExplainRequest`/`ExplainResponse` в том же файле. Требует
  заголовок `X-Auth-Token`. `503`, если вызов провайдера завершился ошибкой.
```

- [ ] **Step 7: Update the `uv.lock` backlog note in `task_plan.md`**

In the root `task_plan.md`, find the existing backlog bullet about `uv` being missing from `PATH` and `backend/uv.lock` not being regenerated after adding `anthropic` (in the `## Будущие задачи (backlog)` section). Extend it to also mention `google-genai`:

Find this text (or the closest current wording — the bullet already exists from Phase 2's `anthropic` addition):
```
Нужно один раз запустить `uv lock`/`uv sync` там, где `uv` реально стоит, и закоммитить обновлённый `uv.lock`.
```

Replace it with:
```
Нужно один раз запустить `uv lock`/`uv sync` там, где `uv` реально стоит, и закоммитить обновлённый `uv.lock`. Тот же пробел теперь и у `google-genai` (добавлена для Gemini-провайдера, 2026-08-06) — `.venv` уже содержит обе зависимости, но `uv.lock` не отражает ни одну из них.
```

- [ ] **Step 8: Commit**

```bash
git add backend/src/baduk_backend/main.py backend/tests/test_main.py backend/README.md task_plan.md
git commit -m "feat: select LLM provider via BADUK_LLM_PROVIDER env var"
```

---

## Manual verification (after all tasks are complete)

If a real `BADUK_GEMINI_API_KEY` is available: run `cd backend && $env:BADUK_GEMINI_API_KEY = "..."; .venv\Scripts\python.exe -m pytest -v -m integration` and confirm `test_explain_with_real_gemini_api` passes with a real, non-empty explanation. Then start the backend with `BADUK_LLM_PROVIDER` unset (or `=gemini`) and confirm `/api/explain` returns a real Gemini-generated explanation end-to-end through the running service — this is the first real, non-mocked confirmation that Gemini's forced function-calling actually returns schema-conformant output from the live API, which no unit test (fake client) can prove.
