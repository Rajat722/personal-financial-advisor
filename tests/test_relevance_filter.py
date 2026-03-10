"""
Tests for model/relevance_filter.py.

Covers:
- SIMILARITY_THRESHOLD constant value
- index_portfolio_terms() correctly reads portfolio.json and indexes all terms
- find_relevant_articles_from_context() includes articles above the threshold
- find_relevant_articles_from_context() excludes articles below the threshold
- Mixed-relevance article set is filtered correctly
"""
import json
import pytest
from unittest.mock import MagicMock

from model.relevance_filter import (
    find_relevant_articles_from_context,
    index_portfolio_terms,
    SIMILARITY_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Threshold constant
# ---------------------------------------------------------------------------

def test_similarity_threshold_value():
    """SIMILARITY_THRESHOLD must be 0.75 — this value is referenced in CLAUDE.md and tests."""
    assert SIMILARITY_THRESHOLD == 0.75


# ---------------------------------------------------------------------------
# index_portfolio_terms
# ---------------------------------------------------------------------------

def test_portfolio_json_loads_all_terms(sample_portfolio, monkeypatch):
    """index_portfolio_terms should upsert one entry per sector, index, ticker, and company."""
    mock_add = MagicMock()
    mock_embed = MagicMock()
    mock_embed.embed_text.return_value = [0.1] * 768
    monkeypatch.setattr("model.relevance_filter.add_to_collection", mock_add)
    monkeypatch.setattr("model.relevance_filter.embedder", mock_embed)

    index_portfolio_terms(path=str(sample_portfolio))

    # sample_portfolio has: 2 sectors + 1 index + 2 tickers + 2 companies = 7 terms
    assert mock_add.call_count == 7


def test_portfolio_terms_include_tickers_and_companies(sample_portfolio, monkeypatch):
    """Indexed terms should include uppercased tickers and company names."""
    captured_terms = []
    mock_embed = MagicMock()
    mock_embed.embed_text.return_value = [0.1] * 768
    monkeypatch.setattr("model.relevance_filter.embedder", mock_embed)
    monkeypatch.setattr(
        "model.relevance_filter.add_to_collection",
        lambda coll, doc_id, term, emb, meta: captured_terms.append(term),
    )

    index_portfolio_terms(path=str(sample_portfolio))

    assert "NVDA" in captured_terms
    assert "AAPL" in captured_terms
    assert "Nvidia" in captured_terms
    assert "Apple" in captured_terms


def test_portfolio_terms_include_sectors_lowercase(sample_portfolio, monkeypatch):
    """Sector terms should be lowercased when indexed."""
    captured_terms = []
    mock_embed = MagicMock()
    mock_embed.embed_text.return_value = [0.1] * 768
    monkeypatch.setattr("model.relevance_filter.embedder", mock_embed)
    monkeypatch.setattr(
        "model.relevance_filter.add_to_collection",
        lambda coll, doc_id, term, emb, meta: captured_terms.append(term),
    )

    index_portfolio_terms(path=str(sample_portfolio))

    # "semiconductors" and "ai" (lowercased from "AI")
    assert "semiconductors" in captured_terms
    assert "ai" in captured_terms


# ---------------------------------------------------------------------------
# find_relevant_articles_from_context — threshold filtering
# ---------------------------------------------------------------------------

def _make_article_collection(ids, documents, metadatas, embeddings):
    """Helper to build a mock ChromaDB collection with .get() returning the given data."""
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
        "embeddings": embeddings,
    }
    return mock_col


def test_relevant_article_passes_threshold(monkeypatch, mock_embedder):
    """
    An article whose best portfolio match has cosine distance <= 0.25
    (i.e. cosine similarity >= 0.75) must be included in results.
    """
    mock_col = _make_article_collection(
        ids=["nvda-earnings-001"],
        documents=["Nvidia Q3 revenue surges on AI chip demand"],
        metadatas=[{"title": "Nvidia Earnings", "url": "https://example.com/nvda"}],
        embeddings=[[0.1] * 768],
    )
    monkeypatch.setattr("model.relevance_filter.get_article_collection", lambda: mock_col)
    monkeypatch.setattr(
        "model.relevance_filter.find_similar_in_portfolio",
        lambda emb, top_k: {"distances": [[0.15]], "documents": [["NVDA Nvidia GPU"]]},
    )

    results = find_relevant_articles_from_context()

    assert len(results) == 1
    assert results[0]["doc_id"] == "nvda-earnings-001"


