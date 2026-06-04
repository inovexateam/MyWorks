"""
Hermes Agent — Data Fetcher
Pulls live prices, 52W data, FII/DII proxy, and earnings from Yahoo Finance (yfinance).
Zero paid APIs required.
"""

import yfinance as yf
import requests
from datetime import datetime, date
import logging
import json
import os

log = logging.getLogger("hermes.data")

# ── Indices ──────────────────────────────────────────────────────────────────
INDEX_TICKERS = {
    "NIFTY 50":   "^NSEI",
    "SENSEX":     "^BSESN",
    "BANK NIFTY": "^NSEBANK",
}

# ── Nifty ticker for alert polling ───────────────────────────────────────────
NIFTY_TICKER = "^NSEI"


def get_price(symbol: str) -> float | None:
    """Return latest price for a single symbol. Returns None on failure."""
    try:
        # Map internal alias used in alerts
        if symbol == "NIFTY50":
            symbol = NIFTY_TICKER
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = info.last_price
        if price and price > 0:
            return round(price, 2)
        # Fallback: last close
        hist = t.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception as e:
        log.warning(f"get_price({symbol}) failed: {e}")
    return None


def get_indices() -> dict:
    """Return {name: {price, change, pct}} for major indices."""
    result = {}
    for name, ticker in INDEX_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            fi = t.fast_info
            price = round(fi.last_price, 2)
            prev  = round(fi.previous_close, 2)
            chg   = round(price - prev, 2)
            pct   = round((chg / prev) * 100, 2)
            result[name] = {"price": price, "change": chg, "pct": pct}
        except Exception as e:
            log.warning(f"Index fetch failed for {name}: {e}")
            result[name] = {"price": 0, "change": 0, "pct": 0}
    return result


def get_stock_quote(symbol: str) -> dict:
    """Return full quote dict for a stock."""
    try:
        t = yf.Ticker(symbol)
        fi = t.fast_info
        price    = round(fi.last_price, 2)
        prev     = round(fi.previous_close, 2)
        chg      = round(price - prev, 2)
        pct      = round((chg / prev) * 100, 2)
        week52h  = round(fi.year_high, 2)
        week52l  = round(fi.year_low, 2)
        return {
            "symbol":   symbol,
            "price":    price,
            "prev":     prev,
            "change":   chg,
            "pct":      pct,
            "week52h":  week52h,
            "week52l":  week52l,
        }
    except Exception as e:
        log.warning(f"get_stock_quote({symbol}) failed: {e}")
        return {}


def get_portfolio_pnl(portfolio: list) -> list:
    """
    Compute day P&L and overall P&L for each holding.
    portfolio = [{"symbol":..., "qty":..., "avg_price":...}, ...]
    """
    rows = []
    for item in portfolio:
        sym   = item["symbol"]
        qty   = item["qty"]
        avg   = item["avg_price"]
        quote = get_stock_quote(sym)
        if not quote:
            continue
        price     = quote["price"]
        day_pnl   = round((quote["change"]) * qty, 2)
        total_pnl = round((price - avg) * qty, 2)
        total_pnl_pct = round(((price - avg) / avg) * 100, 2)
        rows.append({
            **quote,
            "qty":           qty,
            "avg_price":     avg,
            "day_pnl":       day_pnl,
            "total_pnl":     total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "market_value":  round(price * qty, 2),
        })
    return rows


def get_52w_analysis(watchlist: list, danger_pct: float = 8.0) -> list:
    """
    Return 52W analysis for each symbol.
    Flags stocks within danger_pct% of their 52W low.
    """
    results = []
    for sym in watchlist:
        q = get_stock_quote(sym)
        if not q or not q.get("week52l"):
            continue
        price  = q["price"]
        low52  = q["week52l"]
        high52 = q["week52h"]
        pct_from_low  = round(((price - low52) / low52) * 100, 2)
        pct_from_high = round(((high52 - price) / high52) * 100, 2)
        position_pct  = round(((price - low52) / (high52 - low52)) * 100, 2) if high52 != low52 else 50
        results.append({
            "symbol":        sym,
            "price":         price,
            "week52h":       high52,
            "week52l":       low52,
            "pct_from_low":  pct_from_low,
            "pct_from_high": pct_from_high,
            "position_pct":  position_pct,
            "danger":        pct_from_low <= danger_pct,
        })
    # Sort: danger stocks first, then by pct_from_low ascending
    results.sort(key=lambda x: (not x["danger"], x["pct_from_low"]))
    return results


