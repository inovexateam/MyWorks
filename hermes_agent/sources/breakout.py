"""
Hermes — Breakout & Accumulation Scanner
Detects: 52W high breakouts, volume accumulation, price consolidation,
relative strength vs Nifty, delivery % rising trend.
"""

import logging
import yfinance as yf
import pandas as pd

log = logging.getLogger("hermes.breakout")

NIFTY_TICKER = "^NSEI"


def _history(symbol: str, period: str = "6mo") -> pd.DataFrame | None:
    try:
        df = yf.Ticker(symbol).history(period=period, interval="1d")
        if df.empty or len(df) < 20:
            return None
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        log.debug(f"History failed {symbol}: {e}")
        return None


def scan_breakouts(watchlist: list) -> list:
    """
    Scan for stocks breaking out of 52W highs on high volume.
    This is the single most powerful buy signal in trending markets.
    """
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        try:
            df = _history(sym, "1y")
            if df is None:
                continue

            close  = df["close"]
            volume = df["volume"]
            price  = float(close.iloc[-1])
            high52 = float(close.rolling(252).max().iloc[-1])
            avg_vol = float(volume.rolling(20).mean().iloc[-1])
            curr_vol = float(volume.iloc[-1])
            vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1

            # Breakout: price within 1% of 52W high
            near_high = price >= high52 * 0.99
            # Volume confirmation: volume > 1.5x average on breakout
            vol_confirm = vol_ratio >= 1.5

            if near_high:
                results.append({
                    "symbol":     sym.replace(".NS",""),
                    "price":      round(price, 2),
                    "high52":     round(high52, 2),
                    "vol_ratio":  vol_ratio,
                    "confirmed":  vol_confirm,
                    "type":       "BREAKOUT",
                    "severity":   "HIGH" if vol_confirm else "MEDIUM",
                    "meaning":    f"Price at 52W high {'with strong volume ✅' if vol_confirm else '— low volume, unconfirmed ⚠️'}",
                })
        except Exception as e:
            log.debug(f"Breakout scan failed {sym}: {e}")

    return sorted(results, key=lambda x: (x["confirmed"], x["vol_ratio"]), reverse=True)


def scan_accumulation(watchlist: list, days: int = 5) -> list:
    """
    Detect quiet accumulation: volume building up without price moving.
    Classic operator/institution signature.
    """
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        try:
            df = _history(sym, "3mo")
            if df is None or len(df) < days + 10:
                continue

            close    = df["close"]
            volume   = df["volume"]
            recent   = df.tail(days)

            avg_vol_20  = float(volume.iloc[:-days].rolling(20).mean().iloc[-1])
            recent_vol  = float(recent["volume"].mean())
            vol_ratio   = round(recent_vol / avg_vol_20, 2) if avg_vol_20 > 0 else 1

            # Price range over last N days (tight range = consolidation)
            price_range_pct = round(
                (float(recent["high"].max()) - float(recent["low"].min()))
                / float(recent["close"].mean()) * 100, 2)

            # Accumulation: high volume + tight price range
            accumulating = vol_ratio >= 1.5 and price_range_pct < 3.0

            if accumulating:
                results.append({
                    "symbol":          sym.replace(".NS",""),
                    "price":           round(float(close.iloc[-1]), 2),
                    "vol_ratio":       vol_ratio,
                    "price_range_pct": price_range_pct,
                    "type":            "ACCUMULATION",
                    "severity":        "HIGH" if vol_ratio >= 2 else "MEDIUM",
                    "meaning":         f"High volume ({vol_ratio:.1f}x avg) in tight {price_range_pct:.1f}% range — someone is quietly buying",
                })
        except Exception as e:
            log.debug(f"Accumulation scan failed {sym}: {e}")

    return sorted(results, key=lambda x: x["vol_ratio"], reverse=True)


def scan_consolidation(watchlist: list) -> list:
    """
    Detect price coiling: narrow range for 5+ days = spring loading for big move.
    """
    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        try:
            df = _history(sym, "3mo")
            if df is None or len(df) < 15:
                continue

            recent5  = df.tail(5)
            recent20 = df.tail(20)

            range5   = float(recent5["high"].max()  - recent5["low"].min())
            range20  = float(recent20["high"].max() - recent20["low"].min())
            squeeze  = round(range5 / range20, 3) if range20 > 0 else 1

            # Squeeze: recent 5-day range < 25% of 20-day range
            if squeeze < 0.25:
                price = float(df["close"].iloc[-1])
                results.append({
                    "symbol":   sym.replace(".NS",""),
                    "price":    round(price, 2),
                    "squeeze":  squeeze,
                    "type":     "CONSOLIDATION",
                    "severity": "MEDIUM",
                    "meaning":  f"Price coiling tight (5d range = {squeeze*100:.0f}% of 20d range) — big move coming",
                })
        except Exception as e:
            log.debug(f"Consolidation scan failed {sym}: {e}")

    return sorted(results, key=lambda x: x["squeeze"])


def get_relative_strength(watchlist: list, period: str = "3mo") -> list:
    """
    Relative Strength vs Nifty.
    RS > 100 = outperforming Nifty = strong stock.
    RS < 100 = underperforming = weak.
    """
    try:
        nifty_df = yf.Ticker(NIFTY_TICKER).history(period=period, interval="1d")
        if nifty_df.empty:
            return []
        nifty_ret = float(nifty_df["Close"].iloc[-1]) / float(nifty_df["Close"].iloc[0]) - 1
    except Exception:
        return []

    results = []
    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        try:
            df = yf.Ticker(sym).history(period=period, interval="1d")
            if df.empty:
                continue
            stock_ret = float(df["Close"].iloc[-1]) / float(df["Close"].iloc[0]) - 1
            rs = round((1 + stock_ret) / (1 + nifty_ret) * 100, 2)
            results.append({
                "symbol":     sym.replace(".NS",""),
                "price":      round(float(df["Close"].iloc[-1]), 2),
                "stock_ret":  round(stock_ret * 100, 2),
                "nifty_ret":  round(nifty_ret * 100, 2),
                "rs":         rs,
                "outperform": rs > 100,
            })
        except Exception as e:
            log.debug(f"RS failed {sym}: {e}")

    return sorted(results, key=lambda x: x["rs"], reverse=True)


def full_breakout_scan(watchlist: list) -> dict:
    return {
        "breakouts":     scan_breakouts(watchlist),
        "accumulation":  scan_accumulation(watchlist),
        "consolidation": scan_consolidation(watchlist),
        "rel_strength":  get_relative_strength(watchlist),
    }
