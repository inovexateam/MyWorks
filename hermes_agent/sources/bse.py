"""
Hermes — BSE Source
Fetches corporate actions: dividends, splits, bonuses, rights issues.
Ex-dividend date = price drops by dividend amount. Always alert before it.
"""

import requests
import logging
from datetime import date, datetime, timedelta

log = logging.getLogger("hermes.bse")

BSE_BASE = "https://api.bseindia.com/BseIndiaAPI/api"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer":    "https://www.bseindia.com/",
    "Accept":     "application/json",
}

# BSE uses numeric codes — map NSE symbols to BSE codes via yfinance fallback
NSE_TO_BSE_SCRIP = {
    "RELIANCE":  "500325",
    "TCS":       "532540",
    "INFY":      "500209",
    "HDFCBANK":  "500180",
    "ICICIBANK": "532174",
    "WIPRO":     "507685",
    "SBIN":      "500112",
    "BAJFINANCE":"500034",
    "NIFTY50":   None,
}


def _get(url: str, params: dict = None) -> dict | list | None:
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning(f"BSE fetch error: {e}")
    return None


def _sym_clean(symbol: str) -> str:
    return symbol.replace(".NS", "").upper()


# ── Corporate Actions ─────────────────────────────────────────────────────────

def get_corporate_actions(watchlist: list, days_ahead: int = 30) -> list:
    """
    Returns upcoming corporate actions within days_ahead for watchlist.
    Includes: dividend, bonus, split, rights, AGM/EGM.
    Uses NSE corporate actions endpoint (more reliable than BSE for broad list).
    """
    import requests as req

    session = req.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer":    "https://www.nseindia.com/",
        "Accept":     "application/json",
    })

    try:
        session.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass

    today    = date.today()
    end_date = today + timedelta(days=days_ahead)
    results  = []
    watch_syms = {_sym_clean(s) for s in watchlist}

    try:
        url  = "https://www.nseindia.com/api/corporates-corporateActions"
        params = {
            "index":     "equities",
            "from_date": today.strftime("%d-%m-%Y"),
            "to_date":   end_date.strftime("%d-%m-%Y"),
        }
        r = session.get(url, params=params, timeout=15)
        data = r.json() if r.status_code == 200 else []

        for item in (data if isinstance(data, list) else []):
            sym = _sym_clean(item.get("symbol", ""))
            if sym not in watch_syms:
                continue

            action_type = item.get("purpose", "").upper()
            ex_date_str = item.get("exDate", "") or item.get("exdividendDate", "")

            # Parse ex-date
            ex_date = None
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    ex_date = datetime.strptime(ex_date_str, fmt).date()
                    break
                except Exception:
                    continue

            if not ex_date or ex_date < today:
                continue

            days_out = (ex_date - today).days

            # Classify
            category = "OTHER"
            if "DIVIDEND" in action_type:
                category = "DIVIDEND"
                # Extract amount if present
            elif "BONUS" in action_type:
                category = "BONUS"
            elif "SPLIT" in action_type:
                category = "SPLIT"
            elif "RIGHTS" in action_type:
                category = "RIGHTS"
            elif "AGM" in action_type or "EGM" in action_type:
                category = "MEETING"

            results.append({
                "symbol":   sym,
                "action":   item.get("purpose", ""),
                "category": category,
                "ex_date":  str(ex_date),
                "days_out": days_out,
                "urgent":   days_out <= 5,
                "details":  item.get("remarks", ""),
            })

    except Exception as e:
        log.warning(f"Corporate actions fetch failed: {e}")

    results.sort(key=lambda x: x["days_out"])
    return results


def get_dividend_calendar(watchlist: list) -> list:
    """Convenience: filter corporate actions to dividends only."""
    all_actions = get_corporate_actions(watchlist, days_ahead=60)
    return [a for a in all_actions if a["category"] == "DIVIDEND"]


# ── Results Calendar (earnings from BSE) ──────────────────────────────────────

def get_results_impact(watchlist: list) -> list:
    """
    Fetches recent quarterly results and flags beat/miss vs estimates.
    Uses BSE quarterly results API.
    """
    watch_syms = {_sym_clean(s) for s in watchlist}
    results = []

    for sym in watch_syms:
        scrip = NSE_TO_BSE_SCRIP.get(sym)
        if not scrip:
            continue
        try:
            url  = f"{BSE_BASE}/FinancialResultNew/w"
            params = {"pageno": 1, "strCat": "-1", "strPrevDate": "",
                      "strScrip": scrip, "strSearch": "P", "strToDate": "",
                      "strType": "C"}
            data = _get(url, params)
            if not data:
                continue
            items = data.get("Table", [])
            if not items:
                continue
            latest = items[0]
            results.append({
                "symbol":       sym,
                "period":       latest.get("audited", ""),
                "revenue":      latest.get("netsales", 0),
                "net_profit":   latest.get("netprofit", 0),
                "eps":          latest.get("eps", 0),
                "date":         latest.get("newsdate", ""),
            })
        except Exception as e:
            log.debug(f"Results fetch skipped for {sym}: {e}")

    return results
