"""
Shared pytest fixtures and global patches for the test suite.

Module-level patches (outside fixtures) are started here so they are active
when pytest imports test modules. This prevents module-level API calls such as
`embedder = GeminiEmbedder()` in model/relevance_filter.py from reaching
real external services during collection.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Global patches — started at import time, before any test module is loaded
# ---------------------------------------------------------------------------

# Prevent google-genai Client from making real API calls during tests.
# Both model/embedder.py and model/model.py create a module-level genai.Client instance.
patch("google.genai.Client", return_value=MagicMock()).start()


# ---------------------------------------------------------------------------
# Reusable fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_embedder(monkeypatch):
    """Replace the module-level embedder instance in relevance_filter with a mock."""
    m = MagicMock()
    m.embed_text.return_value = [0.1] * 384
    monkeypatch.setattr("model.relevance_filter.embedder", m)
    return m


@pytest.fixture
def sample_portfolio(tmp_path):
    """Write a minimal portfolio JSON to a temp file and return its path."""
    portfolio = {
        "equities": [
            {"ticker": "NVDA", "company": "Nvidia"},
            {"ticker": "AAPL", "company": "Apple"},
        ],
        "sectors": ["semiconductors", "AI"],
        "indices": ["S&P 500"],
    }
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(portfolio))
    return path


@pytest.fixture
def sample_article_data():
    """Return a dict of valid Article field values for reuse in tests."""
    return {
        "id": "abc123def456",
        "url": "https://finance.yahoo.com/news/nvidia-earnings",
        "source_domain": "finance.yahoo.com",
        "title": "Nvidia Posts Record Q3 Earnings on AI Demand",
        "published_at_utc": datetime(2025, 8, 15, 20, 0, tzinfo=timezone.utc),
        "summary": "Nvidia Q3 revenue surged 122% YoY driven by data center AI chips.",
        "tickers": ["NVDA"],
        "sectors": ["semiconductors", "AI"],
    }


# ---------------------------------------------------------------------------
# External service mocks (available for any test that needs them)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_newsdata(monkeypatch):
    """Mock the NewsData.io fetch function to return an empty list."""
    mock_fn = MagicMock(return_value=[])
    monkeypatch.setattr("news.newsdata.fetch_finance_news_from_newsdataio", mock_fn)
    return mock_fn


@pytest.fixture
def mock_yfinance(monkeypatch):
    """Mock yfinance.download to return an empty DataFrame."""
    import pandas as pd
    mock_fn = MagicMock(return_value=pd.DataFrame())
    try:
        monkeypatch.setattr("yfinance.download", mock_fn)
    except AttributeError:
        pass  # yfinance not installed — skip silently
    return mock_fn


@pytest.fixture
def mock_gemini_generate(monkeypatch):
    """Mock Gemini GenerativeModel.generate_content to return a fixed response."""
    mock_response = MagicMock()
    mock_response.text = '{"insights": []}'
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response
    monkeypatch.setattr("model.model.model", mock_model)
    return mock_model
