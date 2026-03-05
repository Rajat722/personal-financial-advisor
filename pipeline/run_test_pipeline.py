# run_pipeline.py

import json
import os
from datetime import datetime
from core.logging import get_logger
from model.relevance_filter import find_relevant_articles_from_context, index_portfolio_terms
from random.stock_details import get_stock_OHLCV_data, format_summary_json, format_time_series_table
from model.model import summarize_multiple_articles, get_insights_from_news_and_prices, get_end_of_day_summary

# === Logging setup ===
logger = get_logger("logger")
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def save_log(filename, content):
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    path = os.path.join(LOG_DIR, f"{filename}_{timestamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
    logger.info(f"✅Log file saved at: {path}")

# === Step 1: Index portfolio terms ===
index_portfolio_terms() #-> works well

# === Step 2: Find relevant articles ===
# TODO -> need to test how well this works
relevant_articles = find_relevant_articles_from_context() 
logger.info(f"Found {len(relevant_articles)} relevant articles.\n")

# === Step 3: Format articles into prompt blocks ===
# TODO -> fix this ->JSON had \n after every key and value
def format_article_blocks(articles):
    blocks = []
    for i, article in enumerate(articles):
        title = article['metadata'].get("title", f"Untitled Article {i+1}")
        text = article['text']
        blocks.append(f"--- Article {i+1} ---\nTitle: {title}\nText: {text}\n")
    return "\n".join(blocks)

article_blocks = format_article_blocks(relevant_articles)

# === Step 4: Extract tickers ===
with open("D:\\Dev\\pfa-backend-fastapi\\portfolio2.json", "r") as f:
    portfolio = json.load(f)

tickers = [item["ticker"] for item in portfolio["equities"]]

# === Step 5: Fetch stock data ===
# getting stock data worked well
stock_data = get_stock_OHLCV_data(tickers, interval="30m", period="1d")
# TODO -> fix this ->time_series_json had \n after every key and value
time_series_json = json.dumps(format_time_series_table(stock_data), indent=2)

# === Step 6: Generate insights from Gemini ===
logger.info("\nGenerating structured insights from Gemini...")
try:
    # TODO-> fix this-> all tries failed. exceeded quota
    insights_response = get_insights_from_news_and_prices(article_blocks, time_series_json)
    logger.info(insights_response)
    save_log("insights_response", {"response": insights_response})
except Exception as e:
    logger.info(f"❌ Failed to get insights: {e}")
    insights_response = "{}"

# === Step 7: Summarize all relevant articles ===
logger.info("\nSummarizing all relevant articles...")
try:
    # TODO-> fix this-> all tries failed. exceeded quota
    summarized_articles_json = summarize_multiple_articles(article_blocks)
    logger.info(summarized_articles_json)
    save_log("summarized_articles", {"response": summarized_articles_json})
except Exception as e:
    print(f"❌ Failed to summarize articles: {e}")
    summarized_articles_json = "[]"

# === Step 8: Generate EOD summary ===
logger.info("\nCreating end-of-day personalized summary...")
try:
    # TODO-> fix this-> all tries failed. exceeded quota
    eod_summary = get_end_of_day_summary(insights_response, summarized_articles_json)
    logger.info(eod_summary)
    save_log("eod_summary", {"response": eod_summary})
except Exception as e:
    logger.info(f"❌ Failed to generate EOD summary: {e}")

# === Optional: Save relevant article metadata to DB ===
from storage.vector_store import add_article_to_collection
for article in relevant_articles:
    embedding = article.get("embedding")
    try:
        if embedding is not None:
            add_article_to_collection("relevant", article["doc_id"], article["text"], embedding, article["metadata"])
        else:
            print(f"⚠️ Skipping {article['doc_id']} due to missing embedding.")    
    except Exception as e:
        logger.info(f"⚠️ Failed to save article {article['doc_id']} to relevant collection: {e}")

# === Done ===
logger.info("\n✅ Full pipeline complete.")
