"""
Hermes — Fundamentals Screener
P/E ratio, Debt/Equity, ROE, Revenue growth, Free Cash Flow.
Uses yfinance .info which pulls from Yahoo Finance fundamentals.
Supplemented by Screener.in scraping for Indian-specific data.
"""

import logging
import yfinance as yf
import requests
from bs4 import BeautifulSoup

log = logging.getLogger("hermes.fundamentals")

# Sector average P/E benchmarks (NSE India approximate)
SECTOR_PE = {
    "IT":      25, "Banking": 14, "FMCG":  45, "Auto":   18,
    "Pharma":  28, "Realty":  30, "Metal":  10, "Energy": 12,
    "Infra":   20, "Default": 22,
}

SECTOR_MAP = {
    "INFY": "IT",    "TCS": "IT",      "WIPRO": "IT",    "HCLTECH": "IT",
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking", "AXISBANK": "Banking",
    "HINDUNILVR": "FMCG",  "NESTLEIND": "FMCG",   "BRITANNIA": "FMCG",
    "MARUTI": "Auto",      "TATAMOTORS": "Auto",   "BAJAJ-AUTO": "Auto",
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma",    "CIPLA": "Pharma",
    "RELIANCE": "Energy",  "ONGC": "Energy",       "BPCL": "Energy",
    "TATASTEEL": "Metal",  "HINDALCO": "Metal",    "JSWSTEEL": "Metal",
    "DLF": "Realty",       "GODREJPROP": "Realty",
}


def get_fundamentals(symbol: str) -> dict | None:
    """
    Full fundamental snapshot for one stock.
    Returns key metrics with interpretation for beginners.
    """
    sym = symbol.replace(".NS", "").upper()
    try:
        t    = yf.Ticker(symbol if symbol.endswith(".NS") else symbol + ".NS")
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            return None

        price        = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        pe           = info.get("trailingPE")
        fwd_pe       = info.get("forwardPE")
        pb           = info.get("priceToBook")
        roe          = info.get("returnOnEquity")
        debt_eq      = info.get("debtToEquity")
        rev_growth   = info.get("revenueGrowth")        # YoY
        earn_growth  = info.get("earningsGrowth")
        profit_margin= info.get("profitMargins")
        fcf          = info.get("freeCashflow")
        market_cap   = info.get("marketCap")
        div_yield    = info.get("dividendYield")
        beta         = info.get("beta")
        sector       = info.get("sector", SECTOR_MAP.get(sym, "Default"))
        name         = info.get("longName", sym)
        analyst_rec  = info.get("recommendationKey", "—")
        target_price = info.get("targetMeanPrice")

        # Sector average PE
        sector_key  = _map_sector(sector)
        sector_pe   = SECTOR_PE.get(sector_key, SECTOR_PE["Default"])

        # Scoring
        score = 0
        flags = []

        # P/E check
        pe_flag = "N/A"
        if pe:
            if pe < sector_pe * 0.8:
                score += 2; pe_flag = "CHEAP vs sector ✅"
            elif pe < sector_pe * 1.2:
                score += 1; pe_flag = "FAIR valued 🟡"
            else:
                score -= 1; pe_flag = "EXPENSIVE vs sector ❌"

        # ROE check
        roe_flag = "N/A"
        if roe:
            roe_pct = round(roe * 100, 1)
            if roe_pct > 20:
                score += 2; roe_flag = f"{roe_pct}% — Excellent ✅"
            elif roe_pct > 15:
                score += 1; roe_flag = f"{roe_pct}% — Good 🟡"
            elif roe_pct > 10:
                roe_flag = f"{roe_pct}% — Average 🟠"
            else:
                score -= 1; roe_flag = f"{roe_pct}% — Poor ❌"
        else:
            roe_pct = None

        # Debt check
        debt_flag = "N/A"
        if debt_eq is not None:
            if debt_eq < 30:
                score += 1; debt_flag = f"{debt_eq:.0f}% — Low debt ✅"
            elif debt_eq < 80:
                debt_flag = f"{debt_eq:.0f}% — Manageable 🟡"
            else:
                score -= 1; debt_flag = f"{debt_eq:.0f}% — High debt ❌"

        # Revenue growth
        rev_flag = "N/A"
        if rev_growth:
            rev_pct = round(rev_growth * 100, 1)
            if rev_pct > 15:
                score += 2; rev_flag = f"{rev_pct}% — Strong growth ✅"
            elif rev_pct > 8:
                score += 1; rev_flag = f"{rev_pct}% — Moderate growth 🟡"
            elif rev_pct > 0:
                rev_flag = f"{rev_pct}% — Slow growth 🟠"
            else:
                score -= 1; rev_flag = f"{rev_pct}% — Revenue declining ❌"
        else:
            rev_pct = None

        # FCF check
        fcf_flag = "N/A"
        if fcf:
            if fcf > 0:
                score += 1; fcf_flag = f"{_inr(fcf)} — Positive ✅"
            else:
                score -= 1; fcf_flag = f"{_inr(fcf)} — Negative ❌"

        # Analyst target
        upside = None
        if target_price and price:
            upside = round(((target_price - price) / price) * 100, 1)

        overall = (
            "STRONG BUY"  if score >= 6 else
            "BUY"         if score >= 4 else
            "HOLD"        if score >= 2 else
            "SELL"        if score >= 0 else
            "STRONG SELL"
        )

        return {
            "symbol":        sym,
            "name":          name,
            "price":         round(float(price), 2),
            "market_cap":    market_cap,
            "pe":            round(pe, 1) if pe else None,
            "fwd_pe":        round(fwd_pe, 1) if fwd_pe else None,
            "sector_pe":     sector_pe,
            "pe_flag":       pe_flag,
            "pb":            round(pb, 2) if pb else None,
            "roe":           roe_pct if roe else None,
            "roe_flag":      roe_flag,
            "debt_eq":       round(debt_eq, 1) if debt_eq is not None else None,
            "debt_flag":     debt_flag,
            "rev_growth":    rev_pct if rev_growth else None,
            "rev_flag":      rev_flag,
            "earn_growth":   round(earn_growth * 100, 1) if earn_growth else None,
            "profit_margin": round(profit_margin * 100, 1) if profit_margin else None,
            "fcf":           fcf,
            "fcf_flag":      fcf_flag,
            "beta":          round(beta, 2) if beta else None,
            "div_yield":     round(div_yield * 100, 2) if div_yield else None,
            "analyst_rec":   analyst_rec.upper() if analyst_rec else "—",
            "target_price":  round(target_price, 2) if target_price else None,
            "upside":        upside,
            "sector":        sector_key,
            "score":         score,
            "overall":       overall,
        }
    except Exception as e:
        log.warning(f"Fundamentals failed {symbol}: {e}")
        return None


