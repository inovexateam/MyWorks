"""
Hermes — Signal Engine
Combines all data sources into a unified, prioritised signal list.
Each signal has: symbol, type, severity, summary, timeframe (TODAY/1W/1M).
"""

import logging
from datetime import date

log = logging.getLogger("hermes.signals")


SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _sig(symbol: str, sig_type: str, severity: str,
         summary: str, timeframe: str, data: dict = None) -> dict:
    return {
        "symbol":    symbol,
        "type":      sig_type,
        "severity":  severity,
        "summary":   summary,
        "timeframe": timeframe,  # TODAY | 1W | 1M
        "data":      data or {},
        "date":      str(date.today()),
    }


# ── Individual signal builders ────────────────────────────────────────────────

def signals_from_bulk_deals(deals: list) -> list:
    sigs = []
    for d in deals:
        action = d.get("buy_sell", "").upper()
        val    = d.get("value_cr", 0)
        sev    = "HIGH" if val >= 10 else "MEDIUM"
        emoji  = "🟢" if "BUY" in action else "🔴"
        sigs.append(_sig(
            symbol    = d["symbol"],
            sig_type  = f"{d['type']}_DEAL",
            severity  = sev,
            summary   = f"{emoji} {d['type']} deal — {d['client']} {action} ₹{val:.1f}Cr @ ₹{d['price']:,.2f}",
            timeframe = "TODAY",
            data      = d,
        ))
    return sigs


def signals_from_oi(oi: dict) -> list:
    if not oi:
        return []
    sigs = []
    sentiment = oi.get("sentiment", "NEUTRAL")
    pcr       = oi.get("pcr", 1.0)
    sym       = oi.get("symbol", "")

    if sentiment != "NEUTRAL":
        emoji = "📈" if sentiment == "BULLISH" else "📉"
        sev   = "HIGH" if abs(pcr - 1.0) > 0.4 else "MEDIUM"
        sigs.append(_sig(
            symbol    = sym,
            sig_type  = "OI_SENTIMENT",
            severity  = sev,
            summary   = (f"{emoji} Options chain {sentiment} — PCR {pcr:.2f} "
                         f"· Support ₹{oi['support']:,} · Resistance ₹{oi['resistance']:,}"),
            timeframe = "1W",
            data      = oi,
        ))
    return sigs


def signals_from_corporate_actions(actions: list) -> list:
    sigs = []
    for a in actions:
        if a["category"] == "DIVIDEND":
            sev = "HIGH" if a["days_out"] <= 5 else "MEDIUM"
            sigs.append(_sig(
                symbol    = a["symbol"],
                sig_type  = "DIVIDEND",
                severity  = sev,
                summary   = f"💰 Dividend ex-date in {a['days_out']}d ({a['ex_date']}) — {a['action']}",
                timeframe = "1W" if a["days_out"] <= 7 else "1M",
                data      = a,
            ))
        elif a["category"] == "BONUS":
            sigs.append(_sig(
                symbol    = a["symbol"],
                sig_type  = "BONUS",
                severity  = "MEDIUM",
                summary   = f"🎁 Bonus issue in {a['days_out']}d ({a['ex_date']}) — {a['action']}",
                timeframe = "1W" if a["days_out"] <= 7 else "1M",
                data      = a,
            ))
        elif a["category"] == "SPLIT":
            sigs.append(_sig(
                symbol    = a["symbol"],
                sig_type  = "SPLIT",
                severity  = "MEDIUM",
                summary   = f"✂️ Stock split in {a['days_out']}d ({a['ex_date']}) — {a['action']}",
                timeframe = "1W" if a["days_out"] <= 7 else "1M",
                data      = a,
            ))
    return sigs


def signals_from_promoter(activity: list) -> list:
    sigs = []
    for a in activity:
        action = a.get("action", "")
        emoji  = "🟢" if action == "BUY" else "🔴"
        sev    = "HIGH" if action == "BUY" else "MEDIUM"
        sigs.append(_sig(
            symbol    = a["symbol"],
            sig_type  = "PROMOTER_ACTIVITY",
            severity  = sev,
            summary   = f"{emoji} Promoter {action} — {a['person']} · Qty: {a['qty']:,}",
            timeframe = "1W",
            data      = a,
        ))
    return sigs


def signals_from_macro_events(events: list, watchlist: list) -> list:
    sigs = []
    for ev in events:
        impact = ev.get("impact", "MEDIUM")
        sev    = "CRITICAL" if impact == "HIGH" and ev["days_out"] <= 2 else \
                 "HIGH"     if impact == "HIGH" else "MEDIUM"
        emoji  = "🚨" if sev == "CRITICAL" else "⚠️"
        # Tag all watchlist stocks for macro events
        for sym in watchlist:
            sigs.append(_sig(
                symbol    = sym.replace(".NS", ""),
                sig_type  = "MACRO_EVENT",
                severity  = sev,
                summary   = f"{emoji} {ev['event']} in {ev['days_out']}d ({ev['date']}) — market-wide impact",
                timeframe = "TODAY" if ev["days_out"] == 0 else \
                            "1W"    if ev["days_out"] <= 7 else "1M",
                data      = ev,
            ))
    # Deduplicate macro events (one per event, not per stock)
    seen = set()
    unique = []
    for s in sigs:
        key = s["summary"]
        if key not in seen:
            seen.add(key)
            s["symbol"] = "MARKET"
            unique.append(s)
    return unique


