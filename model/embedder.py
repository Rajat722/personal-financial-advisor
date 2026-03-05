# embedder.py

"""
Handles text embedding using sentence-transformers.
This is used for both portfolio terms and article text.
"""

from sentence_transformers import SentenceTransformer
import google.generativeai as genai

from typing import List
from tenacity import retry, wait_exponential, stop_after_attempt

from core.logging import get_logger

log = get_logger("log")
# Load the sentence-transformers model only once at module level


def all_mini_embed_text(text: str) -> list:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(text).tolist()


class GeminiEmbedder:
    def __init__(self, model_name: str = "models/embedding-001"):
        self.model = genai.get_model(model_name)

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
    def embed_text(self, text: str) -> List[float]:
        """Embed a single string"""
        response = self.model.embed_content(
            content=text,
            task_type="retrieval_document"
        )
        return response["embedding"]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of strings one at a time"""
        embeddings = []
        for idx, text in enumerate(texts):
            try:
                log.info(f"Embedding text {idx + 1}/{len(texts)}")
                embedding = self.embed_text(text)
                embeddings.append(embedding)
            except Exception as e:
                log.info(f"❌ Failed to embed: {e}")
                log.info("Safely failing over to all-MiniLM-L6-v2")
                all_mini_embeddings = all_mini_embed_text(text=text)
                log.info(f"Checking if all_mini_embeddings is empty | size: {len(all_mini_embeddings)}")
                embeddings.append(all_mini_embeddings) 
        return embeddings
