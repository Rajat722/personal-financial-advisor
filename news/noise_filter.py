# noise_filter.py — shared noise filter for institutional holding disclosures
#
# Used by both:
#   news/news_ingest_pipeline.py  — at ingest time (prevents storing noise)
#   model/relevance_filter.py     — at query time (catches pre-filter articles)
#
# Each pattern is a separate compiled regex (no re.VERBOSE) for predictability.
# All patterns are case-insensitive.
#
# FALSE POSITIVE RISK: These patterns distinguish institutional fund disclosures from
# real corporate news. E.g., "Goldman Sachs Reduces Position in Apple" = noise,
# but "Berkshire Hathaway Trims Apple Stake" = real news. The heuristics below err on
# the side of keeping real news (i.e., we accept some noise slipping through rather than
# blocking legitimate portfolio-relevant articles).

import re

_PATTERNS = [
    # "14,675 Shares in Apple" / "200 Shares of Microsoft"
    # Requires a specific share count — real news doesn't format this way.
    re.compile(r"\d[\d,]+\s+shares?\s+(?:in|of)\b", re.IGNORECASE),

    # "Has $50.15 Million [position/stake/holding]"
    re.compile(r"\bhas\s+\$[\d,.]+\s+(?:million|billion)\b", re.IGNORECASE),

    # "Stock Position Lifted by Vanguard" / "Apple Stake Reduced by [fund]"
    # Passive voice with fund as object — real corporate news uses active voice.
    re.compile(
        r"\b(?:stock\s+)?(?:holdings?|position|stake)\b.{0,15}"
        r"\b(?:lifted|raised|reduced|cut|boosted|trimmed|increased|decreased|lowered|sold|bought)\b",
        re.IGNORECASE,
    ),

    # "Grows Position in Apple" / "Trims Stake in Tesla" (fund portfolio management language)
    # NOTE: intentionally excludes sells/buys/acquires to avoid catching real corporate news
    # like "Berkshire Hathaway Sells Its Apple Position" or "Apple Acquires Stake in X".
    re.compile(
        r"\b(?:lifts?|raises?|reduces?|cuts?|boosts?|trims?|"
        r"increases?|decreases?|lowers?|grows?)\b"
        r".{0,40}\b(?:holdings?|position|stake)\s+in\b",
        re.IGNORECASE,
    ),

    # "Stock Holdings in Apple $AAPL"
    re.compile(r"\b(?:stock\s+)?holdings?\s+(?:in|of)\b.+\$[A-Z]", re.IGNORECASE),

    # "4th Largest Position" / "2nd Largest Holding"
    re.compile(r"\b\d+(?:st|nd|rd|th)\s+largest\s+(?:position|holding)\b", re.IGNORECASE),

    # "Short Interest Up 21.1%"
    re.compile(r"\bshort\s+interest\b.+\d+%", re.IGNORECASE),

    # "Shares Acquired by Aviso Financial" / "Shares Sold by [fund]"
    # Passive voice — distinguishes fund disclosures from "Berkshire Buys Shares".
    re.compile(r"\bshares?\s+(?:acquired|sold|bought|purchased)\s+by\b", re.IGNORECASE),

    # "Invests $550,000 in Costco" — specific dollar amount required; real news uses % or context.
    re.compile(r"\binvests?\s+\$[\d,.]+", re.IGNORECASE),

    # "Buys New Shares in Apple" / "Purchases Additional Shares in Tesla"
    # "new" or "additional" qualifier signals institutional disclosure, not corporate action.
    re.compile(
        r"\b(?:buys?|purchases?)\s+(?:new\s+|additional\s+)(?:\d+\s+)?shares?\s+in\b",
        re.IGNORECASE,
    ),

    # "is Bouchey Financial Group Ltd's Largest Position" / "[X]'s Biggest Holding"
    re.compile(r"(?:largest|biggest)\s+(?:position|holding)", re.IGNORECASE),

    # "Has $845,000 Stake in Alphabet" / "Holds $2.3 Million Position"
    re.compile(
        r"\b(?:has|holds?|owns?)\s+\$[\d,.]+\s+(?:thousand\s+)?(?:stake|position|holding)\b",
        re.IGNORECASE,
    ),

    # "Bright Futures Wealth Management LLC. Purchases New Position in JPMorgan"
    # Uses "position" instead of "shares" — fund-specific phrasing safe to filter.
    re.compile(
        r"\b(?:buys?|purchases?)\s+(?:new\s+|additional\s+)position\s+in\b",
        re.IGNORECASE,
    ),

    # "[Fund LLC] Takes Position in JPMorgan" — anchored to fund entity indicators so
    # "Microsoft Takes Position in OpenAI" (real news, no fund keyword) is NOT blocked.
    re.compile(
        r"\b(?:LLC|Ltd\.?|L\.P\.|LP|management|capital|advisors?|wealth|asset|partners?|associates?)\b"
        r".{0,80}\btakes?\s+(?:a\s+)?(?:new\s+)?position\s+in\b",
        re.IGNORECASE,
    ),

    # "[Fund LLC] Makes New $2.20 Million Investment in Amazon" — anchored to fund entity
    # indicators so "Microsoft Makes $2B Investment in OpenAI" is NOT blocked.
    re.compile(
        r"\b(?:LLC|Ltd\.?|L\.P\.|LP|management|capital|advisors?|wealth|asset|partners?|associates?)\b"
        r".{0,80}\bmakes?\s+(?:a?\s+)?(?:new\s+)?\$[\d,.]+\s+(?:million|billion|thousand)\s+investment\s+in\b",
        re.IGNORECASE,
    ),

    # "[Fund LLC] Acquires New Position in Cloudflare" — anchored to fund entity indicators
    # so "Nvidia Acquires Stake in [company]" (real news) is NOT blocked.
    re.compile(
        r"\b(?:LLC|Ltd\.?|L\.P\.|LP|management|capital|advisors?|wealth|asset|partners?|associates?)\b"
        r".{0,80}\bacquires?\s+(?:a\s+)?(?:new\s+)?position\s+in\b",
        re.IGNORECASE,
    ),

    # Insider sale articles below $1M threshold — "Insider Selling:" prefix format.
    # Matches titles like: "Insider Selling: Company CAO Sells $70,806.48 in Stock"
    # The amount pattern (\$\d{1,3},\d{3}) covers $1,000–$999,999 (exactly one comma group).
    # The negative lookahead (?![\d,]) prevents matching mid-number (e.g. "$36,471,323" is NOT caught).
    # Does NOT match titles with "million"/"billion" — those are material and should pass through.
    re.compile(
        r"\binsider\s+(?:selling|sale|transaction)s?\b"
        r"(?!.*\b(?:million|billion)\b)"
        r".{0,150}\$\d{1,3},\d{3}(?:\.\d+)?(?![\d,])",
        re.IGNORECASE,
    ),

    # Role-based insider sale articles below $1M — no "insider" keyword in title.
    # Matches: "Verizon (NYSE:VZ) SVP Sells $428,450.00 in Stock"
    #          "Cloudflare (NYSE:NET) COO Sells 25,641 Shares for $428,000"
    # Does NOT match: "Apple CEO Tim Cook Sells $36 million in Stock" (has "million")
    #                 "Director Harry Sloan Buys $2.185M" ("buys", not "sells")
    # Anchored to known executive role titles to avoid catching corporate M&A/divestiture news.
    re.compile(
        r"\b(?:CEO|CFO|COO|CTO|CMO|CRO|CAO|SVP|EVP|VP|President|Director|Chairman)\b"
        r".{0,80}\bsells?\b"
        r"(?!.*\b(?:million|billion)\b)"
        r".{0,80}\$\d{1,3},\d{3}(?:\.\d+)?(?![\d,])",
        re.IGNORECASE,
    ),
]


