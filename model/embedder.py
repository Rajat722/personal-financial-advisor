# embedder.py

"""
Handles text embedding using Google Gemini gemini-embedding-001 via the google-genai SDK.
Used for both portfolio terms and article text.
"""

import time
from dotenv import load_dotenv
from google import genai
from google.genai.types import EmbedContentConfig

from typing import List
from tenacity import retry, wait_exponential, stop_after_attempt

from core.config import settings
from core.logging import get_logger

load_dotenv()

log = get_logger("embedder")

EMBED_MODEL = "models/gemini-embedding-001"
EXPECTED_EMBEDDING_DIM = 3072  # gemini-embedding-001 output dimension

_client = genai.Client(api_key=settings.GEMINI_API_KEY)


class GeminiEmbedder:
    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
    def embed_text(self, text: str) -> List[float]:
        """Embed a single string using gemini-embedding-001. Raises on failure."""
        result = _client.models.embed_content(
            model=self.model_name,
            contents=text,
            config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        embedding = list(result.embeddings[0].values)
        if not embedding:
            raise ValueError("Gemini returned empty embedding")
        if len(embedding) != EXPECTED_EMBEDDING_DIM:
            raise ValueError(
                f"Embedding dimension mismatch: expected {EXPECTED_EMBEDDING_DIM}, got {len(embedding)}"
            )
        return embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings one at a time with rate-limit delay between calls.

        Raises immediately if any embedding fails — does not fall back to alternate models.
        """
        embeddings = []
        for idx, text in enumerate(texts):
            log.info(f"Embedding text {idx + 1}/{len(texts)}")
            embedding = self.embed_text(text)  # raises on failure — no fallback
            embeddings.append(embedding)
            if idx < len(texts) - 1:
                time.sleep(settings.GEMINI_RETRY_DELAY)
        return embeddings


# Module-level convenience function used by main.py, ui/dashboard.py, etc.
_default_embedder: "GeminiEmbedder | None" = None


def embed_text(text: str) -> List[float]:
    """Embed a single string using the shared GeminiEmbedder instance."""
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = GeminiEmbedder()
    return _default_embedder.embed_text(text)
