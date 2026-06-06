"""
Hermes Agent — JSON Store
Single source of truth for runtime data.
All files live in data/ which is gitignored.
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

_FILES = {
    "alerts":   "alerts.json",
    "holdings": "holdings.json",
    "watchlist":"watchlist.json",
}

# ── Defaults (used on first run if no JSON exists yet) ───────────────────────

_DEFAULTS = {
    "alerts": [
        {"symbol": "RELIANCE.NS",  "condition": "below", "level": 2850.00, "cooldown_hours": 4},
        {"symbol": "HDFCBANK.NS",  "condition": "above", "level": 1780.00, "cooldown_hours": 4},
        {"symbol": "INFY.NS",      "condition": "below", "level": 1420.00, "cooldown_hours": 4},
        {"symbol": "TCS.NS",       "condition": "above", "level": 4200.00, "cooldown_hours": 4},
        {"symbol": "NIFTY50",      "condition": "above", "level": 24800.0, "cooldown_hours": 2},
        {"symbol": "SBIN.NS",      "condition": "below", "level": 820.00,  "cooldown_hours": 4},
    ],
    "holdings": [
        {"symbol": "RELIANCE.NS",  "qty": 50,  "avg_price": 2650.00},
        {"symbol": "TCS.NS",       "qty": 30,  "avg_price": 3820.00},
        {"symbol": "INFY.NS",      "qty": 80,  "avg_price": 1450.00},
        {"symbol": "HDFCBANK.NS",  "qty": 60,  "avg_price": 1750.00},
        {"symbol": "ICICIBANK.NS", "qty": 40,  "avg_price": 1020.00},
    ],
    "watchlist": [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
        "ICICIBANK.NS", "WIPRO.NS", "BAJFINANCE.NS", "SBIN.NS",
    ],
}


def _path(key: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, _FILES[key])


def load(key: str) -> list:
    """Load a JSON file. Returns default if file doesn't exist yet."""
    p = _path(key)
    if not os.path.exists(p):
        save(key, _DEFAULTS[key])   # seed on first run
        return list(_DEFAULTS[key])
    with open(p) as f:
        return json.load(f)


def save(key: str, data: list):
    """Write data to JSON file."""
    with open(_path(key), "w") as f:
        json.dump(data, f, indent=2)
