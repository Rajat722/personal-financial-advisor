# main.py
import uuid
from datetime import datetime

from model.embedder import embed_text
from model.relevance_filter import SIMILARITY_THRESHOLD, index_portfolio_terms
from storage.vector_store import (
    add_article_to_collection,
    find_similar_in_portfolio
)
from news.extract_text_from_article import extract_article_text
from model.model import summarize_article
from core.logging import get_logger

log = get_logger("main")

def is_article_relevant(article_embedding: list, threshold: float = SIMILARITY_THRESHOLD) -> bool:
    """Return True if the article embedding is semantically close enough to the portfolio.

    ChromaDB returns cosine distances (lower = more similar).
    Convert to similarity before comparing against threshold.
    """
    results = find_similar_in_portfolio(article_embedding, top_k=3)
    distances = results.get("distances", [[]])[0]
    similarities = [1.0 - d for d in distances]
    log.info(f"Similarity scores: {similarities}")
    return any(sim >= threshold for sim in similarities)

def main() -> None:
    """CLI entry point: index portfolio, prompt for a URL, summarize if relevant."""
    index_portfolio_terms()

    article_url = input("Enter news article URL: ").strip()
    article_text = extract_article_text(article_url)
    article_embedding = embed_text(article_text)

    if is_article_relevant(article_embedding):
        log.info("Article is relevant. Calling Gemini for summarization...")
        summary_json = summarize_article(article_text)

        doc_id = f"article-{str(uuid.uuid4())}"
        metadata = {
            "type": "article",
            "title": article_text[:100],
            "url": article_url,
            "summary": summary_json,
            "timestamp": str(datetime.now())
        }
        add_article_to_collection("articles", doc_id, article_text, article_embedding, metadata)

        log.info("Summary saved successfully.")
        log.info(summary_json)
    else:
        log.info("Article is not relevant to the portfolio. Skipping.")

if __name__ == "__main__":
    main()