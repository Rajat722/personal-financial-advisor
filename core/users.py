# core/users.py
"""
Multi-user portfolio loader.

Loads all user portfolio JSON files from user_portfolios/ directory.
Computes the union of all tickers, companies, sectors, and indices
for shared ingestion and data fetching.
"""

import json
from pathlib import Path
from core.logging import get_logger

log = get_logger("users")

ROOT = Path(__file__).resolve().parent.parent
USER_PORTFOLIOS_DIR = ROOT / "user_portfolios"


def load_all_users() -> list[dict]:
    """Load all user portfolio JSON files from user_portfolios/ directory.

    Returns a list of user dicts, each containing user_id, name, email,
    and the full portfolio data (equities, sectors, indices).
    Skips files that fail to parse with a warning.
    """
    users = []
    if not USER_PORTFOLIOS_DIR.exists():
        log.warning(f"User portfolios directory not found: {USER_PORTFOLIOS_DIR}")
        return users

    for path in sorted(USER_PORTFOLIOS_DIR.glob("user_*.json")):
        try:
            with open(path, "r") as f:
                user = json.load(f)
            if "user_id" not in user or "equities" not in user:
                log.warning(f"Skipping {path.name} — missing user_id or equities field.")
                continue
            users.append(user)
            log.info(f"Loaded user '{user['user_id']}' — {len(user['equities'])} equities")
        except Exception as e:
            log.warning(f"Failed to load {path.name}: {e}")

    log.info(f"Loaded {len(users)} user(s) total.")
    return users


def build_master_equities(users: list[dict]) -> list[dict]:
    """Build a deduplicated list of all equities across all users.

    When the same ticker appears in multiple users' portfolios, the
    equity entry from the first user (alphabetically by user_id) is used.
    The news_tier is set to the MINIMUM tier across all users who hold it
    (lower tier = higher priority = fetched first).

    Returns a list of equity dicts in the same format as portfolio.json equities.
    """
    seen: dict[str, dict] = {}  # ticker → equity dict
    tier_min: dict[str, int] = {}  # ticker → minimum tier across users

    for user in users:
        for eq in user.get("equities", []):
            ticker = eq["ticker"].upper()
            tier = eq.get("news_tier", 3)
            if ticker not in seen:
                seen[ticker] = eq.copy()
                tier_min[ticker] = tier
            else:
                tier_min[ticker] = min(tier_min[ticker], tier)

    # Apply the minimum tier to each equity
    for ticker, eq in seen.items():
        eq["news_tier"] = tier_min[ticker]

    result = sorted(seen.values(), key=lambda e: e["ticker"])
    log.info(f"Master equities: {len(result)} unique tickers from {len(users)} user(s)")
    return result


def build_master_portfolio(users: list[dict]) -> dict:
    """Build a master portfolio dict containing the union of all users' holdings.

    This is used for shared ingestion and data fetching — NOT for
    per-user digest generation (each user has their own portfolio for that).

    Returns a dict with the same structure as portfolio.json:
    {"equities": [...], "sectors": [...], "indices": [...]}
    """
    master_equities = build_master_equities(users)

    # Union of all sectors and indices across users
    all_sectors: set[str] = set()
    all_indices: set[str] = set()
    for user in users:
        all_sectors.update(s.lower() for s in user.get("sectors", []))
        all_indices.update(user.get("indices", []))

    return {
        "equities": master_equities,
        "sectors": sorted(all_sectors),
        "indices": sorted(all_indices),
    }


def get_all_tickers(users: list[dict]) -> list[str]:
    """Return a sorted, deduplicated list of all tickers across all users."""
    tickers: set[str] = set()
    for user in users:
        for eq in user.get("equities", []):
            tickers.add(eq["ticker"].upper())
    return sorted(tickers)
