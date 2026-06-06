"""
Hermes — NSE Source
Fetches: bulk/block deals, OI spikes, delivery %, circuit breakers, FII/DII trend.
All from NSE public endpoints (no API key needed).
"""

import requests
import logging
from datetime import datetime, date

log = logging.getLogger("hermes.nse")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://www.nseindia.com/",
    "Accept":     "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
})

NSE_BASE = "https://www.nseindia.com"


def _refresh_session():
    """NSE requires a valid browser session cookie."""
    try:
        SESSION.get(NSE_BASE, timeout=10)
        SESSION.get(f"{NSE_BASE}/market-data/live-equity-market", timeout=10)
    except Exception as e:
        log.warning(f"Session refresh failed: {e}")


def _get(url: str, params: dict = None) -> dict | list | None:
    try:
        _refresh_session()
        r = SESSION.get(url, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        log.warning(f"NSE {url} returned {r.status_code}")
    except Exception as e:
        log.warning(f"NSE fetch error {url}: {e}")
    return None


# ── Bulk & Block Deals ────────────────────────────────────────────────────────

def get_bulk_deals(watchlist: list) -> list:
    """
    Returns bulk deals for watchlist stocks today.
    A bulk deal = >0.5% of total shares traded by a single client.
    """
    data = _get(f"{NSE_BASE}/api/bulk-deal-archives", params={"number": 10, "type": "bulk"})
    if not data:
        return []

    watch_syms = {s.replace(".NS", "").upper() for s in watchlist}
    results = []
    for deal in (data if isinstance(data, list) else data.get("data", [])):
        sym = str(deal.get("symbol", "")).upper()
        if sym in watch_syms:
            qty      = deal.get("quantityTraded", 0)
            price    = deal.get("tradePrice", 0)
            client   = deal.get("clientName", "Unknown")
            buy_sell = deal.get("buySell", "")
            results.append({
                "symbol":   sym,
                "client":   client,
                "buy_sell": buy_sell,
                "qty":      qty,
                "price":    price,
                "value_cr": round((qty * price) / 1e7, 2),
                "type":     "BULK",
            })
    return results


def get_block_deals(watchlist: list) -> list:
    """Block deals = negotiated large trades (usually institutions)."""
    data = _get(f"{NSE_BASE}/api/block-deal-archives", params={"number": 10, "type": "block"})
    if not data:
        return []

    watch_syms = {s.replace(".NS", "").upper() for s in watchlist}
    results = []
    for deal in (data if isinstance(data, list) else data.get("data", [])):
        sym = str(deal.get("symbol", "")).upper()
        if sym in watch_syms:
            qty      = deal.get("quantityTraded", 0)
            price    = deal.get("tradePrice", 0)
            client   = deal.get("clientName", "Unknown")
            buy_sell = deal.get("buySell", "")
            results.append({
                "symbol":   sym,
                "client":   client,
                "buy_sell": buy_sell,
                "qty":      qty,
                "price":    price,
                "value_cr": round((qty * price) / 1e7, 2),
                "type":     "BLOCK",
            })
    return results


# ── Options Chain — OI Spike Detection ───────────────────────────────────────

def get_oi_analysis(symbol: str) -> dict | None:
    """
    Fetch options chain for a symbol.
    Returns max pain, PCR (put-call ratio), and top OI buildup strikes.
    High PCR (>1.2) = bullish. Low PCR (<0.8) = bearish.
    """
    sym = symbol.replace(".NS", "").upper()
    data = _get(f"{NSE_BASE}/api/option-chain-equities", params={"symbol": sym})
    if not data:
        return None

    try:
        records = data.get("records", {})
        exp_dates = records.get("expiryDates", [])
        if not exp_dates:
            return None

        nearest_exp = exp_dates[0]
        chain = records.get("data", [])

        total_call_oi = 0
        total_put_oi  = 0
        strikes = {}

        for row in chain:
            if row.get("expiryDate") != nearest_exp:
                continue
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {})
            pe = row.get("PE", {})
            ce_oi = ce.get("openInterest", 0)
            pe_oi = pe.get("openInterest", 0)
            total_call_oi += ce_oi
            total_put_oi  += pe_oi
            strikes[strike] = {"ce_oi": ce_oi, "pe_oi": pe_oi}

        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

        # Max pain = strike with max combined OI
        max_pain_strike = max(strikes, key=lambda k: strikes[k]["ce_oi"] + strikes[k]["pe_oi"], default=0)

        # Top resistance (highest call OI = market expects price won't go above)
        top_resistance = max(strikes, key=lambda k: strikes[k]["ce_oi"], default=0)
        # Top support (highest put OI = market expects price won't fall below)
        top_support    = max(strikes, key=lambda k: strikes[k]["pe_oi"], default=0)

        sentiment = "BULLISH" if pcr > 1.2 else ("BEARISH" if pcr < 0.8 else "NEUTRAL")

        return {
            "symbol":         sym,
            "expiry":         nearest_exp,
            "pcr":            pcr,
            "sentiment":      sentiment,
            "max_pain":       max_pain_strike,
            "resistance":     top_resistance,
            "support":        top_support,
            "total_call_oi":  total_call_oi,
            "total_put_oi":   total_put_oi,
        }
    except Exception as e:
        log.warning(f"OI analysis failed for {sym}: {e}")
        return None


