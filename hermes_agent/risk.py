"""
Hermes — Risk Management Engine
ATR stop-loss, position sizing, trailing stops, risk/reward, pre-trade checklist.
"""

import logging
import pandas as pd
import yfinance as yf
from datetime import date

log = logging.getLogger("hermes.risk")

# ── Config defaults (override in config.py if needed) ────────────────────────
MAX_POSITION_PCT   = 20.0   # max single stock as % of portfolio
MIN_RISK_REWARD    = 2.0    # minimum R:R ratio to consider a trade
ATR_PERIOD         = 14
ATR_STOP_MULTIPLIER = 2.0   # stop = entry - (ATR * multiplier)


# ── ATR Calculation ───────────────────────────────────────────────────────────

def _atr(symbol: str, period: int = ATR_PERIOD) -> float | None:
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="1d")
        if df.empty or len(df) < period + 1:
            return None
        df.columns = [c.lower() for c in df.columns]
        high  = df["high"]
        low   = df["low"]
        close = df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = round(float(tr.ewm(span=period, adjust=False).mean().iloc[-1]), 2)
        return atr
    except Exception as e:
        log.warning(f"ATR failed {symbol}: {e}")
        return None


# ── Stop Loss ─────────────────────────────────────────────────────────────────

def get_stop_loss(symbol: str, entry_price: float,
                  multiplier: float = ATR_STOP_MULTIPLIER) -> dict:
    """
    ATR-based stop-loss. More robust than arbitrary %.
    stop = entry - (ATR * multiplier)
    """
    atr = _atr(symbol)
    if atr is None:
        # fallback: 5% stop
        stop = round(entry_price * 0.95, 2)
        return {"symbol": symbol, "entry": entry_price, "stop": stop,
                "atr": None, "risk_per_share": round(entry_price - stop, 2),
                "risk_pct": 5.0, "method": "FALLBACK_5PCT"}

    stop         = round(entry_price - (atr * multiplier), 2)
    risk_per_sh  = round(entry_price - stop, 2)
    risk_pct     = round((risk_per_sh / entry_price) * 100, 2)

    return {
        "symbol":        symbol,
        "entry":         entry_price,
        "atr":           atr,
        "stop":          stop,
        "risk_per_share":risk_per_sh,
        "risk_pct":      risk_pct,
        "method":        "ATR",
    }


# ── Position Sizing ───────────────────────────────────────────────────────────

def get_position_size(
    symbol: str,
    entry_price: float,
    portfolio_value: float,
    risk_per_trade_pct: float = 1.0,    # risk 1% of portfolio per trade
    max_position_pct: float   = MAX_POSITION_PCT,
) -> dict:
    """
    Risk-based position sizing.
    Qty = (portfolio * risk%) / risk_per_share
    Capped at max_position_pct of portfolio.
    """
    sl = get_stop_loss(symbol, entry_price)
    risk_per_sh   = sl["risk_per_share"]
    if risk_per_sh <= 0:
        risk_per_sh = entry_price * 0.05

    risk_amount   = portfolio_value * (risk_per_trade_pct / 100)
    ideal_qty     = int(risk_amount / risk_per_sh)
    ideal_value   = ideal_qty * entry_price

    # Cap at max position size
    max_value     = portfolio_value * (max_position_pct / 100)
    if ideal_value > max_value:
        ideal_qty   = int(max_value / entry_price)
        ideal_value = ideal_qty * entry_price

    position_pct  = round((ideal_value / portfolio_value) * 100, 2)

    return {
        "symbol":          symbol,
        "entry":           entry_price,
        "qty":             ideal_qty,
        "position_value":  round(ideal_value, 2),
        "position_pct":    position_pct,
        "risk_amount":     round(risk_amount, 2),
        "risk_per_share":  risk_per_sh,
        "stop_loss":       sl["stop"],
        "risk_pct_stock":  sl["risk_pct"],
    }


# ── Risk / Reward Calculator ──────────────────────────────────────────────────

