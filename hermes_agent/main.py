"""
Hermes Agent — Main Scheduler (v2)
All jobs:
  08:00  Morning brief (extended with signals, macro, global)
  06:00  Corporate actions + earnings warning
  06:30  Macro events calendar
  Hourly (market hrs) Bulk/block deal scan
  Hourly (market hrs) FII trend check
  Hourly (market hrs) OI scan
  Hourly (market hrs) Circuit breaker check
  15:45  52W range report
  09:00 Sun  Weekly signal digest (1W + 1M outlook)
  30s poll   Price alerts (existing)
"""

import schedule
import time
import logging
import threading
import pytz
from datetime import datetime, date

import config
from data_fetcher import (
    get_indices, get_portfolio_pnl, get_fii_dii_data,
    get_news_headlines, get_52w_analysis, get_earnings_calendar,
)
from formatter import (
    format_52w_report, format_earnings_reminder,
    format_signal_digest, format_corporate_action_alert,
    format_macro_alert, format_deal_alert, format_fii_trend_alert,
    format_morning_brief_extended,
)
from telegram_sender import TelegramSender
from alert_watcher import AlertWatcher
from signals import collect_all_signals, filter_by_timeframe
from sources.nse import (
    get_bulk_deals, get_block_deals, get_circuit_stocks, get_fii_dii_trend,
)
from sources.bse import get_corporate_actions
from sources.macro import (
    get_upcoming_macro_events, get_high_impact_news,
    get_crude_price, get_inr_usd, get_global_markets,
)

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


def ist_now() -> datetime:
    return datetime.now(IST)


def is_weekday() -> bool:
    return ist_now().weekday() < 5


def is_market_open() -> bool:
    now = ist_now()
    if now.weekday() >= 5:
        return False
    from datetime import time as dtime
    t = now.time()
    return dtime(config.MARKET_OPEN_HOUR, config.MARKET_OPEN_MINUTE) <= t <= \
           dtime(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)


