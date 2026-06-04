"""
Hermes Agent — Telegram Sender
Handles all outbound messages to your Telegram chat.
"""

import requests
import logging
import time

log = logging.getLogger("hermes.telegram")


class TelegramSender:
    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token: str, chat_id: str):
        self.token   = token
        self.chat_id = chat_id

    def _url(self, method: str) -> str:
        return self.BASE_URL.format(token=self.token, method=method)

    def send(self, text: str, parse_mode: str = "MarkdownV2", retries: int = 3) -> bool:
        """Send a message. Returns True on success."""
        payload = {
            "chat_id":    self.chat_id,
            "text":       text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(
                    self._url("sendMessage"),
                    json=payload,
                    timeout=15,
                )
                data = resp.json()
                if data.get("ok"):
                    log.info("Message sent successfully.")
                    return True
                else:
                    log.error(f"Telegram API error: {data.get('description')}")
                    # If parse error, fall back to plain text
                    if "parse" in str(data.get("description", "")).lower() and parse_mode != "HTML":
                        log.warning("Retrying with plain text due to parse error.")
                        return self.send(text, parse_mode="", retries=1)
            except requests.RequestException as e:
                log.warning(f"Send attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
        return False

    def send_long(self, text: str, parse_mode: str = "MarkdownV2") -> bool:
        """
        Telegram max message length is 4096 chars.
        Split long messages and send in parts.
        """
        max_len = 4000
        if len(text) <= max_len:
            return self.send(text, parse_mode)

        parts = []
        while text:
            # Split at last newline before limit
            chunk = text[:max_len]
            split_at = chunk.rfind("\n")
            if split_at == -1:
                split_at = max_len
            parts.append(text[:split_at])
            text = text[split_at:].lstrip("\n")

        success = True
        for i, part in enumerate(parts, 1):
            suffix = f"\n_\\({i}/{len(parts)}\\)_" if len(parts) > 1 else ""
            ok = self.send(part + suffix, parse_mode)
            if not ok:
                success = False
            time.sleep(0.5)  # Telegram rate limit
        return success

    def test_connection(self) -> bool:
        """Ping Telegram to verify bot token and chat ID are valid."""
        try:
            resp = requests.get(self._url("getMe"), timeout=10)
            data = resp.json()
            if not data.get("ok"):
                log.error(f"Bot token invalid: {data}")
                return False
            bot_name = data["result"].get("username", "unknown")
            log.info(f"Connected as @{bot_name}")
            return True
        except Exception as e:
            log.error(f"Connection test failed: {e}")
            return False
