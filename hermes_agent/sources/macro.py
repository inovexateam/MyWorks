"""
Hermes — Macro Source
Fetches: RBI/Fed event calendar, crude oil price, INR/USD rate, global news via RSS.
All free sources. No API key needed.
"""

import requests
import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

log = logging.getLogger("hermes.macro")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ── RSS Feeds ─────────────────────────────────────────────────────────────────
# Free, reliable, no auth needed
RSS_FEEDS = {
    "Economic Times Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Moneycontrol Markets":   "https://www.moneycontrol.com/rss/marketreports.xml",
    "Reuters Business":       "https://feeds.reuters.com/reuters/businessNews",
    "Bloomberg India":        "https://feeds.bloomberg.com/markets/news.rss",
    "RBI Press Releases":     "https://rbi.org.in/Scripts/RSSFeedsDisplay.aspx?top=20&url=PressReleases",
    "PIB Finance":            "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
    "NSE Circulars":          "https://nseindia.com/rss/news.xml",
}

# Keywords that indicate high market impact
HIGH_IMPACT_KEYWORDS = [
    "rbi", "repo rate", "monetary policy", "inflation", "gdp",
    "fed", "federal reserve", "rate hike", "rate cut",
    "crude", "oil price", "opec",
    "war", "geopolitical", "sanctions", "conflict",
    "fii", "fpi", "foreign investor",
    "rupee", "dollar", "inr", "usd",
    "recession", "slowdown", "growth",
    "budget", "fiscal", "tax",
    "sebi", "ban", "suspension", "fraud",
]

STOCK_IMPACT_MAP = {
    "crude":    ["ONGC.NS", "RELIANCE.NS", "INDIGO.NS", "BPCL.NS"],
    "rbi":      ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS"],
    "fed":      ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS"],
    "rupee":    ["INFY.NS", "TCS.NS", "WIPRO.NS"],
    "war":      ["ONGC.NS", "HINDALCO.NS", "COALINDIA.NS"],
    "inflation":["FMCG", "NESTLEIND.NS", "HINDUNILVR.NS"],
}


# ── Crude Oil Price ───────────────────────────────────────────────────────────

def get_crude_price() -> dict:
    """
    Fetch Brent crude price from investing.com public endpoint.
    Fallback to Yahoo Finance ^BRNUSD.
    """
    try:
        import yfinance as yf
        t = yf.Ticker("BZ=F")   # Brent crude futures
        fi = t.fast_info
        price = round(fi.last_price, 2)
        prev  = round(fi.previous_close, 2)
        chg   = round(price - prev, 2)
        pct   = round((chg / prev) * 100, 2) if prev else 0
        return {"price": price, "change": chg, "pct": pct, "currency": "USD"}
    except Exception as e:
        log.warning(f"Crude price fetch failed: {e}")
        return {"price": 0, "change": 0, "pct": 0, "currency": "USD"}


# ── INR/USD Rate ──────────────────────────────────────────────────────────────

def get_inr_usd() -> dict:
    try:
        import yfinance as yf
        t  = yf.Ticker("INR=X")
        fi = t.fast_info
        rate = round(fi.last_price, 4)
        prev = round(fi.previous_close, 4)
        chg  = round(rate - prev, 4)
        pct  = round((chg / prev) * 100, 2) if prev else 0
        return {"rate": rate, "change": chg, "pct": pct}
    except Exception as e:
        log.warning(f"INR/USD fetch failed: {e}")
        return {"rate": 0, "change": 0, "pct": 0}


# ── RSS News Fetcher ──────────────────────────────────────────────────────────

