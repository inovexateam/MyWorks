"""
Hermes Agent — Tkinter GUI v2
Full dashboard wired to all v2 sources and signal engine.

Tabs: Portfolio | Indices & Macro | Alerts | Signals | 52W Range | Earnings | Corporate Actions | Holdings
Right panel: market status, manual triggers, schedule, live log

Run:  python gui.py
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import logging
import schedule
import pytz
from datetime import datetime
import sys
import os
import re

sys.path.insert(0, os.path.dirname(__file__))

import config
from store import load as store_load, save as store_save
from data_fetcher import (
    get_indices, get_portfolio_pnl, get_fii_dii_data,
    get_news_headlines, get_52w_analysis, get_earnings_calendar,
)
from formatter import (
    format_52w_report, format_earnings_reminder,
    format_signal_digest, format_corporate_action_alert,
    format_macro_alert, format_deal_alert,
    format_morning_brief_extended,
)
from telegram_sender import TelegramSender
from alert_watcher import AlertWatcher
from signals import collect_all_signals, filter_by_timeframe
from sources.nse import get_bulk_deals, get_block_deals, get_circuit_stocks, get_fii_dii_trend
from sources.bse import get_corporate_actions
from sources.macro import (
    get_upcoming_macro_events, get_high_impact_news,
    get_crude_price, get_inr_usd, get_global_markets,
)
from sources.technicals import analyze_watchlist, analyze
from risk import (
    pre_trade_checklist, portfolio_risk_analysis,
    get_stop_loss, get_position_size, TrailingStopTracker,
)

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":        "#0b0d0f", "bg2": "#111417", "bg3": "#181c20", "bg4": "#1e2328",
    "border":    "#2a2f36", "border2": "#353c45",
    "text":      "#e8eaed", "muted": "#7a8290", "dim": "#4a5260",
    "green":     "#22c55e", "red": "#ef4444", "amber": "#f59e0b",
    "blue":      "#3b82f6", "purple": "#a78bfa", "teal": "#2dd4bf",
    "green_dim": "#14532d", "red_dim": "#450a0a", "amber_dim": "#451a03",
}

IST = pytz.timezone("Asia/Kolkata")
log_queue: queue.Queue = queue.Queue()


class QueueLogHandler(logging.Handler):
    def emit(self, record):
        log_queue.put(("log", self.format(record)))


os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    handlers=[
        QueueLogHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "logs", "hermes.log")),
    ],
)
log = logging.getLogger("hermes.gui")

sender = TelegramSender(token=config.TELEGRAM_BOT_TOKEN, chat_id=config.TELEGRAM_CHAT_ID)


# ── Reusable widgets ──────────────────────────────────────────────────────────

class SectionLabel(tk.Label):
    def __init__(self, parent, text, **kw):
        super().__init__(parent, text=text.upper(), bg=C["bg"], fg=C["dim"],
                         font=("Courier", 8), anchor="w", **kw)

class Card(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["bg2"], highlightbackground=C["border"],
                         highlightthickness=1, padx=10, pady=8, **kw)

class HermesButton(tk.Button):
    def __init__(self, parent, text, command, accent=False, **kw):
        col = C["green"] if accent else C["muted"]
        super().__init__(parent, text=text, command=command,
                         bg=C["bg3"], fg=col, activebackground=C["bg4"],
                         activeforeground=C["text"], relief="flat",
                         highlightbackground=C["border"], highlightthickness=1,
                         font=("Courier", 9, "bold"), padx=10, pady=4, cursor="hand2", **kw)

    def set_busy(self, busy: bool):
        self.config(state="disabled" if busy else "normal",
                    fg=C["dim"] if busy else C["green"])


# ── Main Application ──────────────────────────────────────────────────────────

class HermesGUI:
    def __init__(self, root: tk.Tk):
        self.root    = root
        self.root.title("Hermes Agent v2")
        self.root.configure(bg=C["bg"])
        self.root.minsize(1100, 720)
        self.running = True
        self.alert_vars: dict[str, tk.BooleanVar] = {}
        self.alert_editing_idx = None
        self.signals_cache: list = []

        self.watcher = AlertWatcher(
            alerts=config.PRICE_ALERTS, sender=sender,
            poll_seconds=config.ALERT_POLL_SECONDS,
        )
        self.trail_tracker = TrailingStopTracker()
        self.ta_cache: list = []

        self._build_ui()
        self._start_background_threads()
        self._poll_queue()
        self.root.after(800, self._refresh_portfolio)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Topbar
        top = tk.Frame(self.root, bg=C["bg"], pady=10, padx=16)
        top.pack(fill="x")
        tk.Label(top, text="H", bg=C["bg"], fg=C["green"],
                 font=("Courier", 20, "bold")).pack(side="left")
        tk.Label(top, text="ERMES", bg=C["bg"], fg=C["text"],
                 font=("Courier", 20, "bold")).pack(side="left")
        tk.Label(top, text=" / agent v2", bg=C["bg"], fg=C["muted"],
                 font=("Courier", 11)).pack(side="left", padx=(4, 0))

        right = tk.Frame(top, bg=C["bg"])
        right.pack(side="right")
        self.status_dot   = tk.Label(right, text="●", bg=C["bg"], fg=C["green"], font=("Courier", 12))
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(right, text="INITIALISING…", bg=C["bg"], fg=C["muted"], font=("Courier", 9))
        self.status_label.pack(side="left", padx=(4, 12))
        self.clock_label  = tk.Label(right, text="", bg=C["bg"], fg=C["muted"], font=("Courier", 9))
        self.clock_label.pack(side="left")

        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")

        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=C["bg"], padx=16, pady=12)
        left.pack(side="left", fill="both", expand=True)

        right_panel = tk.Frame(body, bg=C["bg"], padx=0, pady=0, width=300)
        right_panel.pack(side="right", fill="y")
        right_panel.pack_propagate(False)

        # Notebook
        style = ttk.Style()
        style.theme_use("default")
        style.configure("H.TNotebook", background=C["bg"], borderwidth=0, tabmargins=0)
        style.configure("H.TNotebook.Tab", background=C["bg3"], foreground=C["muted"],
                         font=("Courier", 8, "bold"), padding=[10, 5], borderwidth=0)
        style.map("H.TNotebook.Tab",
                  background=[("selected", C["bg4"])], foreground=[("selected", C["text"])])

        self.notebook = ttk.Notebook(left, style="H.TNotebook")
        self.notebook.pack(fill="both", expand=True)

        self._build_tab_portfolio()
        self._build_tab_indices()
        self._build_tab_alerts()
        self._build_tab_signals()
        self._build_tab_technicals()
        self._build_tab_risk()
        self._build_tab_market_pulse()
        self._build_tab_52w()
        self._build_tab_earnings()
        self._build_tab_corporate()
        self._build_tab_fundamentals()
        self._build_tab_journal()
        self._build_tab_holdings()

        self._build_right_panel(right_panel)
        self._tick_clock()

    # ── Tab: Portfolio ────────────────────────────────────────────────────────

    def _build_tab_portfolio(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Portfolio  ")
        SectionLabel(f, "Live Portfolio P&L").pack(anchor="w", pady=(10, 4))

        cards = tk.Frame(f, bg=C["bg"])
        cards.pack(fill="x", pady=(0, 8))
        self.pnl_day_val   = self._metric_card(cards, "Day P&L",     "—")
        self.pnl_total_val = self._metric_card(cards, "Overall P&L", "—")
        self.pnl_value_val = self._metric_card(cards, "Market Value","—")
        self.pnl_inv_val   = self._metric_card(cards, "Invested",    "—")

        cols = ("Symbol","Price","Chg%","Qty","Avg","Day P&L","Total P&L","Total P&L%","Value")
        self.port_tree = self._make_tree(f, cols, heights=10)
        self.port_tree.pack(fill="both", expand=True, pady=(0, 8))
        widths = [110,90,70,60,90,90,90,90,90]
        for col, w in zip(cols, widths):
            self.port_tree.heading(col, text=col)
            self.port_tree.column(col, anchor="center", width=w, minwidth=60)
        self.port_tree.column("Symbol", anchor="w")

        btn_row = tk.Frame(f, bg=C["bg"])
        btn_row.pack(fill="x")
        self.refresh_btn = HermesButton(btn_row, "↻  REFRESH", self._refresh_portfolio, accent=True)
        self.refresh_btn.pack(side="left")
        self.last_refresh_lbl = tk.Label(btn_row, text="", bg=C["bg"], fg=C["dim"], font=("Courier", 8))
        self.last_refresh_lbl.pack(side="left", padx=10)

    # ── Tab: Indices & Macro ──────────────────────────────────────────────────

    def _build_tab_indices(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Indices & Macro  ")

        # Split into two columns
        left_col  = tk.Frame(f, bg=C["bg"])
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=10)
        right_col = tk.Frame(f, bg=C["bg"])
        right_col.pack(side="left", fill="both", expand=True, pady=10)

        # Indices
        SectionLabel(left_col, "NSE Indices").pack(anchor="w", pady=(0, 4))
        cols = ("Index","Price","Change","Chg%")
        self.idx_tree = self._make_tree(left_col, cols, heights=5)
        self.idx_tree.pack(fill="x")
        for col in cols:
            self.idx_tree.heading(col, text=col)
            self.idx_tree.column(col, anchor="center", width=110, minwidth=80)
        self.idx_tree.column("Index", anchor="w", width=150)

        # Global markets
        SectionLabel(left_col, "Global Markets").pack(anchor="w", pady=(12, 4))
        gcols = ("Market","Price","Chg%")
        self.global_tree = self._make_tree(left_col, gcols, heights=7)
        self.global_tree.pack(fill="x")
        for col in gcols:
            self.global_tree.heading(col, text=col)
            self.global_tree.column(col, anchor="center", width=110, minwidth=80)
        self.global_tree.column("Market", anchor="w", width=150)

        HermesButton(left_col, "↻  REFRESH", self._refresh_indices).pack(anchor="w", pady=(8, 0))

        # Macro panel (right)
        SectionLabel(right_col, "Macro Indicators").pack(anchor="w", pady=(0, 4))
        macro_card = Card(right_col)
        macro_card.pack(fill="x", pady=(0, 10))
        self.macro_labels: dict[str, tk.Label] = {}
        for key, lbl in [("crude","Brent Crude"),("inr","INR/USD"),
                          ("fii_net","FII Net"),("dii_net","DII Net")]:
            row = tk.Frame(macro_card, bg=C["bg2"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=lbl+":", bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 8), width=14, anchor="w").pack(side="left")
            v = tk.Label(row, text="—", bg=C["bg2"], fg=C["text"], font=("Courier", 9, "bold"))
            v.pack(side="left")
            self.macro_labels[key] = v

        SectionLabel(right_col, "Macro Events — Next 30 Days").pack(anchor="w", pady=(8, 4))
        cols = ("Event","Date","Days","Impact")
        self.macro_tree = self._make_tree(right_col, cols, heights=8)
        self.macro_tree.pack(fill="x")
        widths2 = [200, 90, 50, 70]
        for col, w in zip(cols, widths2):
            self.macro_tree.heading(col, text=col)
            self.macro_tree.column(col, anchor="center", width=w, minwidth=40)
        self.macro_tree.column("Event", anchor="w")
        self.macro_tree.tag_configure("high",   foreground=C["red"])
        self.macro_tree.tag_configure("medium", foreground=C["amber"])

        SectionLabel(right_col, "FII / DII Flow").pack(anchor="w", pady=(10, 4))
        fii_card = Card(right_col)
        fii_card.pack(fill="x")
        self.fii_labels: dict[str, tk.Label] = {}
        for key, lbl in [("fii_buy","FII Buy"),("fii_sell","FII Sell"),
                          ("dii_buy","DII Buy"),("dii_sell","DII Sell")]:
            row = tk.Frame(fii_card, bg=C["bg2"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=lbl+":", bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 8), width=12, anchor="w").pack(side="left")
            v = tk.Label(row, text="—", bg=C["bg2"], fg=C["text"], font=("Courier", 8, "bold"))
            v.pack(side="left")
            self.fii_labels[key] = v

    # ── Tab: Alerts ───────────────────────────────────────────────────────────

    def _build_tab_alerts(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Alerts  ")

        SectionLabel(f, "Add / Edit Alert").pack(anchor="w", pady=(10, 4))
        form = Card(f)
        form.pack(fill="x", pady=(0, 8))

        r1 = tk.Frame(form, bg=C["bg2"])
        r1.pack(fill="x", pady=(0, 6))
        for lbl, var_attr, w, default in [
            ("Symbol",     "alert_sym_var",   14, "RELIANCE.NS"),
            ("Level ₹",    "alert_level_var", 10, ""),
            ("Cooldown h", "alert_cool_var",  6,  "4"),
        ]:
            tk.Label(r1, text=lbl, bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 8), width=10, anchor="w").pack(side="left")
            v = tk.StringVar(value=default)
            setattr(self, var_attr, v)
            e = tk.Entry(r1, textvariable=v, bg=C["bg3"], fg=C["text"],
                         insertbackground=C["text"], relief="flat",
                         font=("Courier", 10), width=w,
                         highlightbackground=C["border"], highlightthickness=1)
            e.pack(side="left", padx=(0, 12))

        r2 = tk.Frame(form, bg=C["bg2"])
        r2.pack(fill="x")
        tk.Label(r2, text="Condition", bg=C["bg2"], fg=C["muted"],
                 font=("Courier", 8), width=10, anchor="w").pack(side="left")
        self.alert_cond_var = tk.StringVar(value="below")
        ttk.Combobox(r2, textvariable=self.alert_cond_var,
                     values=["below","above"], state="readonly",
                     width=8, font=("Courier", 10)).pack(side="left", padx=(0, 16))

        self.alert_save_btn = HermesButton(r2, "＋  ADD ALERT", self._save_alert, accent=True)
        self.alert_save_btn.pack(side="left", padx=(0, 6))
        HermesButton(r2, "✕  CLEAR", self._clear_alert_form).pack(side="left")
        self.form_status_lbl = tk.Label(r2, text="", bg=C["bg2"], fg=C["green"], font=("Courier", 8))
        self.form_status_lbl.pack(side="left", padx=10)

        SectionLabel(f, "Active Rules").pack(anchor="w", pady=(6, 4))
        lf = tk.Frame(f, bg=C["bg"])
        lf.pack(fill="both", expand=True)
        canvas = tk.Canvas(lf, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=canvas.yview)
        self.alert_inner = tk.Frame(canvas, bg=C["bg"])
        self.alert_inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.alert_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._populate_alert_rows()

        SectionLabel(f, "Recent Fires").pack(anchor="w", pady=(8, 2))
        self.alert_log = scrolledtext.ScrolledText(
            f, height=4, bg=C["bg3"], fg=C["amber"], font=("Courier", 8),
            relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1)
        self.alert_log.pack(fill="x", pady=(0, 8))

    # ── Tab: Signals ──────────────────────────────────────────────────────────

    def _build_tab_signals(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Signals  ")

        ctrl = tk.Frame(f, bg=C["bg"])
        ctrl.pack(fill="x", pady=(10, 6))
        SectionLabel(ctrl, "Signal Digest").pack(side="left")
        self.sig_tf_var = tk.StringVar(value="TODAY")
        for tf in ("TODAY", "1W", "1M"):
            tk.Radiobutton(ctrl, text=tf, variable=self.sig_tf_var, value=tf,
                           bg=C["bg"], fg=C["muted"], selectcolor=C["bg3"],
                           activebackground=C["bg"], font=("Courier", 8),
                           command=self._filter_signals).pack(side="left", padx=4)

        cols = ("Symbol","Type","Severity","Timeframe","Summary")
        self.sig_tree = self._make_tree(f, cols, heights=16)
        self.sig_tree.pack(fill="both", expand=True, pady=(0, 8))
        widths = [90, 120, 80, 80, 500]
        for col, w in zip(cols, widths):
            self.sig_tree.heading(col, text=col)
            self.sig_tree.column(col, anchor="w" if col=="Summary" else "center", width=w, minwidth=60)

        self.sig_tree.tag_configure("CRITICAL", foreground=C["red"])
        self.sig_tree.tag_configure("HIGH",     foreground=C["amber"])
        self.sig_tree.tag_configure("MEDIUM",   foreground=C["teal"])
        self.sig_tree.tag_configure("LOW",      foreground=C["muted"])

        btn_row = tk.Frame(f, bg=C["bg"])
        btn_row.pack(fill="x")
        self.sig_refresh_btn = HermesButton(btn_row, "↻  RUN SIGNAL SCAN", self._refresh_signals, accent=True)
        self.sig_refresh_btn.pack(side="left")
        self.sig_send_btn = HermesButton(btn_row, "📨  SEND TO TELEGRAM", self._send_signals)
        self.sig_send_btn.pack(side="left", padx=(6, 0))
        self.sig_status_lbl = tk.Label(btn_row, text="", bg=C["bg"], fg=C["muted"], font=("Courier", 8))
        self.sig_status_lbl.pack(side="left", padx=10)

    # ── Tab: Technicals ───────────────────────────────────────────────────────

    def _build_tab_technicals(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Technicals  ")

        SectionLabel(f, "Technical Analysis — Full Watchlist").pack(anchor="w", pady=(10, 4))

        cols = ("Symbol","Price","TA Signal","RSI","RSI Signal",
                "MA50","Above MA50","MACD Cross","MA Cross","Volume","BB Signal","Support","Resistance")
        self.ta_tree = self._make_tree(f, cols, heights=12)
        self.ta_tree.pack(fill="both", expand=True, pady=(0, 8))
        widths = [90,80,90,55,80,80,80,90,90,70,90,80,80]
        for col, w in zip(cols, widths):
            self.ta_tree.heading(col, text=col)
            self.ta_tree.column(col, anchor="center", width=w, minwidth=55)
        self.ta_tree.column("Symbol", anchor="w")
        self.ta_tree.tag_configure("STRONG BUY",  foreground=C["green"])
        self.ta_tree.tag_configure("BUY",         foreground=C["teal"])
        self.ta_tree.tag_configure("NEUTRAL",     foreground=C["muted"])
        self.ta_tree.tag_configure("SELL",        foreground=C["amber"])
        self.ta_tree.tag_configure("STRONG SELL", foreground=C["red"])

        btn_row = tk.Frame(f, bg=C["bg"])
        btn_row.pack(fill="x")
        self.ta_refresh_btn = HermesButton(btn_row, "↻  RUN TA SCAN", self._refresh_ta, accent=True)
        self.ta_refresh_btn.pack(side="left")
        self.ta_send_btn = HermesButton(btn_row, "📨  SEND SUMMARY", self._send_ta_summary)
        self.ta_send_btn.pack(side="left", padx=(6, 0))
        self.ta_status_lbl = tk.Label(btn_row, text="", bg=C["bg"], fg=C["muted"], font=("Courier", 8))
        self.ta_status_lbl.pack(side="left", padx=10)

        # Single stock deep dive
        SectionLabel(f, "Deep Dive — Single Stock").pack(anchor="w", pady=(10, 4))
        dd_row = tk.Frame(f, bg=C["bg"])
        dd_row.pack(fill="x")
        self.ta_sym_var = tk.StringVar()
        tk.Entry(dd_row, textvariable=self.ta_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat", font=("Courier", 10), width=18,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        HermesButton(dd_row, "ANALYSE + SEND", self._deep_dive_ta, accent=True).pack(side="left")

    # ── Tab: Risk Manager ─────────────────────────────────────────────────────

    def _build_tab_risk(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Risk Manager  ")

        left_col = tk.Frame(f, bg=C["bg"])
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=10)
        right_col = tk.Frame(f, bg=C["bg"])
        right_col.pack(side="left", fill="both", expand=True, pady=10)

        # Portfolio risk
        SectionLabel(left_col, "Portfolio Risk Analysis").pack(anchor="w", pady=(0, 4))
        self.risk_summary_text = scrolledtext.ScrolledText(
            left_col, height=8, bg=C["bg2"], fg=C["text"],
            font=("Courier", 9), relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1)
        self.risk_summary_text.pack(fill="x", pady=(0, 8))

        HermesButton(left_col, "↻  ANALYSE PORTFOLIO RISK",
                     self._refresh_risk, accent=True).pack(anchor="w", pady=(0, 8))
        HermesButton(left_col, "📨  SEND RISK REPORT",
                     self._send_risk_report).pack(anchor="w")

        # Trailing stops
        SectionLabel(left_col, "Trailing Stop Tracker").pack(anchor="w", pady=(12, 4))
        trail_form = Card(left_col)
        trail_form.pack(fill="x", pady=(0, 6))
        tr = tk.Frame(trail_form, bg=C["bg2"])
        tr.pack(fill="x")
        self.trail_sym_var  = tk.StringVar()
        self.trail_entry_var = tk.StringVar()
        for lbl, var, w in [("Symbol", self.trail_sym_var, 14), ("Entry ₹", self.trail_entry_var, 10)]:
            tk.Label(tr, text=lbl, bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 8), width=9, anchor="w").pack(side="left")
            tk.Entry(tr, textvariable=var, bg=C["bg3"], fg=C["text"],
                     insertbackground=C["text"], relief="flat", font=("Courier", 10), width=w,
                     highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        HermesButton(trail_form, "＋ TRACK", self._add_trailing_stop, accent=True).pack(anchor="w", pady=(6,0))

        cols = ("Symbol","Entry","Current High","Stop","Trail%")
        self.trail_tree = self._make_tree(left_col, cols, heights=5)
        self.trail_tree.pack(fill="x")
        for col in cols:
            self.trail_tree.heading(col, text=col)
            self.trail_tree.column(col, anchor="center", width=90, minwidth=70)
        self.trail_tree.column("Symbol", anchor="w")

        # Pre-trade checklist (right col)
        SectionLabel(right_col, "Pre-Trade Checklist").pack(anchor="w", pady=(0, 4))
        ptc_card = Card(right_col)
        ptc_card.pack(fill="x", pady=(0, 8))
        ptc_form = tk.Frame(ptc_card, bg=C["bg2"])
        ptc_form.pack(fill="x", pady=(0, 6))
        self.ptc_sym_var   = tk.StringVar()
        self.ptc_entry_var = tk.StringVar()
        self.ptc_target_var= tk.StringVar()
        for lbl, var, w, ph in [
            ("Symbol",   self.ptc_sym_var,    14, "RELIANCE.NS"),
            ("Entry ₹",  self.ptc_entry_var,  10, "2920"),
            ("Target ₹", self.ptc_target_var, 10, "3200"),
        ]:
            row = tk.Frame(ptc_card, bg=C["bg2"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=lbl, bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 8), width=10, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=var, bg=C["bg3"], fg=C["text"],
                     insertbackground=C["text"], relief="flat", font=("Courier", 10), width=w,
                     highlightbackground=C["border"], highlightthickness=1).pack(side="left")

        HermesButton(ptc_card, "🔍  RUN CHECKLIST", self._run_checklist, accent=True).pack(anchor="w", pady=(6,0))

        self.ptc_result_text = scrolledtext.ScrolledText(
            right_col, height=16, bg=C["bg2"], fg=C["text"],
            font=("Courier", 9), relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1)
        self.ptc_result_text.pack(fill="both", expand=True, pady=(8, 0))

        # Stop-loss calculator
        SectionLabel(right_col, "Quick Stop-Loss Calculator").pack(anchor="w", pady=(10, 4))
        sl_row = tk.Frame(right_col, bg=C["bg"])
        sl_row.pack(fill="x")
        self.sl_sym_var   = tk.StringVar()
        self.sl_entry_var = tk.StringVar()
        tk.Entry(sl_row, textvariable=self.sl_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat", font=("Courier", 10), width=14,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,6))
        tk.Entry(sl_row, textvariable=self.sl_entry_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat", font=("Courier", 10), width=10,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,6))
        HermesButton(sl_row, "CALC", self._calc_stop_loss).pack(side="left")
        self.sl_result_lbl = tk.Label(right_col, text="", bg=C["bg"], fg=C["teal"],
                                       font=("Courier", 9, "bold"))
        self.sl_result_lbl.pack(anchor="w", pady=(4,0))

    # ── Technicals data methods ───────────────────────────────────────────────

    def _refresh_ta(self):
        self.ta_refresh_btn.set_busy(True)
        self.ta_status_lbl.config(text="Scanning…", fg=C["muted"])
        self._log_gui("Running TA scan…")
        threading.Thread(target=self._fetch_ta, daemon=True).start()

    def _fetch_ta(self):
        try:
            results = analyze_watchlist(config.WATCHLIST)
            log_queue.put(("ta", results))
        except Exception as e:
            log.error(f"TA scan: {e}")
            log_queue.put(("ta", []))

    def _update_ta_ui(self, results: list):
        self.ta_cache = results
        for i in self.ta_tree.get_children(): self.ta_tree.delete(i)
        for r in results:
            sym  = r["symbol"].replace(".NS","")
            sig  = r.get("ta_signal","NEUTRAL")
            rsi  = r.get("rsi")
            rsi_s = f"{rsi:.1f}" if rsi else "—"
            ma50 = r.get("ma50")
            ma50_s = f"₹{ma50:,.2f}" if ma50 else "—"
            abv  = "✅" if r.get("above_ma50") else "❌"
            mc   = r.get("macd_cross","—")
            mac  = r.get("ma_cross","—")
            vol  = r.get("volume_signal","—")
            bb   = r.get("bb_signal","—")
            sup  = f"₹{r['support']:,.2f}" if r.get("support") else "—"
            res  = f"₹{r['resistance']:,.2f}" if r.get("resistance") else "—"
            self.ta_tree.insert("", "end", tags=(sig,), values=(
                sym, f"₹{r['price']:,.2f}", sig, rsi_s, r.get("rsi_signal","—"),
                ma50_s, abv, mc, mac, vol, bb, sup, res))

        self.ta_refresh_btn.set_busy(False)
        self.ta_status_lbl.config(text=f"{len(results)} stocks scanned.", fg=C["green"])
        self._log_gui(f"TA scan complete — {len(results)} stocks.")

    def _send_ta_summary(self):
        self.ta_send_btn.set_busy(True)
        threading.Thread(target=self._do_send_ta, daemon=True).start()

    def _do_send_ta(self):
        try:
            from formatter import format_ta_watchlist_summary
            results = self.ta_cache or analyze_watchlist(config.WATCHLIST)
            ok = sender.send_long(format_ta_watchlist_summary(results))
            log_queue.put(("ta_send_done", ok))
        except Exception as e:
            log.error(f"TA send: {e}")
            log_queue.put(("ta_send_done", False))

    def _deep_dive_ta(self):
        sym = self.ta_sym_var.get().strip().upper()
        if not sym: return
        if not sym.endswith(".NS") and sym not in ("NIFTY50","BANKNIFTY"):
            sym += ".NS"
        self._log_gui(f"Deep dive TA: {sym}…")
        def _run():
            try:
                from formatter import format_ta_snapshot
                r  = analyze(sym)
                if r:
                    ok = sender.send_long(format_ta_snapshot(r))
                    log_queue.put(("log", f"TA snapshot for {sym} {'sent ✅' if ok else 'failed ❌'}"))
            except Exception as e:
                log.error(f"Deep dive TA {sym}: {e}")
        threading.Thread(target=_run, daemon=True).start()

    # ── Risk Manager data methods ─────────────────────────────────────────────

    def _refresh_risk(self):
        self._log_gui("Analysing portfolio risk…")
        threading.Thread(target=self._fetch_risk, daemon=True).start()

    def _fetch_risk(self):
        try:
            from data_fetcher import get_portfolio_pnl
            pnl  = get_portfolio_pnl(config.PORTFOLIO)
            risk = portfolio_risk_analysis(config.PORTFOLIO, pnl)
            log_queue.put(("risk", risk))
        except Exception as e:
            log.error(f"Risk analysis: {e}")
            log_queue.put(("risk", {}))

    def _update_risk_ui(self, risk: dict):
        self.risk_summary_text.config(state="normal")
        self.risk_summary_text.delete("1.0","end")
        if not risk:
            self.risk_summary_text.insert("end","No data available.")
            self.risk_summary_text.config(state="disabled")
            return
        total = risk.get("total_value",0)
        top5  = risk.get("top5_conc_pct",0)
        divs  = "✅ Diversified" if risk.get("diversified") else "⚠️ Concentrated"
        it    = risk.get("it_exposure_pct",0)
        bank  = risk.get("bank_exposure_pct",0)
        lines = [
            f"Portfolio: ₹{total:,.0f}",
            f"Status: {divs}",
            f"Top-5 Concentration: {top5:.1f}%",
            f"IT Exposure: {it:.1f}%  |  Banking: {bank:.1f}%",
            "",
        ]
        warns = risk.get("warnings",[])
        if warns:
            lines.append("WARNINGS:")
            lines += [f"  {w}" for w in warns]
            lines.append("")
        lines.append("POSITIONS:")
        for p in sorted(risk.get("positions",[]), key=lambda x: x["pct"], reverse=True):
            sym = p["symbol"].replace(".NS","")
            flag = "⚠ " if p["overweight"] else "  "
            lines.append(f"{flag}{sym:<14} {p['pct']:>5.1f}%   ₹{p['value']:>12,.0f}")
        self.risk_summary_text.insert("end", "\n".join(lines))
        self.risk_summary_text.config(state="disabled")
        self._log_gui("Portfolio risk analysis done.")

    def _send_risk_report(self):
        self._log_gui("Sending risk report…")
        def _run():
            try:
                from data_fetcher import get_portfolio_pnl
                from formatter import format_risk_summary
                pnl  = get_portfolio_pnl(config.PORTFOLIO)
                risk = portfolio_risk_analysis(config.PORTFOLIO, pnl)
                ok   = sender.send_long(format_risk_summary(risk))
                log_queue.put(("log", f"Risk report {'sent ✅' if ok else 'failed ❌'}"))
            except Exception as e:
                log.error(f"Risk report send: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _run_checklist(self):
        sym    = self.ptc_sym_var.get().strip().upper()
        entry_s = self.ptc_entry_var.get().strip()
        if not sym or not entry_s: return
        if not sym.endswith(".NS") and sym not in ("NIFTY50","BANKNIFTY"):
            sym += ".NS"
        try:
            entry = float(entry_s.replace(",",""))
        except ValueError:
            return
        self._log_gui(f"Running pre-trade checklist for {sym}…")
        def _run():
            try:
                from sources.technicals import analyze as ta_analyze
                from sources.nse import get_fii_dii_trend as _fii_trend
                from data_fetcher import get_earnings_calendar, get_portfolio_pnl
                from formatter import format_pre_trade_checklist

                ta_r      = ta_analyze(sym) or {}
                fii_trend = _fii_trend()
                earnings  = get_earnings_calendar([sym])
                earn_days = earnings[0]["days_out"] if earnings else 999
                pnl       = get_portfolio_pnl(config.PORTFOLIO)
                port_val  = sum(r.get("market_value",0) for r in pnl)

                result = pre_trade_checklist(
                    sym, entry, port_val, config.PORTFOLIO,
                    ta_r, fii_trend, earn_days)
                log_queue.put(("checklist", result))
            except Exception as e:
                log.error(f"Checklist: {e}")
                log_queue.put(("checklist", None))
        threading.Thread(target=_run, daemon=True).start()

    def _update_checklist_ui(self, result: dict | None):
        self.ptc_result_text.config(state="normal")
        self.ptc_result_text.delete("1.0","end")
        if not result:
            self.ptc_result_text.insert("end","Error running checklist.")
            self.ptc_result_text.config(state="disabled")
            return
        verdict = result["verdict"]
        passed  = result["passed"]
        total   = result["total"]
        stop    = result.get("stop_loss",0)
        pos     = result.get("position",{})
        lines   = [
            f"VERDICT: {verdict}  ({passed}/{total} passed)",
            f"Entry:   ₹{result['entry']:,.2f}",
            f"Stop:    ₹{stop:,.2f}",
        ]
        if pos:
            lines.append(f"Qty:     {pos.get('qty',0)} shares  "
                         f"(₹{pos.get('position_value',0):,.0f}  {pos.get('position_pct',0):.1f}%)")
        lines.append("")
        for c in result.get("checks",[]):
            icon = "✅" if c["pass"] else "❌"
            lines.append(f"{icon} {c['name']}")
            lines.append(f"   {c['detail']}")

        col_map = {"STRONG BUY":C["green"],"BUY":C["teal"],
                   "WATCH":C["amber"],"AVOID":C["red"]}
        self.ptc_result_text.tag_config("verdict", foreground=col_map.get(verdict, C["text"]),
                                         font=("Courier",10,"bold"))
        self.ptc_result_text.insert("end", lines[0]+"\n", "verdict")
        self.ptc_result_text.insert("end", "\n".join(lines[1:]))
        self.ptc_result_text.config(state="disabled")

        # Also send to Telegram
        try:
            from formatter import format_pre_trade_checklist
            sender.send_long(format_pre_trade_checklist(result))
        except Exception:
            pass

    def _calc_stop_loss(self):
        sym   = self.sl_sym_var.get().strip().upper()
        entry_s = self.sl_entry_var.get().strip()
        if not sym or not entry_s: return
        if not sym.endswith(".NS"): sym += ".NS"
        try: entry = float(entry_s.replace(",",""))
        except ValueError: return
        def _run():
            try:
                sl = get_stop_loss(sym, entry)
                msg = (f"Stop: ₹{sl['stop']:,.2f}  |  "
                       f"Risk: ₹{sl['risk_per_share']:,.2f} ({sl['risk_pct']:.1f}%)  |  "
                       f"ATR: {sl['atr'] or 'N/A'}  |  Method: {sl['method']}")
                log_queue.put(("sl_result", msg))
            except Exception as e:
                log_queue.put(("sl_result", f"Error: {e}"))
        threading.Thread(target=_run, daemon=True).start()

    def _add_trailing_stop(self):
        sym    = self.trail_sym_var.get().strip().upper()
        entry_s = self.trail_entry_var.get().strip()
        if not sym or not entry_s: return
        if not sym.endswith(".NS"): sym += ".NS"
        try: entry = float(entry_s.replace(",",""))
        except ValueError: return
        self.trail_tracker.add(sym, entry)
        self._populate_trail_tree()
        self._log_gui(f"Trailing stop added: {sym} @ ₹{entry:,.2f}")

    def _populate_trail_tree(self):
        for i in self.trail_tree.get_children(): self.trail_tree.delete(i)
        for t in self.trail_tracker.get_all():
            self.trail_tree.insert("", "end", values=(
                t["symbol"].replace(".NS",""),
                f"₹{t['entry']:,.2f}",
                f"₹{t['current_high']:,.2f}",
                f"₹{t['stop']:,.2f}",
                f"{t['trail_pct']:.0f}%",
            ))

    def _build_tab_market_pulse(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Market Pulse  ")

        left  = tk.Frame(f, bg=C["bg"]); left.pack(side="left",  fill="both", expand=True, padx=(0,6), pady=10)
        right = tk.Frame(f, bg=C["bg"]); right.pack(side="left", fill="both", expand=True, pady=10)

        # VIX
        SectionLabel(left, "India VIX — Fear Index").pack(anchor="w", pady=(0,4))
        self.vix_card = Card(left); self.vix_card.pack(fill="x", pady=(0,8))
        self.vix_val_lbl   = tk.Label(self.vix_card, text="—", bg=C["bg2"], fg=C["text"],  font=("Courier",22,"bold")); self.vix_val_lbl.pack(anchor="w")
        self.vix_level_lbl = tk.Label(self.vix_card, text="—", bg=C["bg2"], fg=C["muted"], font=("Courier",9));         self.vix_level_lbl.pack(anchor="w")
        self.vix_mean_lbl  = tk.Label(self.vix_card, text="—", bg=C["bg2"], fg=C["muted"], font=("Courier",8), wraplength=260, justify="left"); self.vix_mean_lbl.pack(anchor="w")
        self.vix_act_lbl   = tk.Label(self.vix_card, text="—", bg=C["bg2"], fg=C["amber"], font=("Courier",8), wraplength=260, justify="left"); self.vix_act_lbl.pack(anchor="w")

        SectionLabel(left, "Put/Call Ratio — Sentiment").pack(anchor="w", pady=(8,4))
        self.pcr_card = Card(left); self.pcr_card.pack(fill="x", pady=(0,8))
        self.pcr_val_lbl   = tk.Label(self.pcr_card, text="—", bg=C["bg2"], fg=C["text"],  font=("Courier",18,"bold")); self.pcr_val_lbl.pack(anchor="w")
        self.pcr_level_lbl = tk.Label(self.pcr_card, text="—", bg=C["bg2"], fg=C["muted"], font=("Courier",9));         self.pcr_level_lbl.pack(anchor="w")
        self.pcr_mean_lbl  = tk.Label(self.pcr_card, text="—", bg=C["bg2"], fg=C["muted"], font=("Courier",8), wraplength=260, justify="left"); self.pcr_mean_lbl.pack(anchor="w")

        SectionLabel(left, "Advance / Decline").pack(anchor="w", pady=(8,4))
        self.ad_card = Card(left); self.ad_card.pack(fill="x", pady=(0,8))
        self.ad_val_lbl  = tk.Label(self.ad_card, text="—", bg=C["bg2"], fg=C["text"],  font=("Courier",13,"bold")); self.ad_val_lbl.pack(anchor="w")
        self.ad_mean_lbl = tk.Label(self.ad_card, text="—", bg=C["bg2"], fg=C["muted"], font=("Courier",8), wraplength=260, justify="left"); self.ad_mean_lbl.pack(anchor="w")

        HermesButton(left, "↻  REFRESH SENTIMENT",   self._refresh_sentiment, accent=True).pack(anchor="w", pady=(4,2))
        HermesButton(left, "📨  SEND SENTIMENT REPORT", self._send_sentiment).pack(anchor="w")

        # Sector rotation
        SectionLabel(right, "Sector Rotation Today").pack(anchor="w", pady=(0,4))
        cols = ("Sector","Today %","This Week %","Flow")
        self.sector_tree = self._make_tree(right, cols, heights=10)
        self.sector_tree.pack(fill="x", pady=(0,8))
        for col in cols:
            self.sector_tree.heading(col, text=col)
            self.sector_tree.column(col, anchor="center", width=110, minwidth=70)
        self.sector_tree.column("Sector", anchor="w", width=100)
        self.sector_tree.column("Flow",   anchor="w", width=130)
        self.sector_tree.tag_configure("up",   foreground=C["green"])
        self.sector_tree.tag_configure("dn",   foreground=C["red"])
        self.sector_tree.tag_configure("flat", foreground=C["muted"])

        # Options unusual
        SectionLabel(right, "Unusual Options Activity").pack(anchor="w", pady=(8,4))
        cols2 = ("Symbol","Spot","PCR","Sentiment","Resistance","Support","IV","Unusual")
        self.opt_tree = self._make_tree(right, cols2, heights=6)
        self.opt_tree.pack(fill="x", pady=(0,6))
        widths2 = [80,80,55,80,85,80,60,100]
        for col,w in zip(cols2,widths2):
            self.opt_tree.heading(col, text=col)
            self.opt_tree.column(col, anchor="center", width=w, minwidth=50)
        self.opt_tree.column("Symbol", anchor="w")
        self.opt_tree.tag_configure("BULLISH", foreground=C["green"])
        self.opt_tree.tag_configure("BEARISH", foreground=C["red"])
        self.opt_tree.tag_configure("NEUTRAL", foreground=C["muted"])
        HermesButton(right, "↻  SCAN OPTIONS",       self._refresh_options, accent=True).pack(anchor="w", pady=(0,4))
        HermesButton(right, "📨  SEND OPTIONS REPORT", self._send_options).pack(anchor="w", pady=(0,8))

        # Promoter
        SectionLabel(right, "Promoter & Institutional Holdings").pack(anchor="w", pady=(4,4))
        cols3 = ("Symbol","Promoter%","Pledge%","FII%","MF%","Risk")
        self.promo_tree = self._make_tree(right, cols3, heights=5)
        self.promo_tree.pack(fill="x")
        for col in cols3:
            self.promo_tree.heading(col, text=col)
            self.promo_tree.column(col, anchor="center", width=82, minwidth=55)
        self.promo_tree.column("Symbol", anchor="w")
        self.promo_tree.tag_configure("high",   foreground=C["red"])
        self.promo_tree.tag_configure("medium", foreground=C["amber"])
        self.promo_tree.tag_configure("safe",   foreground=C["green"])
        btn_row2 = tk.Frame(right, bg=C["bg"]); btn_row2.pack(fill="x", pady=(4,0))
        HermesButton(btn_row2, "↻  FETCH", self._refresh_promoter, accent=True).pack(side="left")
        HermesButton(btn_row2, "📨  SEND",  self._send_promoter).pack(side="left", padx=(6,0))

    # ── Market Pulse methods ──────────────────────────────────────────────────

    def _refresh_sentiment(self):
        self._log_gui("Fetching VIX + sentiment…")
        threading.Thread(target=self._fetch_sentiment, daemon=True).start()

    def _fetch_sentiment(self):
        try:
            from sources.vix import get_full_sentiment
            from sources.sector import get_sector_performance, get_rotation_signals
            sent   = get_full_sentiment()
            sector = get_sector_performance()
            rsigs  = get_rotation_signals(sector, config.WATCHLIST)
            log_queue.put(("sentiment", (sent, sector, rsigs)))
        except Exception as e:
            log.error(f"Sentiment fetch: {e}")

    def _update_sentiment_ui(self, data):
        sent, sector_data, rsigs = data
        vix  = sent.get("vix", {}); pcr = sent.get("pcr", {}); ad = sent.get("ad", {})
        mood = sent.get("mood", "NEUTRAL")
        v    = vix.get("vix", 0)
        vix_col = C["red"] if v > 20 else (C["amber"] if v > 15 else C["green"])
        self.vix_val_lbl.config(text=f"{v:.2f}", fg=vix_col)
        self.vix_level_lbl.config(text=vix.get("level","—"))
        self.vix_mean_lbl.config(text=vix.get("meaning","—"))
        self.vix_act_lbl.config(text=f"→ {vix.get('action','—')}")
        p = pcr.get("pcr", 0)
        pcr_col = C["green"] if p > 1.2 else (C["red"] if p < 0.8 else C["muted"])
        self.pcr_val_lbl.config(text=f"{p:.2f}", fg=pcr_col)
        self.pcr_level_lbl.config(text=pcr.get("level","—"))
        self.pcr_mean_lbl.config(text=pcr.get("meaning","—"))
        adv = ad.get("advances",0); dec = ad.get("declines",0)
        self.ad_val_lbl.config(text=f"▲ {adv}  ▼ {dec}  Ratio {ad.get('ratio',0):.2f}")
        self.ad_mean_lbl.config(text=ad.get("meaning","—"))
        for i in self.sector_tree.get_children(): self.sector_tree.delete(i)
        for s in sector_data:
            tag  = "up" if s["pct"]>0 else ("dn" if s["pct"]<0 else "flat")
            flow = "🟢 Flowing IN" if s["pct"]>0 else "🔴 Flowing OUT"
            self.sector_tree.insert("","end", tags=(tag,), values=(
                s["sector"], f"{s['pct']:+.2f}%", f"{s['week_pct']:+.2f}%", flow))
        self._log_gui(f"Sentiment refreshed. Market mood: {mood}")

    def _send_sentiment(self):
        threading.Thread(target=self._do_send_sentiment, daemon=True).start()

    def _do_send_sentiment(self):
        try:
            from sources.vix import get_full_sentiment
            from sources.sector import get_sector_performance, get_rotation_signals
            from formatter import format_sentiment_report, format_sector_rotation
            sent   = get_full_sentiment()
            sector = get_sector_performance()
            rsigs  = get_rotation_signals(sector, config.WATCHLIST)
            ok1 = sender.send_long(format_sentiment_report(sent))
            ok2 = sender.send_long(format_sector_rotation(sector, rsigs))
            log_queue.put(("log", f"Sentiment {'sent ✅' if ok1 and ok2 else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Sentiment send: {e}")

    def _refresh_options(self):
        self._log_gui("Scanning unusual options…")
        threading.Thread(target=self._fetch_options, daemon=True).start()

    def _fetch_options(self):
        try:
            from sources.options import scan_unusual_activity
            log_queue.put(("options", scan_unusual_activity(config.WATCHLIST)))
        except Exception as e:
            log.error(f"Options scan: {e}"); log_queue.put(("options", []))

    def _update_options_ui(self, data):
        for i in self.opt_tree.get_children(): self.opt_tree.delete(i)
        for r in data:
            sym  = r["symbol"]; sent = r.get("sentiment","NEUTRAL")
            un   = len(r.get("unusual",[])); iv_flag = "⚠️ SPIKE" if r.get("iv_spike") else f"{r.get('avg_iv',0):.0f}%"
            self.opt_tree.insert("","end", tags=(sent,), values=(
                sym, f"₹{r.get('spot',0):,.0f}", f"{r.get('pcr',0):.2f}", sent,
                f"₹{r.get('resistance',0):,}" if r.get("resistance") else "—",
                f"₹{r.get('support',0):,}"    if r.get("support")    else "—",
                iv_flag, f"{un} bets" if un else "—"))
        self._log_gui(f"Options scan done — {len(data)} symbols.")

    def _send_options(self):
        threading.Thread(target=self._do_send_options, daemon=True).start()

    def _do_send_options(self):
        try:
            from sources.options import scan_unusual_activity
            from formatter import format_options_activity
            ok = sender.send_long(format_options_activity(scan_unusual_activity(config.WATCHLIST)))
            log_queue.put(("log", f"Options report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Options send: {e}")

    def _refresh_promoter(self):
        self._log_gui("Fetching shareholding…")
        threading.Thread(target=self._fetch_promoter, daemon=True).start()

    def _fetch_promoter(self):
        try:
            from sources.promoter import get_watchlist_shareholding, get_pledge_alerts
            data   = get_watchlist_shareholding(config.WATCHLIST)
            alerts = get_pledge_alerts(data)
            log_queue.put(("promoter", (data, alerts)))
        except Exception as e:
            log.error(f"Promoter fetch: {e}"); log_queue.put(("promoter", ([],[])))

    def _update_promoter_ui(self, data):
        sh_data, alerts = data
        for i in self.promo_tree.get_children(): self.promo_tree.delete(i)
        for s in sh_data:
            risk_tag = {"HIGH":"high","MEDIUM":"medium","LOW":"safe","NONE":"safe"}.get(s["pledge_risk"],"safe")
            risk_lbl = {"HIGH":"🔴 HIGH","MEDIUM":"🟡 MED","LOW":"🟢 LOW","NONE":"✅ OK"}.get(s["pledge_risk"],"—")
            chg_sym  = "+" if s["pledge_chg"]>=0 else ""
            self.promo_tree.insert("","end", tags=(risk_tag,), values=(
                s["symbol"][:9], f"{s['promoter_pct']:.1f}%",
                f"{s['pledge_pct']:.1f}% ({chg_sym}{s['pledge_chg']:.1f})",
                f"{s['fii_pct']:.1f}%", f"{s['dii_pct']:.1f}%", risk_lbl))
        if alerts:
            for a in alerts[:3]:
                self._log_gui(f"Pledge: {a['symbol']} — {a['message'][:55]}")
        self._log_gui(f"Shareholding loaded — {len(sh_data)} stocks.")

    def _send_promoter(self):
        threading.Thread(target=self._do_send_promoter, daemon=True).start()

    def _do_send_promoter(self):
        try:
            from sources.promoter import get_watchlist_shareholding, get_pledge_alerts
            from formatter import format_shareholding_report
            data   = get_watchlist_shareholding(config.WATCHLIST)
            alerts = get_pledge_alerts(data)
            ok     = sender.send_long(format_shareholding_report(data, alerts))
            log_queue.put(("log", f"Shareholding report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Promoter send: {e}")

    def _build_tab_52w(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  52W Range  ")
        SectionLabel(f, "52-Week Range Analysis").pack(anchor="w", pady=(10, 4))

        cols = ("Symbol","Price","52W Low","52W High","% from Low","% from High","Range Bar","Status")
        self.w52_tree = self._make_tree(f, cols, heights=14)
        self.w52_tree.pack(fill="both", expand=True, pady=(0, 8))
        widths = [100,80,80,80,90,95,140,80]
        for col, w in zip(cols, widths):
            self.w52_tree.heading(col, text=col)
            self.w52_tree.column(col, anchor="center", width=w, minwidth=60)
        self.w52_tree.column("Symbol", anchor="w")
        self.w52_tree.column("Range Bar", anchor="w")
        self.w52_tree.tag_configure("danger", foreground=C["red"])
        self.w52_tree.tag_configure("warn",   foreground=C["amber"])
        self.w52_tree.tag_configure("safe",   foreground=C["green"])

        HermesButton(f, "↻  RUN 52W ANALYSIS", self._refresh_52w).pack(anchor="w")

    # ── Tab: Earnings ─────────────────────────────────────────────────────────

    def _build_tab_earnings(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Earnings  ")
        SectionLabel(f, "Upcoming Earnings").pack(anchor="w", pady=(10, 4))

        cols = ("Symbol","Date","Days Out","Status")
        self.earn_tree = self._make_tree(f, cols, heights=14)
        self.earn_tree.pack(fill="both", expand=True, pady=(0, 8))
        for col in cols:
            self.earn_tree.heading(col, text=col)
            self.earn_tree.column(col, anchor="center", width=160, minwidth=80)
        self.earn_tree.column("Symbol", anchor="w", width=120)
        self.earn_tree.tag_configure("urgent", foreground=C["red"])
        self.earn_tree.tag_configure("soon",   foreground=C["amber"])
        self.earn_tree.tag_configure("ok",     foreground=C["text"])

        HermesButton(f, "↻  FETCH EARNINGS", self._refresh_earnings).pack(anchor="w")

    # ── Tab: Corporate Actions ────────────────────────────────────────────────

    def _build_tab_corporate(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Corporate Actions  ")
        SectionLabel(f, "Dividends · Splits · Bonuses · Rights (Next 30 Days)").pack(anchor="w", pady=(10, 4))

        cols = ("Symbol","Category","Action","Ex-Date","Days Out","Urgent")
        self.corp_tree = self._make_tree(f, cols, heights=14)
        self.corp_tree.pack(fill="both", expand=True, pady=(0, 8))
        widths = [100, 90, 260, 90, 70, 70]
        for col, w in zip(cols, widths):
            self.corp_tree.heading(col, text=col)
            self.corp_tree.column(col, anchor="center", width=w, minwidth=60)
        self.corp_tree.column("Symbol", anchor="w")
        self.corp_tree.column("Action", anchor="w")
        self.corp_tree.tag_configure("urgent", foreground=C["red"])
        self.corp_tree.tag_configure("soon",   foreground=C["amber"])
        self.corp_tree.tag_configure("ok",     foreground=C["text"])

        HermesButton(f, "↻  FETCH CORPORATE ACTIONS", self._refresh_corporate).pack(anchor="w")

    # ── Tab: Holdings Manager ─────────────────────────────────────────────────

    # ── Tab: Fundamentals ─────────────────────────────────────────────────────

    def _build_tab_fundamentals(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Fundamentals  ")

        left  = tk.Frame(f, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,6), pady=10)
        right = tk.Frame(f, bg=C["bg"]); right.pack(side="left", fill="both", expand=True, pady=10)

        # Watchlist fundamentals table
        SectionLabel(left, "Watchlist Fundamentals Screener").pack(anchor="w", pady=(0,4))
        cols = ("Symbol","Price","P/E","Sector P/E","ROE%","Debt%","Rev Growth","Margin%","Signal","Score")
        self.fund_tree = self._make_tree(left, cols, heights=12)
        self.fund_tree.pack(fill="both", expand=True, pady=(0,8))
        widths = [90,80,60,80,60,60,85,70,90,55]
        for col,w in zip(cols,widths):
            self.fund_tree.heading(col, text=col)
            self.fund_tree.column(col, anchor="center", width=w, minwidth=50)
        self.fund_tree.column("Symbol", anchor="w")
        for sig in ("STRONG BUY","BUY","HOLD","SELL","STRONG SELL"):
            col = {
                "STRONG BUY":C["green"],"BUY":C["teal"],
                "HOLD":C["muted"],"SELL":C["amber"],"STRONG SELL":C["red"]
            }[sig]
            self.fund_tree.tag_configure(sig, foreground=col)

        btn_row = tk.Frame(left, bg=C["bg"]); btn_row.pack(fill="x")
        self.fund_refresh_btn = HermesButton(btn_row, "↻  SCREEN ALL", self._refresh_fundamentals, accent=True)
        self.fund_refresh_btn.pack(side="left")
        HermesButton(btn_row, "📨  SEND REPORT", self._send_fundamentals).pack(side="left", padx=(6,0))
        self.fund_status_lbl = tk.Label(btn_row, text="", bg=C["bg"], fg=C["muted"], font=("Courier",8))
        self.fund_status_lbl.pack(side="left", padx=10)

        # Single stock deep dive (right)
        SectionLabel(right, "Single Stock Deep Dive").pack(anchor="w", pady=(0,4))
        dd_row = tk.Frame(right, bg=C["bg"]); dd_row.pack(fill="x", pady=(0,8))
        self.fund_sym_var = tk.StringVar()
        tk.Entry(dd_row, textvariable=self.fund_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat", font=("Courier",10), width=18,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        HermesButton(dd_row, "ANALYSE + SEND", self._fund_deep_dive, accent=True).pack(side="left")

        self.fund_detail_text = scrolledtext.ScrolledText(
            right, bg=C["bg2"], fg=C["text"], font=("Courier",8),
            relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1)
        self.fund_detail_text.pack(fill="both", expand=True)

        # Global macro
        SectionLabel(right, "Global Macro Indicators").pack(anchor="w", pady=(8,4))
        self.macro_detail_text = scrolledtext.ScrolledText(
            right, height=8, bg=C["bg2"], fg=C["text"], font=("Courier",8),
            relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1)
        self.macro_detail_text.pack(fill="x")
        btn_row2 = tk.Frame(right, bg=C["bg"]); btn_row2.pack(fill="x", pady=(4,0))
        HermesButton(btn_row2, "↻  FETCH MACRO", self._refresh_global_macro, accent=True).pack(side="left")
        HermesButton(btn_row2, "📨  SEND MACRO",  self._send_global_macro).pack(side="left", padx=(6,0))

    # ── Tab: Trade Journal ────────────────────────────────────────────────────

    def _build_tab_journal(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Journal  ")

        left  = tk.Frame(f, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,6), pady=10)
        right = tk.Frame(f, bg=C["bg"]); right.pack(side="left", fill="y", pady=10, padx=(0,6))
        right.configure(width=320); right.pack_propagate(False)

        # Log new trade
        SectionLabel(left, "Log a Trade").pack(anchor="w", pady=(0,4))
        form = Card(left); form.pack(fill="x", pady=(0,8))
        self.j_sym_var    = tk.StringVar()
        self.j_entry_var  = tk.StringVar()
        self.j_qty_var    = tk.StringVar()
        self.j_stop_var   = tk.StringVar()
        self.j_target_var = tk.StringVar()
        self.j_reason_var = tk.StringVar()
        self.j_side_var   = tk.StringVar(value="BUY")

        r1 = tk.Frame(form, bg=C["bg2"]); r1.pack(fill="x", pady=(0,4))
        for lbl, var, w in [("Symbol",self.j_sym_var,12),("Entry ₹",self.j_entry_var,10),("Qty",self.j_qty_var,6)]:
            tk.Label(r1,text=lbl,bg=C["bg2"],fg=C["muted"],font=("Courier",8),width=9,anchor="w").pack(side="left")
            tk.Entry(r1,textvariable=var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                     relief="flat",font=("Courier",10),width=w,
                     highlightbackground=C["border"],highlightthickness=1).pack(side="left",padx=(0,8))

        r2 = tk.Frame(form, bg=C["bg2"]); r2.pack(fill="x", pady=(0,4))
        for lbl, var, w in [("Stop ₹",self.j_stop_var,10),("Target ₹",self.j_target_var,10)]:
            tk.Label(r2,text=lbl,bg=C["bg2"],fg=C["muted"],font=("Courier",8),width=9,anchor="w").pack(side="left")
            tk.Entry(r2,textvariable=var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                     relief="flat",font=("Courier",10),width=w,
                     highlightbackground=C["border"],highlightthickness=1).pack(side="left",padx=(0,8))
        tk.Label(r2,text="Side",bg=C["bg2"],fg=C["muted"],font=("Courier",8),width=5,anchor="w").pack(side="left")
        ttk.Combobox(r2,textvariable=self.j_side_var,values=["BUY","SELL"],
                     state="readonly",width=6,font=("Courier",10)).pack(side="left")

        r3 = tk.Frame(form, bg=C["bg2"]); r3.pack(fill="x")
        tk.Label(r3,text="Reason",bg=C["bg2"],fg=C["muted"],font=("Courier",8),width=9,anchor="w").pack(side="left")
        tk.Entry(r3,textvariable=self.j_reason_var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                 relief="flat",font=("Courier",10),width=40,
                 highlightbackground=C["border"],highlightthickness=1).pack(side="left",fill="x",expand=True)

        btn_row = tk.Frame(form, bg=C["bg2"]); btn_row.pack(fill="x", pady=(8,0))
        HermesButton(btn_row,"＋  LOG ENTRY",self._log_trade_entry,accent=True).pack(side="left")
        self.j_status_lbl = tk.Label(btn_row,text="",bg=C["bg2"],fg=C["green"],font=("Courier",8))
        self.j_status_lbl.pack(side="left",padx=10)

        # Open trades
        SectionLabel(left, "Open Trades — Double-click to Close").pack(anchor="w", pady=(8,4))
        cols = ("ID","Symbol","Side","Entry ₹","Qty","Stop ₹","Target ₹","Date","Reason")
        self.open_tree = self._make_tree(left, cols, heights=6)
        self.open_tree.pack(fill="x", pady=(0,8))
        widths2 = [40,80,50,80,50,70,70,90,180]
        for col,w in zip(cols,widths2):
            self.open_tree.heading(col,text=col)
            self.open_tree.column(col,anchor="center",width=w,minwidth=40)
        self.open_tree.column("Symbol",anchor="w")
        self.open_tree.column("Reason",anchor="w")
        self.open_tree.bind("<Double-1>", self._open_close_dialog)

        # Close trade form
        SectionLabel(left, "Close a Trade").pack(anchor="w", pady=(0,4))
        close_form = Card(left); close_form.pack(fill="x")
        cr = tk.Frame(close_form, bg=C["bg2"]); cr.pack(fill="x")
        self.j_close_id_var   = tk.StringVar()
        self.j_exit_var       = tk.StringVar()
        self.j_exit_reason_var= tk.StringVar(value="Target hit")
        for lbl,var,w in [("Trade ID",self.j_close_id_var,6),("Exit ₹",self.j_exit_var,10)]:
            tk.Label(cr,text=lbl,bg=C["bg2"],fg=C["muted"],font=("Courier",8),width=10,anchor="w").pack(side="left")
            tk.Entry(cr,textvariable=var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                     relief="flat",font=("Courier",10),width=w,
                     highlightbackground=C["border"],highlightthickness=1).pack(side="left",padx=(0,8))
        cr2 = tk.Frame(close_form, bg=C["bg2"]); cr2.pack(fill="x",pady=(4,0))
        tk.Label(cr2,text="Exit Reason",bg=C["bg2"],fg=C["muted"],font=("Courier",8),width=10,anchor="w").pack(side="left")
        ttk.Combobox(cr2,textvariable=self.j_exit_reason_var,
                     values=["Target hit","Stop-loss hit","Trailing stop","Manual exit","News"],
                     state="readonly",width=18,font=("Courier",10)).pack(side="left",padx=(0,8))
        btn_row3 = tk.Frame(close_form,bg=C["bg2"]); btn_row3.pack(fill="x",pady=(6,0))
        HermesButton(btn_row3,"✓  CLOSE TRADE",self._close_trade_entry,accent=True).pack(side="left")

        # Performance stats (right)
        SectionLabel(right, "Performance Stats").pack(anchor="w", pady=(0,4))
        self.stats_text = scrolledtext.ScrolledText(
            right, bg=C["bg2"], fg=C["text"], font=("Courier",9),
            relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1)
        self.stats_text.pack(fill="both", expand=True, pady=(0,8))

        btn_row4 = tk.Frame(right,bg=C["bg"]); btn_row4.pack(fill="x")
        HermesButton(btn_row4,"↻  REFRESH STATS",self._refresh_journal_stats,accent=True).pack(fill="x",pady=2)
        HermesButton(btn_row4,"📨  SEND STATS",   self._send_journal_stats).pack(fill="x",pady=2)

        # Closed trades
        SectionLabel(right, "Recent Closed Trades").pack(anchor="w", pady=(8,4))
        cols2 = ("ID","Symbol","P&L","P&L%","Status")
        self.closed_tree = self._make_tree(right, cols2, heights=8)
        self.closed_tree.pack(fill="x")
        for col in cols2:
            self.closed_tree.heading(col,text=col)
            self.closed_tree.column(col,anchor="center",width=58,minwidth=40)
        self.closed_tree.column("Symbol",anchor="w",width=80)
        self.closed_tree.tag_configure("WIN",  foreground=C["green"])
        self.closed_tree.tag_configure("LOSS", foreground=C["red"])
        self.closed_tree.tag_configure("BREAK_EVEN", foreground=C["muted"])

        self._refresh_journal_ui()

    # ── Fundamentals methods ──────────────────────────────────────────────────

    def _refresh_fundamentals(self):
        self.fund_refresh_btn.set_busy(True)
        self.fund_status_lbl.config(text="Scanning…", fg=C["muted"])
        self._log_gui("Running fundamentals screener…")
        threading.Thread(target=self._fetch_fundamentals, daemon=True).start()

    def _fetch_fundamentals(self):
        try:
            from sources.fundamentals import get_watchlist_fundamentals
            data = get_watchlist_fundamentals(config.WATCHLIST)
            log_queue.put(("fundamentals", data))
        except Exception as e:
            log.error(f"Fundamentals: {e}")
            log_queue.put(("fundamentals", []))

    def _update_fundamentals_ui(self, data: list):
        for i in self.fund_tree.get_children(): self.fund_tree.delete(i)
        sig_map = {"STRONG BUY":"🚀","BUY":"📈","HOLD":"⏸","SELL":"📉","STRONG SELL":"🔻"}
        for r in data:
            sym  = r["symbol"]
            sig  = r.get("overall","HOLD")
            emoji= sig_map.get(sig,"⏸")
            self.fund_tree.insert("","end", tags=(sig,), values=(
                sym,
                f"₹{r.get('price',0):,.2f}",
                f"{r['pe']:.1f}"     if r.get("pe")           else "—",
                f"{r['sector_pe']}"  if r.get("sector_pe")    else "—",
                f"{r['roe']:.1f}%"   if r.get("roe")          else "—",
                f"{r['debt_eq']:.0f}%" if r.get("debt_eq") is not None else "—",
                f"{r['rev_growth']:+.1f}%" if r.get("rev_growth") else "—",
                f"{r['profit_margin']:.1f}%" if r.get("profit_margin") else "—",
                f"{emoji} {sig}",
                str(r.get("score",0)),
            ))
        self.fund_refresh_btn.set_busy(False)
        self.fund_status_lbl.config(text=f"{len(data)} stocks screened.", fg=C["green"])
        self._log_gui(f"Fundamentals done — {len(data)} stocks.")

    def _send_fundamentals(self):
        self._log_gui("Sending fundamentals report…")
        threading.Thread(target=self._do_send_fundamentals, daemon=True).start()

    def _do_send_fundamentals(self):
        try:
            from sources.fundamentals import get_watchlist_fundamentals
            from formatter import format_fundamentals_report
            data = get_watchlist_fundamentals(config.WATCHLIST)
            ok   = sender.send_long(format_fundamentals_report(data))
            log_queue.put(("log", f"Fundamentals report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Fundamentals send: {e}")

    def _fund_deep_dive(self):
        sym = self.fund_sym_var.get().strip().upper()
        if not sym: return
        if not sym.endswith(".NS"): sym += ".NS"
        self._log_gui(f"Deep dive fundamentals: {sym}…")
        def _run():
            try:
                from sources.fundamentals import get_fundamentals
                from formatter import format_single_fundamental
                r = get_fundamentals(sym)
                if r:
                    log_queue.put(("fund_detail", r))
                    sender.send_long(format_single_fundamental(r))
            except Exception as e:
                log.error(f"Fund deep dive: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def _update_fund_detail_ui(self, r: dict):
        self.fund_detail_text.config(state="normal")
        self.fund_detail_text.delete("1.0","end")
        lines = [
            f"{r.get('overall','—')} — {r['symbol']}  ₹{r.get('price',0):,.2f}",
            f"Sector: {r.get('sector','—')}  Score: {r.get('score',0)}/8",
            "─"*40,
            f"P/E:           {r.get('pe','—')}  (Sector avg {r.get('sector_pe','—')})",
            f"P/E Flag:      {r.get('pe_flag','—')}",
            f"ROE:           {r.get('roe','—')}%  {r.get('roe_flag','')}",
            f"Debt/Equity:   {r.get('debt_eq','—')}%  {r.get('debt_flag','')}",
            f"Rev Growth:    {r.get('rev_growth','—')}%  {r.get('rev_flag','')}",
            f"Profit Margin: {r.get('profit_margin','—')}%",
            f"FCF:           {r.get('fcf_flag','—')}",
            f"Beta:          {r.get('beta','—')}",
            f"Dividend:      {r.get('div_yield','—')}%",
            f"Analyst:       {r.get('analyst_rec','—')}",
            f"Target Price:  ₹{r.get('target_price','—')}  ({r.get('upside','—')}% upside)",
        ]
        self.fund_detail_text.insert("end", "\n".join(lines))
        self.fund_detail_text.config(state="disabled")

    def _refresh_global_macro(self):
        self._log_gui("Fetching global macro…")
        threading.Thread(target=self._fetch_global_macro, daemon=True).start()

    def _fetch_global_macro(self):
        try:
            from sources.global_macro import get_global_macro
            log_queue.put(("global_macro", get_global_macro()))
        except Exception as e:
            log.error(f"Global macro: {e}")

    def _update_global_macro_ui(self, macro: dict):
        data = macro.get("data",{})
        self.macro_detail_text.config(state="normal")
        self.macro_detail_text.delete("1.0","end")
        rows = [
            ("US 10Y Yield",  "US_10Y",    "%"),
            ("DXY Dollar Idx","DXY",       ""),
            ("India 10Y",     "INDIA_10Y", "%"),
            ("Brent Crude",   "CRUDE_WTI", "$"),
            ("Gold",          "GOLD",      "$"),
            ("US VIX",        "SP500_VIX", ""),
        ]
        lines = []
        for label, key, unit in rows:
            d   = data.get(key,{})
            val = d.get("price",0); pct = d.get("pct",0)
            arrow = "▲" if pct>0 else ("▼" if pct<0 else "─")
            lines.append(f"{label:<18} {unit}{val:<10} {arrow}{pct:+.2f}%")
        spread   = macro.get("spread",0)
        inverted = macro.get("inverted",False)
        lines.append(f"{'Yield Curve':<18} {spread:.3f}%    {'⚠ INVERTED' if inverted else 'Normal'}")
        self.macro_detail_text.insert("end", "\n".join(lines))
        self.macro_detail_text.config(state="disabled")
        sigs = macro.get("signals",[])
        if sigs:
            self._log_gui(f"Macro alerts: {len(sigs)} signals.")

    def _send_global_macro(self):
        threading.Thread(target=self._do_send_global_macro, daemon=True).start()

    def _do_send_global_macro(self):
        try:
            from sources.global_macro import get_global_macro
            from formatter import format_global_macro_report
            ok = sender.send_long(format_global_macro_report(get_global_macro()))
            log_queue.put(("log", f"Global macro {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Global macro send: {e}")

    # ── Trade Journal methods ─────────────────────────────────────────────────

    def _log_trade_entry(self):
        sym    = self.j_sym_var.get().strip().upper()
        entry_s= self.j_entry_var.get().strip()
        qty_s  = self.j_qty_var.get().strip()
        if not sym or not entry_s or not qty_s:
            self.j_status_lbl.config(text="Symbol, Entry, Qty required.", fg=C["red"]); return
        if not sym.endswith(".NS") and sym not in ("NIFTY50","BANKNIFTY"):
            sym += ".NS"
        try:
            entry  = float(entry_s.replace(",",""))
            qty    = int(qty_s)
            stop   = float(self.j_stop_var.get().replace(",",""))   if self.j_stop_var.get()   else None
            target = float(self.j_target_var.get().replace(",","")) if self.j_target_var.get() else None
        except ValueError:
            self.j_status_lbl.config(text="Invalid numbers.", fg=C["red"]); return
        from sources.journal import add_trade
        tid = add_trade(sym, entry, qty, stop_loss=stop, target=target,
                        reason=self.j_reason_var.get(), side=self.j_side_var.get())
        self.j_status_lbl.config(text=f"Trade #{tid} logged!", fg=C["green"])
        self.root.after(3000, lambda: self.j_status_lbl.config(text=""))
        self._refresh_journal_ui()
        self._log_gui(f"Trade logged: #{tid} {sym} {self.j_side_var.get()} {qty}@{entry}")

    def _close_trade_entry(self):
        tid_s  = self.j_close_id_var.get().strip()
        exit_s = self.j_exit_var.get().strip()
        if not tid_s or not exit_s:
            return
        try:
            tid  = int(tid_s)
            exit_p = float(exit_s.replace(",",""))
        except ValueError:
            return
        from sources.journal import close_trade
        result = close_trade(tid, exit_p, exit_reason=self.j_exit_reason_var.get())
        if result:
            pnl    = result.get("pnl",0)
            status = result.get("status","—")
            col    = C["green"] if pnl>=0 else C["red"]
            self.j_status_lbl.config(
                text=f"#{tid} closed: {status}  ₹{pnl:+,.2f}", fg=col)
            self.root.after(4000, lambda: self.j_status_lbl.config(text=""))
            self._refresh_journal_ui()

    def _open_close_dialog(self, event):
        item = self.open_tree.focus()
        if not item: return
        row = self.open_tree.item(item)["values"]
        if row:
            self.j_close_id_var.set(str(row[0]))

    def _refresh_journal_ui(self):
        from sources.journal import get_open_trades, get_closed_trades, get_performance_stats
        # Open trades
        for i in self.open_tree.get_children(): self.open_tree.delete(i)
        for t in get_open_trades():
            self.open_tree.insert("","end", values=(
                t["id"], t["symbol"].replace(".NS",""),
                t.get("side","BUY"),
                f"₹{t['entry_price']:,.2f}",
                t["qty"],
                f"₹{t['stop_loss']:,.2f}"  if t.get("stop_loss")  else "—",
                f"₹{t['target']:,.2f}"     if t.get("target")     else "—",
                t["entry_date"],
                (t.get("reason","")[:30]) if t.get("reason") else "—",
            ))
        # Closed trades
        for i in self.closed_tree.get_children(): self.closed_tree.delete(i)
        for t in get_closed_trades(limit=30):
            tag = t.get("status","BREAK_EVEN")
            self.closed_tree.insert("","end", tags=(tag,), values=(
                t["id"], t["symbol"].replace(".NS",""),
                f"₹{t['pnl']:+,.2f}" if t.get("pnl") is not None else "—",
                f"{t['pnl_pct']:+.2f}%" if t.get("pnl_pct") is not None else "—",
                tag,
            ))
        # Stats
        stats = get_performance_stats()
        self.stats_text.config(state="normal")
        self.stats_text.delete("1.0","end")
        if stats.get("total",0) == 0:
            self.stats_text.insert("end","No closed trades yet.\nStart logging your trades!")
        else:
            lines = [
                f"Grade:       {stats.get('grade','—')}",
                f"Total Trades {stats['total']}",
                f"Wins         {stats['wins']} ({stats['win_rate']:.1f}%)",
                f"Losses       {stats['losses']}",
                "─"*32,
                f"Avg Win      ₹{stats['avg_win']:,.2f}",
                f"Avg Loss     ₹{stats['avg_loss']:,.2f}",
                f"R:R Ratio    {stats['rr_ratio']:.2f}",
                f"Expectancy   ₹{stats['expectancy']:,.2f}/trade",
                "─"*32,
                f"Total P&L    ₹{stats['total_pnl']:,.2f}",
            ]
            self.stats_text.insert("end","\n".join(lines))
        self.stats_text.config(state="disabled")

    def _refresh_journal_stats(self):
        self._refresh_journal_ui()
        self._log_gui("Journal stats refreshed.")

    def _send_journal_stats(self):
        threading.Thread(target=self._do_send_journal, daemon=True).start()

    def _do_send_journal(self):
        try:
            from sources.journal import get_performance_stats
            from formatter import format_journal_stats
            ok = sender.send_long(format_journal_stats(get_performance_stats()))
            log_queue.put(("log", f"Journal stats {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Journal send: {e}")

    def _build_tab_holdings(self):
        f = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(f, text="  Holdings  ")

        SectionLabel(f, "Add / Edit Holding").pack(anchor="w", pady=(10, 4))
        form = Card(f)
        form.pack(fill="x", pady=(0, 8))

        r1 = tk.Frame(form, bg=C["bg2"])
        r1.pack(fill="x", pady=(0, 6))
        self.h_sym_var   = tk.StringVar()
        self.h_qty_var   = tk.StringVar()
        self.h_avg_var   = tk.StringVar()
        for lbl, var, w, ph in [
            ("Symbol",    self.h_sym_var,  14, "RELIANCE.NS"),
            ("Qty",       self.h_qty_var,  8,  "50"),
            ("Avg Price ₹",self.h_avg_var, 10, "2650.00"),
        ]:
            tk.Label(r1, text=lbl, bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 8), width=12, anchor="w").pack(side="left")
            e = tk.Entry(r1, textvariable=var, bg=C["bg3"], fg=C["text"],
                         insertbackground=C["text"], relief="flat",
                         font=("Courier", 10), width=w,
                         highlightbackground=C["border"], highlightthickness=1)
            e.pack(side="left", padx=(0, 12))

        r2 = tk.Frame(form, bg=C["bg2"])
        r2.pack(fill="x")
        self.h_editing_idx = None
        self.h_save_btn = HermesButton(r2, "＋  ADD HOLDING", self._save_holding, accent=True)
        self.h_save_btn.pack(side="left", padx=(0, 6))
        HermesButton(r2, "✕  CLEAR", self._clear_holding_form).pack(side="left")
        self.h_status_lbl = tk.Label(r2, text="", bg=C["bg2"], fg=C["green"], font=("Courier", 8))
        self.h_status_lbl.pack(side="left", padx=10)

        SectionLabel(f, "Current Holdings").pack(anchor="w", pady=(6, 4))
        cols = ("Symbol","Qty","Avg Price","Actions")
        self.hold_tree = self._make_tree(f, cols, heights=12)
        self.hold_tree.pack(fill="both", expand=True, pady=(0, 8))
        for col in cols:
            self.hold_tree.heading(col, text=col)
            self.hold_tree.column(col, anchor="center", width=160, minwidth=80)
        self.hold_tree.column("Symbol", anchor="w", width=120)

        # watchlist section
        SectionLabel(f, "Watchlist — Add/Remove Symbols").pack(anchor="w", pady=(8, 4))
        wrow = tk.Frame(f, bg=C["bg"])
        wrow.pack(fill="x", pady=(0, 6))
        self.w_sym_var = tk.StringVar()
        tk.Entry(wrow, textvariable=self.w_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat", font=("Courier", 10), width=20,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        HermesButton(wrow, "＋ ADD", self._add_watchlist, accent=True).pack(side="left", padx=(0,4))
        HermesButton(wrow, "✕ REMOVE SELECTED", self._remove_watchlist).pack(side="left")

        cols2 = ("Symbol",)
        self.watch_tree = self._make_tree(f, cols2, heights=6)
        self.watch_tree.pack(fill="x")
        self.watch_tree.heading("Symbol", text="Watchlist")
        self.watch_tree.column("Symbol", anchor="w", width=200)

        self._populate_hold_tree()
        self._populate_watch_tree()

    # ── Right Panel ───────────────────────────────────────────────────────────

    def _build_right_panel(self, parent):
        tk.Frame(parent, bg=C["border"], width=1).pack(side="left", fill="y")
        inner = tk.Frame(parent, bg=C["bg"], padx=14, pady=12)
        inner.pack(fill="both", expand=True)

        SectionLabel(inner, "Market Status").pack(anchor="w", pady=(0, 4))
        sc = Card(inner)
        sc.pack(fill="x", pady=(0, 10))
        self.market_status_dot = tk.Label(sc, text="●", bg=C["bg2"], font=("Courier", 12))
        self.market_status_dot.pack(side="left")
        self.market_status_lbl = tk.Label(sc, text="Checking…", bg=C["bg2"],
                                           fg=C["muted"], font=("Courier", 9, "bold"))
        self.market_status_lbl.pack(side="left", padx=(6, 0))

        SectionLabel(inner, "Manual Triggers").pack(anchor="w", pady=(6, 4))
        self.brief_btn  = HermesButton(inner, "📨  SEND BRIEF",      self._trigger_brief, accent=True)
        self.sig_btn2   = HermesButton(inner, "🧠  SEND SIGNALS",    self._send_signals)
        self.ta_btn2    = HermesButton(inner, "📊  SEND TA SUMMARY", self._send_ta_summary)
        self.sent_btn   = HermesButton(inner, "🌡️  SEND SENTIMENT",  self._send_sentiment)
        self.opt_btn2   = HermesButton(inner, "🎯  SEND OPTIONS",    self._send_options)
        self.fund_btn2  = HermesButton(inner, "📈  SEND FUNDAMENTALS",self._send_fundamentals)
        self.macro_btn2 = HermesButton(inner, "🌐  SEND GLOBAL MACRO",self._send_global_macro)
        self.w52_btn    = HermesButton(inner, "📐  SEND 52W",        self._trigger_52w)
        self.corp_btn   = HermesButton(inner, "💰  SEND CORP ACT",   self._trigger_corporate)
        self.earn_btn   = HermesButton(inner, "🗓  SEND EARNINGS",   self._trigger_earnings)
        self.macro_btn  = HermesButton(inner, "📅  SEND MACRO EVT",  self._trigger_macro)
        self.test_btn   = HermesButton(inner, "🔌  TEST TELEGRAM",   self._test_telegram)
        for btn in (self.brief_btn, self.sig_btn2, self.ta_btn2, self.sent_btn,
                    self.opt_btn2, self.fund_btn2, self.macro_btn2,
                    self.w52_btn, self.corp_btn, self.earn_btn,
                    self.macro_btn, self.test_btn):
            btn.pack(fill="x", pady=2)

        SectionLabel(inner, "Schedule").pack(anchor="w", pady=(10, 4))
        sc2 = Card(inner)
        sc2.pack(fill="x", pady=(0, 8))
        for lbl, val in [
            ("Brief",    "08:00 IST"),
            ("52W",      "15:45 IST"),
            ("Corp Act", "06:00 IST"),
            ("Macro",    "06:30 IST"),
            ("Bulk/OI",  "Hourly"),
            ("Alerts",   f"/{config.ALERT_POLL_SECONDS}s"),
            ("Weekly",   "Sun 09:00"),
        ]:
            row = tk.Frame(sc2, bg=C["bg2"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=lbl+":", bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 7), width=10, anchor="w").pack(side="left")
            tk.Label(row, text=val, bg=C["bg2"], fg=C["teal"],
                     font=("Courier", 7, "bold")).pack(side="left")

        SectionLabel(inner, "Live Log").pack(anchor="w", pady=(4, 2))
        self.log_box = scrolledtext.ScrolledText(
            inner, bg=C["bg3"], fg=C["text"], font=("Courier", 7),
            relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1, wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("INFO",    foreground=C["text"])
        self.log_box.tag_config("WARNING", foreground=C["amber"])
        self.log_box.tag_config("ERROR",   foreground=C["red"])
        self.log_box.tag_config("DEBUG",   foreground=C["dim"])
        self.log_box.tag_config("SUCCESS", foreground=C["green"])
        tk.Button(inner, text="Clear Log", command=self._clear_log,
                  bg=C["bg3"], fg=C["dim"], relief="flat",
                  font=("Courier", 7), cursor="hand2").pack(anchor="e", pady=(2, 0))

    # ── Tree factory ──────────────────────────────────────────────────────────

    def _make_tree(self, parent, cols, heights=8) -> ttk.Treeview:
        s = ttk.Style()
        s.configure("H.Treeview", background=C["bg2"], foreground=C["text"],
                     fieldbackground=C["bg2"], rowheight=24, font=("Courier", 9), borderwidth=0)
        s.configure("H.Treeview.Heading", background=C["bg3"], foreground=C["muted"],
                     font=("Courier", 8, "bold"), relief="flat")
        s.map("H.Treeview", background=[("selected", C["bg4"])], foreground=[("selected", C["text"])])
        return ttk.Treeview(parent, columns=cols, show="headings",
                             style="H.Treeview", height=heights)

    def _metric_card(self, parent, label, value):
        f = Card(parent)
        f.pack(side="left", padx=(0, 8), pady=2)
        tk.Label(f, text=label, bg=C["bg2"], fg=C["muted"], font=("Courier", 8)).pack(anchor="w")
        v = tk.Label(f, text=value, bg=C["bg2"], fg=C["text"], font=("Courier", 14, "bold"))
        v.pack(anchor="w")
        return v

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _tick_clock(self):
        self.clock_label.config(text=datetime.now(IST).strftime("%d %b %Y  %H:%M:%S IST"))
        self._update_market_status()
        self.root.after(1000, self._tick_clock)

    def _update_market_status(self):
        now = datetime.now(IST)
        from datetime import time as dtime
        t      = now.time()
        open_t = dtime(config.MARKET_OPEN_HOUR, config.MARKET_OPEN_MINUTE)
        cls_t  = dtime(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)
        is_open = now.weekday() < 5 and open_t <= t <= cls_t
        if is_open:
            self.market_status_dot.config(fg=C["green"])
            self.market_status_lbl.config(text="MARKET OPEN",   fg=C["green"])
            self.status_dot.config(fg=C["green"])
            self.status_label.config(text="LIVE · NSE")
        else:
            self.market_status_dot.config(fg=C["red"])
            self.market_status_lbl.config(text="MARKET CLOSED", fg=C["red"])
            self.status_dot.config(fg=C["amber"])
            self.status_label.config(text="PRE/POST MARKET")

    def _is_market_open(self) -> bool:
        now = datetime.now(IST)
        if now.weekday() >= 5: return False
        from datetime import time as dtime
        t = now.time()
        return dtime(config.MARKET_OPEN_HOUR, config.MARKET_OPEN_MINUTE) <= t <= \
               dtime(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)

    # ─────────────────────────────────────────────────────────────────────────
    # DATA REFRESH — Portfolio
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_portfolio(self):
        self.refresh_btn.set_busy(True)
        self._log_gui("Fetching portfolio…")
        threading.Thread(target=self._fetch_portfolio, daemon=True).start()

    def _fetch_portfolio(self):
        try:
            rows = get_portfolio_pnl(config.PORTFOLIO)
            log_queue.put(("portfolio", rows))
        except Exception as e:
            log.error(f"Portfolio fetch: {e}")
            log_queue.put(("portfolio", []))

    def _update_portfolio_ui(self, rows: list):
        for i in self.port_tree.get_children():
            self.port_tree.delete(i)
        tot_day = tot_pnl = tot_val = tot_inv = 0
        for r in rows:
            sym  = r["symbol"].replace(".NS", "")
            pct  = r.get("pct", 0)
            dp   = r.get("day_pnl", 0)
            tp   = r.get("total_pnl", 0)
            tpp  = r.get("total_pnl_pct", 0)
            mv   = r.get("market_value", 0)
            inv  = r.get("qty", 0) * r.get("avg_price", 0)
            tot_day += dp; tot_pnl += tp; tot_val += mv; tot_inv += inv
            tag = "up" if pct >= 0 else "dn"
            self.port_tree.insert("", "end", tags=(tag,), values=(
                sym, f"₹{r['price']:,.2f}",
                f"{'+'if pct>=0 else ''}{pct:.2f}%",
                r["qty"], f"₹{r['avg_price']:,.2f}",
                f"{'+'if dp>=0 else ''}₹{dp:,.0f}",
                f"{'+'if tp>=0 else ''}₹{tp:,.0f}",
                f"{'+'if tpp>=0 else ''}{tpp:.2f}%",
                f"₹{mv:,.0f}",
            ))
        self.port_tree.tag_configure("up", foreground=C["green"])
        self.port_tree.tag_configure("dn", foreground=C["red"])

        def _col(v): return C["green"] if v >= 0 else C["red"]
        self.pnl_day_val.config(text=f"{'+'if tot_day>=0 else ''}₹{tot_day:,.0f}", fg=_col(tot_day))
        self.pnl_total_val.config(text=f"{'+'if tot_pnl>=0 else ''}₹{tot_pnl:,.0f}", fg=_col(tot_pnl))
        self.pnl_value_val.config(text=f"₹{tot_val:,.0f}", fg=C["text"])
        self.pnl_inv_val.config(text=f"₹{tot_inv:,.0f}", fg=C["muted"])
        self.last_refresh_lbl.config(text=f"Updated {datetime.now(IST).strftime('%H:%M:%S')} IST")
        self.refresh_btn.set_busy(False)
        self._log_gui(f"Portfolio refreshed — {len(rows)} holdings.")

    # ── Indices & Macro ───────────────────────────────────────────────────────

    def _refresh_indices(self):
        self._log_gui("Fetching indices + macro…")
        threading.Thread(target=self._fetch_indices, daemon=True).start()

    def _fetch_indices(self):
        try:
            indices  = get_indices()
            fii      = get_fii_dii_data()
            crude    = get_crude_price()
            inr      = get_inr_usd()
            global_m = get_global_markets()
            macro_ev = get_upcoming_macro_events(days_ahead=30)
            log_queue.put(("indices", (indices, fii, crude, inr, global_m, macro_ev)))
        except Exception as e:
            log.error(f"Indices fetch: {e}")

    def _update_indices_ui(self, data):
        indices, fii, crude, inr, global_m, macro_ev = data

        for i in self.idx_tree.get_children(): self.idx_tree.delete(i)
        for name, d in indices.items():
            tag = "up" if d["pct"] >= 0 else "dn"
            self.idx_tree.insert("", "end", tags=(tag,), values=(
                name, f"{d['price']:,.2f}",
                f"{'+'if d['change']>=0 else ''}{d['change']:,.2f}",
                f"{'+'if d['pct']>=0 else ''}{d['pct']:.2f}%",
            ))
        self.idx_tree.tag_configure("up", foreground=C["green"])
        self.idx_tree.tag_configure("dn", foreground=C["red"])

        for i in self.global_tree.get_children(): self.global_tree.delete(i)
        for g in global_m:
            tag = "up" if g["pct"] >= 0 else "dn"
            self.global_tree.insert("", "end", tags=(tag,), values=(
                g["name"], f"{g['price']:,.2f}", f"{'+'if g['pct']>=0 else ''}{g['pct']:.2f}%"))
        self.global_tree.tag_configure("up", foreground=C["green"])
        self.global_tree.tag_configure("dn", foreground=C["red"])

        def _inr_fmt(v):
            if abs(v) >= 1e7: return f"₹{v/1e7:.2f} Cr"
            if abs(v) >= 1e5: return f"₹{v/1e5:.2f} L"
            return f"₹{v:,.2f}"

        for key, lbl in self.fii_labels.items():
            val = fii.get(key, 0)
            lbl.config(text=_inr_fmt(val), fg=C["green"] if val >= 0 else C["red"])

        if crude and crude.get("price"):
            cp  = crude["pct"]
            col = C["green"] if cp >= 0 else C["red"]
            self.macro_labels["crude"].config(
                text=f"${crude['price']:.2f} ({'+' if cp>=0 else ''}{cp:.2f}%)", fg=col)
        if inr and inr.get("rate"):
            ip  = inr["pct"]
            col = C["red"] if ip >= 0 else C["green"]   # INR weakening is bad
            self.macro_labels["inr"].config(
                text=f"₹{inr['rate']:.2f} ({'+' if ip>=0 else ''}{ip:.4f})", fg=col)
        fn = fii.get("fii_net", 0)
        dn = fii.get("dii_net", 0)
        self.macro_labels["fii_net"].config(text=_inr_fmt(fn), fg=C["green"] if fn>=0 else C["red"])
        self.macro_labels["dii_net"].config(text=_inr_fmt(dn), fg=C["green"] if dn>=0 else C["red"])

        for i in self.macro_tree.get_children(): self.macro_tree.delete(i)
        for ev in macro_ev:
            tag = "high" if ev["impact"] == "HIGH" else "medium"
            self.macro_tree.insert("", "end", tags=(tag,), values=(
                ev["event"], ev["date"], f"{ev['days_out']}d", ev["impact"]))

        self._log_gui("Indices + macro refreshed.")

    # ── Signals ───────────────────────────────────────────────────────────────

    def _refresh_signals(self):
        self.sig_refresh_btn.set_busy(True)
        self.sig_status_lbl.config(text="Scanning all sources…", fg=C["muted"])
        self._log_gui("Running full signal scan…")
        threading.Thread(target=self._fetch_signals, daemon=True).start()

    def _fetch_signals(self):
        try:
            sigs = collect_all_signals(config.WATCHLIST)
            log_queue.put(("signals", sigs))
        except Exception as e:
            log.error(f"Signal scan: {e}")
            log_queue.put(("signals", []))

    def _update_signals_ui(self, sigs: list):
        self.signals_cache = sigs
        self._filter_signals()
        self.sig_refresh_btn.set_busy(False)
        self.sig_status_lbl.config(text=f"{len(sigs)} signals found.", fg=C["green"])
        self._log_gui(f"Signal scan complete — {len(sigs)} signals.")

    def _filter_signals(self):
        tf   = self.sig_tf_var.get()
        sigs = filter_by_timeframe(self.signals_cache, tf) if self.signals_cache else []
        for i in self.sig_tree.get_children(): self.sig_tree.delete(i)
        for s in sigs:
            self.sig_tree.insert("", "end", tags=(s["severity"],), values=(
                s["symbol"], s["type"], s["severity"], s["timeframe"], s["summary"]))

    def _send_signals(self):
        self.sig_send_btn.set_busy(True)
        self._log_gui("Sending signal digest to Telegram…")
        threading.Thread(target=self._do_send_signals, daemon=True).start()

    def _do_send_signals(self):
        try:
            sigs = self.signals_cache or collect_all_signals(config.WATCHLIST)
            tf   = self.sig_tf_var.get()
            msg  = format_signal_digest(sigs, tf)
            ok   = sender.send_long(msg)
            log_queue.put(("sig_send_done", ok))
        except Exception as e:
            log.error(f"Signal send: {e}")
            log_queue.put(("sig_send_done", False))

    # ── 52W ───────────────────────────────────────────────────────────────────

    def _refresh_52w(self):
        self._log_gui("Running 52W analysis…")
        threading.Thread(target=lambda: log_queue.put(
            ("w52", get_52w_analysis(config.WATCHLIST, config.DANGER_ZONE_PCT))),
            daemon=True).start()

    def _update_52w_ui(self, data: list):
        for i in self.w52_tree.get_children(): self.w52_tree.delete(i)
        for s in data:
            sym = s["symbol"].replace(".NS","")
            bl  = round(s["position_pct"]/100*12)
            bar = "█"*bl + "░"*(12-bl)
            st  = "⚠ DANGER" if s["danger"] else ("NEAR HIGH" if s["pct_from_high"]<5 else "OK")
            tag = "danger" if s["danger"] else ("warn" if s["pct_from_high"]<10 else "safe")
            self.w52_tree.insert("", "end", tags=(tag,), values=(
                sym, f"₹{s['price']:,.2f}", f"₹{s['week52l']:,.2f}", f"₹{s['week52h']:,.2f}",
                f"{s['pct_from_low']:.1f}%", f"{s['pct_from_high']:.1f}%", bar, st))
        self._log_gui(f"52W done — {len(data)} stocks.")

    # ── Earnings ──────────────────────────────────────────────────────────────

    def _refresh_earnings(self):
        self._log_gui("Fetching earnings…")
        threading.Thread(target=lambda: log_queue.put(
            ("earnings", get_earnings_calendar(config.WATCHLIST))), daemon=True).start()

    def _update_earnings_ui(self, data: list):
        for i in self.earn_tree.get_children(): self.earn_tree.delete(i)
        for e in data:
            sym  = e["symbol"].replace(".NS","")
            days = e["days_out"]
            tag  = "urgent" if days<=3 else ("soon" if days<=7 else "ok")
            st   = "⚠ GET READY" if days<=3 else ("Soon" if days<=7 else "Upcoming")
            self.earn_tree.insert("", "end", tags=(tag,), values=(sym, str(e["date"]), f"{days}d", st))
        self._log_gui(f"Earnings loaded — {len(data)} events.")

    # ── Corporate Actions ─────────────────────────────────────────────────────

    def _refresh_corporate(self):
        self._log_gui("Fetching corporate actions…")
        threading.Thread(target=self._fetch_corporate, daemon=True).start()

    def _fetch_corporate(self):
        try:
            data = get_corporate_actions(config.WATCHLIST, days_ahead=30)
            log_queue.put(("corporate", data))
        except Exception as e:
            log.error(f"Corporate fetch: {e}")
            log_queue.put(("corporate", []))

    def _update_corporate_ui(self, data: list):
        for i in self.corp_tree.get_children(): self.corp_tree.delete(i)
        for a in data:
            sym  = a["symbol"]
            tag  = "urgent" if a["urgent"] else ("soon" if a["days_out"]<=14 else "ok")
            urg  = "🚨 YES" if a["urgent"] else "—"
            self.corp_tree.insert("", "end", tags=(tag,), values=(
                sym, a["category"], a["action"][:50], a["ex_date"], f"{a['days_out']}d", urg))
        self._log_gui(f"Corporate actions loaded — {len(data)} items.")

    # ── Holdings Manager ──────────────────────────────────────────────────────

    def _save_holding(self):
        sym = self.h_sym_var.get().strip().upper()
        if not sym: self.h_status_lbl.config(text="Symbol required.", fg=C["red"]); return
        if not sym.endswith(".NS") and sym not in ("NIFTY50","BANKNIFTY"):
            sym += ".NS"
        try:
            qty = int(self.h_qty_var.get().strip())
            avg = float(self.h_avg_var.get().strip())
        except ValueError:
            self.h_status_lbl.config(text="Qty and Avg must be numbers.", fg=C["red"]); return

        h = {"symbol": sym, "qty": qty, "avg_price": avg}
        if self.h_editing_idx is not None:
            config.PORTFOLIO[self.h_editing_idx] = h
            self.h_editing_idx = None
            self.h_save_btn.config(text="＋  ADD HOLDING")
        else:
            config.PORTFOLIO.append(h)

        store_save("holdings", config.PORTFOLIO)
        # Rebuild watchlist from portfolio if not already there
        port_syms = {p["symbol"] for p in config.PORTFOLIO}
        for s in port_syms:
            if s not in config.WATCHLIST:
                config.WATCHLIST.append(s)
        store_save("watchlist", config.WATCHLIST)

        self._populate_hold_tree()
        self._populate_watch_tree()
        self._clear_holding_form()
        self.h_status_lbl.config(text=f"Saved {sym}.", fg=C["green"])
        self.root.after(3000, lambda: self.h_status_lbl.config(text=""))
        log.info(f"Holding saved: {h}")

    def _edit_holding(self, idx: int):
        h = config.PORTFOLIO[idx]
        self.h_sym_var.set(h["symbol"])
        self.h_qty_var.set(str(h["qty"]))
        self.h_avg_var.set(str(h["avg_price"]))
        self.h_editing_idx = idx
        self.h_save_btn.config(text="✎  SAVE HOLDING")

    def _delete_holding(self, idx: int):
        h = config.PORTFOLIO[idx]
        if messagebox.askyesno("Delete", f"Delete {h['symbol']} ({h['qty']} shares)?"):
            config.PORTFOLIO.pop(idx)
            store_save("holdings", config.PORTFOLIO)
            self._populate_hold_tree()
            self._clear_holding_form()

    def _clear_holding_form(self):
        self.h_sym_var.set(""); self.h_qty_var.set(""); self.h_avg_var.set("")
        self.h_editing_idx = None
        self.h_save_btn.config(text="＋  ADD HOLDING")

    def _populate_hold_tree(self):
        for i in self.hold_tree.get_children(): self.hold_tree.delete(i)
        for idx, h in enumerate(config.PORTFOLIO):
            self.hold_tree.insert("", "end", values=(
                h["symbol"].replace(".NS",""), h["qty"],
                f"₹{h['avg_price']:,.2f}", f"Edit({idx})  Del({idx})"))

        # Bind double-click to edit
        def _on_double(event):
            item = self.hold_tree.focus()
            if not item: return
            row   = self.hold_tree.index(item)
            self._edit_holding(row)
        self.hold_tree.bind("<Double-1>", _on_double)

        # Right-click context menu
        menu = tk.Menu(self.root, tearoff=0, bg=C["bg3"], fg=C["text"])
        menu.add_command(label="Edit",   command=lambda: self._edit_holding(
            self.hold_tree.index(self.hold_tree.focus())))
        menu.add_command(label="Delete", command=lambda: self._delete_holding(
            self.hold_tree.index(self.hold_tree.focus())))
        def _popup(event):
            try: menu.tk_popup(event.x_root, event.y_root)
            finally: menu.grab_release()
        self.hold_tree.bind("<Button-3>", _popup)

    def _add_watchlist(self):
        sym = self.w_sym_var.get().strip().upper()
        if not sym: return
        if not sym.endswith(".NS") and sym not in ("NIFTY50","BANKNIFTY"):
            sym += ".NS"
        if sym not in config.WATCHLIST:
            config.WATCHLIST.append(sym)
            store_save("watchlist", config.WATCHLIST)
            self._populate_watch_tree()
        self.w_sym_var.set("")

    def _remove_watchlist(self):
        item = self.watch_tree.focus()
        if not item: return
        idx = self.watch_tree.index(item)
        sym = config.WATCHLIST[idx]
        if messagebox.askyesno("Remove", f"Remove {sym} from watchlist?"):
            config.WATCHLIST.pop(idx)
            store_save("watchlist", config.WATCHLIST)
            self._populate_watch_tree()

    def _populate_watch_tree(self):
        for i in self.watch_tree.get_children(): self.watch_tree.delete(i)
        for sym in config.WATCHLIST:
            self.watch_tree.insert("", "end", values=(sym,))

    # ─────────────────────────────────────────────────────────────────────────
    # ALERTS CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def _save_alert(self):
        sym   = self.alert_sym_var.get().strip().upper()
        cond  = self.alert_cond_var.get()
        try:
            level = float(self.alert_level_var.get().replace(",",""))
            cool  = float(self.alert_cool_var.get())
        except ValueError:
            self._form_status("Level and cooldown must be numbers.", error=True); return
        if not sym: self._form_status("Symbol required.", error=True); return
        if not sym.endswith(".NS") and sym not in ("NIFTY50","BANKNIFTY","SENSEX","^NSEI"):
            sym += ".NS"
        a = {"symbol": sym, "condition": cond, "level": level, "cooldown_hours": cool}
        if self.alert_editing_idx is not None:
            config.PRICE_ALERTS[self.alert_editing_idx] = a
            self.alert_editing_idx = None
            self.alert_save_btn.config(text="＋  ADD ALERT")
        else:
            config.PRICE_ALERTS.append(a)
        store_save("alerts", config.PRICE_ALERTS)
        self._populate_alert_rows()
        self._clear_alert_form()
        self._form_status(f"Saved: {sym} {cond} ₹{level:,.2f}")
        log.info(f"Alert saved: {a}")

    def _edit_alert(self, idx: int):
        a = config.PRICE_ALERTS[idx]
        self.alert_sym_var.set(a["symbol"])
        self.alert_cond_var.set(a["condition"])
        self.alert_level_var.set(str(a["level"]))
        self.alert_cool_var.set(str(a["cooldown_hours"]))
        self.alert_editing_idx = idx
        self.alert_save_btn.config(text="✎  SAVE CHANGES")

    def _delete_alert(self, idx: int):
        a = config.PRICE_ALERTS[idx]
        if messagebox.askyesno("Delete", f"Delete {a['symbol']} {a['condition']} {a['level']}?"):
            config.PRICE_ALERTS.pop(idx)
            store_save("alerts", config.PRICE_ALERTS)
            self._populate_alert_rows()
            if self.alert_editing_idx == idx: self._clear_alert_form()

    def _clear_alert_form(self):
        self.alert_sym_var.set(""); self.alert_cond_var.set("below")
        self.alert_level_var.set(""); self.alert_cool_var.set("4")
        self.alert_editing_idx = None
        self.alert_save_btn.config(text="＋  ADD ALERT")
        self.form_status_lbl.config(text="")

    def _form_status(self, msg: str, error: bool = False):
        self.form_status_lbl.config(text=msg, fg=C["red"] if error else C["green"])
        self.root.after(4000, lambda: self.form_status_lbl.config(text=""))

    def _populate_alert_rows(self):
        for w in self.alert_inner.winfo_children(): w.destroy()
        self.alert_vars.clear()
        if not config.PRICE_ALERTS:
            tk.Label(self.alert_inner, text="No alerts. Add one above.",
                     bg=C["bg"], fg=C["dim"], font=("Courier", 9)).pack(pady=20)
            return
        for i, a in enumerate(config.PRICE_ALERTS):
            key = f"{a['symbol']}_{a['condition']}_{a['level']}"
            var = tk.BooleanVar(value=True)
            self.alert_vars[key] = var
            row = Card(self.alert_inner)
            row.pack(fill="x", pady=3)
            sym = a["symbol"].replace(".NS","")
            dir_col = C["red"] if a["condition"]=="below" else C["green"]
            direction = "▼ BELOW" if a["condition"]=="below" else "▲ ABOVE"

            lf = tk.Frame(row, bg=C["bg2"]); lf.pack(side="left", fill="x", expand=True)
            tk.Label(lf, text=sym, bg=C["bg2"], fg=C["text"],
                     font=("Courier", 11, "bold")).pack(anchor="w")
            tk.Label(lf, text=f"{direction}  ₹{a['level']:,.2f}  ·  cooldown {a['cooldown_hours']}h",
                     bg=C["bg2"], fg=dir_col, font=("Courier", 8)).pack(anchor="w")

            rf = tk.Frame(row, bg=C["bg2"]); rf.pack(side="right")
            sl = tk.Label(rf, text="ARMED", bg=C["bg2"], fg=C["green"], font=("Courier", 8, "bold"))
            sl.pack(side="left", padx=(0,6))

            def _tog(v=var, lbl=sl, r=row):
                def _fn():
                    lbl.config(text="ARMED" if v.get() else "OFF",
                               fg=C["green"] if v.get() else C["dim"])
                    r.config(highlightbackground=C["border"] if v.get() else C["dim"])
                return _fn
            tk.Checkbutton(rf, variable=var, bg=C["bg2"], activebackground=C["bg2"],
                           selectcolor=C["green_dim"], fg=C["green"],
                           command=_tog()).pack(side="left", padx=(0,4))
            tk.Button(rf, text="✎", bg=C["bg3"], fg=C["blue"], relief="flat",
                      font=("Courier",10), cursor="hand2", padx=4,
                      command=lambda idx=i: self._edit_alert(idx)).pack(side="left", padx=(0,4))
            tk.Button(rf, text="✕", bg=C["bg3"], fg=C["red"], relief="flat",
                      font=("Courier",10), cursor="hand2", padx=4,
                      command=lambda idx=i: self._delete_alert(idx)).pack(side="left")

    # ─────────────────────────────────────────────────────────────────────────
    # TELEGRAM TRIGGERS
    # ─────────────────────────────────────────────────────────────────────────

    def _trigger_brief(self):
        self.brief_btn.set_busy(True)
        self._log_gui("Sending extended brief…")
        threading.Thread(target=self._do_brief, daemon=True).start()

    def _do_brief(self):
        try:
            indices    = get_indices()
            port_pnl   = get_portfolio_pnl(config.PORTFOLIO)
            fii        = get_fii_dii_data()
            news       = get_news_headlines(config.WATCHLIST, max_per_stock=2)
            earnings   = get_earnings_calendar(config.WATCHLIST)
            soon       = [e for e in earnings if e["days_out"] <= config.EARNINGS_REMINDER_DAYS]
            signals    = collect_all_signals(config.WATCHLIST)
            today_sigs = filter_by_timeframe(signals, "TODAY")
            crude      = get_crude_price()
            inr        = get_inr_usd()
            global_m   = get_global_markets()
            macro_ev   = get_upcoming_macro_events(days_ahead=7)
            msg = format_morning_brief_extended(
                indices, port_pnl, fii, news, soon, today_sigs,
                crude, inr, global_m, macro_ev)
            ok = sender.send_long(msg)
            log_queue.put(("brief_done", ok))
        except Exception as e:
            log.error(f"Brief: {e}")
            log_queue.put(("brief_done", False))

    def _trigger_52w(self):
        self.w52_btn.set_busy(True)
        threading.Thread(target=self._do_52w_send, daemon=True).start()

    def _do_52w_send(self):
        try:
            msg = format_52w_report(get_52w_analysis(config.WATCHLIST, config.DANGER_ZONE_PCT))
            ok  = sender.send_long(msg)
            log_queue.put(("w52_send_done", ok))
        except Exception as e:
            log.error(f"52W send: {e}")
            log_queue.put(("w52_send_done", False))

    def _trigger_earnings(self):
        self.earn_btn.set_busy(True)
        threading.Thread(target=self._do_earn_send, daemon=True).start()

    def _do_earn_send(self):
        try:
            ok = sender.send_long(format_earnings_reminder(get_earnings_calendar(config.WATCHLIST)))
            log_queue.put(("earn_send_done", ok))
        except Exception as e:
            log.error(f"Earnings send: {e}")
            log_queue.put(("earn_send_done", False))

    def _trigger_corporate(self):
        self.corp_btn.set_busy(True)
        self._log_gui("Sending corporate actions…")
        threading.Thread(target=self._do_corp_send, daemon=True).start()

    def _do_corp_send(self):
        try:
            actions = get_corporate_actions(config.WATCHLIST, days_ahead=30)
            for a in [x for x in actions if x["urgent"]]:
                sender.send(format_corporate_action_alert(a))
            ok = True
            log_queue.put(("corp_send_done", ok))
        except Exception as e:
            log.error(f"Corp send: {e}")
            log_queue.put(("corp_send_done", False))

    def _trigger_macro(self):
        self.macro_btn.set_busy(True)
        threading.Thread(target=self._do_macro_send, daemon=True).start()

    def _do_macro_send(self):
        try:
            events = get_upcoming_macro_events(days_ahead=7)
            crude  = get_crude_price()
            inr    = get_inr_usd()
            for ev in events[:3]:
                sender.send(format_macro_alert(ev, crude, inr))
            log_queue.put(("macro_send_done", True))
        except Exception as e:
            log.error(f"Macro send: {e}")
            log_queue.put(("macro_send_done", False))

    def _test_telegram(self):
        self.test_btn.set_busy(True)
        threading.Thread(target=self._do_test, daemon=True).start()

    def _do_test(self):
        ok = sender.test_connection()
        if ok: sender.send("🟢 *Hermes GUI v2* connected\\!", parse_mode="MarkdownV2")
        log_queue.put(("telegram_test", ok))

    # ─────────────────────────────────────────────────────────────────────────
    # LOG
    # ─────────────────────────────────────────────────────────────────────────

    def _log_gui(self, msg: str, level: str = "INFO"):
        log_queue.put(("log", f"{datetime.now(IST).strftime('%H:%M:%S')} [GUI] {level} — {msg}"))

    def _append_log(self, msg: str):
        self.log_box.config(state="normal")
        tag = "ERROR" if "ERROR" in msg else \
              "WARNING" if "WARNING" in msg else \
              "SUCCESS" if ("✅" in msg or "sent" in msg.lower()) else "INFO"
        self.log_box.insert("end", msg+"\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")
        if int(self.log_box.index("end-1c").split(".")[0]) > 500:
            self.log_box.config(state="normal")
            self.log_box.delete("1.0","50.0")
            self.log_box.config(state="disabled")

    def _append_alert_log(self, msg: str):
        self.alert_log.config(state="normal")
        self.alert_log.insert("end", msg+"\n")
        self.alert_log.see("end")
        self.alert_log.config(state="disabled")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0","end")
        self.log_box.config(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # QUEUE POLL
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                kind, data = log_queue.get_nowait()
                if   kind == "log":           self._append_log(data)
                elif kind == "portfolio":     self._update_portfolio_ui(data)
                elif kind == "indices":       self._update_indices_ui(data)
                elif kind == "w52":           self._update_52w_ui(data)
                elif kind == "earnings":      self._update_earnings_ui(data)
                elif kind == "signals":       self._update_signals_ui(data)
                elif kind == "corporate":     self._update_corporate_ui(data)
                elif kind == "ta":            self._update_ta_ui(data)
                elif kind == "risk":          self._update_risk_ui(data)
                elif kind == "checklist":     self._update_checklist_ui(data)
                elif kind == "sentiment":     self._update_sentiment_ui(data)
                elif kind == "options":       self._update_options_ui(data)
                elif kind == "promoter":      self._update_promoter_ui(data)
                elif kind == "fundamentals":  self._update_fundamentals_ui(data)
                elif kind == "fund_detail":   self._update_fund_detail_ui(data)
                elif kind == "global_macro":  self._update_global_macro_ui(data)
                elif kind == "sl_result":
                    self.sl_result_lbl.config(text=data)
                elif kind == "ta_send_done":
                    self.ta_send_btn.set_busy(False)
                    self._log_gui("✅ TA summary sent!" if data else "❌ TA send failed.")
                elif kind == "brief_done":
                    self.brief_btn.set_busy(False)
                    self._log_gui("✅ Brief sent!" if data else "❌ Brief failed.")
                elif kind == "w52_send_done":
                    self.w52_btn.set_busy(False)
                    self._log_gui("✅ 52W sent!" if data else "❌ 52W failed.")
                elif kind == "earn_send_done":
                    self.earn_btn.set_busy(False)
                    self._log_gui("✅ Earnings sent!" if data else "❌ Earnings failed.")
                elif kind == "corp_send_done":
                    self.corp_btn.set_busy(False)
                    self._log_gui("✅ Corp actions sent!" if data else "❌ Corp send failed.")
                elif kind == "macro_send_done":
                    self.macro_btn.set_busy(False)
                    self._log_gui("✅ Macro sent!" if data else "❌ Macro failed.")
                elif kind == "sig_send_done":
                    self.sig_send_btn.set_busy(False)
                    self._log_gui("✅ Signals sent!" if data else "❌ Signal send failed.")
                elif kind == "telegram_test":
                    self.test_btn.set_busy(False)
                    if data:
                        self._log_gui("✅ Telegram connected!")
                        messagebox.showinfo("Hermes","Connected! Check Telegram.")
                    else:
                        self._log_gui("❌ Telegram FAILED. Check .env", "ERROR")
                        messagebox.showerror("Hermes","Telegram failed.\nCheck .env file.")
                elif kind == "alert_fired":
                    sym, cond, level, price = data
                    self._append_alert_log(
                        f"{datetime.now(IST).strftime('%H:%M:%S')} — {sym} {cond} ₹{level:,.2f} @ ₹{price:,.2f}")
        except queue.Empty:
            pass
        if self.running:
            self.root.after(100, self._poll_queue)

    # ─────────────────────────────────────────────────────────────────────────
    # BACKGROUND THREADS
    # ─────────────────────────────────────────────────────────────────────────

    def _start_background_threads(self):
        self._setup_schedule()
        threading.Thread(target=self._run_schedule, daemon=True, name="Scheduler").start()
        threading.Thread(target=self._run_alerts,   daemon=True, name="AlertWatcher").start()
        threading.Thread(target=self._auto_refresh,  daemon=True, name="AutoRefresh").start()
        log.info("All background threads started.")

    def _setup_schedule(self):
        schedule.clear()
        schedule.every().day.at("06:00").do(self._trigger_corporate)
        schedule.every().day.at("06:30").do(self._trigger_macro)
        schedule.every().day.at(config.MORNING_BRIEF_TIME).do(self._trigger_brief)
        schedule.every().day.at(config.AFTER_MARKET_TIME).do(self._trigger_52w)
        schedule.every(1).hours.do(self._refresh_signals)
        schedule.every().sunday.at("09:00").do(self._send_signals)

    def _run_schedule(self):
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def _run_alerts(self):
        def _patched_poll():
            for alert in self.watcher.alerts:
                if self.watcher._on_cooldown(alert): continue
                from data_fetcher import get_price
                from formatter import format_price_alert
                price = get_price(alert["symbol"])
                if price is None: continue
                prev_key = self.watcher._prev_key(alert)
                prev = self.watcher.state.get(prev_key)
                if prev is not None: prev = float(prev)
                gui_key = f"{alert['symbol']}_{alert['condition']}_{alert['level']}"
                var = self.alert_vars.get(gui_key)
                if var and not var.get(): continue
                if self.watcher._crossed(alert, prev, price):
                    msg  = format_price_alert(alert["symbol"], alert["condition"], alert["level"], price)
                    sent = sender.send(msg)
                    if sent:
                        self.watcher._mark_fired(alert)
                        log_queue.put(("alert_fired", (alert["symbol"], alert["condition"], alert["level"], price)))
                self.watcher.state[prev_key] = price
            self.watcher._save_state()
        self.watcher.poll_once = _patched_poll
        self.watcher.run(self._is_market_open)

    def _auto_refresh(self):
        while self.running:
            time.sleep(300)
            if self._is_market_open():
                try:
                    rows = get_portfolio_pnl(config.PORTFOLIO)
                    log_queue.put(("portfolio", rows))
                    # Check trailing stops
                    for r in rows:
                        sym   = r["symbol"]
                        price = r.get("price")
                        if price:
                            alert = self.trail_tracker.update(sym, price)
                            if alert:
                                from formatter import format_trailing_stop_alert
                                sender.send(format_trailing_stop_alert(alert))
                                log_queue.put(("log", f"🛑 Trailing stop hit: {sym} @ ₹{price}"))
                    self._populate_trail_tree()
                except Exception as e:
                    log.error(f"Auto-refresh: {e}")

    def _on_close(self):
        self.running = False
        self.root.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.title("Hermes Agent v2")
    try: root.iconbitmap("")
    except Exception: pass
    HermesGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
