"""
Hermes — Technical Analysis
RSI, MACD, MA crossovers, Bollinger Bands, Volume spikes, Support/Resistance.
Uses yfinance for history + pandas_ta for indicators.
"""

import logging
import pandas as pd
try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False
    logging.warning("pandas_ta not installed. Run: pip install pandas-ta")

import yfinance as yf

log = logging.getLogger("hermes.technicals")

PERIOD   = "6mo"   # 6 months of daily data
INTERVAL = "1d"


def _history(symbol: str) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(symbol).history(period=PERIOD, interval=INTERVAL)
        if df.empty or len(df) < 30:
            return None
        df.columns = [c.lower() for c in df.columns]
        return df.copy()
    except Exception as e:
        log.warning(f"History fetch failed {symbol}: {e}")
        return None


def _fallback_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs  = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def analyze(symbol: str) -> dict | None:
    """
    Full technical snapshot for a symbol.
    Returns dict with all indicators and signals.
    """
    df = _history(symbol)
    if df is None:
        return None

    close  = df["close"]
    volume = df["volume"]
    high   = df["high"]
    low    = df["low"]

    result = {"symbol": symbol, "price": round(float(close.iloc[-1]), 2)}

    # ── RSI ──────────────────────────────────────────────────────────────────
    try:
        if HAS_TA:
            rsi_s = ta.rsi(close, length=14)
        else:
            rsi_s = _fallback_rsi(close, 14)
        rsi = round(float(rsi_s.iloc[-1]), 2)
        result["rsi"] = rsi
        result["rsi_signal"] = (
            "OVERSOLD"   if rsi < 30 else
            "OVERBOUGHT" if rsi > 70 else
            "NEUTRAL"
        )
    except Exception as e:
        log.debug(f"RSI failed {symbol}: {e}")
        result["rsi"] = None
        result["rsi_signal"] = "N/A"

    # ── Moving Averages ───────────────────────────────────────────────────────
    try:
        ma50  = round(float(close.rolling(50).mean().iloc[-1]),  2)
        ma200 = round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None
        price = result["price"]
        result["ma50"]  = ma50
        result["ma200"] = ma200
        result["above_ma50"]  = price > ma50
        result["above_ma200"] = price > ma200 if ma200 else None

        # Golden / Death cross
        if ma200:
            ma50_prev  = round(float(close.rolling(50).mean().iloc[-2]),  2)
            ma200_prev = round(float(close.rolling(200).mean().iloc[-2]), 2)
            if ma50_prev <= ma200_prev and ma50 > ma200:
                result["ma_cross"] = "GOLDEN"   # bullish
            elif ma50_prev >= ma200_prev and ma50 < ma200:
                result["ma_cross"] = "DEATH"    # bearish
            else:
                result["ma_cross"] = "NONE"
        else:
            result["ma_cross"] = "N/A"
    except Exception as e:
        log.debug(f"MA failed {symbol}: {e}")
        result["ma50"] = result["ma200"] = None
        result["ma_cross"] = "N/A"

    # ── MACD ─────────────────────────────────────────────────────────────────
    try:
        if HAS_TA:
            macd_df = ta.macd(close, fast=12, slow=26, signal=9)
            macd_col = [c for c in macd_df.columns if c.startswith("MACD_")
                        and "s" not in c.lower() and "h" not in c.lower()]
            sig_col  = [c for c in macd_df.columns if "MACDs" in c]
            hist_col = [c for c in macd_df.columns if "MACDh" in c]
            macd_val  = round(float(macd_df[macd_col[0]].iloc[-1]),  4) if macd_col  else None
            macd_sig  = round(float(macd_df[sig_col[0]].iloc[-1]),   4) if sig_col   else None
            macd_hist = round(float(macd_df[hist_col[0]].iloc[-1]),  4) if hist_col  else None
        else:
            ema12     = close.ewm(span=12).mean()
            ema26     = close.ewm(span=26).mean()
            macd_line = ema12 - ema26
            signal_ln = macd_line.ewm(span=9).mean()
            macd_val  = round(float(macd_line.iloc[-1]),             4)
            macd_sig  = round(float(signal_ln.iloc[-1]),             4)
            macd_hist = round(float((macd_line - signal_ln).iloc[-1]),4)

        result["macd"]      = macd_val
        result["macd_signal"] = macd_sig
        result["macd_hist"] = macd_hist

        # Crossover signal
        if macd_val is not None and macd_sig is not None:
            if HAS_TA:
                prev_macd = float(macd_df[macd_col[0]].iloc[-2]) if macd_col else 0
                prev_sig  = float(macd_df[sig_col[0]].iloc[-2])  if sig_col  else 0
            else:
                ema12_p    = close.ewm(span=12).mean()
                ema26_p    = close.ewm(span=26).mean()
                macd_p     = ema12_p - ema26_p
                sig_p      = macd_p.ewm(span=9).mean()
                prev_macd  = float(macd_p.iloc[-2])
                prev_sig   = float(sig_p.iloc[-2])

            if prev_macd <= prev_sig and macd_val > macd_sig:
                result["macd_cross"] = "BULLISH"
            elif prev_macd >= prev_sig and macd_val < macd_sig:
                result["macd_cross"] = "BEARISH"
            else:
                result["macd_cross"] = "NONE"
        else:
            result["macd_cross"] = "N/A"
    except Exception as e:
        log.debug(f"MACD failed {symbol}: {e}")
        result["macd"] = result["macd_signal"] = result["macd_hist"] = None
        result["macd_cross"] = "N/A"

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    try:
        if HAS_TA:
            bb = ta.bbands(close, length=20, std=2)
            bb_cols = bb.columns.tolist()
            bbl = float(bb[[c for c in bb_cols if "BBL" in c][0]].iloc[-1])
            bbm = float(bb[[c for c in bb_cols if "BBM" in c][0]].iloc[-1])
            bbh = float(bb[[c for c in bb_cols if "BBU" in c][0]].iloc[-1])
        else:
            bbm = close.rolling(20).mean()
            std = close.rolling(20).std()
            bbl = float((bbm - 2*std).iloc[-1])
            bbh = float((bbm + 2*std).iloc[-1])
            bbm = float(bbm.iloc[-1])

        price = result["price"]
        bbl   = round(bbl, 2)
        bbm   = round(bbm, 2)
        bbh   = round(bbh, 2)
        bw    = round((bbh - bbl) / bbm * 100, 2)   # bandwidth %

        result["bb_lower"] = bbl
        result["bb_mid"]   = bbm
        result["bb_upper"] = bbh
        result["bb_width"] = bw
        result["bb_signal"] = (
            "SQUEEZE"      if bw < 5 else   # low vol = big move coming
            "NEAR_LOWER"   if price <= bbl * 1.01 else
            "NEAR_UPPER"   if price >= bbh * 0.99 else
            "INSIDE"
        )
    except Exception as e:
        log.debug(f"BB failed {symbol}: {e}")
        result["bb_signal"] = "N/A"

    # ── Volume Analysis ───────────────────────────────────────────────────────
    try:
        avg_vol  = float(volume.rolling(20).mean().iloc[-1])
        curr_vol = float(volume.iloc[-1])
        vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0
        result["volume"]      = int(curr_vol)
        result["avg_volume"]  = int(avg_vol)
        result["volume_ratio"] = vol_ratio
        result["volume_signal"] = (
            "SPIKE"  if vol_ratio >= 2.0 else
            "HIGH"   if vol_ratio >= 1.5 else
            "NORMAL" if vol_ratio >= 0.7 else
            "LOW"
        )
    except Exception as e:
        log.debug(f"Volume failed {symbol}: {e}")
        result["volume_signal"] = "N/A"

    # ── Support & Resistance ──────────────────────────────────────────────────
    try:
        # Use recent 90-day pivots
        recent  = df.tail(90)
        pivots  = []
        prices  = recent["close"].values
        for i in range(2, len(prices) - 2):
            if prices[i] == max(prices[i-2:i+3]):
                pivots.append(("R", round(float(prices[i]), 2)))
            elif prices[i] == min(prices[i-2:i+3]):
                pivots.append(("S", round(float(prices[i]), 2)))

        price = result["price"]
        supports    = sorted([p for t, p in pivots if t == "S" and p < price], reverse=True)
        resistances = sorted([p for t, p in pivots if t == "R" and p > price])
        result["support"]    = supports[0]    if supports    else None
        result["resistance"] = resistances[0] if resistances else None
    except Exception as e:
        log.debug(f"S/R failed {symbol}: {e}")
        result["support"] = result["resistance"] = None

    # ── Supertrend ────────────────────────────────────────────────────────────
    try:
        if HAS_TA:
            st = ta.supertrend(high, low, close, length=10, multiplier=3)
            st_col = [c for c in st.columns if "SUPERTd" in c]
            if st_col:
                st_dir = int(st[st_col[0]].iloc[-1])  # 1=bullish, -1=bearish
                st_val_col = [c for c in st.columns if c.startswith("SUPERT_") and "d" not in c and "l" not in c and "s" not in c]
                st_price = round(float(st[st_val_col[0]].iloc[-1]), 2) if st_val_col else None
                result["supertrend"]       = st_price
                result["supertrend_dir"]   = "UP" if st_dir == 1 else "DOWN"
                result["supertrend_signal"]= "BUY" if st_dir == 1 else "SELL"
            else:
                result["supertrend_dir"] = "N/A"; result["supertrend_signal"] = "N/A"
        else:
            result["supertrend_dir"] = "N/A"; result["supertrend_signal"] = "N/A"
    except Exception as e:
        log.debug(f"Supertrend failed {symbol}: {e}")
        result["supertrend_dir"] = "N/A"; result["supertrend_signal"] = "N/A"

    # ── ADX — Trend Strength ──────────────────────────────────────────────────
    try:
        if HAS_TA:
            adx_df  = ta.adx(high, low, close, length=14)
            adx_col = [c for c in adx_df.columns if c.startswith("ADX_")]
            adx_val = round(float(adx_df[adx_col[0]].iloc[-1]), 2) if adx_col else None
        else:
            # Manual ADX fallback
            adx_val = None
        result["adx"] = adx_val
        result["adx_strength"] = (
            "STRONG"  if adx_val and adx_val > 25 else
            "WEAK"    if adx_val and adx_val < 20 else
            "MODERATE" if adx_val else "N/A"
        )
        result["adx_tradeable"] = adx_val and adx_val > 25
    except Exception as e:
        log.debug(f"ADX failed {symbol}: {e}")
        result["adx"] = None; result["adx_strength"] = "N/A"

    # ── Stochastic RSI ────────────────────────────────────────────────────────
    try:
        if HAS_TA:
            stoch_df = ta.stochrsi(close, length=14, rsi_length=14, k=3, d=3)
            k_col = [c for c in stoch_df.columns if "STOCHRSIk" in c]
            d_col = [c for c in stoch_df.columns if "STOCHRSId" in c]
            stoch_k = round(float(stoch_df[k_col[0]].iloc[-1]), 2) if k_col else None
            stoch_d = round(float(stoch_df[d_col[0]].iloc[-1]), 2) if d_col else None
            result["stoch_k"] = stoch_k
            result["stoch_d"] = stoch_d
            result["stoch_signal"] = (
                "OVERSOLD"   if stoch_k and stoch_k < 20 else
                "OVERBOUGHT" if stoch_k and stoch_k > 80 else
                "NEUTRAL"
            )
        else:
            result["stoch_k"] = None; result["stoch_signal"] = "N/A"
    except Exception as e:
        log.debug(f"StochRSI failed {symbol}: {e}")
        result["stoch_k"] = None; result["stoch_signal"] = "N/A"

    # ── OBV — On Balance Volume ───────────────────────────────────────────────
    try:
        if HAS_TA:
            obv_s = ta.obv(close, volume)
        else:
            obv_s = (close.diff().apply(lambda x: 1 if x > 0 else -1) * volume).cumsum()
        obv_now  = float(obv_s.iloc[-1])
        obv_prev = float(obv_s.iloc[-5])   # 5-day comparison
        obv_trend = "RISING" if obv_now > obv_prev else "FALLING"
        # Rising OBV + flat price = accumulation
        price_change_5d = abs(float(close.iloc[-1]) - float(close.iloc[-5])) / float(close.iloc[-5]) * 100
        result["obv_trend"]        = obv_trend
        result["obv_accumulating"] = obv_trend == "RISING" and price_change_5d < 2.0
    except Exception as e:
        log.debug(f"OBV failed {symbol}: {e}")
        result["obv_trend"] = "N/A"; result["obv_accumulating"] = False

    # ── Pivot Points ──────────────────────────────────────────────────────────
    try:
        # Previous day OHLC
        prev_h = float(high.iloc[-2]); prev_l = float(low.iloc[-2]); prev_c = float(close.iloc[-2])
        pp = round((prev_h + prev_l + prev_c) / 3, 2)
        result["pivot"] = pp
        result["pivot_r1"] = round(2*pp - prev_l, 2)
        result["pivot_r2"] = round(pp + (prev_h - prev_l), 2)
        result["pivot_s1"] = round(2*pp - prev_h, 2)
        result["pivot_s2"] = round(pp - (prev_h - prev_l), 2)
        cur = float(close.iloc[-1])
        result["pivot_position"] = "ABOVE" if cur > pp else "BELOW"
    except Exception as e:
        log.debug(f"Pivot failed {symbol}: {e}")
        result["pivot"] = None

    # ── Candlestick Patterns ──────────────────────────────────────────────────
    try:
        o = float(df["open"].iloc[-1])
        h2= float(high.iloc[-1])
        l2= float(low.iloc[-1])
        c2= float(close.iloc[-1])
        body   = abs(c2 - o)
        candle_range = h2 - l2
        upper_wick = h2 - max(o, c2)
        lower_wick = min(o, c2) - l2

        patterns = []
        if candle_range > 0:
            if body / candle_range < 0.1:
                patterns.append("DOJI")          # indecision
            if lower_wick > 2*body and upper_wick < body:
                patterns.append("HAMMER")         # bullish reversal
            if upper_wick > 2*body and lower_wick < body:
                patterns.append("SHOOTING STAR")  # bearish reversal

        # Engulfing (needs previous candle)
        if len(df) >= 2:
            po = float(df["open"].iloc[-2]); pc = float(df["close"].iloc[-2])
            if c2 > o and pc < po and c2 > po and o < pc:
                patterns.append("BULLISH ENGULFING")
            elif c2 < o and pc > po and c2 < po and o > pc:
                patterns.append("BEARISH ENGULFING")

        result["candlestick_patterns"] = patterns
        result["candlestick_signal"]   = (
            "BULLISH" if any(p in patterns for p in ["HAMMER","BULLISH ENGULFING"]) else
            "BEARISH" if any(p in patterns for p in ["SHOOTING STAR","BEARISH ENGULFING"]) else
            "NEUTRAL"
        )
    except Exception as e:
        log.debug(f"Candle failed {symbol}: {e}")
        result["candlestick_patterns"] = []; result["candlestick_signal"] = "NEUTRAL"

    # ── Price Action (HH/HL/LH/LL) ───────────────────────────────────────────
    try:
        highs  = high.rolling(5).max()
        lows   = low.rolling(5).min()
        hh = float(highs.iloc[-1]) > float(highs.iloc[-6])   # higher high
        hl = float(lows.iloc[-1])  > float(lows.iloc[-6])    # higher low
        lh = float(highs.iloc[-1]) < float(highs.iloc[-6])   # lower high
        ll = float(lows.iloc[-1])  < float(lows.iloc[-6])    # lower low
        if hh and hl:   pa = "UPTREND"
        elif lh and ll: pa = "DOWNTREND"
        elif hh and ll: pa = "VOLATILE"
        else:           pa = "SIDEWAYS"
        result["price_action"] = pa
    except Exception as e:
        log.debug(f"Price action failed {symbol}: {e}")
        result["price_action"] = "N/A"

    # ── Overall TA Signal ─────────────────────────────────────────────────────
    bullish = 0
    bearish = 0
    if result.get("rsi_signal")        == "OVERSOLD":       bullish += 1
    if result.get("rsi_signal")        == "OVERBOUGHT":     bearish += 1
    if result.get("above_ma50"):                            bullish += 1
    if result.get("above_ma50")        == False:            bearish += 1
    if result.get("above_ma200"):                           bullish += 1
    if result.get("above_ma200")       == False:            bearish += 1
    if result.get("macd_cross")        == "BULLISH":        bullish += 2
    if result.get("macd_cross")        == "BEARISH":        bearish += 2
    if result.get("ma_cross")          == "GOLDEN":         bullish += 2
    if result.get("ma_cross")          == "DEATH":          bearish += 2
    if result.get("volume_signal")    in ("SPIKE","HIGH"):  bullish += 1
    if result.get("bb_signal")         == "NEAR_LOWER":     bullish += 1
    if result.get("bb_signal")         == "NEAR_UPPER":     bearish += 1
    if result.get("supertrend_signal") == "BUY":            bullish += 2
    if result.get("supertrend_signal") == "SELL":           bearish += 2
    if result.get("stoch_signal")      == "OVERSOLD":       bullish += 1
    if result.get("stoch_signal")      == "OVERBOUGHT":     bearish += 1
    if result.get("obv_accumulating"):                      bullish += 1
    if result.get("candlestick_signal")== "BULLISH":        bullish += 1
    if result.get("candlestick_signal")== "BEARISH":        bearish += 1
    if result.get("price_action")      == "UPTREND":        bullish += 1
    if result.get("price_action")      == "DOWNTREND":      bearish += 1
    # ADX gates: only count trend signals if trend is strong
    if not result.get("adx_tradeable", True):
        bullish = max(0, bullish - 1); bearish = max(0, bearish - 1)

    score = bullish - bearish
    result["ta_score"]  = score
    result["ta_signal"] = (
        "STRONG BUY"  if score >= 4 else
        "BUY"         if score >= 2 else
        "SELL"        if score <= -2 else
        "STRONG SELL" if score <= -4 else
        "NEUTRAL"
    )

    return result


def analyze_watchlist(watchlist: list) -> list:
    """Run analyze() for all symbols. Returns list sorted by ta_score desc."""
    results = []
    for sym in watchlist:
        try:
            r = analyze(sym)
            if r:
                results.append(r)
        except Exception as e:
            log.warning(f"TA skipped {sym}: {e}")
    results.sort(key=lambda x: x.get("ta_score", 0), reverse=True)
    return results
