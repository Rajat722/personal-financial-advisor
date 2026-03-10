"""
Tests for news/article_model_classes.py (Pydantic models).

Covers:
- Article: required fields, optional defaults, list independence, validation errors
- DigestItem: creation and missing-field validation
- Digest: nested model creation
"""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from news.article_model_classes import Article, DigestItem, Digest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_DT = datetime(2025, 8, 15, 20, 0, tzinfo=timezone.utc)


def _make_article(**overrides) -> Article:
    defaults = {
        "id": "abc123def456",
        "url": "https://finance.yahoo.com/news/nvidia-earnings",
        "source_domain": "finance.yahoo.com",
        "title": "Nvidia Posts Record Q3 Earnings on AI Demand",
        "published_at_utc": _BASE_DT,
    }
    return Article(**{**defaults, **overrides})


def _make_digest_item(**overrides) -> DigestItem:
    defaults = {
        "article_id": "abc123",
        "url": "https://finance.yahoo.com/news/nvidia-earnings",
        "title": "Nvidia Q3 Earnings Beat",
        "tickers": ["NVDA"],
        "tldr": "Nvidia beats Q3 revenue estimates on AI chip demand.",
        "why_matters": "Portfolio has 4.2% allocation to NVDA.",
        "confidence": "High",
        "source": "Yahoo Finance",
        "published_local": "2025-08-15 4:00 PM ET",
    }
    return DigestItem(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------

class TestArticle:
    def test_valid_article_creation(self):
        article = _make_article()
        assert article.id == "abc123def456"
        assert article.title == "Nvidia Posts Record Q3 Earnings on AI Demand"
        assert article.source_domain == "finance.yahoo.com"
        assert article.published_at_utc == _BASE_DT

    def test_optional_summary_defaults_to_none(self):
        assert _make_article().summary is None

    def test_optional_body_defaults_to_none(self):
        assert _make_article().body is None

    def test_tickers_defaults_to_empty_list(self):
        assert _make_article().tickers == []

    def test_sectors_defaults_to_empty_list(self):
        assert _make_article().sectors == []

    def test_optional_fields_accept_values(self):
        article = _make_article(
            summary="Nvidia Q3 revenue surged 122% YoY.",
            body="Full article body text here.",
            tickers=["NVDA", "AMD"],
            sectors=["semiconductors", "AI"],
        )
        assert article.summary == "Nvidia Q3 revenue surged 122% YoY."
        assert article.tickers == ["NVDA", "AMD"]
        assert article.sectors == ["semiconductors", "AI"]

    def test_missing_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Article(
                url="https://example.com",
                source_domain="example.com",
                title="Test Article",
                published_at_utc=_BASE_DT,
            )

    def test_missing_title_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Article(
                id="abc",
                url="https://example.com",
                source_domain="example.com",
                published_at_utc=_BASE_DT,
            )

    def test_missing_published_at_utc_raises_validation_error(self):
        with pytest.raises(ValidationError):
            Article(
                id="abc",
                url="https://example.com",
                source_domain="example.com",
                title="Test Article",
            )

    def test_invalid_published_at_type_raises_validation_error(self):
        with pytest.raises(ValidationError):
            _make_article(published_at_utc="not-a-datetime")

    def test_list_instances_are_independent(self):
        """Each Article instance must have its own tickers list, not a shared default."""
        a1 = _make_article()
        a2 = _make_article()
        a1.tickers.append("NVDA")
        assert a2.tickers == [], "tickers list was shared between instances"

    def test_article_with_all_fields(self, sample_article_data):
        article = Article(**sample_article_data)
        assert article.id == sample_article_data["id"]
        assert article.tickers == ["NVDA"]
        assert article.sectors == ["semiconductors", "AI"]


# ---------------------------------------------------------------------------
# DigestItem
# ---------------------------------------------------------------------------

class TestDigestItem:
    def test_valid_digest_item_creation(self):
        item = _make_digest_item()
        assert item.article_id == "abc123"
        assert item.confidence == "High"
        assert item.tickers == ["NVDA"]

    def test_missing_required_field_raises_validation_error(self):
        with pytest.raises(ValidationError):
            DigestItem(
                article_id="abc",
                url="https://example.com",
                title="Test",
                tickers=["NVDA"],
                # missing: tldr, why_matters, confidence, source, published_local
            )

    def test_confidence_values(self):
        for level in ("High", "Medium", "Low"):
            item = _make_digest_item(confidence=level)
            assert item.confidence == level


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------

class TestDigest:
    def test_valid_digest_creation(self):
        item = _make_digest_item()
        digest = Digest(
            window="post",
            date_et="2025-08-15",
            top_items=[item],
            movers=[{"ticker": "NVDA", "change_pct": 2.5}],
            sector_bullets=["Semiconductors +3.1%"],
            events=[{"title": "Fed rate decision", "why": "Affects growth stocks"}],
        )
        assert digest.window == "post"
        assert digest.date_et == "2025-08-15"
        assert len(digest.top_items) == 1
        assert digest.top_items[0].confidence == "High"
        assert digest.sector_bullets == ["Semiconductors +3.1%"]

    def test_digest_pre_window(self):
        digest = Digest(
            window="pre",
            date_et="2025-08-15",
            top_items=[],
            movers=[],
            sector_bullets=[],
            events=[],
        )
        assert digest.window == "pre"
        assert digest.top_items == []

    def test_digest_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Digest(
                window="post",
                # missing date_et, top_items, movers, sector_bullets, events
            )
