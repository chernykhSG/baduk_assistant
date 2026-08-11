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
