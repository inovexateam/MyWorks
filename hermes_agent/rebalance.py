"""
Hermes — Portfolio Rebalancing Suggester
Detects when any stock exceeds target allocation.
Suggests trim/add actions to bring back to balance.
"""

import logging

log = logging.getLogger("hermes.rebalance")

MAX_SINGLE_STOCK_PCT = 20.0
MIN_SINGLE_STOCK_PCT =  2.0
TARGET_CASH_PCT      = 10.0   # always keep 10% cash


def get_rebalance_suggestions(portfolio_pnl: list, total_portfolio_value: float) -> dict:
    """
    Analyse current allocation vs targets.
    Returns: overweight stocks to trim, underweight to add, cash suggestion.
    """
    if not portfolio_pnl or total_portfolio_value <= 0:
        return {}

    # Include cash as a position
    invested = sum(r.get("market_value",0) for r in portfolio_pnl)
    cash_pct = round(((total_portfolio_value - invested) / total_portfolio_value) * 100, 1)

    positions = []
    for r in portfolio_pnl:
        sym  = r["symbol"].replace(".NS","")
        mv   = r.get("market_value", 0)
        pct  = round((mv / total_portfolio_value) * 100, 2)
        positions.append({
            "symbol":    sym,
            "market_val":mv,
            "pct":       pct,
            "overweight": pct > MAX_SINGLE_STOCK_PCT,
            "tiny":       pct < MIN_SINGLE_STOCK_PCT,
        })

    positions.sort(key=lambda x: x["pct"], reverse=True)

    overweight   = [p for p in positions if p["overweight"]]
    tiny         = [p for p in positions if p["tiny"]]
    balanced     = [p for p in positions if not p["overweight"] and not p["tiny"]]
    cash_low     = cash_pct < 5.0
    cash_high    = cash_pct > 30.0

    actions = []

    for p in overweight:
        excess_pct  = p["pct"] - MAX_SINGLE_STOCK_PCT
        excess_val  = round((excess_pct / 100) * total_portfolio_value, 0)
        actions.append({
            "action":  "TRIM",
            "symbol":  p["symbol"],
            "current": p["pct"],
            "target":  MAX_SINGLE_STOCK_PCT,
            "amount":  excess_val,
            "reason":  f"At {p['pct']:.1f}% — reduce to {MAX_SINGLE_STOCK_PCT:.0f}% target",
        })

    if cash_low:
        actions.append({
            "action":  "RAISE CASH",
            "symbol":  "CASH",
            "current": cash_pct,
            "target":  TARGET_CASH_PCT,
            "amount":  round((TARGET_CASH_PCT - cash_pct) / 100 * total_portfolio_value, 0),
            "reason":  f"Cash at {cash_pct:.1f}% — keep at least {TARGET_CASH_PCT:.0f}% for opportunities",
        })

    # Overall health score
    n_over   = len(overweight)
    health   = (
        "HEALTHY"     if n_over == 0 and not cash_low else
        "NEEDS TRIM"  if n_over <= 2 else
        "REBALANCE NOW"
    )

    return {
        "total_value":   total_portfolio_value,
        "cash_pct":      cash_pct,
        "positions":     positions,
        "overweight":    overweight,
        "balanced":      balanced,
        "tiny":          tiny,
        "actions":       actions,
        "health":        health,
        "max_pct":       MAX_SINGLE_STOCK_PCT,
        "cash_target":   TARGET_CASH_PCT,
    }