def signals_from_macro_news(news: list) -> list:
    sigs = []
    for n in news[:5]:   # top 5 high-impact only
        affected = n.get("affected_stocks", [])
        symbols  = [s.replace(".NS", "") for s in affected] if affected else ["MARKET"]
        for sym in symbols:
            sigs.append(_sig(
                symbol    = sym,
                sig_type  = "NEWS",
                severity  = "HIGH" if n["impact_score"] >= 3 else "MEDIUM",
                summary   = f"📰 [{n['source']}] {n['title'][:80]}",
                timeframe = "TODAY",
                data      = {"link": n.get("link", ""), "score": n["impact_score"]},
            ))
    return sigs


def signals_from_fii_trend(trend: list) -> list:
    """Detect sustained FII buying or selling (3+ consecutive days)."""
    sigs = []
    if len(trend) < 3:
        return sigs

    fii_rows = [r for r in trend if r["category"] == "FII/FPI"][:5]
    if len(fii_rows) < 3:
        return sigs

    nets       = [r["net"] for r in fii_rows[:3]]
    all_buy    = all(n > 0 for n in nets)
    all_sell   = all(n < 0 for n in nets)
    total_net  = sum(nets)

    if all_buy:
        sigs.append(_sig(
            symbol    = "MARKET",
            sig_type  = "FII_TREND",
            severity  = "HIGH",
            summary   = f"🟢 FII buying for 3+ consecutive days — net ₹{total_net/1e7:.1f}Cr bullish signal",
            timeframe = "1W",
        ))
    elif all_sell:
        sigs.append(_sig(
            symbol    = "MARKET",
            sig_type  = "FII_TREND",
            severity  = "HIGH",
            summary   = f"🔴 FII selling for 3+ consecutive days — net ₹{abs(total_net)/1e7:.1f}Cr bearish signal",
            timeframe = "1W",
        ))
    return sigs


def signals_from_circuit(circuit_stocks: list) -> list:
    sigs = []
    for s in circuit_stocks:
        emoji = "🚀" if s["circuit"] == "UPPER" else "💥"
        sigs.append(_sig(
            symbol    = s["symbol"],
            sig_type  = "CIRCUIT",
            severity  = "CRITICAL",
            summary   = f"{emoji} {s['symbol']} hit {s['circuit']} CIRCUIT — {s['change_pct']:+.1f}% @ ₹{s['price']:,.2f}",
            timeframe = "TODAY",
            data      = s,
        ))
    return sigs


# ── Master signal collector ───────────────────────────────────────────────────

def collect_all_signals(watchlist: list) -> list:
    """
    Pull all sources and return a unified, deduplicated, sorted signal list.
    Sorted: CRITICAL → HIGH → MEDIUM → LOW, then TODAY → 1W → 1M.
    """
    from sources.nse   import (get_bulk_deals, get_block_deals, get_oi_analysis,
                                get_circuit_stocks, get_fii_dii_trend, get_promoter_activity)
    from sources.bse   import get_corporate_actions
    from sources.macro import (get_upcoming_macro_events, get_high_impact_news)

    all_signals = []

    log.info("Collecting signals — bulk/block deals…")
    try:
        bulk  = get_bulk_deals(watchlist)
        block = get_block_deals(watchlist)
        all_signals += signals_from_bulk_deals(bulk + block)
    except Exception as e:
        log.warning(f"Bulk/block signals failed: {e}")

    log.info("Collecting signals — OI analysis…")
    for sym in watchlist:
        try:
            oi = get_oi_analysis(sym)
            all_signals += signals_from_oi(oi)
        except Exception as e:
            log.debug(f"OI signal skipped for {sym}: {e}")

    log.info("Collecting signals — circuit breakers…")
    try:
        circuits = get_circuit_stocks(watchlist)
        all_signals += signals_from_circuit(circuits)
    except Exception as e:
        log.warning(f"Circuit signals failed: {e}")

    log.info("Collecting signals — corporate actions…")
    try:
        actions = get_corporate_actions(watchlist, days_ahead=30)
        all_signals += signals_from_corporate_actions(actions)
    except Exception as e:
        log.warning(f"Corporate action signals failed: {e}")

    log.info("Collecting signals — promoter activity…")
    try:
        promo = get_promoter_activity(watchlist)
        all_signals += signals_from_promoter(promo)
    except Exception as e:
        log.warning(f"Promoter signals failed: {e}")

    log.info("Collecting signals — macro events…")
    try:
        events = get_upcoming_macro_events(days_ahead=30)
        all_signals += signals_from_macro_events(events, watchlist)
    except Exception as e:
        log.warning(f"Macro event signals failed: {e}")

    log.info("Collecting signals — macro news…")
    try:
        news = get_high_impact_news(watchlist)
        all_signals += signals_from_macro_news(news)
    except Exception as e:
        log.warning(f"Macro news signals failed: {e}")

    log.info("Collecting signals — FII trend…")
    try:
        trend = get_fii_dii_trend()
        all_signals += signals_from_fii_trend(trend)
    except Exception as e:
        log.warning(f"FII trend signals failed: {e}")

    # Sort: severity first, then timeframe
    tf_order = {"TODAY": 0, "1W": 1, "1M": 2}
    all_signals.sort(key=lambda s: (
        SEVERITY_ORDER.get(s["severity"], 9),
        tf_order.get(s["timeframe"], 9),
    ))

    log.info(f"Signal collection complete — {len(all_signals)} signals.")
    return all_signals


def filter_by_timeframe(signals: list, timeframe: str) -> list:
    return [s for s in signals if s["timeframe"] == timeframe]


def filter_by_symbol(signals: list, symbol: str) -> list:
    sym = symbol.replace(".NS", "").upper()
    return [s for s in signals if s["symbol"] == sym or s["symbol"] == "MARKET"]