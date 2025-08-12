# vector_store.py

import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings

import os

project_root = os.path.dirname(os.path.abspath(__file__))

# Create a persistent client that saves data to disk
client = chromadb.PersistentClient(path=os.path.join(project_root, "chroma_store"), settings=Settings(anonymized_telemetry=False))

# Load or create the 'portfolio' collection (like a table in SQL)
def get_portfolio_collection():
    return client.get_or_create_collection(name="portfolio")

# Load or create the 'articles' collection (like a table in SQL)
def get_article_collection():
    return client.get_or_create_collection(name="articles")

# Load or create the 'context' collection (like a table in SQL)
def get_context_collection():
    return client.get_or_create_collection(name="context")

# Function to add a document + embedding to the vector store
# Add a document + embedding to the specified collection
def add_article_to_collection(collection_name, doc_id, text, embedding, metadata):
    """
    Adds a new document and its embedding to a ChromaDB collection.

    Args:
        collection_name (str): The name of the collection ("portfolio" or "articles").
        doc_id (str): Unique identifier for the document.
        text (str): Raw text of the article or portfolio term.
        embedding (list): Dense vector embedding.
        metadata (dict): Additional info (title, URL, summary, timestamp).
    """
    collection = client.get_or_create_collection(name=collection_name)
    collection.add(
        ids=[doc_id],
        documents=[text],
        embeddings=[embedding],
        metadatas=[metadata]
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
    return collection.query(query_embeddings=[query_embedding], n_results=top_k)