"""html_renderer.py — converts pipeline markdown digest into Portfolio Pulse HTML email."""
import html
import re

# ── CSS copied verbatim from sample_templates/digest_2026-03-08.html ─────────
_CSS = """\
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #f0f0f0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      color: #1a1a1a;
      font-size: 16px;
      line-height: 1.6;
    }

    .wrapper {
      max-width: 640px;
      margin: 24px auto;
      background: #ffffff;
      border-radius: 4px;
      overflow: hidden;
    }

    /* ── Meta / Published ── */
    .meta {
      padding: 20px 36px 0;
      font-size: 13px;
      color: #999;
    }

    /* ── Header ── */
    .header {
      padding: 14px 36px 12px;
    }
    .brand {
      font-size: 38px;
      font-weight: 800;
      letter-spacing: -1.5px;
      line-height: 1.1;
      color: #1a1a1a;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-icon {
      font-size: 34px;
      line-height: 1;
    }
    .tagline {
      font-size: 17px;
      font-style: italic;
      color: #666;
      margin-top: 2px;
      padding-left: 46px;
    }

    /* ── Intro ── */
    .intro {
      padding: 10px 36px 22px;
      font-size: 16px;
      line-height: 1.65;
      color: #1a1a1a;
    }
    .intro p { margin-bottom: 12px; }
    .intro p:last-child { margin-bottom: 0; }

    /* ── Blue divider with icon ── */
    .divider {
      display: flex;
      align-items: center;
      padding: 4px 36px;
    }
    .divider-line {
      flex: 1;
      height: 2px;
      background: #2952cc;
    }
    .divider-circle {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      border: 2px solid #2952cc;
      background: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 10px;
      font-size: 15px;
      flex-shrink: 0;
    }

    /* ── Sections ── */
    .section {
      padding: 22px 36px;
    }
    .section-label {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 2.5px;
      color: #2952cc;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .section-title {
      font-size: 22px;
      font-weight: 700;
      color: #1a1a1a;
      margin-bottom: 18px;
      line-height: 1.25;
    }

    /* ── Portfolio snapshot stats ── */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 14px;
    }
    .stat-box {
      background: #f5f7ff;
      border-radius: 8px;
      padding: 12px 8px;
      text-align: center;
    }
    .stat-value {
      font-size: 18px;
      font-weight: 700;
      color: #1a1a1a;
      line-height: 1.2;
    }
    .stat-label {
      font-size: 10px;
      color: #888;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-top: 4px;
    }
    .stat-note {
      font-size: 13px;
      color: #666;
      margin-top: 6px;
    }

    /* ── Colors ── */
    .pos { color: #16a34a; }
    .neg { color: #dc2626; }

    /* ── Movers table ── */
    .movers-table {
      width: 100%;
      border-collapse: collapse;
    }
    .movers-table td {
      padding: 9px 6px 9px 0;
      vertical-align: top;
      font-size: 14px;
      border-bottom: 1px solid #f2f2f2;
    }
    .movers-table tr:last-child td { border-bottom: none; }
    .col-ticker {
      font-weight: 700;
      font-size: 13px;
      width: 52px;
      color: #1a1a1a;
      padding-right: 2px !important;
    }
    .col-change {
      font-weight: 600;
      font-size: 13px;
      width: 72px;
      white-space: nowrap;
    }
    .col-driver {
      color: #444;
      line-height: 1.5;
    }

    /* ── Key Insights list ── */
    .insights-list {
      list-style: none;
    }
    .insights-list li {
      padding: 9px 0;
      font-size: 15px;
      line-height: 1.55;
      border-bottom: 1px solid #f2f2f2;
      color: #333;
    }
    .insights-list li:last-child { border-bottom: none; }
    .ticker-tag {
      font-weight: 700;
      color: #2952cc;
    }

    /* ── News items ── */
    .news-item {
      padding: 16px 0;
      border-bottom: 1px solid #efefef;
    }
    .news-item:last-child { border-bottom: none; }
    .news-headline {
      font-size: 18px;
      font-weight: 700;
      color: #1a1a1a;
      margin-bottom: 8px;
      line-height: 1.3;
    }
    .news-body {
      font-size: 15px;
      color: #333;
      line-height: 1.6;
    }
    .news-body .why {
      font-weight: 700;
    }

    /* ── Earnings ── */
    .earnings-empty {
      font-size: 15px;
      color: #888;
      font-style: italic;
      padding: 4px 0 12px;
    }

    /* ── Thin rule between stories ── */
    .thin-rule {
      border: none;
      border-top: 1px solid #e8e8e8;
      margin: 0 36px;
    }

    /* ── Footer ── */
    .footer {
      background: #f8f8f8;
      border-top: 1px solid #ebebeb;
      padding: 20px 36px;
      font-size: 12px;
      color: #aaa;
      text-align: center;
      line-height: 1.8;
    }
    .footer a {
      color: #2952cc;
      text-decoration: none;
    }
    .footer a:hover { text-decoration: underline; }

    @media (max-width: 600px) {
      .wrapper { margin: 0; border-radius: 0; }
      .stats-grid { grid-template-columns: repeat(2, 1fr); }
      .brand { font-size: 30px; }
      .section { padding: 18px 20px; }
      .divider { padding: 4px 20px; }
      .intro { padding: 10px 20px 18px; }
      .header { padding: 14px 20px 10px; }
      .meta { padding: 16px 20px 0; }
      .footer { padding: 16px 20px; }
      .thin-rule { margin: 0 20px; }
    }"""

