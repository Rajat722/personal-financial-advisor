# news_ingest_pipeline.py
import sys
import os

from core.logging import get_logger
from news.normalize import normalize_article
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import uuid
from datetime import datetime
from newspaper import Article

from newsdata import fetch_finance_news_from_newsdataio
from model.embedder import GeminiEmbedder, embed_text
from storage.vector_store import upsert_to_collection

log = get_logger("log")
embedder = GeminiEmbedder()


# --- Extract full article content from a URL ---
def extract_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        log.info(f"Failed to extract article from {url}: {e}")
        return None

# --- Main ingestion pipeline ---
def ingest_daily_news():
    q = "NVDA,Nvidia,Semiconductors"
    log.info(f"Fetching news metadata from NewsData.io for these keywords: {q}")
    articles = fetch_finance_news_from_newsdataio(q)
    log.info(f"Fetched {len(articles)} articles.")

    for article in articles:
        article = normalize_article(article)
        url = article.url
        title = article.title
        pub_date = article.published_at_utc
        summary = article.summary
        source = article.source_domain
        tickers = article.tickers
        log.info(f"\nProcessing: {title}")
        # text = extract_article_text(url)
        # print(f"text:\n{text}")
        if not summary:
            log.info("Skipped (summary not present)")
            continue

        embedding = embedder.embed_text(title +"-"+ summary)
        doc_id = article.id

        metadata = {
            "url": url,
            "title": title,
            "source": source,
            "published_ts": int(pub_date.timestamp()),
            "published_iso": pub_date.isoformat(),
            "tickers": tickers,
        }
        document = title +"-"+summary[:1500]
        collection_name = "articles"
        upsert_to_collection(collection_name, doc_id, document, embedding, metadata)
        log.info(f"Stored in vector DB collection: {collection_name}")

if __name__ == "__main__":
    ingest_daily_news()
    log.info("news ingestion for today completed")
