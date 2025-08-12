from app.embedder import embed_text
from app.vector_store import (
    add_article_to_collection,
    find_similar_in_portfolio
)
import json
import os
project_root = os.path.dirname(os.path.abspath(__file__))
portfolio_path=os.path.join(project_root, "portfolio.json")
def load_portfolio_terms():
    with open(portfolio_path, "r") as f:
        data = json.load(f)
        print("printing portfolio: ", data)
    return data["equities"]

def index_portfolio_terms(entities):
    for term in entities:
        stock = term['ticker'] + ':' + term['company']
        emb = embed_text(stock)
        add_article_to_collection(
            collection_name="portfolio",
            doc_id=f"portfolio-{stock}",
            text=stock,
            embedding=emb,
            metadata={"type": "portfolio_term", "label": stock}
        )
    return 'Success'

def build_portfolio_collection():
    """
    Loads portfolio terms from a JSON file and indexes them in the vector store.
    """
    entities = load_portfolio_terms()
    index_portfolio_terms(entities)
    return 'Success'