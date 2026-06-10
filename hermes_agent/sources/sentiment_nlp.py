"""
Hermes — News Sentiment Scorer
Scores each headline +1 (positive) / -1 (negative) / 0 (neutral).
Tracks 7-day sentiment trend per stock.
Detects sentiment flip (was positive, now negative = sell signal).
"""

import logging
import json
import os
from datetime import datetime, timedelta
import yfinance as yf

log = logging.getLogger("hermes.sentiment_nlp")

SENTIMENT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "sentiment_history.json")

# Positive keywords → bullish for stock
POSITIVE = [
    "wins contract", "wins deal", "new order", "acquisition", "partnership",
    "record profit", "record revenue", "beats estimate", "upgrade", "buy rating",
    "dividend", "bonus", "buyback", "expansion", "launch", "approval", "fda",
    "strong growth", "outperform", "raises guidance", "increases stake",
    "promoter buys", "fii buying", "institutional buying", "all-time high",
    "debt-free", "rating upgrade", "new high", "profit up", "revenue up",
]

# Negative keywords → bearish for stock
NEGATIVE = [
    "loss", "fraud", "default", "penalty", "lawsuit", "raid", "downgrade",
    "sell rating", "misses estimate", "profit down", "revenue down",
    "md resigns", "ceo resigns", "promoter sells", "pledges shares",
    "debt burden", "rating downgrade", "investigation", "scam", "ban",
    "suspended", "closure", "layoffs", "write-off", "provision", "npa",
    "below estimate", "disappoints", "guidance cut", "reduces stake",
    "fii selling", "institutional selling",
]

# High-impact negative (score -2)
CRITICAL_NEGATIVE = [
    "fraud", "default", "sebi ban", "cbi raid", "ed raid", "promoter arrested",
    "insolvency", "nclat", "liquidation",
]


def score_headline(title: str) -> int:
    """Score a single headline. Returns -2, -1, 0, +1."""
    title_lower = title.lower()
    # Critical negatives first
    for kw in CRITICAL_NEGATIVE:
        if kw in title_lower:
            return -2
    score = 0
    for kw in POSITIVE:
        if kw in title_lower:
            score += 1
    for kw in NEGATIVE:
        if kw in title_lower:
            score -= 1
    return max(-2, min(1, score))


def _load_history() -> dict:
    try:
        if os.path.exists(SENTIMENT_FILE):
            with open(SENTIMENT_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_history(history: dict):
    os.makedirs(os.path.dirname(SENTIMENT_FILE), exist_ok=True)
    with open(SENTIMENT_FILE, "w") as f:
        json.dump(history, f, indent=2)


def analyze_news_sentiment(watchlist: list, max_per_stock: int = 5) -> list:
    """
    Score recent news for all watchlist stocks.
    Returns per-stock sentiment with 7-day trend and flip detection.
    """
    history  = _load_history()
    today    = datetime.now().strftime("%Y-%m-%d")
    results  = []

    for sym in watchlist:
        if sym == "NIFTY50":
            continue
        try:
            t    = yf.Ticker(sym)
            news = t.news or []

            scored_news = []
            total_score = 0
            for n in news[:max_per_stock]:
                title = n.get("title", "")
                score = score_headline(title)
                total_score += score
                scored_news.append({
                    "title":   title[:80],
                    "score":   score,
                    "emoji":   "🟢" if score > 0 else ("🔴" if score < 0 else "⚪"),
                    "age_h":   round((datetime.now().timestamp() - n.get("providerPublishTime", 0)) / 3600, 1),
                })

            avg_score = round(total_score / len(scored_news), 2) if scored_news else 0

            # Store in history
            sym_key = sym.replace(".NS", "")
            if sym_key not in history:
                history[sym_key] = []
            history[sym_key].append({"date": today, "score": avg_score})

            # Keep only last 14 days
            cutoff = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
            history[sym_key] = [h for h in history[sym_key] if h["date"] >= cutoff]

            # 7-day trend
            recent = history[sym_key][-7:]
            trend_scores = [h["score"] for h in recent]
            trend_avg    = round(sum(trend_scores) / len(trend_scores), 2) if trend_scores else 0

            # Flip detection
            prev_scores  = trend_scores[:-1]
            prev_avg     = sum(prev_scores) / len(prev_scores) if prev_scores else 0
            sentiment_flip = (
                "POSITIVE_TO_NEGATIVE" if prev_avg > 0 and avg_score < 0 else
                "NEGATIVE_TO_POSITIVE" if prev_avg < 0 and avg_score > 0 else
                None
            )

            sentiment = (
                "VERY POSITIVE" if avg_score >= 0.7 else
                "POSITIVE"      if avg_score > 0    else
                "NEGATIVE"      if avg_score < 0    else
                "VERY NEGATIVE" if avg_score <= -0.7 else
                "NEUTRAL"
            )

            results.append({
                "symbol":         sym_key,
                "today_score":    avg_score,
                "trend_avg":      trend_avg,
                "sentiment":      sentiment,
                "sentiment_flip": sentiment_flip,
                "news":           scored_news,
                "flip_alert":     sentiment_flip is not None,
            })
        except Exception as e:
            log.debug(f"Sentiment failed {sym}: {e}")

    _save_history(history)
    return sorted(results, key=lambda x: x["today_score"], reverse=True)
