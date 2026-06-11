"""
Hermes — Tax P&L Calculator
STCG (< 1 year = 15%) vs LTCG (> 1 year = 10% above ₹1L).
Tells you: "hold X more days to save ₹Y in tax."
"""

import logging
from datetime import date, datetime, timedelta

log = logging.getLogger("hermes.tax")

STCG_RATE     = 0.15   # 15% for < 1 year
LTCG_RATE     = 0.10   # 10% for > 1 year
LTCG_EXEMPTION= 100_000.0   # ₹1L exemption per year


def calculate_tax(entry_date: str, entry_price: float,
                  current_price: float, qty: int,
                  exit_date: str = None) -> dict:
    """
    Calculate tax for a single position.
    Returns STCG vs LTCG tax, savings, and advice.
    """
    try:
        entry_dt = datetime.strptime(entry_date, "%Y-%m-%d").date()
    except Exception:
        return {}

    exit_dt    = date.today() if not exit_date else datetime.strptime(exit_date, "%Y-%m-%d").date()
    holding_days = (exit_dt - entry_dt).days
    ltcg_date    = entry_dt + timedelta(days=365)

    pnl          = (current_price - entry_price) * qty
    is_profit    = pnl > 0

    if not is_profit:
        # Loss — can offset against gains
        return {
            "holding_days": holding_days,
            "pnl":          round(pnl, 2),
            "is_profit":    False,
            "tax_stcg":     0,
            "tax_ltcg":     0,
            "advice":       "Loss position — can offset against other gains for tax purposes.",
        }

    # Current tax
    if holding_days >= 365:
        # LTCG — exempt first ₹1L
        taxable = max(0, pnl - LTCG_EXEMPTION)
        tax_now = round(taxable * LTCG_RATE, 2)
        tax_type = "LTCG"
    else:
        tax_now  = round(pnl * STCG_RATE, 2)
        tax_type = "STCG"
        days_to_ltcg = (ltcg_date - exit_dt).days

    # Tax if sold today as STCG vs waiting for LTCG
    stcg_tax     = round(pnl * STCG_RATE, 2)
    ltcg_taxable = max(0, pnl - LTCG_EXEMPTION)
    ltcg_tax     = round(ltcg_taxable * LTCG_RATE, 2)
    tax_saving   = round(stcg_tax - ltcg_tax, 2)

    # Advice
    if holding_days >= 365:
        advice = f"✅ Already LTCG. Tax = ₹{tax_now:,.0f} ({LTCG_RATE*100:.0f}% on gains above ₹1L)"
    else:
        days_to_ltcg = (ltcg_date - exit_dt).days
        if days_to_ltcg > 0 and tax_saving > 5000:
            advice = (f"💡 Hold {days_to_ltcg} more days until {ltcg_date} to save "
                      f"₹{tax_saving:,.0f} in tax (STCG ₹{stcg_tax:,.0f} → LTCG ₹{ltcg_tax:,.0f})")
        elif days_to_ltcg <= 30 and tax_saving > 0:
            advice = f"⏰ Only {days_to_ltcg} days to LTCG — consider waiting to save ₹{tax_saving:,.0f}"
        else:
            advice = f"Current tax (STCG): ₹{stcg_tax:,.0f}. LTCG after {ltcg_date}: ₹{ltcg_tax:,.0f}"

    return {
        "holding_days":  holding_days,
        "entry_date":    entry_date,
        "ltcg_date":     str(ltcg_date),
        "pnl":           round(pnl, 2),
        "is_profit":     True,
        "current_type":  tax_type,
        "tax_now":       tax_now,
        "stcg_tax":      stcg_tax,
        "ltcg_tax":      ltcg_tax,
        "tax_saving":    tax_saving,
        "advice":        advice,
    }


def calculate_portfolio_tax(portfolio: list, portfolio_pnl: list) -> list:
    """
    Calculate tax for all holdings.
    portfolio      = [{symbol, qty, avg_price, entry_date}, ...]  from store
    portfolio_pnl  = [{symbol, price, ...}, ...] from data_fetcher
    """
    price_map = {r["symbol"].replace(".NS",""): r.get("price", 0) for r in portfolio_pnl}
    results   = []

    for h in portfolio:
        sym        = h["symbol"].replace(".NS","")
        cur_price  = price_map.get(sym, h.get("avg_price", 0))
        entry_date = h.get("entry_date", "2024-01-01")   # fallback

        r = calculate_tax(
            entry_date   = entry_date,
            entry_price  = h["avg_price"],
            current_price= cur_price,
            qty          = h["qty"],
        )
        if r:
            r["symbol"] = sym
            results.append(r)

    return results


def total_tax_summary(tax_results: list) -> dict:
    profits = [r for r in tax_results if r.get("is_profit")]
    losses  = [r for r in tax_results if not r.get("is_profit",True)]

    total_pnl      = sum(r["pnl"] for r in tax_results)
    total_stcg_tax = sum(r.get("stcg_tax",0) for r in profits)
    total_ltcg_tax = sum(r.get("ltcg_tax",0) for r in profits)
    total_saving   = sum(r.get("tax_saving",0) for r in profits)
    total_loss     = sum(r["pnl"] for r in losses)

    # Loss offset against STCG
    net_stcg    = max(0, sum(r["pnl"] for r in profits if r.get("current_type")=="STCG") + total_loss)
    net_stcg_tax= round(net_stcg * STCG_RATE, 2)

    return {
        "total_pnl":      round(total_pnl, 2),
        "stcg_tax":       round(total_stcg_tax, 2),
        "ltcg_tax":       round(total_ltcg_tax, 2),
        "potential_saving": round(total_saving, 2),
        "total_loss_offset": round(total_loss, 2),
        "net_tax_after_offset": net_stcg_tax,
    }
