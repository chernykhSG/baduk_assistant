# Free-Form LLM Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /api/ask` — a single-shot, open-text question about the current board position, answered by the `llama` LLM provider with the same structured-output + post-hoc numeric consistency-checking anti-hallucination guarantee the three existing detector-triggered explanation flows already have, plus a matching UI block in `LlmExplanationPanel`.

**Architecture:** A new, parallel (not reused) set of types/functions mirrors the existing `Finding`-based explanation pipeline (`Claim`/`Explanation`/`verify_and_retry`/`LlamaProvider.complete`) one level down: `QuestionClaim`/`QuestionAnswer`/`verify_question_and_retry`/`LlamaProvider.answer_question`. Claims cite either the position's `rootInfo` or a specific candidate move from `moveInfos` (via a new `cited_move` field), instead of a `finding_id`. The new provider method is NOT added to the shared `LLMProvider` Protocol — the endpoint gates on `hasattr(provider, "answer_question")` (structural, matches this codebase's existing duck-typing style) rather than importing the concrete `LlamaProvider` class, keeping `llama_cpp` an optional import exactly like every other file in `api/`.

**Tech Stack:** Python 3.12 / Pydantic v2 / FastAPI (backend, unchanged), Preact/TypeScript (frontend, unchanged). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-18-phase-2-free-form-questions-design.md`

## Global Constraints

- Only the `llama` provider implements question-answering in this slice. `claude`/`gemini` are untouched — no changes to `llm/orchestrator.py`'s `LLMProvider` Protocol, `llm/providers/claude.py`, or `llm/providers/gemini.py`.
- **Deviation from the spec's literal `api/ask.py` sketch, found while grounding this plan in the actual code — see "Note on provider gating" below:** the endpoint gates on `hasattr(provider, "answer_question")`, not `isinstance(provider, LlamaProvider)`. Importing the concrete `LlamaProvider` class into `api/ask.py` or `llm/consistency.py` at module level would force an unconditional `import llama_cpp` (a heavy, environment-specific dependency) into code paths that must keep working when the active provider is `claude`/`gemini` and `llama_cpp` isn't installed — exactly the failure this codebase already avoids everywhere else (`main.py`'s `_select_llm_provider` imports `LlamaProvider` only inside its own `elif` branch; `api/explain.py` only ever imports the `LLMProvider` Protocol, never a concrete class). `hasattr` achieves the same runtime gate without that import, and is consistent with the Protocol-based (structural) typing this whole LLM layer already uses.
- No new environment variables. `BADUK_LLAMA_MODEL_PATH`/`BADUK_LLAMA_N_GPU_LAYERS` already exist and are unchanged.
- Zero changes to any existing test file: `backend/tests/llm/test_consistency.py`, `backend/tests/llm/test_prompts.py`, `backend/tests/llm/test_llama_provider.py`, `backend/tests/llm/test_schemas.py`, `backend/tests/test_api_explain.py`, `backend/tests/test_api_explain_integration.py`, `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`. Every task in this plan only ADDS new test functions to these files (or adds new files) — no existing test's body changes.
- `QuestionClaim.cited_field` is a `Literal["winrate", "scoreLead", "visits", "prior"]` type alias (`QuestionCitedField`), mirroring the existing `Claim.cited_field: CitedField` pattern in `llm/schemas.py` — not a bare `str`.
- **Deviation from the spec's literal `build_ask_user_prompt` description, found while grounding this plan in the actual code:** `analysis.moveInfos[i].move` is already a GTP-format string (e.g. `"Q4"`) straight from KataGo — it is NOT the raw `(x, y)` grid-index tuple that `Finding.stones` uses (that's the one field `xy_to_gtp()` exists to convert). `weak_group.py`'s `_pv_focus()` already relies on this (`gtp_to_xy(move_info.move, ...)` converts FROM the GTP string). `build_ask_user_prompt` therefore uses `move_info.move` directly — no coordinate conversion, no `xy_to_gtp` import.

---

### Task 1: `QuestionAnswer` schemas + consistency checker

**Files:**
- Modify: `backend/src/baduk_backend/llm/schemas.py`
- Modify: `backend/src/baduk_backend/llm/consistency.py`
- Test: `backend/tests/llm/test_schemas.py` (add tests, do not change existing ones)
- Test: `backend/tests/llm/test_consistency.py` (add tests, do not change existing ones)

**Interfaces:**
- Consumes: `AnalyzeResponse`/`RootInfo`/`MoveInfo` (existing, `baduk_backend.api.schemas`).
- Produces: `QuestionCitedField`, `QuestionClaim`, `QuestionAnswer` (all in `llm/schemas.py`); `verify_question_and_retry(provider: _AskProvider, question: str, analysis: AnalyzeResponse, board_size: int) -> tuple[QuestionAnswer, bool]` (in `llm/consistency.py`) — Task 3 (the llama provider) and Task 4 (the endpoint) both call this by name. `_AskProvider` is a local `Protocol` in `consistency.py` requiring one method: `answer_question(self, question: str, analysis: AnalyzeResponse, board_size: int, corrections: list[str] | None = None) -> QuestionAnswer`.

Current `llm/schemas.py` (read before writing your diff — do not guess at the surrounding content):

```python
from typing import Literal

from pydantic import BaseModel

CitedField = Literal[
    "weak_score",
    "own_certainty",
    "boundary_certainty",
    "liberties",
    "delta_score",
    "visits",
    "winrate",
    "scoreLead",
]


class Claim(BaseModel):
    text: str
    finding_id: str
    cited_field: CitedField
    cited_number: float


class Explanation(BaseModel):
    summary: str
    claims: list[Claim]
    rag_doc_id: str | None = None
```

- [ ] **Step 1: Write the failing tests for the new schemas**

Append to `backend/tests/llm/test_schemas.py`:

```python
from baduk_backend.llm.schemas import QuestionAnswer, QuestionClaim


def test_question_claim_cited_move_defaults_to_none():
    claim = QuestionClaim(cited_field="winrate", cited_number=0.6)
    assert claim.cited_move is None


def test_question_claim_can_cite_a_specific_move():
    claim = QuestionClaim(cited_field="prior", cited_number=0.3, cited_move="Q4")
    assert claim.cited_move == "Q4"


def test_question_answer_rag_doc_id_defaults_to_none():
    answer = QuestionAnswer(answer="...", claims=[])
    assert answer.rag_doc_id is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'QuestionAnswer'` (and `QuestionClaim`).

- [ ] **Step 3: Add `QuestionCitedField`/`QuestionClaim`/`QuestionAnswer` to `llm/schemas.py`**

Append to `backend/src/baduk_backend/llm/schemas.py` (leave the existing `CitedField`/`Claim`/`Explanation` above untouched):

```python
QuestionCitedField = Literal["winrate", "scoreLead", "visits", "prior"]


class QuestionClaim(BaseModel):
    cited_field: QuestionCitedField
    cited_number: float
    # None -> the claim cites analysis.rootInfo (the position's overall
    # evaluation). A GTP move string (e.g. "Q4") -> the claim cites the
    # matching entry in analysis.moveInfos (a specific candidate move).
    cited_move: str | None = None


class QuestionAnswer(BaseModel):
    answer: str
    claims: list[QuestionClaim]
    rag_doc_id: str | None = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_schemas.py -v`
Expected: PASS (all 5 tests — 2 pre-existing + 3 new).

- [ ] **Step 5: Write the failing tests for `verify_question_and_retry`**

Append to `backend/tests/llm/test_consistency.py` (the existing file already imports `AnalyzeResponse`/`RootInfo` at the top — reuse those, don't re-import):

```python
from baduk_backend.llm.consistency import verify_question_and_retry
from baduk_backend.llm.schemas import QuestionAnswer, QuestionClaim


