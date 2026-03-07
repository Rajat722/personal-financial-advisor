# noise_filter.py — shared noise filter for institutional holding disclosures
#
# Used by both:
#   news/news_ingest_pipeline.py  — at ingest time (prevents storing noise)
#   model/relevance_filter.py     — at query time (catches pre-filter articles)

import re

_NOISE_RE = re.compile(
    r"""
    \d[\d,]+\s+shares?\s+(?:in|of)\b            # "14,675 Shares in Apple"
    | \bhas\s+\$[\d,.]+\s+(?:million|billion)\b  # "Has $50.15 Million"
    | \b(?:stock\s+)?(?:holdings?|position|stake)\b.{0,15}
      \b(?:lifted|raised|reduced|cut|boosted|trimmed|
          increased|decreased|lowered|sold|bought)\b
                                                 # "Stock Position Lifted by..."
    | \b(?:lifts?|raises?|reduces?|cuts?|boosts?|trims?|
          increases?|decreases?|lowers?|grows?|buys?|sells?|acquires?)\b
      .{0,40}\b(?:holdings?|position|stake)\s+in\b
                                                 # "Grows Position in Apple"
    | \b(?:stock\s+)?holdings?\s+(?:in|of)\b.+\$[A-Z]
                                                 # "Stock Holdings in Apple $AAPL"
    | \b\d+(?:st|nd|rd|th)\s+largest\s+(?:position|holding)\b
                                                 # "4th Largest Position"
    | \bshort\s+interest\b.+\d+%                # "Short Interest Up 21.1%"
    | \bshares?\s+(?:acquired|sold|bought|purchased)\s+by\b
                                                 # "Shares Acquired by Aviso Financial"
    | \binvests?\s+\$[\d,.]+                     # "Invests $550,000 in Costco"
    | \b(?:buys?|purchases?)\s+(?:new\s+|additional\s+)?(?:\d+\s+)?shares?\s+in\b
                                                 # "Buys New Shares in Johnson & Johnson"
    | \b(?:largest|biggest)\s+(?:position|holding)\b
                                                 # "is Bouchey Financial Group Ltd's Largest Position"
    | \b(?:has|holds?|owns?)\s+\$[\d,.]+\s+(?:thousand\s+)?(?:stake|position|holding)\b
                                                 # "Has $845,000 Stake in Alphabet"
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_noise_article(title: str) -> bool:
    """Return True if the article title matches known institutional disclosure patterns."""
    return bool(_NOISE_RE.search(title))