def _parse_rss(url: str, source: str, max_items: int = 5) -> list:
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        root = ET.fromstring(r.content)
        channel = root.find("channel")
        if channel is None:
            channel = root

        for item in channel.findall("item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            desc  = (item.findtext("description") or "").strip()[:200]

            # Score impact
            text_lower = (title + " " + desc).lower()
            impact_score = sum(1 for kw in HIGH_IMPACT_KEYWORDS if kw in text_lower)

            items.append({
                "source":       source,
                "title":        title,
                "link":         link,
                "published":    pub,
                "desc":         desc,
                "impact_score": impact_score,
                "high_impact":  impact_score >= 2,
            })
    except Exception as e:
        log.debug(f"RSS parse failed for {source}: {e}")
    return items


def get_macro_news(max_per_feed: int = 3) -> list:
    """Fetch and merge news from all RSS feeds, sorted by impact score."""
    all_items = []
    for source, url in RSS_FEEDS.items():
        all_items.extend(_parse_rss(url, source, max_per_feed))
    all_items.sort(key=lambda x: x["impact_score"], reverse=True)
    return all_items


def get_high_impact_news(watchlist: list = None) -> list:
    """Return only high-impact news items, optionally tagged with affected stocks."""
    news = get_macro_news()
    high = [n for n in news if n["high_impact"]]

    if watchlist:
        watch_syms = {s.replace(".NS", "").lower() for s in watchlist}
        for item in high:
            text = (item["title"] + " " + item["desc"]).lower()
            affected = []
            for kw, stocks in STOCK_IMPACT_MAP.items():
                if kw in text:
                    affected.extend([s for s in stocks if s in watchlist or s.replace(".NS","").lower() in watch_syms])
            item["affected_stocks"] = list(set(affected))

    return high


# ── RBI / Fed Event Calendar ──────────────────────────────────────────────────

# Hardcoded upcoming key dates — update quarterly
# These are the dates that move markets most
MACRO_CALENDAR = [
    # Format: {"event": ..., "date": "YYYY-MM-DD", "impact": "HIGH/MEDIUM"}
    {"event": "RBI MPC Meeting",           "date": "2026-06-06",  "impact": "HIGH"},
    {"event": "RBI MPC Result Announcement","date": "2026-06-06", "impact": "HIGH"},
    {"event": "US Fed FOMC Meeting",       "date": "2026-06-11",  "impact": "HIGH"},
    {"event": "US CPI Inflation Data",     "date": "2026-06-11",  "impact": "HIGH"},
    {"event": "India CPI Inflation",       "date": "2026-06-13",  "impact": "MEDIUM"},
    {"event": "India IIP Data",            "date": "2026-06-13",  "impact": "MEDIUM"},
    {"event": "India GDP Q4 FY26",         "date": "2026-06-30",  "impact": "HIGH"},
    {"event": "RBI MPC Meeting",           "date": "2026-08-05",  "impact": "HIGH"},
    {"event": "Union Budget FY27",         "date": "2027-02-01",  "impact": "HIGH"},
]


def get_upcoming_macro_events(days_ahead: int = 30) -> list:
    """Return macro events within days_ahead, sorted by date."""
    today    = date.today()
    end_date = today + timedelta(days=days_ahead)
    upcoming = []

    for ev in MACRO_CALENDAR:
        try:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            if today <= ev_date <= end_date:
                days_out = (ev_date - today).days
                upcoming.append({
                    **ev,
                    "ev_date": ev_date,
                    "days_out": days_out,
                    "urgent":   days_out <= 3,
                })
        except Exception:
            continue

    upcoming.sort(key=lambda x: x["days_out"])
    return upcoming


# ── Global Market Snapshot ────────────────────────────────────────────────────

GLOBAL_INDICES = {
    "S&P 500":    "^GSPC",
    "NASDAQ":     "^IXIC",
    "Dow Jones":  "^DJI",
    "Nikkei 225": "^N225",
    "Hang Seng":  "^HSI",
    "FTSE 100":   "^FTSE",
    "SGX Nifty":  "^NSEI",   # proxy
}


def get_global_markets() -> list:
    """Returns global index snapshot — useful for gauging overnight sentiment."""
    import yfinance as yf
    results = []
    for name, ticker in GLOBAL_INDICES.items():
        try:
            fi    = yf.Ticker(ticker).fast_info
            price = round(fi.last_price, 2)
            prev  = round(fi.previous_close, 2)
            pct   = round(((price - prev) / prev) * 100, 2) if prev else 0
            results.append({"name": name, "price": price, "pct": pct})
        except Exception:
            pass
    return results