class _RecordingFakeAskProvider:
    def __init__(self, responses: list[QuestionAnswer]):
        self._responses = list(responses)
        self.calls: list[list[str] | None] = []

    def answer_question(self, question, analysis, board_size, corrections=None):
        self.calls.append(corrections)
        return self._responses.pop(0)


def _analysis_with_move() -> AnalyzeResponse:
    from baduk_backend.api.schemas import MoveInfo

    return AnalyzeResponse(
        id="x",
        moveInfos=[MoveInfo(move="Q4", winrate=0.55, scoreLead=1.5, visits=300, prior=0.2, pv=["Q4"])],
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[0.0] * 81,
    )


def test_verify_question_and_retry_accepts_correct_rootinfo_claim_on_first_try():
    answer = QuestionAnswer(
        answer="...", claims=[QuestionClaim(cited_field="winrate", cited_number=0.5)]
    )
    provider = _RecordingFakeAskProvider([answer])

    result, verified = verify_question_and_retry(provider, "какой сейчас winrate?", _analysis(), 9)

    assert verified is True
    assert result == answer
    assert provider.calls == [None]


def test_verify_question_and_retry_accepts_correct_move_specific_claim():
    answer = QuestionAnswer(
        answer="...",
        claims=[QuestionClaim(cited_field="prior", cited_number=0.2, cited_move="Q4")],
    )
    provider = _RecordingFakeAskProvider([answer])

    result, verified = verify_question_and_retry(
        provider, "насколько силён ход Q4?", _analysis_with_move(), 9
    )

    assert verified is True
    assert result == answer


def test_verify_question_and_retry_rejects_claim_citing_a_move_not_in_moveinfos_then_retries():
    bad = QuestionAnswer(
        answer="...",
        claims=[QuestionClaim(cited_field="prior", cited_number=0.2, cited_move="C3")],
    )
    good = QuestionAnswer(
        answer="...", claims=[QuestionClaim(cited_field="winrate", cited_number=0.5)]
    )
    provider = _RecordingFakeAskProvider([bad, good])

    result, verified = verify_question_and_retry(provider, "вопрос", _analysis(), 9)

    assert verified is True
    assert result == good
    assert provider.calls[0] is None
    assert provider.calls[1] is not None
    assert "prior" in provider.calls[1][0]


def test_verify_question_and_retry_retries_on_wrong_number_then_succeeds():
    bad = QuestionAnswer(
        answer="...", claims=[QuestionClaim(cited_field="winrate", cited_number=0.1)]
    )
    good = QuestionAnswer(
        answer="...", claims=[QuestionClaim(cited_field="winrate", cited_number=0.5)]
    )
    provider = _RecordingFakeAskProvider([bad, good])

    result, verified = verify_question_and_retry(provider, "вопрос", _analysis(), 9)

    assert verified is True
    assert result == good
    assert "winrate" in provider.calls[1][0]


def test_verify_question_and_retry_rejects_empty_claims_list():
    empty = QuestionAnswer(answer="...", claims=[])
    good = QuestionAnswer(
        answer="...", claims=[QuestionClaim(cited_field="winrate", cited_number=0.5)]
    )
    provider = _RecordingFakeAskProvider([empty, good])

    result, verified = verify_question_and_retry(provider, "вопрос", _analysis(), 9)

    assert verified is True
    assert result == good


def test_verify_question_and_retry_falls_back_after_exhausting_retries():
    bad = QuestionAnswer(
        answer="...", claims=[QuestionClaim(cited_field="winrate", cited_number=0.1)]
    )
    provider = _RecordingFakeAskProvider([bad, bad, bad])

    result, verified = verify_question_and_retry(provider, "вопрос", _analysis(), 9)

    assert verified is False
    assert result.claims == []
    # The fallback is a verbatim dump of rootInfo, not a hallucinated template
    # referencing a Finding (there is no Finding here).
    assert "0.5" in result.answer
    assert "не удалось" in result.answer.lower()


def test_verify_question_and_retry_accepts_valid_rag_doc_id(monkeypatch):
    from baduk_backend.rag.schemas import RagSnippet

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        assert query == "какой сейчас winrate?"
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

    answer = QuestionAnswer(
        answer="...",
        claims=[QuestionClaim(cited_field="winrate", cited_number=0.5)],
        rag_doc_id="two-eyes-necessary",
    )
    provider = _RecordingFakeAskProvider([answer])

    result, verified = verify_question_and_retry(provider, "какой сейчас winrate?", _analysis(), 9)

    assert verified is True
    assert result.rag_doc_id == "two-eyes-necessary"


def test_verify_question_and_retry_rejects_hallucinated_rag_doc_id_then_retries(monkeypatch):
    from baduk_backend.rag.schemas import RagSnippet

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        return [
            RagSnippet(
                doc_id="real-doc", title="...", source="...", text_snippet="...", relevance_score=0.9
            )
        ]

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    bad = QuestionAnswer(
        answer="...",
        claims=[QuestionClaim(cited_field="winrate", cited_number=0.5)],
        rag_doc_id="made-up-doc",
    )
    good = QuestionAnswer(
        answer="...",
        claims=[QuestionClaim(cited_field="winrate", cited_number=0.5)],
        rag_doc_id="real-doc",
    )
    provider = _RecordingFakeAskProvider([bad, good])

    result, verified = verify_question_and_retry(provider, "вопрос", _analysis(), 9)

    assert verified is True
    assert result.rag_doc_id == "real-doc"
    assert "made-up-doc" in provider.calls[1][0]
```

Note: `_analysis()` above is the existing module-level helper already defined at the top of `test_consistency.py` (returns `AnalyzeResponse` with `moveInfos=[]`) — reuse it as-is for the root-info-only cases; the new `_analysis_with_move()` helper is only needed for the `cited_move` cases.

- [ ] **Step 6: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v -k question`
Expected: FAIL — `ImportError: cannot import name 'verify_question_and_retry'`.

- [ ] **Step 7: Add `verify_question_and_retry` and its helpers to `llm/consistency.py`**

Current `llm/consistency.py` (read before writing your diff): it has module-level `MAX_CONSISTENCY_RETRIES = 2`, `FLOAT_TOLERANCE = 0.01`, `_FINDING_FIELDS`, `_EMPTY_CLAIMS_CORRECTION`, and the functions `_true_value`/`_claim_matches`/`_mismatches`/`_correction_message`/`_fallback_explanation`/`_rag_doc_id_valid`/`_rag_doc_id_correction_message`/`_is_verified`/`_build_corrections`/`verify_and_retry` — leave every one of those untouched. Add the following at the end of the file. First, add `Protocol` to the existing `typing` import at the top — the file currently has no `typing` import at all (it only imports from `baduk_backend.*`), so add a new line:

```python
from typing import Protocol
```

Then, also add the new schema imports to the existing `from baduk_backend.llm.schemas import Claim, Explanation` line, changing it to:

```python
from baduk_backend.llm.schemas import Claim, Explanation, QuestionAnswer, QuestionClaim
```

Then append at the end of the file:

