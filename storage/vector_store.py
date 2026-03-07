# vector_store.py

import chromadb
from chromadb.config import Settings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = str(ROOT / "chroma_store")

# Create a persistent client that saves data to disk
client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings(anonymized_telemetry=False))


def get_portfolio_collection():
    """Return the portfolio ChromaDB collection."""
    return client.get_or_create_collection(name="portfolio")


def get_article_collection():
    """Return the articles ChromaDB collection."""
    return client.get_or_create_collection(name="articles")


def upsert_to_collection(collection_name: str, ids, documents, embedding, metadata) -> None:
    """
    Upsert a document and its embedding into a named ChromaDB collection.

    Args:
        collection_name: The name of the collection ("portfolio" or "articles").
        ids: Unique identifier(s) for the document(s).
        documents: Raw text of the article or portfolio term.
        embedding: Dense vector embedding (must not be None).
        metadata: Additional info (title, URL, summary, timestamp).

    Raises:
        ValueError: If embedding is None or contains None values.
    """
    ids = ids if isinstance(ids, list) else [ids]
    documents = documents if isinstance(documents, list) else [documents]
    embedding = embedding if isinstance(embedding, list) and isinstance(embedding[0], (list, tuple)) else [embedding]
    metadata = metadata if isinstance(metadata, list) else [metadata]

    # Guard: reject None embeddings before they corrupt the store
    for i, emb in enumerate(embedding):
        if emb is None:
            raise ValueError(f"Embedding at index {i} is None — refusing to upsert to '{collection_name}'")

    assert len(ids) == len(documents) == len(embedding) == len(metadata)
    client.get_or_create_collection(name=collection_name).upsert(
        ids=ids, documents=documents, embeddings=embedding, metadatas=metadata
    )


def find_similar_in_portfolio(query_embedding: list, top_k: int = 5) -> dict:
    """
    Search for the most semantically similar portfolio terms to the input embedding.

    Args:
        query_embedding: Embedding of the article text.
        top_k: Number of top matches to return.

    Returns:
        Matching documents, metadatas, and cosine distances.
    """
    collection = get_portfolio_collection()
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )


def find_recent_articles(query_embedding: list, start_ts: int, end_ts: int, top_k: int = 20) -> dict:
    """Query articles collection filtered by a UTC timestamp range."""
    col = get_article_collection()
    return col.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"published_ts": {"$gte": int(start_ts), "$lte": int(end_ts)}},
        include=["ids", "documents", "metadatas", "distances"]
    )


def _format_results(res: dict) -> list:
    """Flatten a raw ChromaDB query result into a list of hit dicts."""
    hits = []
    for i in range(len(res["ids"][0])):
        hits.append({
            "id": res["ids"][0][i],
            "similarity": 1 - res["distances"][0][i],
            "metadata": res["metadatas"][0][i],
            "document": res["documents"][0][i],
        })
    return hits


# Aliases used across the codebase
add_article_to_collection = upsert_to_collection
add_to_collection = upsert_to_collection
