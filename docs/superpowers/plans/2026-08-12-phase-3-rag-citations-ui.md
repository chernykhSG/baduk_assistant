# Phase 3 RAG Citations in UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the RAG citation (title/source/full text) that the `llama-cpp-python` provider cited in an explanation, in a collapsible section of `LlmExplanationPanel` — with zero UI change when no citation was made.

**Architecture:** Backend gains a point lookup (`get_snippet_by_id`, by primary key, not semantic search) that `/api/explain` calls once, only when `Explanation.rag_doc_id` is set, to enrich the bare `doc_id` into a full `RagCitation` on `ExplainResponse`. Frontend mirrors that type and renders it as a native `<details>/<summary>` disclosure, only when present.

**Tech Stack:** Python 3.12 (FastAPI/pydantic, existing Chroma-backed `rag/` package), TypeScript/Preact (existing `ipc/client.ts` + `LlmExplanationPanel.tsx`). No new dependencies.

## Global Constraints

- Branch `phase-3-rag-citations-ui`, forked from `main`. Never commit directly to `main`.
- `Explanation`/`Claim` (backend `llm/schemas.py`, frontend `ipc/client.ts`) and `llama.py`/`consistency.py` are **not modified** — `rag_doc_id` on `Explanation` already exists and is untouched; this plan only adds enrichment on top, at the `ExplainResponse` layer.
- `get_snippet_by_id(doc_id: str, store_path: Path = DEFAULT_STORE_PATH) -> RagSnippet | None` — no `embedding_model` parameter (unlike `retrieve_knowledge`; this is a primary-key lookup via `collection.get(ids=[doc_id])`, not a semantic query, so no embedding is ever computed).
- `get_snippet_by_id` never raises — returns `None` for every failure mode (store missing, collection missing, id not found), since citation enrichment is a non-critical improvement to the response, not a required part of it.
- `citation` is only populated when `explanation.rag_doc_id is not None` **and** `get_snippet_by_id` actually finds something — otherwise `null`, with no error raised anywhere in `/api/explain`.
- `citation` is a required (`X | null`, not `X?`) field on both the backend `ExplainResponse` and the frontend `ExplainResponse` TypeScript interface — matching the existing style of every other field on that type (`finding`, `explanation`, `verified`, `message` are all `X | null`, none are optional).
- The citation section in `LlmExplanationPanel` renders **only** when `result.citation` is non-null — no "RAG not used" placeholder, no visible change to the panel when there's no citation.
- Frontend citation UI is a native `<details>/<summary>` element (no custom JS toggle) — keyboard-accessible for free, matching the project's established architectural requirement for keyboard-first UI.
- `chromadb`/`sentence_transformers` stay lazily imported (inside functions) everywhere new code touches them.
- Full spec: `docs/superpowers/specs/2026-08-12-phase-3-rag-citations-ui-design.md`.

---

### Task 1: Backend — `get_snippet_by_id` + `RagCitation` + `/api/explain` wiring

**Files:**
- Modify: `backend/src/baduk_backend/rag/retrieval.py`
- Modify: `backend/src/baduk_backend/api/schemas.py`
- Modify: `backend/src/baduk_backend/api/explain.py`
- Modify: `backend/tests/rag/test_retrieval.py`
- Modify: `backend/tests/test_api_explain.py`

**Interfaces:**
- Consumes: `RagSnippet` (`baduk_backend.rag.schemas`, already exists: `doc_id: str, title: str, source: str, text_snippet: str, relevance_score: float`), `get_chroma_client`/`COLLECTION_NAME`/`DEFAULT_STORE_PATH` (`baduk_backend.rag.store`, already exist), `Explanation.rag_doc_id: str | None` (`baduk_backend.llm.schemas`, already exists).
- Produces: `get_snippet_by_id(doc_id: str, store_path: Path = DEFAULT_STORE_PATH) -> RagSnippet | None` (importable from `baduk_backend.rag.retrieval`); `RagCitation(doc_id: str, title: str, source: str, text_snippet: str)` and `ExplainResponse.citation: RagCitation | None = None` (importable from `baduk_backend.api.schemas`). Task 2 does not consume anything from this task directly (frontend only talks to the HTTP JSON contract), but the exact JSON shape `{"doc_id": ..., "title": ..., "source": ..., "text_snippet": ...}` for the `citation` field is what Task 2's TypeScript type must match.

- [ ] **Step 1: Write the failing tests for `get_snippet_by_id`**

