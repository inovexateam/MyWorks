"""
Hermes — Earnings Beat/Miss History
Last 4 quarters: actual EPS vs analyst estimate.
Consistent beater = re-rates higher. Consistent misser = avoid.
"""

import logging
import yfinance as yf

log = logging.getLogger("hermes.earnings_history")


def get_earnings_history(symbol: str) -> dict | None:
    """
    Fetch last 4 quarters of EPS: actual vs estimate.
    Returns beat/miss streak and surprise %.
    """
    try:
        t = yf.Ticker(symbol if symbol.endswith(".NS") else symbol + ".NS")
        earnings = t.quarterly_earnings
        if earnings is None or earnings.empty:
            return None

        records = []
        for period, row in earnings.iterrows():
            actual   = row.get("Actual",   None)
            estimate = row.get("Estimate", None)
            if actual is None:
                continue
            surprise_pct = None
            result       = "N/A"
            if estimate and estimate != 0:
                surprise_pct = round(((actual - estimate) / abs(estimate)) * 100, 1)
                result = "BEAT" if actual > estimate else ("MISS" if actual < estimate else "INLINE")
            records.append({
                "period":       str(period),
                "actual":       round(float(actual),   2),
                "estimate":     round(float(estimate), 2) if estimate else None,
                "surprise_pct": surprise_pct,
                "result":       result,
            })

        if not records:
            return None

        # Streak
        streak_count = 0
        streak_type  = records[0]["result"] if records else "N/A"
        for r in records:
            if r["result"] == streak_type and streak_type in ("BEAT","MISS"):
                streak_count += 1
            else:
                break

        beats  = sum(1 for r in records if r["result"] == "BEAT")
        misses = sum(1 for r in records if r["result"] == "MISS")
        avg_surprise = round(
            sum(r["surprise_pct"] for r in records if r["surprise_pct"] is not None)
            / max(1, sum(1 for r in records if r["surprise_pct"] is not None)), 1)

        quality = (
            "EXCELLENT" if beats >= 3 and avg_surprise > 5 else
            "GOOD"      if beats >= 2 else
            "AVERAGE"   if beats == misses else
            "POOR"
        )

        return {
            "symbol":       symbol.replace(".NS",""),
            "records":      records[:4],
            "beats":        beats,
            "misses":       misses,
            "streak_type":  streak_type,
            "streak_count": streak_count,
            "avg_surprise": avg_surprise,
            "quality":      quality,
            "consistent_beater": beats >= 3,
            "consistent_misser": misses >= 3,
        }
    except Exception as e:
        log.debug(f"Earnings history failed {symbol}: {e}")
        return None


def get_watchlist_earnings_history(watchlist: list) -> list:
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        r = get_earnings_history(sym)
        if r:
            results.append(r)
    results.sort(key=lambda x: x["beats"], reverse=True)
    return results