_FOOTER_HTML = """\
  <div class="footer">
    <p>You're receiving this because you're an early tester of Portfolio Pulse.</p>
    <p>Powered by Gemini AI &nbsp;·&nbsp; News from NewsData.io &nbsp;·&nbsp; Prices from yfinance</p>
    <p style="margin-top: 8px;">
      <a href="#">Unsubscribe</a> &nbsp;·&nbsp;
      <a href="#">Manage Preferences</a> &nbsp;·&nbsp;
      <a href="#">View in Browser</a>
    </p>
    <p style="margin-top: 10px; font-size: 11px; color: #ccc;">
      Portfolio Pulse is for informational purposes only. Nothing here constitutes financial advice.
    </p>
  </div>"""


def _divider(icon: str) -> str:
    return (
        '  <div class="divider">\n'
        '    <div class="divider-line"></div>\n'
        f'    <div class="divider-circle">{icon}</div>\n'
        '    <div class="divider-line"></div>\n'
        '  </div>'
    )


# ── Parsers ───────────────────────────────────────────────────────────────────

def _is_positive(val: str) -> bool:
    """Return True if the value string starts with '+' or has no sign (positive)."""
    s = val.strip()
    return not s.startswith("-")


def _parse_portfolio_snapshot(md: str) -> dict:
    """Parse _build_portfolio_summary() markdown output into a structured dict.

    Expected format:
        ## Portfolio Snapshot
        **Est. Value:** $143,664  |  **Today's P&L:** +$2,929  |  **Total Gain:** +$69,285 (+93.2%)
        **Top Gainer:** NET (+5.7%)  |  **Top Loser:** T (-1.4%)
        _(Based on 20 of 25 holdings with today's data)_
    """
    def _get(pattern: str, default: str = "N/A") -> str:
        m = re.search(pattern, md)
        return m.group(1).strip() if m else default

    est_value   = _get(r'\*\*Est\. Value:\*\*\s*(\S+)')
    day_pnl     = _get(r"\*\*Today's P&L:\*\*\s*(\S+)")
    total_gain  = _get(r'\*\*Total Gain:\*\*\s*([^\s(|]+)')
    total_return = _get(r'\*\*Total Gain:\*\*[^(]*\(([^)]+)\)')
    top_gainer  = _get(r'\*\*Top Gainer:\*\*\s*(\S+\s*\([^)]+\))')
    top_loser   = _get(r'\*\*Top Loser:\*\*\s*(\S+\s*\([^)]+\))')

    holdings_m = re.search(r'Based on (\d+) of (\d+)', md)
    holdings_with_data = int(holdings_m.group(1)) if holdings_m else 0
    total_holdings     = int(holdings_m.group(2)) if holdings_m else 0

    return {
        "est_value":           est_value,
        "day_pnl":             day_pnl,
        "day_pnl_positive":    _is_positive(day_pnl),
        "total_gain":          total_gain,
        "total_gain_positive": _is_positive(total_gain),
        "total_return":        total_return,
        "total_return_positive": _is_positive(total_return),
        "top_gainer":          top_gainer,
        "top_loser":           top_loser,
        "holdings_with_data":  holdings_with_data,
        "total_holdings":      total_holdings,
    }


