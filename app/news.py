import httpx
import os
from dotenv import load_dotenv
load_dotenv()
from app.chunker import Chunker
from newspaper import Article
from app.filter import parse_relevant_chunks
from app.vector_store import get_portfolio_collection
from app.portfolio_collection import build_portfolio_collection

# NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")


async def fetch_news_articles():
    NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
    url = 'https://newsapi.org/v2/everything'
    params = {
        "apikey": NEWSDATA_API_KEY,
        "q": "stocks, investing, finance",
        "language": "en"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        articles = response.json().get("articles", [])
        chunker = Chunker()
        filtered_articles = []
        _ = build_portfolio_collection()
        portfolio_embeddings = get_portfolio_collection()
        for article in articles[:5]:
            full_text = get_full_text(article["url"])
            chunks = chunker.chunk(full_text)
            obj = {
                "title": article["title"],
                "content": chunks
            }
            filtered_article = parse_relevant_chunks(obj, portfolio_embeddings)
            if filtered_article:
                filtered_articles.append(filtered_article)
        return filtered_articles

def get_full_text(article_url):
    try:
        article = Article(article_url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        print(f"Failed to extract article: {e}")
        return None