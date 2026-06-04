"""
Hermes Agent — Main Scheduler
Orchestrates all four tasks:
  1. 08:00 IST  → Morning Brief (indices + FII + portfolio P&L + news)
  2. Market hrs → Price Alert watcher (continuous polling)
  3. 15:45 IST  → After-market 52W Range Report
  4. Daily       → Earnings Calendar (sent with morning brief + 3-day reminders)

Run:
    python main.py

Dependencies:
    pip install yfinance requests schedule pytz
"""

import schedule
import time
import logging
import threading
import pytz
from datetime import datetime

import config
from data_fetcher import (
    get_indices,
    get_portfolio_pnl,
    get_fii_dii_data,
    get_news_headlines,
    get_52w_analysis,
    get_earnings_calendar,
)
from formatter import (
    format_morning_brief,
    format_52w_report,
    format_earnings_reminder,
)
from telegram_sender import TelegramSender
from alert_watcher import AlertWatcher

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/hermes.log"),
    ],
)
log = logging.getLogger("hermes.main")

IST = pytz.timezone("Asia/Kolkata")


# ── Utilities ─────────────────────────────────────────────────────────────────

def ist_now() -> datetime:
    return datetime.now(IST)


def is_market_open() -> bool:
    """True during NSE trading hours on weekdays (IST)."""
    now = ist_now()
    if now.weekday() >= 5:       # Saturday=5, Sunday=6
        return False
    t = now.time()
    from datetime import time as dtime
    open_t  = dtime(config.MARKET_OPEN_HOUR,  config.MARKET_OPEN_MINUTE)
    close_t = dtime(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)
    return open_t <= t <= close_t


def is_weekday() -> bool:
    return ist_now().weekday() < 5


# ── Task runners ──────────────────────────────────────────────────────────────

def run_morning_brief():
    """Fetch everything and send the morning brief."""
    if not is_weekday():
        log.info("Morning brief skipped — weekend.")
        return

    log.info("▶ Running morning brief…")
    try:
        indices       = get_indices()
        portfolio_pnl = get_portfolio_pnl(config.PORTFOLIO)
        fii_dii       = get_fii_dii_data()
        news          = get_news_headlines(config.WATCHLIST, max_per_stock=2)
        earnings      = get_earnings_calendar(config.WATCHLIST)

        # Flag upcoming earnings for in-brief reminder
        earnings_soon = [e for e in earnings if e["days_out"] <= config.EARNINGS_REMINDER_DAYS]

        msg = format_morning_brief(
            indices       = indices,
            portfolio_rows = portfolio_pnl,
            fii_dii       = fii_dii,
            news          = news,
            earnings_soon = earnings_soon,
        )
        sender.send_long(msg)
        log.info("✅ Morning brief sent.")

    except Exception as e:
        log.exception(f"Morning brief failed: {e}")
        sender.send("⚠️ Hermes: Morning brief failed\\. Check logs\\.", parse_mode="MarkdownV2")


def run_52w_report():
    """Fetch 52W data for all watchlist stocks and send after-market report."""
    if not is_weekday():
        log.info("52W report skipped — weekend.")
        return

    log.info("▶ Running 52W report…")
    try:
        analysis = get_52w_analysis(config.WATCHLIST, config.DANGER_ZONE_PCT)
        msg = format_52w_report(analysis)
        sender.send_long(msg)
        log.info("✅ 52W report sent.")
    except Exception as e:
        log.exception(f"52W report failed: {e}")
        sender.send("⚠️ Hermes: 52W report failed\\. Check logs\\.", parse_mode="MarkdownV2")


def run_earnings_reminder():
    """Send earnings calendar daily (weekdays). Highlights near-term dates."""
    if not is_weekday():
        return
    log.info("▶ Running earnings reminder check…")
    try:
        earnings = get_earnings_calendar(config.WATCHLIST)
        # Only send standalone reminder if something is ≤ EARNINGS_REMINDER_DAYS away
        upcoming = [e for e in earnings if e["days_out"] <= config.EARNINGS_REMINDER_DAYS]
        if upcoming:
            msg = format_earnings_reminder(earnings)
            sender.send_long(msg)
            log.info(f"✅ Earnings reminder sent ({len(upcoming)} stock(s) close).")
        else:
            log.info("No imminent earnings — skipping standalone reminder.")
    except Exception as e:
        log.exception(f"Earnings reminder failed: {e}")


# ── Boot ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("  HERMES AGENT — STARTING UP")
    log.info("=" * 60)

    # Validate Telegram connection
    if not sender.test_connection():
        log.error("❌ Telegram connection failed. Check your BOT_TOKEN and CHAT_ID in config.py.")
        return

    log.info("✅ Telegram connected.")

    # ── Schedule fixed-time tasks ─────────────────────────────────────────────
    schedule.every().day.at(config.MORNING_BRIEF_TIME).do(run_morning_brief)
    schedule.every().day.at(config.AFTER_MARKET_TIME).do(run_52w_report)
    # Earnings reminder fires 30 min before morning brief
    reminder_time = _offset_time(config.MORNING_BRIEF_TIME, minutes=-30)
    schedule.every().day.at(reminder_time).do(run_earnings_reminder)

    log.info(f"📅 Scheduled: Morning brief @ {config.MORNING_BRIEF_TIME} IST")
    log.info(f"📅 Scheduled: 52W report    @ {config.AFTER_MARKET_TIME} IST")
    log.info(f"📅 Scheduled: Earnings check @ {reminder_time} IST")

    # ── Alert watcher in background thread ───────────────────────────────────
    watcher = AlertWatcher(
        alerts       = config.PRICE_ALERTS,
        sender       = sender,
        poll_seconds = config.ALERT_POLL_SECONDS,
    )
    alert_thread = threading.Thread(
        target = watcher.run,
        args   = (is_market_open,),
        daemon = True,
        name   = "AlertWatcher",
    )
    alert_thread.start()
    log.info(f"🔔 Alert watcher running (polls every {config.ALERT_POLL_SECONDS}s during market hours).")

    # ── Optional: send brief immediately on startup if market not yet open ───
    now_str = ist_now().strftime("%H:%M")
    if now_str < config.MORNING_BRIEF_TIME:
        log.info("Hermes started before brief time — waiting for scheduled run.")
    else:
        log.info("Hermes started mid-session. Sending startup status…")
        sender.send(
            "🟢 *Hermes Agent online\\.*\n"
            "_Alert watcher armed\\. Next brief: tomorrow 08:00 IST\\._",
            parse_mode="MarkdownV2",
        )

    # ── Main loop ─────────────────────────────────────────────────────────────
    log.info("Hermes is running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)


def _offset_time(time_str: str, minutes: int) -> str:
    """Offset a HH:MM string by N minutes."""
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    total = total % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


# ── Global sender (shared by scheduler + watcher) ────────────────────────────
sender = TelegramSender(
    token   = config.TELEGRAM_BOT_TOKEN,
    chat_id = config.TELEGRAM_CHAT_ID,
)

if __name__ == "__main__":
    main()
