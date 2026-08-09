# llama Default Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the backend's default `BADUK_LLM_PROVIDER` from `"gemini"` to `"llama"`, and update every place that documents the current default.

**Architecture:** A single-line change to the default argument in `backend/src/baduk_backend/main.py::run()`'s call to `_select_llm_provider()`, plus matching prose updates in `backend/README.md`, `CLAUDE.md`, and `task_plan.md`. No other code changes — `_select_llm_provider()` itself, and the `ClaudeProvider`/`GeminiProvider`/`LlamaProvider` classes, are untouched.

**Tech Stack:** Python 3.12, FastAPI backend (`backend/`) — no new dependencies.

## Global Constraints

- Work happens only on branch `fix-llama-default-provider`, forked from `main`. Never commit directly to `main`.
- The only code change is the default-argument literal in `run()`'s call to `_select_llm_provider()`. Do not modify `_select_llm_provider()`'s branches, or any provider class.
- Existing tests in `backend/tests/test_main.py` are not modified — they call `_select_llm_provider(...)` with explicit values (`"claude"`, `"gemini"`, `"llama"`, or an invalid string) and never exercise `run()`'s default argument, since `run()` itself is not unit-tested (it blocks on `uvicorn.run`).
- Claude and Gemini provider code, and their selectability via `BADUK_LLM_PROVIDER=claude`/`BADUK_LLM_PROVIDER=gemini`, are not removed, disabled, or deprioritized in code — only the default value changes.

---

## Context for this task

**Current `backend/src/baduk_backend/main.py`** (relevant excerpt, lines 67-104 — `_select_llm_provider` is unchanged, only the `run()` call site changes):

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
        if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
            raise RuntimeError(
                "BADUK_LLAMA_MODEL_PATH env var must be set when BADUK_LLM_PROVIDER=llama"
            )
        from baduk_backend.llm.providers.llama import LlamaProvider

        return LlamaProvider()
    else:
        raise RuntimeError(
            f"Unknown BADUK_LLM_PROVIDER={provider_name!r}, expected 'claude', 'gemini', or 'llama'"
        )


def run() -> None:
    import uvicorn

    llm_provider = _select_llm_provider(os.environ.get("BADUK_LLM_PROVIDER", "gemini"))

    engine_manager, config_path = _build_engine_manager()
```

**Current `backend/README.md`** ("Running the backend service" section, relevant paragraph):

```markdown
`BADUK_LLM_PROVIDER` selects the active provider: `"claude"`, `"gemini"`,
or `"llama"` (defaults to `"gemini"` if unset). Depending on the value:
```

**Current `CLAUDE.md`** (lines 19-22, full text):

```markdown
.venv\Scripts\python.exe -m pytest -v -m integration  # реальный KataGo — требует BADUK_KATAGO_BINARY/BADUK_KATAGO_MODEL
                                                       # (тот же прогон также содержит два теста реальных LLM API — Claude требует BADUK_CLAUDE_API_KEY, Gemini — BADUK_GEMINI_API_KEY, каждый самостоятельно скипается без своего ключа)
```
Backend-сервис (`run()` в `main.py`) при старте требует `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` плюс API-ключ активного LLM-провайдера (fail-fast, `RuntimeError` без него) — используется эндпоинтом `/api/explain`. Провайдер выбирается через `BADUK_LLM_PROVIDER` (`"claude"` или `"gemini"`, по умолчанию `"gemini"`, если переменная не задана): для `claude` требуется `BADUK_CLAUDE_API_KEY` (опционально `BADUK_CLAUDE_MODEL` переопределяет модель), для `gemini` — `BADUK_GEMINI_API_KEY` (опционально `BADUK_GEMINI_MODEL`).
```

