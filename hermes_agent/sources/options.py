"""
Hermes — Unusual Options Activity
Detects large OI buildup, IV spikes, unusual call/put buying.
Smart money leaves footprints in options — this finds them.
"""

import logging
import requests

log = logging.getLogger("hermes.options")

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer":    "https://www.nseindia.com/",
    "Accept":     "application/json",
}


def _session():
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass
    return s


def _get_chain(symbol: str, is_index: bool = False) -> dict | None:
    try:
        session = _session()
        if is_index:
            url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        else:
            url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
        r = session.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.debug(f"Options chain failed {symbol}: {e}")
    return None


def analyze_options(symbol: str) -> dict | None:
    """
    Full options analysis for one symbol.
    Returns: PCR, max pain, top OI strikes, IV, unusual activity flags.
    """
    sym = symbol.replace(".NS", "").upper()
    is_index = sym in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")
    data = _get_chain(sym, is_index)
    if not data:
        return None

    try:
        records  = data.get("records", {})
        exp_dates = records.get("expiryDates", [])
        if not exp_dates:
            return None

        nearest  = exp_dates[0]
        chain    = records.get("data", [])
        spot     = float(records.get("underlyingValue", 0))

        strikes  = {}
        total_ce_oi = total_pe_oi = 0
        total_ce_vol = total_pe_vol = 0

        for row in chain:
            if row.get("expiryDate") != nearest:
                continue
            k   = row.get("strikePrice", 0)
            ce  = row.get("CE", {})
            pe  = row.get("PE", {})

            ce_oi  = ce.get("openInterest",        0)
            pe_oi  = pe.get("openInterest",        0)
            ce_vol = ce.get("totalTradedVolume",   0)
            pe_vol = pe.get("totalTradedVolume",   0)
            ce_iv  = ce.get("impliedVolatility",   0)
            pe_iv  = pe.get("impliedVolatility",   0)
            ce_chg = ce.get("changeinOpenInterest",0)
            pe_chg = pe.get("changeinOpenInterest",0)

            strikes[k] = {
                "ce_oi":  ce_oi,  "pe_oi":  pe_oi,
                "ce_vol": ce_vol, "pe_vol": pe_vol,
                "ce_iv":  ce_iv,  "pe_iv":  pe_iv,
                "ce_chg": ce_chg, "pe_chg": pe_chg,
            }
            total_ce_oi  += ce_oi;  total_pe_oi  += pe_oi
            total_ce_vol += ce_vol; total_pe_vol += pe_vol

        if not strikes:
            return None

        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 1.0

        # Max pain
        max_pain = max(strikes, key=lambda k: strikes[k]["ce_oi"] + strikes[k]["pe_oi"])

        # Top resistance (highest call OI above spot)
        above = {k: v for k, v in strikes.items() if k > spot}
        resistance = max(above, key=lambda k: above[k]["ce_oi"]) if above else None

        # Top support (highest put OI below spot)
        below = {k: v for k, v in strikes.items() if k < spot}
        support = max(below, key=lambda k: below[k]["pe_oi"]) if below else None

        # Unusual activity: OI change > 50% of existing OI at a strike
        unusual = []
        avg_ce_oi = total_ce_oi / len(strikes) if strikes else 1
        avg_pe_oi = total_pe_oi / len(strikes) if strikes else 1

        for k, v in strikes.items():
            # Large fresh call buying (bullish bet)
            if v["ce_chg"] > avg_ce_oi * 2 and v["ce_chg"] > 0:
                unusual.append({
                    "strike":    k,
                    "type":      "CALL_BUILDUP",
                    "oi_change": v["ce_chg"],
                    "iv":        v["ce_iv"],
                    "meaning":   f"Big bet that {sym} will cross ₹{k:,} before {nearest}",
                })
            # Large fresh put buying (bearish bet)
            if v["pe_chg"] > avg_pe_oi * 2 and v["pe_chg"] > 0:
                unusual.append({
                    "strike":    k,
                    "type":      "PUT_BUILDUP",
                    "oi_change": v["pe_chg"],
                    "iv":        v["pe_iv"],
                    "meaning":   f"Big bet that {sym} will fall below ₹{k:,} before {nearest}",
                })

        # IV spike detection (IV > 40% is elevated for most stocks)
        near_strikes = {k: v for k, v in strikes.items()
                       if abs(k - spot) / spot < 0.05}
        avg_iv = 0.0
        if near_strikes:
            ivs = [v["ce_iv"] for v in near_strikes.values() if v["ce_iv"] > 0]
            avg_iv = round(sum(ivs) / len(ivs), 2) if ivs else 0.0

        iv_spike = avg_iv > 40

        sentiment = (
            "BULLISH"  if pcr > 1.2 else
            "BEARISH"  if pcr < 0.8 else
            "NEUTRAL"
        )

        return {
            "symbol":      sym,
            "spot":        spot,
            "expiry":      nearest,
            "pcr":         pcr,
            "sentiment":   sentiment,
            "max_pain":    max_pain,
            "resistance":  resistance,
            "support":     support,
            "avg_iv":      avg_iv,
            "iv_spike":    iv_spike,
            "unusual":     sorted(unusual, key=lambda x: x["oi_change"], reverse=True)[:3],
            "total_ce_oi": total_ce_oi,
            "total_pe_oi": total_pe_oi,
        }
    except Exception as e:
        log.warning(f"Options analysis failed {sym}: {e}")
        return None


def scan_unusual_activity(watchlist: list) -> list:
    """Scan all watchlist stocks for unusual options activity."""
    results = []
    # Always include Nifty and BankNifty
    symbols = ["NIFTY", "BANKNIFTY"] + [
        s.replace(".NS", "") for s in watchlist
        if s not in ("NIFTY50", "BANKNIFTY")
    ]
    for sym in symbols:
        try:
            r = analyze_options(sym)
            if r:
                results.append(r)
        except Exception as e:
            log.debug(f"Options scan skipped {sym}: {e}")
    return results