```python
class _AskProvider(Protocol):
    def answer_question(
        self,
        question: str,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> QuestionAnswer: ...


def _question_true_value(claim: QuestionClaim, analysis: AnalyzeResponse) -> float | None:
    if claim.cited_move is None:
        return getattr(analysis.rootInfo, claim.cited_field, None)
    for move_info in analysis.moveInfos:
        if move_info.move == claim.cited_move:
            return getattr(move_info, claim.cited_field, None)
    return None


def _question_claim_matches(claim: QuestionClaim, analysis: AnalyzeResponse) -> bool:
    true_value = _question_true_value(claim, analysis)
    if true_value is None:
        return False
    if claim.cited_field == "visits":
        return int(claim.cited_number) == int(true_value)
    return abs(claim.cited_number - true_value) <= FLOAT_TOLERANCE


def _question_mismatches(answer: QuestionAnswer, analysis: AnalyzeResponse) -> list[QuestionClaim]:
    return [c for c in answer.claims if not _question_claim_matches(c, analysis)]


def _question_correction_message(claim: QuestionClaim, analysis: AnalyzeResponse) -> str:
    true_value = _question_true_value(claim, analysis)
    if true_value is None:
        move_part = f' хода "{claim.cited_move}"' if claim.cited_move else " текущей позиции"
        return (
            f'Поле "{claim.cited_field}" не найдено для{move_part} - '
            "убери это утверждение или сошлись на подходящем поле из переданных данных."
        )
    return (
        f'Ты сослался на число {claim.cited_number} для поля "{claim.cited_field}", '
        f"но настоящее значение - {true_value}. Используй точное число или убери это утверждение."
    )


def _fallback_answer(analysis: AnalyzeResponse) -> QuestionAnswer:
    answer = (
        "Не удалось получить проверенный ответ на этот вопрос. "
        f"Точные данные текущей позиции: winrate={analysis.rootInfo.winrate:.2f}, "
        f"scoreLead={analysis.rootInfo.scoreLead:.2f}, visits={analysis.rootInfo.visits}. "
        "Эти числа - напрямую из анализа KataGo; содержательный текстовый ответ "
        "на ваш вопрос проверить не удалось."
    )
    return QuestionAnswer(answer=answer, claims=[])


def _question_rag_doc_id_valid(rag_doc_id: str | None, question: str) -> bool:
    if rag_doc_id is None:
        return True
    from baduk_backend.llm.prompts import RAG_TOP_K
    from baduk_backend.rag.retrieval import retrieve_knowledge

    try:
        snippets = retrieve_knowledge(question, top_k=RAG_TOP_K)
    except (RuntimeError, ImportError):
        return False
    return rag_doc_id in {s.doc_id for s in snippets}


def _question_rag_doc_id_correction_message(rag_doc_id: str | None) -> str:
    return (
        f'Ты сослался на doc_id="{rag_doc_id}", которого не было среди найденных материалов - '
        "убери цитату или используй настоящий doc_id."
    )


def _is_question_verified(answer: QuestionAnswer, analysis: AnalyzeResponse, rag_doc_id_ok: bool) -> bool:
    return bool(answer.claims) and not _question_mismatches(answer, analysis) and rag_doc_id_ok


def _build_question_corrections(
    answer: QuestionAnswer, analysis: AnalyzeResponse, rag_doc_id_ok: bool
) -> list[str]:
    if not answer.claims:
        corrections = [_EMPTY_CLAIMS_CORRECTION]
    else:
        corrections = [
            _question_correction_message(c, analysis) for c in _question_mismatches(answer, analysis)
        ]
    if not rag_doc_id_ok:
        corrections.append(_question_rag_doc_id_correction_message(answer.rag_doc_id))
    return corrections


def verify_question_and_retry(
    provider: _AskProvider, question: str, analysis: AnalyzeResponse, board_size: int
) -> tuple[QuestionAnswer, bool]:
    answer = provider.answer_question(question, analysis, board_size)
    for _ in range(MAX_CONSISTENCY_RETRIES):
        rag_doc_id_ok = _question_rag_doc_id_valid(answer.rag_doc_id, question)
        if _is_question_verified(answer, analysis, rag_doc_id_ok):
            return answer, True
        corrections = _build_question_corrections(answer, analysis, rag_doc_id_ok)
        answer = provider.answer_question(question, analysis, board_size, corrections=corrections)
    rag_doc_id_ok = _question_rag_doc_id_valid(answer.rag_doc_id, question)
    if _is_question_verified(answer, analysis, rag_doc_id_ok):
        return answer, True
    return _fallback_answer(analysis), False
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_consistency.py -v`
Expected: PASS (all tests — the full pre-existing set plus the 8 new `question`-prefixed ones).

- [ ] **Step 9: Run the full backend test suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS — every pre-existing test, unchanged.

- [ ] **Step 10: Commit**

```bash
git add backend/src/baduk_backend/llm/schemas.py backend/src/baduk_backend/llm/consistency.py backend/tests/llm/test_schemas.py backend/tests/llm/test_consistency.py
git commit -m "feat: add QuestionAnswer schema and consistency checker for free-form questions"
```

---

### Task 2: Prompts for the ask flow

**Files:**
- Modify: `backend/src/baduk_backend/llm/prompts.py`
- Test: `backend/tests/llm/test_prompts.py` (add tests, do not change existing ones)

**Interfaces:**
- Consumes: `AnalyzeResponse`/`RootInfo`/`MoveInfo` (existing, `baduk_backend.api.schemas`).
- Produces: `ASK_SYSTEM_PROMPT: str`, `ANSWER_TOOL_PARAMETERS: dict`, `ANSWER_WITH_RAG_TOOL_PARAMETERS: dict`, `ASK_DECISION_TOOL_PARAMETERS: dict`, `build_ask_user_prompt(question: str, analysis: AnalyzeResponse, board_size: int) -> str` (all in `llm/prompts.py`) — Task 3 (`llama.py`) imports and uses all five by name.

Current `llm/prompts.py` (read before writing your diff) already has `SYSTEM_PROMPT`, `EXPLANATION_TOOL_NAME`/`EXPLANATION_TOOL_DESCRIPTION`/`EXPLANATION_TOOL_PARAMETERS`, `RAG_SEARCH_INSTRUCTIONS`, `EXPLANATION_WITH_RAG_TOOL_PARAMETERS`, `RAG_DECISION_TOOL_PARAMETERS`, `RAG_TOP_K = 3`, `build_rag_query(finding)`, `build_user_prompt(finding, analysis, board_size)`. Leave every one of those untouched. `RAG_SEARCH_INSTRUCTIONS` and `RAG_TOP_K` are reused as-is by the new code (Task 3) — do not duplicate them.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/llm/test_prompts.py`:

```python
from baduk_backend.api.schemas import MoveInfo
from baduk_backend.llm.prompts import (
    ANSWER_TOOL_PARAMETERS,
    ANSWER_WITH_RAG_TOOL_PARAMETERS,
    ASK_DECISION_TOOL_PARAMETERS,
    build_ask_user_prompt,
)


def _analysis_with_moves() -> AnalyzeResponse:
    return AnalyzeResponse(
        id="x",
        moveInfos=[
            MoveInfo(move="Q4", winrate=0.55, scoreLead=1.5, visits=300, prior=0.2, pv=["Q4"]),
        ],
        rootInfo=RootInfo(winrate=0.5, scoreLead=0.0, visits=250),
        ownership=[0.0] * 81,
    )


def test_answer_tool_parameters_cited_field_enum_matches_question_cited_field():
    enum = ANSWER_TOOL_PARAMETERS["properties"]["claims"]["items"]["properties"]["cited_field"]["enum"]
    assert set(enum) == {"winrate", "scoreLead", "visits", "prior"}


def test_answer_tool_parameters_claims_support_cited_move():
    cited_move_schema = ANSWER_TOOL_PARAMETERS["properties"]["claims"]["items"]["properties"]["cited_move"]
    assert cited_move_schema["type"] == ["string", "null"]


def test_answer_with_rag_tool_parameters_adds_rag_doc_id():
    assert "rag_doc_id" in ANSWER_WITH_RAG_TOOL_PARAMETERS["properties"]
    assert "answer" in ANSWER_WITH_RAG_TOOL_PARAMETERS["properties"]


