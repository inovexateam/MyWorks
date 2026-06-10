"""
Hermes — Trade Journal
SQLite-backed journal for all trades.
Tracks: win rate, avg win, avg loss, R:R, best/worst setups.
The single most important tool for improving as a trader.
"""

import sqlite3
import logging
import os
from datetime import datetime

log = logging.getLogger("hermes.journal")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "journal.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            entry_date  TEXT NOT NULL,
            exit_date   TEXT,
            entry_price REAL NOT NULL,
            exit_price  REAL,
            qty         INTEGER NOT NULL,
            side        TEXT DEFAULT 'BUY',
            stop_loss   REAL,
            target      REAL,
            reason      TEXT,
            exit_reason TEXT,
            pnl         REAL,
            pnl_pct     REAL,
            status      TEXT DEFAULT 'OPEN',
            tags        TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS mistakes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id   INTEGER,
            mistake    TEXT,
            lesson     TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.commit()


def add_trade(symbol: str, entry_price: float, qty: int,
              entry_date: str = None, stop_loss: float = None,
              target: float = None, reason: str = "", tags: str = "",
              side: str = "BUY") -> int:
    init_db()
    entry_date = entry_date or datetime.now().strftime("%Y-%m-%d")
    with _conn() as con:
        cur = con.execute("""
        INSERT INTO trades (symbol, entry_date, entry_price, qty, side, stop_loss, target, reason, tags, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
        """, (symbol.upper(), entry_date, entry_price, qty, side, stop_loss, target, reason, tags))
        con.commit()
        log.info(f"Trade added: {symbol} {side} {qty}@{entry_price}")
        return cur.lastrowid


def close_trade(trade_id: int, exit_price: float,
                exit_date: str = None, exit_reason: str = "",
                notes: str = "") -> dict:
    init_db()
    exit_date = exit_date or datetime.now().strftime("%Y-%m-%d")
    with _conn() as con:
        row = con.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            return {}
        cols    = [d[0] for d in con.execute("PRAGMA table_info(trades)").fetchall()]
        trade   = dict(zip(cols, row))
        entry   = trade["entry_price"]
        qty     = trade["qty"]
        side    = trade["side"]
        pnl     = round((exit_price - entry) * qty * (1 if side=="BUY" else -1), 2)
        pnl_pct = round((exit_price - entry) / entry * 100 * (1 if side=="BUY" else -1), 2)
        status  = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAK_EVEN")
        con.execute("""
        UPDATE trades SET exit_price=?, exit_date=?, exit_reason=?,
        pnl=?, pnl_pct=?, status=?, notes=? WHERE id=?
        """, (exit_price, exit_date, exit_reason, pnl, pnl_pct, status, notes, trade_id))
        con.commit()
        log.info(f"Trade closed: #{trade_id} {status} PnL={pnl}")
        return {"trade_id": trade_id, "pnl": pnl, "pnl_pct": pnl_pct, "status": status}


def get_open_trades() -> list:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM trades WHERE status='OPEN' ORDER BY entry_date DESC").fetchall()
        cols = [d[0] for d in con.execute("PRAGMA table_info(trades)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def get_closed_trades(limit: int = 50) -> list:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM trades WHERE status != 'OPEN' ORDER BY exit_date DESC LIMIT ?",
            (limit,)).fetchall()
        cols = [d[0] for d in con.execute("PRAGMA table_info(trades)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def get_performance_stats() -> dict:
    init_db()
    trades = get_closed_trades(limit=1000)
    if not trades:
        return {"total": 0}

    wins   = [t for t in trades if t["status"]=="WIN"]
    losses = [t for t in trades if t["status"]=="LOSS"]
    total  = len(trades)

    win_rate   = round(len(wins) / total * 100, 1) if total > 0 else 0
    avg_win    = round(sum(t["pnl"] for t in wins)   / len(wins),   2) if wins   else 0
    avg_loss   = round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0
    total_pnl  = round(sum(t["pnl"] for t in trades), 2)
    expectancy = round((win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss), 2)
    rr_ratio   = round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else 0

    # Best and worst trades
    best  = max(trades, key=lambda x: x["pnl"] or 0)
    worst = min(trades, key=lambda x: x["pnl"] or 0)

    # Per-symbol stats
    by_sym = {}
    for t in trades:
        sym = t["symbol"]
        if sym not in by_sym:
            by_sym[sym] = {"wins":0,"losses":0,"pnl":0}
        if t["status"]=="WIN":   by_sym[sym]["wins"]   += 1
        elif t["status"]=="LOSS":by_sym[sym]["losses"] += 1
        by_sym[sym]["pnl"] += (t["pnl"] or 0)

    return {
        "total":      total,
        "wins":       len(wins),
        "losses":     len(losses),
        "win_rate":   win_rate,
        "avg_win":    avg_win,
        "avg_loss":   avg_loss,
        "total_pnl":  total_pnl,
        "expectancy": expectancy,
        "rr_ratio":   rr_ratio,
        "best_trade": best,
        "worst_trade":worst,
        "by_symbol":  by_sym,
        "grade": (
            "EXCELLENT" if win_rate>=60 and rr_ratio>=2 else
            "GOOD"      if win_rate>=50 and rr_ratio>=1.5 else
            "AVERAGE"   if win_rate>=40 else
            "NEEDS WORK"
        ),
    }


def add_mistake(trade_id: int, mistake: str, lesson: str):
    init_db()
    with _conn() as con:
        con.execute("INSERT INTO mistakes (trade_id, mistake, lesson) VALUES (?,?,?)",
                    (trade_id, mistake, lesson))
        con.commit()


def get_all_trades(limit: int = 100) -> list:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        cols = [d[0] for d in con.execute("PRAGMA table_info(trades)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]
