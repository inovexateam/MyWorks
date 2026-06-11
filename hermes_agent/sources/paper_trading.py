"""
Hermes — Paper Trading
Virtual ₹10L portfolio to test strategies without real money.
SQLite backed. Tracks virtual P&L, win rate, all trades.
"""

import sqlite3
import logging
import os
from datetime import datetime

log = logging.getLogger("hermes.paper_trading")

DB_PATH       = os.path.join(os.path.dirname(__file__), "..", "data", "paper_trading.db")
STARTING_CASH = 1_000_000.0   # ₹10 Lakh


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS pt_account (
            id         INTEGER PRIMARY KEY,
            cash       REAL DEFAULT 1000000,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS pt_positions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            qty         INTEGER NOT NULL,
            avg_price   REAL NOT NULL,
            entry_date  TEXT NOT NULL
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS pt_trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT NOT NULL,
            action      TEXT NOT NULL,
            qty         INTEGER NOT NULL,
            price       REAL NOT NULL,
            value       REAL NOT NULL,
            pnl         REAL,
            trade_date  TEXT NOT NULL,
            reason      TEXT
        )""")
        # Seed account if empty
        row = con.execute("SELECT id FROM pt_account").fetchone()
        if not row:
            con.execute("INSERT INTO pt_account (cash) VALUES (?)", (STARTING_CASH,))
        con.commit()


def get_cash() -> float:
    init_db()
    with _conn() as con:
        row = con.execute("SELECT cash FROM pt_account LIMIT 1").fetchone()
    return row[0] if row else STARTING_CASH


def get_positions() -> list:
    init_db()
    with _conn() as con:
        rows = con.execute("SELECT * FROM pt_positions").fetchall()
        cols = [d[0] for d in con.execute("PRAGMA table_info(pt_positions)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def paper_buy(symbol: str, qty: int, price: float, reason: str = "") -> dict:
    init_db()
    sym   = symbol.replace(".NS","").upper()
    value = round(qty * price, 2)
    cash  = get_cash()

    if value > cash:
        return {"success": False, "error": f"Insufficient cash. Have ₹{cash:,.0f}, need ₹{value:,.0f}"}

    with _conn() as con:
        # Update or create position
        pos = con.execute("SELECT * FROM pt_positions WHERE symbol=?", (sym,)).fetchone()
        if pos:
            old_qty   = pos[2]; old_avg = pos[3]
            new_qty   = old_qty + qty
            new_avg   = round((old_qty * old_avg + qty * price) / new_qty, 2)
            con.execute("UPDATE pt_positions SET qty=?, avg_price=? WHERE symbol=?",
                        (new_qty, new_avg, sym))
        else:
            con.execute("INSERT INTO pt_positions (symbol, qty, avg_price, entry_date) VALUES (?,?,?,?)",
                        (sym, qty, round(price,2), datetime.now().strftime("%Y-%m-%d")))
        # Deduct cash
        con.execute("UPDATE pt_account SET cash = cash - ?", (value,))
        # Log trade
        con.execute("INSERT INTO pt_trades (symbol,action,qty,price,value,trade_date,reason) VALUES (?,?,?,?,?,?,?)",
                    (sym,"BUY",qty,price,value,datetime.now().strftime("%Y-%m-%d"),reason))
        con.commit()

    log.info(f"Paper BUY: {sym} {qty}@{price} = ₹{value:,.0f}")
    return {"success": True, "symbol": sym, "qty": qty, "price": price, "value": value}


def paper_sell(symbol: str, qty: int, price: float, reason: str = "") -> dict:
    init_db()
    sym = symbol.replace(".NS","").upper()
    with _conn() as con:
        pos = con.execute("SELECT * FROM pt_positions WHERE symbol=?", (sym,)).fetchone()
        if not pos or pos[2] < qty:
            held = pos[2] if pos else 0
            return {"success": False, "error": f"Only {held} shares held, cannot sell {qty}"}

        avg_price = pos[3]
        pnl       = round((price - avg_price) * qty, 2)
        value     = round(qty * price, 2)
        new_qty   = pos[2] - qty

        if new_qty == 0:
            con.execute("DELETE FROM pt_positions WHERE symbol=?", (sym,))
        else:
            con.execute("UPDATE pt_positions SET qty=? WHERE symbol=?", (new_qty, sym))

        con.execute("UPDATE pt_account SET cash = cash + ?", (value,))
        con.execute("INSERT INTO pt_trades (symbol,action,qty,price,value,pnl,trade_date,reason) VALUES (?,?,?,?,?,?,?,?)",
                    (sym,"SELL",qty,price,value,pnl,datetime.now().strftime("%Y-%m-%d"),reason))
        con.commit()

    log.info(f"Paper SELL: {sym} {qty}@{price} PnL=₹{pnl:,.0f}")
    return {"success": True, "symbol": sym, "qty": qty, "price": price, "pnl": pnl}


def get_portfolio_summary(current_prices: dict = None) -> dict:
    init_db()
    positions = get_positions()
    cash      = get_cash()

    rows = []
    total_invested = 0
    total_market   = 0

    for p in positions:
        sym       = p["symbol"]
        qty       = p["qty"]
        avg       = p["avg_price"]
        invested  = qty * avg
        cur_price = (current_prices or {}).get(sym, avg)
        market_val= qty * cur_price
        pnl       = market_val - invested
        pnl_pct   = round((pnl / invested) * 100, 2) if invested else 0

        total_invested += invested
        total_market   += market_val

        rows.append({
            "symbol":     sym,
            "qty":        qty,
            "avg_price":  avg,
            "cur_price":  round(cur_price, 2),
            "invested":   round(invested, 2),
            "market_val": round(market_val, 2),
            "pnl":        round(pnl, 2),
            "pnl_pct":    pnl_pct,
        })

    total_value = total_market + cash
    total_pnl   = total_value - STARTING_CASH

    return {
        "cash":          round(cash, 2),
        "positions":     rows,
        "total_invested":round(total_invested, 2),
        "total_market":  round(total_market, 2),
        "total_value":   round(total_value, 2),
        "total_pnl":     round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / STARTING_CASH) * 100, 2),
        "starting_cash": STARTING_CASH,
    }


def get_trade_history(limit: int = 50) -> list:
    init_db()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM pt_trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        cols = [d[0] for d in con.execute("PRAGMA table_info(pt_trades)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def reset_paper_portfolio():
    init_db()
    with _conn() as con:
        con.execute("DELETE FROM pt_positions")
        con.execute("DELETE FROM pt_trades")
        con.execute("UPDATE pt_account SET cash=?", (STARTING_CASH,))
        con.commit()
    log.info("Paper portfolio reset to ₹10L cash.")
