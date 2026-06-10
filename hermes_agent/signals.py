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

    log.info("Collecting signals — technical analysis…")
    try:
        from sources.technicals import analyze_watchlist
        ta_results = analyze_watchlist(watchlist)
        all_signals += signals_from_ta(ta_results)
    except Exception as e:
        log.warning(f"TA signals failed: {e}")

    log.info("Collecting signals — sector rotation…")
    try:
        from sources.sector import get_sector_performance, get_rotation_signals
        sector_data = get_sector_performance()
        for sig in get_rotation_signals(sector_data, watchlist):
            sev = "HIGH" if abs(sig["pct"]) > 2 else "MEDIUM"
            all_signals.append(_sig(
                sig.get("symbol","MARKET"), "SECTOR_ROTATION", sev,
                sig["message"], "TODAY", sig))
    except Exception as e:
        log.warning(f"Sector signals failed: {e}")

    log.info("Collecting signals — VIX/sentiment…")
    try:
        from sources.vix import get_full_sentiment
        sent = get_full_sentiment()
        vix  = sent.get("vix",{})
        v    = vix.get("vix",0)
        if v > 20:
            sev = "CRITICAL" if v > 25 else "HIGH"
            all_signals.append(_sig(
                "MARKET","VIX_ALERT", sev,
                f"🌡️ India VIX at {v:.1f} — {vix.get('level','')} — {vix.get('meaning','')}",
                "TODAY", sent))
        pcr = sent.get("pcr",{})
        p   = pcr.get("pcr",1.0)
        if p > 1.3 or p < 0.7:
            sev = "HIGH" if (p > 1.5 or p < 0.6) else "MEDIUM"
            all_signals.append(_sig(
                "MARKET","PCR_EXTREME", sev,
                f"📊 Market PCR at {p:.2f} — {pcr.get('level','')} — {pcr.get('meaning','')}",
                "TODAY", sent))
    except Exception as e:
        log.warning(f"VIX signals failed: {e}")

    log.info("Collecting signals — promoter/shareholding…")
    try:
        from sources.promoter import get_watchlist_shareholding, get_pledge_alerts
        sh_data = get_watchlist_shareholding(watchlist)
        for a in get_pledge_alerts(sh_data):
            sev = a.get("severity","MEDIUM")
            all_signals.append(_sig(
                a["symbol"], a["type"], sev,
                f"🏛️ {a['message']} — {a['action']}", "1M", a))
    except Exception as e:
        log.warning(f"Promoter signals failed: {e}")

    log.info("Collecting signals — unusual options…")
    try:
        from sources.options import scan_unusual_activity
        options_data = scan_unusual_activity(watchlist)
        for r in options_data:
            sym = r["symbol"]
            for u in r.get("unusual",[]):
                bet = "RISE above" if u["type"]=="CALL_BUILDUP" else "FALL below"
                all_signals.append(_sig(
                    sym, "UNUSUAL_OPTIONS", "HIGH",
                    f"🎯 Large options bet: {sym} will {bet} ₹{u['strike']:,} — {u['meaning']}",
                    "1W", u))
            if r.get("iv_spike"):
                all_signals.append(_sig(
                    sym, "IV_SPIKE", "MEDIUM",
                    f"📈 IV spike on {sym} — big move expected before {r['expiry']}",
                    "TODAY", r))
    except Exception as e:
        log.warning(f"Options signals failed: {e}")

    log.info("Collecting signals — fundamentals…")
    try:
        from sources.fundamentals import get_watchlist_fundamentals, get_fundamental_signals
        fund_data = get_watchlist_fundamentals(watchlist)
        for s in get_fundamental_signals(fund_data):
            all_signals.append(s)
    except Exception as e:
        log.warning(f"Fundamental signals failed: {e}")

    log.info("Collecting signals — global macro…")
    try:
        from sources.global_macro import get_global_macro, get_global_macro_signals
        macro = get_global_macro()
        all_signals += get_global_macro_signals(macro)
    except Exception as e:
        log.warning(f"Global macro signals failed: {e}")

    log.info("Collecting signals — breakout scanner…")
    try:
        from sources.breakout import full_breakout_scan
        scan = full_breakout_scan(watchlist)
        for r in scan.get("breakouts", []):
            all_signals.append(_sig(
                r["symbol"], "BREAKOUT", r["severity"],
                f"🚀 BREAKOUT: {r['symbol']} at 52W high ₹{r['high52']:,.2f} — {r['meaning']}",
                "TODAY", r))
        for r in scan.get("accumulation", []):
            all_signals.append(_sig(
                r["symbol"], "ACCUMULATION", r["severity"],
                f"📦 ACCUMULATION: {r['symbol']} — {r['meaning']}",
                "1W", r))
        for r in scan.get("consolidation", []):
            all_signals.append(_sig(
                r["symbol"], "CONSOLIDATION", "MEDIUM",
                f"🔔 COILING: {r['symbol']} — {r['meaning']}",
                "1W", r))
        top_rs = [r for r in scan.get("rel_strength",[]) if r["rs"] > 115]
        for r in top_rs[:3]:
            all_signals.append(_sig(
                r["symbol"], "REL_STRENGTH", "MEDIUM",
                f"💪 {r['symbol']} outperforming Nifty by {r['rs']-100:.1f}% — relative strength signal",
                "1W", r))
    except Exception as e:
        log.warning(f"Breakout signals failed: {e}")

    log.info("Collecting signals — news sentiment…")
    try:
        from sources.sentiment_nlp import analyze_news_sentiment
        sent_data = analyze_news_sentiment(watchlist)
        for s in sent_data:
            if s.get("flip_alert"):
                flip = s["sentiment_flip"]
                sev  = "HIGH" if "NEGATIVE" in flip else "MEDIUM"
                emoji = "🔴" if "NEGATIVE" in flip else "🟢"
                all_signals.append(_sig(
                    s["symbol"], "SENTIMENT_FLIP", sev,
                    f"{emoji} News sentiment flipped {flip.replace('_',' ')} for {s['symbol']}",
                    "TODAY", s))
            elif s["today_score"] <= -1:
                all_signals.append(_sig(
                    s["symbol"], "NEGATIVE_NEWS", "MEDIUM",
                    f"📰 Negative news trend for {s['symbol']} — score {s['today_score']}",
                    "TODAY", s))
    except Exception as e:
        log.warning(f"Sentiment signals failed: {e}")

    log.info("Collecting signals — insider trades…")
    try:
        from sources.insider import get_insider_trades
        insider = get_insider_trades(watchlist)
        for t in insider:
            if t["is_key_person"] and t["is_open_market"] and t["action"]=="BUY":
                all_signals.append(_sig(
                    t["symbol"], "INSIDER_BUY", "HIGH",
                    f"🏛️ INSIDER BUY: {t['person'][:25]} bought {t['qty']:,} shares open market — {t['meaning']}",
                    "1W", t))
            elif t["is_key_person"] and t["action"]=="SELL":
                all_signals.append(_sig(
                    t["symbol"], "INSIDER_SELL", "MEDIUM",
                    f"🏛️ INSIDER SELL: {t['person'][:25]} sold {t['qty']:,} shares",
                    "1W", t))
    except Exception as e:
        log.warning(f"Options signals failed: {e}")

    # Sort: severity first, then timeframe
    tf_order = {"TODAY": 0, "1W": 1, "1M": 2}
    all_signals.sort(key=lambda s: (
        SEVERITY_ORDER.get(s["severity"], 9),
        tf_order.get(s["timeframe"], 9),
    ))

    log.info(f"Signal collection complete — {len(all_signals)} signals.")
    return all_signals


