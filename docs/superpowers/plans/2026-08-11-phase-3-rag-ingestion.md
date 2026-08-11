# Phase 3 RAG Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest the user's existing `Baduk-knowledge-base` (452 markdown cards) into a local Chroma vector store and provide a working `retrieve_knowledge(query, top_k)` function over it — no LLM-pipeline or frontend changes in this slice.

**Architecture:** A pure card-parser (frontmatter + body, no heavy deps) feeds a manual, on-demand ingestion script that embeds card bodies with BGE-M3 and writes them into a persistent local Chroma collection (`backend/rag_store/`). `retrieve_knowledge()` embeds a query with the same model and reads from that collection. Both `run_ingest()` and `retrieve_knowledge()` accept an injectable `embedding_model` parameter so tests never need to download the real ~2GB model.

**Tech Stack:** Python 3.12, `pyyaml` (frontmatter parsing), `sentence-transformers` + `BAAI/bge-m3` (local embeddings), `chromadb` (persistent local vector store) — all three new, added to `backend/pyproject.toml`'s `[project.optional-dependencies] rag` group (mirrors the existing `llama` optional group for `llama-cpp-python`).

## Global Constraints

- Branch `phase-3-rag-ingestion`, forked from `main`. Never commit directly to `main`.
- New code lives entirely under `backend/src/baduk_backend/rag/` (new package, sibling to `api/`, `board/`, `config/`, `feature_extraction/`, `llm/`) and `backend/tests/rag/` — no changes to any existing file outside `backend/pyproject.toml` (new dependency entries only).
- `chromadb`/`sentence_transformers`/`pyyaml` imports are **lazy** (inside functions, not at module top level) so `import baduk_backend` never requires them. Every test file that needs them starts with `pytest.importorskip(...)`.
- `RagSnippet.text_snippet` is the **full** card body, never truncated.
- Only cards with frontmatter `status: reviewed` are ingested; others are parsed successfully (so their `status` is inspectable) but excluded by the ingestion loop, not by the parser.
- `retrieve_knowledge()` has exactly the signature `retrieve_knowledge(query: str, top_k: int = 3, ...) -> list[RagSnippet]` — no `category` filter, no `board_context` parameter (explicitly deferred per the spec).
- Ingestion is a full rebuild every run (delete + recreate the Chroma collection) — no incremental sync.
- Out of scope for this plan (do not implement): wiring `retrieve_knowledge` into `prompts.py`/`explain.py`/any LLM provider, anti-hallucination `doc_id` verification, frontend citations UI, `category` filtering, open-source content sources other than `Baduk-knowledge-base`.
- Full spec: `docs/superpowers/specs/2026-08-11-phase-3-rag-ingestion-design.md`.
- Verified external APIs used in this plan (checked against current docs/model card, not memory): `chromadb.PersistentClient(path=...)`, `client.create_collection(name=..., configuration={"hnsw": {"space": "cosine"}})`, `collection.add(ids=, embeddings=, documents=, metadatas=)`, `collection.query(query_embeddings=[[...]], n_results=N)` returning `{"ids": [[...]], "documents": [[...]], "metadatas": [[...]], "distances": [[...]]}` (one outer list per query embedding); cosine `distance = 1 - cosine_similarity`, so `relevance_score = 1 - distance`; `sentence_transformers.SentenceTransformer("BAAI/bge-m3").encode(list_of_str)` returns embeddings (call `.tolist()` before passing to Chroma, which expects plain lists).

---

### Task 1: Card parser

