# news_ingest_pipeline.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import uuid
from datetime import datetime
from newspaper import Article

from newsdata import fetch_finance_news_from_newsdataio
from model.embedder import embed_text
from storage.vector_store import add_article_to_collection

# --- Extract full article content from a URL ---
def extract_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        print(f"Failed to extract article from {url}: {e}")
        return None

# --- Main ingestion pipeline ---
def ingest_daily_news():
    print("Fetching news metadata from NewsData.io...")
    articles = fetch_finance_news_from_newsdataio(q="TSLA")
    print(f"Fetched {len(articles)} articles.")

    for entry in articles:
        url = entry.get("link")
        title = entry.get("title")
        pub_date = entry.get("pubDate")

        print(f"\nProcessing: {title}")
        text = extract_article_text(url)
        # print(f"text:\n{text}")
        if not text or len(text.split()) < 100:
            print("Skipped (content too short or missing)")
            continue

        embedding = embed_text(text)
        doc_id = f"context-{str(uuid.uuid4())}"

        metadata = {
            "title": title,
            "url": url,
            "pubDate": pub_date,
            "timestamp_fetched": str(datetime.utcnow()),
            "source": "NewsData.io"
        }

        add_article_to_collection("context", doc_id, text, embedding, metadata)
        print("Stored in vector DB: context")

if __name__ == "__main__":
    ingest_daily_news()
    print("news ingestion for today completed")
