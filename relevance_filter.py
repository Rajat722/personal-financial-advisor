# relevance_filter.py

import uuid
import json
from vector_store import get_context_collection, find_similar_in_portfolio, add_article_to_collection
from embedder import embed_text

SIMILARITY_THRESHOLD = 0.75

# --- Load and index portfolio terms from JSON ---
def index_portfolio_terms(path="D:\\Dev\\pfa-backend-fastapi\\portfolio2.json"):
    with open(path, "r") as f:
        data = json.load(f)

    equities = data.get("equities", [])
    terms = []

    for item in equities:
        ticker = item.get("ticker")
        company = item.get("company")
        if ticker:
            terms.append(ticker)
        if company:
            terms.append(company)

    for term in terms:
        embedding = embed_text(term)
        add_article_to_collection("portfolio", f"portfolio-{term}", term, embedding, {"type": "portfolio_term"})

# --- Retrieve relevant articles from context DB based on portfolio embedding match ---
def find_relevant_articles_from_context():
    context_collection = get_context_collection()
    
    all_articles = context_collection.get(include=["documents", "embeddings", "metadatas"])

    relevant_articles = []

    for doc_id, text, metadata, embedding in zip(
    all_articles["ids"],
    all_articles["documents"],
    all_articles["metadatas"],
    all_articles["embeddings"]
    ):
        try:
            results = find_similar_in_portfolio(embedding, top_k=3)
            scores = results.get("distances", [[]])[0]

            if any(score >= SIMILARITY_THRESHOLD for score in scores):
                relevant_articles.append({
                    "doc_id": doc_id,
                    "text": text,
                    "metadata": metadata,
                    "scores": scores
                })
        except Exception as e:
            print(f"Skipping {doc_id} due to error: {e}")

    return relevant_articles

# --- Example usage ---
if __name__ == "__main__":
    matches = find_relevant_articles_from_context()
    print(f"\nFound {len(matches)} relevant articles:\n")
    for i, article in enumerate(matches):
        print(f"[{i+1}] {article['metadata'].get('title')}\n{article['metadata'].get('url')}\n")
