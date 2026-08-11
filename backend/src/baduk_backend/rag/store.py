from pathlib import Path

DEFAULT_STORE_PATH = Path(__file__).resolve().parents[3] / "rag_store"
COLLECTION_NAME = "knowledge_base"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"


def get_chroma_client(store_path: Path = DEFAULT_STORE_PATH):
    import chromadb

    return chromadb.PersistentClient(path=str(store_path))


def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")


def to_float_vectors(raw_embeddings) -> list[list[float]]:
    # SentenceTransformer.encode() returns a numpy array (or a list of numpy
    # arrays); iterating it yields numpy scalar floats, which Chroma's
    # embeddings=/query_embeddings= params do not reliably accept - convert
    # explicitly to plain Python floats.
    return [[float(x) for x in vector] for vector in raw_embeddings]
