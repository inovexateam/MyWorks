"""
Hermes — Global Macro Signals
US 10Y yield, DXY Dollar Index, India 10Y yield, yield curve.
These are the MASTER signals that drive FII flows into/out of India.
"""

import logging
import yfinance as yf

log = logging.getLogger("hermes.global_macro")

MACRO_TICKERS = {
    "US_10Y":       "^TNX",       # US 10-year Treasury yield
    "US_2Y":        "^IRX",       # US 2-year yield (for curve)
    "DXY":          "DX-Y.NYB",   # Dollar Index
    "INDIA_10Y":    "IN10YT=RR",  # India 10-year bond yield
    "GOLD":         "GC=F",       # Gold futures
    "CRUDE_WTI":    "CL=F",       # WTI crude
    "COPPER":       "HG=F",       # Copper (economic health indicator)
    "SP500_VIX":    "^VIX",       # US fear index
}


def _fetch(ticker: str) -> dict:
    try:
        t  = yf.Ticker(ticker)
        fi = t.fast_info
        price = round(float(fi.last_price), 4)
        prev  = round(float(fi.previous_close), 4)
        chg   = round(price - prev, 4)
        pct   = round((chg / prev) * 100, 4) if prev else 0
        return {"price": price, "prev": prev, "change": chg, "pct": pct}
    except Exception as e:
        log.debug(f"Macro fetch failed {ticker}: {e}")
        return {"price": 0, "prev": 0, "change": 0, "pct": 0}


def get_global_macro() -> dict:
    """
    Full global macro snapshot with market impact interpretations.
    """
    data = {}
    for name, ticker in MACRO_TICKERS.items():
        data[name] = _fetch(ticker)

    # Yield curve (10Y - 2Y spread)
    us10y = data["US_10Y"]["price"]
    us2y  = data["US_2Y"]["price"]
    spread = round(us10y - us2y, 3)
    inverted = spread < 0

    # Dollar strength impact
    dxy       = data["DXY"]["price"]
    dxy_chg   = data["DXY"]["pct"]
    dxy_strong = dxy_chg > 0.5   # dollar rising fast = FII selling India

    # US VIX
    us_vix    = data["SP500_VIX"]["price"]

    # Interpret for India market
    signals = []

    # 1. US 10Y yield rising fast
    us10y_pct = data["US_10Y"]["pct"]
    if us10y_pct > 2:
        signals.append({
            "severity": "HIGH",
            "indicator": "US 10Y Yield",
            "value":     f"{us10y:.2f}%",
            "change":    f"{us10y_pct:+.2f}%",
            "impact":    "Negative for India",
            "meaning":   "Rising US yields = FIIs moving money out of India to US bonds",
            "action":    "Expect FII selling pressure. Be cautious with new buys.",
        })
    elif us10y_pct < -2:
        signals.append({
            "severity": "MEDIUM",
            "indicator": "US 10Y Yield",
            "value":     f"{us10y:.2f}%",
            "change":    f"{us10y_pct:+.2f}%",
            "impact":    "Positive for India",
            "meaning":   "Falling US yields = FIIs looking for better returns in India",
            "action":    "Expect FII buying. Good environment for quality stocks.",
        })

    # 2. DXY rising sharply
    if dxy_strong:
        signals.append({
            "severity": "HIGH",
            "indicator": "Dollar Index (DXY)",
            "value":     f"{dxy:.2f}",
            "change":    f"{dxy_chg:+.2f}%",
            "impact":    "Negative for India",
            "meaning":   "Strong dollar = FIIs sell emerging markets including India",
            "action":    "Reduce exposure. IT stocks benefit (they earn in dollars).",
        })

    # 3. Yield curve inverted
    if inverted:
        signals.append({
            "severity": "HIGH",
            "indicator": "US Yield Curve",
            "value":     f"Spread {spread:.3f}%",
            "change":    "INVERTED",
            "impact":    "Recession Warning",
            "meaning":   "Inverted yield curve historically precedes US recession by 12-18 months",
            "action":    "Be cautious. Defensive stocks (FMCG, Pharma) are safer.",
        })

    # 4. US VIX spike
    if us_vix > 25:
        signals.append({
            "severity": "HIGH",
            "indicator": "US Fear Index (VIX)",
            "value":     f"{us_vix:.2f}",
            "change":    "",
            "impact":    "Global risk-off",
            "meaning":   "US markets in fear. Global selloff likely affects India too.",
            "action":    "Stay on sidelines or hedge. Wait for fear to subside.",
        })

    # 5. Gold rising (safe haven demand)
    gold_pct = data["GOLD"]["pct"]
    if gold_pct > 1.5:
        signals.append({
            "severity": "MEDIUM",
            "indicator": "Gold",
            "value":     f"${data['GOLD']['price']:,.2f}",
            "change":    f"{gold_pct:+.2f}%",
            "impact":    "Risk-off signal",
            "meaning":   "Money moving to safe-haven gold = uncertainty in markets",
            "action":    "Caution on aggressive bets. Consider defensive positions.",
        })

    # 6. Copper falling (economic slowdown signal)
    copper_pct = data["COPPER"]["pct"]
    if copper_pct < -2:
        signals.append({
            "severity": "MEDIUM",
            "indicator": "Copper (Economy Signal)",
            "value":     f"${data['COPPER']['price']:.3f}",
            "change":    f"{copper_pct:+.2f}%",
            "impact":    "Global slowdown warning",
            "meaning":   "Copper falls when global economy slows. Affects metal stocks.",
            "action":    "Avoid TATASTEEL, HINDALCO, VEDL. Watch for further weakness.",
        })

    return {
        "data":     data,
        "us10y":    us10y,
        "us2y":     us2y,
        "spread":   spread,
        "inverted": inverted,
        "dxy":      dxy,
        "dxy_chg":  dxy_chg,
        "us_vix":   us_vix,
        "signals":  signals,
    }


def get_global_macro_signals(macro: dict) -> list:
    """Convert macro signals to Hermes signal format."""
    sigs = []
    for s in macro.get("signals", []):
        sigs.append({
            "symbol":    "MARKET",
            "type":      "GLOBAL_MACRO",
            "severity":  s["severity"],
            "timeframe": "1W",
            "summary":   f"🌐 {s['indicator']} {s['value']} {s['change']} — {s['meaning']}",
            "data":      s,
        })
    return sigs
