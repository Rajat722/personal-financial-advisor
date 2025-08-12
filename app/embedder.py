"""
Handles text embedding using sentence-transformers.
This is used for both portfolio terms and article text.
"""

from sentence_transformers import SentenceTransformer

# Load the sentence-transformers model only once at module level
model = SentenceTransformer("all-MiniLM-L6-v2")

def embed_text(text: str) -> list:
    return model.encode(text).tolist()