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
