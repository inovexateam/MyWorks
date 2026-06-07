"""
Hermes Agent — Telegram Message Formatter
Builds all four Hermes message types using Telegram MarkdownV2.
"""

from datetime import datetime


# ── Helpers ──────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def _arrow(val: float) -> str:
    return "📈" if val >= 0 else "📉"


def _sign(val: float) -> str:
    return f"+{val:,.2f}" if val >= 0 else f"{val:,.2f}"


def _inr(val: float) -> str:
    """Format as ₹ with Indian lakh/crore grouping."""
    if abs(val) >= 1_00_00_000:
        return f"₹{val/1_00_00_000:.2f} Cr"
    if abs(val) >= 1_00_000:
        return f"₹{val/1_00_000:.2f} L"
    return f"₹{val:,.2f}"


def _pct_bar(position_pct: float, width: int = 10) -> str:
    """Visual bar: ░░░█░░░░░░ showing where price sits in 52W range."""
    filled = round(position_pct / 100 * width)
    filled = max(0, min(width, filled))
    return "▓" * filled + "░" * (width - filled)


# ── 1. Morning Brief ─────────────────────────────────────────────────────────

def format_morning_brief(
    indices: dict,
    portfolio_rows: list,
    fii_dii: dict,
    news: list,
    earnings_soon: list,
) -> str:
    now = datetime.now().strftime("%d %b %Y · %H:%M IST")
    lines = []

    # Header
    lines += [
        "🌅 *HERMES MORNING BRIEF*",
        f"_{_esc(now)}_",
        "",
    ]

    # Indices
    lines.append("*📊 MARKETS*")
    for name, d in indices.items():
        arrow = "📈" if d["pct"] >= 0 else "📉"
        sign  = "+" if d["pct"] >= 0 else ""
        lines.append(
            f"{arrow} *{_esc(name)}* `{d['price']:,.2f}` "
            f"\\({_esc(sign + str(d['pct']))}%\\)"
        )
    lines.append("")

    # FII / DII
    fii_net = fii_dii.get("fii_net", 0)
    dii_net = fii_dii.get("dii_net", 0)
    fii_arrow = "🟢" if fii_net >= 0 else "🔴"
    dii_arrow = "🟢" if dii_net >= 0 else "🟡"
    lines += [
        "*🏦 FII / DII FLOW*",
        f"{fii_arrow} FII Net: *{_esc(_inr(fii_net))}*  "
        f"\\(Buy {_esc(_inr(fii_dii.get('fii_buy',0)))} · Sell {_esc(_inr(fii_dii.get('fii_sell',0)))}\\)",
        f"{dii_arrow} DII Net: *{_esc(_inr(dii_net))}*  "
        f"\\(Buy {_esc(_inr(fii_dii.get('dii_buy',0)))} · Sell {_esc(_inr(fii_dii.get('dii_sell',0)))}\\)",
        "",
    ]

    # Portfolio P&L
    total_day_pnl   = sum(r.get("day_pnl", 0)   for r in portfolio_rows)
    total_total_pnl = sum(r.get("total_pnl", 0) for r in portfolio_rows)
    total_value     = sum(r.get("market_value", 0) for r in portfolio_rows)

    day_emoji   = "🟢" if total_day_pnl   >= 0 else "🔴"
    total_emoji = "🟢" if total_total_pnl >= 0 else "🔴"

    lines += [
        "*💼 PORTFOLIO SNAPSHOT*",
        f"Portfolio Value: `{_esc(_inr(total_value))}`",
        f"{day_emoji} Day P&L: *{_esc(_inr(total_day_pnl))}*",
        f"{total_emoji} Overall P&L: *{_esc(_inr(total_total_pnl))}*",
        "",
    ]
    for r in portfolio_rows:
        e  = "▲" if r.get("pct", 0) >= 0 else "▼"
        dp = "🟢" if r.get("day_pnl", 0) >= 0 else "🔴"
        sym_clean = r["symbol"].replace(".NS", "")
        lines.append(
            f"{dp} *{_esc(sym_clean)}* `{r['price']:,.2f}` {_esc(e + str(abs(r['pct'])) + '%')} "
            f"· Day: {_esc(_inr(r['day_pnl']))} · Total: {_esc(_inr(r['total_pnl']))}"
        )
    lines.append("")

    # News
    if news:
        lines.append("*📰 STOCK NEWS*")
        for n in news[:6]:
            sym_clean = n["symbol"].replace(".NS", "")
            age = f"{n['age_hours']:.0f}h ago"
            lines.append(
                f"• \\[{_esc(sym_clean)}\\] {_esc(n['title'][:80])}… "
                f"_{_esc(age)}_"
            )
        lines.append("")

    # Earnings reminders
    if earnings_soon:
        lines.append("*⚠️ EARNINGS THIS WEEK*")
        for e in earnings_soon:
            sym_clean = e["symbol"].replace(".NS", "")
            lines.append(
                f"🗓 *{_esc(sym_clean)}* reports in *{e['days_out']}d* "
                f"\\({_esc(str(e['date']))}\\)"
            )
        lines.append("")

    lines.append("_— Hermes Agent · Free · Open Source_")
    return "\n".join(lines)