Add to `backend/tests/rag/test_retrieval.py` (the file already has `pytest.importorskip("chromadb")`/`("sentence_transformers")`, `run_ingest`, `KB_ROOT`, `_FakeEmbeddingModel` — reuse them, add `get_snippet_by_id` to the existing `from baduk_backend.rag.retrieval import retrieve_knowledge` import line):

```python
def test_get_snippet_by_id_returns_snippet_when_found(tmp_path):
    store_path = tmp_path / "rag_store"
    fake = _FakeEmbeddingModel()
    run_ingest(knowledge_base_path=KB_ROOT, store_path=store_path, embedding_model=fake)

    snippet = get_snippet_by_id("valid_principle", store_path=store_path)

    assert snippet is not None
    assert snippet.doc_id == "valid_principle"
    assert snippet.title
    assert snippet.source
    assert snippet.text_snippet


def test_get_snippet_by_id_returns_none_when_doc_id_not_found(tmp_path):
    store_path = tmp_path / "rag_store"
    fake = _FakeEmbeddingModel()
    run_ingest(knowledge_base_path=KB_ROOT, store_path=store_path, embedding_model=fake)

    snippet = get_snippet_by_id("does-not-exist", store_path=store_path)

    assert snippet is None


def test_get_snippet_by_id_returns_none_when_store_missing(tmp_path):
    snippet = get_snippet_by_id("anything", store_path=tmp_path / "does_not_exist")

    assert snippet is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_retrieval.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_snippet_by_id'`.

- [ ] **Step 3: Implement `get_snippet_by_id` in `rag/retrieval.py`**

Read the current file first (it already has `retrieve_knowledge`, imports `Path`, `RagSnippet`, and from `baduk_backend.rag.store` imports `COLLECTION_NAME, DEFAULT_STORE_PATH, get_chroma_client, get_embedding_model, to_float_vectors`). Append this new function after `retrieve_knowledge`:

```python
def get_snippet_by_id(doc_id: str, store_path: Path = DEFAULT_STORE_PATH) -> RagSnippet | None:
    if not store_path.exists():
        return None

    client = get_chroma_client(store_path)
    from chromadb.errors import NotFoundError

    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except NotFoundError:
        return None

    result = collection.get(ids=[doc_id])
    ids = result["ids"]
    if not ids:
        return None

    metadata = result["metadatas"][0]
    document = result["documents"][0]
    return RagSnippet(
        doc_id=ids[0],
        title=metadata["title"],
        source=metadata["source"],
        text_snippet=document,
        # This is a direct id lookup, not a ranked semantic query - there is
        # no distance/similarity to report. 1.0 documents "this is exactly
        # the requested card", not a computed relevance.
        relevance_score=1.0,
    )
```

Note: unlike `retrieve_knowledge`, this function takes no `embedding_model` parameter — `collection.get(ids=...)` is a primary-key lookup, it never computes or needs an embedding.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_retrieval.py -v`
Expected: PASS (all tests, including the 3 new ones).

- [ ] **Step 5: Add `RagCitation` and `ExplainResponse.citation` to `api/schemas.py`**

Read the current file first to find the exact location of `ExplainResponse` (currently `finding: Finding | None = None`, `explanation: Explanation | None = None`, `verified: bool | None = None`, `message: str | None = None` — no other fields). Add a new `RagCitation` class immediately before `ExplainResponse`, and add `citation` as the last field of `ExplainResponse`:

```python
class RagCitation(BaseModel):
    doc_id: str
    title: str
    source: str
    text_snippet: str


class ExplainResponse(BaseModel):
    finding: Finding | None = None
    explanation: Explanation | None = None
    verified: bool | None = None
    message: str | None = None
    citation: RagCitation | None = None
