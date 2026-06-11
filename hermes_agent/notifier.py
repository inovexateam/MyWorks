"""
Hermes — Multi-Channel Notifier + Claude AI Outlook
Telegram (primary) + SMS via Twilio (fallback for critical alerts).
Claude API for plain-English stock outlook.
"""

import logging
import os
import requests

log = logging.getLogger("hermes.notifier")


# ── SMS via Twilio ────────────────────────────────────────────────────────────

def send_sms(message: str, to_number: str = None) -> bool:
    """
    Send SMS via Twilio free tier.
    Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO in .env
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID","")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN","")
    from_number = os.getenv("TWILIO_FROM","")
    to_number   = to_number or os.getenv("TWILIO_TO","")

    if not all([account_sid, auth_token, from_number, to_number]):
        log.debug("Twilio not configured — skipping SMS")
        return False

    try:
        # Strip markdown for SMS
        clean = message.replace("*","").replace("_","").replace("`","").replace("\\","")
        clean = clean[:160]   # SMS limit

        url  = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {"From": from_number, "To": to_number, "Body": clean}
        r    = requests.post(url, data=data, auth=(account_sid, auth_token), timeout=15)
        if r.status_code in (200, 201):
            log.info(f"SMS sent to {to_number}")
            return True
        else:
            log.warning(f"SMS failed: {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        log.warning(f"SMS error: {e}")
        return False


def send_critical_alert(message: str, telegram_sender=None) -> bool:
    """
    For CRITICAL alerts: try Telegram first, fall back to SMS.
    """
    tg_ok = False
    if telegram_sender:
        tg_ok = telegram_sender.send(message)

    if not tg_ok:
        log.warning("Telegram failed for critical alert — trying SMS fallback")
        sms_ok = send_sms(message)
        return sms_ok

    return tg_ok


# ── Claude AI Outlook ─────────────────────────────────────────────────────────

def get_claude_outlook(
    symbol: str,
    ta_result: dict,
    fund_result: dict,
    signals: list,
    timeframe: str = "1 week",
) -> str | None:
    """
    Use Claude API to generate a plain-English stock outlook.
    Beginner-friendly: no jargon, clear action.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY","")
    if not api_key:
        log.debug("ANTHROPIC_API_KEY not set — skipping AI outlook")
        return None

    try:
        sym       = symbol.replace(".NS","")
        sig_texts = [s["summary"] for s in signals[:5] if s.get("symbol") == sym]

        prompt = f"""You are a stock market advisor helping a complete beginner understand their stock.

Stock: {sym}
Current Price: ₹{ta_result.get('price', 0):,.2f}

Technical Signals:
- RSI: {ta_result.get('rsi', 'N/A')} ({ta_result.get('rsi_signal', 'N/A')})
- Overall TA Signal: {ta_result.get('ta_signal', 'N/A')}
- MACD: {ta_result.get('macd_cross', 'N/A')}
- Above 50MA: {ta_result.get('above_ma50', 'N/A')}

Fundamental Score: {fund_result.get('overall', 'N/A') if fund_result else 'N/A'}
- P/E: {fund_result.get('pe', 'N/A') if fund_result else 'N/A'}
- ROE: {fund_result.get('roe', 'N/A') if fund_result else 'N/A'}%

Recent Signals: {chr(10).join(sig_texts) if sig_texts else 'None'}

Write a simple 3-4 sentence outlook for the next {timeframe} for a complete beginner.
Rules:
1. No jargon. If you use a term, explain it in brackets.
2. End with a clear action: BUY / HOLD / SELL / WAIT
3. Mention the biggest risk.
4. Keep it under 100 words.
"""

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )

        if response.status_code == 200:
            data    = response.json()
            content = data.get("content", [])
            text    = " ".join(block.get("text","") for block in content if block.get("type")=="text")
            return text.strip()
        else:
            log.warning(f"Claude API error: {response.status_code}")
            return None

    except Exception as e:
        log.warning(f"Claude outlook failed {symbol}: {e}")
        return None


def get_portfolio_claude_outlook(
    portfolio: list,
    portfolio_pnl: list,
    signals: list,
    rules_result: dict,
) -> str | None:
    """
    Claude AI summary for entire portfolio.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY","")
    if not api_key:
        return None

    try:
        verdict = rules_result.get("verdict","—")
        top_sigs = [s["summary"] for s in signals[:6] if s["severity"] in ("CRITICAL","HIGH")]

        holdings_text = "\n".join(
            f"- {r['symbol'].replace('.NS','')}: ₹{r.get('price',0):,.0f} "
            f"({'+'if r.get('total_pnl',0)>=0 else ''}₹{r.get('total_pnl',0):,.0f})"
            for r in portfolio_pnl[:5]
        )

        prompt = f"""You are a friendly stock advisor for a beginner investor in India.

Today's Market Status: {verdict}

Portfolio Holdings:
{holdings_text}

Top Signals Today:
{chr(10).join(top_sigs) if top_sigs else 'No critical signals'}

Write a friendly 4-5 sentence morning briefing for this beginner investor.
Rules:
1. Plain English only — explain any market term you use
2. Tell them what to watch today
3. Give one specific action if any
4. Reassure them if markets are volatile
5. Under 120 words
"""

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-sonnet-4-20250514",
                "max_tokens": 400,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )

        if response.status_code == 200:
            data    = response.json()
            content = data.get("content", [])
            text    = " ".join(block.get("text","") for block in content if block.get("type")=="text")
            return text.strip()
        return None
    except Exception as e:
        log.warning(f"Portfolio Claude outlook failed: {e}")
        return None