def test_irrelevant_article_blocked_by_threshold(monkeypatch, mock_embedder):
    """
    An article whose best portfolio match has cosine distance > 0.25
    (i.e. cosine similarity < 0.75) must be excluded from results.
    """
    mock_col = _make_article_collection(
        ids=["cooking-recipes-001"],
        documents=["Best holiday cookie recipes for the family"],
        metadatas=[{"title": "Cookie Recipes", "url": "https://example.com/cookies"}],
        embeddings=[[0.5] * 768],
    )
    monkeypatch.setattr("model.relevance_filter.get_article_collection", lambda: mock_col)
    monkeypatch.setattr(
        "model.relevance_filter.find_similar_in_portfolio",
        lambda emb, top_k: {"distances": [[0.90]], "documents": [["SPY S&P 500"]]},
    )

    results = find_relevant_articles_from_context()

    assert len(results) == 0


def test_article_at_exact_threshold_is_included(monkeypatch, mock_embedder):
    """An article at exactly the boundary distance (1 - 0.75 = 0.25) should be included."""
    mock_col = _make_article_collection(
        ids=["boundary-article"],
        documents=["Semiconductor sector outlook"],
        metadatas=[{"title": "Sector Outlook"}],
        embeddings=[[0.2] * 768],
    )
    monkeypatch.setattr("model.relevance_filter.get_article_collection", lambda: mock_col)
    monkeypatch.setattr(
        "model.relevance_filter.find_similar_in_portfolio",
        lambda emb, top_k: {"distances": [[0.25]], "documents": [["semiconductors chip"]]},
    )

    results = find_relevant_articles_from_context()

    assert len(results) == 1


def test_mixed_relevance_only_returns_relevant(monkeypatch, mock_embedder):
    """When articles has both relevant and irrelevant articles, only relevant ones are returned."""
    mock_col = _make_article_collection(
        ids=["art-relevant", "art-irrelevant"],
        documents=[
            "Apple reports record iPhone sales in Q4",
            "Best cookie recipes for the holidays",
        ],
        metadatas=[
            {"title": "Apple Q4 Sales"},
            {"title": "Cookie Recipes"},
        ],
        embeddings=[[0.1] * 768, [0.5] * 768],
    )
    monkeypatch.setattr("model.relevance_filter.get_article_collection", lambda: mock_col)

    call_count = 0

    def mock_similar(emb, top_k):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"distances": [[0.10]], "documents": [["AAPL Apple Inc"]]}
        return {"distances": [[0.95]], "documents": [["AAPL Apple Inc"]]}

    monkeypatch.setattr("model.relevance_filter.find_similar_in_portfolio", mock_similar)

    results = find_relevant_articles_from_context()

    assert len(results) == 1
    assert results[0]["doc_id"] == "art-relevant"


def test_empty_context_returns_empty_list(monkeypatch, mock_embedder):
    """find_relevant_articles_from_context returns [] when the articles collection is empty."""
    mock_col = _make_article_collection(
        ids=[], documents=[], metadatas=[], embeddings=[]
    )
    monkeypatch.setattr("model.relevance_filter.get_article_collection", lambda: mock_col)

    results = find_relevant_articles_from_context()

    assert results == []


def test_none_embedding_is_skipped(monkeypatch, mock_embedder):
    """Articles with None embeddings must be skipped without crashing."""
    mock_col = _make_article_collection(
        ids=["bad-article"],
        documents=["Article with no embedding"],
        metadatas=[{"title": "Bad Article"}],
        embeddings=[None],
    )
    monkeypatch.setattr("model.relevance_filter.get_article_collection", lambda: mock_col)

    results = find_relevant_articles_from_context()

    assert results == []
