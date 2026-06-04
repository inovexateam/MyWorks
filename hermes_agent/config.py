"""
Hermes Agent — Configuration
Edit this file to set your portfolio, alerts, and Telegram credentials.
"""

# ─── Telegram ───────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"   # from @BotFather
TELEGRAM_CHAT_ID   = "YOUR_CHAT_ID_HERE"     # your personal chat ID

# ─── Portfolio ───────────────────────────────────────────────────────────────
# symbol: NSE ticker  |  qty: shares held  |  avg_price: your buy price (₹)
PORTFOLIO = [
    {"symbol": "RELIANCE.NS",  "qty": 50,   "avg_price": 2650.00},
    {"symbol": "TCS.NS",       "qty": 30,   "avg_price": 3820.00},
    {"symbol": "INFY.NS",      "qty": 80,   "avg_price": 1450.00},
    {"symbol": "HDFCBANK.NS",  "qty": 60,   "avg_price": 1750.00},
    {"symbol": "ICICIBANK.NS", "qty": 40,   "avg_price": 1020.00},
]

# ─── Watchlist (for news + 52W + earnings) ───────────────────────────────────
# Can include stocks you don't own yet
WATCHLIST = [s["symbol"] for s in PORTFOLIO] + [
    "WIPRO.NS",
    "BAJFINANCE.NS",
    "SBIN.NS",
]

# ─── Price Alerts ────────────────────────────────────────────────────────────
# condition: "above" fires when price crosses ABOVE level
#            "below" fires when price drops BELOW level
# cooldown_hours: minimum hours between repeat alerts for same rule
PRICE_ALERTS = [
    {"symbol": "RELIANCE.NS",  "condition": "below", "level": 2850.00, "cooldown_hours": 4},
    {"symbol": "HDFCBANK.NS",  "condition": "above", "level": 1780.00, "cooldown_hours": 4},
    {"symbol": "INFY.NS",      "condition": "below", "level": 1420.00, "cooldown_hours": 4},
    {"symbol": "TCS.NS",       "condition": "above", "level": 4200.00, "cooldown_hours": 4},
    {"symbol": "NIFTY50",      "condition": "above", "level": 24800.0, "cooldown_hours": 2},
    {"symbol": "SBIN.NS",      "condition": "below", "level": 820.00,  "cooldown_hours": 4},
]

# ─── 52W Danger Threshold ────────────────────────────────────────────────────
# Flag a stock if it's within this % of its 52-week low
DANGER_ZONE_PCT = 8.0

# ─── Earnings Reminder ───────────────────────────────────────────────────────
# Send a reminder this many days before earnings
EARNINGS_REMINDER_DAYS = 3

# ─── Scheduler Times (IST, 24h) ──────────────────────────────────────────────
MORNING_BRIEF_TIME    = "08:00"   # morning brief
AFTER_MARKET_TIME     = "15:45"   # 52W range report (after NSE close at 15:30)
ALERT_POLL_SECONDS    = 30        # how often to poll prices during market hours

# ─── Market Hours (IST) ──────────────────────────────────────────────────────
MARKET_OPEN_HOUR    = 9
MARKET_OPEN_MINUTE  = 15
MARKET_CLOSE_HOUR   = 15
MARKET_CLOSE_MINUTE = 30
