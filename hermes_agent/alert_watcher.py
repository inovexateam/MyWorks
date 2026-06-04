"""
Hermes Agent — Alert Watcher
Polls prices during market hours and fires Telegram alerts the moment
any configured level is breached. Cooldown prevents alert spam.
"""

import time
import json
import os
import logging
from datetime import datetime, timedelta

from data_fetcher import get_price
from formatter import format_price_alert

log = logging.getLogger("hermes.alerts")

STATE_FILE = os.path.join(os.path.dirname(__file__), "data", "alert_state.json")


class AlertWatcher:
    def __init__(self, alerts: list, sender, poll_seconds: int = 30):
        """
        alerts      : list of alert dicts from config.py
        sender      : TelegramSender instance
        poll_seconds: how often to check prices
        """
        self.alerts       = alerts
        self.sender       = sender
        self.poll_seconds = poll_seconds
        self.state        = self._load_state()

    # ── State persistence (survives restarts) ────────────────────────────────

    def _load_state(self) -> dict:
        """Load last-fired timestamps from disk."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_state(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def _alert_key(self, alert: dict) -> str:
        return f"{alert['symbol']}_{alert['condition']}_{alert['level']}"

    def _on_cooldown(self, alert: dict) -> bool:
        key         = self._alert_key(alert)
        last_fired  = self.state.get(key)
        if not last_fired:
            return False
        cooldown_h  = alert.get("cooldown_hours", 4)
        fired_at    = datetime.fromisoformat(last_fired)
        return datetime.now() < fired_at + timedelta(hours=cooldown_h)

    def _mark_fired(self, alert: dict):
        key = self._alert_key(alert)
        self.state[key] = datetime.now().isoformat()
        self._save_state()

    # ── Price check ──────────────────────────────────────────────────────────

    def _check_alert(self, alert: dict, price: float) -> bool:
        """Return True if the alert condition is met."""
        if alert["condition"] == "above":
            return price >= alert["level"]
        if alert["condition"] == "below":
            return price <= alert["level"]
        return False

    # ── Previous-price cache (detect crossings, not just levels) ─────────────

    def _prev_key(self, alert: dict) -> str:
        return f"prev_{self._alert_key(alert)}"

    def _crossed(self, alert: dict, prev: float | None, current: float) -> bool:
        """
        True only on a fresh crossing — price moving through the level.
        This prevents re-firing when price sits on the level all day.
        """
        if prev is None:
            # First run: fire if condition already met
            return self._check_alert(alert, current)

        if alert["condition"] == "above":
            return prev < alert["level"] <= current
        if alert["condition"] == "below":
            return prev > alert["level"] >= current
        return False

    # ── Main poll loop ────────────────────────────────────────────────────────

    def poll_once(self):
        """Run a single poll cycle across all alerts."""
        for alert in self.alerts:
            if self._on_cooldown(alert):
                continue

            sym   = alert["symbol"]
            price = get_price(sym)
            if price is None:
                log.warning(f"Could not fetch price for {sym}")
                continue

            prev_key = self._prev_key(alert)
            prev     = self.state.get(prev_key)
            if prev is not None:
                prev = float(prev)

            if self._crossed(alert, prev, price):
                log.info(f"ALERT TRIGGERED: {sym} {alert['condition']} {alert['level']} @ {price}")
                msg = format_price_alert(
                    symbol        = sym,
                    condition     = alert["condition"],
                    level         = alert["level"],
                    current_price = price,
                )
                sent = self.sender.send(msg)
                if sent:
                    self._mark_fired(alert)
                else:
                    log.error(f"Failed to send alert for {sym}")

            # Always update previous price
            self.state[prev_key] = price
        self._save_state()

    def run(self, market_open_fn):
        """
        Continuously poll during market hours.
        market_open_fn() -> bool: returns True when market is open.
        Blocks forever — run in a thread or process.
        """
        log.info(f"Alert watcher started. Polling every {self.poll_seconds}s during market hours.")
        while True:
            if market_open_fn():
                try:
                    self.poll_once()
                except Exception as e:
                    log.exception(f"Unexpected error in poll_once: {e}")
            else:
                log.debug("Market closed. Alert watcher sleeping.")
            time.sleep(self.poll_seconds)
