# Hermes Agent 🪽
**Your personal stock market intelligence agent. Free. Open source. Runs 24/7.**

---

## What it does

| Time | Task |
|------|------|
| **08:00 IST** | Morning Brief — indices, FII/DII flow, portfolio P&L, stock news, upcoming earnings |
| **Market hours** | Price Alerts — fires the moment any stock crosses your set level |
| **15:45 IST** | 52W Range Report — where each stock sits, danger flags if near 52W low |
| **Daily** | Earnings reminder — 3-day advance warning before any result day |

All delivered to your **Telegram** as formatted messages. One agent, zero subscriptions.

---

## Quick Start

### 1. Clone / download
```bash
# Place all files in a folder called hermes_agent/
cd hermes_agent/
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create your Telegram bot
1. Open Telegram → message **@BotFather**
2. Send `/newbot` → follow prompts → copy the token
3. Send any message to your new bot

### 4. Run setup
```bash
python setup.py
```
This auto-detects your chat ID, patches `config.py`, and sends a test message.

### 5. Edit your portfolio
Open `config.py` and fill in:
```python
PORTFOLIO = [
    {"symbol": "RELIANCE.NS", "qty": 50, "avg_price": 2650.00},
    # add your stocks...
]

PRICE_ALERTS = [
    {"symbol": "RELIANCE.NS", "condition": "below", "level": 2850.00, "cooldown_hours": 4},
    # add your alerts...
]
```

**Symbol format**: Use Yahoo Finance NSE tickers — append `.NS` for NSE stocks.
Examples: `RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `INFY.NS`, `SBIN.NS`

### 6. Start Hermes
```bash
python main.py
```

---

## File Structure

```
hermes_agent/
├── main.py            # Scheduler — entry point
├── config.py          # Your portfolio, alerts, credentials
├── data_fetcher.py    # Yahoo Finance + NSE data layer
├── formatter.py       # Telegram message builder (all 4 formats)
├── telegram_sender.py # Telegram API wrapper
├── alert_watcher.py   # Real-time price polling during market hours
├── setup.py           # One-time setup wizard
├── requirements.txt
├── data/
│   └── alert_state.json   # Persists alert cooldown state across restarts
└── logs/
    └── hermes.log         # Full event log
```

---

## Running 24/7

### Option A — systemd (Linux server / Raspberry Pi)
```ini
# /etc/systemd/system/hermes.service
[Unit]
Description=Hermes Stock Agent
After=network.target

[Service]
WorkingDirectory=/path/to/hermes_agent
ExecStart=/usr/bin/python3 /path/to/hermes_agent/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable hermes
sudo systemctl start hermes
sudo systemctl status hermes
```

### Option B — Screen (quick and easy)
```bash
screen -S hermes
python main.py
# Ctrl+A then D to detach
# screen -r hermes to reattach
```

### Option C — Raspberry Pi
A Pi Zero 2W (~₹2,000) runs Hermes 24/7 at <3W power draw.
Same setup as Linux above.

### Option D — Free cloud (Render / Railway)
Deploy as a background worker. Set environment variables instead of hardcoding in config.py for security.

---

## Configuration Reference

```python
# config.py — key settings

DANGER_ZONE_PCT       = 8.0   # % above 52W low to flag as danger
EARNINGS_REMINDER_DAYS = 3    # days before earnings to send reminder
MORNING_BRIEF_TIME    = "08:00"  # IST, 24h
AFTER_MARKET_TIME     = "15:45"  # IST, 24h
ALERT_POLL_SECONDS    = 30    # price check frequency during market hours
```

---

## Data Sources
- **Prices / 52W / Earnings**: Yahoo Finance via `yfinance` (free, no API key)
- **FII/DII**: NSE India public endpoint (free)
- **News**: Yahoo Finance news feed per ticker (free)

---

## Limitations
- Yahoo Finance data has ~15 min delay for free tier
- FII/DII data is provisional and updates post-market
- Earnings dates from yfinance may occasionally be missing for smaller stocks

---

## License
MIT — free to use, modify, and self-host.
