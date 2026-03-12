# This script is designed to run as a Streamlit app. Ensure Streamlit is installed in your environment.
# If not already installed, run: pip install streamlit

import streamlit as st
import uuid
from datetime import datetime

from model.embedder import embed_text
from storage.vector_store import (
    add_article_to_collection,
    find_similar_in_portfolio,
    get_portfolio_collection,
    get_article_collection
)
from news.extract_text_from_article import extract_article_text, extract_json_block
from model.model import summarize_article
from model.relevance_filter import SIMILARITY_THRESHOLD


st.set_page_config(page_title="AI News Relevance Checker", layout="wide")
st.title("AI-Powered Financial News Relevance Dashboard")

# Input URL from user
article_url = st.text_input("Enter a finance news article URL:", "")

if article_url:
    with st.spinner("Extracting article..."):
        try:
            article_text = extract_article_text(article_url)
            st.success("Article successfully extracted.")
            st.text_area("Extracted Article Content", article_text, height=200)

            # Embed article
            article_embedding = embed_text(article_text)

            # Run semantic search against portfolio
            results = find_similar_in_portfolio(article_embedding, top_k=5)
            scores = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            documents = results.get("documents", [[]])[0]
            print(results)
            print(scores)
            print(metadatas)
            print(documents)

            # Display results
            st.subheader("Similarity Results")
            for i, score in enumerate(scores):
                st.markdown(f"**Match {i+1}:** {metadatas[i].get('type', 'Unknown')} — `{documents[i]}`")
                st.markdown(f"Cosine Similarity Score: `{round(score, 3)}`")
                st.markdown("---")

            if any(score >= SIMILARITY_THRESHOLD for score in scores):
                st.subheader("inside ")
                st.success("This article is relevant to your portfolio. Summarizing...")
                summary_json = summarize_article(article_text)

                # Save result
                doc_id = f"article-{str(uuid.uuid4())}"
                metadata = {
                    "type": "article",
                    "title": article_text[:100],
                    "url": article_url,
                    "summary": summary_json,
                    "timestamp": str(datetime.now())
                }
                
                add_article_to_collection("articles", doc_id, article_text, article_embedding, metadata)

                # Display summary
                parsed_summary = extract_json_block(summary_json)
                st.subheader("Gemini Summary")
                st.json(parsed_summary)
            else:
                st.warning("This article is NOT relevant to your portfolio.")

        except Exception as e:
            st.error(f"Failed to process article: {e}")

else:
    st.info("Please enter a news article URL above to get started.")