(Note: this text is already stale in two ways unrelated to the default-provider change — it doesn't mention `llama` at all, and only names "два теста" for the real-API integration suite when there are now three. Both gaps are fixed as part of this task since the paragraph is being edited anyway.)

---

### Task 1: Change the default provider and update its documentation

**Files:**
- Modify: `backend/src/baduk_backend/main.py:102`
- Modify: `backend/README.md` (the "Running the backend service" section)
- Modify: `CLAUDE.md` (lines 19-22)
- Modify: `task_plan.md` (two "Где мы сейчас" paragraphs + decisions log)

**Interfaces:** None — this task changes only a default literal and documentation prose, no function signatures.

- [ ] **Step 1: Change the default in `main.py`**

In `backend/src/baduk_backend/main.py`, change:

```python
    llm_provider = _select_llm_provider(os.environ.get("BADUK_LLM_PROVIDER", "gemini"))
```

to:

```python
    llm_provider = _select_llm_provider(os.environ.get("BADUK_LLM_PROVIDER", "llama"))
```

- [ ] **Step 2: Run the full non-integration test suite to confirm nothing broke**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: all tests PASS, same count as before this change (this literal isn't exercised by any existing unit test, so this run is a pure regression check, not a targeted verification).

- [ ] **Step 3: Update `backend/README.md`**

In the "Running the backend service" section, change:

```markdown
`BADUK_LLM_PROVIDER` selects the active provider: `"claude"`, `"gemini"`,
or `"llama"` (defaults to `"gemini"` if unset). Depending on the value:
```

to:

```markdown
`BADUK_LLM_PROVIDER` selects the active provider: `"claude"`, `"gemini"`,
or `"llama"` (defaults to `"llama"` if unset). Depending on the value:
```

- [ ] **Step 4: Update `CLAUDE.md`**

Replace lines 19-22 (the full block quoted in the Context section above) with:

```markdown
.venv\Scripts\python.exe -m pytest -v -m integration  # реальный KataGo — требует BADUK_KATAGO_BINARY/BADUK_KATAGO_MODEL
                                                       # (тот же прогон также содержит три теста реальных LLM API — Claude требует BADUK_CLAUDE_API_KEY, Gemini — BADUK_GEMINI_API_KEY, llama-cpp-python — BADUK_LLAMA_MODEL_PATH, каждый самостоятельно скипается без своего требования)
```
Backend-сервис (`run()` в `main.py`) при старте требует `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` плюс конфигурацию активного LLM-провайдера (fail-fast, `RuntimeError` без неё) — используется эндпоинтом `/api/explain`. Провайдер выбирается через `BADUK_LLM_PROVIDER` (`"claude"`, `"gemini"` или `"llama"`, по умолчанию `"llama"`, если переменная не задана): для `claude` требуется `BADUK_CLAUDE_API_KEY` (опционально `BADUK_CLAUDE_MODEL` переопределяет модель), для `gemini` — `BADUK_GEMINI_API_KEY` (опционально `BADUK_GEMINI_MODEL`), для `llama` — `BADUK_LLAMA_MODEL_PATH` (опционально `BADUK_LLAMA_N_GPU_LAYERS`).
```

- [ ] **Step 5: Update `task_plan.md`'s two "Где мы сейчас" paragraphs**

In the Gemini paragraph (starts with `**Gemini как второй LLM-провайдер — реализован, готов к мержу (не смёржен).**`), find this fragment:

```
Task 3 — `_select_llm_provider()` в `main.py` по `BADUK_LLM_PROVIDER` (дефолт `"gemini"` — намеренное решение пользователя, не `"claude"`), README/`CLAUDE.md` обновлены.
```

Replace it with:

```
Task 3 — `_select_llm_provider()` в `main.py` по `BADUK_LLM_PROVIDER` (дефолт на момент этой фичи — `"gemini"`, намеренное решение пользователя, не `"claude"`; дефолт сменился на `"llama"` позже в этой же сессии, см. ниже), README/`CLAUDE.md` обновлены.
```

In the llama-cpp-python paragraph (starts with `**llama-cpp-python как третий LLM-провайдер — реализован, готов к мержу (не смёржен).**`), find this fragment:

```
Дизайн-спек: `docs/superpowers/specs/2026-08-06-llama-cpp-provider-design.md` — третий провайдер наравне с Claude/Gemini (дефолт `BADUK_LLM_PROVIDER` НЕ меняется, остаётся `"gemini"`), grammar-constrained JSON
```

Replace it with:

```
Дизайн-спек: `docs/superpowers/specs/2026-08-06-llama-cpp-provider-design.md` — третий провайдер наравне с Claude/Gemini (дефолт `BADUK_LLM_PROVIDER` на момент этой фичи не менялся, оставался `"gemini"`; сменился на `"llama"` отдельной точечной задачей позже в этой же сессии, см. ниже), grammar-constrained JSON
```

- [ ] **Step 6: Add a decisions log entry to `task_plan.md`**

At the end of the `## Decisions log` section (after the last existing entry), add:

```markdown
- 2026-08-06 — Пользователь явно решил: llama-cpp-python (локальный, бесплатный, без лимитов запросов) становится основным LLM-решением проекта — та же исходная мотивация, что привела к добавлению обоих облачных провайдеров (платные API с ограничениями). Дефолт `BADUK_LLM_PROVIDER` сменён с `"gemini"` на `"llama"` в `main.py::run()`. Claude/Gemini код и выбор через `BADUK_LLM_PROVIDER=claude`/`BADUK_LLM_PROVIDER=gemini` осознанно оставлены нетронутыми — не в фокусе тестирования/разработки, но полностью рабочие. → `docs/superpowers/specs/2026-08-06-llama-default-provider-design.md`
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/baduk_backend/main.py backend/README.md CLAUDE.md task_plan.md
git commit -m "feat: make llama-cpp-python the default LLM provider"
```

---

## Manual verification (after the task is complete)

Start the backend with `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL`/`BADUK_LLAMA_MODEL_PATH` set and `BADUK_LLM_PROVIDER` left unset — confirm it starts successfully using the llama provider (no `RuntimeError` about a missing Claude/Gemini key). Then confirm `BADUK_LLM_PROVIDER=gemini` (with `BADUK_GEMINI_API_KEY` set) still starts successfully using Gemini, proving the non-default providers remain fully functional.