def test_ask_decision_tool_parameters_offers_retrieve_knowledge_and_record_answer():
    tool_consts = [
        branch["properties"]["tool"]["const"] for branch in ASK_DECISION_TOOL_PARAMETERS["oneOf"]
    ]
    assert set(tool_consts) == {"retrieve_knowledge", "record_answer"}


def test_build_ask_user_prompt_includes_question_and_root_info():
    prompt = build_ask_user_prompt("почему белые слабы?", _analysis(), 9)
    assert "почему белые слабы?" in prompt
    assert "winrate=0.5" in prompt


def test_build_ask_user_prompt_lists_move_candidates_with_gtp_coords_not_converted_again():
    prompt = build_ask_user_prompt("что насчёт Q4?", _analysis_with_moves(), 9)
    # move_info.move is already a GTP string straight from KataGo - it must
    # appear verbatim, not be passed through xy_to_gtp() a second time.
    assert "Q4" in prompt
    assert "prior=0.2" in prompt


def test_build_ask_user_prompt_omits_move_candidates_block_when_there_are_none():
    prompt = build_ask_user_prompt("вопрос", _analysis(), 9)
    assert "Ходы-кандидаты" not in prompt
```

Note: `_analysis()` and `RootInfo`/`AnalyzeResponse` imports are already present at the top of `test_prompts.py` from the pre-existing tests — reuse them, don't re-import.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py -v -k "answer or ask"`
Expected: FAIL — `ImportError: cannot import name 'ANSWER_TOOL_PARAMETERS'`.

- [ ] **Step 3: Add the new prompt constants/function to `llm/prompts.py`**

Append to `backend/src/baduk_backend/llm/prompts.py`:

```python
ASK_SYSTEM_PROMPT = """\
Ты - тренер по игре в го, отвечающий на вопрос игрока кю-уровня о текущей \
позиции на русском языке. Тебе даны числа из анализа KataGo для этой позиции \
и, возможно, для нескольких ходов-кандидатов. Правила:
1. Обязательно цитируй числа только из переданных данных через инструмент \
record_answer - никогда не выдумывай новые числа.
2. Каждое утверждение (claim) должно ссылаться на конкретное поле (winrate, \
scoreLead, visits или prior) и точное число из данных; если утверждение о \
конкретном ходе-кандидате, укажи его координату в cited_move, иначе оставь \
cited_move пустым (null) - тогда утверждение сверяется с общей оценкой позиции.
3. Отвечай по существу вопроса игрока, не уходи в сторону.
4. Никогда не переоценивай позицию против чисел KataGo - твоя роль объяснить \
то, что уже посчитал движок, а не заново оценить позицию.
"""

ANSWER_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "Ответ на вопрос игрока на русском."},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cited_field": {
                        "type": "string",
                        "enum": ["winrate", "scoreLead", "visits", "prior"],
                    },
                    "cited_number": {"type": "number"},
                    "cited_move": {"type": ["string", "null"]},
                },
                "required": ["cited_field", "cited_number"],
            },
        },
    },
    "required": ["answer", "claims"],
}

ANSWER_WITH_RAG_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        **ANSWER_TOOL_PARAMETERS["properties"],  # answer, claims
        "rag_doc_id": {"type": ["string", "null"]},
    },
    "required": ["answer", "claims"],
}

ASK_DECISION_TOOL_PARAMETERS = {
    "oneOf": [
        {
            "type": "object",
            "properties": {"tool": {"const": "retrieve_knowledge"}},
            "required": ["tool"],
        },
        {
            "type": "object",
            "properties": {
                "tool": {"const": "record_answer"},
                **ANSWER_WITH_RAG_TOOL_PARAMETERS["properties"],
            },
            "required": ["tool", "answer", "claims"],
        },
    ]
}

# Cap on how many candidate moves are rendered into the prompt - moveInfos is
# already sorted by KataGo's own ranking (most-visited first), the same
# assumption feature_extraction/weak_group.py's pv_focus_top_k relies on.
ASK_TOP_MOVE_INFOS = 5


def build_ask_user_prompt(question: str, analysis: AnalyzeResponse, board_size: int) -> str:
    root = (
        f"rootInfo (общая оценка позиции): winrate={analysis.rootInfo.winrate}, "
        f"scoreLead={analysis.rootInfo.scoreLead}, visits={analysis.rootInfo.visits}\n"
    )
    top_moves = analysis.moveInfos[:ASK_TOP_MOVE_INFOS]
    if top_moves:
        move_lines = [
            f"- {m.move}: winrate={m.winrate}, scoreLead={m.scoreLead}, visits={m.visits}, prior={m.prior}"
            for m in top_moves
        ]
        moves_block = "Ходы-кандидаты (moveInfos):\n" + "\n".join(move_lines) + "\n"
    else:
        moves_block = ""
    return f"{root}{moves_block}Вопрос игрока: {question}\nОтветь на вопрос через record_answer."
```