**Files:**
- Create: `backend/src/baduk_backend/rag/__init__.py` (empty)
- Create: `backend/src/baduk_backend/rag/schemas.py`
- Create: `backend/src/baduk_backend/rag/cards.py`
- Create: `backend/tests/rag/__init__.py` (empty)
- Create: `backend/tests/rag/fixtures/valid_principle.md`
- Create: `backend/tests/rag/fixtures/valid_draft.md`
- Create: `backend/tests/rag/fixtures/missing_field.md`
- Create: `backend/tests/rag/fixtures/missing_title.md`
- Create: `backend/tests/rag/test_cards.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Produces: `ParsedCard` (pydantic model: `doc_id: str, type: str, category: str, status: str, title: str, source: str, body: str`) and `parse_card_file(path: Path, wiki_root: Path) -> ParsedCard` — both importable from `baduk_backend.rag.schemas` / `baduk_backend.rag.cards`. Task 2 imports and calls `parse_card_file` directly.

- [ ] **Step 1: Add `pyyaml` to `pyproject.toml`**

In `backend/pyproject.toml`, add a new `[project.optional-dependencies]` entry (the file currently has `llama = ["llama-cpp-python>=0.3.34"]` under that section — add a sibling key, don't touch the `llama` line):

```toml
[project.optional-dependencies]
llama = ["llama-cpp-python>=0.3.34"]
rag = ["pyyaml>=6.0"]
```

Run: `cd backend && .venv\Scripts\python.exe -m pip install pyyaml>=6.0`
Expected: installs successfully (pure-Python, no build issues).

- [ ] **Step 2: Write the failing tests**

Create the four fixture files first.

`backend/tests/rag/fixtures/valid_principle.md`:
```markdown
---
type: principle
category: тест
status: reviewed
tags: [пример]
created: 2026-01-01
updated: 2026-01-01
---

# Тестовый принцип

Обоснование: потому что так проще объяснить в тесте.
```

`backend/tests/rag/fixtures/valid_draft.md`:
```markdown
---
type: mistake
category: тест
status: draft
tags: []
created: 2026-01-01
updated: 2026-01-01
---

# Тестовая ошибка

Текст ошибки.
```

`backend/tests/rag/fixtures/missing_field.md`:
```markdown
---
type: principle
status: reviewed
---

# Без категории

Текст.
```

`backend/tests/rag/fixtures/missing_title.md`:
```markdown
---
type: principle
category: тест
status: reviewed
---

Текст без заголовка.
```

Create `backend/tests/rag/test_cards.py`:

```python
from pathlib import Path

import pytest

from baduk_backend.rag.cards import parse_card_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_card_file_extracts_all_fields():
    card = parse_card_file(FIXTURES / "valid_principle.md", FIXTURES)

    assert card.doc_id == "valid_principle"
    assert card.type == "principle"
    assert card.category == "тест"
    assert card.status == "reviewed"
    assert card.title == "Тестовый принцип"
    assert card.source == "valid_principle.md"
    assert "Обоснование" in card.body
    assert not card.body.startswith("---")


def test_parse_card_file_preserves_non_reviewed_status():
    card = parse_card_file(FIXTURES / "valid_draft.md", FIXTURES)

    assert card.status == "draft"


def test_parse_card_file_raises_on_missing_frontmatter_field():
    with pytest.raises(ValueError, match="category"):
        parse_card_file(FIXTURES / "missing_field.md", FIXTURES)


def test_parse_card_file_raises_on_missing_title():
    with pytest.raises(ValueError, match="Title"):
        parse_card_file(FIXTURES / "missing_title.md", FIXTURES)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_cards.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'baduk_backend.rag'`).

- [ ] **Step 4: Create the empty package init files**

Create `backend/src/baduk_backend/rag/__init__.py` (empty file).
Create `backend/tests/rag/__init__.py` (empty file).

- [ ] **Step 5: Write `rag/schemas.py`**

```python
from pydantic import BaseModel


class ParsedCard(BaseModel):
    doc_id: str
    type: str
    category: str
    status: str
    title: str
    source: str
    body: str
```

- [ ] **Step 6: Write `rag/cards.py`**

```python
import re
from pathlib import Path