# ── 2. Price Alert ───────────────────────────────────────────────────────────

def format_price_alert(
    symbol: str,
    condition: str,
    level: float,
    current_price: float,
) -> str:
    sym_clean = symbol.replace(".NS", "")
    direction = "CROSSED ABOVE 🚀" if condition == "above" else "DROPPED BELOW 🔻"
    now = datetime.now().strftime("%H:%M:%S IST")
    return (
        f"🔔 *HERMES PRICE ALERT*\n\n"
        f"*{_esc(sym_clean)}* has {_esc(direction)}\n\n"
        f"📍 Alert Level: `{_esc(f'{level:,.2f}')}`\n"
        f"💹 Current Price: `{_esc(f'{current_price:,.2f}')}`\n\n"
        f"_{_esc(now)}_\n"
        f"_— Hermes Agent_"
    )


# ── 3. After-Market 52W Report ───────────────────────────────────────────────

def format_52w_report(analysis: list) -> str:
    now = datetime.now().strftime("%d %b %Y · %H:%M IST")
    lines = [
        "📐 *HERMES 52\\-WEEK RANGE REPORT*",
        f"_{_esc(now)}_",
        "",
    ]

    danger_stocks = [s for s in analysis if s["danger"]]
    safe_stocks   = [s for s in analysis if not s["danger"]]

    if danger_stocks:
        lines.append("*⚠️  DANGER ZONE \\(within 8% of 52W Low\\)*")
        for s in danger_stocks:
            sym_clean = s["symbol"].replace(".NS", "")
            bar = _pct_bar(s["position_pct"])
            lines += [
                f"🔴 *{_esc(sym_clean)}*",
                f"   Price: `{s['price']:,.2f}` · Low: `{s['week52l']:,.2f}` · High: `{s['week52h']:,.2f}`",
                f"   `{_esc(bar)}` {_esc(str(s['position_pct']))}% in range",
                f"   Only *{_esc(str(s['pct_from_low']))}% above 52W low* \\— review position\\!",
                "",
            ]

    if safe_stocks:
        lines.append("*📊 YOUR WATCHLIST*")
        for s in safe_stocks:
            sym_clean = s["symbol"].replace(".NS", "")
            bar = _pct_bar(s["position_pct"])
            emoji = "🟢" if s["pct_from_low"] > 30 else "🟡"
            lines += [
                f"{emoji} *{_esc(sym_clean)}* `{s['price']:,.2f}`",
                f"   `{_esc(bar)}` {_esc(str(s['position_pct']))}% in range",
                f"   ↑ {_esc(str(s['pct_from_high']))}% from 52W High · ↓ {_esc(str(s['pct_from_low']))}% from 52W Low",
            ]

    lines.append("\n_— Hermes Agent · End of Day_")
    return "\n".join(lines)


# ── 4. Earnings Calendar Update ─────────────────────────────────────────────

