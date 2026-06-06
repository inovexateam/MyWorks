"""
Hermes Agent — Configuration
Credentials load from .env (never commit that file).
Portfolio / alerts / watchlist live in data/*.json (also gitignored).
Only schedule settings and thresholds live here.
"""

import os
from dotenv import load_dotenv
from store import load as _load

load_dotenv()

# ─── Credentials (from .env) ─────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")

# ─── Runtime data (from data/*.json) ─────────────────────────────────────────
PORTFOLIO     = _load("holdings")
WATCHLIST     = _load("watchlist")
PRICE_ALERTS  = _load("alerts")

# ─── Thresholds ───────────────────────────────────────────────────────────────
DANGER_ZONE_PCT        = 8.0
EARNINGS_REMINDER_DAYS = 3

# ─── Schedule (IST, 24h) ──────────────────────────────────────────────────────
MORNING_BRIEF_TIME  = "08:00"
AFTER_MARKET_TIME   = "15:45"
ALERT_POLL_SECONDS  = 30

# ─── Market Hours (IST) ───────────────────────────────────────────────────────
MARKET_OPEN_HOUR    = 9
MARKET_OPEN_MINUTE  = 15
MARKET_CLOSE_HOUR   = 15
MARKET_CLOSE_MINUTE = 30
