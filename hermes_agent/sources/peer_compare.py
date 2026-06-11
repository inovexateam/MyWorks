"""
Hermes — Peer Comparison
Compare your stock vs sector peers on P/E, ROE, growth, margins.
Tells you if you hold the best stock in its sector or a laggard.
"""

import logging
import yfinance as yf

log = logging.getLogger("hermes.peer_compare")

# Sector peer groups (NSE)
PEER_GROUPS = {
    "IT":       ["INFY.NS","TCS.NS","WIPRO.NS","HCLTECH.NS","TECHM.NS","LTIM.NS"],
    "BANKING":  ["HDFCBANK.NS","ICICIBANK.NS","SBIN.NS","AXISBANK.NS","KOTAKBANK.NS","INDUSINDBK.NS"],
    "FMCG":     ["HINDUNILVR.NS","NESTLEIND.NS","BRITANNIA.NS","DABUR.NS","MARICO.NS","GODREJCP.NS"],
    "AUTO":     ["MARUTI.NS","TATAMOTORS.NS","M&M.NS","BAJAJ-AUTO.NS","HEROMOTOCO.NS","EICHERMOT.NS"],
    "PHARMA":   ["SUNPHARMA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","TORNTPHARM.NS","AUROPHARMA.NS"],
    "REALTY":   ["DLF.NS","GODREJPROP.NS","OBEROIRLTY.NS","PRESTIGE.NS","PHOENIXLTD.NS"],
    "METAL":    ["TATASTEEL.NS","HINDALCO.NS","JSWSTEEL.NS","COALINDIA.NS","VEDL.NS","NMDC.NS"],
    "ENERGY":   ["RELIANCE.NS","ONGC.NS","BPCL.NS","IOC.NS","NTPC.NS","POWERGRID.NS"],
    "INFRA":    ["LT.NS","ADANIPORTS.NS","ULTRACEMCO.NS","GRASIM.NS","AMBUJACEM.NS"],
}

STOCK_TO_SECTOR = {}
for sector, stocks in PEER_GROUPS.items():
    for s in stocks:
        STOCK_TO_SECTOR[s.replace(".NS","")] = sector


def get_peer_comparison(symbol: str) -> dict | None:
    """
    Compare a stock against all its sector peers.
    Shows where it ranks on P/E, ROE, revenue growth.
    """
    sym     = symbol.replace(".NS","").upper()
    sector  = STOCK_TO_SECTOR.get(sym)
    if not sector:
        # Try to find sector from yfinance
        try:
            info   = yf.Ticker(symbol if ".NS" in symbol else symbol+".NS").info
            yf_sec = (info.get("sector","") or "").lower()
            if "tech" in yf_sec or "software" in yf_sec: sector = "IT"
            elif "bank" in yf_sec or "financial" in yf_sec: sector = "BANKING"
            elif "consumer" in yf_sec: sector = "FMCG"
            elif "auto" in yf_sec: sector = "AUTO"
            elif "pharma" in yf_sec or "health" in yf_sec: sector = "PHARMA"
        except Exception:
            pass
    if not sector:
        return None

    peers   = PEER_GROUPS.get(sector, [])
    records = []
    for peer in peers:
        try:
            info = yf.Ticker(peer).info
            pe   = info.get("trailingPE")
            roe  = info.get("returnOnEquity")
            rev  = info.get("revenueGrowth")
            margin = info.get("profitMargins")
            price  = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            mcap   = info.get("marketCap", 0)
            records.append({
                "symbol":  peer.replace(".NS",""),
                "price":   round(float(price), 2) if price else 0,
                "pe":      round(float(pe), 1)    if pe    else None,
                "roe":     round(float(roe)*100,1) if roe  else None,
                "rev_growth": round(float(rev)*100,1) if rev else None,
                "margin":  round(float(margin)*100,1)  if margin else None,
                "mcap":    mcap,
                "is_target": peer.replace(".NS","") == sym,
            })
        except Exception as e:
            log.debug(f"Peer fetch failed {peer}: {e}")

    if not records:
        return None

    # Rankings
    valid_pe  = [r for r in records if r["pe"]  is not None]
    valid_roe = [r for r in records if r["roe"] is not None]
    valid_rev = [r for r in records if r["rev_growth"] is not None]

    for r in records:
        r["pe_rank"]  = sorted(valid_pe,  key=lambda x: x["pe"]).index(r)+1  if r in valid_pe  else None
        r["roe_rank"] = sorted(valid_roe, key=lambda x: -x["roe"]).index(r)+1 if r in valid_roe else None
        r["rev_rank"] = sorted(valid_rev, key=lambda x: -x["rev_growth"] if x["rev_growth"] else 0).index(r)+1 if r in valid_rev else None

    target = next((r for r in records if r["is_target"]), None)

    # Sector averages
    avg_pe  = round(sum(r["pe"]  for r in valid_pe)  / len(valid_pe),  1) if valid_pe  else None
    avg_roe = round(sum(r["roe"] for r in valid_roe) / len(valid_roe), 1) if valid_roe else None

    return {
        "symbol":  sym,
        "sector":  sector,
        "peers":   sorted(records, key=lambda x: x.get("roe") or 0, reverse=True),
        "target":  target,
        "avg_pe":  avg_pe,
        "avg_roe": avg_roe,
        "n_peers": len(records),
    }
