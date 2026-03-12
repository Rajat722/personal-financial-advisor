# embedder.py
"""
Handles text embedding using Google Gemini gemini-embedding-001 via the google-genai SDK.
Used for both portfolio terms and article text.

Falls back to GEMINI_FALLBACK_API_KEY when the primary key hits ResourceExhausted
(quota / credit exhaustion). Once primary is exhausted for the session all subsequent
calls go directly to the fallback client.
"""

import time
from dotenv import load_dotenv
from google import genai
from google.genai.types import EmbedContentConfig

from typing import List
from tenacity import retry, wait_exponential, stop_after_attempt

try:
    from google.api_core.exceptions import ResourceExhausted
except ImportError:
    ResourceExhausted = Exception  # type: ignore

from core.config import settings
from core.logging import get_logger

load_dotenv()

log = get_logger("embedder")

EMBED_MODEL = "models/gemini-embedding-001"
EXPECTED_EMBEDDING_DIM = 3072  # gemini-embedding-001 output dimension

_primary_client = genai.Client(api_key=settings.GEMINI_API_KEY)
_fallback_client = (
    genai.Client(api_key=settings.GEMINI_FALLBACK_API_KEY)
    if settings.GEMINI_FALLBACK_API_KEY
    else None
)

# Session flag: once primary quota is exhausted, skip straight to fallback.
_primary_exhausted: bool = False


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
def _embed_with_client(client: genai.Client, model_name: str, text: str) -> List[float]:
    """Single embedding call against a specific client. Tenacity retries on transient errors."""
    result = client.models.embed_content(
        model=model_name,
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


class GeminiEmbedder:
    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name

    def embed_text(self, text: str) -> List[float]:
        """Embed a single string, falling back to secondary key on quota exhaustion."""
        global _primary_exhausted

        if not _primary_exhausted:
            try:
                return _embed_with_client(_primary_client, self.model_name, text)
            except ResourceExhausted:
                if _fallback_client is None:
                    raise RuntimeError(
                        "Primary Gemini key quota exhausted and GEMINI_FALLBACK_API_KEY is not set."
                    )
                log.warning("Primary Gemini key quota exhausted — switching to fallback key.")
                _primary_exhausted = True
            # Fall through to fallback.

        if _fallback_client is None:
            raise RuntimeError(
                "Primary Gemini key quota exhausted and GEMINI_FALLBACK_API_KEY is not set."
            )
        try:
            return _embed_with_client(_fallback_client, self.model_name, text)
        except ResourceExhausted as e:
            raise RuntimeError("Both Gemini API keys have exhausted their quota.") from e

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
