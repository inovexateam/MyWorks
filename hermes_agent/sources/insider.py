"""
Hermes — Insider Trading Tracker
Fetches director/KMP open-market purchases from NSE/BSE filings.
CEO buying from open market = very bullish.
Insider selling after ESOP = cautious signal.
"""

import logging
import requests

log = logging.getLogger("hermes.insider")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://www.nseindia.com/",
    "Accept":     "application/json",
}


def _nse_session():
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try: s.get("https://www.nseindia.com", timeout=10)
    except Exception: pass
    return s


def get_insider_trades(watchlist: list) -> list:
    """
    Fetch insider trading disclosures from NSE.
    Filters to open-market buys/sells by directors/KMP.
    """
    session  = _nse_session()
    watch_syms = {s.replace(".NS","").upper() for s in watchlist}
    results  = []

    try:
        url  = "https://www.nseindia.com/api/corporates-pit"
        params = {"index":"equities", "from_date":"", "to_date":"", "symbol":""}
        r = session.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return []

        data = r.json()
        items = data.get("data", []) if isinstance(data, dict) else (data or [])

        for item in items:
            sym = str(item.get("symbol","")).upper()
            if sym not in watch_syms:
                continue

            person   = item.get("personCategory","")
            acq_type = item.get("acquisitionMode","")
            qty_acq  = int(item.get("noOfSecAcq",  0) or 0)
            qty_sold = int(item.get("noOfSecSold", 0) or 0)
            val_acq  = float(item.get("valueOfSecAcq",  0) or 0)
            val_sold = float(item.get("valueOfSecSold", 0) or 0)
            date_str = item.get("date","")

            action = "BUY" if qty_acq > qty_sold else "SELL"
            qty    = qty_acq if action=="BUY" else qty_sold
            value  = val_acq if action=="BUY" else val_sold

            # Only flag meaningful trades
            if qty == 0:
                continue

            is_key_person = any(k in person.upper() for k in
                               ["DIRECTOR","MD","CEO","CFO","KMP","PROMOTER","CHAIRMAN"])
            is_open_market = "MARKET" in acq_type.upper() or "OPEN" in acq_type.upper()

            severity = (
                "HIGH"   if (action=="BUY" and is_key_person and is_open_market) else
                "MEDIUM" if is_key_person else
                "LOW"
            )

            results.append({
                "symbol":      sym,
                "person":      person[:40],
                "action":      action,
                "qty":         qty,
                "value":       value,
                "value_cr":    round(value / 1e7, 2),
                "mode":        acq_type,
                "date":        date_str,
                "is_open_market": is_open_market,
                "is_key_person":  is_key_person,
                "severity":    severity,
                "meaning": (
                    f"Director/CEO buying from OPEN MARKET — very bullish signal"
                    if action=="BUY" and is_key_person and is_open_market else
                    f"Insider selling — monitor closely"
                    if action=="SELL" and is_key_person else
                    f"Insider {action.lower()} {qty:,} shares"
                ),
            })

    except Exception as e:
        log.warning(f"Insider trades fetch failed: {e}")

    # Sort: open market buys by key persons first
    results.sort(key=lambda x: (
        x["is_key_person"] and x["is_open_market"] and x["action"]=="BUY",
        x["value_cr"]
    ), reverse=True)

    return results