def format_earnings_reminder(earnings: list, upcoming_days: int = 14) -> str:
    now = datetime.now().strftime("%d %b %Y")
    lines = [
        "🗓 *HERMES EARNINGS CALENDAR*",
        f"_{_esc(now)}_",
        "",
    ]

    if not earnings:
        lines.append("_No upcoming earnings found for your watchlist\\._")
    else:
        for e in earnings:
            sym_clean = e["symbol"].replace(".NS", "")
            if e["days_out"] == 0:
                tag = "🔴 TODAY"
            elif e["days_out"] <= 3:
                tag = f"🟠 {e['days_out']}d \\— GET READY"
            elif e["days_out"] <= 7:
                tag = f"🟡 {e['days_out']}d"
            else:
                tag = f"🟢 {e['days_out']}d"
            lines.append(
                f"{tag} · *{_esc(sym_clean)}* · {_esc(str(e['date']))}"
            )

    lines.append("\n_— Hermes Agent_")
    return "\n".join(lines)


# ── 5. Signal Digest (TODAY / 1W / 1M) ──────────────────────────────────────

def format_signal_digest(signals: list, timeframe: str = "TODAY") -> str:
    now = datetime.now().strftime("%d %b %Y · %H:%M IST")
    tf_label = {"TODAY": "TODAY'S SIGNALS", "1W": "1\\-WEEK OUTLOOK", "1M": "1\\-MONTH OUTLOOK"}
    tf_sigs  = [s for s in signals if s["timeframe"] == timeframe]

    lines = [
        f"🧠 *HERMES SIGNAL DIGEST — {_esc(tf_label.get(timeframe, timeframe))}*",
        f"_{_esc(now)}_",
        "",
    ]

    if not tf_sigs:
        lines.append("_No significant signals detected\\._")
        lines.append("\n_— Hermes Agent_")
        return "\n".join(lines)

    # Group by severity
    for sev in ("CRITICAL", "HIGH", "MEDIUM"):
        sev_sigs = [s for s in tf_sigs if s["severity"] == sev]
        if not sev_sigs:
            continue
        emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "ℹ️"}.get(sev, "•")
        lines.append(f"*{emoji} {_esc(sev)}*")
        for s in sev_sigs:
            sym = s["symbol"]
            lines.append(f"• \\[*{_esc(sym)}*\\] {_esc(s['summary'])}")
        lines.append("")

    lines.append("_— Hermes Agent_")
    return "\n".join(lines)


# ── 6. Corporate Action Alert ────────────────────────────────────────────────

def format_corporate_action_alert(action: dict) -> str:
    sym   = _esc(action["symbol"])
    cat   = action["category"]
    emoji = {"DIVIDEND": "💰", "BONUS": "🎁", "SPLIT": "✂️",
              "RIGHTS": "📋", "MEETING": "🏛", "OTHER": "📌"}.get(cat, "📌")
    days  = action["days_out"]
    urgency = "TODAY" if days == 0 else f"in {days}d"

    return (
        f"{emoji} *HERMES CORPORATE ACTION ALERT*\n\n"
        f"*{sym}* — *{_esc(cat)}*\n"
        f"📅 Ex\\-Date: `{_esc(action['ex_date'])}` \\({_esc(urgency)}\\)\n"
        f"📋 Details: {_esc(action['action'])}\n\n"
        f"_{_esc(datetime.now().strftime('%H:%M IST'))}_\n"
        f"_— Hermes Agent_"
    )


# ── 7. Macro Event Alert ─────────────────────────────────────────────────────

def format_macro_alert(event: dict, crude: dict = None, inr: dict = None) -> str:
    days = event["days_out"]
    urgency = "🚨 TODAY" if days == 0 else f"⚠️ in {days}d"

    lines = [
        f"🌐 *HERMES MACRO ALERT*",
        "",
        f"*{_esc(event['event'])}*",
        f"{_esc(urgency)} · {_esc(event['date'])}",
        f"Impact: *{_esc(event['impact'])}*",
        "",
    ]

    if crude and crude.get("price"):
        arrow = "📈" if crude["pct"] >= 0 else "📉"
        crude_pct = f"{crude['pct']:+.2f}"
        lines.append(f"{arrow} Brent Crude: `${crude['price']:.2f}` "
                     f"\\({_esc(crude_pct)}%\\)")

    if inr and inr.get("rate"):
        arrow = "📉" if inr["pct"] >= 0 else "📈"
        inr_pct = f"{inr['pct']:+.4f}"
        lines.append(f"{arrow} INR\\/USD: `₹{inr['rate']:.2f}` "
                     f"\\({_esc(inr_pct)}\\)")

    lines.append(f"\n_{_esc(datetime.now().strftime('%H:%M IST'))}_")
    lines.append("_— Hermes Agent_")
    return "\n".join(lines)


