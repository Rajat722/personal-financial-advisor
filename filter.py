from torch import cosine_similarity


SIMILARITY_THRESHOLD = 0.75

def is_relevant(article_embedding, portfolio_embeddings):
    scores = [cosine_similarity(article_embedding, pe) for pe in portfolio_embeddings.values()]
    return max(scores) >= SIMILARITY_THRESHOLD
