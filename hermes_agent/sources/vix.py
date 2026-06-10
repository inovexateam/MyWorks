"""
Hermes — India VIX + Market Sentiment
VIX = Fear index. High VIX = panic = possible buying opportunity.
Low VIX = calm = market may be complacent.
PCR = Put/Call Ratio. High = bearish bets. Low = bullish bets.
"""

import logging
import requests
import yfinance as yf

log = logging.getLogger("hermes.vix")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://www.nseindia.com/",
    "Accept":     "application/json",
}


def get_india_vix() -> dict:
    """
    India VIX — measures expected market volatility for next 30 days.
    Interpretation:
      < 12  : Very calm, possibly complacent
      12-15 : Normal range
      15-20 : Moderate fear, watch carefully
      20-25 : High fear, smart money may start buying
      > 25  : Extreme fear — historically good time to buy quality stocks
      > 30  : Panic — major uncertainty
    """
    try:
        t  = yf.Ticker("^INDIAVIX")
        fi = t.fast_info
        vix   = round(float(fi.last_price), 2)
        prev  = round(float(fi.previous_close), 2)
        chg   = round(vix - prev, 2)
        pct   = round((chg / prev) * 100, 2) if prev else 0

        if vix < 12:
            level = "VERY LOW"
            meaning = "Market is very calm — be cautious, correction possible"
            action  = "Hold positions, don't chase rallies"
        elif vix < 15:
            level = "NORMAL"
            meaning = "Market fear is normal — good environment to trade"
            action  = "Normal trading conditions"
        elif vix < 20:
            level = "ELEVATED"
            meaning = "Some fear in market — volatility picking up"
            action  = "Reduce position sizes slightly, tighten stop-losses"
        elif vix < 25:
            level = "HIGH"
            meaning = "Market is scared — big moves likely in both directions"
            action  = "Only trade high-conviction setups, keep stops tight"
        elif vix < 30:
            level = "VERY HIGH"
            meaning = "Panic setting in — extreme swings expected"
            action  = "Experienced traders: look for buy opportunities in quality stocks"
        else:
            level = "EXTREME PANIC"
            meaning = "Market is in fear mode — historically a buying zone"
            action  = "Quality stocks at discount — start accumulating slowly"

        return {
            "vix":     vix,
            "prev":    prev,
            "change":  chg,
            "pct":     pct,
            "level":   level,
            "meaning": meaning,
            "action":  action,
        }
    except Exception as e:
        log.warning(f"VIX fetch failed: {e}")
        return {"vix": 0, "level": "N/A", "meaning": "Could not fetch", "action": "—"}


def get_market_pcr() -> dict:
    """
    Market-wide Put/Call Ratio from NSE.
    PCR > 1.2 = more puts than calls = bearish sentiment (contrarian: bullish)
    PCR < 0.8 = more calls than puts = bullish sentiment (contrarian: could correct)
    PCR 0.8-1.2 = balanced
    """
    try:
        session = requests.Session()
        session.headers.update(NSE_HEADERS)
        session.get("https://www.nseindia.com", timeout=10)

        r = session.get(
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            timeout=15)
        data = r.json()

        records = data.get("records", {})
        chain   = records.get("data", [])

        total_call_oi = sum(
            row.get("CE", {}).get("openInterest", 0)
            for row in chain if "CE" in row)
        total_put_oi = sum(
            row.get("PE", {}).get("openInterest", 0)
            for row in chain if "PE" in row)

        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 1.0

        if pcr > 1.5:
            level = "EXTREME FEAR"
            meaning = "Too many people are betting market will fall (bearish bets)"
            action  = "Contrarian signal: Market may actually bounce from here"
        elif pcr > 1.2:
            level = "BEARISH"
            meaning = "More people are protecting against a fall than buying"
            action  = "Cautious — wait for confirmation before buying"
        elif pcr > 0.8:
            level = "NEUTRAL"
            meaning = "Balanced bets on both sides — no strong bias"
            action  = "Follow the trend, no extreme fear or greed"
        elif pcr > 0.5:
            level = "BULLISH"
            meaning = "More people are betting market will rise"
            action  = "Momentum is up — ride the trend with tight stops"
        else:
            level = "EXTREME GREED"
            meaning = "Everyone is bullish — contrarian warning sign"
            action  = "Market may be overheated — tighten stops, take partial profits"

        return {
            "pcr":            pcr,
            "total_call_oi":  total_call_oi,
            "total_put_oi":   total_put_oi,
            "level":          level,
            "meaning":        meaning,
            "action":         action,
        }
    except Exception as e:
        log.warning(f"PCR fetch failed: {e}")
        return {"pcr": 0, "level": "N/A", "meaning": "Could not fetch", "action": "—"}


def get_advance_decline() -> dict:
    """
    Advance/Decline ratio — how many stocks rose vs fell today.
    A:D > 2:1 = broad rally     A:D < 1:2 = broad selloff
    """
    try:
        session = requests.Session()
        session.headers.update(NSE_HEADERS)
        session.get("https://www.nseindia.com", timeout=10)
        r = session.get(
            "https://www.nseindia.com/api/live-analysis-variations",
            timeout=15)
        data = r.json() if r.status_code == 200 else []

        advances = sum(1 for d in data if float(d.get("perChange", 0)) > 0)
        declines  = sum(1 for d in data if float(d.get("perChange", 0)) < 0)
        unchanged = sum(1 for d in data if float(d.get("perChange", 0)) == 0)
        total     = advances + declines + unchanged

        ratio = round(advances / declines, 2) if declines > 0 else advances

        if ratio > 2:
            breadth = "STRONG RALLY"
            meaning = "Most stocks are rising today — broad market strength"
        elif ratio > 1.2:
            breadth = "MILD RALLY"
            meaning = "More stocks rising than falling — positive day"
        elif ratio > 0.8:
            breadth = "MIXED"
            meaning = "About equal risers and fallers — no clear direction"
        elif ratio > 0.5:
            breadth = "MILD SELLOFF"
            meaning = "More stocks falling than rising — weak market"
        else:
            breadth = "BROAD SELLOFF"
            meaning = "Most stocks are falling today — market-wide weakness"

        return {
            "advances":  advances,
            "declines":  declines,
            "unchanged": unchanged,
            "total":     total,
            "ratio":     ratio,
            "breadth":   breadth,
            "meaning":   meaning,
        }
    except Exception as e:
        log.warning(f"A/D fetch failed: {e}")
        return {"advances": 0, "declines": 0, "ratio": 1.0,
                "breadth": "N/A", "meaning": "Could not fetch"}


def get_full_sentiment() -> dict:
    """Combined sentiment snapshot."""
    vix = get_india_vix()
    pcr = get_market_pcr()
    ad  = get_advance_decline()

    # Overall market mood
    score = 0
    if vix.get("vix", 15) > 20:  score -= 1
    if vix.get("vix", 15) < 12:  score -= 1  # complacency
    if pcr.get("pcr", 1) > 1.2:  score -= 1
    if pcr.get("pcr", 1) < 0.8:  score += 1
    if ad.get("ratio", 1) > 1.5:  score += 1
    if ad.get("ratio", 1) < 0.7:  score -= 1

    mood = ("BULLISH" if score >= 1 else
            "BEARISH" if score <= -1 else "NEUTRAL")

    return {"vix": vix, "pcr": pcr, "ad": ad, "mood": mood, "score": score}