# ── Delivery % ────────────────────────────────────────────────────────────────

def get_delivery_data(watchlist: list) -> list:
    """
    High delivery % (>60%) = conviction buying, not just speculation.
    Fetched from NSE bhavcopy-style equity data.
    """
    data = _get(f"{NSE_BASE}/api/live-analysis-variations")
    if not data:
        return []

    watch_syms = {s.replace(".NS", "").upper() for s in watchlist}
    results = []

    for item in data if isinstance(data, list) else []:
        sym = str(item.get("symbol", "")).upper()
        if sym not in watch_syms:
            continue
        deliv_pct = item.get("deliveryToTradedQuantity", 0)
        results.append({
            "symbol":       sym,
            "delivery_pct": round(float(deliv_pct), 2),
            "high_conviction": float(deliv_pct) >= 60,
        })
    return results


# ── Circuit Breakers ──────────────────────────────────────────────────────────

def get_circuit_stocks(watchlist: list) -> list:
    """Detect if any watchlist stock has hit upper or lower circuit."""
    data = _get(f"{NSE_BASE}/api/live-analysis-variations")
    if not data:
        return []

    watch_syms = {s.replace(".NS", "").upper() for s in watchlist}
    results = []

    for item in data if isinstance(data, list) else []:
        sym   = str(item.get("symbol", "")).upper()
        if sym not in watch_syms:
            continue
        pct   = float(item.get("perChange", 0))
        price = float(item.get("lastPrice", 0))
        if abs(pct) >= 19.5:   # NSE circuit is typically ±20%
            results.append({
                "symbol":    sym,
                "price":     price,
                "change_pct": pct,
                "circuit":   "UPPER" if pct > 0 else "LOWER",
            })
    return results


# ── FII/DII Trend (5-day) ─────────────────────────────────────────────────────

def get_fii_dii_trend() -> list:
    """
    Returns last 5 days of FII/DII net flow.
    Sustained FII buying (3+ days) = strong bullish signal.
    """
    data = _get(f"{NSE_BASE}/api/fiidiiTradeReact")
    if not data or not isinstance(data, list):
        return []

    rows = []
    for d in data[:10]:   # last 10 records
        cat = d.get("category", "")
        if cat not in ("FII/FPI", "DII"):
            continue
        rows.append({
            "date":     d.get("date", ""),
            "category": cat,
            "buy":      float(d.get("buyValue",  0)),
            "sell":     float(d.get("sellValue", 0)),
            "net":      float(d.get("netValue",  0)),
        })
    return rows


# ── Promoter Activity (via NSE filings) ──────────────────────────────────────

def get_promoter_activity(watchlist: list) -> list:
    """
    Scrapes recent insider/promoter shareholding changes.
    Promoter buying = high conviction. Promoter selling = flag.
    """
    data = _get(f"{NSE_BASE}/api/corporates-pit",
                params={"index": "equities", "from_date": "", "to_date": ""})
    if not data:
        return []

    watch_syms = {s.replace(".NS", "").upper() for s in watchlist}
    results = []

    for item in (data.get("data", []) if isinstance(data, dict) else []):
        sym = str(item.get("symbol", "")).upper()
        if sym not in watch_syms:
            continue
        acq_type = item.get("acquisitionMode", "")
        person   = item.get("personCategory", "")
        if "PROMOTER" in person.upper():
            qty    = item.get("noOfSecAcq", 0) or item.get("noOfSecSold", 0)
            action = "BUY" if item.get("noOfSecAcq", 0) > 0 else "SELL"
            results.append({
                "symbol": sym,
                "person": person,
                "action": action,
                "qty":    qty,
                "mode":   acq_type,
                "date":   item.get("date", ""),
            })
    return results
