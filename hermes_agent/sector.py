"""
Hermes — Sector Rotation Tracker
Tracks which NSE sectors are gaining/losing money flow.
Uses NSE sector indices via yfinance.
"""

import logging
import yfinance as yf

log = logging.getLogger("hermes.sector")

# NSE Sector Indices — Yahoo Finance tickers
SECTORS = {
    "IT":          "^CNXIT",
    "Banking":     "^NSEBANK",
    "FMCG":        "^CNXFMCG",
    "Auto":        "^CNXAUTO",
    "Pharma":      "^CNXPHARMA",
    "Realty":      "^CNXREALTY",
    "Metal":       "^CNXMETAL",
    "Energy":      "^CNXENERGY",
    "Infra":       "^CNXINFRA",
    "Media":       "^CNXMEDIA",
}

# Which stocks belong to which sector (for "your stock is in hot sector" alerts)
SECTOR_STOCKS = {
    "IT":      ["INFY.NS","TCS.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS"],
    "Banking": ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","AXISBANK.NS","KOTAKBANK.NS"],
    "FMCG":    ["HINDUNILVR.NS","NESTLEIND.NS","BRITANNIA.NS","DABUR.NS","MARICO.NS"],
    "Auto":    ["MARUTI.NS","TATAMOTORS.NS","BAJAJ-AUTO.NS","HEROMOTOCO.NS","M&M.NS"],
    "Pharma":  ["SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","APOLLOHOSP.NS"],
    "Realty":  ["DLF.NS","GODREJPROP.NS","OBEROIRLTY.NS","PHOENIXLTD.NS"],
    "Metal":   ["TATASTEEL.NS","HINDALCO.NS","JSWSTEEL.NS","COALINDIA.NS","VEDL.NS"],
    "Energy":  ["RELIANCE.NS","ONGC.NS","BPCL.NS","IOC.NS","NTPC.NS"],
}


def get_sector_performance() -> list:
    """
    Returns performance of all NSE sector indices.
    Sorted best to worst by today's % change.
    """
    results = []
    for name, ticker in SECTORS.items():
        try:
            t  = yf.Ticker(ticker)
            fi = t.fast_info
            price = round(float(fi.last_price), 2)
            prev  = round(float(fi.previous_close), 2)
            chg   = round(price - prev, 2)
            pct   = round((chg / prev) * 100, 2) if prev else 0

            # 5-day trend
            hist = t.history(period="5d", interval="1d")
            week_pct = 0.0
            if len(hist) >= 2:
                week_pct = round(
                    ((float(hist["Close"].iloc[-1]) - float(hist["Close"].iloc[0]))
                     / float(hist["Close"].iloc[0])) * 100, 2)

            results.append({
                "sector":   name,
                "price":    price,
                "change":   chg,
                "pct":      pct,
                "week_pct": week_pct,
                "trend":    "UP" if week_pct > 0 else "DOWN",
            })
        except Exception as e:
            log.debug(f"Sector {name} failed: {e}")

    results.sort(key=lambda x: x["pct"], reverse=True)
    return results


def get_sector_for_stock(symbol: str) -> str | None:
    sym = symbol.replace(".NS", "").upper() + ".NS"
    for sector, stocks in SECTOR_STOCKS.items():
        if sym in stocks or symbol in stocks:
            return sector
    return None


def get_rotation_signals(sector_data: list, watchlist: list) -> list:
    """
    Detect rotation signals:
    - Sector outperforming for 3+ days = money flowing IN
    - Sector underperforming = money flowing OUT
    - Your stock's sector is hot/cold
    """
    signals = []

    # Top 2 sectors gaining, bottom 2 losing
    top    = [s for s in sector_data if s["pct"] > 1.0][:2]
    bottom = [s for s in sector_data if s["pct"] < -1.0][-2:]

    for s in top:
        signals.append({
            "sector":  s["sector"],
            "type":    "INFLOW",
            "pct":     s["pct"],
            "week_pct":s["week_pct"],
            "message": f"Money flowing INTO {s['sector']} sector today ({s['pct']:+.2f}%)",
        })

    for s in bottom:
        signals.append({
            "sector":  s["sector"],
            "type":    "OUTFLOW",
            "pct":     s["pct"],
            "week_pct":s["week_pct"],
            "message": f"Money flowing OUT of {s['sector']} sector today ({s['pct']:+.2f}%)",
        })

    # Check if user's watchlist stocks are in hot/cold sectors
    for sym in watchlist:
        sector = get_sector_for_stock(sym)
        if not sector:
            continue
        sec_data = next((s for s in sector_data if s["sector"] == sector), None)
        if not sec_data:
            continue
        sym_clean = sym.replace(".NS", "")
        if sec_data["pct"] > 1.5:
            signals.append({
                "sector":   sector,
                "symbol":   sym_clean,
                "type":     "STOCK_SECTOR_UP",
                "pct":      sec_data["pct"],
                "week_pct": sec_data["week_pct"],
                "message":  f"{sym_clean} is in {sector} sector which is rising {sec_data['pct']:+.2f}% today",
            })
        elif sec_data["pct"] < -1.5:
            signals.append({
                "sector":   sector,
                "symbol":   sym_clean,
                "type":     "STOCK_SECTOR_DOWN",
                "pct":      sec_data["pct"],
                "week_pct": sec_data["week_pct"],
                "message":  f"{sym_clean} is in {sector} sector which is falling {sec_data['pct']:+.2f}% today",
            })

    return signals