def get_watchlist_fundamentals(watchlist: list) -> list:
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        r = get_fundamentals(sym)
        if r:
            results.append(r)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_fundamental_signals(fund_data: list) -> list:
    """Generate buy/sell/watch signals from fundamentals."""
    signals = []
    for r in fund_data:
        sym   = r["symbol"]
        score = r["score"]
        overall = r["overall"]

        if overall in ("STRONG BUY", "BUY"):
            sev = "HIGH" if overall == "STRONG BUY" else "MEDIUM"
            reasons = []
            if r.get("pe_flag","").startswith("CHEAP"):   reasons.append(f"P/E {r['pe']} vs sector avg {r['sector_pe']}")
            if r.get("roe_flag","").startswith(("20","19","18","17","16","15","Exc")): reasons.append(f"ROE {r['roe']}%")
            if r.get("rev_flag","").startswith(("15","16","17","18","19","20","25","Str")): reasons.append(f"Revenue +{r['rev_growth']}%")
            signals.append({
                "symbol": sym, "type": "FUNDAMENTAL_BUY",
                "severity": sev, "timeframe": "1M",
                "summary": f"📈 {overall} — {', '.join(reasons) if reasons else f'Score {score}/8'}",
                "data": r,
            })

        if overall in ("SELL", "STRONG SELL"):
            reasons = []
            if r.get("debt_flag","").startswith("High"):  reasons.append(f"High debt {r['debt_eq']}%")
            if r.get("rev_flag","").contains("declining"): reasons.append("Revenue declining")
            signals.append({
                "symbol": sym, "type": "FUNDAMENTAL_SELL",
                "severity": "HIGH", "timeframe": "1M",
                "summary": f"📉 Fundamental warning: {overall} — {', '.join(reasons) if reasons else f'Score {score}/8'}",
                "data": r,
            })

        # High upside from analyst target
        if r.get("upside") and r["upside"] > 20:
            signals.append({
                "symbol": sym, "type": "ANALYST_UPSIDE",
                "severity": "MEDIUM", "timeframe": "1M",
                "summary": f"🎯 Analyst target ₹{r['target_price']:,.0f} = {r['upside']:+.1f}% upside from current price",
                "data": r,
            })

    return signals


def _map_sector(yf_sector: str) -> str:
    s = (yf_sector or "").lower()
    if "technology" in s or "software" in s:   return "IT"
    if "bank" in s or "financial" in s:         return "Banking"
    if "consumer" in s or "food" in s:          return "FMCG"
    if "auto" in s or "vehicle" in s:           return "Auto"
    if "pharma" in s or "health" in s:          return "Pharma"
    if "real estate" in s or "realty" in s:     return "Realty"
    if "metal" in s or "mining" in s:           return "Metal"
    if "energy" in s or "oil" in s:             return "Energy"
    if "infra" in s or "construct" in s:        return "Infra"
    return "Default"


def _inr(val: float) -> str:
    if val is None: return "N/A"
    if abs(val) >= 1e7: return f"₹{val/1e7:.1f}Cr"
    if abs(val) >= 1e5: return f"₹{val/1e5:.1f}L"
    return f"₹{val:,.0f}"