# ── 8. Bulk/Block Deal Alert ─────────────────────────────────────────────────

def format_deal_alert(deal: dict) -> str:
    action = deal.get("buy_sell", "").upper()
    emoji  = "🟢" if "BUY" in action else "🔴"
    sym    = _esc(deal["symbol"])
    now    = datetime.now().strftime("%H:%M:%S IST")

    return (
        f"{emoji} *HERMES {_esc(deal['type'])} DEAL ALERT*\n\n"
        f"*{sym}* — {_esc(action)}\n"
        f"👤 Client: {_esc(deal['client'])}\n"
        f"📊 Qty: `{deal['qty']:,}` shares\n"
        f"💰 Value: `₹{deal['value_cr']:.2f} Cr` @ `₹{deal['price']:,.2f}`\n\n"
        f"_{_esc(now)}_\n"
        f"_— Hermes Agent_"
    )


# ── 9. FII Trend Alert ───────────────────────────────────────────────────────

def format_fii_trend_alert(signal: dict) -> str:
    return (
        f"🏦 *HERMES FII TREND ALERT*\n\n"
        f"{_esc(signal['summary'])}\n\n"
        f"_Sustained flow = smart money conviction\\. Review positions\\._\n"
        f"_{_esc(datetime.now().strftime('%H:%M IST'))}_\n"
        f"_— Hermes Agent_"
    )


# ── 10. Morning Brief — extended with signals ────────────────────────────────

def format_morning_brief_extended(
    indices: dict,
    portfolio_rows: list,
    fii_dii: dict,
    news: list,
    earnings_soon: list,
    signals_today: list,
    crude: dict = None,
    inr: dict   = None,
    global_mkts: list = None,
    macro_events: list = None,
) -> str:
    """Extended morning brief that includes signals, macro, global markets."""
    from formatter import format_morning_brief
    # Build base brief first
    base = format_morning_brief(indices, portfolio_rows, fii_dii, news, earnings_soon)

    extra = []

    # Global markets
    if global_mkts:
        extra.append("*🌍 GLOBAL MARKETS*")
        for g in global_mkts[:4]:
            arrow   = "📈" if g["pct"] >= 0 else "📉"
            g_pct   = f"{g['pct']:+.2f}"
            extra.append(
                f"{arrow} *{_esc(g['name'])}* `{g['price']:,.2f}` "
                f"\\({_esc(g_pct)}%\\)"
            )
        extra.append("")

    # Macro
    if crude and crude.get("price"):
        arrow     = "📈" if crude["pct"] >= 0 else "📉"
        crude_pct = f"{crude['pct']:+.2f}"
        extra.append(
            f"{arrow} *Brent Crude*: `${crude['price']:.2f}` "
            f"\\({_esc(crude_pct)}%\\)"
        )
    if inr and inr.get("rate"):
        arrow   = "📉" if inr["pct"] >= 0 else "📈"
        inr_pct = f"{inr['pct']:+.4f}"
        extra.append(
            f"{arrow} *INR\\/USD*: `₹{inr['rate']:.2f}` "
            f"\\({_esc(inr_pct)}\\)"
        )
    if crude or inr:
        extra.append("")

    # Macro events this week
    if macro_events:
        extra.append("*📅 MACRO EVENTS THIS WEEK*")
        for ev in macro_events[:3]:
            urgency = "🚨" if ev["urgent"] else "📌"
            extra.append(
                f"{urgency} {_esc(ev['event'])} — {_esc(str(ev['days_out']))}d "
                f"\\({_esc(ev['date'])}\\)"
            )
        extra.append("")

    # Today's top signals
    critical = [s for s in signals_today if s["severity"] in ("CRITICAL", "HIGH")]
    if critical:
        extra.append("*🧠 TODAY'S KEY SIGNALS*")
        for s in critical[:5]:
            extra.append(f"• {_esc(s['summary'])}")
        extra.append("")

    if not extra:
        return base

    # Insert extra block before the footer
    footer = "_— Hermes Agent · Free · Open Source_"
    return base.replace(footer, "\n".join(extra) + "\n" + footer)


# ── 11. Technical Snapshot ───────────────────────────────────────────────────

