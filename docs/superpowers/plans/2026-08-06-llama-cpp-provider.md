# llama-cpp-python LLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local GGUF-model inference via `llama-cpp-python` as a third, selectable LLM provider for `/api/explain`, alongside the existing Claude and Gemini cloud providers.

**Architecture:** A new `LlamaProvider` class implements the existing `LLMProvider` Protocol (`backend/src/baduk_backend/llm/orchestrator.py`, unchanged) using `llama_cpp.Llama`'s grammar-constrained JSON output (`response_format={"type": "json_object", "schema": ...}`) — the local-inference equivalent of Claude's/Gemini's forced tool-use. It reuses the shared `SYSTEM_PROMPT`/`build_user_prompt`/`EXPLANATION_TOOL_PARAMETERS` from `llm/prompts.py` unchanged. `main.py::_select_llm_provider()` gains a third `"llama"` branch; the default (`"gemini"`) does not change.

**Tech Stack:** Python 3.12, FastAPI backend (`backend/`), `llama-cpp-python>=0.3.34` (verified against this exact version's source on GitHub — see Context section), existing `anthropic`/`google-genai`, `pytest`.

## Global Constraints

- Work happens only on branch `phase-2-llama-provider`, forked from `main`. Never commit directly to `main`.
- TDD: write the failing test first, verify it fails, then implement, then verify it passes.
- No hardcoded model/binary paths in source code — only via `BADUK_LLAMA_MODEL_PATH`. Placeholder paths (e.g. `C:/path/to/model.gguf`) may appear only in README command examples, never in `.py` files.
- Unit tests must NOT require a real GGUF model file, GPU, or network — only the self-skipping integration test (gated on `BADUK_LLAMA_MODEL_PATH` being set) does real inference.
- `main.py`'s default `BADUK_LLM_PROVIDER` stays `"gemini"` — this task does not change it.
- Do not modify `llm/orchestrator.py` or `llm/consistency.py` — both are provider-agnostic and out of scope.
- This machine's `uv` is sometimes missing from `PATH` (a known, already-documented issue). Additionally — specific to `llama-cpp-python` — a plain `pip install llama-cpp-python` without a matching prebuilt wheel falls back to building from source, which failed on this exact machine during design research with a Windows long-path error (`OSError: [Errno 2] No such file or directory` deep in `vendor/llama.cpp/...`, `pip`'s own hint: enable Windows Long Path support). Task 2's install step documents the prebuilt-CUDA-wheel install path as the primary route specifically because it sidesteps this failure entirely (no source build needed), with the long-path fix as an explicit fallback only if no matching wheel exists.

---

## Context for every task

**Current `backend/src/baduk_backend/llm/providers/gemini.py`** (full file, for structural reference — `LlamaProvider` follows the same shape):

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
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            ),
        )
        for call in response.function_calls or []:
            if call.name == EXPLANATION_TOOL_NAME and call.args:
                return Explanation.model_validate(call.args)
        raise RuntimeError("Gemini did not call record_explanation")
