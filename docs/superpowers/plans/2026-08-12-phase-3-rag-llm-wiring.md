# Phase 3 RAG-to-LLM Wiring (llama only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `LlamaProvider` (the project's default LLM provider) agentically decide whether to search the RAG knowledge base before explaining a finding, with a deterministic query, a two-branch `oneOf` grammar-constrained decision, and an anti-hallucination check on the resulting `doc_id` citation — with zero behavior change for Claude/Gemini or when RAG isn't installed/ingested.

**Architecture:** `LlamaProvider.complete()` makes one model call when RAG is unavailable (today's behavior, unchanged), or up to two when it is available: a decision call (`oneOf`-constrained: `retrieve_knowledge` vs. `record_explanation`), and — only if the model chose to search — a second, independent single-shot finalize call with the retrieved fragments folded into a freshly-built prompt (not a multi-turn conversation). `consistency.py` never trusts the provider's citation: it independently recomputes the valid `doc_id` set via the same deterministic query before accepting `rag_doc_id`.

**Tech Stack:** Python 3.12, existing `llama-cpp-python` grammar-constrained JSON (`response_format={"type":"json_object","schema":...}`), existing `retrieve_knowledge()` from the already-merged RAG ingestion slice. No new dependencies.

## Global Constraints

- Branch `phase-3-rag-llm-wiring`, forked from `main`. Never commit directly to `main`.
- `backend/src/baduk_backend/llm/providers/claude.py` and `backend/src/baduk_backend/llm/providers/gemini.py` are **not modified** in this plan, at all — RAG-as-tool for those providers is explicitly out of scope.
- No frontend changes.
- The RAG search query is built **deterministically** from `Finding` fields (`build_rag_query()`) — the model never writes the query text itself, only decides whether to search.
- At most **one** `retrieve_knowledge` hop per `complete()` call — after the model chooses to search, the second call is forced directly into the finalize-only schema, never back into the `oneOf` decision schema. This is a hard cap, not a configurable retry count.
- The second (post-search) call is a **fresh, independent single-shot call** — same `system` message, a **newly built** `user` message (original context + corrections if any + retrieved fragments). It does not echo the decision call's raw output as conversation history.
- `rag_doc_id` lives on `Explanation` (not on `Claim`) — one optional citation per explanation, not per numeric claim.
- `consistency.py` never trusts what the provider claims to have retrieved — it independently recomputes the valid `doc_id` set by calling `retrieve_knowledge()` itself with the same deterministic query, exactly mirroring the existing "recompute the true value, don't trust the provider" pattern already used for numeric `claims`.
- `chromadb`/`sentence_transformers` stay **lazily imported** (inside functions, never at module top level) everywhere new code touches them — `import baduk_backend` must never require the `[rag]` optional-dependency group.
- Three degradation cases must all leave `LlamaProvider` working exactly as it does today (single call, `EXPLANATION_TOOL_PARAMETERS` schema, no `rag_doc_id`): `[rag]` extra not installed; extra installed but `backend/rag_store/` doesn't exist (ingestion never run); extra installed and store exists, but the actual `retrieve_knowledge()` call fails unexpectedly mid-flow.
- Full spec: `docs/superpowers/specs/2026-08-12-phase-3-rag-llm-wiring-design.md`.

---

### Task 1: `Explanation.rag_doc_id` + prompt building blocks

**Files:**
- Modify: `backend/src/baduk_backend/llm/schemas.py`
- Modify: `backend/src/baduk_backend/llm/prompts.py`
- Create: `backend/tests/llm/test_schemas.py`
- Modify: `backend/tests/llm/test_prompts.py`

**Interfaces:**
- Produces: `Explanation(summary: str, claims: list[Claim], rag_doc_id: str | None = None)`; `build_rag_query(finding: Finding) -> str`; `RAG_SEARCH_INSTRUCTIONS: str`; `EXPLANATION_WITH_RAG_TOOL_PARAMETERS: dict`; `RAG_DECISION_TOOL_PARAMETERS: dict` — all importable from `baduk_backend.llm.schemas` / `baduk_backend.llm.prompts`. Tasks 2 and 3 import all of these directly.

- [ ] **Step 1: Write the failing test for `Explanation.rag_doc_id`**

Create `backend/tests/llm/test_schemas.py`:

```python
from baduk_backend.llm.schemas import Explanation


def test_explanation_rag_doc_id_defaults_to_none():
    explanation = Explanation(summary="...", claims=[])
    assert explanation.rag_doc_id is None


def test_explanation_rag_doc_id_can_be_set():
    explanation = Explanation(summary="...", claims=[], rag_doc_id="two-eyes-necessary")
    assert explanation.rag_doc_id == "two-eyes-necessary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_schemas.py -v`
Expected: FAIL — `AttributeError: 'Explanation' object has no attribute 'rag_doc_id'` on the first test.

- [ ] **Step 3: Add the field to `Explanation`**

In `backend/src/baduk_backend/llm/schemas.py`, the current `Explanation` class is:

```python
class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
```

Change it to:

```python
class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
    rag_doc_id: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_schemas.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing tests for `build_rag_query`**

Add to `backend/tests/llm/test_prompts.py` (the file already imports `MistakeFinding`, `WeakGroupFinding` — add `build_rag_query` to the existing `from baduk_backend.llm.prompts import (...)` block):

```python
def test_build_rag_query_for_weak_group():
    from baduk_backend.llm.prompts import build_rag_query

    finding = WeakGroupFinding(
        finding_id="f1",
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
    query = build_rag_query(finding)
    assert query == "слабая группа камней с недостатком глаз и территории"


def test_build_rag_query_for_mistake():
    from baduk_backend.llm.prompts import build_rag_query

    finding = MistakeFinding(
        finding_id="f2",
        turn_number=10,
        color="W",
        move="Q4",
        delta_score=3.0,
        stage="middlegame",
        severity="medium",
        confidence=0.6,
    )
    query = build_rag_query(finding)
    assert query == "ошибка хода, потеря очков на стадии middlegame"


def test_explanation_with_rag_tool_parameters_extends_base_schema():
    from baduk_backend.llm.prompts import EXPLANATION_TOOL_PARAMETERS, EXPLANATION_WITH_RAG_TOOL_PARAMETERS

    assert "summary" in EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert "claims" in EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert "rag_doc_id" in EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert EXPLANATION_WITH_RAG_TOOL_PARAMETERS["required"] == ["summary", "claims"]
    # extension, not a fork: the base schema's own claims/summary shape is untouched
    assert (
        EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"]["claims"]
        == EXPLANATION_TOOL_PARAMETERS["properties"]["claims"]
    )


def test_rag_decision_tool_parameters_has_two_branches():
    from baduk_backend.llm.prompts import RAG_DECISION_TOOL_PARAMETERS

    branches = RAG_DECISION_TOOL_PARAMETERS["oneOf"]
    assert len(branches) == 2
    tools = {branch["properties"]["tool"]["const"] for branch in branches}
    assert tools == {"retrieve_knowledge", "record_explanation"}
    search_branch = next(b for b in branches if b["properties"]["tool"]["const"] == "retrieve_knowledge")
    assert search_branch["required"] == ["tool"]
    finalize_branch = next(b for b in branches if b["properties"]["tool"]["const"] == "record_explanation")
    assert "rag_doc_id" in finalize_branch["properties"]
    assert set(finalize_branch["required"]) == {"tool", "summary", "claims"}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_rag_query'` (and similarly for the two new constants).

- [ ] **Step 7: Add the new building blocks to `prompts.py`**

In `backend/src/baduk_backend/llm/prompts.py`, append after the existing `EXPLANATION_TOOL_PARAMETERS` definition and before `build_user_prompt`:

```python
RAG_SEARCH_INSTRUCTIONS = """\
У тебя есть доступ к базе знаний Го через retrieve_knowledge. Если находка \
напоминает известный принцип или распространённую ошибку, поиск поможет дать \
более обоснованное объяснение. Если сомневаешься - лучше поискать. Если явной \
связи с базой знаний нет - отвечай record_explanation сразу, без поиска.
"""

EXPLANATION_WITH_RAG_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        **EXPLANATION_TOOL_PARAMETERS["properties"],  # summary, claims
        "rag_doc_id": {"type": ["string", "null"]},
    },
    "required": ["summary", "claims"],
}

RAG_DECISION_TOOL_PARAMETERS = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"tool": {"const": "retrieve_knowledge"}},
            "required": ["tool"],
        },
        {
            "type": "object",
            "properties": {
                "tool": {"const": "record_explanation"},
                **EXPLANATION_WITH_RAG_TOOL_PARAMETERS["properties"],
            },
            "required": ["tool", "summary", "claims"],
        },
    ]
}


def build_rag_query(finding: Finding) -> str:
    if finding.type == "weak_group":
        return "слабая группа камней с недостатком глаз и территории"
    return f"ошибка хода, потеря очков на стадии {finding.stage}"
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py tests/llm/test_schemas.py -v`
Expected: PASS (all tests).

- [ ] **Step 9: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, same count as before plus 6 new tests.

- [ ] **Step 10: Commit**

```bash
git add backend/src/baduk_backend/llm/schemas.py backend/src/baduk_backend/llm/prompts.py backend/tests/llm/test_schemas.py backend/tests/llm/test_prompts.py
git commit -m "feat: add Explanation.rag_doc_id and RAG decision/query prompt building blocks"
```

---

### Task 2: `consistency.py` — `rag_doc_id` anti-hallucination check

**Files:**
- Modify: `backend/src/baduk_backend/llm/consistency.py`
- Modify: `backend/tests/llm/test_consistency.py`

**Interfaces:**
- Consumes: `Explanation.rag_doc_id` (Task 1); `build_rag_query` (Task 1); `retrieve_knowledge` (already exists in `baduk_backend.rag.retrieval`, from the already-merged RAG ingestion slice).
- Produces: `verify_and_retry()`'s existing public signature is unchanged — `rag_doc_id` verification is folded into its existing internal `_is_verified`/corrections-building logic. No new public names Task 3 needs to import from here.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/llm/test_consistency.py` (the file already imports `Claim`, `Explanation` from `baduk_backend.llm.schemas` — no new top-level imports needed, the tests below import `RagSnippet` locally):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v`
Expected: 3 of the 4 new tests FAIL, 1 passes trivially (current code doesn't look at `rag_doc_id` at all, so anything not exercising the "should be rejected" path already behaves correctly by accident):
- `test_verify_and_retry_accepts_valid_rag_doc_id` — PASSES already (nothing to reject, current code's silence is indistinguishable from "verified").
- `test_verify_and_retry_rejects_hallucinated_rag_doc_id_then_retries` — FAILS: current code never retries, so `result.rag_doc_id` stays `"made-up-doc"` instead of becoming `"real-doc"`, and `provider.calls[1]` is `None` instead of a corrections list.
- `test_verify_and_retry_treats_rag_store_unavailable_as_invalid_citation` — FAILS: `result.rag_doc_id` stays `"anything"` instead of becoming `None`.
- `test_verify_and_retry_correction_does_not_mention_empty_claims_when_only_rag_doc_id_is_wrong` — FAILS (with an `IndexError`, not just a failed assertion): current code never retries, so `provider.calls[1]` is never populated and `provider.calls[1][0]` raises.

- [ ] **Step 3: Add the `rag_doc_id` check to `consistency.py`**

Current `backend/src/baduk_backend/llm/consistency.py` in full:

```python
from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.orchestrator import LLMProvider
from baduk_backend.llm.schemas import Claim, Explanation

MAX_CONSISTENCY_RETRIES = 2
FLOAT_TOLERANCE = 0.01

_FINDING_FIELDS: dict[str, set[str]] = {
    "weak_group": {"weak_score", "own_certainty", "boundary_certainty", "liberties"},
    "mistake": {"delta_score"},
}

_EMPTY_CLAIMS_CORRECTION = (
    "Твой ответ не содержит ни одного утверждения (claims), ссылающегося на конкретное число. "
    "Добавь хотя бы одно утверждение с точной ссылкой на поле и число из переданных данных."
)


def _true_value(field: str, finding: Finding, analysis: AnalyzeResponse) -> float | None:
    if field in _FINDING_FIELDS[finding.type]:
        return getattr(finding, field)
    return getattr(analysis.rootInfo, field, None)


def _claim_matches(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> bool:
    if claim.finding_id != finding.finding_id:
        return False
    true_value = _true_value(claim.cited_field, finding, analysis)
    if true_value is None:
        return False
    if claim.cited_field in ("liberties", "visits"):
        return int(claim.cited_number) == int(true_value)
    return abs(claim.cited_number - true_value) <= FLOAT_TOLERANCE


def _mismatches(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> list[Claim]:
    return [c for c in explanation.claims if not _claim_matches(c, finding, analysis)]


def _correction_message(claim: Claim, finding: Finding, analysis: AnalyzeResponse) -> str:
    if claim.finding_id != finding.finding_id:
        return (
            f'Ты сослался на находку с finding_id="{claim.finding_id}", но это утверждение должно '
            f'ссылаться на текущую находку с finding_id="{finding.finding_id}". Исправь finding_id.'
        )
    true_value = _true_value(claim.cited_field, finding, analysis)
    if true_value is None:
        return (
            f'Поле "{claim.cited_field}" не относится к находке типа "{finding.type}" - '
            "убери это утверждение или сошлись на подходящем поле из переданных данных."
        )
    return (
        f'Ты сослался на число {claim.cited_number} для поля "{claim.cited_field}", '
        f"но настоящее значение - {true_value}. Используй точное число или убери это утверждение."
    )


def _fallback_explanation(finding: Finding) -> Explanation:
    if finding.type == "weak_group":
        summary = (
            f"Обнаружена слабая группа (ход {finding.turn_number}): "
            f"показатель уязвимости {finding.weak_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        )
    else:
        summary = (
            f"Обнаружена потеря очков на ходе {finding.turn_number}: "
            f"Δ={finding.delta_score:.2f}, уверенность {finding.confidence:.2f}. "
            "Не удалось получить проверенное текстовое объяснение - "
            "эти числа стоит свериться с ходами-кандидатами вручную."
        )
    return Explanation(summary=summary, claims=[])


def _is_verified(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> bool:
    # An explanation with zero claims makes no checkable assertions at all -
    # treat it the same as a numeric mismatch rather than trivially passing,
    # otherwise citation-based verification is defeated by simply omitting
    # claims. `_fallback_explanation` legitimately returns claims=[] too, but
    # that value is only ever constructed and returned directly as the final
    # result below - it never flows back through this check.
    return bool(explanation.claims) and not _mismatches(explanation, finding, analysis)


def verify_and_retry(
    provider: LLMProvider, finding: Finding, analysis: AnalyzeResponse, board_size: int
) -> tuple[Explanation, bool]:
    explanation = provider.complete(finding, analysis, board_size)
    for _ in range(MAX_CONSISTENCY_RETRIES):
        if _is_verified(explanation, finding, analysis):
            return explanation, True
        mismatches = _mismatches(explanation, finding, analysis)
        corrections = (
            [_correction_message(c, finding, analysis) for c in mismatches]
            if mismatches
            else [_EMPTY_CLAIMS_CORRECTION]
        )
        explanation = provider.complete(finding, analysis, board_size, corrections=corrections)
    if _is_verified(explanation, finding, analysis):
        return explanation, True
    return _fallback_explanation(finding), False
```

Replace the `_is_verified` function and everything from `verify_and_retry` onward with:

```python
def _rag_doc_id_valid(rag_doc_id: str | None, finding: Finding) -> bool:
    if rag_doc_id is None:
        return True
    from baduk_backend.llm.prompts import build_rag_query
    from baduk_backend.rag.retrieval import retrieve_knowledge

    query = build_rag_query(finding)
    try:
        snippets = retrieve_knowledge(query, top_k=3)
    except (RuntimeError, ImportError):
        return False
    return rag_doc_id in {s.doc_id for s in snippets}


def _rag_doc_id_correction_message(rag_doc_id: str | None) -> str:
    return (
        f'Ты сослался на doc_id="{rag_doc_id}", которого не было среди найденных материалов - '
        "убери цитату или используй настоящий doc_id."
    )


def _is_verified(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> bool:
    # An explanation with zero claims makes no checkable assertions at all -
    # treat it the same as a numeric mismatch rather than trivially passing,
    # otherwise citation-based verification is defeated by simply omitting
    # claims. `_fallback_explanation` legitimately returns claims=[] too, but
    # that value is only ever constructed and returned directly as the final
    # result below - it never flows back through this check.
    return (
        bool(explanation.claims)
        and not _mismatches(explanation, finding, analysis)
        and _rag_doc_id_valid(explanation.rag_doc_id, finding)
    )


def _build_corrections(explanation: Explanation, finding: Finding, analysis: AnalyzeResponse) -> list[str]:
    if not explanation.claims:
        corrections = [_EMPTY_CLAIMS_CORRECTION]
    else:
        corrections = [
            _correction_message(c, finding, analysis)
            for c in _mismatches(explanation, finding, analysis)
        ]
    if not _rag_doc_id_valid(explanation.rag_doc_id, finding):
        corrections.append(_rag_doc_id_correction_message(explanation.rag_doc_id))
    return corrections


def verify_and_retry(
    provider: LLMProvider, finding: Finding, analysis: AnalyzeResponse, board_size: int
) -> tuple[Explanation, bool]:
    explanation = provider.complete(finding, analysis, board_size)
    for _ in range(MAX_CONSISTENCY_RETRIES):
        if _is_verified(explanation, finding, analysis):
            return explanation, True
        corrections = _build_corrections(explanation, finding, analysis)
        explanation = provider.complete(finding, analysis, board_size, corrections=corrections)
    if _is_verified(explanation, finding, analysis):
        return explanation, True
    return _fallback_explanation(finding), False
```

Note: `build_rag_query`/`retrieve_knowledge` are imported **inside** `_rag_doc_id_valid`, not at module top level — `retrieve_knowledge` transitively touches `chromadb`/`sentence_transformers` (lazily, inside its own call chain), and this file must stay importable without the `[rag]` optional-dependency group installed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v`
Expected: PASS (all tests, including the pre-existing ones — the corrections-building refactor must not change any existing test's outcome).

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, same count as before plus 4 new tests.

- [ ] **Step 6: Commit**

```bash
git add backend/src/baduk_backend/llm/consistency.py backend/tests/llm/test_consistency.py
git commit -m "feat: verify rag_doc_id citations against an independently recomputed doc_id set"
```

---

### Task 3: `llama.py` — agentic RAG decision flow

**Files:**
- Modify: `backend/src/baduk_backend/llm/providers/llama.py`
- Modify: `backend/tests/llm/test_llama_provider.py`

**Interfaces:**
- Consumes: `EXPLANATION_WITH_RAG_TOOL_PARAMETERS`, `RAG_DECISION_TOOL_PARAMETERS`, `RAG_SEARCH_INSTRUCTIONS`, `build_rag_query` (Task 1); `retrieve_knowledge`, `RagSnippet`, `DEFAULT_STORE_PATH` (already exist in `baduk_backend.rag.retrieval` / `baduk_backend.rag.schemas` / `baduk_backend.rag.store`, from the already-merged RAG ingestion slice).
- Produces: `LlamaProvider.complete()`'s public signature is unchanged. New module-level helpers importable from `baduk_backend.llm.providers.llama` for direct testing: `_rag_available() -> bool`, `_format_snippets(snippets: list[RagSnippet]) -> str`. Task 4 only calls `LlamaProvider.complete()` — it does not need any of these helpers directly.

- [ ] **Step 1: Add the autouse fixture that isolates existing tests from local `rag_store/` state**

At the top of `backend/tests/llm/test_llama_provider.py`, right after the module-level imports (`pytest.importorskip("llama_cpp")` etc.) and before the first test function, add:

```python
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
```

This step alone requires no implementation change yet (the function doesn't exist), so don't run tests after this step in isolation — proceed to Step 2 first.

- [ ] **Step 2: Write the failing tests for the new agentic flow**

Add to `backend/tests/llm/test_llama_provider.py`:

```python
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
    from baduk_backend.llm.providers.llama import _rag_available

    monkeypatch.setattr("baduk_backend.rag.store.DEFAULT_STORE_PATH", tmp_path / "does_not_exist")

    assert _rag_available() is False


def test_rag_available_returns_true_when_installed_and_store_exists(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    pytest.importorskip("sentence_transformers")
    from baduk_backend.llm.providers.llama import _rag_available

    store_path = tmp_path / "rag_store"
    store_path.mkdir()
    monkeypatch.setattr("baduk_backend.rag.store.DEFAULT_STORE_PATH", store_path)

    assert _rag_available() is True
```

Also modify the existing `_FakeLlama` class (currently accepts a single fixed `response`) to support returning a different response per call, needed by the two-call tests above:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_llama_provider.py -v`
Expected: most of the new tests FAIL, for two different reasons:
- `test_llama_provider_without_rag_available_uses_original_single_call_schema` — PASSES already (today's `complete()` already does exactly one call with `EXPLANATION_TOOL_PARAMETERS`; this test documents/protects that behavior going forward, it doesn't need Step 4 to pass yet).
- Every other new test — FAILS with `AttributeError: <module 'baduk_backend.llm.providers.llama'> has no attribute '_rag_available'` (from `monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", ...)`, which errors if the target attribute doesn't already exist) or `ImportError`/`AttributeError` on `_format_snippets`/`_rag_available` direct imports — none of these names exist until Step 4.

- [ ] **Step 4: Rewrite `llama.py`**

Current `backend/src/baduk_backend/llm/providers/llama.py` in full:

```python
from __future__ import annotations

import json
import os
import threading

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
        if llm is not None:
            self._llm = llm
        else:
            n_gpu_layers_raw = os.environ.get("BADUK_LLAMA_N_GPU_LAYERS", str(DEFAULT_N_GPU_LAYERS))
            try:
                n_gpu_layers = int(n_gpu_layers_raw)
            except ValueError as exc:
                raise ValueError(
                    f"BADUK_LLAMA_N_GPU_LAYERS must be an integer, got {n_gpu_layers_raw!r}"
                ) from exc

            self._llm = llama_cpp.Llama(
                model_path=os.environ["BADUK_LLAMA_MODEL_PATH"],
                n_gpu_layers=n_gpu_layers,
                n_ctx=DEFAULT_N_CTX,
                verbose=False,
            )
        self._lock = threading.Lock()

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

        with self._lock:
            response = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object", "schema": EXPLANATION_TOOL_PARAMETERS},
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        finish_reason = response["choices"][0].get("finish_reason")
        content = response["choices"][0]["message"]["content"]
        if not content:
            raise RuntimeError(
                f"Llama did not produce structured output (finish_reason={finish_reason!r})"
            )
        try:
            return Explanation.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                f"Llama did not produce valid structured output "
                f"(finish_reason={finish_reason!r}, content={content[:200]!r})"
            ) from exc
```

Replace it in full with:

```python
from __future__ import annotations

import json
import os
import threading

import llama_cpp
from pydantic import ValidationError

from baduk_backend.api.schemas import AnalyzeResponse
from baduk_backend.feature_extraction.schemas import Finding
from baduk_backend.llm.prompts import (
    EXPLANATION_TOOL_PARAMETERS,
    EXPLANATION_WITH_RAG_TOOL_PARAMETERS,
    RAG_DECISION_TOOL_PARAMETERS,
    RAG_SEARCH_INSTRUCTIONS,
    SYSTEM_PROMPT,
    build_rag_query,
    build_user_prompt,
)
from baduk_backend.llm.schemas import Explanation
from baduk_backend.rag.schemas import RagSnippet

DEFAULT_N_GPU_LAYERS = -1
DEFAULT_N_CTX = 8192
DEFAULT_MAX_TOKENS = 2048
RAG_TOP_K = 3


def _rag_available() -> bool:
    try:
        import chromadb  # noqa: F401
        import sentence_transformers  # noqa: F401
        from baduk_backend.rag.store import DEFAULT_STORE_PATH
    except ImportError:
        return False
    return DEFAULT_STORE_PATH.exists()


def _format_snippets(snippets: list[RagSnippet]) -> str:
    if not snippets:
        return "Поиск по базе знаний не дал результатов."
    parts = ["Найденные материалы из базы знаний Го:"]
    for snippet in snippets:
        parts.append(
            f'doc_id="{snippet.doc_id}", "{snippet.title}" ({snippet.source}):\n{snippet.text_snippet}'
        )
    return "\n\n".join(parts)


def _extract_json(choice: dict) -> dict:
    finish_reason = choice.get("finish_reason")
    content = choice["message"]["content"]
    if not content:
        raise RuntimeError(
            f"Llama did not produce structured output (finish_reason={finish_reason!r})"
        )
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Llama did not produce valid structured output "
            f"(finish_reason={finish_reason!r}, content={content[:200]!r})"
        ) from exc


def _validate_explanation(data: dict) -> Explanation:
    try:
        return Explanation.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(
            f"Llama did not produce valid structured output (content={data!r})"
        ) from exc


class LlamaProvider:
    def __init__(self, llm: llama_cpp.Llama | None = None):
        if llm is not None:
            self._llm = llm
        else:
            n_gpu_layers_raw = os.environ.get("BADUK_LLAMA_N_GPU_LAYERS", str(DEFAULT_N_GPU_LAYERS))
            try:
                n_gpu_layers = int(n_gpu_layers_raw)
            except ValueError as exc:
                raise ValueError(
                    f"BADUK_LLAMA_N_GPU_LAYERS must be an integer, got {n_gpu_layers_raw!r}"
                ) from exc

            self._llm = llama_cpp.Llama(
                model_path=os.environ["BADUK_LLAMA_MODEL_PATH"],
                n_gpu_layers=n_gpu_layers,
                n_ctx=DEFAULT_N_CTX,
                verbose=False,
            )
        self._lock = threading.Lock()

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

        if not _rag_available():
            choice = self._call(SYSTEM_PROMPT, user_content, EXPLANATION_TOOL_PARAMETERS)
            return _validate_explanation(_extract_json(choice))

        system_prompt = SYSTEM_PROMPT + "\n" + RAG_SEARCH_INSTRUCTIONS
        decision_choice = self._call(system_prompt, user_content, RAG_DECISION_TOOL_PARAMETERS)
        decision = _extract_json(decision_choice)

        if decision.get("tool") != "retrieve_knowledge":
            decision.pop("tool", None)
            return _validate_explanation(decision)

        from baduk_backend.rag.retrieval import retrieve_knowledge

        try:
            snippets = retrieve_knowledge(build_rag_query(finding), top_k=RAG_TOP_K)
        except (RuntimeError, ImportError):
            snippets = []

        final_user_content = user_content + "\n\n" + _format_snippets(snippets)
        final_choice = self._call(system_prompt, final_user_content, EXPLANATION_WITH_RAG_TOOL_PARAMETERS)
        return _validate_explanation(_extract_json(final_choice))

    def _call(self, system_prompt: str, user_content: str, schema: dict) -> dict:
        with self._lock:
            response = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object", "schema": schema},
                max_tokens=DEFAULT_MAX_TOKENS,
            )
        return response["choices"][0]
```

Note the mid-flow `except (RuntimeError, ImportError)`: `RuntimeError` covers `retrieve_knowledge()`'s own "store not found" error (a race between `_rag_available()`'s check and this call), `ImportError` covers the — currently unreachable via this exact call path, but defensive — case where `chromadb`/`sentence_transformers` become unimportable between the two checks. Both degrade to "search returned nothing" rather than crashing the whole `/api/explain` request.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_llama_provider.py -v`
Expected: PASS (all tests — the 10 pre-existing tests plus 9 new ones).

- [ ] **Step 6: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, same count as before plus 9 new tests (Task 1's 6 + Task 2's 4 + this task's 9 = 19 new tests total by this point, on top of the 131 already on `main`).

- [ ] **Step 7: Commit**

```bash
git add backend/src/baduk_backend/llm/providers/llama.py backend/tests/llm/test_llama_provider.py
git commit -m "feat: agentic RAG search decision in LlamaProvider (oneOf decision schema, single search hop)"
```

---

### Task 4: Real end-to-end integration test

**Files:**
- Modify: `backend/tests/test_api_explain_integration.py`

**Interfaces:**
- Consumes: `LlamaProvider` (Task 3), `DEFAULT_STORE_PATH` (already exists in `baduk_backend.rag.store`). Nothing later depends on this task — it's the last one.

- [ ] **Step 1: Write the new integration test**

Add to `backend/tests/test_api_explain_integration.py`, after the existing `test_explain_with_real_llama` function:

```python
def test_explain_with_real_llama_and_rag():
    if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
        pytest.skip("BADUK_LLAMA_MODEL_PATH not set")

    from baduk_backend.rag.store import DEFAULT_STORE_PATH

    if not DEFAULT_STORE_PATH.exists():
        pytest.skip(
            "backend/rag_store/ not found - run ingestion first: python -m baduk_backend.rag.ingest"
        )

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.feature_extraction.schemas import WeakGroupFinding
    from baduk_backend.llm.providers.llama import LlamaProvider

    provider = LlamaProvider()
    finding = WeakGroupFinding(
        finding_id="f_test",
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
    # The model may legitimately decide this specific finding doesn't need a
    # search - only assert the citation is well-formed when one was made.
    if explanation.rag_doc_id is not None:
        assert isinstance(explanation.rag_doc_id, str)
        assert explanation.rag_doc_id != ""
```

- [ ] **Step 2: Run to verify it self-skips cleanly on this machine's default state**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_explain_integration.py -v -m integration`
Expected: the new test shows `SKIPPED` (reason depends on whether `BADUK_LLAMA_MODEL_PATH` is set in this shell — if it is, from an earlier session, but `backend/rag_store/` doesn't exist, it should skip with the ingestion-reminder message; if `backend/rag_store/` does exist from the earlier live-verification run in this same repo, and `BADUK_LLAMA_MODEL_PATH` is also set, it will actually run against the real model - either outcome is acceptable evidence the skip logic works, since the goal of this step is confirming no crash / no unconditional skip due to a bug, not a specific skip reason).

- [ ] **Step 3: Run the full non-integration backend suite to confirm no regressions**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, same count as Task 3's end state (the new test is `@pytest.mark.integration`-marked via the file's module-level `pytestmark`, deselected by default `addopts`).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_api_explain_integration.py
git commit -m "test: add real end-to-end integration test for llama RAG search decision"
```

---

## Manual verification (after the plan is complete)

With both `BADUK_LLAMA_MODEL_PATH` and a real, ingested `backend/rag_store/` present:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests/test_api_explain_integration.py::test_explain_with_real_llama_and_rag -v -m integration
```

Expected: passes, and manually inspecting the test's printed output (or adding a temporary `print(explanation)`) should show the model at least sometimes choosing to search for a finding that plausibly matches a real knowledge-base card (e.g. the same `weak_group` finding used in `test_explain_with_real_llama`), with `rag_doc_id` set to a real `doc_id` when it does.
