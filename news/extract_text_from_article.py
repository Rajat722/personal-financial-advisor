from newspaper import Article


def extract_article_text(url: str) -> str:
    """Download and parse the full text of a news article from its URL.

    Uses newspaper3k to extract article body text. Returns empty string if
    extraction fails (paywall, bot protection, network error, etc.).
    Callers should check len(result) > 200 before using the output.
    """
    article = Article(url)
    article.download()
    article.parse()
    return article.text