def risk_reward(entry: float, stop: float, target: float) -> dict:
    """
    R:R ratio = (target - entry) / (entry - stop)
    Minimum acceptable: 2.0 (risk ₹1 to make ₹2)
    """
    risk   = entry - stop
    reward = target - entry
    if risk <= 0:
        return {"ratio": 0, "valid": False, "reason": "Stop >= Entry"}
    ratio  = round(reward / risk, 2)
    return {
        "entry":  entry,
        "stop":   stop,
        "target": target,
        "risk":   round(risk,   2),
        "reward": round(reward, 2),
        "ratio":  ratio,
        "valid":  ratio >= MIN_RISK_REWARD,
        "grade":  "EXCELLENT" if ratio >= 3 else "GOOD" if ratio >= 2 else "POOR",
    }


# ── Trailing Stop Tracker ─────────────────────────────────────────────────────

class TrailingStopTracker:
    """
    Tracks highest price seen since entry and updates trailing stop.
    Persists in memory — rebuild from holdings on startup.
    """
    def __init__(self):
        self._state: dict[str, dict] = {}   # symbol → {high, stop, entry}

    def add(self, symbol: str, entry: float, trail_pct: float = 8.0):
        atr  = _atr(symbol)
        stop = round(entry * (1 - trail_pct / 100), 2) if not atr else \
               round(entry - atr * ATR_STOP_MULTIPLIER, 2)
        self._state[symbol] = {"entry": entry, "high": entry,
                                "stop": stop, "trail_pct": trail_pct}

    def update(self, symbol: str, current_price: float) -> dict | None:
        """
        Call this every price poll. Returns alert dict if stop is hit.
        Also raises stop if price makes a new high.
        """
        if symbol not in self._state:
            return None
        s = self._state[symbol]
        if current_price > s["high"]:
            s["high"] = current_price
            # Raise stop
            atr = _atr(symbol)
            if atr:
                s["stop"] = round(current_price - atr * ATR_STOP_MULTIPLIER, 2)
            else:
                s["stop"] = round(current_price * (1 - s["trail_pct"] / 100), 2)

        if current_price <= s["stop"]:
            profit = round(current_price - s["entry"], 2)
            pct    = round((profit / s["entry"]) * 100, 2)
            return {
                "symbol":        symbol,
                "entry":         s["entry"],
                "stop_hit":      s["stop"],
                "current_price": current_price,
                "profit":        profit,
                "pct":           pct,
                "action":        "SELL — Trailing stop hit",
            }
        return None

    def get_all(self) -> list:
        result = []
        for sym, s in self._state.items():
            result.append({
                "symbol":     sym,
                "entry":      s["entry"],
                "current_high": s["high"],
                "stop":       s["stop"],
                "trail_pct":  s["trail_pct"],
            })
        return result


# ── Portfolio Risk Analysis ───────────────────────────────────────────────────

def portfolio_risk_analysis(portfolio: list, portfolio_pnl: list) -> dict:
    """
    Analyse overall portfolio risk:
    - Concentration alerts
    - Correlation warning (rough sector grouping)
    - Total risk exposure
    """
    total_value = sum(r.get("market_value", 0) for r in portfolio_pnl)
    if total_value == 0:
        return {}

    positions = []
    for r in portfolio_pnl:
        sym  = r["symbol"]
        mv   = r.get("market_value", 0)
        pct  = round((mv / total_value) * 100, 2)
        positions.append({
            "symbol":  sym,
            "value":   mv,
            "pct":     pct,
            "overweight": pct > MAX_POSITION_PCT,
        })

    overweight  = [p for p in positions if p["overweight"]]
    top5_conc   = sum(sorted([p["pct"] for p in positions], reverse=True)[:5])

    # Sector groups (rough)
    IT_STOCKS   = {"TCS","INFY","WIPRO","HCLTECH","TECHM"}
    BANK_STOCKS = {"HDFCBANK","ICICIBANK","SBIN","AXISBANK","KOTAKBANK"}

    it_pct   = sum(p["pct"] for p in positions if p["symbol"].replace(".NS","") in IT_STOCKS)
    bank_pct = sum(p["pct"] for p in positions if p["symbol"].replace(".NS","") in BANK_STOCKS)

    return {
        "total_value":    round(total_value, 2),
        "positions":      positions,
        "overweight":     overweight,
        "top5_conc_pct":  round(top5_conc, 2),
        "it_exposure_pct":   round(it_pct,   2),
        "bank_exposure_pct": round(bank_pct, 2),
        "diversified":    top5_conc < 80 and not overweight,
        "warnings": [
            f"⚠️ {p['symbol'].replace('.NS','')} is {p['pct']:.1f}% of portfolio (>{MAX_POSITION_PCT}%)"
            for p in overweight
        ] + (
            [f"⚠️ IT sector = {it_pct:.1f}% of portfolio — high concentration"] if it_pct > 40 else []
        ) + (
            [f"⚠️ Banking sector = {bank_pct:.1f}% — high concentration"] if bank_pct > 40 else []
        ),
    }