def format_ta_snapshot(ta_result: dict) -> str:
    sym   = _esc(ta_result["symbol"].replace(".NS", ""))
    price = ta_result.get("price", 0)
    sig   = ta_result.get("ta_signal", "NEUTRAL")
    score = ta_result.get("ta_score",  0)

    sig_emoji = {"STRONG BUY": "🚀", "BUY": "📈", "STRONG SELL": "🔻",
                 "SELL": "📉", "NEUTRAL": "➡️"}.get(sig, "➡️")

    rsi  = ta_result.get("rsi")
    ma50 = ta_result.get("ma50")
    ma200= ta_result.get("ma200")
    macd_cross = ta_result.get("macd_cross", "NONE")
    ma_cross   = ta_result.get("ma_cross",   "NONE")
    vol_sig    = ta_result.get("volume_signal", "N/A")
    bb_sig     = ta_result.get("bb_signal",    "N/A")
    support    = ta_result.get("support")
    resistance = ta_result.get("resistance")

    now = datetime.now().strftime("%d %b %Y · %H:%M IST")
    lines = [
        f"📊 *HERMES TECHNICAL SNAPSHOT — {sym}*",
        f"_{_esc(now)}_",
        "",
        f"{sig_emoji} *{_esc(sig)}* \\(score: {_esc(str(score))}\\)",
        f"💹 Price: `₹{price:,.2f}`",
        "",
        "*INDICATORS*",
    ]

    if rsi is not None:
        rsi_emoji = "🔴" if rsi > 70 else ("🟢" if rsi < 30 else "🟡")
        lines.append(f"{rsi_emoji} RSI: `{rsi:.1f}` — {_esc(ta_result.get('rsi_signal',''))}")

    if ma50:
        a50 = "above ✅" if ta_result.get("above_ma50") else "below ❌"
        lines.append(f"📏 MA50: `₹{ma50:,.2f}` — {_esc(a50)}")
    if ma200:
        a200 = "above ✅" if ta_result.get("above_ma200") else "below ❌"
        lines.append(f"📏 MA200: `₹{ma200:,.2f}` — {_esc(a200)}")

    if ma_cross != "NONE" and ma_cross != "N/A":
        emoji = "✨" if ma_cross == "GOLDEN" else "☠️"
        lines.append(f"{emoji} MA Cross: *{_esc(ma_cross)} CROSS*")

    if macd_cross != "NONE" and macd_cross != "N/A":
        emoji = "📈" if macd_cross == "BULLISH" else "📉"
        lines.append(f"{emoji} MACD: *{_esc(macd_cross)} crossover*")

    lines.append(f"📊 Volume: {_esc(vol_sig)} \\(ratio {ta_result.get('volume_ratio',1):.1f}x\\)")
    lines.append(f"〰️ Bollinger: {_esc(bb_sig)}")

    if support or resistance:
        lines.append("")
        lines.append("*KEY LEVELS*")
        if support:    lines.append(f"🟢 Support:    `₹{support:,.2f}`")
        if resistance: lines.append(f"🔴 Resistance: `₹{resistance:,.2f}`")

    lines.append("\n_— Hermes Agent_")
    return "\n".join(lines)


def format_ta_watchlist_summary(ta_results: list) -> str:
    now = datetime.now().strftime("%d %b %Y · %H:%M IST")
    lines = [
        "📊 *HERMES TECHNICAL SUMMARY — WATCHLIST*",
        f"_{_esc(now)}_",
        "",
    ]
    sig_map = {"STRONG BUY":"🚀","BUY":"📈","NEUTRAL":"➡️","SELL":"📉","STRONG SELL":"🔻"}
    for r in ta_results:
        sym   = r["symbol"].replace(".NS","")
        sig   = r.get("ta_signal","NEUTRAL")
        emoji = sig_map.get(sig, "➡️")
        rsi   = r.get("rsi")
        rsi_s = f"RSI {rsi:.0f}" if rsi else "—"
        vol   = r.get("volume_signal","—")
        mc    = r.get("macd_cross","—")
        lines.append(
            f"{emoji} *{_esc(sym)}* `₹{r['price']:,.2f}` — "
            f"{_esc(sig)} \\| {_esc(rsi_s)} \\| Vol:{_esc(vol)} \\| MACD:{_esc(mc)}"
        )
    lines.append("\n_— Hermes Agent_")
    return "\n".join(lines)