def _offset_time(time_str: str, minutes: int) -> str:
    h, m  = map(int, time_str.split(":"))
    total = (h * 60 + m + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


# ── Job: Morning Brief (extended) ────────────────────────────────────────────

def run_morning_brief():
    if not is_weekday():
        return
    log.info("▶ Morning brief (extended)…")
    try:
        indices    = get_indices()
        port_pnl   = get_portfolio_pnl(config.PORTFOLIO)
        fii_dii    = get_fii_dii_data()
        news       = get_news_headlines(config.WATCHLIST, max_per_stock=2)
        earnings   = get_earnings_calendar(config.WATCHLIST)
        soon       = [e for e in earnings if e["days_out"] <= config.EARNINGS_REMINDER_DAYS]
        signals    = collect_all_signals(config.WATCHLIST)
        today_sigs = filter_by_timeframe(signals, "TODAY")
        crude      = get_crude_price()
        inr        = get_inr_usd()
        global_mkts= get_global_markets()
        macro_evts = get_upcoming_macro_events(days_ahead=7)

        msg = format_morning_brief_extended(
            indices, port_pnl, fii_dii, news, soon,
            today_sigs, crude, inr, global_mkts, macro_evts,
        )
        sender.send_long(msg)
        log.info("✅ Extended morning brief sent.")
    except Exception as e:
        log.exception(f"Morning brief failed: {e}")
        sender.send("⚠️ Hermes: Morning brief failed\\.", parse_mode="MarkdownV2")


# ── Job: Corporate Actions Warning ───────────────────────────────────────────

def run_corporate_actions():
    if not is_weekday():
        return
    log.info("▶ Corporate actions check…")
    try:
        actions = get_corporate_actions(config.WATCHLIST, days_ahead=30)
        urgent  = [a for a in actions if a["days_out"] <= 5]
        for a in urgent:
            msg = format_corporate_action_alert(a)
            sender.send(msg)
        if urgent:
            log.info(f"✅ {len(urgent)} corporate action alert(s) sent.")
        else:
            log.info("No urgent corporate actions today.")
    except Exception as e:
        log.exception(f"Corporate actions job failed: {e}")


# ── Job: Macro Events Calendar ────────────────────────────────────────────────

def run_macro_events():
    if not is_weekday():
        return
    log.info("▶ Macro events check…")
    try:
        events = get_upcoming_macro_events(days_ahead=7)
        urgent = [e for e in events if e["days_out"] <= 3]
        crude  = get_crude_price()
        inr    = get_inr_usd()
        for ev in urgent:
            msg = format_macro_alert(ev, crude, inr)
            sender.send(msg)
        if urgent:
            log.info(f"✅ {len(urgent)} macro event alert(s) sent.")
    except Exception as e:
        log.exception(f"Macro events job failed: {e}")


# ── Job: Bulk/Block Deal Scanner ─────────────────────────────────────────────

def run_bulk_block_scan():
    if not is_market_open():
        return
    log.info("▶ Bulk/block deal scan…")
    try:
        bulk  = get_bulk_deals(config.WATCHLIST)
        block = get_block_deals(config.WATCHLIST)
        for deal in bulk + block:
            if deal.get("value_cr", 0) >= 5:   # only alert if ≥₹5Cr
                msg = format_deal_alert(deal)
                sender.send(msg)
        if bulk or block:
            log.info(f"✅ Deals found: {len(bulk)} bulk, {len(block)} block.")
    except Exception as e:
        log.exception(f"Bulk/block scan failed: {e}")


# ── Job: FII Trend Check ──────────────────────────────────────────────────────

def run_fii_trend():
    if not is_market_open():
        return
    log.info("▶ FII trend check…")
    try:
        from signals import signals_from_fii_trend
        trend = get_fii_dii_trend()
        sigs  = signals_from_fii_trend(trend)
        for s in sigs:
            msg = format_fii_trend_alert(s)
            sender.send(msg)
    except Exception as e:
        log.exception(f"FII trend check failed: {e}")


# ── Job: Circuit Breaker Check ────────────────────────────────────────────────

def run_circuit_check():
    if not is_market_open():
        return
    log.info("▶ Circuit check…")
    try:
        from signals import signals_from_circuit
        circuits = get_circuit_stocks(config.WATCHLIST)
        sigs     = signals_from_circuit(circuits)
        for s in sigs:
            sender.send(
                f"🚨 *CIRCUIT BREAKER*\n\n{s['summary']}\n\n"
                f"_— Hermes Agent_", parse_mode="MarkdownV2"
            )
    except Exception as e:
        log.exception(f"Circuit check failed: {e}")


# ── Job: 52W Report ───────────────────────────────────────────────────────────

def run_52w_report():
    if not is_weekday():
        return
    log.info("▶ 52W report…")
    try:
        analysis = get_52w_analysis(config.WATCHLIST, config.DANGER_ZONE_PCT)
        msg = format_52w_report(analysis)
        sender.send_long(msg)
        log.info("✅ 52W report sent.")
    except Exception as e:
        log.exception(f"52W report failed: {e}")


# ── Job: Weekly Signal Digest (1W + 1M) ──────────────────────────────────────

def run_breakout_scan():
    if not is_market_open():
        return
    log.info("▶ Breakout scan…")
    try:
        from sources.breakout import full_breakout_scan
        from formatter import format_breakout_report
        scan = full_breakout_scan(config.WATCHLIST)
        if scan["breakouts"] or scan["accumulation"]:
            sender.send_long(format_breakout_report(scan))
    except Exception as e:
        log.exception(f"Breakout scan failed: {e}")


def run_fundamentals_brief():
    if not is_weekday():
        return
    log.info("▶ Fundamentals brief…")
    try:
        from sources.fundamentals import get_watchlist_fundamentals
        from formatter import format_fundamentals_report
        data = get_watchlist_fundamentals(config.WATCHLIST)
        sender.send_long(format_fundamentals_report(data))
    except Exception as e:
        log.exception(f"Fundamentals brief failed: {e}")


def run_global_macro_brief():
    if not is_weekday():
        return
    log.info("▶ Global macro brief…")
    try:
        from sources.global_macro import get_global_macro
        from formatter import format_global_macro_report
        macro = get_global_macro()
        if macro.get("signals"):
            sender.send_long(format_global_macro_report(macro))
    except Exception as e:
        log.exception(f"Global macro brief failed: {e}")


def run_weekly_digest():
    log.info("▶ Weekly signal digest…")
    try:
        signals = collect_all_signals(config.WATCHLIST)
        for tf in ("1W", "1M"):
            msg = format_signal_digest(signals, tf)
            sender.send_long(msg)
        log.info("✅ Weekly digest sent.")
    except Exception as e:
        log.exception(f"Weekly digest failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_golden_rules():
    if not is_weekday(): return
    log.info("▶ Golden rules check…")
    try:
        from rules import check_golden_rules
        from formatter import format_golden_rules
        result = check_golden_rules(config.PORTFOLIO, config.WATCHLIST)
        sender.send_long(format_golden_rules(result))
        log.info(f"✅ Golden rules: {result['verdict']}")
    except Exception as e:
        log.exception(f"Golden rules failed: {e}")


def run_weekly_rebalance_check():
    if not is_weekday(): return
    log.info("▶ Rebalance check…")
    try:
        from data_fetcher import get_portfolio_pnl
        from rebalance import get_rebalance_suggestions
        from formatter import format_rebalance_report
        pnl   = get_portfolio_pnl(config.PORTFOLIO)
        total = sum(r.get("market_value",0) for r in pnl)
        result= get_rebalance_suggestions(pnl, total)
        if result.get("health") != "HEALTHY":
            sender.send_long(format_rebalance_report(result))
    except Exception as e:
        log.exception(f"Rebalance check failed: {e}")


def run_vwap_eod_report():
    if not is_weekday(): return
    log.info("▶ VWAP EOD report…")
    try:
        from sources.vwap import get_watchlist_vwap
        from formatter import format_vwap_report
        data = get_watchlist_vwap(config.WATCHLIST)
        sender.send_long(format_vwap_report(data))
    except Exception as e:
        log.exception(f"VWAP EOD report failed: {e}")


def main():
    log.info("=" * 60)
    log.info("  HERMES AGENT v2 — STARTING UP")
    log.info("=" * 60)

    if not sender.test_connection():
        log.error("❌ Telegram connection failed. Check .env")
        return

    # Fixed-time jobs
    schedule.every().day.at("06:00").do(run_corporate_actions)
    schedule.every().day.at("06:30").do(run_macro_events)
    schedule.every().day.at(config.MORNING_BRIEF_TIME).do(run_morning_brief)
    schedule.every().day.at(config.AFTER_MARKET_TIME).do(run_52w_report)
    schedule.every().sunday.at("09:00").do(run_weekly_digest)
    schedule.every().day.at("07:45").do(run_golden_rules)
    schedule.every().monday.at("08:30").do(run_weekly_rebalance_check)
    schedule.every().day.at("15:50").do(run_vwap_eod_report)

    # Hourly market-hours jobs
    schedule.every(1).hours.do(run_bulk_block_scan)
    schedule.every(1).hours.do(run_fii_trend)
    schedule.every(1).hours.do(run_circuit_check)
    schedule.every(1).hours.do(run_breakout_scan)
    schedule.every().day.at("07:00").do(run_fundamentals_brief)
    schedule.every().day.at("07:15").do(run_global_macro_brief)

    log.info("📅 All jobs scheduled.")

    # Alert watcher thread
    watcher = AlertWatcher(
        alerts=config.PRICE_ALERTS,
        sender=sender,
        poll_seconds=config.ALERT_POLL_SECONDS,
    )
    threading.Thread(target=watcher.run, args=(is_market_open,),
                     daemon=True, name="AlertWatcher").start()
    log.info("🔔 Alert watcher armed.")

    sender.send("🟢 *Hermes Agent v2 online\\.*\n_All signal monitors armed\\._",
                parse_mode="MarkdownV2")

    while True:
        schedule.run_pending()
        time.sleep(1)


sender = TelegramSender(
    token=config.TELEGRAM_BOT_TOKEN,
    chat_id=config.TELEGRAM_CHAT_ID,
)

if __name__ == "__main__":
    main()
