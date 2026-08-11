from pathlib import Path

from baduk_backend.rag.schemas import RagSnippet
from baduk_backend.rag.store import (
    COLLECTION_NAME,
    DEFAULT_STORE_PATH,
    get_chroma_client,
    get_embedding_model,
    to_float_vectors,
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
    from chromadb.errors import NotFoundError

    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except NotFoundError as exc:
        raise RuntimeError(
            f"RAG collection '{COLLECTION_NAME}' not found in {store_path} - run ingestion first: "
            "python -m baduk_backend.rag.ingest"
        ) from exc

    model = embedding_model or get_embedding_model()
    query_embedding = to_float_vectors(model.encode([query]))

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
