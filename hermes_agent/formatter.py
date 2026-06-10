"""
Hermes Agent — Telegram Message Formatter (v3)
All messages are beginner-friendly:
  - Plain English explanations
  - Monospace tables (readable on mobile)
  - Every number explained
  - Severity: 🔴 ACT NOW / 🟡 WATCH / 🟢 INFO / ⚪ FYI
"""

from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))

def _inr(val: float) -> str:
    if abs(val) >= 1_00_00_000: return f"₹{val/1_00_00_000:.2f} Cr"
    if abs(val) >= 1_00_000:    return f"₹{val/1_00_000:.2f} L"
    return f"₹{val:,.2f}"

def _pct_bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "▓" * filled + "░" * (width - filled)

def _sev(severity: str) -> str:
    return {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢","INFO":"⚪"}.get(severity,"⚪")

def _now() -> str:
    from pytz import timezone
    return datetime.now(timezone("Asia/Kolkata")).strftime("%d %b %Y  %H:%M IST")

def _trend(val: float) -> str:
    return "▲" if val > 0 else ("▼" if val < 0 else "─")

def _block(lines: list) -> str:
    """Wrap lines in a monospace code block for clean table rendering."""
    return "```\n" + "\n".join(lines) + "\n```"


# ── 1. Morning Brief ──────────────────────────────────────────────────────────

def format_morning_brief(
    indices, portfolio_rows, fii_dii, news, earnings_soon,
):
    lines = [
        f"🌅 *HERMES MORNING BRIEF*",
        f"_{_esc(_now())}_",
        "",
        "📊 *MARKET OVERVIEW*",
    ]

    # Indices table
    tbl = ["Index            Price      Change"]
    tbl.append("─" * 38)
    for name, d in indices.items():
        arrow = _trend(d["pct"])
        sign  = "+" if d["pct"] >= 0 else ""
        tbl.append(f"{name:<16} {d['price']:>9,.2f}  {arrow}{sign}{d['pct']:.2f}%")
    lines.append(_block(tbl))

    # FII/DII
    fn  = fii_dii.get("fii_net", 0)
    dn  = fii_dii.get("dii_net", 0)
    lines += [
        "🏦 *FII / DII FLOW*",
        "_FII = Foreign investors  \\|  DII = Indian mutual funds_",
    ]
    fii_tbl = [
        f"FII Net  {_inr(fn):>12}  {'🟢 Buying' if fn>=0 else '🔴 Selling'}",
        f"DII Net  {_inr(dn):>12}  {'🟢 Buying' if dn>=0 else '🔴 Selling'}",
    ]
    lines.append(_block(fii_tbl))

    # Portfolio
    total_day   = sum(r.get("day_pnl",   0) for r in portfolio_rows)
    total_pnl   = sum(r.get("total_pnl", 0) for r in portfolio_rows)
    total_val   = sum(r.get("market_value", 0) for r in portfolio_rows)

    lines += [
        "💼 *YOUR PORTFOLIO*",
        f"_Total Value: {_esc(_inr(total_val))}_",
    ]
    ptbl = ["Stock       Today's P&L    Total P&L"]
    ptbl.append("─" * 40)
    for r in portfolio_rows:
        sym = r["symbol"].replace(".NS","")[:10]
        dp  = r.get("day_pnl",   0)
        tp  = r.get("total_pnl", 0)
        ptbl.append(
            f"{sym:<10}  {_inr(dp):>12}  {_inr(tp):>12}"
            f"  {'▲' if dp>=0 else '▼'}")
    ptbl.append("─" * 40)
    ptbl.append(f"{'TOTAL':<10}  {_inr(total_day):>12}  {_inr(total_pnl):>12}")
    lines.append(_block(ptbl))

    # News
    if news:
        lines += ["", "📰 *STOCK NEWS*"]
        for n in news[:5]:
            sym = n["symbol"].replace(".NS","")
            lines.append(f"• \\[{_esc(sym)}\\] {_esc(n['title'][:70])}…")

    # Earnings reminder
    if earnings_soon:
        lines += ["", "⚠️ *RESULTS COMING SOON*"]
        for e in earnings_soon:
            sym = e["symbol"].replace(".NS","")
            lines.append(f"🗓 *{_esc(sym)}* — results in *{e['days_out']}d* \\({_esc(str(e['date']))}\\)")
            lines.append("_Tip: Avoid buying just before results — price can swing wildly_")

    lines.append(f"\n_Hermes Agent · {_esc(_now())}_")
    return "\n".join(lines)


def format_morning_brief_extended(
    indices, portfolio_rows, fii_dii, news, earnings_soon,
    signals_today, crude=None, inr=None, global_mkts=None, macro_events=None,
):
    base = format_morning_brief(indices, portfolio_rows, fii_dii, news, earnings_soon)
    extra = []

    if global_mkts:
        extra.append("\n🌍 *GLOBAL MARKETS*")
        gtbl = ["Market           Price      Today"]
        gtbl.append("─" * 38)
        for g in global_mkts[:5]:
            arrow = "▲" if g["pct"] >= 0 else "▼"
            gtbl.append(f"{g['name']:<16} {g['price']:>9,.2f}  {arrow}{g['pct']:+.2f}%")
        extra.append(_block(gtbl))

    if crude or inr:
        extra.append("🛢️ *GLOBAL INDICATORS*")
        mac = []
        if crude and crude.get("price"):
            mac.append(f"Brent Crude  ${crude['price']:>7.2f}  {_trend(crude['pct'])}{crude['pct']:+.2f}%")
        if inr and inr.get("rate"):
            mac.append(f"INR/USD      ₹{inr['rate']:>7.2f}  {_trend(inr['pct'])}{inr['pct']:+.4f}")
        extra.append(_block(mac))

    if macro_events:
        extra.append("📅 *KEY EVENTS THIS WEEK*")
        for ev in macro_events[:3]:
            urg = "🔴" if ev["impact"]=="HIGH" else "🟡"
            extra.append(f"{urg} {_esc(ev['event'])} — in {ev['days_out']}d")
            extra.append(f"   _Why it matters: Market moves before and after this event_")

    critical = [s for s in signals_today if s["severity"] in ("CRITICAL","HIGH")]
    if critical:
        extra.append("\n🧠 *TODAY'S KEY ALERTS*")
        for s in critical[:4]:
            extra.append(f"{_sev(s['severity'])} {_esc(s['summary'])}")

    footer = "_Hermes Agent"
    return base.replace(footer, "\n".join(extra) + "\n" + footer)


# ── 2. Price Alert ────────────────────────────────────────────────────────────

def format_price_alert(symbol, condition, level, current_price):
    sym       = symbol.replace(".NS","")
    direction = "CROSSED ABOVE 🚀" if condition=="above" else "DROPPED BELOW 🔻"
    sev       = "🔴 ACT NOW" if condition=="below" else "🟢 OPPORTUNITY"
    diff      = abs(current_price - level)
    diff_pct  = round((diff / level) * 100, 2)

    tbl = [
        f"Stock         {sym}",
        f"Alert Level   ₹{level:,.2f}",
        f"Current Price ₹{current_price:,.2f}",
        f"Moved by      ₹{diff:,.2f}  ({diff_pct:.2f}%)",
    ]

    return "\n".join([
        f"🔔 *PRICE ALERT — {_esc(sym)}*",
        "",
        f"*{_esc(direction)}*",
        f"Severity: {sev}",
        "",
        _block(tbl),
        "",
        f"_What to do: Check your trading plan for {_esc(sym)} and act accordingly_",
        f"_{_esc(_now())} · Hermes Agent_",
    ])


# ── 3. 52W Range Report ───────────────────────────────────────────────────────

def format_52w_report(analysis):
    lines = [
        "📐 *52\\-WEEK RANGE REPORT*",
        "_Where each stock sits between its yearly low and high_",
        f"_{_esc(_now())}_",
        "",
    ]

    danger = [s for s in analysis if s["danger"]]
    safe   = [s for s in analysis if not s["danger"]]

    if danger:
        lines.append("🔴 *DANGER ZONE — Near 52\\-Week Low*")
        lines.append("_These stocks are close to their lowest price in a year_")
        dtbl = ["Stock      Price      52W Low    52W High   Position"]
        dtbl.append("─" * 58)
        for s in danger:
            sym = s["symbol"].replace(".NS","")[:8]
            bar = _pct_bar(s["position_pct"], 8)
            dtbl.append(
                f"{sym:<8}  ₹{s['price']:>8,.2f}  ₹{s['week52l']:>8,.2f}"
                f"  ₹{s['week52h']:>8,.2f}  [{bar}]")
            dtbl.append(f"         Only {s['pct_from_low']:.1f}% above yearly low  ⚠️")
        lines.append(_block(dtbl))
        lines.append("_Tip: A stock near its yearly low CAN keep falling. Don't catch a falling knife._")

    if safe:
        lines.append("\n📊 *WATCHLIST POSITIONS*")
        stbl = ["Stock      Price      From Low   From High  Range"]
        stbl.append("─" * 56)
        for s in safe:
            sym = s["symbol"].replace(".NS","")[:8]
            bar = _pct_bar(s["position_pct"], 8)
            stbl.append(
                f"{sym:<8}  ₹{s['price']:>8,.2f}"
                f"  +{s['pct_from_low']:>5.1f}%"
                f"  -{s['pct_from_high']:>5.1f}%"
                f"  [{bar}]")
        lines.append(_block(stbl))

    lines.append(f"\n_Hermes Agent · {_esc(_now())}_")
    return "\n".join(lines)


# ── 4. Earnings Calendar ──────────────────────────────────────────────────────

def format_earnings_reminder(earnings):
    lines = [
        "🗓 *UPCOMING RESULTS CALENDAR*",
        "_These companies will announce their quarterly results soon_",
        f"_{_esc(_now())}_",
        "",
    ]
    if not earnings:
        lines.append("_No upcoming results found for your watchlist_")
    else:
        tbl = ["Stock      Results Date  Days Left  Status"]
        tbl.append("─" * 48)
        for e in earnings:
            sym  = e["symbol"].replace(".NS","")[:8]
            days = e["days_out"]
            if days == 0:    status = "🔴 TODAY"
            elif days <= 3:  status = "🟠 VERY SOON"
            elif days <= 7:  status = "🟡 THIS WEEK"
            else:            status = "🟢 UPCOMING"
            tbl.append(f"{sym:<8}  {str(e['date']):<13}  {days:>4}d      {status}")
        lines.append(_block(tbl))
        lines.append("_Tip: Stock prices move a lot around results. Beginners should avoid_")
        lines.append("_trading just before or after result announcements._")

    lines.append(f"\n_Hermes Agent · {_esc(_now())}_")
    return "\n".join(lines)


# ── 5. Signal Digest ──────────────────────────────────────────────────────────

def format_signal_digest(signals, timeframe="TODAY"):
    tf_label = {"TODAY":"TODAY","1W":"NEXT 1 WEEK","1M":"NEXT 1 MONTH"}.get(timeframe, timeframe)
    tf_sigs  = [s for s in signals if s["timeframe"]==timeframe]

    lines = [
        f"🧠 *HERMES SIGNAL DIGEST — {_esc(tf_label)}*",
        f"_{_esc(_now())}_",
        "",
        "_What is a signal? A signal is an alert that something_",
        "_important may be happening with a stock or the market._",
        "",
    ]

    if not tf_sigs:
        lines.append("_No significant signals detected right now_")
        lines.append(f"\n_Hermes Agent · {_esc(_now())}_")
        return "\n".join(lines)

    for sev in ("CRITICAL","HIGH","MEDIUM"):
        sigs = [s for s in tf_sigs if s["severity"]==sev]
        if not sigs: continue
        label = {"CRITICAL":"🔴 ACT NOW","HIGH":"🟠 IMPORTANT","MEDIUM":"🟡 WATCH"}.get(sev)
        lines.append(f"*{label}*")
        tbl = []
        for s in sigs:
            sym = s["symbol"][:10]
            tbl.append(f"{sym:<10}  {s['type']:<20}")
            tbl.append(f"  ➜ {s['summary'][:65]}")
        lines.append(_block(tbl))

    lines.append(f"\n_Hermes Agent · {_esc(_now())}_")
    return "\n".join(lines)


# ── 6. Corporate Action Alert ─────────────────────────────────────────────────

def format_corporate_action_alert(action):
    sym = action["symbol"]
    cat = action["category"]
    emoji = {"DIVIDEND":"💰","BONUS":"🎁","SPLIT":"✂️","RIGHTS":"📋","MEETING":"🏛"}.get(cat,"📌")
    urgency = "TODAY" if action["days_out"]==0 else f"in {action['days_out']} days"

    explain = {
        "DIVIDEND": "Company is paying cash to shareholders. Price usually drops by dividend amount on ex-date.",
        "BONUS":    "Company gives free extra shares. Good sign of company confidence.",
        "SPLIT":    "Stock splits into smaller price units. Your value stays same but you get more shares.",
        "RIGHTS":   "Company offering new shares to existing shareholders at a discounted price.",
    }.get(cat, "Corporate event that may affect stock price.")

    tbl = [
        f"Stock       {sym}",
        f"Event       {cat}",
        f"Ex-Date     {action['ex_date']}",
        f"When        {urgency}",
        f"Details     {action['action'][:40]}",
    ]

    return "\n".join([
        f"{emoji} *CORPORATE ACTION — {_esc(sym)}*",
        "",
        _block(tbl),
        "",
        f"📖 *What this means:*",
        f"_{_esc(explain)}_",
        "",
        f"_{'🔴 Urgent — act before ex-date' if action['urgent'] else '🟡 Mark this date in your calendar'}_",
        f"_{_esc(_now())} · Hermes Agent_",
    ])


# ── 7. Macro Alert ────────────────────────────────────────────────────────────

def format_macro_alert(event, crude=None, inr=None):
    days    = event["days_out"]
    urgency = "🔴 TODAY" if days==0 else f"🟡 In {days} days"

    explain = {
        "RBI":    "RBI sets interest rates. Rate cut = good for stocks. Rate hike = bad for stocks.",
        "Fed":    "US Federal Reserve rate decision affects global markets including India.",
        "CPI":    "Inflation data. High inflation = RBI may raise rates = bad for markets.",
        "GDP":    "India growth rate. Higher GDP = stronger economy = good for stocks.",
        "Budget": "Government spending plan. Some sectors benefit, some suffer.",
    }
    exp_text = next((v for k, v in explain.items() if k.lower() in event["event"].lower()),
                    "This economic event can cause market volatility.")

    tbl = [f"Event    {event['event'][:40]}",
           f"When     {event['date']}  ({urgency})",
           f"Impact   {event['impact']}"]
    if crude and crude.get("price"):
        tbl.append(f"Crude    ${crude['price']:.2f}  ({crude['pct']:+.2f}%)")
    if inr and inr.get("rate"):
        tbl.append(f"INR/USD  ₹{inr['rate']:.2f}  ({inr['pct']:+.4f})")

    return "\n".join([
        "🌐 *MACRO EVENT ALERT*",
        "",
        _block(tbl),
        "",
        "📖 *What this means for you:*",
        f"_{_esc(exp_text)}_",
        "",
        "_Tip: Avoid big trades just before major economic announcements._",
        f"_{_esc(_now())} · Hermes Agent_",
    ])


# ── 8. Bulk/Block Deal Alert ──────────────────────────────────────────────────

def format_deal_alert(deal):
    action = deal.get("buy_sell","").upper()
    emoji  = "🟢" if "BUY" in action else "🔴"
    sym    = deal["symbol"]

    explain = (
        "A big investor is BUYING — could be a positive sign for the stock."
        if "BUY" in action else
        "A big investor is SELLING — watch if this continues over multiple days."
    )

    tbl = [
        f"Stock     {sym}",
        f"Action    {action}",
        f"Investor  {deal['client'][:30]}",
        f"Quantity  {deal['qty']:,} shares",
        f"Value     {_inr(deal['value_cr']*1e7)}",
        f"Price     ₹{deal['price']:,.2f}",
        f"Type      {deal['type']} DEAL",
    ]

    return "\n".join([
        f"{emoji} *{deal['type']} DEAL ALERT — {_esc(sym)}*",
        "",
        _block(tbl),
        "",
        "📖 *What this means:*",
        f"_{_esc(explain)}_",
        "",
        "_A bulk deal = someone traded >0.5% of total shares in one go_",
        f"_{_esc(_now())} · Hermes Agent_",
    ])


# ── 9. FII Trend Alert ────────────────────────────────────────────────────────

def format_fii_trend_alert(signal):
    is_buy = "buying" in signal["summary"].lower()
    emoji  = "🟢" if is_buy else "🔴"
    return "\n".join([
        f"{emoji} *FII TREND ALERT*",
        "",
        _block([signal["summary"][:70]]),
        "",
        "📖 *What this means:*",
        "_FII = big foreign funds like Morgan Stanley, Goldman Sachs_",
        f"_When they {'buy' if is_buy else 'sell'} for 3+ days in a row, the market usually follows_",
        "",
        f"_Tip: {'This is a bullish sign — quality stocks may rise' if is_buy else 'Be cautious — foreign money is leaving India'}_",
        f"_{_esc(_now())} · Hermes Agent_",
    ])


# ── 10. TA Snapshot ───────────────────────────────────────────────────────────

def format_ta_snapshot(r):
    sym   = r["symbol"].replace(".NS","")
    sig   = r.get("ta_signal","NEUTRAL")
    score = r.get("ta_score",0)
    sig_emoji = {"STRONG BUY":"🚀","BUY":"📈","STRONG SELL":"🔻","SELL":"📉","NEUTRAL":"➡️"}.get(sig,"➡️")

    rsi   = r.get("rsi")
    ma50  = r.get("ma50")
    ma200 = r.get("ma200")

    tbl = [f"{'Indicator':<16} {'Value':<12} {'What it means':<28}"]
    tbl.append("─" * 58)

    if rsi is not None:
        rsi_mean = "Oversold — may bounce" if rsi<30 else ("Overbought — may fall" if rsi>70 else "Normal range")
        tbl.append(f"{'RSI':<16} {rsi:<12.1f} {rsi_mean}")

    if ma50:
        pos = "Price ABOVE — uptrend ✅" if r.get("above_ma50") else "Price BELOW — downtrend ❌"
        tbl.append(f"{'50-day Average':<16} ₹{ma50:<10,.2f} {pos}")

    if ma200:
        pos = "Price ABOVE — long uptrend ✅" if r.get("above_ma200") else "Price BELOW — long downtrend ❌"
        tbl.append(f"{'200-day Avg':<16} ₹{ma200:<10,.2f} {pos}")

    mc = r.get("macd_cross","NONE")
    if mc not in ("NONE","N/A"):
        mc_mean = "Momentum turning UP" if mc=="BULLISH" else "Momentum turning DOWN"
        tbl.append(f"{'MACD Cross':<16} {mc:<12} {mc_mean}")

    mac = r.get("ma_cross","NONE")
    if mac not in ("NONE","N/A"):
        mac_mean = "Very bullish long signal ✨" if mac=="GOLDEN" else "Very bearish long signal ☠️"
        tbl.append(f"{'MA Cross':<16} {mac:<12} {mac_mean}")

    vol = r.get("volume_signal","—")
    tbl.append(f"{'Volume':<16} {vol:<12} {'Unusually high — watch' if vol=='SPIKE' else 'Normal'}")

    bb  = r.get("bb_signal","—")
    bb_mean = {"SQUEEZE":"Big move coming soon!","NEAR_LOWER":"Near support","NEAR_UPPER":"Near resistance"}.get(bb,"Normal range")
    tbl.append(f"{'Bollinger Band':<16} {bb:<12} {bb_mean}")

    lines = [
        f"📊 *TECHNICAL ANALYSIS — {_esc(sym)}*",
        f"_{_esc(_now())}_",
        "",
        f"{sig_emoji} *Overall Signal: {_esc(sig)}* \\(score: {score}\\)",
        f"💹 Current Price: ₹{r.get('price',0):,.2f}",
        "",
        _block(tbl),
    ]

    sup = r.get("support")
    res = r.get("resistance")
    if sup or res:
        kl = []
        if sup: kl.append(f"Support Level   ₹{sup:,.2f}  ← Price likely bounces here")
        if res: kl.append(f"Resistance      ₹{res:,.2f}  ← Price may struggle to cross this")
        lines.append(_block(kl))

    lines += [
        "📖 *Beginner Guide:*",
        "_RSI < 30 = oversold = possibly good time to buy_",
        "_RSI > 70 = overbought = possibly good time to sell_",
        "_Price above 50-day average = stock is in an uptrend_",
        f"_{_esc(_now())} · Hermes Agent_",
    ]
    return "\n".join(lines)


def format_ta_watchlist_summary(ta_results):
    lines = [
        "📊 *TECHNICAL SUMMARY — ALL YOUR STOCKS*",
        f"_{_esc(_now())}_",
        "",
        "_Signal Guide: 🚀 Strong Buy  📈 Buy  ➡️ Neutral  📉 Sell  🔻 Strong Sell_",
        "",
    ]
    sig_map = {"STRONG BUY":"🚀","BUY":"📈","NEUTRAL":"➡️","SELL":"📉","STRONG SELL":"🔻"}
    tbl = [f"{'Stock':<10} {'Price':>9} {'Signal':<13} {'RSI':>5} {'Trend'}"]
    tbl.append("─" * 55)
    for r in ta_results:
        sym  = r["symbol"].replace(".NS","")[:9]
        sig  = r.get("ta_signal","NEUTRAL")
        emoji = sig_map.get(sig,"➡️")
        rsi  = f"{r['rsi']:.0f}" if r.get("rsi") else "—"
        trend = "▲ Uptrend" if r.get("above_ma50") else "▼ Downtrend"
        tbl.append(f"{sym:<10} {r['price']:>9,.2f} {emoji} {sig:<11} {rsi:>5} {trend}")
    lines.append(_block(tbl))
    lines.append(f"\n_Hermes Agent · {_esc(_now())}_")
    return "\n".join(lines)


# ── 11. Pre-Trade Checklist ───────────────────────────────────────────────────

def format_pre_trade_checklist(result):
    sym     = result["symbol"].replace(".NS","")
    verdict = result["verdict"]
    passed  = result["passed"]
    total   = result["total"]
    entry   = result["entry"]
    stop    = result.get("stop_loss",0)
    pos     = result.get("position",{})

    v_emoji = {"STRONG BUY":"🚀","BUY":"📈","WATCH":"👀","AVOID":"🚫"}.get(verdict,"❓")
    explain = {
        "STRONG BUY": "All conditions are met. This looks like a good setup.",
        "BUY":        "Most conditions are met. Reasonable entry with proper stop-loss.",
        "WATCH":      "Some conditions are not ideal. Wait for better setup.",
        "AVOID":      "Multiple conditions failed. High risk. Skip this trade.",
    }.get(verdict,"")

    lines = [
        f"✅ *PRE\\-TRADE CHECKLIST — {_esc(sym)}*",
        f"_{_esc(_now())}_",
        "",
        f"{v_emoji} *Verdict: {_esc(verdict)}* \\({passed}/{total} checks passed\\)",
        f"_{_esc(explain)}_",
        "",
    ]

    detail_tbl = [f"{'Check':<28} {'Result'}"]
    detail_tbl.append("─" * 50)
    for c in result.get("checks",[]):
        icon = "✅" if c["pass"] else "❌"
        detail_tbl.append(f"{icon} {c['name']:<26} {'PASS' if c['pass'] else 'FAIL'}")
        detail_tbl.append(f"   {c['detail'][:46]}")
    lines.append(_block(detail_tbl))

    trade_tbl = [
        f"Entry Price    ₹{entry:,.2f}",
        f"Stop-Loss      ₹{stop:,.2f}  ← Sell immediately if price hits this",
        f"Risk per share ₹{entry-stop:,.2f}",
    ]
    if pos:
        trade_tbl += [
            f"Suggested Qty  {pos.get('qty',0)} shares",
            f"Position Value ₹{pos.get('position_value',0):,.0f}  ({pos.get('position_pct',0):.1f}% of portfolio)",
            f"Max Risk       ₹{pos.get('risk_amount',0):,.0f}  (1% of portfolio)",
        ]
    lines += ["*TRADE PLAN*", _block(trade_tbl)]
    lines.append(f"\n_Hermes Agent · {_esc(_now())}_")
    return "\n".join(lines)


# ── 12. Trailing Stop Alert ───────────────────────────────────────────────────

def format_trailing_stop_alert(result):
    sym    = result["symbol"].replace(".NS","")
    profit = result["profit"]
    pct    = result["pct"]
    emoji  = "🟢" if profit>=0 else "🔴"

    tbl = [
        f"Stock          {sym}",
        f"You bought at  ₹{result['entry']:,.2f}",
        f"Stop hit at    ₹{result['stop_hit']:,.2f}",
        f"Current price  ₹{result['current_price']:,.2f}",
        f"Your P&L       {'+' if profit>=0 else ''}₹{profit:,.2f}  ({pct:+.2f}%)",
    ]
    return "\n".join([
        f"🛑 *TRAILING STOP HIT — {_esc(sym)}*",
        "",
        _block(tbl),
        "",
        f"{emoji} *Action: SELL NOW*",
        "_Your automatic stop-loss has been triggered._",
        "_This protects you from further losses._",
        f"_{_esc(_now())} · Hermes Agent_",
    ])


# ── 13. Risk Summary ──────────────────────────────────────────────────────────

def format_risk_summary(risk):
    total = risk.get("total_value",0)
    top5  = risk.get("top5_conc_pct",0)
    divs  = "✅ Well diversified" if risk.get("diversified") else "⚠️ Too concentrated"

    lines = [
        "🛡️ *PORTFOLIO RISK REPORT*",
        "_How safe is your portfolio?_",
        f"_{_esc(_now())}_",
        "",
        _block([
            f"Total Value      {_inr(total)}",
            f"Diversification  {divs}",
            f"Top 5 stocks     {top5:.1f}% of portfolio",
            f"IT exposure      {risk.get('it_exposure_pct',0):.1f}%",
            f"Banking exposure {risk.get('bank_exposure_pct',0):.1f}%",
        ]),
    ]

    warns = risk.get("warnings",[])
    if warns:
        lines += ["🔴 *WARNINGS*"]
        for w in warns:
            lines.append(f"• {_esc(w)}")
        lines.append("")

    lines.append("*POSITION BREAKDOWN*")
    ptbl = [f"{'Stock':<12} {'% of Portfolio':>15} {'Value':>14}  {'Status'}"]
    ptbl.append("─" * 55)
    for p in sorted(risk.get("positions",[]), key=lambda x: x["pct"], reverse=True):
        sym  = p["symbol"].replace(".NS","")[:11]
        flag = "⚠️ TOO LARGE" if p["overweight"] else "OK"
        ptbl.append(f"{sym:<12} {p['pct']:>14.1f}%  {_inr(p['value']):>14}  {flag}")
    lines.append(_block(ptbl))

    lines += [
        "📖 *Tip:*",
        "_No single stock should be more than 20% of your portfolio._",
        "_Spreading across sectors reduces risk if one sector falls._",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 14. Sector Rotation ───────────────────────────────────────────────────────

def format_sector_rotation(sector_data, signals):
    lines = [
        "🔄 *SECTOR ROTATION REPORT*",
        "_Which parts of the market are gaining or losing money today_",
        f"_{_esc(_now())}_",
        "",
    ]

    tbl = [f"{'Sector':<12} {'Today':>8} {'This Week':>10} {'Money Flow'}"]
    tbl.append("─" * 48)
    for s in sector_data:
        flow  = "🟢 Flowing IN" if s["pct"]>0 else "🔴 Flowing OUT"
        tbl.append(
            f"{s['sector']:<12} {s['pct']:>+7.2f}%  {s['week_pct']:>+8.2f}%   {flow}")
    lines.append(_block(tbl))

    if signals:
        lines.append("*SIGNALS FOR YOUR STOCKS*")
        for sig in signals:
            emoji = "🟢" if "UP" in sig["type"] else "🔴"
            lines.append(f"{emoji} {_esc(sig['message'])}")

    lines += [
        "",
        "📖 *What is sector rotation?*",
        "_Big investors move money between sectors depending on the economy._",
        "_When IT stocks are rising but Banking is falling, money is rotating._",
        "_If your stock's sector is getting money = positive for your stock._",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 15. VIX + Sentiment ───────────────────────────────────────────────────────

def format_sentiment_report(sentiment):
    vix = sentiment.get("vix",{})
    pcr = sentiment.get("pcr",{})
    ad  = sentiment.get("ad",{})
    mood= sentiment.get("mood","NEUTRAL")

    mood_emoji = "🟢" if mood=="BULLISH" else ("🔴" if mood=="BEARISH" else "🟡")

    lines = [
        "🌡️ *MARKET SENTIMENT REPORT*",
        "_How is the market feeling right now?_",
        f"_{_esc(_now())}_",
        "",
        f"{mood_emoji} *Overall Market Mood: {_esc(mood)}*",
        "",
    ]

    tbl = [f"{'Indicator':<20} {'Value':<10} {'Reading'}"]
    tbl.append("─" * 55)

    v = vix.get("vix",0)
    tbl.append(f"{'India VIX':<20} {v:<10.2f} {vix.get('level','—')}")
    tbl.append(f"  ↳ {vix.get('meaning','')[:45]}")

    p = pcr.get("pcr",0)
    tbl.append(f"{'Put/Call Ratio':<20} {p:<10.2f} {pcr.get('level','—')}")
    tbl.append(f"  ↳ {pcr.get('meaning','')[:45]}")

    a = ad.get("ratio",0)
    adv = ad.get("advances",0); dec = ad.get("declines",0)
    tbl.append(f"{'Adv/Dec Ratio':<20} {a:<10.2f} {ad.get('breadth','—')}")
    tbl.append(f"  ↳ {adv} stocks rising, {dec} falling today")

    lines.append(_block(tbl))

    lines += [
        "📖 *Beginner Guide:*",
        "_VIX = Fear Index. Above 20 = high fear. Above 25 = extreme fear._",
        "_High fear can mean BUYING OPPORTUNITY for strong stocks._",
        "_PCR above 1.2 = most people are scared = market may actually rise._",
        "",
        f"*What to do now:* _{_esc(vix.get('action','Monitor the market'))}_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 16. Promoter Pledge + Shareholding ───────────────────────────────────────

def format_shareholding_report(shareholding_data, alerts):
    lines = [
        "🏛️ *PROMOTER & INSTITUTIONAL HOLDINGS*",
        "_Who owns your stocks and are they buying or selling?_",
        f"_{_esc(_now())}_",
        "",
    ]

    tbl = [f"{'Stock':<10} {'Promoter':>9} {'Pledge':>7} {'FII':>6} {'MF/DII':>7} {'Risk'}"]
    tbl.append("─" * 58)
    for s in shareholding_data:
        sym  = s["symbol"][:9]
        risk = {"HIGH":"🔴 HIGH","MEDIUM":"🟡 MED","LOW":"🟢 LOW","NONE":"✅ NONE"}.get(
            s["pledge_risk"],"—")
        tbl.append(
            f"{sym:<10} {s['promoter_pct']:>8.1f}%"
            f"  {s['pledge_pct']:>6.1f}%"
            f"  {s['fii_pct']:>5.1f}%"
            f"  {s['dii_pct']:>6.1f}%"
            f"  {risk}")
    lines.append(_block(tbl))

    if alerts:
        lines.append("*ALERTS*")
        for a in alerts:
            sev_e = "🔴" if a["severity"]=="HIGH" else "🟡"
            lines.append(f"{sev_e} *{_esc(a['symbol'])}* — {_esc(a['message'])}")
            lines.append(f"   _Action: {_esc(a['action'])}_")
            lines.append("")

    lines += [
        "📖 *Beginner Guide:*",
        "_Promoter = company founders/owners. High pledge % = danger sign._",
        "_FII = foreign funds. DII/MF = Indian mutual funds._",
        "_If MF is quietly buying = smart Indian money is confident._",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 17. Unusual Options Activity ─────────────────────────────────────────────

def format_options_activity(options_data):
    lines = [
        "🎯 *UNUSUAL OPTIONS ACTIVITY*",
        "_Big investors are placing large bets — here's what they expect_",
        f"_{_esc(_now())}_",
        "",
        "📖 *Quick Guide:*",
        "_CALL option = bet that price will RISE_",
        "_PUT option  = bet that price will FALL_",
        "_Unusual activity = someone placed a very large bet_",
        "",
    ]

    for r in options_data:
        sym = r["symbol"]
        pcr = r.get("pcr",1.0)
        sent= r.get("sentiment","NEUTRAL")
        mp  = r.get("max_pain",0)
        sup = r.get("support")
        res = r.get("resistance")
        iv  = r.get("avg_iv",0)
        spot= r.get("spot",0)

        sent_emoji = "🟢" if sent=="BULLISH" else ("🔴" if sent=="BEARISH" else "🟡")
        lines.append(f"{sent_emoji} *{_esc(sym)}* — Sentiment: {_esc(sent)}")

        tbl = [
            f"Current Price   ₹{spot:,.2f}",
            f"Put/Call Ratio  {pcr:.2f}  ({'More puts=bearish bets' if pcr>1 else 'More calls=bullish bets'})",
            f"Max Pain Level  ₹{mp:,}  (Market tends to close near this on expiry)",
        ]
        if sup: tbl.append(f"Options Support ₹{sup:,}  (Big put bets defending this level)")
        if res: tbl.append(f"Options Resist  ₹{res:,}  (Big call bets capping upside)")
        if iv:  tbl.append(f"Implied Volat.  {iv:.1f}%  ({'⚠️ HIGH — big move expected' if iv>40 else 'Normal'})")
        lines.append(_block(tbl))

        unusual = r.get("unusual",[])
        if unusual:
            lines.append(f"*🚨 UNUSUAL BETS DETECTED:*")
            for u in unusual:
                bet_type = "RISE above" if u["type"]=="CALL_BUILDUP" else "FALL below"
                lines.append(f"• Large bet placed that {sym} will {bet_type} ₹{u['strike']:,}")
                lines.append(f"  _OI change: {u['oi_change']:,} contracts · IV: {u['iv']:.1f}%_")

        lines.append("")

    lines.append(f"_Hermes Agent · {_esc(_now())}_")
    return "\n".join(lines)


# ── 18. Fundamentals Report ──────────────────────────────────────────────────

def format_fundamentals_report(fund_data: list) -> str:
    lines = [
        "📈 *FUNDAMENTALS REPORT — YOUR WATCHLIST*",
        "_Is each stock cheap or expensive? Is the business growing?_",
        f"_{_esc(_now())}_",
        "",
        "_Signal:  🚀 Strong Buy  📈 Buy  ⏸ Hold  📉 Sell  🔻 Strong Sell_",
        "",
    ]
    sig_map = {"STRONG BUY":"🚀","BUY":"📈","HOLD":"⏸","SELL":"📉","STRONG SELL":"🔻"}
    tbl = [f"{'Stock':<10} {'P/E':>6} {'ROE':>6} {'Debt':>6} {'Rev Grw':>8} {'Signal'}"]
    tbl.append("─" * 58)
    for r in fund_data:
        sym   = r["symbol"][:9]
        pe    = f"{r['pe']:.0f}"    if r.get("pe")    else "—"
        roe   = f"{r['roe']:.0f}%"  if r.get("roe")   else "—"
        debt  = f"{r['debt_eq']:.0f}%" if r.get("debt_eq") is not None else "—"
        rev   = f"{r['rev_growth']:+.0f}%" if r.get("rev_growth") else "—"
        sig   = r.get("overall","—")
        emoji = sig_map.get(sig,"⏸")
        tbl.append(f"{sym:<10} {pe:>6} {roe:>6} {debt:>6} {rev:>8}  {emoji} {sig}")
    lines.append(_block(tbl))

    # Highlight top picks
    buys = [r for r in fund_data if r.get("overall") in ("STRONG BUY","BUY")]
    if buys:
        lines.append("*🏆 TOP FUNDAMENTAL PICKS*")
        for r in buys[:3]:
            upside = f" · Analyst target {r['upside']:+.0f}% upside" if r.get("upside") else ""
            lines.append(f"• *{_esc(r['symbol'])}* — {_esc(r.get('overall',''))} (score {r['score']}/8){_esc(upside)}")

    lines += [
        "",
        "📖 *Beginner Guide:*",
        "_P/E: Lower than sector average = cheaper = potentially better buy_",
        "_ROE above 15% = company uses your money efficiently_",
        "_Debt below 50% = company is not over-borrowed_",
        "_Revenue Growth above 10% = business is expanding_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


def format_single_fundamental(r: dict) -> str:
    sym = r["symbol"]
    sig = r.get("overall","HOLD")
    sig_emoji = {"STRONG BUY":"🚀","BUY":"📈","HOLD":"⏸","SELL":"📉","STRONG SELL":"🔻"}.get(sig,"⏸")

    tbl = [f"{'Metric':<22} {'Value':<14} {'Assessment'}"]
    tbl.append("─" * 60)
    if r.get("pe"):     tbl.append(f"{'P/E Ratio':<22} {r['pe']:<14.1f} {r.get('pe_flag','')[:25]}")
    if r.get("roe"):    tbl.append(f"{'ROE (Return on Equity)':<22} {str(r['roe'])+'%':<14} {r.get('roe_flag','')[:25]}")
    if r.get("debt_eq") is not None: tbl.append(f"{'Debt/Equity':<22} {str(r['debt_eq'])+'%':<14} {r.get('debt_flag','')[:25]}")
    if r.get("rev_growth"): tbl.append(f"{'Revenue Growth':<22} {str(r['rev_growth'])+'%':<14} {r.get('rev_flag','')[:25]}")
    if r.get("profit_margin"): tbl.append(f"{'Profit Margin':<22} {str(r['profit_margin'])+'%':<14} {'Good' if r['profit_margin']>15 else 'Average'}")
    if r.get("beta"):   tbl.append(f"{'Beta (Volatility)':<22} {r['beta']:<14} {'High risk' if r['beta']>1.3 else 'Moderate'}")
    if r.get("div_yield"): tbl.append(f"{'Dividend Yield':<22} {str(r['div_yield'])+'%':<14} {'Regular income'}")
    if r.get("target_price"):
        tbl.append(f"{'Analyst Target':<22} ₹{r['target_price']:<13,.2f} {str(r.get('upside',''))+('% upside' if r.get('upside') else '')}")

    lines = [
        f"📊 *FUNDAMENTAL ANALYSIS — {_esc(sym)}*",
        f"_{r.get('name','')[:50]}_",
        f"_{_esc(_now())}_",
        "",
        f"{sig_emoji} *Overall: {_esc(sig)}* \\(score {r['score']}/8\\)",
        f"💹 Price: ₹{r.get('price',0):,.2f}   Sector: {_esc(r.get('sector',''))}",
        "",
        _block(tbl),
        "",
        "📖 *What to do:*",
        f"_{_esc({'STRONG BUY':'All fundamentals are strong. Can consider buying with proper stop-loss.','BUY':'Good fundamentals. Monitor for a good entry price.','HOLD':'Mixed signals. If you own it, hold. Do not add more.','SELL':'Fundamentals weakening. Consider reducing position.','STRONG SELL':'Multiple red flags. Review your position urgently.'}.get(sig,'Review the numbers carefully before deciding.'))}_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 19. Global Macro Report ───────────────────────────────────────────────────

def format_global_macro_report(macro: dict) -> str:
    data = macro.get("data", {})
    lines = [
        "🌐 *GLOBAL MACRO SNAPSHOT*",
        "_These global factors directly affect the Indian stock market_",
        f"_{_esc(_now())}_",
        "",
    ]

    def _pct_fmt(v): return f"{v:+.2f}%" if v else "—"

    tbl = [f"{'Indicator':<18} {'Value':>10} {'Change':>9} {'Impact on India'}"]
    tbl.append("─" * 65)
    rows_info = [
        ("US 10Y Yield",   "US_10Y",    "%",  "Rising = FII outflows from India"),
        ("US Dollar (DXY)","DXY",       "",   "Stronger $ = FII selling India"),
        ("India 10Y Yield","INDIA_10Y", "%",  "Rising = costly loans for companies"),
        ("Brent Crude",    "CRUDE_WTI", "$",  "Rising = bad for auto/airline/FMCG"),
        ("Gold",           "GOLD",      "$",  "Rising = global fear/uncertainty"),
        ("Copper",         "COPPER",    "$",  "Falling = global slowdown warning"),
        ("US VIX",         "SP500_VIX", "",   "Above 25 = global risk-off"),
    ]
    for label, key, unit, impact in rows_info:
        d = data.get(key, {})
        val = d.get("price", 0)
        pct = d.get("pct",   0)
        arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "─")
        tbl.append(f"{label:<18} {unit+str(val):>10} {arrow+_pct_fmt(pct):>9}  {impact[:30]}")
    lines.append(_block(tbl))

    # Yield curve
    spread   = macro.get("spread", 0)
    inverted = macro.get("inverted", False)
    lines.append(_block([
        f"Yield Curve Spread  {spread:.3f}%  {'⚠️ INVERTED — Recession warning' if inverted else '✅ Normal'}",
    ]))

    # Signals
    sigs = macro.get("signals", [])
    if sigs:
        lines.append("*⚠️ ACTIVE ALERTS*")
        for s in sigs:
            sev_e = "🔴" if s["severity"]=="HIGH" else "🟡"
            lines.append(f"{sev_e} *{_esc(s['indicator'])}* — {_esc(s['meaning'])}")
            lines.append(f"   _Action: {_esc(s['action'])}_")
            lines.append("")

    lines += [
        "📖 *Beginner Guide:*",
        "_When US 10Y yield rises AND DXY rises = double trouble for India_",
        "_FIIs sell India and move money to US bonds (safer + better yield)_",
        "_Watch these two numbers every morning before trading_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 20. Breakout Scanner Report ───────────────────────────────────────────────

def format_breakout_report(scan: dict) -> str:
    lines = [
        "🚀 *BREAKOUT & ACCUMULATION SCANNER*",
        "_Stocks that are coiling, accumulating, or breaking out_",
        f"_{_esc(_now())}_",
        "",
    ]

    breakouts = scan.get("breakouts", [])
    if breakouts:
        lines.append("*🚀 BREAKOUTS — At or Near 52\\-Week High*")
        tbl = [f"{'Stock':<10} {'Price':>10} {'52W High':>10} {'Volume':>8} {'Status'}"]
        tbl.append("─" * 55)
        for r in breakouts[:5]:
            conf = "✅ Confirmed" if r["confirmed"] else "⚠️ Low Vol"
            tbl.append(f"{r['symbol']:<10} ₹{r['price']:>9,.2f} ₹{r['high52']:>9,.2f} {r['vol_ratio']:>6.1f}x  {conf}")
        lines.append(_block(tbl))
        lines.append("_Tip: Breakout + high volume = strongest buy signal in technical analysis_")
        lines.append("")

    accum = scan.get("accumulation", [])
    if accum:
        lines.append("*📦 ACCUMULATION — Quiet Buying Detected*")
        tbl = [f"{'Stock':<10} {'Price':>10} {'Vol Ratio':>10} {'Price Range':>12}"]
        tbl.append("─" * 48)
        for r in accum[:5]:
            tbl.append(f"{r['symbol']:<10} ₹{r['price']:>9,.2f} {r['vol_ratio']:>9.1f}x {r['price_range_pct']:>10.1f}%")
        lines.append(_block(tbl))
        lines.append("_High volume + tight price = someone is accumulating quietly_")
        lines.append("")

    consol = scan.get("consolidation", [])
    if consol:
        lines.append("*🔔 CONSOLIDATION — Big Move Coming*")
        for r in consol[:3]:
            lines.append(f"• *{_esc(r['symbol'])}* ₹{r['price']:,.2f} — {_esc(r['meaning'])}")
        lines.append("")

    rs = scan.get("rel_strength", [])
    if rs:
        lines.append("*💪 RELATIVE STRENGTH vs Nifty*")
        tbl = [f"{'Stock':<10} {'Price':>10} {'Stock Ret':>10} {'Nifty Ret':>10} {'RS Score':>9}"]
        tbl.append("─" * 55)
        for r in rs[:8]:
            flag = "✅" if r["outperform"] else "❌"
            tbl.append(f"{r['symbol']:<10} ₹{r['price']:>9,.2f} {r['stock_ret']:>+9.1f}%  {r['nifty_ret']:>+9.1f}%  {r['rs']:>7.1f} {flag}")
        lines.append(_block(tbl))

    lines += [
        "📖 *Beginner Guide:*",
        "_Breakout = price crossing its highest level in a year — very bullish_",
        "_Accumulation = someone buying quietly before big move_",
        "_Relative Strength > 100 = stock beating the index_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 21. News Sentiment Report ─────────────────────────────────────────────────

def format_sentiment_nlp_report(sent_data: list) -> str:
    lines = [
        "📰 *NEWS SENTIMENT REPORT*",
        "_Is the news about your stocks positive or negative?_",
        f"_{_esc(_now())}_",
        "",
    ]

    tbl = [f"{'Stock':<10} {'Today':>7} {'7d Avg':>7} {'Sentiment':<18} {'Flip?'}"]
    tbl.append("─" * 58)
    for s in sent_data:
        sym    = s["symbol"][:9]
        score  = s["today_score"]
        trend  = s["trend_avg"]
        sent   = s["sentiment"]
        flip   = "⚠️ FLIP!" if s.get("flip_alert") else "—"
        emoji  = "🟢" if score > 0 else ("🔴" if score < 0 else "⚪")
        tbl.append(f"{sym:<10} {emoji}{score:>+5.2f}  {trend:>+6.2f}  {sent:<18} {flip}")
    lines.append(_block(tbl))

    # Highlight flips
    flips = [s for s in sent_data if s.get("flip_alert")]
    if flips:
        lines.append("*⚠️ SENTIMENT FLIPS — Act Fast*")
        for s in flips:
            flip = s["sentiment_flip"].replace("_"," ")
            lines.append(f"• *{_esc(s['symbol'])}* — News turned {_esc(flip)}")
            if s.get("news"):
                top = s["news"][0]
                lines.append(f"  Latest: {_esc(top['title'][:60])}")

    lines += [
        "",
        "📖 *Guide:*",
        "_Positive score = good news = stock may rise_",
        "_Sentiment flip from positive to negative = sell alert_",
        "_Score below -1 for 3+ days = strong negative signal_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 22. Insider Trades Report ─────────────────────────────────────────────────

def format_insider_report(trades: list) -> str:
    lines = [
        "🏛️ *INSIDER TRADING REPORT*",
        "_Company directors and promoters buying/selling their own stock_",
        f"_{_esc(_now())}_",
        "",
    ]

    buys  = [t for t in trades if t["action"]=="BUY"]
    sells = [t for t in trades if t["action"]=="SELL"]

    if buys:
        lines.append("*🟢 INSIDER BUYING — Bullish Signal*")
        tbl = [f"{'Stock':<10} {'Person':<25} {'Qty':>10} {'Value':>10} {'Type'}"]
        tbl.append("─" * 65)
        for t in buys[:5]:
            mkt = "Open Mkt ✅" if t["is_open_market"] else "Other"
            tbl.append(f"{t['symbol']:<10} {t['person'][:24]:<25} {t['qty']:>10,} ₹{t['value_cr']:>7.1f}Cr  {mkt}")
        lines.append(_block(tbl))
        lines.append("_Open market buy = director using their OWN money = highest conviction_")
        lines.append("")

    if sells:
        lines.append("*🔴 INSIDER SELLING — Monitor Closely*")
        tbl = [f"{'Stock':<10} {'Person':<25} {'Qty':>10}"]
        tbl.append("─" * 48)
        for t in sells[:5]:
            tbl.append(f"{t['symbol']:<10} {t['person'][:24]:<25} {t['qty']:>10,}")
        lines.append(_block(tbl))
        lines.append("_Selling alone is not always bad — could be personal reasons_")
        lines.append("")

    lines += [
        "📖 *Guide:*",
        "_CEO/MD buying from open market = strongest possible buy signal_",
        "_Promoter selling = could mean they expect price to fall_",
        "_Multiple insiders selling = serious red flag — review your position_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 23. Correlation & Beta Report ─────────────────────────────────────────────

def format_correlation_report(corr: dict, beta: dict, drawdown: list) -> str:
    lines = [
        "🔗 *PORTFOLIO CORRELATION & RISK REPORT*",
        "_Are your stocks truly diversified or moving together?_",
        f"_{_esc(_now())}_",
        "",
    ]

    if beta:
        pb = beta.get("portfolio_beta", 1.0)
        lines.append("*📊 PORTFOLIO BETA*")
        lines.append(_block([
            f"Portfolio Beta   {pb:.2f}",
            f"Interpretation   {beta.get('interpretation','')}",
            f"Risk Level       {beta.get('risk_level','')}",
        ]))
        lines.append("_Beta > 1 means your portfolio falls MORE than Nifty when market drops_")
        lines.append("")

    if corr and corr.get("high_corr"):
        lines.append("*⚠️ HIGHLY CORRELATED PAIRS*")
        lines.append("_These stocks move together — holding both = hidden concentration_")
        tbl = [f"{'Stock 1':<12} {'Stock 2':<12} {'Correlation':>12} {'Risk'}"]
        tbl.append("─" * 45)
        for p in corr["high_corr"][:6]:
            tbl.append(f"{p['stock1']:<12} {p['stock2']:<12} {p['corr']:>12.3f}  {p['risk']}")
        lines.append(_block(tbl))
        lines.append("_Correlation > 0.8 = almost same risk. Consider removing one._")
        lines.append("")

    if drawdown:
        lines.append("*📉 DRAWDOWN SCENARIOS — If Market Falls*")
        tbl = [f"{'Scenario':<20} {'Estimated Loss':>16} {'Portfolio Left':>16}"]
        tbl.append("─" * 55)
        for d in drawdown:
            tbl.append(f"{d['scenario']:<20} ₹{d['est_loss']:>13,.0f}  ₹{d['rem_value']:>14,.0f}")
        lines.append(_block(tbl))
        lines.append("_This helps you prepare mentally and financially for market falls_")

    lines += [
        "",
        "📖 *What to do:*",
        "_Sell one stock from highly correlated pairs_",
        "_If portfolio beta > 1.3, reduce risky high-beta stocks_",
        "_Always keep 20% cash as buffer for drawdown opportunities_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)


# ── 24. Trade Journal Report ──────────────────────────────────────────────────

def format_journal_stats(stats: dict) -> str:
    if not stats or stats.get("total",0) == 0:
        return "\n".join([
            "📓 *TRADE JOURNAL*",
            "_No closed trades yet. Start logging your trades!_",
            f"\n_Hermes Agent · {_esc(_now())}_",
        ])

    grade = stats.get("grade","—")
    g_emoji = {"EXCELLENT":"🏆","GOOD":"🥇","AVERAGE":"🥈","NEEDS WORK":"🥉"}.get(grade,"—")

    lines = [
        "📓 *TRADE JOURNAL — PERFORMANCE REPORT*",
        f"_{_esc(_now())}_",
        "",
        f"{g_emoji} *Grade: {_esc(grade)}*",
        "",
    ]

    tbl = [
        f"Total Trades     {stats['total']}",
        f"Wins             {stats['wins']}  ({stats['win_rate']:.1f}%)",
        f"Losses           {stats['losses']}",
        f"Win Rate         {stats['win_rate']:.1f}%",
        f"Average Win      ₹{stats['avg_win']:,.2f}",
        f"Average Loss     ₹{stats['avg_loss']:,.2f}",
        f"Risk:Reward      {stats['rr_ratio']:.2f}",
        f"Expectancy       ₹{stats['expectancy']:,.2f} per trade",
        f"Total P&L        ₹{stats['total_pnl']:,.2f}",
    ]
    lines.append(_block(tbl))

    best  = stats.get("best_trade",{})
    worst = stats.get("worst_trade",{})
    if best:
        lines.append(_block([
            f"Best Trade   {best.get('symbol','')}  +₹{best.get('pnl',0):,.2f}",
            f"Worst Trade  {worst.get('symbol','')}  ₹{worst.get('pnl',0):,.2f}",
        ]))

    lines += [
        "📖 *What these numbers mean:*",
        "_Win Rate above 50% = more wins than losses_",
        "_Risk:Reward above 2 = profits cover losses even at 40% win rate_",
        "_Expectancy > 0 = your system makes money on average_",
        "",
        "_The goal: Win Rate 50%+ AND Risk:Reward 2:1 = consistently profitable_",
        f"\n_Hermes Agent · {_esc(_now())}_",
    ]
    return "\n".join(lines)