`board_size` is accepted but unused by the body above - kept in the signature for symmetry with `build_user_prompt(finding, analysis, board_size)` and because the caller (Task 3's `answer_question`) already has it on hand from its own signature; no coordinate conversion is needed in this slice (see Global Constraints).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_prompts.py -v`
Expected: PASS (full pre-existing set plus the 7 new tests).

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/baduk_backend/llm/prompts.py backend/tests/llm/test_prompts.py
git commit -m "feat: add prompts and JSON schemas for the free-form question flow"
```

---

### Task 3: `LlamaProvider.answer_question`

**Files:**
- Modify: `backend/src/baduk_backend/llm/providers/llama.py`
- Test: `backend/tests/llm/test_llama_provider.py` (add tests, do not change existing ones)
- Test: `backend/tests/test_api_ask_integration.py` (new file — live-model integration test)

**Interfaces:**
- Consumes: `QuestionAnswer` (Task 1, `llm.schemas`); `ASK_SYSTEM_PROMPT`/`ANSWER_TOOL_PARAMETERS`/`ANSWER_WITH_RAG_TOOL_PARAMETERS`/`ASK_DECISION_TOOL_PARAMETERS`/`build_ask_user_prompt`/`RAG_SEARCH_INSTRUCTIONS`/`RAG_TOP_K` (Task 2 + existing, `llm.prompts`); `_rag_available`/`_call`/`_extract_json`/`_format_snippets` (existing, this same file/class).
- Produces: `LlamaProvider.answer_question(self, question: str, analysis: AnalyzeResponse, board_size: int, corrections: list[str] | None = None) -> QuestionAnswer` — Task 4's endpoint calls this indirectly (through `verify_question_and_retry`, which calls whatever `_AskProvider`-shaped object it's given).

Current `llm/providers/llama.py` (read before writing your diff) — the class `LlamaProvider` has `__init__`, `complete()`, and a private `_call(self, system_prompt, user_content, schema) -> dict` method; module-level helpers `_rag_available()`, `_format_snippets()`, `_extract_json()`, `_validate_explanation()`. Leave every one of those untouched.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/llm/test_llama_provider.py` (the file already imports `pytest`, `json`, `AnalyzeResponse`, `RootInfo`, `LlamaProvider`, and has `_FakeLlama`/`_chat_completion_response`/`_no_rag_by_default` fixture already defined at module scope — reuse them, don't redefine):

```python
def _question_json_response(answer: str, claims: list[dict]):
    return _chat_completion_response(json.dumps({"answer": answer, "claims": claims}))


def test_llama_provider_answer_question_parses_json_response():
    response = _question_json_response(
        "Winrate сейчас 50%.", [{"cited_field": "winrate", "cited_number": 0.5}]
    )
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    answer = provider.answer_question("какой winrate?", _analysis(), board_size=9)

    assert answer.answer == "Winrate сейчас 50%."
    assert answer.claims[0].cited_field == "winrate"


def test_llama_provider_answer_question_uses_answer_tool_schema_without_rag():
    from baduk_backend.llm.prompts import ANSWER_TOOL_PARAMETERS

    response = _question_json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    provider.answer_question("вопрос", _analysis(), board_size=9)

    assert llm.calls[0]["response_format"] == {"type": "json_object", "schema": ANSWER_TOOL_PARAMETERS}


def test_llama_provider_answer_question_prompt_includes_the_question_text():
    response = _question_json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    provider.answer_question("почему белые слабы?", _analysis(), board_size=9)

    sent_messages = llm.calls[0]["messages"]
    user_content = next(m["content"] for m in sent_messages if m["role"] == "user")
    assert "почему белые слабы?" in user_content


def test_llama_provider_answer_question_appends_corrections_to_prompt():
    response = _question_json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    provider.answer_question("вопрос", _analysis(), board_size=9, corrections=["ты ошибся про X"])

    sent_messages = llm.calls[0]["messages"]
    user_content = next(m["content"] for m in sent_messages if m["role"] == "user")
    assert "ты ошибся про X" in user_content


def test_llama_provider_answer_question_raises_if_content_is_none():
    response = _chat_completion_response(None)
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    with pytest.raises(RuntimeError, match="did not produce"):
        provider.answer_question("вопрос", _analysis(), board_size=9)


def test_llama_provider_answer_question_raises_on_schema_validation_failure():
    response = {
        "choices": [
            {"finish_reason": "length", "message": {"content": json.dumps({"answer": "ok"})}}
        ]
    }
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    with pytest.raises(RuntimeError, match="finish_reason='length'"):
        provider.answer_question("вопрос", _analysis(), board_size=9)


def test_llama_provider_answer_question_without_rag_available_uses_single_call_schema():
    from baduk_backend.llm.prompts import ANSWER_TOOL_PARAMETERS

    response = _question_json_response("ok", [])
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    answer = provider.answer_question("вопрос", _analysis(), board_size=9)

    assert len(llm.calls) == 1
    assert llm.calls[0]["response_format"] == {"type": "json_object", "schema": ANSWER_TOOL_PARAMETERS}
    assert answer.rag_doc_id is None


def test_llama_provider_answer_question_with_rag_available_can_decide_not_to_search(monkeypatch):
    from baduk_backend.llm.prompts import ASK_DECISION_TOOL_PARAMETERS

    monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", lambda: True)
    response = _chat_completion_response(
        json.dumps({"tool": "record_answer", "answer": "ok", "claims": []})
    )
    llm = _FakeLlama(response)
    provider = LlamaProvider(llm=llm)

    answer = provider.answer_question("вопрос", _analysis(), board_size=9)

    assert len(llm.calls) == 1
    assert llm.calls[0]["response_format"] == {
        "type": "json_object",
        "schema": ASK_DECISION_TOOL_PARAMETERS,
    }
    assert answer.answer == "ok"
    assert answer.rag_doc_id is None


def test_llama_provider_answer_question_with_rag_available_searches_with_the_question_text(monkeypatch):
    from baduk_backend.llm.prompts import ANSWER_WITH_RAG_TOOL_PARAMETERS
    from baduk_backend.rag.schemas import RagSnippet

    monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", lambda: True)

    captured_queries = []

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        captured_queries.append(query)
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
        json.dumps({"answer": "У группы нет двух глаз.", "claims": [], "rag_doc_id": "two-eyes-necessary"})
    )
    llm = _FakeLlama([decision_response, final_response])
    provider = LlamaProvider(llm=llm)

    answer = provider.answer_question("почему группа слаба?", _analysis(), board_size=9)

    assert len(llm.calls) == 2
    assert captured_queries == ["почему группа слаба?"]
    assert llm.calls[1]["response_format"] == {
        "type": "json_object",
        "schema": ANSWER_WITH_RAG_TOOL_PARAMETERS,
    }
    final_user_content = next(m["content"] for m in llm.calls[1]["messages"] if m["role"] == "user")
    assert "two-eyes-necessary" in final_user_content
    assert answer.rag_doc_id == "two-eyes-necessary"
    assert answer.answer == "У группы нет двух глаз."


def test_llama_provider_answer_question_degrades_gracefully_when_search_fails_mid_flow(monkeypatch):
    monkeypatch.setattr("baduk_backend.llm.providers.llama._rag_available", lambda: True)

    def fake_retrieve_knowledge(query, top_k=3, **kwargs):
        raise RuntimeError("RAG store not found")

    monkeypatch.setattr("baduk_backend.rag.retrieval.retrieve_knowledge", fake_retrieve_knowledge)

    decision_response = _chat_completion_response(json.dumps({"tool": "retrieve_knowledge"}))
    final_response = _chat_completion_response(json.dumps({"answer": "ok", "claims": [], "rag_doc_id": None}))
    llm = _FakeLlama([decision_response, final_response])
    provider = LlamaProvider(llm=llm)

    answer = provider.answer_question("вопрос", _analysis(), board_size=9)

    assert len(llm.calls) == 2
    final_user_content = next(m["content"] for m in llm.calls[1]["messages"] if m["role"] == "user")
    assert "не дал результатов" in final_user_content
    assert answer.rag_doc_id is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_llama_provider.py -v -k answer_question`
Expected: FAIL — `AttributeError: 'LlamaProvider' object has no attribute 'answer_question'`.

- [ ] **Step 3: Add `answer_question` and `_validate_question_answer` to `llama.py`**

Add this import line alongside the existing `from baduk_backend.llm.schemas import Explanation` line, changing it to:

```python
from baduk_backend.llm.schemas import Explanation, QuestionAnswer
```

Add these names to the existing `from baduk_backend.llm.prompts import (...)` block (it currently imports `EXPLANATION_TOOL_PARAMETERS, EXPLANATION_WITH_RAG_TOOL_PARAMETERS, RAG_DECISION_TOOL_PARAMETERS, RAG_SEARCH_INSTRUCTIONS, RAG_TOP_K, SYSTEM_PROMPT, build_rag_query, build_user_prompt` — keep every existing name, add the five new ones so the import block reads):

```python
from baduk_backend.llm.prompts import (
    ANSWER_TOOL_PARAMETERS,
    ANSWER_WITH_RAG_TOOL_PARAMETERS,
    ASK_DECISION_TOOL_PARAMETERS,
    ASK_SYSTEM_PROMPT,
    EXPLANATION_TOOL_PARAMETERS,
    EXPLANATION_WITH_RAG_TOOL_PARAMETERS,
    RAG_DECISION_TOOL_PARAMETERS,
    RAG_SEARCH_INSTRUCTIONS,
    RAG_TOP_K,
    SYSTEM_PROMPT,
    build_ask_user_prompt,
    build_rag_query,
    build_user_prompt,
)
```

Add a new module-level function next to `_validate_explanation`:

```python
def _validate_question_answer(data: dict, finish_reason: str | None = None) -> QuestionAnswer:
    try:
        return QuestionAnswer.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(
            f"Llama did not produce valid structured output "
            f"(finish_reason={finish_reason!r}, content={data!r})"
        ) from exc
```

Add a new method to the `LlamaProvider` class, after `complete()` and before `_call()`:

```python
    def answer_question(
        self,
        question: str,
        analysis: AnalyzeResponse,
        board_size: int,
        corrections: list[str] | None = None,
    ) -> QuestionAnswer:
        user_content = build_ask_user_prompt(question, analysis, board_size)
        if corrections:
            user_content += "\n\nИсправь предыдущий ответ:\n" + "\n".join(corrections)

        if not _rag_available():
            choice = self._call(ASK_SYSTEM_PROMPT, user_content, ANSWER_TOOL_PARAMETERS)
            return _validate_question_answer(_extract_json(choice), choice.get("finish_reason"))

        system_prompt = ASK_SYSTEM_PROMPT + "\n" + RAG_SEARCH_INSTRUCTIONS
        decision_choice = self._call(system_prompt, user_content, ASK_DECISION_TOOL_PARAMETERS)
        decision = _extract_json(decision_choice)

        if decision.get("tool") != "retrieve_knowledge":
            return _validate_question_answer(decision, decision_choice.get("finish_reason"))

        from baduk_backend.rag.retrieval import retrieve_knowledge

        try:
            snippets = retrieve_knowledge(question, top_k=RAG_TOP_K)
        except (RuntimeError, ImportError):
            snippets = []

        final_user_content = user_content + "\n\n" + _format_snippets(snippets)
        final_choice = self._call(system_prompt, final_user_content, ANSWER_WITH_RAG_TOOL_PARAMETERS)
        return _validate_question_answer(_extract_json(final_choice), final_choice.get("finish_reason"))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/llm/test_llama_provider.py -v`
Expected: PASS (full pre-existing set plus the 10 new `answer_question`-prefixed tests).

- [ ] **Step 5: Write the integration test (self-skips without a real model)**

Create `backend/tests/test_api_ask_integration.py`, mirroring `backend/tests/test_api_explain_integration.py`'s structure (module-marked `pytest.mark.integration`, skips inline when the env var is absent, calls the provider directly rather than through the HTTP layer — same pattern that file already uses for its `test_explain_with_real_llama`):

```python
import os

import pytest

pytestmark = pytest.mark.integration


def test_ask_with_real_llama():
    if not os.environ.get("BADUK_LLAMA_MODEL_PATH"):
        pytest.skip("BADUK_LLAMA_MODEL_PATH not set")

    from baduk_backend.api.schemas import AnalyzeResponse, RootInfo
    from baduk_backend.llm.providers.llama import LlamaProvider

    provider = LlamaProvider()
    analysis = AnalyzeResponse(
        id="x",
        moveInfos=[],
        rootInfo=RootInfo(winrate=0.4, scoreLead=-3.0, visits=800),
        ownership=[0.1] * 81,
    )

    answer = provider.answer_question("Кто сейчас впереди по очкам?", analysis, board_size=9)

    assert answer.answer
    assert len(answer.claims) > 0
```

- [ ] **Step 6: Run the integration test if credentials are available, otherwise confirm it skips cleanly**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_ask_integration.py -v -m integration`
Expected: PASS if `BADUK_LLAMA_MODEL_PATH` is set on this machine (per this project's established local setup); otherwise SKIPPED. A hard FAIL is not acceptable.

- [ ] **Step 7: Run the full backend test suite (non-integration)**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS — every pre-existing test plus all of this task's new tests.

- [ ] **Step 8: Commit**

```bash
git add backend/src/baduk_backend/llm/providers/llama.py backend/tests/llm/test_llama_provider.py backend/tests/test_api_ask_integration.py
git commit -m "feat: add LlamaProvider.answer_question for free-form questions"
```

---

### Task 4: `POST /api/ask` endpoint

**Files:**
- Modify: `backend/src/baduk_backend/api/schemas.py`
- Create: `backend/src/baduk_backend/api/ask.py`
- Modify: `backend/src/baduk_backend/main.py`
- Test: `backend/tests/test_api_ask.py` (new file)

**Interfaces:**
- Consumes: `verify_question_and_retry` (Task 1, `llm.consistency`); `RagCitation` (existing, `api.schemas`); `require_valid_token` (existing, `baduk_backend.auth`); `get_llm_provider` (existing, `api.explain` — reused, not redefined, matching `api/explain_opening.py`'s already-established convention); `LLMProvider` (existing, `llm.orchestrator`, used only as the FastAPI dependency's return type — see Global Constraints on why the concrete `LlamaProvider` is never imported here).
- Produces: `AskRequest`, `AskResponse` (`api/schemas.py`); `POST /api/ask` route (`api/ask.py`, `router: APIRouter`) — Task 5 (frontend) mirrors these two schemas exactly on the TypeScript side.

Current `api/schemas.py` already has `ExplainRequest`/`RagCitation`/`ExplainResponse` at the end of the file (read the file before writing your diff — the exact surrounding content matters for where you insert).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api_ask.py`, mirroring `backend/tests/test_api_explain.py`'s structure and the `explain_client`-style fixture from `backend/tests/conftest.py` (a plain local fixture here, not added to `conftest.py`, since only this file needs a stub with an `answer_question` method):

```python
from fastapi.testclient import TestClient
import pytest

from baduk_backend.auth import AUTH_TOKEN
from baduk_backend.llm.schemas import QuestionAnswer, QuestionClaim
from baduk_backend.main import app


class _StubAskProvider:
    def answer_question(self, question, analysis, board_size, corrections=None):
        return QuestionAnswer(
            answer="Тестовый ответ",
            claims=[QuestionClaim(cited_field="winrate", cited_number=analysis.rootInfo.winrate)],
        )


class _NonAskProvider:
    """A provider that only implements the Finding-based flow, like ClaudeProvider/GeminiProvider -
    used to prove /api/ask gates on capability, not on being told the provider name."""

    def complete(self, finding, analysis, board_size, corrections=None):
        raise AssertionError("should never be called by /api/ask")


class _FailingAskProvider:
    def answer_question(self, question, analysis, board_size, corrections=None):
        raise RuntimeError("model process crashed")


@pytest.fixture
def ask_client():
    app.state.llm_provider = _StubAskProvider()
    try:
        yield TestClient(app)
    finally:
        del app.state.llm_provider


def _payload(question="почему белые слабы?"):
    return {
        "moves": [["B", "E5"]],
        "boardXSize": 9,
        "boardYSize": 9,
        "analysis": {
            "id": "x",
            "turnNumber": 1,
            "moveInfos": [],
            "rootInfo": {"winrate": 0.5, "scoreLead": 0.0, "visits": 250},
            "ownership": [0.0] * 81,
        },
        "question": question,
    }


def test_ask_returns_verified_answer(ask_client):
    response = ask_client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Тестовый ответ"
    assert body["verified"] is True


def test_ask_without_token_returns_401(ask_client):
    response = ask_client.post("/api/ask", json=_payload())
    assert response.status_code == 401


def test_ask_returns_422_on_empty_question(ask_client):
    response = ask_client.post(
        "/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload(question="")
    )
    assert response.status_code == 422


def test_ask_returns_422_on_too_long_question(ask_client):
    response = ask_client.post(
        "/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload(question="я" * 501)
    )
    assert response.status_code == 422


def test_ask_returns_422_when_ownership_length_mismatches_board_size(ask_client):
    payload = _payload()
    payload["analysis"]["ownership"] = [0.0] * 80
    response = ask_client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=payload)
    assert response.status_code == 422


def test_ask_returns_503_when_provider_cannot_answer_questions():
    app.state.llm_provider = _NonAskProvider()
    try:
        client = TestClient(app)
        response = client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload())
    finally:
        del app.state.llm_provider

    assert response.status_code == 503
    assert "llama" in response.json()["detail"]


def test_ask_returns_503_when_provider_raises():
    app.state.llm_provider = _FailingAskProvider()
    try:
        client = TestClient(app)
        response = client.post("/api/ask", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload())
    finally:
        del app.state.llm_provider

    assert response.status_code == 503
    assert "model process crashed" in response.json()["detail"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_ask.py -v`
Expected: FAIL — `ImportError`/404 (`/api/ask` doesn't exist yet).

- [ ] **Step 3: Add `AskRequest`/`AskResponse` to `api/schemas.py`**

Append to `backend/src/baduk_backend/api/schemas.py`, after the existing `ExplainResponse` class at the end of the file:

```python
class AskRequest(BaseModel):
    moves: list[list[str]] = Field(default_factory=list)
    boardXSize: int = Field(ge=2, le=25)
    boardYSize: int = Field(ge=2, le=25)
    analysis: AnalyzeResponse
    question: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _ownership_matches_board_size(self) -> "AskRequest":
        ownership = self.analysis.ownership
        if ownership is not None and len(ownership) != self.boardXSize * self.boardYSize:
            raise ValueError(
                "analysis.ownership length must equal boardXSize * boardYSize "
                f"({self.boardXSize * self.boardYSize}), got {len(ownership)}"
            )
        return self


class AskResponse(BaseModel):
    answer: str | None = None
    verified: bool | None = None
    message: str | None = None
    citation: RagCitation | None = None
```

(`Field`, `model_validator`, `AnalyzeResponse`, and `RagCitation` are all already imported/defined earlier in this same file — no new imports needed for this step.)

- [ ] **Step 4: Create `api/ask.py`**

Create `backend/src/baduk_backend/api/ask.py`, mirroring `api/explain.py`'s structure. Note: `api/explain_opening.py` already establishes the convention of REUSING `get_llm_provider` by importing it from `explain.py` rather than redefining it (`from baduk_backend.api.explain import get_llm_provider`) — follow that same convention here, don't redefine it a third time:

```python
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from baduk_backend.api.explain import get_llm_provider
from baduk_backend.api.schemas import AskRequest, AskResponse, RagCitation
from baduk_backend.auth import require_valid_token
from baduk_backend.llm.consistency import verify_question_and_retry
from baduk_backend.llm.orchestrator import LLMProvider

router = APIRouter()


@router.post(
    "/api/ask",
    response_model=AskResponse,
    dependencies=[Depends(require_valid_token)],
)
async def ask(
    body: AskRequest,
    provider: LLMProvider = Depends(get_llm_provider),
) -> AskResponse:
    # Structural check, not isinstance(provider, LlamaProvider) - importing
    # the concrete class here would force an unconditional `import llama_cpp`
    # into a module that must keep working when the active provider is
    # claude/gemini and llama_cpp isn't installed at all.
    if not hasattr(provider, "answer_question"):
        raise HTTPException(status_code=503, detail="/api/ask доступен только с провайдером llama")

    try:
        question_answer, verified = await asyncio.to_thread(
            verify_question_and_retry, provider, body.question, body.analysis, body.boardXSize
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    citation = None
    if question_answer.rag_doc_id is not None:
        from baduk_backend.rag.retrieval import get_snippet_by_id

        try:
            snippet = await asyncio.to_thread(get_snippet_by_id, question_answer.rag_doc_id)
        except Exception:
            snippet = None
        if snippet is not None:
            citation = RagCitation(
                doc_id=snippet.doc_id,
                title=snippet.title,
                source=snippet.source,
                text_snippet=snippet.text_snippet,
            )

    return AskResponse(answer=question_answer.answer, verified=verified, citation=citation)
```

- [ ] **Step 5: Register the router in `main.py`**

In `backend/src/baduk_backend/main.py`, change the import line:

```python
from baduk_backend.api import analysis, explain, explain_opening
```

to:

```python
from baduk_backend.api import analysis, ask, explain, explain_opening
```

and add a new line alongside the existing `app.include_router(...)` calls:

```python
app.include_router(ask.router)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_ask.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS — every pre-existing test, unchanged, plus all new tests from Tasks 1-4.

- [ ] **Step 8: Commit**

```bash
git add backend/src/baduk_backend/api/schemas.py backend/src/baduk_backend/api/ask.py backend/src/baduk_backend/main.py backend/tests/test_api_ask.py
git commit -m "feat: add POST /api/ask endpoint"
```

---

### Task 5: Frontend — question input in `LlmExplanationPanel`

**Files:**
- Modify: `frontend/src/renderer/src/ipc/client.ts`
- Modify: `frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx`
- Test: `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx` (add tests, do not change existing ones)

**Interfaces:**
- Consumes: `currentMoveAnalysis`, `currentNodeId` (existing, `state/appState`); `getBoardSize` (existing, `board/sgfLoader`); `gtpMoves` (existing, `board/gameRequestBuilder`) — same values `handleExplain` already computes, reused for the ask request's `moves`/`boardXSize`/`boardYSize`.
- Produces: `AskRequest`, `AskResponse`, `askQuestion(request: AskRequest): Promise<AskResponse>` (`ipc/client.ts`) — a self-contained addition; nothing later in this plan depends on it.

Current `ipc/client.ts` (read before writing your diff) has `ExplainRequest`/`ExplainOpeningRequest`/`RagCitation`/`ExplainResponse`/`explainPosition()`/`explainOpening()` at the end of the file, all following the same `fetch` + `X-Auth-Token` + error-shape pattern. Current `LlmExplanationPanel.tsx` (read before writing your diff, 247 lines) has two independent state blocks in the function body (`status`/`result`/`errorMessage` + `handleExplain`, then `openingColor`/`openingStatus`/`openingResult`/`openingErrorMessage` + `handleExplainOpening`), and the returned JSX renders the first block, then an `.llm-explanation-panel__opening` div for the second. Leave every existing line in both files untouched except where this task's diff explicitly inserts new lines.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx` (the file already imports `render`/`fireEvent`/`waitFor`, mocks `@renderer/ipc/client`, and has a `loadPosition()` helper that sets `currentTree`/`currentNodeId`/`analysisByTurn` for a ready position - reuse it). First, extend the existing mock setup at the top of the file (this is an addition to the `vi.mock`/import block, not a change to any existing test body):

```typescript
import { askQuestion } from '@renderer/ipc/client'
import type { AskResponse } from '@renderer/ipc/client'
```

and change the existing `vi.mock('@renderer/ipc/client', ...)` call's returned object (this line's shape changes, no existing test's *behavior* changes - the mocked module simply gains one more exported function):

```typescript
vi.mock('@renderer/ipc/client', () => ({
  explainPosition: vi.fn(),
  explainOpening: vi.fn(),
  askQuestion: vi.fn()
}))
```

and add, next to the existing `const mockExplainPosition = ...`/`const mockExplainOpening = ...` lines:

```typescript
const mockAskQuestion = vi.mocked(askQuestion)
```

Then append new `it(...)` blocks inside the existing `describe('LlmExplanationPanel', () => { ... })`:

```typescript
  it('disables the ask button when the question field is empty', () => {
    loadPosition()
    const { getByText } = render(<LlmExplanationPanel />)
    expect((getByText('Спросить') as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows a verified answer after a successful ask', async () => {
    loadPosition()
    mockAskQuestion.mockResolvedValue({
      answer: 'Winrate сейчас 60%.',
      verified: true,
      message: null,
      citation: null
    } satisfies AskResponse)

    const { getByText, getByPlaceholderText } = render(<LlmExplanationPanel />)
    fireEvent.input(getByPlaceholderText('Задайте вопрос про текущую позицию...'), {
      target: { value: 'какой сейчас winrate?' }
    })
    fireEvent.click(getByText('Спросить'))

    await waitFor(() => {
      expect(getByText('Winrate сейчас 60%.')).toBeTruthy()
    })
  })

  it('shows an error message when askQuestion rejects', async () => {
    loadPosition()
    mockAskQuestion.mockRejectedValue(new Error('askQuestion failed (503): доступно только с llama'))

    const { getByText, getByPlaceholderText } = render(<LlmExplanationPanel />)
    fireEvent.input(getByPlaceholderText('Задайте вопрос про текущую позицию...'), {
      target: { value: 'вопрос' }
    })
    fireEvent.click(getByText('Спросить'))

    await waitFor(() => {
      expect(getByText(/доступно только с llama/)).toBeTruthy()
    })
  })

  it('resets the ask result when the current position changes', async () => {
    // Mirrors the existing 'clears a stale explanation when the current
    // position changes' test above exactly: two real nodes, each with its
    // own analysisByTurn entry, navigate via currentNodeId.value, and assert
    // through waitFor (the reset runs inside a useEffect, not synchronously).
    const tree = parseSgf('(;GM[1]FF[4]SZ[9];B[ee];W[gg])')
    const [, nodeA, nodeB] = mainLineNodeIds(tree)
    currentTree.value = tree
    currentNodeId.value = nodeA
    analysisByTurn.value = new Map([
      [nodeA, { id: 'a', moveInfos: [], rootInfo: { winrate: 0.6, scoreLead: 1, visits: 100 }, ownership: new Array(81).fill(0) }],
      [nodeB, { id: 'b', moveInfos: [], rootInfo: { winrate: 0.4, scoreLead: -1, visits: 100 }, ownership: new Array(81).fill(0) }]
    ])
    mockAskQuestion.mockResolvedValue({
      answer: 'Ответ про первую позицию',
      verified: true,
      message: null,
      citation: null
    } satisfies AskResponse)

    const { getByText, getByPlaceholderText, queryByText } = render(<LlmExplanationPanel />)
    fireEvent.input(getByPlaceholderText('Задайте вопрос про текущую позицию...'), {
      target: { value: 'вопрос' }
    })
    fireEvent.click(getByText('Спросить'))
    await waitFor(() => expect(getByText('Ответ про первую позицию')).toBeTruthy())

    // Navigate to a different position (B) that also has its own analysis
    // available, without clicking "ask" again.
    currentNodeId.value = nodeB

    await waitFor(() => {
      expect(queryByText('Ответ про первую позицию')).toBeNull()
    })
  })
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: FAIL — `Спросить` button not found (block doesn't exist yet), plus a mock-shape error for `askQuestion` not being exported from `ipc/client.ts` yet.

- [ ] **Step 3: Add `AskRequest`/`AskResponse`/`askQuestion` to `ipc/client.ts`**

Append to `frontend/src/renderer/src/ipc/client.ts`, after the existing `explainOpening()` function at the end of the file:

```typescript
export interface AskRequest {
  moves: [string, string][]
  boardXSize: number
  boardYSize: number
  analysis: AnalyzeResponse
  question: string
}

export interface AskResponse {
  answer: string | null
  verified: boolean | null
  message: string | null
  citation: RagCitation | null
}

export async function askQuestion(request: AskRequest): Promise<AskResponse> {
  const { port, token } = await getConnection()
  const response = await fetch(`http://127.0.0.1:${port}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Auth-Token': token },
    body: JSON.stringify(request)
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(`askQuestion failed (${response.status}): ${body.detail ?? response.statusText}`)
  }
  return response.json()
}
```

- [ ] **Step 4: Add the question-input block to `LlmExplanationPanel.tsx`**

Change the existing import line:

```typescript
import { explainPosition, explainOpening } from '../ipc/client'
import type { ExplainResponse } from '../ipc/client'
```

to:

```typescript
import { explainPosition, explainOpening, askQuestion } from '../ipc/client'
import type { ExplainResponse, AskResponse } from '../ipc/client'
```

Add a new state block inside the `LlmExplanationPanel` function body, after the existing `const [errorMessage, setErrorMessage] = useState<string | null>(null)` line and its surrounding `analysis`/`tree`/`nodeId` reads (which the new block also needs - reuse the same `analysis`/`tree`/`nodeId` consts already declared above, do not redeclare them):

```typescript
  const [question, setQuestion] = useState('')
  const [askStatus, setAskStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')
  const [askResult, setAskResult] = useState<AskResponse | null>(null)
  const [askErrorMessage, setAskErrorMessage] = useState<string | null>(null)

  // Same reasoning as the reset effect above for the "explain this position"
  // block: an answer is only valid for the position it was asked about.
  useEffect(() => {
    setAskStatus('idle')
    setAskResult(null)
    setAskErrorMessage(null)
  }, [nodeId])

  async function handleAsk(): Promise<void> {
    if (!tree || nodeId === null || !analysis || !question.trim()) return
    const requestedNodeId = nodeId
    setAskStatus('loading')
    setAskErrorMessage(null)
    try {
      const boardSize = getBoardSize(tree)
      const moves = gtpMoves(tree, requestedNodeId, boardSize)
      const response = await askQuestion({
        moves,
        boardXSize: boardSize,
        boardYSize: boardSize,
        analysis,
        question: question.trim()
      })
      if (currentNodeId.value !== requestedNodeId) return
      setAskResult(response)
      setAskStatus('done')
    } catch (err) {
      if (currentNodeId.value !== requestedNodeId) return
      setAskErrorMessage(err instanceof Error ? err.message : 'Не удалось получить ответ')
      setAskStatus('error')
    }
  }
```

Add the new block to the returned JSX, between the existing closing `)}` of the "Объяснить эту позицию" result block and the `<div class="llm-explanation-panel__opening">` block:

```tsx
      <div class="llm-explanation-panel__ask">
        <h3>Вопрос</h3>
        <textarea
          placeholder="Задайте вопрос про текущую позицию..."
          value={question}
          onInput={(e) => setQuestion((e.target as HTMLTextAreaElement).value)}
        />
        <button
          type="button"
          disabled={!analysis || !question.trim() || askStatus === 'loading'}
          onClick={handleAsk}
        >
          {askStatus === 'loading' ? 'Спрашиваю...' : 'Спросить'}
        </button>
        {askStatus === 'error' && <div class="llm-explanation-panel__error">{askErrorMessage}</div>}
        {askStatus === 'done' && askResult?.message && (
          <div class="llm-explanation-panel__message">{askResult.message}</div>
        )}
        {askStatus === 'done' && askResult?.answer && (
          <>
            <div
              class={
                askResult.verified
                  ? 'llm-explanation-panel__verified llm-explanation-panel__verified--true'
                  : 'llm-explanation-panel__verified llm-explanation-panel__verified--false'
              }
            >
              {askResult.verified ? 'Проверено' : 'Не удалось проверить численно'}
            </div>
            <div class="llm-explanation-panel__summary">{askResult.answer}</div>
            {askResult.citation && (
              <details class="llm-explanation-panel__citation">
                <summary>
                  {askResult.citation.title}{' '}
                  <span class="llm-explanation-panel__citation-source">
                    ({askResult.citation.source})
                  </span>
                </summary>
                <div class="llm-explanation-panel__citation-text">
                  {askResult.citation.text_snippet}
                </div>
              </details>
            )}
          </>
        )}
      </div>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: PASS (full pre-existing set plus the 4 new tests).

- [ ] **Step 6: Run the full frontend test suite and both typechecks**

Run: `cd frontend && pnpm exec vitest run`
Expected: PASS — every pre-existing test, unchanged.

Run: `cd frontend && pnpm run typecheck:web`
Expected: no output (clean).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/renderer/src/ipc/client.ts frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx frontend/tests/renderer/components/LlmExplanationPanel.test.tsx
git commit -m "feat: add free-form question input to LlmExplanationPanel"
```