def get_earnings_calendar(watchlist: list) -> list:
    """
    Return upcoming earnings dates for watchlist stocks.
    yfinance provides calendar data for most NSE stocks.
    """
    results = []
    today = date.today()
    for sym in watchlist:
        try:
            t = yf.Ticker(sym)
            cal = t.calendar
            if cal is None or cal.empty:
                continue
            # calendar returns a DataFrame; earnings date in index
            if "Earnings Date" in cal.index:
                raw = cal.loc["Earnings Date"]
                # Could be a list or single value
                if hasattr(raw, "__iter__") and not isinstance(raw, str):
                    earn_date = list(raw)[0]
                else:
                    earn_date = raw
                if hasattr(earn_date, "date"):
                    earn_date = earn_date.date()
                if earn_date and earn_date >= today:
                    days_out = (earn_date - today).days
                    results.append({
                        "symbol":    sym,
                        "date":      earn_date,
                        "days_out":  days_out,
                        "reminder":  days_out <= 3,
                    })
        except Exception as e:
            log.debug(f"Earnings fetch skipped for {sym}: {e}")
    results.sort(key=lambda x: x["date"])
    return results


def get_fii_dii_data() -> dict:
    """
    Fetch FII/DII provisional data from NSE India public endpoint.
    Falls back to graceful placeholder if unavailable.
    """
    try:
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer":    "https://www.nseindia.com/",
            "Accept":     "application/json",
        }
        # NSE requires a session cookie — get it first
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=10)
        data = resp.json()
        # data is a list; find today's FII and DII rows
        fii = next((d for d in data if d.get("category") == "FII/FPI"), {})
        dii = next((d for d in data if d.get("category") == "DII"), {})
        return {
            "fii_buy":  float(fii.get("buyValue", 0)),
            "fii_sell": float(fii.get("sellValue", 0)),
            "fii_net":  float(fii.get("netValue", 0)),
            "dii_buy":  float(dii.get("buyValue", 0)),
            "dii_sell": float(dii.get("sellValue", 0)),
            "dii_net":  float(dii.get("netValue", 0)),
            "source":   "NSE",
        }
    except Exception as e:
        log.warning(f"FII/DII fetch failed: {e} — using placeholder")
        return {
            "fii_buy":  0, "fii_sell": 0, "fii_net": 0,
            "dii_buy":  0, "dii_sell": 0, "dii_net": 0,
            "source":   "unavailable",
        }


def get_news_headlines(watchlist: list, max_per_stock: int = 2) -> list:
    """
    Pull recent news for each stock via yfinance .news property.
    Returns list of {symbol, title, publisher, link, age_hours}.
    """
    items = []
    now_ts = datetime.now().timestamp()
    for sym in watchlist:
        try:
            t    = yf.Ticker(sym)
            news = t.news or []
            count = 0
            for n in news:
                if count >= max_per_stock:
                    break
                pub_ts = n.get("providerPublishTime", 0)
                age_h  = round((now_ts - pub_ts) / 3600, 1)
                items.append({
                    "symbol":    sym,
                    "title":     n.get("title", ""),
                    "publisher": n.get("publisher", ""),
                    "link":      n.get("link", ""),
                    "age_hours": age_h,
                })
                count += 1
        except Exception as e:
            log.debug(f"News fetch skipped for {sym}: {e}")
    # Sort by newest first
    items.sort(key=lambda x: x["age_hours"])
    return items
