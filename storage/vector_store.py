# vector_store.py

import chromadb
from chromadb.config import Settings

import os

project_root = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(project_root, "chroma_store")
os.makedirs(CHROMA_DIR, exist_ok=True)

# Create a persistent client that saves data to disk
client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings(anonymized_telemetry=False))


# Load or create the 'portfolio' collection (like a table in SQL)
def get_portfolio_collection():
    return client.get_or_create_collection(name="portfolio")

def get_article_collection():
    return client.get_or_create_collection(name="articles")

def get_context_collection():
    return client.get_or_create_collection(name="context")

# Function to add a document + embedding to the vector store
# Add a document + embedding to the specified collection
def upsert_to_collection(collection_name, ids, documents, embedding, metadata):
    """
    Adds a new document and its embedding to a ChromaDB collection.

    Args:
        collection_name (str): The name of the collection ("portfolio" or "articles").
        doc_id (str): Unique identifier for the document.
        text (str): Raw text of the article or portfolio term.
        embedding (list): Dense vector embedding.
        metadata (dict): Additional info (title, URL, summary, timestamp).
    """
    ids = ids if isinstance(ids, list) else [ids]
    documents = documents if isinstance(documents, list) else [documents]
    embedding = embedding if isinstance(embedding, list) and isinstance(embedding[0], (list, tuple)) else [embedding]
    metadata = metadata if isinstance(metadata, list) else [metadata]
    assert len(ids) == len(documents) == len(embedding) == len(metadata)
    client.get_or_create_collection(name=collection_name).upsert(
        ids=ids, documents=documents, embeddings=embedding, metadatas=metadata
    )

# Query portfolio collection for semantic similarity
def find_similar_in_portfolio(query_embedding, top_k=5):
    """
    Searches for the most semantically similar portfolio terms to the input embedding.

    Args:
        query_embedding (list): Embedding of the article text.
        top_k (int): Number of top matches to return.

    Returns:
        dict: Matching documents, metadatas, and similarity scores.
    """
    collection = get_portfolio_collection()

    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k, 
        include=["ids","documents","metadatas","distances"]
    )


def find_recent_articles(query_embedding, start_ts, end_ts, top_k=20):
    col = get_article_collection()
    return col.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"published_ts": {"$gte": int(start_ts), "$lte": int(end_ts)}},
        include=["ids","documents","metadatas","distances"]
    )

def _format_results(res):
    hits=[]
    for i in range(len(res["ids"][0])):
        hits.append({
            "id": res["ids"][0][i],
            "similarity": 1 - res["distances"][0][i],
            "metadata": res["metadatas"][0][i],
            "document": res["documents"][0][i],
        })
    return hits

