"""
Hermes — Promoter Pledge + MF Stake Changes
Promoter pledging shares = financial stress = sell signal.
MF buying quietly = conviction = buy signal.
Data from NSE/BSE quarterly shareholding pattern filings.
"""

import logging
import requests
import yfinance as yf

log = logging.getLogger("hermes.promoter")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://www.nseindia.com/",
    "Accept":     "application/json",
}


def _nse_session():
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass
    return s


def get_shareholding_pattern(symbol: str) -> dict | None:
    """
    Fetch latest shareholding pattern from NSE.
    Returns promoter %, FII %, DII %, public % and pledge %.
    """
    sym = symbol.replace(".NS", "").upper()
    try:
        session = _nse_session()
        url     = f"https://www.nseindia.com/api/corporate-share-holdings-master?symbol={sym}"
        r       = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None

        # Latest quarter is first item
        latest = data[0] if isinstance(data, list) else data

        promoter_pct = float(latest.get("promoterAndPromoterGroupShareholding", 0))
        pledge_pct   = float(latest.get("promoterAndPromoterGroupPledge",       0))
        fii_pct      = float(latest.get("foreignInstitutionalInvestors",        0))
        dii_pct      = float(latest.get("domesticInstitutionalInvestors",       0))
        public_pct   = float(latest.get("public",                               0))
        period       = latest.get("date", "")

        # Get previous quarter for change detection
        pledge_prev  = 0.0
        fii_prev     = 0.0
        dii_prev     = 0.0
        if isinstance(data, list) and len(data) > 1:
            prev         = data[1]
            pledge_prev  = float(prev.get("promoterAndPromoterGroupPledge", 0))
            fii_prev     = float(prev.get("foreignInstitutionalInvestors",  0))
            dii_prev     = float(prev.get("domesticInstitutionalInvestors", 0))

        pledge_chg = round(pledge_pct - pledge_prev, 2)
        fii_chg    = round(fii_pct    - fii_prev,    2)
        dii_chg    = round(dii_pct    - dii_prev,    2)

        # Risk assessment
        pledge_risk = (
            "HIGH"   if pledge_pct > 50 else
            "MEDIUM" if pledge_pct > 25 else
            "LOW"    if pledge_pct > 10 else
            "NONE"
        )

        return {
            "symbol":       sym,
            "period":       period,
            "promoter_pct": round(promoter_pct, 2),
            "pledge_pct":   round(pledge_pct,   2),
            "pledge_prev":  round(pledge_prev,  2),
            "pledge_chg":   pledge_chg,
            "pledge_risk":  pledge_risk,
            "fii_pct":      round(fii_pct,      2),
            "fii_chg":      fii_chg,
            "dii_pct":      round(dii_pct,      2),
            "dii_chg":      dii_chg,
            "public_pct":   round(public_pct,   2),
            "pledge_increasing": pledge_chg > 2.0,
            "pledge_decreasing": pledge_chg < -2.0,
            "mf_buying":    dii_chg > 1.0,
            "mf_selling":   dii_chg < -1.0,
            "fii_buying":   fii_chg > 1.0,
            "fii_selling":  fii_chg < -1.0,
        }
    except Exception as e:
        log.warning(f"Shareholding fetch failed {sym}: {e}")
        return None


def get_watchlist_shareholding(watchlist: list) -> list:
    """Fetch shareholding for all watchlist stocks."""
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        data = get_shareholding_pattern(sym)
        if data:
            results.append(data)
    return results


def get_pledge_alerts(shareholding_data: list) -> list:
    """
    Return alerts for:
    - High pledge % (>25%)
    - Pledge increasing quarter on quarter
    - MF/FII buying or selling significantly
    """
    alerts = []
    for s in shareholding_data:
        sym = s["symbol"]

        # High pledge
        if s["pledge_pct"] > 25:
            severity = "HIGH" if s["pledge_pct"] > 50 else "MEDIUM"
            alerts.append({
                "symbol":   sym,
                "type":     "HIGH_PLEDGE",
                "severity": severity,
                "pledge":   s["pledge_pct"],
                "message":  f"Promoter has pledged {s['pledge_pct']:.1f}% of shares — financial stress signal",
                "action":   "Be careful — if stock falls, forced selling can accelerate the drop",
            })

        # Pledge increasing
        if s["pledge_increasing"]:
            alerts.append({
                "symbol":   sym,
                "type":     "PLEDGE_INCREASING",
                "severity": "HIGH",
                "pledge":   s["pledge_pct"],
                "message":  f"Pledge INCREASED by {s['pledge_chg']:+.1f}% this quarter ({s['pledge_pct']:.1f}% total)",
                "action":   "Warning: Promoter borrowing more against shares — watch closely",
            })

        # Pledge decreasing (positive)
        if s["pledge_decreasing"]:
            alerts.append({
                "symbol":   sym,
                "type":     "PLEDGE_DECREASING",
                "severity": "LOW",
                "pledge":   s["pledge_pct"],
                "message":  f"Pledge REDUCED by {abs(s['pledge_chg']):.1f}% this quarter — good sign",
                "action":   "Promoter repaying loans — positive for stock",
            })

        # MF buying
        if s["mf_buying"]:
            alerts.append({
                "symbol":   sym,
                "type":     "MF_BUYING",
                "severity": "MEDIUM",
                "change":   s["dii_chg"],
                "message":  f"Mutual Funds increased stake by {s['dii_chg']:+.1f}% this quarter",
                "action":   "Smart Indian money is accumulating — positive signal",
            })

        # FII buying
        if s["fii_buying"]:
            alerts.append({
                "symbol":   sym,
                "type":     "FII_BUYING",
                "severity": "MEDIUM",
                "change":   s["fii_chg"],
                "message":  f"Foreign Investors increased stake by {s['fii_chg']:+.1f}% this quarter",
                "action":   "Foreign institutional money entering — bullish for stock",
            })

        # FII selling
        if s["fii_selling"]:
            alerts.append({
                "symbol":   sym,
                "type":     "FII_SELLING",
                "severity": "MEDIUM",
                "change":   s["fii_chg"],
                "message":  f"Foreign Investors reduced stake by {abs(s['fii_chg']):.1f}% this quarter",
                "action":   "Foreign money exiting — watch for continued weakness",
            })

    return alerts
