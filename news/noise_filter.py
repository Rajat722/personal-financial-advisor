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
        r"\b(?:LLC|Ltd\.?|Ltda\.?|L\.P\.|LP|Co\.?|Corp\.?|Inc\.?|Pte\.?|GmbH|SA|AG|NV|BV|Pty\.?|management|capital|advisors?|wealth|asset|partners?|associates?|group|fund|trust|holdings?)\b"
        r".{0,80}\btakes?\s+(?:a\s+)?(?:new\s+)?position\s+in\b",
        re.IGNORECASE,
    ),

    # "[Fund LLC] Makes New $2.20 Million Investment in Amazon" — anchored to fund entity
    # indicators so "Microsoft Makes $2B Investment in OpenAI" is NOT blocked.
    re.compile(
        r"\b(?:LLC|Ltd\.?|Ltda\.?|L\.P\.|LP|Co\.?|Corp\.?|Inc\.?|Pte\.?|GmbH|SA|AG|NV|BV|Pty\.?|management|capital|advisors?|wealth|asset|partners?|associates?|group|fund|trust|holdings?)\b"
        r".{0,80}\bmakes?\s+(?:a?\s+)?(?:new\s+)?\$[\d,.]+\s+(?:million|billion|thousand)\s+investment\s+in\b",
        re.IGNORECASE,
    ),

    # "[Fund LLC] Acquires New Position in Cloudflare" — anchored to fund entity indicators
    # so "Nvidia Acquires Stake in [company]" (real news) is NOT blocked.
    re.compile(
        r"\b(?:LLC|Ltd\.?|Ltda\.?|L\.P\.|LP|Co\.?|Corp\.?|Inc\.?|Pte\.?|GmbH|SA|AG|NV|BV|Pty\.?|management|capital|advisors?|wealth|asset|partners?|associates?|group|fund|trust|holdings?)\b"
        r".{0,80}\bacquires?\s+(?:a\s+)?(?:new\s+)?position\s+in\b",
        re.IGNORECASE,
    ),

    # "How-Pick-An-Sp-500-Fund" / "best-stocks-to-buy-now-march-2026"
    # URL slugs stored as article titles — 4+ hyphen-separated tokens, no spaces.
    # The API may return slugs with title-cased words (How-Pick-An-...) so IGNORECASE
    # is required. False positive guard: real headlines always contain spaces.
    re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){3,}$", re.IGNORECASE),

    # "Gordian Capital Buys Shares of 10,810 Alphabet" / "Firm Purchases 2,800 Shares of JPMorgan"
    # The specific share count after "of" distinguishes fund disclosures from corporate M&A.
    # "Apple Buys Stake in AI Startup" does NOT match (no digit after "of").
    re.compile(
        r"\b(?:buys?|purchases?|acquires?)\s+(?:shares?|stake)\s+of\s+[\d,]+\s",
        re.IGNORECASE,
    ),

    # "Jefferies Financial Group Inc. Takes $2.13 Million Position in Axon Enterprise"
    # "Engineers Gate Builds $85 Million Position in Net-Lease Retail REIT Agree Realty"
    # Dollar amount is the anchor — real M&A uses "invests", "acquires", "buys equity",
    # not "takes/builds/establishes position". Limited to "position" (not "stake") to
    # avoid blocking genuine M&A like "Apple Takes $2B Stake in OpenAI".
    re.compile(
        r"\b(?:takes?|builds?|establishes?)\s+\$[\d,.]+\s+(?:million|billion|thousand)\s+position\s+in\b",
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


# ---------------------------------------------------------------------------
# Speculative / opinion / historical return article filter
# ---------------------------------------------------------------------------
# These are SEO articles built around a speculative question or a historical
# return calculation. They contain no fresh news — just projections, "what-if"
# scenarios, or backward-looking performance data. They match portfolio tickers
# with high similarity but generate zero actionable insights.

_SPECULATIVE_PATTERNS = [
    # "Can Nvidia Stock Reach a $10 Trillion Market Cap by 2030?"
    # "Can Tesla Reach $500 by Year-End?"
    re.compile(r"\bcan\s+.{1,40}\breach\b", re.IGNORECASE),

    # "Where Will Realty Income Be in 10 Years?"
    # "Where Could Tesla Be in 3 Years?"
    # "Where Might Apple Stock Be in 5 Years?"
    re.compile(r"\bwhere\s+(?:will|could|might|may)\s+.{1,40}\bbe\s+in\s+\d+\s+years?\b", re.IGNORECASE),

    # "Is Tesla Stock Going to $1,000?"
    # "Is NVDA Going to $200?"
    re.compile(r"\bis\s+.{1,30}\bgoing\s+to\s+\$", re.IGNORECASE),

    # "If You Invested $1000 In Apple 20 Years Ago"
    # "If You Had Invested $500 in Tesla Stock 5 Years Ago"
    # "If I Had $5,000 to Invest in AI, I'd Put It in This Stock"
    # Subject is constrained to "i" or "you" — "If Tesla Had $5B" does NOT match.
    re.compile(r"\bif\s+(?:i|you)\s+(?:had\s+)?(?:invested\b|\$)", re.IGNORECASE),

    # "Here's How Much You Would Have Made Owning Microsoft Stock"
    # "How Much $1000 Invested In Apple Would Be Worth Today"
    re.compile(r"\bhow\s+much\s+.{0,30}\b(?:invested|made|worth)\b", re.IGNORECASE),

    # "Here's How Much $1000 Invested In Apple 20 Years Ago Would Be Worth Today"
    re.compile(r"\$\d+\s+invested\s+in\b", re.IGNORECASE),

    # "Forget QQQ: 3 Sector ETFs Quietly Outperforming Tech"
    # "Forget Tesla: Here's a Better EV Stock"
    re.compile(r"^forget\s+\w+\s*:", re.IGNORECASE),

    # "Prediction: This AI Stock Will Be the Biggest Winner of the Capex Boom"
    # Only matches when "Prediction:" is the FIRST word — real analyst notes lead with
    # the institution name ("Morgan Stanley Predicts...", "BofA Raises Target...").
    re.compile(r"^prediction\s*:", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Price-alert article filter
# ---------------------------------------------------------------------------
# Catches pure opinion-hook titles that have no causal content.
# "Here's What Happened" / "Here's Why" are intentionally excluded — those
# articles typically contain the actual explanation and are handled at the
# LLM level via the PRICE-ONLY ARTICLES rule in the analyst prompt.

_PRICE_ALERT_PATTERNS = [
    # "Trading 1.3% Higher — Time to Buy?"
    # "Down 4% — Time to Sell?"
    re.compile(r"[-\u2013\u2014]\s*time\s+to\s+(?:buy|sell)\??\s*$", re.IGNORECASE),

    # "Apple Trading Down 2.2% – Should You Sell?"
    # "Stock Is Down 10% — Should You Buy?"
    re.compile(r"\bshould\s+you\s+(?:buy|sell)\??\s*$", re.IGNORECASE),
]


def is_price_alert_article(title: str) -> bool:
    """Return True if the article is a pure opinion-hook price alert with no causal content.

    Only catches "— Time to Buy?" / "— Time to Sell?" suffix patterns.
    "Here's What Happened" and "Here's Why" are intentionally NOT filtered here —
    those articles often contain the actual cause of the price move and are handled
    by the PRICE-ONLY ARTICLES rule in the analyst prompt instead.
    """
    return any(p.search(title) for p in _PRICE_ALERT_PATTERNS)


def is_speculative_article(title: str) -> bool:
    """Return True if the article is a speculative opinion/projection piece with no fresh news.

    False positive guard: checked against known good articles —
    'Apple Just Unveiled the iPhone 17e. Should You Buy, Sell, or Hold AAPL Stock Now?' does NOT match
    because it lacks the speculative question patterns above.
    'Nvidia Stock Reaches All-Time High' does NOT match 'can .* reach' because it lacks 'can'.
    'Is Amazon Stock a Long-Term Buy?' does NOT match 'is .* going to $' because it lacks 'going to $'.
    """
    return any(p.search(title) for p in _SPECULATIVE_PATTERNS)
