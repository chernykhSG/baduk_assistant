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

    assert len(snippets) == 2
    doc_ids = {s.doc_id for s in snippets}
    assert doc_ids == {"valid_principle", "valid_exercise"}
    for snippet in snippets:
        assert isinstance(snippet.relevance_score, float)
        assert snippet.text_snippet  # full body, non-empty
        assert snippet.title
        assert snippet.source


def test_retrieve_knowledge_raises_when_store_missing(tmp_path):
    with pytest.raises(RuntimeError, match="ingestion"):
        retrieve_knowledge("запрос", store_path=tmp_path / "does_not_exist")
