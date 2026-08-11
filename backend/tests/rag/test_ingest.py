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
