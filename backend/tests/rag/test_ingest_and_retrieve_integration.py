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
