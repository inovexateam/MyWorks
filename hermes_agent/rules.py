"""
Hermes — Golden Rules Engine
7 rules checked every morning. Fires SAFE / CAUTION / AVOID.
The single most important discipline tool for beginners.
"""

import logging
from datetime import datetime
import yfinance as yf
import pytz

log = logging.getLogger("hermes.rules")

IST = pytz.timezone("Asia/Kolkata")


def check_golden_rules(portfolio: list, watchlist: list) -> dict:
    """
    Check all 7 golden rules and return verdict + details.
    """
    rules  = []
    passed = 0

    # Rule 1: Is Nifty in uptrend? (price > 50-day MA)
    try:
        df    = yf.Ticker("^NSEI").history(period="3mo", interval="1d")
        price = float(df["Close"].iloc[-1])
        ma50  = float(df["Close"].rolling(50).mean().iloc[-1])
        ok    = price > ma50
        rules.append({
            "rule":    "Nifty is in uptrend (above 50-day average)",
            "pass":    ok,
            "value":   f"Nifty {price:,.0f} vs MA50 {ma50:,.0f}",
            "explain": "Don't fight the market trend. If Nifty is falling, avoid buying.",
        })
        if ok: passed += 1
    except Exception as e:
        log.debug(f"Rule 1 failed: {e}")
        rules.append({"rule":"Nifty uptrend","pass":None,"value":"N/A","explain":"Could not check"})

    # Rule 2: India VIX below 20
    try:
        from sources.vix import get_india_vix
        vix_data = get_india_vix()
        vix = vix_data.get("vix", 15)
        ok  = vix < 20
        rules.append({
            "rule":    "India VIX below 20 (fear is manageable)",
            "pass":    ok,
            "value":   f"VIX = {vix:.2f}",
            "explain": "High VIX = high volatility = risky to enter new positions.",
        })
        if ok: passed += 1
    except Exception as e:
        log.debug(f"Rule 2 failed: {e}")
        rules.append({"rule":"VIX < 20","pass":None,"value":"N/A","explain":"Could not check"})

    # Rule 3: FII net positive last 3 days
    try:
        from sources.nse import get_fii_dii_trend
        trend    = get_fii_dii_trend()
        fii_rows = [r for r in trend if r.get("category")=="FII/FPI"][:3]
        nets     = [r["net"] for r in fii_rows]
        ok       = sum(1 for n in nets if n > 0) >= 2
        avg_net  = sum(nets)/len(nets) if nets else 0
        rules.append({
            "rule":    "FII net positive last 3 days",
            "pass":    ok,
            "value":   f"Avg FII net ₹{avg_net/1e7:.1f}Cr",
            "explain": "Foreign money flowing in = market support. Flowing out = weakness.",
        })
        if ok: passed += 1
    except Exception as e:
        log.debug(f"Rule 3 failed: {e}")
        rules.append({"rule":"FII positive","pass":None,"value":"N/A","explain":"Could not check"})

    # Rule 4: No earnings within 7 days for held stocks
    try:
        from data_fetcher import get_earnings_calendar
        earnings  = get_earnings_calendar([h["symbol"] for h in portfolio])
        imminent  = [e for e in earnings if e["days_out"] <= 7]
        ok        = len(imminent) == 0
        rules.append({
            "rule":    "No earnings within 7 days for held stocks",
            "pass":    ok,
            "value":   f"{len(imminent)} stock(s) reporting soon" if imminent else "All clear",
            "explain": "Stocks move wildly on results. Avoid adding just before announcement.",
        })
        if ok: passed += 1
    except Exception as e:
        log.debug(f"Rule 4 failed: {e}")
        rules.append({"rule":"No imminent earnings","pass":None,"value":"N/A","explain":"Could not check"})

    # Rule 5: No major macro event in next 2 days
    try:
        from sources.economic_calendar import get_upcoming_events
        events  = get_upcoming_events(days_ahead=2)
        high_ev = [e for e in events if e["impact"]=="HIGH"]
        ok      = len(high_ev) == 0
        rules.append({
            "rule":    "No major macro event in next 2 days",
            "pass":    ok,
            "value":   high_ev[0]["event"] if high_ev else "None",
            "explain": "Markets are unpredictable around RBI/Fed events. Avoid big trades.",
        })
        if ok: passed += 1
    except Exception as e:
        log.debug(f"Rule 5 failed: {e}")
        rules.append({"rule":"No macro event soon","pass":None,"value":"N/A","explain":"Could not check"})

    # Rule 6: No circuit breakers on watchlist stocks
    try:
        from sources.nse import get_circuit_stocks
        circuits = get_circuit_stocks(watchlist)
        ok       = len(circuits) == 0
        rules.append({
            "rule":    "No circuit breakers on your stocks",
            "pass":    ok,
            "value":   f"{len(circuits)} stock(s) in circuit" if circuits else "All clear",
            "explain": "Circuit = extreme move. Wait for normalcy before trading that stock.",
        })
        if ok: passed += 1
    except Exception as e:
        log.debug(f"Rule 6 failed: {e}")
        rules.append({"rule":"No circuit stocks","pass":None,"value":"N/A","explain":"Could not check"})

    # Rule 7: DXY not rising sharply (dollar not too strong)
    try:
        from sources.global_macro import get_global_macro
        macro   = get_global_macro()
        dxy_pct = macro.get("dxy_chg", 0)
        ok      = dxy_pct < 0.5
        rules.append({
            "rule":    "Dollar not rising sharply (DXY change < 0.5%)",
            "pass":    ok,
            "value":   f"DXY {dxy_pct:+.2f}% today",
            "explain": "Strong dollar = FIIs sell Indian stocks. DXY rising = caution.",
        })
        if ok: passed += 1
    except Exception as e:
        log.debug(f"Rule 7 failed: {e}")
        rules.append({"rule":"DXY not spiking","pass":None,"value":"N/A","explain":"Could not check"})

    total   = len(rules)
    verdict = (
        "✅ SAFE TO TRADE"   if passed >= 6 else
        "⚠️ CAUTION"         if passed >= 4 else
        "🔴 AVOID NEW TRADES" if passed >= 2 else
        "🚫 STAY OUT TODAY"
    )

    explanation = {
        "✅ SAFE TO TRADE":    "Most conditions are positive. Good day to trade with your plan.",
        "⚠️ CAUTION":          "Mixed conditions. Trade smaller sizes. Stick to high-conviction setups only.",
        "🔴 AVOID NEW TRADES": "Multiple warning signs. Do not enter new positions. Manage existing ones.",
        "🚫 STAY OUT TODAY":   "Almost all conditions are negative. Cash is a position. Sit this one out.",
    }.get(verdict, "")

    return {
        "verdict":     verdict,
        "explanation": explanation,
        "passed":      passed,
        "total":       total,
        "rules":       rules,
        "date":        datetime.now(IST).strftime("%d %b %Y"),
        "time":        datetime.now(IST).strftime("%H:%M IST"),
    }
