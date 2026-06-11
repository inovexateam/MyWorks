"""
Hermes — VWAP + Intraday Price Levels
Real-time VWAP during market hours using 5-min candles.
VWAP = Volume Weighted Average Price — the institutional benchmark.
Price above VWAP = bullish. Below = bearish.
"""

import logging
import yfinance as yf
import pandas as pd
from datetime import date

log = logging.getLogger("hermes.vwap")


def get_vwap(symbol: str) -> dict | None:
    """
    Calculate today's VWAP from 5-min intraday data.
    Also returns: price vs VWAP, support/resistance from intraday highs/lows.
    """
    try:
        t  = yf.Ticker(symbol if symbol.endswith(".NS") else symbol + ".NS")
        df = t.history(period="1d", interval="5m")
        if df.empty or len(df) < 5:
            return None

        df.columns = [c.lower() for c in df.columns]
        # VWAP = sum(typical_price * volume) / sum(volume)
        df["typical"] = (df["high"] + df["low"] + df["close"]) / 3
        df["tp_vol"]  = df["typical"] * df["volume"]
        df["cum_vol"] = df["volume"].cumsum()
        df["cum_tpvol"] = df["tp_vol"].cumsum()
        df["vwap"]    = df["cum_tpvol"] / df["cum_vol"]

        price   = round(float(df["close"].iloc[-1]), 2)
        vwap    = round(float(df["vwap"].iloc[-1]),  2)
        diff    = round(price - vwap, 2)
        diff_pct= round((diff / vwap) * 100, 2) if vwap else 0

        # Intraday high/low = dynamic support/resistance
        intra_high = round(float(df["high"].max()),  2)
        intra_low  = round(float(df["low"].min()),   2)
        open_price = round(float(df["open"].iloc[0]),2)

        # VWAP bands (1 std dev above/below)
        std  = float(df["typical"].rolling(len(df)).std().iloc[-1])
        band_upper = round(vwap + std, 2)
        band_lower = round(vwap - std, 2)

        position = (
            "STRONG ABOVE" if diff_pct >  1.0 else
            "ABOVE"        if diff_pct >  0.2 else
            "AT VWAP"      if abs(diff_pct) <= 0.2 else
            "BELOW"        if diff_pct > -1.0 else
            "STRONG BELOW"
        )

        signal = (
            "BUY ZONE"  if position in ("ABOVE","STRONG ABOVE") else
            "SELL ZONE" if position in ("BELOW","STRONG BELOW") else
            "NEUTRAL"
        )

        return {
            "symbol":      symbol.replace(".NS",""),
            "price":       price,
            "vwap":        vwap,
            "diff":        diff,
            "diff_pct":    diff_pct,
            "position":    position,
            "signal":      signal,
            "band_upper":  band_upper,
            "band_lower":  band_lower,
            "intra_high":  intra_high,
            "intra_low":   intra_low,
            "open_price":  open_price,
            "candles":     len(df),
        }
    except Exception as e:
        log.warning(f"VWAP failed {symbol}: {e}")
        return None


def get_watchlist_vwap(watchlist: list) -> list:
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            sym = "^NSEI"
        r = get_vwap(sym)
        if r:
            results.append(r)
    results.sort(key=lambda x: x["diff_pct"], reverse=True)
    return results
