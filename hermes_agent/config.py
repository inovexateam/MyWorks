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

# ─── Optional: Twilio SMS fallback ───────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN",  "")
TWILIO_FROM        = os.getenv("TWILIO_FROM",        "")
TWILIO_TO          = os.getenv("TWILIO_TO",          "")

# ─── Optional: Anthropic Claude API for AI outlook ───────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY",  "")

# ─── Paper trading starting capital ──────────────────────────────────────────
PAPER_STARTING_CASH = 1_000_000   # ₹10 Lakh

# ─── Tax settings ────────────────────────────────────────────────────────────
STCG_RATE  = 0.15
LTCG_RATE  = 0.10
LTCG_EXEMPTION = 100_000