def is_noise_article(title: str) -> bool:
    """Return True if the article title matches known institutional disclosure patterns."""
    return any(p.search(title) for p in _PATTERNS)


# ---------------------------------------------------------------------------
# Generic SEO roundup article filter
# ---------------------------------------------------------------------------
# These are templated daily list articles ("Best Water Stocks To Watch Today – March 5th")
# that contain no specific portfolio-relevant content. They match portfolio term embeddings
# but waste article slots and LLM context with zero-signal content.

_ROUNDUP_PATTERNS = [
    # "Best Tech Stocks To Watch Today" / "Promising Energy Stocks To Follow Now"
    # "Top Space Stocks To Research – March 5th" / "Casino Stocks To Consider"
    re.compile(r"\bstocks?\s+to\s+(?:watch|follow|research|consider|buy|avoid)\b", re.IGNORECASE),

    # "Stocks To Keep An Eye On"
    re.compile(r"\bstocks?\s+to\s+keep\s+an\s+eye\s+on\b", re.IGNORECASE),

    # "Stocks Worth Watching" / "Stocks Worth Following"
    re.compile(r"\bstocks?\s+worth\s+(?:watching|following|researching)\b", re.IGNORECASE),

    # "Stocks To Add to Your Watchlist"
    re.compile(r"\bstocks?\s+to\s+add\s+to\b", re.IGNORECASE),

    # "12 Cheap AI Stocks to Buy in 2026" / "13 Most Profitable Growth Stocks to Buy Right Now"
    re.compile(r"\b\d+\s+\w.{0,30}\bstocks?\s+to\s+buy\b", re.IGNORECASE),
]


def is_generic_roundup(title: str) -> bool:
    """Return True if the article is a generic SEO stock-list roundup with no specific content.

    False positive guard: checked against known good articles —
    'Is Amazon Stock a Long-Term Buy?' and 'Should You Buy AAPL Stock Now?' do NOT match
    because they lack the 'stocks to [verb]' phrasing.
    """
    return any(p.search(title) for p in _ROUNDUP_PATTERNS)