```

- [ ] **Step 6: Write the failing tests for `/api/explain` citation wiring**

Add to `backend/tests/test_api_explain.py` (the file already imports `AUTH_TOKEN` from `baduk_backend.auth` and has a `_payload(...)` helper — reuse `_payload()` unmodified):

```python
def test_explain_includes_citation_when_rag_doc_id_is_set(monkeypatch):
    from fastapi.testclient import TestClient

    from baduk_backend.llm.schemas import Claim, Explanation
    from baduk_backend.main import app
    from baduk_backend.rag.schemas import RagSnippet

    class _CitingProvider:
        def complete(self, finding, analysis, board_size, corrections=None):
            return Explanation(
                summary="...",
                claims=[
                    Claim(
                        text="...",
                        finding_id=finding.finding_id,
                        cited_field="weak_score",
                        cited_number=finding.weak_score,
                    )
                ],
                rag_doc_id="two-eyes-necessary",
            )

    def fake_get_snippet_by_id(doc_id, **kwargs):
        assert doc_id == "two-eyes-necessary"
        return RagSnippet(
            doc_id="two-eyes-necessary",
            title="Два глаза",
            source="principles/two-eyes.md",
            text_snippet="Группа с двумя глазами не может быть захвачена.",
            relevance_score=1.0,
        )

    monkeypatch.setattr("baduk_backend.rag.retrieval.get_snippet_by_id", fake_get_snippet_by_id)

    app.state.llm_provider = _CitingProvider()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
        )
        assert response.status_code == 200
        assert response.json()["citation"] == {
            "doc_id": "two-eyes-necessary",
            "title": "Два глаза",
            "source": "principles/two-eyes.md",
            "text_snippet": "Группа с двумя глазами не может быть захвачена.",
        }
    finally:
        del app.state.llm_provider


def test_explain_omits_citation_when_rag_doc_id_is_none(explain_client):
    response = explain_client.post(
        "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
    )
    assert response.status_code == 200
    assert response.json()["citation"] is None


def test_explain_omits_citation_when_snippet_lookup_returns_none(monkeypatch):
    from fastapi.testclient import TestClient

    from baduk_backend.llm.schemas import Claim, Explanation
    from baduk_backend.main import app

    class _CitingProvider:
        def complete(self, finding, analysis, board_size, corrections=None):
            return Explanation(
                summary="...",
                claims=[
                    Claim(
                        text="...",
                        finding_id=finding.finding_id,
                        cited_field="weak_score",
                        cited_number=finding.weak_score,
                    )
                ],
                rag_doc_id="vanished-doc",
            )

    def fake_get_snippet_by_id(doc_id, **kwargs):
        return None

    monkeypatch.setattr("baduk_backend.rag.retrieval.get_snippet_by_id", fake_get_snippet_by_id)

    app.state.llm_provider = _CitingProvider()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/explain", headers={"X-Auth-Token": AUTH_TOKEN}, json=_payload()
        )
        assert response.status_code == 200
        assert response.json()["citation"] is None
    finally:
        del app.state.llm_provider
```

Note `test_explain_omits_citation_when_rag_doc_id_is_none` reuses the shared `explain_client` fixture (from `conftest.py`) unmodified — its `_StubLLMProvider` never sets `rag_doc_id`, so this test needs no monkeypatching at all, and doubles as a regression check that adding the citation logic didn't change any existing behavior on that path.

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_explain.py -v`
Expected: only `test_explain_includes_citation_when_rag_doc_id_is_set` FAILS — after Step 5, `ExplainResponse.citation` exists as a field but `explain.py` never sets it yet, so it's always `None`; that test's `assert response.json()["citation"] == {...}` fails comparing `None == {...}`. The other two new tests PASS already, trivially: `citation` being unconditionally `None` before Step 8 already satisfies both `is None` assertions — they're regression guards for Step 8, not tests that need to go red first.

- [ ] **Step 8: Wire citation enrichment into `explain.py`**

Read the current file first (13 lines of imports + the `explain` handler). Add `RagCitation` to the existing `from baduk_backend.api.schemas import ExplainRequest, ExplainResponse` import line, and add the enrichment block between the existing `try/except` block (that produces `explanation, verified`) and the final `return`:

```python
    citation = None
    if explanation.rag_doc_id is not None:
        from baduk_backend.rag.retrieval import get_snippet_by_id

        snippet = await asyncio.to_thread(get_snippet_by_id, explanation.rag_doc_id)
        if snippet is not None:
            citation = RagCitation(
                doc_id=snippet.doc_id,
                title=snippet.title,
                source=snippet.source,
                text_snippet=snippet.text_snippet,
            )

    return ExplainResponse(finding=finding, explanation=explanation, verified=verified, citation=citation)
```