from baduk_backend.rag.schemas import ParsedCard

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def parse_card_file(path: Path, wiki_root: Path) -> ParsedCard:
    import yaml

    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"malformed card {path}: no YAML frontmatter block found")

    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()

    for field in ("type", "category", "status"):
        if field not in frontmatter:
            raise ValueError(f"malformed card {path}: missing frontmatter field '{field}'")

    title_match = _TITLE_RE.search(body)
    if not title_match:
        raise ValueError(f"malformed card {path}: no '# Title' heading found in body")

    return ParsedCard(
        doc_id=path.stem,
        type=frontmatter["type"],
        category=frontmatter["category"],
        status=frontmatter["status"],
        title=title_match.group(1).strip(),
        source=str(path.relative_to(wiki_root)).replace("\\", "/"),
        body=body,
    )
```

Note: `import yaml` is deliberately inside the function, not at module top level, per the Global Constraints lazy-import rule (even though `pyyaml` is lightweight and unlikely to cause install issues like `llama-cpp-python` did, this keeps the pattern uniform across the whole `rag/` package so no file in it requires optional deps just to be imported).

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_cards.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Run the full backend suite to confirm no regressions**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, same count as before plus 4 new tests.

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/src/baduk_backend/rag/__init__.py backend/src/baduk_backend/rag/schemas.py backend/src/baduk_backend/rag/cards.py backend/tests/rag/__init__.py backend/tests/rag/fixtures/ backend/tests/rag/test_cards.py
git commit -m "feat: add RAG card parser (frontmatter + body extraction)"
```

---

### Task 2: Ingestion script