```

**`llm/prompts.py`** (unchanged by this plan, full exports used by `LlamaProvider`):
- `SYSTEM_PROMPT: str`
- `EXPLANATION_TOOL_PARAMETERS: dict` (JSON-schema-shaped: `type`/`properties`/`items`/`enum`/`required` keys)
- `build_user_prompt(finding: Finding, analysis: AnalyzeResponse, board_size: int) -> str`

(`EXPLANATION_TOOL_NAME`/`EXPLANATION_TOOL_DESCRIPTION` also exist but are Claude/Gemini-specific "tool" framing — not needed for `LlamaProvider`, which doesn't use tool-calling.)

**`LLMProvider` Protocol** (`backend/src/baduk_backend/llm/orchestrator.py`, unchanged):
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

**Verified `llama-cpp-python` v0.3.34 API** (read directly from `raw.githubusercontent.com/abetlen/llama-cpp-python/v0.3.34/llama_cpp/llama.py` and `llama_types.py` during planning — do not rely on memory or older docs, this library's API has shifted across versions):
- `Llama.__init__(self, model_path: str, *, n_gpu_layers: int = 0, n_ctx: int = 512, verbose: bool = True, chat_format: Optional[str] = None, ...)`. `model_path` is required. **`n_gpu_layers` defaults to `0` in the library itself** — our code must pass an explicit value (`-1` = offload all layers to GPU) or the model silently runs on CPU only. **`n_ctx` defaults to `512`**, far too small for this project's system prompt + user prompt + JSON-schema grammar overhead + response — our code passes `8192` explicitly. `chat_format=None` lets the library auto-detect the chat template from the GGUF file's own embedded metadata (Qwen3 GGUF files carry their own template) — do not hardcode a chat format string. `verbose` defaults to `True` (spams stdout) — pass `False` explicitly.
- `create_chat_completion(self, messages: List[ChatCompletionRequestMessage], response_format: Optional[ChatCompletionRequestResponseFormat] = None, max_tokens: Optional[int] = None, ...) -> CreateChatCompletionResponse`. `messages` is a plain list of dicts: `{"role": "system"|"user"|"assistant", "content": "..."}` (confirmed from the library's own docstring example). `max_tokens` defaults to `None` (unbounded) — our code passes `2048` explicitly.
- `ChatCompletionRequestResponseFormat` (`TypedDict`): `{"type": Literal["text", "json_object"], "schema": NotRequired[JsonType]}`. Our code passes exactly `{"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS}` — note the key is `"schema"`, not `"json_schema"`.
- Response shape (`CreateChatCompletionResponse`, a `TypedDict`): `response["choices"][0]["message"]["content"]`, where `content: Optional[str]` — **can be `None`**, our code must check before `json.loads`.
- The module is imported as `import llama_cpp` and called as `llama_cpp.Llama(...)` (module-qualified access, not `from llama_cpp import Llama`) — this matches the existing codebase's own pattern (`claude.py` does `import anthropic; anthropic.Anthropic(...)`, `gemini.py` does `from google import genai; genai.Client(...)`) and is required for the unit tests to be able to `monkeypatch.setattr("llama_cpp.Llama", ...)` and have it take effect — patching a module attribute only works if the calling code looks it up through the module at call time, not if it imported the name directly into its own namespace.

---

### Task 1: `LlamaProvider` implementation + tests

**Files:**
- Create: `backend/src/baduk_backend/llm/providers/llama.py`
- Create: `backend/tests/llm/test_llama_provider.py`
- Modify: `backend/tests/test_api_explain_integration.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: `SYSTEM_PROMPT`, `EXPLANATION_TOOL_PARAMETERS`, `build_user_prompt(...)` from `backend/src/baduk_backend/llm/prompts.py` (pre-existing, unchanged). `LLMProvider` Protocol shape (pre-existing, unchanged).
- Produces (for Task 2 to consume): `backend/src/baduk_backend/llm/providers/llama.py` exports a `LlamaProvider` class: `__init__(self, llm: llama_cpp.Llama | None = None)`, `complete(self, finding, analysis, board_size, corrections=None) -> Explanation`.

- [ ] **Step 1: Install `llama-cpp-python`**

The primary route uses a prebuilt CUDA wheel (this also sidesteps a known Windows long-path build failure — see Global Constraints):

```powershell
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

(Replace `cu124` with whichever CUDA version matches your installed CUDA Toolkit — `cu118`, `cu121`, `cu122`, `cu123`, `cu124`, `cu125`, `cu130`, or `cu132` are available. Check your CUDA version with `nvidia-smi` if unsure.)

If `uv` is on `PATH`, the equivalent is:
```bash
uv add llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

If no prebuilt wheel matches your platform/Python version, `pip` falls back to building from source — on Windows this can fail with an error like `OSError: [Errno 2] No such file or directory` deep inside a path under `vendor/llama.cpp/...`, because the build's file paths exceed Windows' default 260-character path limit. If you hit this, enable Windows Long Path support first (see `https://pip.pypa.io/warnings/enable-long-paths` for the registry/group-policy steps pip itself prints in the error), then retry. A source build also requires the NVIDIA CUDA Toolkit and Visual Studio Build Tools ("Desktop development with C++" workload) installed, with `CMAKE_ARGS="-DGGML_CUDA=on"` and `FORCE_CMAKE=1` set before running `pip install llama-cpp-python`.

Verify with: `python -c "import llama_cpp; print('ok')"` — expect `ok` printed, no `ModuleNotFoundError`. This step only installs the package for local testing/verification — for unit tests (Step 3 onward) no GPU or real model file is needed at all, since they use a fake object instead of a real `Llama` instance.

- [ ] **Step 2: Add the dependency to `pyproject.toml`**

In `backend/pyproject.toml`, add `"llama-cpp-python>=0.3.34",` to the `dependencies` list (after `"google-genai>=1.0.0",`):

```toml
dependencies = [
    "fastapi>=0.141.1",
    "uvicorn[standard]>=0.52.1",
    "anthropic>=0.40.0",
    "google-genai>=1.0.0",
    "llama-cpp-python>=0.3.34",
]
```

- [ ] **Step 3: Write the failing unit tests**

Create `backend/tests/llm/test_llama_provider.py`:

```python
import json

import pytest

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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_llama_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'baduk_backend.llm.providers.llama'` (the module doesn't exist yet).

- [ ] **Step 5: Implement `LlamaProvider`**

Create `backend/src/baduk_backend/llm/providers/llama.py`:

```python
import json
import os

import llama_cpp
from pydantic import ValidationError

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.prompts import EXPLANATION_TOOL_PARAMETERS, SYSTEM_PROMPT, build_user_prompt
from baduk_backend.llm.schemas import Explanation

DEFAULT_N_GPU_LAYERS = -1
DEFAULT_N_CTX = 8192
DEFAULT_MAX_TOKENS = 2048


class LlamaProvider:
    def __init__(self, llm: llama_cpp.Llama | None = None):
        self._llm = llm or llama_cpp.Llama(
            model_path=os.environ["BADUK_LLAMA_MODEL_PATH"],
            n_gpu_layers=int(os.environ.get("BADUK_LLAMA_N_GPU_LAYERS", DEFAULT_N_GPU_LAYERS)),
            n_ctx=DEFAULT_N_CTX,
            verbose=False,
        )

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

        response = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS},
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        content = response["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError("Llama did not produce structured output")
        try:
            return Explanation.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError("Llama did not produce valid structured output") from exc
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_llama_provider.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 7: Add the self-skipping real-model integration test**

In `backend/tests/test_api_explain_integration.py`, add a third test after the existing `test_explain_with_real_gemini_api` (keep the module-level `pytestmark = pytest.mark.integration` as-is — it already covers all three tests):

```python
def test_explain_with_real_llama():
    if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
        pytest.skip("BADUK_LLAMA_MODEL_PATH not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import Finding
    from baduk_backend.llm.providers.llama import LlamaProvider

    provider = LlamaProvider()
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
Expected: all tests PASS (the new `test_explain_with_real_llama` is integration-marked, excluded by default per `pyproject.toml`'s `addopts = "-m \"not integration\""` — it does not run here, that's expected).

- [ ] **Step 9: Commit**

```bash
git add backend/src/baduk_backend/llm/providers/llama.py backend/tests/llm/test_llama_provider.py backend/tests/test_api_explain_integration.py backend/pyproject.toml
git commit -m "feat: add LlamaProvider implementing LLMProvider via llama-cpp-python"
```

---

### Task 2: Provider selection wiring + docs

**Files:**
- Modify: `backend/src/baduk_backend/main.py`
- Test: `backend/tests/test_main.py`
- Modify: `backend/README.md`
- Modify: `task_plan.md` (backlog section)

**Interfaces:**
- Consumes: `LlamaProvider` (`backend/src/baduk_backend/llm/providers/llama.py`, Task 1). `_select_llm_provider(provider_name: str) -> LLMProvider` (pre-existing, `backend/src/baduk_backend/main.py`).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_main.py` (after the existing `test_select_llm_provider_rejects_unknown_value` test):

```python
def test_select_llm_provider_llama_requires_model_path(monkeypatch):
    monkeypatch.delenv("BADUK_LLAMA_MODEL_PATH", raising=False)

    from baduk_backend.main import _select_llm_provider

    with pytest.raises(RuntimeError, match="BADUK_LLAMA_MODEL_PATH"):
        _select_llm_provider("llama")


def test_select_llm_provider_llama_builds_llama_provider(monkeypatch):
    from baduk_backend.main import _select_llm_provider

    monkeypatch.setattr("llama_cpp.Llama", lambda **kwargs: object())
    monkeypatch.setenv("BADUK_LLAMA_MODEL_PATH", "/path/to/model.gguf")

    from baduk_backend.llm.providers.llama import LlamaProvider

    provider = _select_llm_provider("llama")

    assert isinstance(provider, LlamaProvider)
```

Note: the second test patches `llama_cpp.Llama` with a stub that returns a plain `object()` (not a real `Llama` instance) so `LlamaProvider()`'s constructor doesn't try to load a real GGUF file — this is the same technique `test_llama_provider_constructs_llama_with_env_config` uses in Task 1's test file, applied here at the `_select_llm_provider` integration point instead.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: the 2 new tests FAIL — `_select_llm_provider("llama")` currently falls through to the `else` branch and raises `RuntimeError("Unknown BADUK_LLM_PROVIDER='llama', expected 'claude' or 'gemini'")`, which does not match `"BADUK_LLAMA_MODEL_PATH"` for the first test, and the second test's `isinstance` check fails since no `LlamaProvider` is ever constructed.

- [ ] **Step 3: Add the `"llama"` branch to `_select_llm_provider`**

In `backend/src/baduk_backend/main.py`, the current function reads:

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
```

Replace it with:

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
    elif provider_name == "llama":
        from baduk_backend.llm.providers.llama import LlamaProvider

        if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
            raise RuntimeError(
                "BADUK_LLAMA_MODEL_PATH env var must be set when BADUK_LLM_PROVIDER=llama"
            )
        return LlamaProvider()
    else:
        raise RuntimeError(
            f"Unknown BADUK_LLM_PROVIDER={provider_name!r}, expected 'claude', 'gemini', or 'llama'"
        )
```

(The default in `run()` — `os.environ.get("BADUK_LLM_PROVIDER", "gemini")` — is unchanged; this task does not touch that line.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_main.py -v`
Expected: all tests PASS, including the 2 new ones.

- [ ] **Step 5: Run the full non-integration suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Update `backend/README.md`**

Replace the `## Running the real LLM provider integration tests` section through the end of `## Running the backend service` (currently the section starting at `` `tests/test_api_explain_integration.py` (also gated by `-m integration`) calls `` and ending at `Any other `BADUK_LLM_PROVIDER` value fails fast at startup with an error naming the invalid value.`) with:

```markdown
## Running the real LLM provider integration tests

`tests/test_api_explain_integration.py` (also gated by `-m integration`) calls
the real Claude and/or Gemini APIs, or runs real local inference via
`llama-cpp-python`. Each test self-skips if its provider isn't configured:

```powershell
$env:BADUK_CLAUDE_API_KEY = "sk-ant-..."
$env:BADUK_GEMINI_API_KEY = "AIzaSy..."
$env:BADUK_LLAMA_MODEL_PATH = "C:/models/Qwen3-8B-Q4_K_M.gguf"
uv run pytest -v -m integration
```

## Setting up the local llama-cpp-python provider (optional)

This provider runs a GGUF-format model locally via `llama-cpp-python`,
avoiding cloud API costs and rate limits, at the cost of needing a
compatible GPU and a heavier install than the cloud providers.

**Recommended model:** `Qwen3-8B-Instruct`, `Q4_K_M` quantization (~5 GB) —
strong Russian-language quality, fits comfortably in 8 GB VRAM. Download
`Qwen3-8B-Q4_K_M.gguf` from `unsloth/Qwen3-8B-GGUF` on Hugging Face and
place it anywhere on disk — the exact location is up to you, set it via
`BADUK_LLAMA_MODEL_PATH` (see below).

**Installing `llama-cpp-python` with CUDA support (NVIDIA GPUs):** the
primary route is a prebuilt CUDA wheel:

```powershell
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

Replace `cu124` with whichever CUDA version matches your installed CUDA
Toolkit (check with `nvidia-smi`) — `cu118`, `cu121`, `cu122`, `cu123`,
`cu124`, `cu125`, `cu130`, and `cu132` are available.

If no prebuilt wheel matches your platform/Python version, `pip` falls back
to building from source. On Windows this can fail with a long-path error
(`OSError: [Errno 2] No such file or directory` under a path containing
`vendor/llama.cpp/...`) — if you hit this, enable Windows Long Path support
first (registry/group-policy steps are printed in the error itself, or see
`https://pip.pypa.io/warnings/enable-long-paths`), then retry. A source
build also requires the NVIDIA CUDA Toolkit and Visual Studio Build Tools
("Desktop development with C++" workload), with `CMAKE_ARGS="-DGGML_CUDA=on"`
and `FORCE_CMAKE=1` set before running `pip install llama-cpp-python`.

## Running the backend service

`baduk-backend` (the `run()` entry point in `main.py`) requires
`BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` (see above) plus configuration
for whichever LLM provider is active — it fails fast at startup if either
is missing, since `/api/explain` calls that provider.

`BADUK_LLM_PROVIDER` selects the active provider: `"claude"`, `"gemini"`,
or `"llama"` (defaults to `"gemini"` if unset). Depending on the value:
- `claude` — requires `BADUK_CLAUDE_API_KEY`. `BADUK_CLAUDE_MODEL` is
  optional and overrides the default model.
- `gemini` — requires `BADUK_GEMINI_API_KEY`. `BADUK_GEMINI_MODEL` is
  optional and overrides the default model.
- `llama` — requires `BADUK_LLAMA_MODEL_PATH` (absolute path to a `.gguf`
  model file — see "Setting up the local llama-cpp-python provider" above).
  `BADUK_LLAMA_N_GPU_LAYERS` is optional (defaults to `-1`, offloading all
  layers to GPU) — lower it if the model doesn't fit in your VRAM.

Any other `BADUK_LLM_PROVIDER` value fails fast at startup with an error
naming the invalid value.
```

Then update the `## API` section's `/api/explain` bullet (currently ends with `Требует заголовок X-Auth-Token. 503, если вызов провайдера завершился ошибкой.` and lists only `claude`/`gemini`) to:

```markdown
- `POST /api/explain` — LLM-объяснение находки (`weak_group`) через активный
  провайдер (`BADUK_LLM_PROVIDER` — `claude`, `gemini` или `llama`). Тело
  запроса и ответ — см. `ExplainRequest`/`ExplainResponse` в том же файле.
  Требует заголовок `X-Auth-Token`. `503`, если вызов провайдера завершился
  ошибкой.
```

- [ ] **Step 7: Update the `uv.lock` backlog note in `task_plan.md`**

In the root `task_plan.md`, find the existing backlog bullet about `uv` being missing from `PATH` and `backend/uv.lock` not reflecting `anthropic`/`google-genai` (in the `## Будущие задачи (backlog)` section — it currently ends with a sentence added when `google-genai` was added). Extend it to also mention `llama-cpp-python`:

Find this text (or the closest current wording):
```
Тот же пробел теперь и у `google-genai` (добавлена для Gemini-провайдера, 2026-08-06) — `.venv` уже содержит обе зависимости, но `uv.lock` не отражает ни одну из них.
```

Replace it with:
```
Тот же пробел теперь и у `google-genai` (добавлена для Gemini-провайдера, 2026-08-06) и `llama-cpp-python` (добавлена для локального llama.cpp-провайдера, 2026-08-06) — `uv.lock` не отражает ни одну из трёх зависимостей.
```

- [ ] **Step 8: Commit**

```bash
git add backend/src/baduk_backend/main.py backend/tests/test_main.py backend/README.md task_plan.md
git commit -m "feat: select llama-cpp-python via BADUK_LLM_PROVIDER=llama"
```

---

## Manual verification (after both tasks are complete)

If a real GGUF model file is available locally (e.g. the recommended `Qwen3-8B-Q4_K_M.gguf`) and `llama-cpp-python` is installed with a working CUDA build: run `cd backend && $env:BADUK_LLAMA_MODEL_PATH = "C:/path/to/model.gguf"; .venv\Scripts\python.exe -m pytest -v -m integration` and confirm `test_explain_with_real_llama` passes with a real, non-empty explanation generated entirely locally (check GPU utilization during the test run to confirm the model actually offloaded to GPU, not silently falling back to CPU-only — this is the one thing no unit test with a fake object can catch). Then start the backend with `BADUK_LLM_PROVIDER=llama` and confirm `/api/explain` returns a real locally-generated explanation end-to-end through the running service.