(This replaces the current final line `return ExplainResponse(finding=finding, explanation=explanation, verified=verified)`.) `get_snippet_by_id` is imported lazily inside the `if` block, not at module top level, so `api/explain.py` stays importable without the `[rag]` optional-dependency group installed when no finding ever has a `rag_doc_id` (which is always true when RAG isn't installed, since `llama.py` never sets it in that case). `asyncio.to_thread` matches the existing pattern already used for `verify_and_retry` two lines above — Chroma I/O is blocking and must not run on the event loop.

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_api_explain.py -v`
Expected: PASS (all tests, including the 3 new ones).

- [ ] **Step 10: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, same count as before plus 6 new tests (3 in `test_retrieval.py`, 3 in `test_api_explain.py`).

- [ ] **Step 11: Commit**

```bash
git add backend/src/baduk_backend/rag/retrieval.py backend/src/baduk_backend/api/schemas.py backend/src/baduk_backend/api/explain.py backend/tests/rag/test_retrieval.py backend/tests/test_api_explain.py
git commit -m "feat: add get_snippet_by_id and RAG citation enrichment on /api/explain"
```

---

### Task 2: Frontend — citation type + collapsible UI section

**Files:**
- Modify: `frontend/src/renderer/src/ipc/client.ts`
- Modify: `frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx`
- Modify: `frontend/src/renderer/assets/main.css`
- Modify: `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`

**Interfaces:**
- Consumes: the `citation: {doc_id, title, source, text_snippet} | null` JSON shape on `/api/explain`'s response (Task 1, already merged by the time this task runs).
- Produces: `RagCitation` TypeScript interface and `ExplainResponse.citation: RagCitation | null` (importable from `@renderer/ipc/client`). Last task in this plan — nothing downstream consumes this.

- [ ] **Step 1: Add the `RagCitation` type and `citation` field to `ipc/client.ts`**

Read the current file first to find the exact location of `Explanation`/`ExplainResponse` (currently: `export interface Explanation { summary: string; claims: Claim[] }` — do NOT touch this interface, it's unrelated to this change — followed a few lines later by `export interface ExplainResponse { finding: Finding | null; explanation: Explanation | null; verified: boolean | null; message: string | null }`). Add a new `RagCitation` interface immediately before `ExplainResponse`, and add `citation` as the last field:

```typescript
export interface RagCitation {
  doc_id: string
  title: string
  source: string
  text_snippet: string
}

export interface ExplainResponse {
  finding: Finding | null
  explanation: Explanation | null
  verified: boolean | null
  message: string | null
  citation: RagCitation | null
}
```

- [ ] **Step 2: Migrate all 7 existing `ExplainResponse` object literals in the test file to add `citation: null`**

`frontend/tests/renderer/components/LlmExplanationPanel.test.tsx` currently has 7 object literals matching the `ExplainResponse` shape (6 via `mockExplainPosition.mockResolvedValue({...})`, 1 via a direct `resolveExplain({...})` call) — after Step 1, `citation` becomes a required field on the TypeScript interface, so **every one of these 7 literals must gain a `citation: null` line**, or `pnpm run typecheck:web` fails. Find each occurrence (search the file for `mockExplainPosition.mockResolvedValue({` and `resolveExplain({`) and add `citation: null` as the last property in each object, e.g. the first one:

```typescript
mockExplainPosition.mockResolvedValue({
  finding: null,
  explanation: { summary: 'Тестовое объяснение', claims: [] },
  verified: true,
  message: null,
  citation: null
})
```

Apply the same one-line addition (`citation: null`) to all 6 other occurrences, matching each one's existing indentation and trailing-comma style exactly. Do not change any other part of these object literals.

- [ ] **Step 3: Run typecheck to verify the migration is complete**

Run: `cd frontend && pnpm run typecheck:web`
Expected: PASS (0 errors). If any object literal was missed, this fails with a TypeScript error naming the exact line — fix any remaining occurrence before continuing.

- [ ] **Step 4: Write the failing tests for the citation UI section**

Add to `frontend/tests/renderer/components/LlmExplanationPanel.test.tsx`, inside the `describe('LlmExplanationPanel', ...)` block, after the existing tests:

```typescript
  it('shows a collapsible citation section, closed by default, that opens when clicked', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Объяснение с цитатой', claims: [] },
      verified: true,
      message: null,
      citation: {
        doc_id: 'two-eyes-necessary',
        title: 'Два глаза',
        source: 'principles/two-eyes.md',
        text_snippet: 'Группа с двумя глазами не может быть захвачена.'
      }
    })

    const { getByText, container } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Два глаза', { exact: false })).toBeTruthy()
    })

    const details = container.querySelector(
      'details.llm-explanation-panel__citation'
    ) as HTMLDetailsElement
    expect(details).toBeTruthy()
    expect(details.open).toBe(false)

    const summary = details.querySelector('summary') as HTMLElement
    fireEvent.click(summary)
    expect(details.open).toBe(true)
  })

  it('omits the citation section entirely when the response has no citation', async () => {
    loadPosition()
    mockExplainPosition.mockResolvedValue({
      finding: null,
      explanation: { summary: 'Объяснение без цитаты', claims: [] },
      verified: true,
      message: null,
      citation: null
    })

    const { getByText, container } = render(<LlmExplanationPanel />)
    fireEvent.click(getByText('Объяснить эту позицию'))

    await waitFor(() => {
      expect(getByText('Объяснение без цитаты')).toBeTruthy()
    })
    expect(container.querySelector('.llm-explanation-panel__citation')).toBeNull()
  })