**Files:**
- Create: `backend/src/baduk_backend/rag/store.py`
- Create: `backend/src/baduk_backend/rag/ingest.py`
- Create: `backend/tests/rag/fixtures/kb_root/knowledge-base/wiki/principles/valid_principle.md`
- Create: `backend/tests/rag/fixtures/kb_root/knowledge-base/wiki/mistakes/valid_draft.md`
- Create: `backend/tests/rag/fixtures/kb_root/knowledge-base/wiki/exercises/valid_exercise.md`
- Create: `backend/tests/rag/test_ingest.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: `ParsedCard`, `parse_card_file` (Task 1).
- Produces: `run_ingest(knowledge_base_path: Path, store_path: Path = DEFAULT_STORE_PATH, embedding_model=None) -> int` (returns count of ingested cards) and, from `store.py`: `DEFAULT_STORE_PATH: Path`, `COLLECTION_NAME: str`, `get_chroma_client(store_path: Path)`, `get_embedding_model()` — all importable from `baduk_backend.rag.store`/`baduk_backend.rag.ingest`. Task 3's `retrieve_knowledge()` imports `DEFAULT_STORE_PATH`, `COLLECTION_NAME`, `get_chroma_client`, `get_embedding_model` from `store.py` (same names, same module).

- [ ] **Step 1: Add `sentence-transformers`/`chromadb` to `pyproject.toml`**

In `backend/pyproject.toml`, extend the `rag` optional dependency list (currently `rag = ["pyyaml>=6.0"]` from Task 1 — add to the same list, don't create a second `rag` key):

```toml
rag = ["pyyaml>=6.0", "sentence-transformers>=3.0.0", "chromadb>=0.5.0"]
```

Run: `cd backend && .venv\Scripts\python.exe -m pip install "sentence-transformers>=3.0.0" "chromadb>=0.5.0"`
Expected: installs successfully (may take a few minutes — `sentence-transformers` pulls in `torch`).

- [ ] **Step 2: Write the failing tests**

Create the fixture tree (mirrors `Baduk-knowledge-base`'s real layout: `knowledge-base/wiki/{principles,mistakes,exercises}/*.md`).

`backend/tests/rag/fixtures/kb_root/knowledge-base/wiki/principles/valid_principle.md`:
```markdown
---
type: principle
category: тест
status: reviewed
---

# Тестовый принцип

Текст принципа.
```

`backend/tests/rag/fixtures/kb_root/knowledge-base/wiki/mistakes/valid_draft.md`:
```markdown
---
type: mistake
category: тест
status: draft
---

# Тестовая ошибка (черновик)

Этот файл не должен попасть в индекс - status draft, не reviewed.
```

`backend/tests/rag/fixtures/kb_root/knowledge-base/wiki/exercises/valid_exercise.md`:
```markdown
---
type: exercise
category: тест
status: reviewed
---

# Тестовое упражнение

Текст упражнения.
```

Create `backend/tests/rag/test_ingest.py`:

```python
from pathlib import Path

import pytest

pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")

from baduk_backend.rag.ingest import run_ingest  # noqa: E402
from baduk_backend.rag.store import COLLECTION_NAME, get_chroma_client  # noqa: E402

KB_ROOT = Path(__file__).parent / "fixtures" / "kb_root"


class _FakeEmbeddingModel:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, float(i), 0.0] for i, _ in enumerate(texts)]


def test_run_ingest_writes_only_reviewed_cards(tmp_path):
    store_path = tmp_path / "rag_store"

    count = run_ingest(
        knowledge_base_path=KB_ROOT,
        store_path=store_path,
        embedding_model=_FakeEmbeddingModel(),
    )

    assert count == 2  # principle + exercise are reviewed; mistake is draft, excluded

    client = get_chroma_client(store_path)
    collection = client.get_collection(name=COLLECTION_NAME)
    result = collection.get(ids=["valid_principle"])
    assert result["ids"] == ["valid_principle"]
    assert result["metadatas"][0]["title"] == "Тестовый принцип"
    assert result["metadatas"][0]["type"] == "principle"
    assert result["metadatas"][0]["category"] == "тест"
    assert result["metadatas"][0]["source"] == "principles/valid_principle.md"

    got_draft = collection.get(ids=["valid_draft"])
    assert got_draft["ids"] == []  # draft card was never added - collection.get() on a
    # missing id returns an empty result, it does not raise


def test_run_ingest_is_a_full_rebuild(tmp_path):
    store_path = tmp_path / "rag_store"
    fake = _FakeEmbeddingModel()

    first = run_ingest(knowledge_base_path=KB_ROOT, store_path=store_path, embedding_model=fake)
    second = run_ingest(knowledge_base_path=KB_ROOT, store_path=store_path, embedding_model=fake)

    assert first == second == 2  # re-running does not duplicate entries
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_ingest.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'baduk_backend.rag.ingest'`).

- [ ] **Step 4: Write `rag/store.py`**

```python
from pathlib import Path

DEFAULT_STORE_PATH = Path(__file__).resolve().parents[3] / "rag_store"
COLLECTION_NAME = "knowledge_base"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"


def get_chroma_client(store_path: Path = DEFAULT_STORE_PATH):
    import chromadb

    return chromadb.PersistentClient(path=str(store_path))


def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)
```

(`parents[3]` from `backend/src/baduk_backend/rag/store.py`: `rag/` → `baduk_backend/` → `src/` → `backend/` — so `DEFAULT_STORE_PATH` resolves to `backend/rag_store/`, matching the spec.)

- [ ] **Step 5: Write `rag/ingest.py`**

```python
import os
from pathlib import Path

from baduk_backend.rag.cards import parse_card_file
from baduk_backend.rag.store import (
    COLLECTION_NAME,
    DEFAULT_STORE_PATH,
    get_chroma_client,
    get_embedding_model,
)

_CARD_SUBDIRS = ("principles", "mistakes", "exercises")


def run_ingest(
    knowledge_base_path: Path,
    store_path: Path = DEFAULT_STORE_PATH,
    embedding_model=None,
) -> int:
    wiki_root = knowledge_base_path / "knowledge-base" / "wiki"

    cards = []
    for subdir in _CARD_SUBDIRS:
        for md_path in sorted((wiki_root / subdir).glob("*.md")):
            card = parse_card_file(md_path, wiki_root)
            if card.status != "reviewed":
                continue
            cards.append(card)

    model = embedding_model or get_embedding_model()
    raw_embeddings = model.encode([card.body for card in cards])
    # Native SentenceTransformer.encode() returns a numpy array; iterating it
    # yields numpy scalar floats, which Chroma's embeddings= param does not
    # reliably accept - convert explicitly to plain Python floats.
    embeddings = [[float(x) for x in vector] for vector in raw_embeddings]

    client = get_chroma_client(store_path)
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
    )

    if cards:
        collection.add(
            ids=[card.doc_id for card in cards],
            embeddings=embeddings,
            documents=[card.body for card in cards],
            metadatas=[
                {
                    "type": card.type,
                    "category": card.category,
                    "title": card.title,
                    "source": card.source,
                }
                for card in cards
            ],
        )

    return len(cards)


def main() -> None:
    raw_path = os.environ.get("BADUK_KNOWLEDGE_BASE_PATH")
    if not raw_path:
        raise RuntimeError("BADUK_KNOWLEDGE_BASE_PATH env var must be set to run ingestion")
    count = run_ingest(Path(raw_path))
    print(f"Ingested {count} cards into {DEFAULT_STORE_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_ingest.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/src/baduk_backend/rag/store.py backend/src/baduk_backend/rag/ingest.py backend/tests/rag/fixtures/kb_root/ backend/tests/rag/test_ingest.py
git commit -m "feat: add RAG ingestion script (BGE-M3 embeddings into Chroma)"
```

---

### Task 3: `retrieve_knowledge()` + integration test

**Files:**
- Modify: `backend/src/baduk_backend/rag/schemas.py`
- Create: `backend/src/baduk_backend/rag/retrieval.py`
- Create: `backend/tests/rag/test_retrieval.py`
- Create: `backend/tests/rag/test_ingest_and_retrieve_integration.py`

**Interfaces:**
- Consumes: `DEFAULT_STORE_PATH`, `COLLECTION_NAME`, `get_chroma_client`, `get_embedding_model` (Task 2's `store.py`); `run_ingest` (Task 2's `ingest.py`, used only by the integration test).
- Produces: `RagSnippet` (pydantic model, added to `schemas.py`) and `retrieve_knowledge(query: str, top_k: int = 3, store_path: Path = DEFAULT_STORE_PATH, embedding_model=None) -> list[RagSnippet]` — this is the deliverable the spec's "Критерии готовности" checks against; no later task in this plan consumes it (last task).

- [ ] **Step 1: Write the failing unit tests**

Create `backend/tests/rag/test_retrieval.py`:

```python
from pathlib import Path

import pytest

pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")

from baduk_backend.rag.ingest import run_ingest  # noqa: E402
from baduk_backend.rag.retrieval import retrieve_knowledge  # noqa: E402

KB_ROOT = Path(__file__).parent / "fixtures" / "kb_root"


class _FakeEmbeddingModel:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, float(i), 0.0] for i, _ in enumerate(texts)]


def test_retrieve_knowledge_returns_snippets_from_store(tmp_path):
    store_path = tmp_path / "rag_store"
    fake = _FakeEmbeddingModel()
    run_ingest(knowledge_base_path=KB_ROOT, store_path=store_path, embedding_model=fake)

    snippets = retrieve_knowledge("запрос", top_k=2, store_path=store_path, embedding_model=fake)

    assert len(snippets) <= 2
    doc_ids = {s.doc_id for s in snippets}
    assert doc_ids <= {"valid_principle", "valid_exercise"}
    for snippet in snippets:
        assert isinstance(snippet.relevance_score, float)
        assert snippet.text_snippet  # full body, non-empty
        assert snippet.title
        assert snippet.source


def test_retrieve_knowledge_raises_when_store_missing(tmp_path):
    with pytest.raises(RuntimeError, match="ingestion"):
        retrieve_knowledge("запрос", store_path=tmp_path / "does_not_exist")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_retrieval.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'baduk_backend.rag.retrieval'`).

- [ ] **Step 3: Add `RagSnippet` to `rag/schemas.py`**

Append to the existing file (do not remove `ParsedCard`):

```python
class RagSnippet(BaseModel):
    doc_id: str
    title: str
    source: str
    text_snippet: str
    relevance_score: float
```

- [ ] **Step 4: Write `rag/retrieval.py`**

```python
from pathlib import Path

from baduk_backend.rag.schemas import RagSnippet
from baduk_backend.rag.store import (
    COLLECTION_NAME,
    DEFAULT_STORE_PATH,
    get_chroma_client,
    get_embedding_model,
)


def retrieve_knowledge(
    query: str,
    top_k: int = 3,
    store_path: Path = DEFAULT_STORE_PATH,
    embedding_model=None,
) -> list[RagSnippet]:
    if not store_path.exists():
        raise RuntimeError(
            f"RAG store not found at {store_path} - run ingestion first: "
            "python -m baduk_backend.rag.ingest"
        )

    client = get_chroma_client(store_path)
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError(
            f"RAG collection '{COLLECTION_NAME}' not found in {store_path} - run ingestion first: "
            "python -m baduk_backend.rag.ingest"
        ) from exc

    model = embedding_model or get_embedding_model()
    # Same float-coercion note as ingest.py's run_ingest() - see there for why.
    query_embedding = [[float(x) for x in vector] for vector in model.encode([query])]

    results = collection.query(query_embeddings=query_embedding, n_results=top_k)

    snippets = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        snippets.append(
            RagSnippet(
                doc_id=doc_id,
                title=metadata["title"],
                source=metadata["source"],
                text_snippet=document,
                relevance_score=1.0 - distance,
            )
        )
    return snippets
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/rag/test_retrieval.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Write the integration test**

Create `backend/tests/rag/test_ingest_and_retrieve_integration.py`:

```python
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_ingest_and_retrieve_real_knowledge_base():
    kb_path = os.environ.get("BADUK_KNOWLEDGE_BASE_PATH")
    if not kb_path:
        pytest.skip("BADUK_KNOWLEDGE_BASE_PATH not set")
    pytest.importorskip("chromadb")
    pytest.importorskip("sentence_transformers")

    from baduk_backend.rag.ingest import run_ingest
    from baduk_backend.rag.retrieval import retrieve_knowledge

    count = run_ingest(Path(kb_path))
    assert count > 0

    snippets = retrieve_knowledge("два глаза необходимы для безусловной жизни группы", top_k=3)

    doc_ids = [snippet.doc_id for snippet in snippets]
    assert "two-eyes-necessary-for-unconditional-life" in doc_ids
```

This test writes to the real default `backend/rag_store/` location (no `store_path` override) — that is intentional, it exercises the exact same path a real user would run (`python -m baduk_backend.rag.ingest`), and doubles as manual verification of the spec's "Критерии готовности".

- [ ] **Step 7: Run the full backend suite (non-integration)**

Run: `cd backend && .venv\Scripts\python.exe -m pytest -v`
Expected: PASS, no regressions. The new integration test is deselected by the existing `addopts = "-m \"not integration\""` default.

- [ ] **Step 8: Commit**

```bash
git add backend/src/baduk_backend/rag/schemas.py backend/src/baduk_backend/rag/retrieval.py backend/tests/rag/test_retrieval.py backend/tests/rag/test_ingest_and_retrieve_integration.py
git commit -m "feat: add retrieve_knowledge() over the RAG store, plus real end-to-end integration test"
```

---

## Manual verification (after the plan is complete)

Run the integration test with a real `BADUK_KNOWLEDGE_BASE_PATH` pointing at the user's `Baduk-knowledge-base` checkout:

```powershell
$env:BADUK_KNOWLEDGE_BASE_PATH = "C:\GithubProject\Baduk-knowledge-base"
cd backend
.venv\Scripts\python.exe -m pytest tests/rag/test_ingest_and_retrieve_integration.py -v -m integration
```

Expected: `run_ingest` reports a count close to 452 (minus any non-`reviewed` cards), and the known-query assertion passes. This is the same live check the spec's "Критерии готовности" describes.
