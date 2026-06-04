#!/usr/bin/env python3
"""
Hermes Agent — First-Run Setup
Walks you through entering your Telegram credentials and tests the connection.
Run once before starting main.py.
"""

import os
import re
import sys
import requests

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.py")


def get_bot_info(token: str) -> dict | None:
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        data = resp.json()
        return data["result"] if data.get("ok") else None
    except Exception:
        return None


def get_chat_id(token: str) -> str | None:
    """Fetch the most recent chat ID from bot updates."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            timeout=10,
        )
        updates = resp.json().get("result", [])
        if updates:
            msg = updates[-1].get("message") or updates[-1].get("channel_post", {})
            chat = msg.get("chat", {})
            return str(chat.get("id", ""))
    except Exception:
        pass
    return None


def patch_config(token: str, chat_id: str):
    with open(CONFIG_PATH) as f:
        content = f.read()

    content = re.sub(
        r'TELEGRAM_BOT_TOKEN\s*=\s*".*?"',
        f'TELEGRAM_BOT_TOKEN = "{token}"',
        content,
    )
    content = re.sub(
        r'TELEGRAM_CHAT_ID\s*=\s*".*?"',
        f'TELEGRAM_CHAT_ID = "{chat_id}"',
        content,
    )

    with open(CONFIG_PATH, "w") as f:
        f.write(content)


def main():
    print("\n" + "=" * 55)
    print("  HERMES AGENT — FIRST-RUN SETUP")
    print("=" * 55)
    print()

    # Step 1: Bot token
    print("STEP 1 — Telegram Bot Token")
    print("  → Open Telegram, message @BotFather")
    print("  → Send /newbot and follow the prompts")
    print("  → Paste your bot token below\n")
    token = input("Bot token: ").strip()

    bot_info = get_bot_info(token)
    if not bot_info:
        print("❌ Invalid token or no internet. Check and retry.")
        sys.exit(1)
    print(f"✅ Connected as @{bot_info.get('username')}\n")

    # Step 2: Chat ID
    print("STEP 2 — Your Telegram Chat ID")
    print("  → Send any message to your new bot in Telegram now")
    print("  → Then press Enter here to auto-detect your chat ID\n")
    input("Press Enter after messaging the bot…")

    chat_id = get_chat_id(token)
    if chat_id:
        print(f"✅ Chat ID detected: {chat_id}\n")
    else:
        print("⚠️  Could not auto-detect. Find your chat ID at https://t.me/userinfobot")
        chat_id = input("Paste your chat ID: ").strip()

    # Step 3: Write to config
    patch_config(token, chat_id)
    print("✅ config.py updated.\n")

    # Step 4: Send test message
    print("Sending test message to Telegram…")
    payload = {
        "chat_id": chat_id,
        "text":    "✅ *Hermes Agent* connected successfully\\! You're all set\\.",
        "parse_mode": "MarkdownV2",
    }
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json=payload,
        timeout=10,
    )
    if resp.json().get("ok"):
        print("✅ Test message sent! Check Telegram.\n")
    else:
        print(f"⚠️  Message send failed: {resp.json()}\n")

    # Step 5: Install dependencies
    print("STEP 3 — Install Python dependencies")
    print("  Run this command:\n")
    print("  pip install yfinance requests schedule pytz\n")

    print("STEP 4 — Edit your portfolio")
    print("  Open config.py and set PORTFOLIO, WATCHLIST, and PRICE_ALERTS\n")

    print("STEP 5 — Start Hermes")
    print("  python main.py\n")
    print("=" * 55)
    print("  Setup complete. Hermes is ready.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
