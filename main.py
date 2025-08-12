# main.py
import dashboard as st
import json
import uuid
from datetime import datetime
import os

from embedder import embed_text
from vector_store import (
    add_article_to_collection,
    find_similar_in_portfolio
)
from extract_text_from_article import extract_article_text 
from model import summarize_article

# Threshold above which we consider a match to be relevant
SIMILARITY_THRESHOLD = 0.75

project_root = os.path.dirname(os.path.abspath(__file__))
portfolio_path=os.path.join(project_root, "portfolio.json")
def load_portfolio_terms():
    with open(portfolio_path, "r") as f:
        data = json.load(f)
        print("printing portfolio: ", data)
    return data["tickers"] + data["sectors"] + data["indices"]

def index_portfolio_terms(terms):
    for term in terms:
        emb = embed_text(term)
        add_article_to_collection(
            collection_name="portfolio",
            doc_id=f"portfolio-{term}",
            text=term,
            embedding=emb,
            metadata={"type": "portfolio_term", "label": term}
        )

def is_article_relevant(article_embedding, threshold=SIMILARITY_THRESHOLD):
    results = find_similar_in_portfolio(article_embedding, top_k=3)
    scores = results.get("distances", [[]])[0]
    print("scores: \n", scores)
    return any(score >= threshold for score in scores)

def main():
    terms = load_portfolio_terms()
    index_portfolio_terms(terms)

    article_url = input("Enter news article URL: ").strip()
    article_text = extract_article_text(article_url)
    article_embedding = embed_text(article_text)

    if is_article_relevant(article_embedding):
        print("Article is relevant. Calling Gemini for summarization...")
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

        print("Summary saved successfully.")
        print(summary_json)
    else:
        print("Article is not relevant to the portfolio. Skipping.")

if __name__ == "__main__":
    main()