```

This test deliberately checks `HTMLDetailsElement.open` directly (before and after a click on the `<summary>` element specifically) rather than asserting on the visibility of `text_snippet` via `getByText`/`queryByText` — text inside a closed `<details>` stays present in the DOM (jsdom does not strip it), so a text-presence assertion would not reliably distinguish "collapsed" from "expanded".

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: only `'shows a collapsible citation section, closed by default, that opens when clicked'` FAILS — `details` is `null` (`expect(details).toBeTruthy()` fails) since no citation section exists in the component yet. `'omits the citation section entirely...'` PASSES already, trivially: with no citation-rendering code at all, `container.querySelector('.llm-explanation-panel__citation')` is already `null` before Step 6 — it's a regression guard for Step 6, not a test that needs to go red first. All 9 pre-existing tests still PASS (Step 2's migration didn't change any rendered behavior, only added an unused-so-far field to the mocks).

- [ ] **Step 6: Add the citation section to `LlmExplanationPanel.tsx`**

Read the current file first (imports `ExplainResponse` type already; the component body ends with the `summary` block inside the `status === 'done' && result?.explanation` fragment). Add `RagCitation` to nothing (not needed as a separate import — `result.citation` is already typed via `ExplainResponse`), and add a new block immediately after the existing `<div class="llm-explanation-panel__summary">{result.explanation.summary}</div>` line, still inside the same `{status === 'done' && result?.explanation && (<> ... </>)}` fragment:

```tsx
          {result.citation && (
            <details class="llm-explanation-panel__citation">
              <summary>
                {result.citation.title}{' '}
                <span class="llm-explanation-panel__citation-source">({result.citation.source})</span>
              </summary>
              <div class="llm-explanation-panel__citation-text">{result.citation.text_snippet}</div>
            </details>
          )}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd frontend && pnpm exec vitest run tests/renderer/components/LlmExplanationPanel.test.tsx`
Expected: PASS (all 11 tests — 9 pre-existing + 2 new).

- [ ] **Step 8: Add minimal CSS for the new classes**

In `frontend/src/renderer/assets/main.css`, find the existing `.llm-explanation-panel__*` block (around line 385, ending with `.llm-explanation-panel__message, .llm-explanation-panel__summary { margin-top: 8px; white-space: pre-wrap; }`). Add immediately after it:

```css
.llm-explanation-panel__citation {
  margin-top: 8px;
  font-size: 12px;
}
.llm-explanation-panel__citation summary {
  cursor: pointer;
}
.llm-explanation-panel__citation-source {
  opacity: 0.7;
}
.llm-explanation-panel__citation-text {
  margin-top: 4px;
  white-space: pre-wrap;
}
```

- [ ] **Step 9: Run the full frontend suite and typecheck to confirm no regressions**

Run: `cd frontend && pnpm exec vitest run`
Expected: PASS, same count as before plus 2 new tests.

Run: `cd frontend && pnpm run typecheck:web`
Expected: PASS (0 errors).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/renderer/src/ipc/client.ts frontend/src/renderer/src/analysis/LlmExplanationPanel.tsx frontend/src/renderer/assets/main.css frontend/tests/renderer/components/LlmExplanationPanel.test.tsx
git commit -m "feat: show RAG citation as a collapsible section in LlmExplanationPanel"
```

---

## Manual verification (after the plan is complete)

With a real `BADUK_LLAMA_MODEL_PATH` and a real, ingested `backend/rag_store/` present, run the app end-to-end (`BADUK_BACKEND_COMMAND` pointing at the backend sidecar, `pnpm exec electron-vite dev`), open a game, click "Объяснить эту позицию" on a position likely to match a knowledge-base card (e.g. one with an obvious weak group lacking eye shape), and confirm: when the model cites a source, a collapsible section with a real title/source appears under the summary and expands on click; when it doesn't, the panel looks exactly as it did before this plan.