# ── 12. Pre-Trade Checklist ──────────────────────────────────────────────────

def format_pre_trade_checklist(result: dict) -> str:
    sym     = _esc(result["symbol"].replace(".NS",""))
    verdict = result["verdict"]
    passed  = result["passed"]
    total   = result["total"]
    entry   = result["entry"]
    stop    = result.get("stop_loss", 0)
    pos     = result.get("position", {})

    v_emoji = {"STRONG BUY":"🚀","BUY":"📈","WATCH":"👀","AVOID":"🚫"}.get(verdict,"❓")

    lines = [
        f"✅ *PRE\\-TRADE CHECKLIST — {sym}*",
        "",
        f"{v_emoji} *VERDICT: {_esc(verdict)}* \\({passed}/{total} checks passed\\)",
        "",
        f"💰 Entry: `₹{entry:,.2f}`",
        f"🛑 Stop\\-Loss: `₹{stop:,.2f}`",
    ]

    if pos:
        lines.append(f"📦 Suggested Qty: `{pos.get('qty',0)}` shares "
                     f"\\(₹{pos.get('position_value',0):,.0f} · {pos.get('position_pct',0):.1f}% of portfolio\\)")

    lines += ["", "*CHECKS*"]
    for c in result.get("checks", []):
        icon = "✅" if c["pass"] else "❌"
        lines.append(f"{icon} *{_esc(c['name'])}*")
        lines.append(f"    {_esc(c['detail'])}")

    lines.append("\n_— Hermes Agent_")
    return "\n".join(lines)


# ── 13. Trailing Stop Alert ──────────────────────────────────────────────────

def format_trailing_stop_alert(result: dict) -> str:
    sym    = _esc(result["symbol"].replace(".NS",""))
    profit = result["profit"]
    pct    = result["pct"]
    emoji  = "🟢" if profit >= 0 else "🔴"
    now    = datetime.now().strftime("%H:%M:%S IST")
    return (
        f"🛑 *HERMES TRAILING STOP HIT*\n\n"
        f"*{sym}* — SELL TRIGGERED\n\n"
        f"📍 Entry:   `₹{result['entry']:,.2f}`\n"
        f"🛑 Stop:    `₹{result['stop_hit']:,.2f}`\n"
        f"💹 Current: `₹{result['current_price']:,.2f}`\n"
        f"{emoji} P&L:    `{'+'if profit>=0 else ''}₹{profit:,.2f}` \\({_esc(f'{pct:+.2f}')}%\\)\n\n"
        f"_{_esc(now)}_\n_— Hermes Agent_"
    )


# ── 14. Risk Summary ─────────────────────────────────────────────────────────

def format_risk_summary(risk: dict) -> str:
    now = datetime.now().strftime("%d %b %Y · %H:%M IST")
    total = risk.get("total_value", 0)
    top5  = risk.get("top5_conc_pct", 0)
    it    = risk.get("it_exposure_pct",   0)
    bank  = risk.get("bank_exposure_pct", 0)
    divs  = "✅ Diversified" if risk.get("diversified") else "⚠️ Concentrated"
    warns = risk.get("warnings", [])

    lines = [
        "🛡️ *HERMES RISK SUMMARY*",
        f"_{_esc(now)}_",
        "",
        f"Portfolio Value: `₹{total:,.0f}`",
        f"Diversification: {_esc(divs)}",
        f"Top 5 concentration: `{top5:.1f}%`",
        f"IT exposure: `{it:.1f}%`  \\|  Banking: `{bank:.1f}%`",
        "",
    ]

    if warns:
        lines.append("*⚠️ WARNINGS*")
        for w in warns:
            lines.append(f"• {_esc(w)}")
        lines.append("")

    lines.append("*POSITIONS*")
    for p in sorted(risk.get("positions",[]), key=lambda x: x["pct"], reverse=True):
        sym   = p["symbol"].replace(".NS","")
        flag  = "⚠️ " if p["overweight"] else ""
        lines.append(f"{flag}*{_esc(sym)}* `{p['pct']:.1f}%` \\(₹{p['value']:,.0f}\\)")

    lines.append("\n_— Hermes Agent_")
    return "\n".join(lines)