def _parse_movers(md: str) -> list[dict]:
    """Parse _build_movers_section() markdown table into a list of row dicts.

    Expected row format:
        | **TICKER** | ▲ +5.7% | Driver text here |
    """
    rows = []
    for line in md.splitlines():
        # Match: | **TICKER** | ▲/▼ change% | driver text |
        m = re.match(
            r'\|\s*\*\*([^*]+)\*\*\s*\|\s*(▲|▼)\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$',
            line,
        )
        if not m:
            continue
        ticker, arrow, change_pct, driver = (
            m.group(1).strip(),
            m.group(2),
            m.group(3).strip(),
            m.group(4).strip(),
        )
        rows.append({
            "ticker":   ticker,
            "change":   f"{arrow} {change_pct}",
            "positive": arrow == "▲",
            "driver":   driver,
        })
    return rows


def _parse_editorial(md: str) -> dict:
    """Parse the Call 2 editorial markdown into key_insights, earnings_text, news_stories.

    Expected sections (in order):
        Key Market Insights
        - TICKER: bullet text
        ...

        Upcoming Earnings (your portfolio)
        [earnings text or "No portfolio earnings..."]

        News That Mattered Today
        **Headline**
        Body text. **Why it matters:** Analysis text.
        ...
    """
    # ── Key Market Insights ──────────────────────────────────────────────────
    key_insights: list[dict] = []
    insights_m = re.search(
        r'Key Market Insights\s*\n((?:[ \t]*-[^\n]+\n?)+)',
        md, re.IGNORECASE,
    )
    if insights_m:
        for line in insights_m.group(1).splitlines():
            m = re.match(r'\s*-\s*([A-Z0-9.\-]+):\s*(.+)', line.strip())
            if m:
                key_insights.append({"ticker": m.group(1), "text": m.group(2).strip()})

    # ── Upcoming Earnings ────────────────────────────────────────────────────
    earnings_m = re.search(
        r'Upcoming Earnings[^\n]*\n(.*?)(?=\nNews That Mattered|\Z)',
        md, re.IGNORECASE | re.DOTALL,
    )
    earnings_text = (earnings_m.group(1).strip() if earnings_m
                     else "No portfolio earnings events in the next 14 days.")

    # ── News That Mattered Today ─────────────────────────────────────────────
    news_stories: list[dict] = []
    news_m = re.search(r'News That Mattered[^\n]*\n(.*)', md, re.IGNORECASE | re.DOTALL)
    if news_m:
        news_raw = news_m.group(1).strip()
        # Each story: **Headline**\n<body> **Why it matters:** <analysis>
        # Stories are separated by the next **...** headline.
        story_pattern = re.compile(
            r'\*\*([^*\n]+)\*\*[ \t]*\n(.*?)(?=\n[ \t]*\*\*[^*\n]+\*\*[ \t]*\n|\Z)',
            re.DOTALL,
        )
        for sm in story_pattern.finditer(news_raw):
            headline  = sm.group(1).strip()
            full_body = sm.group(2).strip()
            # Split on "**Why it matters:**" (case-insensitive)
            why_parts = re.split(
                r'\*\*Why it matters:\*\*', full_body, maxsplit=1, flags=re.IGNORECASE,
            )
            body          = why_parts[0].strip()
            why_it_matters = why_parts[1].strip() if len(why_parts) > 1 else ""
            news_stories.append({
                "headline":       headline,
                "body":           body,
                "why_it_matters": why_it_matters,
            })

    return {
        "key_insights":  key_insights,
        "earnings_text": earnings_text,
        "news_stories":  news_stories,
    }