def signals_from_ta(ta_results: list) -> list:
    sigs = []
    for r in ta_results:
        sym   = r["symbol"]
        score = r.get("ta_score", 0)
        sig   = r.get("ta_signal", "NEUTRAL")
        rsi   = r.get("rsi")
        macd_cross = r.get("macd_cross", "NONE")
        ma_cross   = r.get("ma_cross",   "NONE")
        vol_sig    = r.get("volume_signal", "NORMAL")
        bb_sig     = r.get("bb_signal",   "INSIDE")

        # Strong buy/sell
        if sig in ("STRONG BUY", "BUY"):
            sev = "HIGH" if sig == "STRONG BUY" else "MEDIUM"
            details = []
            if rsi and rsi < 35:          details.append(f"RSI {rsi:.0f} oversold")
            if macd_cross == "BULLISH":   details.append("MACD bullish cross")
            if ma_cross   == "GOLDEN":    details.append("Golden cross ✨")
            if vol_sig    == "SPIKE":     details.append("Volume spike")
            if bb_sig     == "NEAR_LOWER":details.append("Near BB lower")
            detail_str = " · ".join(details) if details else f"TA score {score}"
            sigs.append(_sig(sym, "TA_BUY", sev,
                f"📈 {sig} — {detail_str}", "TODAY", r))

        elif sig in ("STRONG SELL", "SELL"):
            sev = "HIGH" if sig == "STRONG SELL" else "MEDIUM"
            details = []
            if rsi and rsi > 68:          details.append(f"RSI {rsi:.0f} overbought")
            if macd_cross == "BEARISH":   details.append("MACD bearish cross")
            if ma_cross   == "DEATH":     details.append("Death cross ☠️")
            if bb_sig     == "NEAR_UPPER":details.append("Near BB upper")
            detail_str = " · ".join(details) if details else f"TA score {score}"
            sigs.append(_sig(sym, "TA_SELL", sev,
                f"📉 {sig} — {detail_str}", "TODAY", r))

        # Specific events regardless of overall signal
        if ma_cross == "GOLDEN":
            sigs.append(_sig(sym, "GOLDEN_CROSS", "HIGH",
                f"✨ Golden Cross — 50MA crossed above 200MA (strong uptrend signal)", "1W", r))
        elif ma_cross == "DEATH":
            sigs.append(_sig(sym, "DEATH_CROSS", "HIGH",
                f"☠️ Death Cross — 50MA crossed below 200MA (bearish trend change)", "1W", r))

        if macd_cross in ("BULLISH", "BEARISH"):
            emoji = "📈" if macd_cross == "BULLISH" else "📉"
            sigs.append(_sig(sym, f"MACD_{macd_cross}", "MEDIUM",
                f"{emoji} MACD {macd_cross} crossover — momentum shift", "TODAY", r))

        if bb_sig == "SQUEEZE":
            sigs.append(_sig(sym, "BB_SQUEEZE", "MEDIUM",
                f"🔔 Bollinger Band SQUEEZE — low volatility, big move imminent (width {r.get('bb_width',0):.1f}%)",
                "1W", r))

        if vol_sig == "SPIKE":
            sigs.append(_sig(sym, "VOLUME_SPIKE", "MEDIUM",
                f"📊 Volume SPIKE — {r.get('volume_ratio',0):.1f}x avg volume · something is moving",
                "TODAY", r))

    return sigs


def filter_by_timeframe(signals: list, timeframe: str) -> list:
    return [s for s in signals if s["timeframe"] == timeframe]


def filter_by_symbol(signals: list, symbol: str) -> list:
    sym = symbol.replace(".NS", "").upper()
    return [s for s in signals if s["symbol"] == sym or s["symbol"] == "MARKET"]