# ── Pre-Trade Checklist ───────────────────────────────────────────────────────

def pre_trade_checklist(
    symbol: str,
    entry_price: float,
    portfolio_value: float,
    portfolio: list,
    ta_result: dict,
    fii_trend: list = None,
    earnings_days: int = None,
) -> dict:
    """
    6-point checklist before entering any trade.
    Returns STRONG BUY / WATCH / AVOID with reasons.
    """
    checks = []

    # 1. RSI not overbought
    rsi = ta_result.get("rsi")
    if rsi is not None:
        ok  = rsi < 65
        checks.append({
            "name":   "RSI Not Overbought",
            "pass":   ok,
            "detail": f"RSI {rsi:.1f} {'✅ < 65' if ok else '❌ ≥ 65 — overbought'}",
        })

    # 2. Price above 50-day MA
    above_ma = ta_result.get("above_ma50")
    if above_ma is not None:
        checks.append({
            "name":   "Above 50-day MA",
            "pass":   above_ma,
            "detail": f"MA50 ₹{ta_result.get('ma50',0):,.2f} — "
                      f"{'✅ price above' if above_ma else '❌ price below — downtrend'}",
        })

    # 3. Volume conviction
    vol_sig = ta_result.get("volume_signal", "")
    ok      = vol_sig in ("SPIKE", "HIGH", "NORMAL")
    checks.append({
        "name":   "Volume Conviction",
        "pass":   ok,
        "detail": f"Volume {vol_sig} — {'✅ adequate' if ok else '❌ low volume = weak move'}",
    })

    # 4. FII net positive (last 3 days)
    if fii_trend:
        fii_rows = [r for r in fii_trend if r.get("category") == "FII/FPI"][:3]
        nets     = [r["net"] for r in fii_rows]
        fii_ok   = sum(1 for n in nets if n > 0) >= 2
        checks.append({
            "name":   "FII Flow Positive",
            "pass":   fii_ok,
            "detail": f"FII last 3d nets: {[round(n/1e7,1) for n in nets]} Cr — "
                      f"{'✅ buying' if fii_ok else '❌ selling'}",
        })

    # 5. No earnings within 7 days
    if earnings_days is not None:
        ok = earnings_days > 7
        checks.append({
            "name":   "No Imminent Earnings",
            "pass":   ok,
            "detail": f"Earnings in {earnings_days}d — "
                      f"{'✅ safe' if ok else '❌ < 7 days — high IV risk'}",
        })

    # 6. Position size within limit
    total_invested = sum(h.get("qty",0) * h.get("avg_price",0) for h in portfolio
                        if h["symbol"] == symbol)
    new_value      = entry_price * get_position_size(
        symbol, entry_price, portfolio_value)["qty"]
    total_sym_val  = total_invested + new_value
    pos_pct        = round((total_sym_val / portfolio_value) * 100, 2) if portfolio_value else 0
    ok             = pos_pct <= MAX_POSITION_PCT
    checks.append({
        "name":   f"Position ≤ {MAX_POSITION_PCT}%",
        "pass":   ok,
        "detail": f"Would be {pos_pct:.1f}% of portfolio — "
                  f"{'✅ ok' if ok else f'❌ exceeds {MAX_POSITION_PCT}% limit'}",
    })

    passed = sum(1 for c in checks if c["pass"])
    total  = len(checks)

    verdict = (
        "STRONG BUY" if passed == total else
        "BUY"        if passed >= total - 1 else
        "WATCH"      if passed >= total // 2 else
        "AVOID"
    )

    return {
        "symbol":  symbol,
        "entry":   entry_price,
        "checks":  checks,
        "passed":  passed,
        "total":   total,
        "verdict": verdict,
        "stop_loss": get_stop_loss(symbol, entry_price)["stop"],
        "position":  get_position_size(symbol, entry_price, portfolio_value),
    }
