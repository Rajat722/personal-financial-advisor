from app.vector_store import find_similar_in_portfolio
from app.embedder import embed_text

def is_relevant(article_embedding):
    results = find_similar_in_portfolio(article_embedding, top_k=3)
    scores = results.get("distances", [[]])[0]
    print("scores: \n", scores)
    return any((score <= 0.25 or score >= 1.75) for score in scores)

def parse_relevant_chunks(article, portfolio_embeddings):
    """
    Checks if any article chunks are relevant to the portfolio terms.
    """
    chunks = article.get("content", [])
    content = []
    for chunk in chunks:
        chunk_embedding = embed_text(chunk)
        if chunk_embedding is not None:
            if is_relevant(chunk_embedding):
                content.append(chunk)
    if len(content) == 0:
        return None
    return {'title': article.get("title"), 'content': " ".join(content)}