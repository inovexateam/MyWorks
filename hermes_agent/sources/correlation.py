"""
Hermes — Portfolio Correlation & Beta Analysis
Correlation matrix, portfolio beta, drawdown scenario.
Helps detect hidden concentration risk.
"""

import logging
import yfinance as yf
import pandas as pd

log = logging.getLogger("hermes.correlation")

NIFTY_TICKER = "^NSEI"
PERIOD = "6mo"


def get_correlation_matrix(portfolio: list) -> dict | None:
    """
    Returns correlation matrix between all holdings.
    Correlation > 0.8 = stocks move together = hidden concentration risk.
    """
    symbols = [h["symbol"] for h in portfolio if h["symbol"] != "NIFTY50"]
    if len(symbols) < 2:
        return None

    try:
        prices = {}
        for sym in symbols:
            df = yf.Ticker(sym).history(period=PERIOD, interval="1d")
            if not df.empty:
                prices[sym.replace(".NS","")] = df["Close"]

        if len(prices) < 2:
            return None

        df_all  = pd.DataFrame(prices).dropna()
        returns = df_all.pct_change().dropna()
        corr    = returns.corr().round(3)

        # Find highly correlated pairs
        high_corr_pairs = []
        cols = corr.columns.tolist()
        for i in range(len(cols)):
            for j in range(i+1, len(cols)):
                val = float(corr.iloc[i, j])
                if abs(val) > 0.75:
                    high_corr_pairs.append({
                        "stock1": cols[i],
                        "stock2": cols[j],
                        "corr":   val,
                        "risk":   "HIGH" if abs(val) > 0.9 else "MEDIUM",
                    })

        return {
            "matrix":     corr.to_dict(),
            "symbols":    cols,
            "high_corr":  sorted(high_corr_pairs, key=lambda x: abs(x["corr"]), reverse=True),
            "n_stocks":   len(cols),
        }
    except Exception as e:
        log.warning(f"Correlation matrix failed: {e}")
        return None


def get_portfolio_beta(portfolio: list) -> dict | None:
    """
    Portfolio Beta vs Nifty.
    Beta > 1 = portfolio moves more than market.
    Beta < 1 = portfolio moves less (defensive).
    """
    try:
        nifty_df = yf.Ticker(NIFTY_TICKER).history(period=PERIOD, interval="1d")
        if nifty_df.empty:
            return None
        nifty_ret = nifty_df["Close"].pct_change().dropna()

        total_value   = sum(h.get("qty",0) * h.get("avg_price",0) for h in portfolio)
        weighted_beta = 0.0
        betas         = []

        for h in portfolio:
            sym = h["symbol"]
            if sym == "NIFTY50":
                continue
            try:
                df   = yf.Ticker(sym).history(period=PERIOD, interval="1d")
                if df.empty: continue
                ret  = df["Close"].pct_change().dropna()
                # Align
                aligned = pd.concat([ret, nifty_ret], axis=1, join="inner")
                aligned.columns = ["stock","nifty"]
                cov   = aligned["stock"].cov(aligned["nifty"])
                var   = aligned["nifty"].var()
                beta  = round(cov / var, 3) if var > 0 else 1.0
                weight = (h.get("qty",0) * h.get("avg_price",0)) / total_value if total_value > 0 else 0
                weighted_beta += beta * weight
                betas.append({
                    "symbol": sym.replace(".NS",""),
                    "beta":   beta,
                    "weight": round(weight*100, 1),
                    "risk":   "HIGH" if beta > 1.5 else ("MEDIUM" if beta > 1.1 else "LOW"),
                })
            except Exception:
                pass

        portfolio_beta = round(weighted_beta, 3)
        interpretation = (
            "Very aggressive — moves 50%+ more than market" if portfolio_beta > 1.5 else
            "Aggressive — moves more than market"            if portfolio_beta > 1.2 else
            "Balanced — moves roughly with market"           if portfolio_beta > 0.8 else
            "Defensive — moves less than market"             if portfolio_beta > 0.5 else
            "Very defensive / uncorrelated"
        )

        return {
            "portfolio_beta": portfolio_beta,
            "interpretation": interpretation,
            "stock_betas":    sorted(betas, key=lambda x: x["beta"], reverse=True),
            "risk_level":     "HIGH" if portfolio_beta > 1.3 else ("MEDIUM" if portfolio_beta > 1.0 else "LOW"),
        }
    except Exception as e:
        log.warning(f"Beta calc failed: {e}")
        return None


def get_drawdown_scenario(portfolio_pnl: list, scenarios: list = None) -> list:
    """
    Simulate portfolio loss under different market fall scenarios.
    Uses each stock's beta to estimate impact.
    """
    if scenarios is None:
        scenarios = [5, 10, 20, 30]

    total_value = sum(r.get("market_value",0) for r in portfolio_pnl)
    if total_value == 0:
        return []

    results = []
    for pct_fall in scenarios:
        est_loss = total_value * (pct_fall / 100)
        results.append({
            "scenario":   f"Nifty falls {pct_fall}%",
            "pct_fall":   pct_fall,
            "est_loss":   round(est_loss, 0),
            "rem_value":  round(total_value - est_loss, 0),
            "severity":   "HIGH" if pct_fall >= 20 else ("MEDIUM" if pct_fall >= 10 else "LOW"),
        })
    return results