def parse_digest_markdown(
    portfolio_summary_md: str,
    movers_md: str,
    editorial_md: str,
) -> dict:
    """Parse the three pipeline sections into structured dicts for the HTML renderer."""
    return {
        "portfolio_snapshot": _parse_portfolio_snapshot(portfolio_summary_md),
        "movers":             _parse_movers(movers_md),
        **_parse_editorial(editorial_md),
    }


# ── Renderer ──────────────────────────────────────────────────────────────────

def render_digest_html(
    portfolio_snapshot: dict,
    movers: list[dict],
    key_insights: list[dict],
    earnings_text: str,
    news_stories: list[dict],
    date_str: str,
    article_count: int,
    holdings_count: int,
) -> str:
    """Return a complete Portfolio Pulse HTML email string.

    All dynamic text is passed through html.escape() before insertion.
    The static CSS and structural HTML are copied verbatim from the sample template.
    """
    ps = portfolio_snapshot

    # ── Portfolio Snapshot ───────────────────────────────────────────────────
    pnl_cls  = "pos" if ps.get("day_pnl_positive")    else "neg"
    gain_cls = "pos" if ps.get("total_gain_positive")  else "neg"
    ret_cls  = "pos" if ps.get("total_return_positive") else "neg"

    stats_html = (
        '    <div class="stats-grid">\n'
        '      <div class="stat-box">\n'
        f'        <div class="stat-value">{html.escape(ps.get("est_value", "N/A"))}</div>\n'
        '        <div class="stat-label">Est. Value</div>\n'
        '      </div>\n'
        '      <div class="stat-box">\n'
        f'        <div class="stat-value {pnl_cls}">{html.escape(ps.get("day_pnl", "N/A"))}</div>\n'
        '        <div class="stat-label">Today\'s P&amp;L</div>\n'
        '      </div>\n'
        '      <div class="stat-box">\n'
        f'        <div class="stat-value {gain_cls}">{html.escape(ps.get("total_gain", "N/A"))}</div>\n'
        '        <div class="stat-label">Total Gain</div>\n'
        '      </div>\n'
        '      <div class="stat-box">\n'
        f'        <div class="stat-value {ret_cls}">{html.escape(ps.get("total_return", "N/A"))}</div>\n'
        '        <div class="stat-label">Total Return</div>\n'
        '      </div>\n'
        '    </div>\n'
        '    <p class="stat-note">\n'
        f'      🏆 <strong>Top Gainer:</strong> <span class="pos">{html.escape(ps.get("top_gainer", ""))}</span> &nbsp;·&nbsp;\n'
        f'      📉 <strong>Top Loser:</strong> <span class="neg">{html.escape(ps.get("top_loser", ""))}</span>\n'
        f'      &nbsp;<span style="color:#bbb;">— {ps.get("holdings_with_data", 0)} of {ps.get("total_holdings", 0)} holdings with data today</span>\n'
        '    </p>'
    )

    # ── Movers Table ─────────────────────────────────────────────────────────
    mover_rows = []
    for row in movers:
        chg_cls = "col-change pos" if row["positive"] else "col-change neg"
        mover_rows.append(
            "      <tr>\n"
            f'        <td class="col-ticker">{html.escape(row["ticker"])}</td>\n'
            f'        <td class="{chg_cls}">{html.escape(row["change"])}</td>\n'
            f'        <td class="col-driver">{html.escape(row["driver"])}</td>\n'
            "      </tr>"
        )
    movers_html = "\n".join(mover_rows)

    # ── Key Insights List ─────────────────────────────────────────────────────
    insight_items = []
    for ins in key_insights:
        ticker_tag = f'<span class="ticker-tag">{html.escape(ins["ticker"])}:</span>'
        insight_items.append(f'      <li>{ticker_tag} {html.escape(ins["text"])}</li>')
    insights_html = "\n".join(insight_items)

    # ── Earnings ─────────────────────────────────────────────────────────────
    if "No portfolio earnings events" in earnings_text:
        earnings_html = f'    <p class="earnings-empty">{html.escape(earnings_text)}</p>'
    else:
        lines = [html.escape(ln) for ln in earnings_text.strip().splitlines() if ln.strip()]
        earnings_html = "\n".join(f"    <p>{ln}</p>" for ln in lines)

    # ── News Stories ──────────────────────────────────────────────────────────
    news_parts = []
    for story in news_stories:
        headline_e = html.escape(story.get("headline", ""))
        body_e     = html.escape(story.get("body", ""))
        why_e      = html.escape(story.get("why_it_matters", ""))
        why_span   = f' <span class="why">Why it matters:</span> {why_e}' if why_e else ""
        news_parts.append(
            '    <div class="news-item">\n'
            f'      <p class="news-headline">{headline_e}</p>\n'
            f'      <p class="news-body">{body_e}{why_span}</p>\n'
            '    </div>'
        )
    news_html = "\n\n".join(news_parts)

    intro_text = html.escape(
        f"Good Evening! Here's your personalized portfolio digest for {date_str} — "
        f"curated from {article_count} relevant articles across your {holdings_count} holdings."
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"  <title>Portfolio Pulse \u2014 {html.escape(date_str)}</title>\n"
        "  <style>\n"
        f"{_CSS}\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="wrapper">\n\n'
        f'  <div class="meta">Published on: {html.escape(date_str)}</div>\n\n'
        '  <div class="header">\n'
        '    <div class="brand">\n'
        '      <span class="brand-icon">\U0001f4c8</span> Portfolio Pulse\n'
        '    </div>\n'
        '    <div class="tagline">Read Less News</div>\n'
        '  </div>\n\n'
        '  <div class="intro">\n'
        f'    <p>{intro_text}</p>\n'
        '  </div>\n\n'
        + _divider("\U0001f91d") + "\n\n"
        '  <div class="section">\n'
        '    <div class="section-label">Your Portfolio</div>\n'
        '    <div class="section-title">Today\'s Snapshot</div>\n'
        f"{stats_html}\n"
        '  </div>\n\n'
        + _divider("\U0001f4c8") + "\n\n"
        '  <div class="section">\n'
        '    <div class="section-label">Market Movers</div>\n'
        '    <div class="section-title">What Moved Your Holdings Today</div>\n\n'
        '    <table class="movers-table">\n'
        f"{movers_html}\n"
        '    </table>\n'
        '  </div>\n\n'
        + _divider("\U0001f4a1") + "\n\n"
        '  <div class="section">\n'
        '    <div class="section-label">Key Insights</div>\n'
        '    <div class="section-title">What Matters for Your Holdings</div>\n\n'
        '    <ul class="insights-list">\n'
        f"{insights_html}\n"
        '    </ul>\n'
        '  </div>\n\n'
        + _divider("\U0001f4c5") + "\n\n"
        '  <div class="section">\n'
        '    <div class="section-label">Earnings Calendar</div>\n'
        '    <div class="section-title">Upcoming in Your Portfolio</div>\n'
        f"{earnings_html}\n"
        '  </div>\n\n'
        + _divider("\U0001f4f0") + "\n\n"
        '  <div class="section">\n'
        '    <div class="section-label">News That Mattered Today</div>\n'
        '    <div class="section-title">The Stories Behind the Moves</div>\n\n'
        f"{news_html}\n"
        '  </div>\n\n'
        + _FOOTER_HTML + "\n\n"
        "</div>\n"
        "</body>\n"
        "</html>"
    )
