from fastapi import APIRouter
from app.news import fetch_news_articles
from app.gemini_summarizer import generate_news_summary

router = APIRouter(prefix="/news", tags=["news"])
# /news/summary
@router.get("/summary")
async def get_news_summary():
    articles = await fetch_news_articles()
    summary = await generate_news_summary(articles)
    return {"articles": articles, "summary": summary}