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


    # ─────────────────────────────────────────────────────────────────────────
    # UI BUILD — Clean 5-tab layout
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.configure(bg=C["bg"])
        self._build_topbar()
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")
        self._build_main_area()
        self._tick_clock()

    # ── Topbar ────────────────────────────────────────────────────────────────

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=C["bg"], pady=8, padx=20)
        bar.pack(fill="x")
        # Logo
        logo = tk.Frame(bar, bg=C["bg"]); logo.pack(side="left")
        tk.Label(logo, text="⚡", bg=C["bg"], fg=C["green"], font=("Helvetica",18)).pack(side="left")
        tk.Label(logo, text=" HERMES", bg=C["bg"], fg=C["text"],
                 font=("Helvetica",16,"bold")).pack(side="left")
        tk.Label(logo, text=" AGENT", bg=C["bg"], fg=C["green"],
                 font=("Helvetica",16,"bold")).pack(side="left")
        tk.Label(logo, text="  v2", bg=C["bg"], fg=C["dim"],
                 font=("Helvetica",10)).pack(side="left")

        # Right status cluster
        right = tk.Frame(bar, bg=C["bg"]); right.pack(side="right")

        # Market status pill
        self.mkt_pill = tk.Frame(right, bg=C["bg3"],
                                  highlightbackground=C["border"], highlightthickness=1)
        self.mkt_pill.pack(side="right", padx=(8,0))
        self.mkt_dot = tk.Label(self.mkt_pill, text="●", bg=C["bg3"],
                                 fg=C["green"], font=("Helvetica",10), padx=6)
        self.mkt_dot.pack(side="left")
        self.mkt_lbl = tk.Label(self.mkt_pill, text="CHECKING", bg=C["bg3"],
                                 fg=C["muted"], font=("Helvetica",9,"bold"), padx=6)
        self.mkt_lbl.pack(side="left")

        self.clock_label = tk.Label(right, text="", bg=C["bg"],
                                     fg=C["muted"], font=("Courier",9))
        self.clock_label.pack(side="right", padx=(0,12))

        # Telegram test button
        self.tg_status = tk.Label(right, text="🔌 TG", bg=C["bg"],
                                   fg=C["dim"], font=("Helvetica",9), cursor="hand2")
        self.tg_status.pack(side="right", padx=4)
        self.tg_status.bind("<Button-1>", lambda e: self._test_telegram())

    # ── Main area: sidebar + content ─────────────────────────────────────────

    def _build_main_area(self):
        self.main_frame = tk.Frame(self.root, bg=C["bg"])
        self.main_frame.pack(fill="both", expand=True)

        self._build_sidebar()
        self._build_content_area()

    def _build_sidebar(self):
        """Left sidebar with navigation buttons."""
        self.sidebar = tk.Frame(self.main_frame, bg=C["bg2"], width=170)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Frame(self.sidebar, bg=C["border"], height=1).pack(fill="x")

        # Nav sections
        self.nav_buttons = {}
        self._active_section = "dashboard"

        nav_items = [
            ("─── OVERVIEW", None),
            ("🏠  Dashboard",    "dashboard"),
            ("💼  My Stocks",    "stocks"),
            ("─── ANALYSIS", None),
            ("🧠  Signals",      "signals"),
            ("📊  Technicals",   "technicals"),
            ("🌐  Market",       "market"),
            ("─── MANAGE", None),
            ("🔔  Alerts",       "alerts"),
            ("🛡️  Risk",         "risk"),
            ("🎮  Paper Trade",  "paper"),
            ("─── REPORTING", None),
            ("📈  Fundamentals", "fundamentals"),
            ("📓  Journal",      "journal"),
            ("🧾  Tax & Balance","taxbal"),
            ("─── SETTINGS", None),
            ("⚙️  Holdings",     "holdings"),
        ]

        for label, key in nav_items:
            if key is None:
                # Section header
                tk.Label(self.sidebar, text=label, bg=C["bg2"], fg=C["dim"],
                         font=("Helvetica",8), anchor="w", padx=12, pady=4).pack(fill="x")
            else:
                btn = tk.Button(
                    self.sidebar, text=label, anchor="w",
                    bg=C["bg2"], fg=C["muted"],
                    activebackground=C["bg3"], activeforeground=C["text"],
                    relief="flat", font=("Helvetica",10), padx=12, pady=6,
                    cursor="hand2",
                    command=lambda k=key: self._nav(k),
                )
                btn.pack(fill="x")
                self.nav_buttons[key] = btn

        # Quick send buttons at bottom
        tk.Frame(self.sidebar, bg=C["border"], height=1).pack(fill="x", pady=(8,0))
        tk.Label(self.sidebar, text="─── QUICK SEND", bg=C["bg2"], fg=C["dim"],
                 font=("Helvetica",8), anchor="w", padx=12, pady=4).pack(fill="x")

        for label, cmd in [
            ("📨 Morning Brief",  self._trigger_brief),
            ("📋 Golden Rules",   self._send_golden_rules),
            ("📊 TA Summary",     self._send_ta_summary),
            ("🧾 Tax Report",     self._send_tax_report),
        ]:
            tk.Button(self.sidebar, text=label, anchor="w",
                      bg=C["bg2"], fg=C["teal"],
                      activebackground=C["bg3"], activeforeground=C["text"],
                      relief="flat", font=("Helvetica",9), padx=12, pady=4,
                      cursor="hand2", command=cmd).pack(fill="x")

        # Log at very bottom
        tk.Frame(self.sidebar, bg=C["border"], height=1).pack(fill="x", pady=(8,0))
        tk.Label(self.sidebar, text="─── LIVE LOG", bg=C["bg2"], fg=C["dim"],
                 font=("Helvetica",8), anchor="w", padx=12, pady=4).pack(fill="x")
        self.log_box = tk.Text(
            self.sidebar, bg=C["bg3"], fg=C["muted"],
            font=("Courier",7), relief="flat", wrap="word",
            state="disabled", height=8,
            highlightbackground=C["border"], highlightthickness=0)
        self.log_box.pack(fill="both", expand=True, padx=6, pady=(0,6))
        self.log_box.tag_config("INFO",    foreground=C["muted"])
        self.log_box.tag_config("SUCCESS", foreground=C["green"])
        self.log_box.tag_config("WARNING", foreground=C["amber"])
        self.log_box.tag_config("ERROR",   foreground=C["red"])

    def _nav(self, key: str):
        """Switch content panel."""
        # Deactivate old
        old = self.nav_buttons.get(self._active_section)
        if old:
            old.config(bg=C["bg2"], fg=C["muted"],
                       font=("Helvetica",10), relief="flat")
        # Activate new
        btn = self.nav_buttons.get(key)
        if btn:
            btn.config(bg=C["bg3"], fg=C["text"],
                       font=("Helvetica",10,"bold"), relief="flat")
        self._active_section = key
        # Show panel
        for k, panel in self.panels.items():
            if k == key:
                panel.pack(fill="both", expand=True)
            else:
                panel.pack_forget()

    def _build_content_area(self):
        self.content = tk.Frame(self.main_frame, bg=C["bg"])
        self.content.pack(side="left", fill="both", expand=True)

        # Status bar
        self.status_bar = tk.Frame(self.content, bg=C["bg4"], pady=3)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_lbl = tk.Label(self.status_bar, text="Ready", bg=C["bg4"],
                                    fg=C["dim"], font=("Helvetica",8), padx=10)
        self.status_lbl.pack(side="left")
        self.status_dot   = tk.Label(self.status_bar, text="●", bg=C["bg4"],
                                      fg=C["green"], font=("Helvetica",9))
        self.status_dot.pack(side="right", padx=4)
        self.status_label = tk.Label(self.status_bar, text="INITIALISING",
                                      bg=C["bg4"], fg=C["muted"], font=("Helvetica",8))
        self.status_label.pack(side="right")

        # Panel container (main body + right panel)
        body = tk.Frame(self.content, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=0)

        panel_area = tk.Frame(body, bg=C["bg"])
        panel_area.pack(side="left", fill="both", expand=True)

        # Right panel area (fixed width)
        right_area = tk.Frame(body, bg=C["bg"], width=320)
        right_area.pack(side="right", fill="y")
        right_area.pack_propagate(False)

        self.panels = {}
        sections = [
            ("dashboard",   self._build_panel_dashboard),
            ("stocks",      self._build_panel_stocks),
            ("signals",     self._build_panel_signals),
            ("technicals",  self._build_panel_technicals),
            ("market",      self._build_panel_market),
            ("alerts",      self._build_panel_alerts),
            ("risk",        self._build_panel_risk),
            ("paper",       self._build_panel_paper),
            ("fundamentals",self._build_panel_fundamentals),
            ("journal",     self._build_panel_journal),
            ("taxbal",      self._build_panel_taxbal),
            ("holdings",    self._build_panel_holdings),
        ]
        for key, builder in sections:
            panel = tk.Frame(panel_area, bg=C["bg"])
            self.panels[key] = panel
            builder(panel)

        # Build right panel widgets (market status, triggers, schedule)
        self._build_right_panel(right_area)

        # Show dashboard first
        self._nav("dashboard")

    # ─────────────────────────────────────────────────────────────────────────
    # PANEL BUILDERS
    # ─────────────────────────────────────────────────────────────────────────

    # ── Helper widgets ────────────────────────────────────────────────────────

    def _card(self, parent, title=None, padx=12, pady=8):
        outer = tk.Frame(parent, bg=C["bg2"],
                         highlightbackground=C["border"], highlightthickness=1)
        if title:
            tk.Label(outer, text=title.upper(), bg=C["bg2"], fg=C["dim"],
                     font=("Helvetica",8,"bold"), padx=padx, pady=4,
                     anchor="w").pack(fill="x")
            tk.Frame(outer, bg=C["border"], height=1).pack(fill="x")
        inner = tk.Frame(outer, bg=C["bg2"], padx=padx, pady=pady)
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _stat_box(self, parent, label, value="—", value_color=None):
        f = tk.Frame(parent, bg=C["bg3"],
                     highlightbackground=C["border2"], highlightthickness=1)
        f.pack(side="left", padx=(0,8), pady=4, fill="y")
        tk.Label(f, text=label, bg=C["bg3"], fg=C["muted"],
                 font=("Helvetica",8), padx=12, pady=4).pack(anchor="w")
        v = tk.Label(f, text=value, bg=C["bg3"],
                     fg=value_color or C["text"],
                     font=("Helvetica",16,"bold"), padx=12, pady=2)
        v.pack(anchor="w")
        return v

    def _section(self, parent, text):
        f = tk.Frame(parent, bg=C["bg"]); f.pack(fill="x", pady=(10,4))
        tk.Label(f, text=text.upper(), bg=C["bg"], fg=C["dim"],
                 font=("Helvetica",8,"bold")).pack(side="left")
        tk.Frame(f, bg=C["border"], height=1).pack(side="left", fill="x", expand=True, padx=(8,0))

    def _btn(self, parent, text, cmd, accent=False, small=False):
        col  = C["green"] if accent else C["muted"]
        font = ("Helvetica", 8 if small else 9, "bold")
        b = tk.Button(parent, text=text, command=cmd,
                      bg=C["bg3"], fg=col,
                      activebackground=C["bg4"], activeforeground=C["text"],
                      relief="flat",
                      highlightbackground=C["border"], highlightthickness=1,
                      font=font, padx=10, pady=4 if not small else 2,
                      cursor="hand2")
        return b

    def _tree(self, parent, cols, heights=8, col_widths=None):
        style = ttk.Style()
        style.configure("H.Treeview",
                         background=C["bg2"], foreground=C["text"],
                         fieldbackground=C["bg2"], rowheight=26,
                         font=("Helvetica",9), borderwidth=0)
        style.configure("H.Treeview.Heading",
                         background=C["bg3"], foreground=C["muted"],
                         font=("Helvetica",8,"bold"), relief="flat")
        style.map("H.Treeview",
                  background=[("selected", C["bg4"])],
                  foreground=[("selected", C["text"])])
        frame = tk.Frame(parent, bg=C["bg"])
        frame.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(frame, orient="vertical")
        vsb.pack(side="right", fill="y")
        t = ttk.Treeview(frame, columns=cols, show="headings",
                          style="H.Treeview", height=heights,
                          yscrollcommand=vsb.set)
        vsb.config(command=t.yview)
        t.pack(side="left", fill="both", expand=True)
        for i, col in enumerate(cols):
            t.heading(col, text=col)
            w = (col_widths[i] if col_widths and i < len(col_widths) else 100)
            t.column(col, anchor="center", width=w, minwidth=50)
        return t

    def _entry_row(self, parent, label, var, width=14, bg=None):
        bg = bg or C["bg"]
        row = tk.Frame(parent, bg=bg); row.pack(fill="x", pady=2)
        tk.Label(row, text=label, bg=bg, fg=C["muted"],
                 font=("Helvetica",9), width=14, anchor="w").pack(side="left")
        e = tk.Entry(row, textvariable=var, bg=C["bg3"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     font=("Courier",10), width=width,
                     highlightbackground=C["border"], highlightthickness=1)
        e.pack(side="left")
        return e

    def _scrolltext(self, parent, height=8, fg=None):
        t = scrolledtext.ScrolledText(
            parent, height=height, bg=C["bg3"], fg=fg or C["text"],
            font=("Courier",8), relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1, wrap="word")
        t.pack(fill="both", expand=True, pady=(0,4))
        return t

    # ─────────────────────────────────────────────────────────────────────────
    # DASHBOARD PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_dashboard(self, f):
        f.configure(bg=C["bg"])
        top = tk.Frame(f, bg=C["bg"], padx=16, pady=10)
        top.pack(fill="x")

        # Market mood banner
        self.mood_banner = tk.Label(
            top, text="⟳  LOADING MARKET DATA…",
            bg=C["bg3"], fg=C["muted"],
            font=("Helvetica",13,"bold"),
            pady=10, relief="flat",
            highlightbackground=C["border"], highlightthickness=1)
        self.mood_banner.pack(fill="x", pady=(0,12))

        # Stat row
        stat_row = tk.Frame(top, bg=C["bg"]); stat_row.pack(fill="x", pady=(0,10))
        self.dash_day_pnl   = self._stat_box(stat_row, "Day P&L",     "—")
        self.dash_total_pnl = self._stat_box(stat_row, "Total P&L",   "—")
        self.dash_port_val  = self._stat_box(stat_row, "Portfolio",    "—")
        self.dash_vix       = self._stat_box(stat_row, "India VIX",   "—")
        self.dash_pcr       = self._stat_box(stat_row, "PCR",         "—")

        # Body: left = indices + holdings, right = golden rules + recent signals
        body = tk.Frame(top, bg=C["bg"]); body.pack(fill="both", expand=True)
        left  = tk.Frame(body, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = tk.Frame(body, bg=C["bg"]); right.pack(side="left", fill="both", expand=True)

        # Indices
        self._section(left, "Market Indices")
        self.dash_idx_tree = self._tree(left,
            ("Index","Price","Change","Chg%"), heights=4,
            col_widths=[160,100,100,80])
        self.dash_idx_tree.column("Index", anchor="w")
        self.dash_idx_tree.tag_configure("up", foreground=C["green"])
        self.dash_idx_tree.tag_configure("dn", foreground=C["red"])

        # Holdings P&L
        self._section(left, "Portfolio Today")
        self.dash_port_tree = self._tree(left,
            ("Stock","Price","Day P&L","Total P&L","Signal"), heights=7,
            col_widths=[100,90,100,100,90])
        self.dash_port_tree.column("Stock", anchor="w")
        self.dash_port_tree.tag_configure("up",  foreground=C["green"])
        self.dash_port_tree.tag_configure("dn",  foreground=C["red"])
        self.dash_port_tree.tag_configure("buy", foreground=C["teal"])

        btn_row = tk.Frame(left, bg=C["bg"]); btn_row.pack(fill="x", pady=(4,0))
        self.refresh_btn = self._btn(btn_row,"↻  Refresh Portfolio", self._refresh_portfolio, accent=True)
        self.refresh_btn.pack(side="left")
        self.last_refresh_lbl = tk.Label(btn_row, text="", bg=C["bg"],
                                          fg=C["dim"], font=("Helvetica",8))
        self.last_refresh_lbl.pack(side="left", padx=10)

        # Golden rules
        self._section(right, "Golden Rules — Today")
        _, ri = self._card(right)
        ri.pack_forget()
        rules_card, rules_inner = self._card(right)
        rules_card.pack(fill="x", pady=(0,8))
        self.dash_rules_lbl = tk.Label(rules_inner, text="Run rules check →",
                                        bg=C["bg2"], fg=C["muted"],
                                        font=("Helvetica",11,"bold"))
        self.dash_rules_lbl.pack(anchor="w", pady=(0,4))
        self.dash_rules_detail = tk.Label(rules_inner, text="",
                                           bg=C["bg2"], fg=C["muted"],
                                           font=("Helvetica",8), wraplength=320, justify="left")
        self.dash_rules_detail.pack(anchor="w")
        self._btn(rules_inner,"▶  Check Rules Now", self._refresh_golden_rules, accent=True).pack(anchor="w", pady=(8,0))

        # Top signals
        self._section(right, "Top Signals Today")
        self.dash_sig_tree = self._tree(right,
            ("Sev","Stock","Signal"), heights=6,
            col_widths=[70,80,320])
        self.dash_sig_tree.column("Signal", anchor="w")
        self.dash_sig_tree.tag_configure("CRITICAL", foreground=C["red"])
        self.dash_sig_tree.tag_configure("HIGH",     foreground=C["amber"])
        self.dash_sig_tree.tag_configure("MEDIUM",   foreground=C["teal"])

        # News ticker
        self._section(right, "Latest News")
        self.dash_news_text = tk.Text(right, height=5, bg=C["bg2"], fg=C["muted"],
                                       font=("Helvetica",9), relief="flat",
                                       state="disabled", wrap="word",
                                       highlightbackground=C["border"], highlightthickness=1)
        self.dash_news_text.pack(fill="x", pady=(0,8))
        self.dash_news_text.tag_config("green", foreground=C["green"])
        self.dash_news_text.tag_config("red",   foreground=C["red"])
        self.dash_news_text.tag_config("sym",   foreground=C["purple"], font=("Helvetica",9,"bold"))

    # ─────────────────────────────────────────────────────────────────────────
    # MY STOCKS PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_stocks(self, f):
        nb = self._sub_notebook(f)

        # Tab: Portfolio
        pt = tk.Frame(nb, bg=C["bg"]); nb.add(pt, text="  Portfolio  ")
        cards = tk.Frame(pt, bg=C["bg"], padx=12, pady=8); cards.pack(fill="x")
        self.pnl_day_val   = self._stat_box(cards,"Day P&L","—")
        self.pnl_total_val = self._stat_box(cards,"Overall P&L","—")
        self.pnl_value_val = self._stat_box(cards,"Market Value","—")
        self.pnl_inv_val   = self._stat_box(cards,"Invested","—")

        self._section(pt, "Holdings")
        cols = ("Symbol","Price","Chg%","Qty","Avg","Day P&L","Total P&L","Total%","Value")
        self.port_tree = self._tree(pt, cols, heights=12,
            col_widths=[110,90,70,55,90,95,95,75,95])
        self.port_tree.column("Symbol", anchor="w")
        self.port_tree.tag_configure("up", foreground=C["green"])
        self.port_tree.tag_configure("dn", foreground=C["red"])

        br = tk.Frame(pt, bg=C["bg"], padx=12); br.pack(fill="x", pady=4)
        self.refresh_btn = self._btn(br,"↻  Refresh", self._refresh_portfolio, accent=True)
        self.refresh_btn.pack(side="left")
        self.last_refresh_lbl = tk.Label(br, text="", bg=C["bg"],
                                          fg=C["dim"], font=("Helvetica",8))
        self.last_refresh_lbl.pack(side="left", padx=8)

        # Tab: 52W Range
        wt = tk.Frame(nb, bg=C["bg"]); nb.add(wt, text="  52W Range  ")
        self._section(wt, "52-Week High/Low Position")
        cols2 = ("Symbol","Price","52W Low","52W High","From Low","From High","Range","Status")
        self.w52_tree = self._tree(wt, cols2, heights=14,
            col_widths=[100,90,90,90,80,85,130,80])
        self.w52_tree.column("Symbol", anchor="w")
        self.w52_tree.column("Range",  anchor="w")
        self.w52_tree.tag_configure("danger", foreground=C["red"])
        self.w52_tree.tag_configure("warn",   foreground=C["amber"])
        self.w52_tree.tag_configure("safe",   foreground=C["green"])
        br2 = tk.Frame(wt, bg=C["bg"], padx=12); br2.pack(fill="x", pady=4)
        self._btn(br2,"↻  Analyse", self._refresh_52w, accent=True).pack(side="left")
        self._btn(br2,"📨 Send", self._trigger_52w).pack(side="left", padx=6)

        # Tab: Earnings
        et = tk.Frame(nb, bg=C["bg"]); nb.add(et, text="  Earnings  ")
        self._section(et, "Upcoming Results")
        cols3 = ("Symbol","Date","Days","Status")
        self.earn_tree = self._tree(et, cols3, heights=14,
            col_widths=[120,130,70,160])
        self.earn_tree.column("Symbol", anchor="w")
        self.earn_tree.tag_configure("urgent", foreground=C["red"])
        self.earn_tree.tag_configure("soon",   foreground=C["amber"])
        self.earn_tree.tag_configure("ok",     foreground=C["text"])
        br3 = tk.Frame(et, bg=C["bg"], padx=12); br3.pack(fill="x", pady=4)
        self._btn(br3,"↻  Fetch", self._refresh_earnings, accent=True).pack(side="left")
        self._btn(br3,"📨 Send",  self._trigger_earnings).pack(side="left", padx=6)

        # Tab: Corporate Actions
        ca = tk.Frame(nb, bg=C["bg"]); nb.add(ca, text="  Corp Actions  ")
        self._section(ca, "Dividends · Splits · Bonuses · Rights")
        cols4 = ("Symbol","Category","Action","Ex-Date","Days","Urgent")
        self.corp_tree = self._tree(ca, cols4, heights=14,
            col_widths=[100,90,280,100,60,70])
        self.corp_tree.column("Symbol", anchor="w")
        self.corp_tree.column("Action", anchor="w")
        self.corp_tree.tag_configure("urgent", foreground=C["red"])
        self.corp_tree.tag_configure("soon",   foreground=C["amber"])
        self.corp_tree.tag_configure("ok",     foreground=C["text"])
        br4 = tk.Frame(ca, bg=C["bg"], padx=12); br4.pack(fill="x", pady=4)
        self._btn(br4,"↻  Fetch", self._refresh_corporate, accent=True).pack(side="left")
        self._btn(br4,"📨 Send",  self._trigger_corporate).pack(side="left", padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # SIGNALS PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_signals(self, f):
        top = tk.Frame(f, bg=C["bg"], padx=12, pady=8); top.pack(fill="x")
        ctrl = tk.Frame(top, bg=C["bg"]); ctrl.pack(fill="x", pady=(0,8))
        tk.Label(ctrl, text="Timeframe:", bg=C["bg"], fg=C["muted"],
                 font=("Helvetica",9)).pack(side="left")
        self.sig_tf_var = tk.StringVar(value="TODAY")
        for tf in ("TODAY","1W","1M"):
            tk.Radiobutton(ctrl, text=tf, variable=self.sig_tf_var, value=tf,
                           bg=C["bg"], fg=C["muted"], selectcolor=C["bg3"],
                           activebackground=C["bg"],
                           font=("Helvetica",9,"bold"),
                           command=self._filter_signals).pack(side="left", padx=6)

        cols = ("Sev","Stock","Type","Timeframe","Signal")
        self.sig_tree = self._tree(f, cols, heights=18,
            col_widths=[70,90,130,80,500])
        self.sig_tree.column("Signal", anchor="w")
        for sev, col in [("CRITICAL",C["red"]),("HIGH",C["amber"]),
                          ("MEDIUM",C["teal"]),("LOW",C["muted"])]:
            self.sig_tree.tag_configure(sev, foreground=col)

        br = tk.Frame(f, bg=C["bg"], padx=12); br.pack(fill="x", pady=4)
        self.sig_refresh_btn = self._btn(br,"↻  Scan All Signals", self._refresh_signals, accent=True)
        self.sig_refresh_btn.pack(side="left")
        self.sig_send_btn = self._btn(br,"📨 Send Digest", self._send_signals)
        self.sig_send_btn.pack(side="left", padx=6)
        self.sig_status_lbl = tk.Label(br, text="", bg=C["bg"],
                                        fg=C["dim"], font=("Helvetica",8))
        self.sig_status_lbl.pack(side="left", padx=8)

    # ─────────────────────────────────────────────────────────────────────────
    # TECHNICALS PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_technicals(self, f):
        nb = self._sub_notebook(f)

        # Tab: TA Scanner
        ta = tk.Frame(nb, bg=C["bg"]); nb.add(ta, text="  TA Scanner  ")
        self._section(ta, "Technical Analysis — All Stocks")
        cols = ("Symbol","Price","Signal","RSI","RSI Status","MA50","Above MA","MACD","MA Cross","Volume","BB","Support","Resist")
        self.ta_tree = self._tree(ta, cols, heights=12,
            col_widths=[90,80,95,55,90,85,80,90,90,80,90,85,85])
        self.ta_tree.column("Symbol",  anchor="w")
        for sig,col in [("STRONG BUY",C["green"]),("BUY",C["teal"]),
                         ("NEUTRAL",C["muted"]),("SELL",C["amber"]),
                         ("STRONG SELL",C["red"])]:
            self.ta_tree.tag_configure(sig, foreground=col)

        br = tk.Frame(ta, bg=C["bg"], padx=12); br.pack(fill="x", pady=4)
        self.ta_refresh_btn = self._btn(br,"↻  Run TA Scan", self._refresh_ta, accent=True)
        self.ta_refresh_btn.pack(side="left")
        self.ta_send_btn = self._btn(br,"📨 Send Summary", self._send_ta_summary)
        self.ta_send_btn.pack(side="left", padx=6)
        self.ta_status_lbl = tk.Label(br, text="", bg=C["bg"],
                                       fg=C["dim"], font=("Helvetica",8))
        self.ta_status_lbl.pack(side="left", padx=8)

        # Deep dive
        self._section(ta, "Deep Dive — Single Stock")
        dd = tk.Frame(ta, bg=C["bg"], padx=12); dd.pack(fill="x")
        self.ta_sym_var = tk.StringVar()
        tk.Entry(dd, textvariable=self.ta_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat",
                 font=("Courier",10), width=18,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        self._btn(dd,"Analyse + Send", self._deep_dive_ta, accent=True).pack(side="left")

        # Tab: VWAP
        vt = tk.Frame(nb, bg=C["bg"]); nb.add(vt, text="  VWAP  ")
        self._section(vt, "Intraday VWAP — Institutional Price Benchmark")
        cols2 = ("Symbol","Price","VWAP","Diff%","Signal","Intra High","Intra Low")
        self.vwap_tree = self._tree(vt, cols2, heights=14,
            col_widths=[100,90,90,75,110,100,100])
        self.vwap_tree.column("Symbol", anchor="w")
        self.vwap_tree.tag_configure("BUY ZONE",  foreground=C["green"])
        self.vwap_tree.tag_configure("SELL ZONE", foreground=C["red"])
        self.vwap_tree.tag_configure("NEUTRAL",   foreground=C["muted"])
        br2 = tk.Frame(vt, bg=C["bg"], padx=12); br2.pack(fill="x", pady=4)
        self._btn(br2,"↻  Fetch VWAP", self._refresh_vwap, accent=True).pack(side="left")
        self._btn(br2,"📨 Send", self._send_vwap_report).pack(side="left", padx=6)

        # Tab: Breakout
        bt = tk.Frame(nb, bg=C["bg"]); nb.add(bt, text="  Breakout  ")

        left  = tk.Frame(bt, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,6))
        right = tk.Frame(bt, bg=C["bg"]); right.pack(side="left", fill="both", expand=True)

        self._section(left, "Breakouts — At 52W High")
        cols3 = ("Symbol","Price","52W High","Volume","Confirmed")
        self.bo_tree = self._tree(left, cols3, heights=7,
            col_widths=[100,90,90,80,100])
        self.bo_tree.column("Symbol", anchor="w")
        self.bo_tree.tag_configure("high",   foreground=C["green"])
        self.bo_tree.tag_configure("medium", foreground=C["amber"])

        self._section(left, "Accumulation — Quiet Buying")
        cols4 = ("Symbol","Price","Vol Ratio","Price Range")
        self.acc_tree = self._tree(left, cols4, heights=6,
            col_widths=[100,90,90,100])
        self.acc_tree.column("Symbol", anchor="w")

        self._section(right, "Relative Strength vs Nifty")
        cols5 = ("Symbol","Price","Stock Ret","Nifty Ret","RS Score","Status")
        self.rs_tree = self._tree(right, cols5, heights=10,
            col_widths=[100,85,80,80,80,90])
        self.rs_tree.column("Symbol", anchor="w")
        self.rs_tree.tag_configure("out", foreground=C["green"])
        self.rs_tree.tag_configure("und", foreground=C["red"])

        self._section(right, "Consolidation — Coiling")
        cols6 = ("Symbol","Price","Squeeze%","Meaning")
        self.con_tree = self._tree(right, cols6, heights=5,
            col_widths=[100,85,80,250])
        self.con_tree.column("Symbol",  anchor="w")
        self.con_tree.column("Meaning", anchor="w")

        br3 = tk.Frame(bt, bg=C["bg"], padx=12); br3.pack(fill="x", pady=4, side="bottom")
        self._btn(br3,"↻  Run Breakout Scan", self._refresh_breakout, accent=True).pack(side="left")
        self._btn(br3,"📨 Send Report", self._send_breakout_report).pack(side="left", padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # MARKET PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_market(self, f):
        nb = self._sub_notebook(f)

        # Tab: Indices & Macro
        it = tk.Frame(nb, bg=C["bg"]); nb.add(it, text="  Indices & Macro  ")
        left  = tk.Frame(it, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = tk.Frame(it, bg=C["bg"]); right.pack(side="left", fill="both", expand=True)

        self._section(left, "NSE Indices")
        self.idx_tree = self._tree(left, ("Index","Price","Change","Chg%"), heights=5,
                                    col_widths=[170,100,100,80])
        self.idx_tree.column("Index", anchor="w")
        self.idx_tree.tag_configure("up", foreground=C["green"])
        self.idx_tree.tag_configure("dn", foreground=C["red"])

        self._section(left, "Global Markets")
        self.global_tree = self._tree(left, ("Market","Price","Chg%"), heights=7,
                                       col_widths=[180,110,80])
        self.global_tree.column("Market", anchor="w")
        self.global_tree.tag_configure("up", foreground=C["green"])
        self.global_tree.tag_configure("dn", foreground=C["red"])

        br = tk.Frame(left, bg=C["bg"]); br.pack(fill="x", pady=4)
        self._btn(br,"↻  Refresh", self._refresh_indices, accent=True).pack(side="left")

        self._section(right, "Macro Indicators")
        self.macro_labels = {}
        mac_card, mac_inner = self._card(right)
        mac_card.pack(fill="x", pady=(0,8))
        for key,lbl in [("crude","Brent Crude"),("inr","INR/USD"),
                         ("fii_net","FII Net"),("dii_net","DII Net")]:
            row = tk.Frame(mac_inner, bg=C["bg2"]); row.pack(fill="x", pady=2)
            tk.Label(row, text=lbl+":", bg=C["bg2"], fg=C["muted"],
                     font=("Helvetica",9), width=14, anchor="w").pack(side="left")
            v = tk.Label(row, text="—", bg=C["bg2"], fg=C["text"],
                         font=("Helvetica",10,"bold"))
            v.pack(side="left")
            self.macro_labels[key] = v

        self._section(right, "FII/DII Flow")
        self.fii_labels = {}
        fii_card, fii_inner = self._card(right)
        fii_card.pack(fill="x", pady=(0,8))
        for key,lbl in [("fii_buy","FII Buy"),("fii_sell","FII Sell"),
                         ("dii_buy","DII Buy"),("dii_sell","DII Sell")]:
            row = tk.Frame(fii_inner, bg=C["bg2"]); row.pack(fill="x", pady=2)
            tk.Label(row, text=lbl+":", bg=C["bg2"], fg=C["muted"],
                     font=("Helvetica",9), width=12, anchor="w").pack(side="left")
            v = tk.Label(row, text="—", bg=C["bg2"], fg=C["text"],
                         font=("Helvetica",10,"bold"))
            v.pack(side="left")
            self.fii_labels[key] = v

        self._section(right, "Macro Events — Next 30 Days")
        self.macro_tree = self._tree(right, ("Event","Date","Days","Impact"), heights=7,
                                      col_widths=[210,90,50,80])
        self.macro_tree.column("Event", anchor="w")
        self.macro_tree.tag_configure("high",   foreground=C["red"])
        self.macro_tree.tag_configure("medium", foreground=C["amber"])

        br2 = tk.Frame(right, bg=C["bg"]); br2.pack(fill="x", pady=4)
        self._btn(br2,"📨 Send Macro", self._send_global_macro).pack(side="left")
        self._btn(br2,"📨 Send Events", self._trigger_macro).pack(side="left", padx=6)

        # Tab: Sentiment
        st = tk.Frame(nb, bg=C["bg"]); nb.add(st, text="  Sentiment  ")
        left2  = tk.Frame(st, bg=C["bg"]); left2.pack(side="left", fill="both", expand=True, padx=(0,8))
        right2 = tk.Frame(st, bg=C["bg"]); right2.pack(side="left", fill="both", expand=True)

        self._section(left2, "India VIX — Fear Index")
        vix_card, vix_inner = self._card(left2); vix_card.pack(fill="x", pady=(0,8))
        self.vix_val_lbl   = tk.Label(vix_inner, text="—", bg=C["bg2"], fg=C["text"],  font=("Helvetica",28,"bold")); self.vix_val_lbl.pack(anchor="w")
        self.vix_level_lbl = tk.Label(vix_inner, text="—", bg=C["bg2"], fg=C["muted"], font=("Helvetica",10,"bold")); self.vix_level_lbl.pack(anchor="w")
        self.vix_mean_lbl  = tk.Label(vix_inner, text="—", bg=C["bg2"], fg=C["muted"], font=("Helvetica",9), wraplength=280, justify="left"); self.vix_mean_lbl.pack(anchor="w")
        self.vix_act_lbl   = tk.Label(vix_inner, text="—", bg=C["bg2"], fg=C["amber"], font=("Helvetica",9,"bold"), wraplength=280, justify="left"); self.vix_act_lbl.pack(anchor="w")

        self._section(left2, "Put/Call Ratio")
        pcr_card, pcr_inner = self._card(left2); pcr_card.pack(fill="x", pady=(0,8))
        self.pcr_val_lbl   = tk.Label(pcr_inner, text="—", bg=C["bg2"], fg=C["text"],  font=("Helvetica",22,"bold")); self.pcr_val_lbl.pack(anchor="w")
        self.pcr_level_lbl = tk.Label(pcr_inner, text="—", bg=C["bg2"], fg=C["muted"], font=("Helvetica",10,"bold")); self.pcr_level_lbl.pack(anchor="w")
        self.pcr_mean_lbl  = tk.Label(pcr_inner, text="—", bg=C["bg2"], fg=C["muted"], font=("Helvetica",9), wraplength=280, justify="left"); self.pcr_mean_lbl.pack(anchor="w")

        self._section(left2, "Advance / Decline")
        ad_card, ad_inner = self._card(left2); ad_card.pack(fill="x", pady=(0,8))
        self.ad_val_lbl  = tk.Label(ad_inner, text="—", bg=C["bg2"], fg=C["text"],  font=("Helvetica",14,"bold")); self.ad_val_lbl.pack(anchor="w")
        self.ad_mean_lbl = tk.Label(ad_inner, text="—", bg=C["bg2"], fg=C["muted"], font=("Helvetica",9), wraplength=280, justify="left"); self.ad_mean_lbl.pack(anchor="w")

        br3 = tk.Frame(left2, bg=C["bg"]); br3.pack(fill="x", pady=4)
        self._btn(br3,"↻  Refresh", self._refresh_sentiment, accent=True).pack(side="left")
        self._btn(br3,"📨 Send Report", self._send_sentiment).pack(side="left", padx=6)

        self._section(right2, "Sector Rotation Today")
        self.sector_tree = self._tree(right2, ("Sector","Today%","This Week%","Flow"), heights=12,
                                       col_widths=[120,80,100,140])
        self.sector_tree.column("Sector", anchor="w")
        self.sector_tree.column("Flow",   anchor="w")
        self.sector_tree.tag_configure("up",   foreground=C["green"])
        self.sector_tree.tag_configure("dn",   foreground=C["red"])
        self.sector_tree.tag_configure("flat", foreground=C["muted"])

        # Tab: Options
        ot = tk.Frame(nb, bg=C["bg"]); nb.add(ot, text="  Options  ")
        self._section(ot, "Unusual Options Activity")
        cols_o = ("Symbol","Spot","PCR","Sentiment","Resistance","Support","IV","Unusual")
        self.opt_tree = self._tree(ot, cols_o, heights=10,
            col_widths=[80,85,55,90,90,85,65,110])
        self.opt_tree.column("Symbol", anchor="w")
        self.opt_tree.tag_configure("BULLISH", foreground=C["green"])
        self.opt_tree.tag_configure("BEARISH", foreground=C["red"])
        self.opt_tree.tag_configure("NEUTRAL", foreground=C["muted"])

        self._section(ot, "Promoter & Institutional Holdings")
        cols_p = ("Symbol","Promoter%","Pledge%","FII%","MF%","Risk")
        self.promo_tree = self._tree(ot, cols_p, heights=8,
            col_widths=[90,80,90,65,65,90])
        self.promo_tree.column("Symbol", anchor="w")
        self.promo_tree.tag_configure("high",   foreground=C["red"])
        self.promo_tree.tag_configure("medium", foreground=C["amber"])
        self.promo_tree.tag_configure("safe",   foreground=C["green"])

        br4 = tk.Frame(ot, bg=C["bg"]); br4.pack(fill="x", pady=4)
        self._btn(br4,"↻  Scan Options",   self._refresh_options,  accent=True).pack(side="left")
        self._btn(br4,"↻  Fetch Holdings", self._refresh_promoter).pack(side="left", padx=6)
        self._btn(br4,"📨 Send Options",   self._send_options).pack(side="left", padx=6)
        self._btn(br4,"📨 Send Holdings",  self._send_promoter).pack(side="left", padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # ALERTS PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_alerts(self, f):
        left  = tk.Frame(f, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = tk.Frame(f, bg=C["bg"], width=360); right.pack(side="left", fill="y")
        right.pack_propagate(False)

        # Alert list
        self._section(left, "Active Alert Rules")
        lf = tk.Frame(left, bg=C["bg"]); lf.pack(fill="both", expand=True)
        canvas = tk.Canvas(lf, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=canvas.yview)
        self.alert_inner = tk.Frame(canvas, bg=C["bg"])
        self.alert_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=self.alert_inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._populate_alert_rows()

        self._section(left, "Recent Fires")
        self.alert_log = scrolledtext.ScrolledText(
            left, height=5, bg=C["bg3"], fg=C["amber"],
            font=("Courier",8), relief="flat", state="disabled",
            highlightbackground=C["border"], highlightthickness=1)
        self.alert_log.pack(fill="x", pady=(0,8))

        # Add/edit form (right)
        self._section(right, "Add / Edit Alert")
        form_card, form_inner = self._card(right)
        form_card.pack(fill="x", pady=(0,8))

        self.alert_sym_var   = tk.StringVar(value="RELIANCE.NS")
        self.alert_level_var = tk.StringVar()
        self.alert_cool_var  = tk.StringVar(value="4")
        self.alert_cond_var  = tk.StringVar(value="below")
        self.alert_editing_idx = None

        self._entry_row(form_inner,"Symbol",   self.alert_sym_var,  bg=C["bg2"])
        self._entry_row(form_inner,"Level ₹",  self.alert_level_var,bg=C["bg2"])
        self._entry_row(form_inner,"Cooldown h",self.alert_cool_var, bg=C["bg2"])

        cr = tk.Frame(form_inner, bg=C["bg2"]); cr.pack(fill="x", pady=2)
        tk.Label(cr, text="Condition", bg=C["bg2"], fg=C["muted"],
                 font=("Helvetica",9), width=14, anchor="w").pack(side="left")
        ttk.Combobox(cr, textvariable=self.alert_cond_var,
                     values=["below","above"], state="readonly",
                     width=10, font=("Courier",10)).pack(side="left")

        br = tk.Frame(form_inner, bg=C["bg2"]); br.pack(fill="x", pady=(10,0))
        self.alert_save_btn = self._btn(br,"＋  Add Alert", self._save_alert, accent=True)
        self.alert_save_btn.pack(side="left")
        self._btn(br,"✕ Clear", self._clear_alert_form).pack(side="left", padx=6)
        self.form_status_lbl = tk.Label(form_inner, text="", bg=C["bg2"],
                                         fg=C["green"], font=("Helvetica",8))
        self.form_status_lbl.pack(anchor="w", pady=(4,0))

    # ─────────────────────────────────────────────────────────────────────────
    # RISK PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_risk(self, f):
        nb = self._sub_notebook(f)

        # Tab: Portfolio Risk
        pr = tk.Frame(nb, bg=C["bg"]); nb.add(pr, text="  Portfolio Risk  ")
        left  = tk.Frame(pr, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = tk.Frame(pr, bg=C["bg"]); right.pack(side="left", fill="both", expand=True)

        self._section(left, "Risk Analysis")
        self.risk_summary_text = self._scrolltext(left, height=10)
        br = tk.Frame(left, bg=C["bg"]); br.pack(fill="x", pady=4)
        self._btn(br,"↻  Analyse Risk", self._refresh_risk, accent=True).pack(side="left")
        self._btn(br,"📨 Send Report",  self._send_risk_report).pack(side="left", padx=6)

        self._section(left, "Trailing Stop Tracker")
        trail_form, tf_inner = self._card(left); trail_form.pack(fill="x", pady=(0,6))
        self.trail_sym_var   = tk.StringVar()
        self.trail_entry_var = tk.StringVar()
        self._entry_row(tf_inner,"Symbol", self.trail_sym_var,  bg=C["bg2"])
        self._entry_row(tf_inner,"Entry ₹",self.trail_entry_var,bg=C["bg2"])
        self._btn(tf_inner,"＋  Track Stop", self._add_trailing_stop, accent=True).pack(anchor="w", pady=(8,0))

        cols = ("Symbol","Entry","High","Stop","Trail%")
        self.trail_tree = self._tree(left, cols, heights=5,
            col_widths=[90,85,85,85,70])
        self.trail_tree.column("Symbol", anchor="w")

        # Pre-trade checklist (right)
        self._section(right, "Pre-Trade Checklist")
        ptc_card, ptc_inner = self._card(right); ptc_card.pack(fill="x", pady=(0,8))
        self.ptc_sym_var    = tk.StringVar()
        self.ptc_entry_var  = tk.StringVar()
        self.ptc_target_var = tk.StringVar()
        self._entry_row(ptc_inner,"Symbol",   self.ptc_sym_var,   bg=C["bg2"])
        self._entry_row(ptc_inner,"Entry ₹",  self.ptc_entry_var, bg=C["bg2"])
        self._entry_row(ptc_inner,"Target ₹", self.ptc_target_var,bg=C["bg2"])
        self._btn(ptc_inner,"🔍  Run Checklist", self._run_checklist, accent=True).pack(anchor="w", pady=(10,0))

        self.ptc_result_text = self._scrolltext(right, height=18)

        # Stop-loss calc
        self._section(right, "Quick Stop-Loss Calculator")
        sl_row = tk.Frame(right, bg=C["bg"]); sl_row.pack(fill="x")
        self.sl_sym_var   = tk.StringVar()
        self.sl_entry_var = tk.StringVar()
        for var, ph, w in [(self.sl_sym_var,"Symbol",14),(self.sl_entry_var,"Entry ₹",10)]:
            tk.Entry(sl_row, textvariable=var, bg=C["bg3"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     font=("Courier",10), width=w,
                     highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,6))
        self._btn(sl_row,"Calc", self._calc_stop_loss).pack(side="left")
        self.sl_result_lbl = tk.Label(right, text="", bg=C["bg"],
                                       fg=C["teal"], font=("Courier",9,"bold"))
        self.sl_result_lbl.pack(anchor="w", pady=(4,0))

    # ─────────────────────────────────────────────────────────────────────────
    # PAPER TRADING PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_paper(self, f):
        left  = tk.Frame(f, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = tk.Frame(f, bg=C["bg"], width=320); right.pack(side="left", fill="y")
        right.pack_propagate(False)

        self._section(left, "Virtual Portfolio — ₹10L Starting Capital")
        self.pt_summary_text = self._scrolltext(left, height=5)

        self._section(left, "Open Positions")
        cols = ("Symbol","Qty","Avg ₹","CMP ₹","P&L","P&L%")
        self.pt_pos_tree = self._tree(left, cols, heights=7,
            col_widths=[100,65,90,90,95,70])
        self.pt_pos_tree.column("Symbol", anchor="w")
        self.pt_pos_tree.tag_configure("up", foreground=C["green"])
        self.pt_pos_tree.tag_configure("dn", foreground=C["red"])

        self._section(left, "Trade History")
        cols2 = ("ID","Symbol","Action","Qty","Price","Value","P&L","Date")
        self.pt_hist_tree = self._tree(left, cols2, heights=5,
            col_widths=[40,80,60,50,80,90,80,90])
        self.pt_hist_tree.column("Symbol", anchor="w")

        # Order form (right)
        self._section(right, "Place Paper Trade")
        form_card, form_inner = self._card(right); form_card.pack(fill="x", pady=(0,8))
        self.pt_sym_var   = tk.StringVar()
        self.pt_qty_var   = tk.StringVar()
        self.pt_price_var = tk.StringVar()
        self.pt_reason_var= tk.StringVar()
        self.pt_side_var  = tk.StringVar(value="BUY")
        self._entry_row(form_inner,"Symbol", self.pt_sym_var,  bg=C["bg2"])
        self._entry_row(form_inner,"Qty",    self.pt_qty_var,  bg=C["bg2"], width=8)
        self._entry_row(form_inner,"Price ₹",self.pt_price_var,bg=C["bg2"])
        sr = tk.Frame(form_inner, bg=C["bg2"]); sr.pack(fill="x", pady=2)
        tk.Label(sr, text="Side", bg=C["bg2"], fg=C["muted"],
                 font=("Helvetica",9), width=14, anchor="w").pack(side="left")
        ttk.Combobox(sr, textvariable=self.pt_side_var,
                     values=["BUY","SELL"], state="readonly",
                     width=8, font=("Courier",10)).pack(side="left")
        self._entry_row(form_inner,"Reason", self.pt_reason_var,bg=C["bg2"], width=18)

        self._btn(form_inner,"▶  Execute Paper Trade", self._paper_execute, accent=True).pack(fill="x", pady=(10,0))
        self.pt_status_lbl = tk.Label(right, text="", bg=C["bg"],
                                       fg=C["green"], font=("Helvetica",9,"bold"))
        self.pt_status_lbl.pack(anchor="w", pady=(4,0))

        br = tk.Frame(right, bg=C["bg"]); br.pack(fill="x", pady=(8,0))
        self._btn(br,"↻  Refresh",    self._refresh_paper_portfolio, accent=True).pack(fill="x", pady=2)
        self._btn(br,"📨 Send Report", self._send_paper_report).pack(fill="x", pady=2)
        self._btn(br,"🔄 Reset to ₹10L", self._reset_paper_portfolio).pack(fill="x", pady=2)

        self._refresh_paper_portfolio()

    # ─────────────────────────────────────────────────────────────────────────
    # FUNDAMENTALS PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_fundamentals(self, f):
        nb = self._sub_notebook(f)

        # Tab: Screener
        st = tk.Frame(nb, bg=C["bg"]); nb.add(st, text="  Screener  ")
        self._section(st, "Watchlist Fundamentals")
        cols = ("Symbol","Price","P/E","Sector P/E","ROE%","Debt%","Rev Growth","Margin%","Signal","Score")
        self.fund_tree = self._tree(st, cols, heights=10,
            col_widths=[90,80,60,80,60,60,85,70,95,55])
        self.fund_tree.column("Symbol", anchor="w")
        for sig,col in [("STRONG BUY",C["green"]),("BUY",C["teal"]),
                         ("HOLD",C["muted"]),("SELL",C["amber"]),
                         ("STRONG SELL",C["red"])]:
            self.fund_tree.tag_configure(sig, foreground=col)

        br = tk.Frame(st, bg=C["bg"]); br.pack(fill="x", pady=4)
        self.fund_refresh_btn = self._btn(br,"↻  Screen All", self._refresh_fundamentals, accent=True)
        self.fund_refresh_btn.pack(side="left")
        self._btn(br,"📨 Send", self._send_fundamentals).pack(side="left", padx=6)
        self.fund_status_lbl = tk.Label(br, text="", bg=C["bg"],
                                         fg=C["dim"], font=("Helvetica",8))
        self.fund_status_lbl.pack(side="left", padx=8)

        # Deep dive
        self._section(st, "Single Stock Deep Dive")
        dd = tk.Frame(st, bg=C["bg"]); dd.pack(fill="x")
        self.fund_sym_var = tk.StringVar()
        tk.Entry(dd, textvariable=self.fund_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat",
                 font=("Courier",10), width=18,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        self._btn(dd,"Analyse + Send", self._fund_deep_dive, accent=True).pack(side="left")
        self.fund_detail_text = self._scrolltext(st, height=7)

        # Tab: Screener.in
        sit = tk.Frame(nb, bg=C["bg"]); nb.add(sit, text="  Screener.in  ")
        self._section(sit, "Deep Fundamentals from Screener.in")
        cols2 = ("Symbol","ROCE%","ROE%","D/E","F-Score","Profit Trend","10Y CAGR")
        self.scr_tree = self._tree(sit, cols2, heights=10,
            col_widths=[90,70,65,60,90,110,90])
        self.scr_tree.column("Symbol", anchor="w")
        br2 = tk.Frame(sit, bg=C["bg"]); br2.pack(fill="x", pady=4)
        self.scr_btn = self._btn(br2,"↻  Fetch Screener Data", self._refresh_screener, accent=True)
        self.scr_btn.pack(side="left")
        self._btn(br2,"📨 Send", self._send_screener_report).pack(side="left", padx=6)

        # Tab: Peer Compare
        pct = tk.Frame(nb, bg=C["bg"]); nb.add(pct, text="  Peer Compare  ")
        self._section(pct, "Compare vs Sector Peers")
        pr = tk.Frame(pct, bg=C["bg"]); pr.pack(fill="x", pady=(0,8))
        self.pc_sym_var = tk.StringVar()
        tk.Entry(pr, textvariable=self.pc_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat",
                 font=("Courier",10), width=18,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        self._btn(pr,"Compare + Send", self._run_peer_compare, accent=True).pack(side="left")
        cols3 = ("Stock","P/E","ROE%","Rev Grw","Margin","P/E Rank","ROE Rank")
        self.pc_tree = self._tree(pct, cols3, heights=12,
            col_widths=[110,75,70,80,75,85,85])
        self.pc_tree.column("Stock", anchor="w")
        self.pc_tree.tag_configure("target", foreground=C["amber"])

        # Tab: Earnings History
        eht = tk.Frame(nb, bg=C["bg"]); nb.add(eht, text="  Earnings History  ")
        self._section(eht, "Beat / Miss History — Last 4 Quarters")
        cols4 = ("Symbol","Beats","Misses","Avg Surprise","Quality","Streak")
        self.eh_tree = self._tree(eht, cols4, heights=12,
            col_widths=[100,70,70,110,100,110])
        self.eh_tree.column("Symbol", anchor="w")
        self.eh_tree.tag_configure("EXCELLENT", foreground=C["green"])
        self.eh_tree.tag_configure("GOOD",      foreground=C["teal"])
        self.eh_tree.tag_configure("POOR",      foreground=C["red"])
        br3 = tk.Frame(eht, bg=C["bg"]); br3.pack(fill="x", pady=4)
        self._btn(br3,"↻  Fetch", self._refresh_earnings_history, accent=True).pack(side="left")
        self._btn(br3,"📨 Send",  self._send_earnings_history).pack(side="left", padx=6)

        # Tab: Global Macro
        gmt = tk.Frame(nb, bg=C["bg"]); nb.add(gmt, text="  Global Macro  ")
        self._section(gmt, "Global Macro Indicators")
        self.macro_detail_text = self._scrolltext(gmt, height=12)
        br4 = tk.Frame(gmt, bg=C["bg"]); br4.pack(fill="x", pady=4)
        self._btn(br4,"↻  Fetch Macro", self._refresh_global_macro, accent=True).pack(side="left")
        self._btn(br4,"📨 Send", self._send_global_macro).pack(side="left", padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # JOURNAL PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_journal(self, f):
        left  = tk.Frame(f, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = tk.Frame(f, bg=C["bg"], width=340); right.pack(side="left", fill="y")
        right.pack_propagate(False)

        self._section(left, "Log a Trade")
        form_card, form_inner = self._card(left); form_card.pack(fill="x", pady=(0,8))
        self.j_sym_var    = tk.StringVar()
        self.j_entry_var  = tk.StringVar()
        self.j_qty_var    = tk.StringVar()
        self.j_stop_var   = tk.StringVar()
        self.j_target_var = tk.StringVar()
        self.j_reason_var = tk.StringVar()
        self.j_side_var   = tk.StringVar(value="BUY")

        r1 = tk.Frame(form_inner, bg=C["bg2"]); r1.pack(fill="x")
        for lbl,var,w in [("Symbol",self.j_sym_var,12),("Entry ₹",self.j_entry_var,10),("Qty",self.j_qty_var,6)]:
            tk.Label(r1,text=lbl,bg=C["bg2"],fg=C["muted"],font=("Helvetica",9),width=9,anchor="w").pack(side="left")
            tk.Entry(r1,textvariable=var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                     relief="flat",font=("Courier",10),width=w,
                     highlightbackground=C["border"],highlightthickness=1).pack(side="left",padx=(0,8))

        r2 = tk.Frame(form_inner, bg=C["bg2"]); r2.pack(fill="x", pady=4)
        for lbl,var,w in [("Stop ₹",self.j_stop_var,10),("Target ₹",self.j_target_var,10)]:
            tk.Label(r2,text=lbl,bg=C["bg2"],fg=C["muted"],font=("Helvetica",9),width=9,anchor="w").pack(side="left")
            tk.Entry(r2,textvariable=var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                     relief="flat",font=("Courier",10),width=w,
                     highlightbackground=C["border"],highlightthickness=1).pack(side="left",padx=(0,8))
        tk.Label(r2,text="Side",bg=C["bg2"],fg=C["muted"],font=("Helvetica",9),width=6,anchor="w").pack(side="left")
        ttk.Combobox(r2,textvariable=self.j_side_var,values=["BUY","SELL"],
                     state="readonly",width=6,font=("Courier",10)).pack(side="left")

        r3 = tk.Frame(form_inner, bg=C["bg2"]); r3.pack(fill="x", pady=2)
        tk.Label(r3,text="Reason",bg=C["bg2"],fg=C["muted"],font=("Helvetica",9),width=9,anchor="w").pack(side="left")
        tk.Entry(r3,textvariable=self.j_reason_var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                 relief="flat",font=("Courier",10),width=35,
                 highlightbackground=C["border"],highlightthickness=1).pack(side="left",fill="x",expand=True)

        br = tk.Frame(form_inner, bg=C["bg2"]); br.pack(fill="x", pady=(8,0))
        self._btn(br,"＋  Log Entry", self._log_trade_entry, accent=True).pack(side="left")
        self.j_status_lbl = tk.Label(br, text="", bg=C["bg2"],
                                      fg=C["green"], font=("Helvetica",8))
        self.j_status_lbl.pack(side="left", padx=8)

        self._section(left, "Open Trades — Double-click to Close")
        cols = ("ID","Symbol","Side","Entry ₹","Qty","Stop ₹","Target ₹","Date","Reason")
        self.open_tree = self._tree(left, cols, heights=6,
            col_widths=[40,80,50,80,50,75,75,90,180])
        self.open_tree.column("Symbol", anchor="w")
        self.open_tree.column("Reason", anchor="w")
        self.open_tree.bind("<Double-1>", self._open_close_dialog)

        self._section(left, "Close a Trade")
        close_card, close_inner = self._card(left); close_card.pack(fill="x")
        cr = tk.Frame(close_inner, bg=C["bg2"]); cr.pack(fill="x")
        self.j_close_id_var    = tk.StringVar()
        self.j_exit_var        = tk.StringVar()
        self.j_exit_reason_var = tk.StringVar(value="Target hit")
        for lbl,var,w in [("Trade ID",self.j_close_id_var,6),("Exit ₹",self.j_exit_var,10)]:
            tk.Label(cr,text=lbl,bg=C["bg2"],fg=C["muted"],font=("Helvetica",9),width=10,anchor="w").pack(side="left")
            tk.Entry(cr,textvariable=var,bg=C["bg3"],fg=C["text"],insertbackground=C["text"],
                     relief="flat",font=("Courier",10),width=w,
                     highlightbackground=C["border"],highlightthickness=1).pack(side="left",padx=(0,8))
        cr2 = tk.Frame(close_inner, bg=C["bg2"]); cr2.pack(fill="x",pady=4)
        tk.Label(cr2,text="Exit Reason",bg=C["bg2"],fg=C["muted"],font=("Helvetica",9),width=10,anchor="w").pack(side="left")
        ttk.Combobox(cr2,textvariable=self.j_exit_reason_var,
                     values=["Target hit","Stop-loss hit","Trailing stop","Manual exit","News"],
                     state="readonly",width=18,font=("Courier",10)).pack(side="left",padx=(0,8))
        self._btn(close_inner,"✓  Close Trade", self._close_trade_entry, accent=True).pack(anchor="w",pady=(6,0))

        # Stats (right)
        self._section(right, "Performance Stats")
        self.stats_text = self._scrolltext(right, height=14)
        br2 = tk.Frame(right, bg=C["bg"]); br2.pack(fill="x")
        self._btn(br2,"↻  Refresh Stats", self._refresh_journal_stats, accent=True).pack(fill="x",pady=2)
        self._btn(br2,"📨 Send Stats",    self._send_journal_stats).pack(fill="x",pady=2)

        self._section(right, "Recent Closed Trades")
        cols2 = ("ID","Symbol","P&L","P&L%","Status")
        self.closed_tree = self._tree(right, cols2, heights=8,
            col_widths=[40,80,90,70,90])
        self.closed_tree.column("Symbol", anchor="w")
        self.closed_tree.tag_configure("WIN",       foreground=C["green"])
        self.closed_tree.tag_configure("LOSS",      foreground=C["red"])
        self.closed_tree.tag_configure("BREAK_EVEN",foreground=C["muted"])

        self._refresh_journal_ui()

    # ─────────────────────────────────────────────────────────────────────────
    # TAX & REBALANCE PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_taxbal(self, f):
        nb = self._sub_notebook(f)

        # Tab: Tax
        tt = tk.Frame(nb, bg=C["bg"]); nb.add(tt, text="  Tax P&L  ")
        self._section(tt, "STCG vs LTCG — Hold Advice")
        cols = ("Symbol","P&L","Held Days","Tax Type","Tax Due","Save if Wait","Advice")
        self.tax_tree = self._tree(tt, cols, heights=10,
            col_widths=[90,90,80,80,80,100,260])
        self.tax_tree.column("Symbol", anchor="w")
        self.tax_tree.column("Advice", anchor="w")
        self.tax_tree.tag_configure("ltcg", foreground=C["green"])
        self.tax_tree.tag_configure("stcg", foreground=C["amber"])
        self.tax_summary_lbl = tk.Label(tt, text="", bg=C["bg"],
                                         fg=C["text"], font=("Helvetica",9))
        self.tax_summary_lbl.pack(anchor="w", pady=4)
        br = tk.Frame(tt, bg=C["bg"]); br.pack(fill="x", pady=4)
        self.tax_btn = self._btn(br,"↻  Calculate Tax", self._refresh_tax, accent=True)
        self.tax_btn.pack(side="left")
        self._btn(br,"📨 Send Report", self._send_tax_report).pack(side="left", padx=6)

        # Tab: Rebalance
        rt = tk.Frame(nb, bg=C["bg"]); nb.add(rt, text="  Rebalance  ")
        self.reb_summary_lbl = tk.Label(rt, text="", bg=C["bg"],
                                         fg=C["text"], font=("Helvetica",11,"bold"),
                                         pady=6, padx=12)
        self.reb_summary_lbl.pack(anchor="w")
        cols2 = ("Symbol","Allocation%","Status")
        self.reb_tree = self._tree(rt, cols2, heights=10,
            col_widths=[130,110,120])
        self.reb_tree.column("Symbol", anchor="w")
        self.reb_tree.tag_configure("over", foreground=C["red"])
        self.reb_tree.tag_configure("ok",   foreground=C["green"])
        self.reb_tree.tag_configure("tiny", foreground=C["muted"])
        self._section(rt, "Suggested Actions")
        self.reb_actions_text = self._scrolltext(rt, height=6, fg=C["amber"])
        br2 = tk.Frame(rt, bg=C["bg"]); br2.pack(fill="x", pady=4)
        self._btn(br2,"↻  Analyse", self._refresh_rebalance, accent=True).pack(side="left")
        self._btn(br2,"📨 Send",    self._send_rebalance_report).pack(side="left", padx=6)

        # Tab: Golden Rules
        grt = tk.Frame(nb, bg=C["bg"]); nb.add(grt, text="  Golden Rules  ")
        self._section(grt, "Daily Trading Rules Check")
        self.rules_text = self._scrolltext(grt, height=16)
        br3 = tk.Frame(grt, bg=C["bg"]); br3.pack(fill="x", pady=4)
        self._btn(br3,"↻  Check Rules Now", self._refresh_golden_rules, accent=True).pack(side="left")
        self._btn(br3,"📨 Send",            self._send_golden_rules).pack(side="left", padx=6)

    # ─────────────────────────────────────────────────────────────────────────
    # HOLDINGS PANEL
    # ─────────────────────────────────────────────────────────────────────────

    def _build_panel_holdings(self, f):
        left  = tk.Frame(f, bg=C["bg"]); left.pack(side="left", fill="both", expand=True, padx=(0,8))
        right = tk.Frame(f, bg=C["bg"]); right.pack(side="left", fill="both", expand=True)

        self._section(left, "Add / Edit Holding")
        form_card, form_inner = self._card(left); form_card.pack(fill="x", pady=(0,8))
        self.h_sym_var   = tk.StringVar()
        self.h_qty_var   = tk.StringVar()
        self.h_avg_var   = tk.StringVar()
        self._entry_row(form_inner,"Symbol",    self.h_sym_var, bg=C["bg2"])
        self._entry_row(form_inner,"Qty",       self.h_qty_var, bg=C["bg2"], width=8)
        self._entry_row(form_inner,"Avg Price ₹",self.h_avg_var, bg=C["bg2"])
        br = tk.Frame(form_inner, bg=C["bg2"]); br.pack(fill="x", pady=(10,0))
        self.h_editing_idx = None
        self.h_save_btn = self._btn(br,"＋  Add Holding", self._save_holding, accent=True)
        self.h_save_btn.pack(side="left")
        self._btn(br,"✕ Clear", self._clear_holding_form).pack(side="left", padx=6)
        self.h_status_lbl = tk.Label(form_inner, text="", bg=C["bg2"],
                                      fg=C["green"], font=("Helvetica",8))
        self.h_status_lbl.pack(anchor="w", pady=(4,0))

        self._section(left, "Current Holdings — Double-click to Edit")
        cols = ("Symbol","Qty","Avg Price")
        self.hold_tree = self._tree(left, cols, heights=14,
            col_widths=[140,100,130])
        self.hold_tree.column("Symbol", anchor="w")
        self._populate_hold_tree()

        self._section(right, "Watchlist")
        wr = tk.Frame(right, bg=C["bg"]); wr.pack(fill="x", pady=(0,6))
        self.w_sym_var = tk.StringVar()
        tk.Entry(wr, textvariable=self.w_sym_var, bg=C["bg3"], fg=C["text"],
                 insertbackground=C["text"], relief="flat",
                 font=("Courier",10), width=20,
                 highlightbackground=C["border"], highlightthickness=1).pack(side="left", padx=(0,8))
        self._btn(wr,"＋ Add", self._add_watchlist, accent=True).pack(side="left")
        self._btn(wr,"✕ Remove", self._remove_watchlist).pack(side="left", padx=6)

        cols2 = ("Symbol",)
        self.watch_tree = self._tree(right, cols2, heights=16, col_widths=[240])
        self.watch_tree.column("Symbol", anchor="w")
        self._populate_watch_tree()

    # ─────────────────────────────────────────────────────────────────────────
    # Sub-notebook helper
    # ─────────────────────────────────────────────────────────────────────────

    def _sub_notebook(self, parent) -> ttk.Notebook:
        style = ttk.Style()
        style.configure("Sub.TNotebook", background=C["bg"], borderwidth=0, tabmargins=0)
        style.configure("Sub.TNotebook.Tab", background=C["bg3"], foreground=C["muted"],
                         font=("Helvetica",9,"bold"), padding=[12,5], borderwidth=0)
        style.map("Sub.TNotebook.Tab",
                  background=[("selected",C["bg4"])],
                  foreground=[("selected",C["text"])])
        nb = ttk.Notebook(parent, style="Sub.TNotebook")
        nb.pack(fill="both", expand=True, padx=12, pady=8)
        return nb

    # ─────────────────────────────────────────────────────────────────────────
    # SHARED WIDGET FACTORIES (needed by old backend methods)
    # ─────────────────────────────────────────────────────────────────────────

    def _make_tree(self, parent, cols, heights=8) -> ttk.Treeview:
        """Compatibility shim — new code uses self._tree()."""
        t = self._tree(parent, cols, heights)
        return t

    def _metric_card(self, parent, label, value):
        """Compatibility shim — new code uses self._stat_box()."""
        return self._stat_box(parent, label, value)


    # ── Technicals methods ────────────────────────────────────────────────────

    def _refresh_ta(self):
        self.ta_refresh_btn.set_busy(True)
        self.ta_status_lbl.config(text="Scanning…", fg=C["muted"])
        self._log_gui("Running TA scan…")
        threading.Thread(target=self._fetch_ta, daemon=True).start()

    def _fetch_ta(self):
        try:
            from sources.technicals import analyze_watchlist
            log_queue.put(("ta", analyze_watchlist(config.WATCHLIST)))
        except Exception as e:
            log.error(f"TA scan: {e}"); log_queue.put(("ta", []))

    def _update_ta_ui(self, results: list):
        self.ta_cache = results
        for i in self.ta_tree.get_children(): self.ta_tree.delete(i)
        sig_map = {"STRONG BUY":"🚀 STRONG BUY","BUY":"📈 BUY","NEUTRAL":"➡️ NEUTRAL",
                   "SELL":"📉 SELL","STRONG SELL":"🔻 STRONG SELL"}
        for r in results:
            sym  = r["symbol"].replace(".NS","")
            sig  = r.get("ta_signal","NEUTRAL")
            rsi  = r.get("rsi")
            rsi_s= f"{rsi:.1f}" if rsi else "—"
            ma50 = r.get("ma50")
            ma50_s= f"₹{ma50:,.2f}" if ma50 else "—"
            abv  = "✅ Yes" if r.get("above_ma50") else "❌ No"
            mc   = r.get("macd_cross","—"); mac = r.get("ma_cross","—")
            vol  = r.get("volume_signal","—"); bb = r.get("bb_signal","—")
            sup  = f"₹{r['support']:,.2f}"    if r.get("support")    else "—"
            res  = f"₹{r['resistance']:,.2f}" if r.get("resistance") else "—"
            self.ta_tree.insert("","end", tags=(sig,), values=(
                sym, f"₹{r['price']:,.2f}", sig_map.get(sig,sig),
                rsi_s, r.get("rsi_signal","—"), ma50_s, abv, mc, mac, vol, bb, sup, res))
        self.ta_refresh_btn.set_busy(False)
        self.ta_status_lbl.config(text=f"{len(results)} stocks scanned.", fg=C["green"])
        self._log_gui(f"TA scan done — {len(results)} stocks.")

    def _send_ta_summary(self):
        threading.Thread(target=self._do_send_ta, daemon=True).start()

    def _do_send_ta(self):
        try:
            from sources.technicals import analyze_watchlist
            from formatter import format_ta_watchlist_summary
            results = self.ta_cache or analyze_watchlist(config.WATCHLIST)
            ok = sender.send_long(format_ta_watchlist_summary(results))
            log_queue.put(("log", f"TA summary {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"TA send: {e}")

    def _deep_dive_ta(self):
        sym = self.ta_sym_var.get().strip().upper()
        if not sym: return
        if not sym.endswith(".NS"): sym += ".NS"
        self._log_gui(f"Deep dive TA: {sym}…")
        def _run():
            try:
                from sources.technicals import analyze
                from formatter import format_ta_snapshot
                r = analyze(sym)
                if r:
                    sender.send_long(format_ta_snapshot(r))
                    log_queue.put(("log", f"TA snapshot for {sym} sent ✅"))
            except Exception as e:
                log.error(f"Deep dive TA: {e}")
        threading.Thread(target=_run, daemon=True).start()

    # ── Risk methods ──────────────────────────────────────────────────────────

    def _refresh_risk(self):
        self._log_gui("Analysing portfolio risk…")
        threading.Thread(target=self._fetch_risk, daemon=True).start()

    def _fetch_risk(self):
        try:
            from data_fetcher import get_portfolio_pnl
            pnl  = get_portfolio_pnl(config.PORTFOLIO)
            from risk import portfolio_risk_analysis
            risk = portfolio_risk_analysis(config.PORTFOLIO, pnl)
            log_queue.put(("risk", risk))
        except Exception as e:
            log.error(f"Risk: {e}"); log_queue.put(("risk",{}))

    def _update_risk_ui(self, risk: dict):
        self.risk_summary_text.config(state="normal")
        self.risk_summary_text.delete("1.0","end")
        if not risk:
            self.risk_summary_text.insert("end","No data."); self.risk_summary_text.config(state="disabled"); return
        total = risk.get("total_value",0); top5 = risk.get("top5_conc_pct",0)
        divs  = "✅ Diversified" if risk.get("diversified") else "⚠️ Concentrated"
        lines = [
            f"Portfolio: ₹{total:,.0f}",
            f"Status: {divs}",
            f"Top-5 Concentration: {top5:.1f}%",
            f"IT Exposure: {risk.get('it_exposure_pct',0):.1f}%  |  Banking: {risk.get('bank_exposure_pct',0):.1f}%",
            "",
        ]
        warns = risk.get("warnings",[])
        if warns:
            lines.append("WARNINGS:")
            lines += [f"  {w}" for w in warns]; lines.append("")
        lines.append("POSITIONS:")
        for p in sorted(risk.get("positions",[]), key=lambda x: x["pct"], reverse=True):
            sym  = p["symbol"].replace(".NS","")
            flag = "⚠ " if p["overweight"] else "  "
            lines.append(f"{flag}{sym:<14} {p['pct']:>5.1f}%   ₹{p['value']:>12,.0f}")
        self.risk_summary_text.insert("end","\n".join(lines))
        self.risk_summary_text.config(state="disabled")
        self._log_gui("Portfolio risk done.")

    def _send_risk_report(self):
        threading.Thread(target=self._do_send_risk, daemon=True).start()

    def _do_send_risk(self):
        try:
            from data_fetcher import get_portfolio_pnl
            from risk import portfolio_risk_analysis
            from formatter import format_risk_summary
            pnl  = get_portfolio_pnl(config.PORTFOLIO)
            risk = portfolio_risk_analysis(config.PORTFOLIO, pnl)
            ok   = sender.send_long(format_risk_summary(risk))
            log_queue.put(("log", f"Risk report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Risk send: {e}")

    def _run_checklist(self):
        sym     = self.ptc_sym_var.get().strip().upper()
        entry_s = self.ptc_entry_var.get().strip()
        if not sym or not entry_s: return
        if not sym.endswith(".NS"): sym += ".NS"
        try: entry = float(entry_s.replace(",",""))
        except ValueError: return
        self._log_gui(f"Pre-trade checklist: {sym}…")
        def _run():
            try:
                from sources.technicals import analyze as ta_analyze
                from sources.nse import get_fii_dii_trend as _fii
                from data_fetcher import get_earnings_calendar, get_portfolio_pnl
                from risk import pre_trade_checklist
                from formatter import format_pre_trade_checklist
                ta_r     = ta_analyze(sym) or {}
                earn     = get_earnings_calendar([sym])
                ed       = earn[0]["days_out"] if earn else 999
                pnl      = get_portfolio_pnl(config.PORTFOLIO)
                port_val = sum(r.get("market_value",0) for r in pnl)
                result   = pre_trade_checklist(sym, entry, port_val, config.PORTFOLIO, ta_r, _fii(), ed)
                log_queue.put(("checklist", result))
                sender.send_long(format_pre_trade_checklist(result))
            except Exception as e:
                log.error(f"Checklist: {e}"); log_queue.put(("checklist", None))
        threading.Thread(target=_run, daemon=True).start()

    def _update_checklist_ui(self, result):
        self.ptc_result_text.config(state="normal")
        self.ptc_result_text.delete("1.0","end")
        if not result:
            self.ptc_result_text.insert("end","Error running checklist.")
            self.ptc_result_text.config(state="disabled"); return
        verdict = result["verdict"]; passed = result["passed"]; total = result["total"]
        stop = result.get("stop_loss",0); pos = result.get("position",{})
        lines = [
            f"VERDICT: {verdict}  ({passed}/{total} passed)",
            f"Entry: ₹{result['entry']:,.2f}  |  Stop: ₹{stop:,.2f}",
        ]
        if pos:
            lines.append(f"Qty: {pos.get('qty',0)} shares  (₹{pos.get('position_value',0):,.0f}  {pos.get('position_pct',0):.1f}%)")
        lines.append("─"*40)
        for c in result.get("checks",[]):
            icon = "✅" if c["pass"] else "❌"
            lines.append(f"{icon} {c['name']}")
            lines.append(f"   {c['detail']}")
        col_map = {"STRONG BUY":C["green"],"BUY":C["teal"],"WATCH":C["amber"],"AVOID":C["red"]}
        self.ptc_result_text.tag_config("v", foreground=col_map.get(verdict,C["text"]),
                                         font=("Courier",10,"bold"))
        self.ptc_result_text.insert("end", lines[0]+"\n", "v")
        self.ptc_result_text.insert("end", "\n".join(lines[1:]))
        self.ptc_result_text.config(state="disabled")

    def _calc_stop_loss(self):
        sym = self.sl_sym_var.get().strip().upper()
        entry_s = self.sl_entry_var.get().strip()
        if not sym or not entry_s: return
        if not sym.endswith(".NS"): sym += ".NS"
        try: entry = float(entry_s.replace(",",""))
        except ValueError: return
        def _run():
            try:
                from risk import get_stop_loss
                sl = get_stop_loss(sym, entry)
                msg = (f"Stop: ₹{sl['stop']:,.2f}  |  "
                       f"Risk: ₹{sl['risk_per_share']:,.2f} ({sl['risk_pct']:.1f}%)  |  "
                       f"ATR: {sl['atr'] or 'N/A'}  |  Method: {sl['method']}")
                log_queue.put(("sl_result", msg))
            except Exception as e:
                log_queue.put(("sl_result", f"Error: {e}"))
        threading.Thread(target=_run, daemon=True).start()

    def _add_trailing_stop(self):
        sym     = self.trail_sym_var.get().strip().upper()
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
            self.trail_tree.insert("","end", values=(
                t["symbol"].replace(".NS",""), f"₹{t['entry']:,.2f}",
                f"₹{t['current_high']:,.2f}", f"₹{t['stop']:,.2f}",
                f"{t['trail_pct']:.0f}%"))

    # ── Breakout methods ──────────────────────────────────────────────────────

    def _refresh_breakout(self):
        self._log_gui("Running breakout scan…")
        threading.Thread(target=self._fetch_breakout, daemon=True).start()

    def _fetch_breakout(self):
        try:
            from sources.breakout import full_breakout_scan
            log_queue.put(("breakout", full_breakout_scan(config.WATCHLIST)))
        except Exception as e:
            log.error(f"Breakout: {e}"); log_queue.put(("breakout",{}))

    def _update_breakout_ui(self, scan: dict):
        for i in self.bo_tree.get_children():  self.bo_tree.delete(i)
        for i in self.acc_tree.get_children(): self.acc_tree.delete(i)
        for i in self.rs_tree.get_children():  self.rs_tree.delete(i)
        for i in self.con_tree.get_children(): self.con_tree.delete(i)

        for r in scan.get("breakouts",[]):
            tag = "high" if r["confirmed"] else "medium"
            self.bo_tree.insert("","end", tags=(tag,), values=(
                r["symbol"], f"₹{r['price']:,.2f}", f"₹{r['high52']:,.2f}",
                f"{r['vol_ratio']:.1f}x", "✅ Confirmed" if r["confirmed"] else "⚠️ Low Vol"))

        for r in scan.get("accumulation",[]):
            self.acc_tree.insert("","end", values=(
                r["symbol"], f"₹{r['price']:,.2f}",
                f"{r['vol_ratio']:.1f}x", f"{r['price_range_pct']:.1f}%"))

        for r in scan.get("rel_strength",[]):
            tag = "out" if r["outperform"] else "und"
            self.rs_tree.insert("","end", tags=(tag,), values=(
                r["symbol"], f"₹{r['price']:,.2f}",
                f"{r['stock_ret']:+.1f}%", f"{r['nifty_ret']:+.1f}%",
                f"{r['rs']:.1f}", "✅ Outperform" if r["outperform"] else "❌ Under"))

        for r in scan.get("consolidation",[]):
            self.con_tree.insert("","end", values=(
                r["symbol"], f"₹{r['price']:,.2f}",
                f"{r['squeeze']*100:.0f}%", r["meaning"][:50]))

        self._log_gui("Breakout scan done.")

    def _send_breakout_report(self):
        threading.Thread(target=self._do_send_breakout, daemon=True).start()

    def _do_send_breakout(self):
        try:
            from sources.breakout import full_breakout_scan
            from formatter import format_breakout_report
            ok = sender.send_long(format_breakout_report(full_breakout_scan(config.WATCHLIST)))
            log_queue.put(("log", f"Breakout report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Breakout send: {e}")

    # ── Screener methods ──────────────────────────────────────────────────────

    def _refresh_screener(self):
        self.scr_btn.set_busy(True)
        self._log_gui("Fetching Screener.in data…")
        threading.Thread(target=self._fetch_screener, daemon=True).start()

    def _fetch_screener(self):
        try:
            from sources.screener_in import get_watchlist_screener
            log_queue.put(("screener", get_watchlist_screener(config.WATCHLIST)))
        except Exception as e:
            log.error(f"Screener: {e}"); log_queue.put(("screener",[]))

    def _update_screener_ui(self, data):
        for i in self.scr_tree.get_children(): self.scr_tree.delete(i)
        for r in data:
            pt  = r.get("profit_trend","—")
            fs  = f"{r['f_score']}/{r['f_score_max']}" if r.get("f_score") is not None else "—"
            self.scr_tree.insert("","end", values=(
                r["symbol"],
                f"{r['roce']:.0f}%" if r.get("roce") else "—",
                f"{r['roe']:.0f}%"  if r.get("roe")  else "—",
                f"{r['debt_equity']:.1f}" if r.get("debt_equity") is not None else "—",
                fs, pt,
                f"{r['sales_cagr_10y']:.0f}%" if r.get("sales_cagr_10y") else "—",
            ))
        self.scr_btn.set_busy(False)
        self._log_gui(f"Screener data loaded — {len(data)} stocks.")

    def _send_screener_report(self):
        threading.Thread(target=lambda: self._do_send("screener"), daemon=True).start()

    def _do_send(self, kind):
        try:
            if kind == "screener":
                from sources.screener_in import get_watchlist_screener
                from formatter import format_screener_report
                ok = sender.send_long(format_screener_report(get_watchlist_screener(config.WATCHLIST)))
            log_queue.put(("log", f"{kind} report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"{kind} send: {e}")

    def _refresh_earnings_history(self):
        self._log_gui("Fetching earnings history…")
        threading.Thread(target=self._fetch_eh, daemon=True).start()

    def _fetch_eh(self):
        try:
            from sources.earnings_history import get_watchlist_earnings_history
            log_queue.put(("earnings_history", get_watchlist_earnings_history(config.WATCHLIST)))
        except Exception as e:
            log.error(f"EH: {e}"); log_queue.put(("earnings_history",[]))

    def _update_eh_ui(self, data):
        for i in self.eh_tree.get_children(): self.eh_tree.delete(i)
        for r in data:
            q   = r.get("quality","—")
            strk= f"{r['streak_count']}x {r['streak_type']}" if r.get("streak_type") in ("BEAT","MISS") else "—"
            tag = {"EXCELLENT":"EXCELLENT","GOOD":"GOOD","POOR":"POOR"}.get(q,"")
            self.eh_tree.insert("","end", tags=(tag,), values=(
                r["symbol"], r["beats"], r["misses"],
                f"{r['avg_surprise']:+.1f}%", q, strk))
        self._log_gui(f"Earnings history: {len(data)} stocks.")

    def _send_earnings_history(self):
        threading.Thread(target=self._do_send_eh, daemon=True).start()

    def _do_send_eh(self):
        try:
            from sources.earnings_history import get_watchlist_earnings_history
            from formatter import format_earnings_history
            ok = sender.send_long(format_earnings_history(get_watchlist_earnings_history(config.WATCHLIST)))
            log_queue.put(("log", f"Earnings history {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"EH send: {e}")

    def _run_peer_compare(self):
        sym = self.pc_sym_var.get().strip().upper()
        if not sym: return
        if not sym.endswith(".NS"): sym += ".NS"
        self._log_gui(f"Peer comparison: {sym}…")
        threading.Thread(target=lambda: self._fetch_peer(sym), daemon=True).start()

    def _fetch_peer(self, sym):
        try:
            from sources.peer_compare import get_peer_comparison
            log_queue.put(("peer", get_peer_comparison(sym)))
        except Exception as e:
            log.error(f"Peer: {e}"); log_queue.put(("peer", None))

    def _update_peer_ui(self, result):
        for i in self.pc_tree.get_children(): self.pc_tree.delete(i)
        if not result: return
        for p in result.get("peers",[]):
            tag = ("target",) if p["is_target"] else ()
            self.pc_tree.insert("","end", tags=tag, values=(
                ("→ " if p["is_target"] else "  ") + p["symbol"],
                f"{p['pe']:.1f}"  if p.get("pe")  else "—",
                f"{p['roe']:.1f}%" if p.get("roe") else "—",
                f"{p['rev_growth']:+.1f}%" if p.get("rev_growth") else "—",
                f"{p['margin']:.1f}%" if p.get("margin") else "—",
                f"#{p['pe_rank']}"  if p.get("pe_rank")  else "—",
                f"#{p['roe_rank']}" if p.get("roe_rank") else "—",
            ))
        # Also send to Telegram
        try:
            from formatter import format_peer_comparison
            sender.send_long(format_peer_comparison(result))
        except Exception: pass
        self._log_gui(f"Peer comparison done: {result.get('n_peers',0)} peers.")

    def _refresh_vwap(self):
        self._log_gui("Fetching VWAP…")
        threading.Thread(target=self._fetch_vwap, daemon=True).start()

    def _fetch_vwap(self):
        try:
            from sources.vwap import get_watchlist_vwap
            log_queue.put(("vwap", get_watchlist_vwap(config.WATCHLIST)))
        except Exception as e:
            log.error(f"VWAP: {e}"); log_queue.put(("vwap",[]))

    def _update_vwap_ui(self, data):
        for i in self.vwap_tree.get_children(): self.vwap_tree.delete(i)
        for r in data:
            sig = r.get("signal","NEUTRAL")
            self.vwap_tree.insert("","end", tags=(sig,), values=(
                r["symbol"], f"₹{r['price']:,.2f}", f"₹{r['vwap']:,.2f}",
                f"{r['diff_pct']:+.1f}%", sig))
        self._log_gui(f"VWAP loaded: {len(data)} stocks.")

    def _send_vwap_report(self):
        threading.Thread(target=self._do_send_vwap, daemon=True).start()

    def _do_send_vwap(self):
        try:
            from sources.vwap import get_watchlist_vwap
            from formatter import format_vwap_report
            ok = sender.send_long(format_vwap_report(get_watchlist_vwap(config.WATCHLIST)))
            log_queue.put(("log", f"VWAP report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"VWAP send: {e}")

    # ── Paper Trading methods ─────────────────────────────────────────────────

    def _paper_execute(self):
        sym    = self.pt_sym_var.get().strip().upper()
        qty_s  = self.pt_qty_var.get().strip()
        price_s= self.pt_price_var.get().strip()
        side   = self.pt_side_var.get()
        if not sym or not qty_s or not price_s: return
        if not sym.endswith(".NS"): sym += ".NS"
        try:
            qty   = int(qty_s)
            price = float(price_s.replace(",",""))
        except ValueError: return
        from sources.paper_trading import paper_buy, paper_sell
        result = paper_buy(sym, qty, price, self.pt_reason_var.get()) if side=="BUY" \
                 else paper_sell(sym, qty, price, self.pt_reason_var.get())
        if result.get("success"):
            msg = f"✅ Paper {side}: {sym} {qty}@₹{price:,.2f}"
            self.pt_status_lbl.config(text=msg, fg=C["green"])
            self._log_gui(msg)
            self._refresh_paper_portfolio()
        else:
            self.pt_status_lbl.config(text=f"❌ {result.get('error','Failed')}", fg=C["red"])
        self.root.after(4000, lambda: self.pt_status_lbl.config(text=""))

    def _refresh_paper_portfolio(self):
        threading.Thread(target=self._fetch_paper_portfolio, daemon=True).start()

    def _fetch_paper_portfolio(self):
        try:
            from sources.paper_trading import get_portfolio_summary
            from data_fetcher import get_price
            positions = __import__("sources.paper_trading", fromlist=["get_positions"]).get_positions()
            prices = {}
            for p in positions:
                pr = get_price(p["symbol"] + ".NS")
                if pr: prices[p["symbol"]] = pr
            log_queue.put(("paper_portfolio", get_portfolio_summary(prices)))
        except Exception as e:
            log.error(f"Paper portfolio: {e}")

    def _update_paper_portfolio_ui(self, summary):
        # Summary text
        self.pt_summary_text.config(state="normal"); self.pt_summary_text.delete("1.0","end")
        lines = [
            f"Starting Capital  ₹{summary.get('starting_cash',1000000):,.0f}",
            f"Current Value     ₹{summary.get('total_value',0):,.0f}",
            f"Cash Available    ₹{summary.get('cash',0):,.0f}",
            f"Total P&L         {'+'if summary.get('total_pnl',0)>=0 else ''}₹{summary.get('total_pnl',0):,.0f}  ({summary.get('total_pnl_pct',0):+.2f}%)",
        ]
        self.pt_summary_text.insert("end","\n".join(lines))
        self.pt_summary_text.config(state="disabled")
        # Positions
        for i in self.pt_pos_tree.get_children(): self.pt_pos_tree.delete(i)
        for p in summary.get("positions",[]):
            tag = "up" if p["pnl"]>=0 else "dn"
            self.pt_pos_tree.insert("","end", tags=(tag,), values=(
                p["symbol"], p["qty"], f"₹{p['avg_price']:,.2f}",
                f"₹{p['cur_price']:,.2f}",
                f"{'+'if p['pnl']>=0 else ''}₹{p['pnl']:,.0f}",
                f"{p['pnl_pct']:+.1f}%"))
        # Trade history
        from sources.paper_trading import get_trade_history
        for i in self.pt_hist_tree.get_children(): self.pt_hist_tree.delete(i)
        for t in get_trade_history(limit=20):
            self.pt_hist_tree.insert("","end", values=(
                t["id"], t["symbol"], t["action"], t["qty"],
                f"₹{t['price']:,.2f}", f"₹{t['value']:,.0f}",
                f"{'+'if (t.get('pnl') or 0)>=0 else ''}₹{t.get('pnl',0) or 0:,.0f}",
                t["trade_date"]))

    def _send_paper_report(self):
        threading.Thread(target=self._do_send_paper, daemon=True).start()

    def _do_send_paper(self):
        try:
            from sources.paper_trading import get_portfolio_summary
            from formatter import format_paper_portfolio
            ok = sender.send_long(format_paper_portfolio(get_portfolio_summary()))
            log_queue.put(("log", f"Paper report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Paper send: {e}")

    def _reset_paper_portfolio(self):
        from tkinter import messagebox
        if messagebox.askyesno("Reset","Reset virtual portfolio to ₹10L cash?"):
            from sources.paper_trading import reset_paper_portfolio
            reset_paper_portfolio()
            self._refresh_paper_portfolio()
            self._log_gui("Paper portfolio reset to ₹10L.")

    # ── Tax methods ───────────────────────────────────────────────────────────

    def _refresh_tax(self):
        self.tax_btn.set_busy(True)
        self._log_gui("Calculating tax P&L…")
        threading.Thread(target=self._fetch_tax, daemon=True).start()

    def _fetch_tax(self):
        try:
            from data_fetcher import get_portfolio_pnl
            from tax import calculate_portfolio_tax, total_tax_summary
            pnl     = get_portfolio_pnl(config.PORTFOLIO)
            results = calculate_portfolio_tax(config.PORTFOLIO, pnl)
            summary = total_tax_summary(results)
            log_queue.put(("tax", (results, summary)))
        except Exception as e:
            log.error(f"Tax: {e}"); log_queue.put(("tax",([],{})))

    def _update_tax_ui(self, data):
        results, summary = data
        for i in self.tax_tree.get_children(): self.tax_tree.delete(i)
        for r in results:
            tt  = r.get("current_type","—")
            tag = "ltcg" if tt=="LTCG" else "stcg"
            save= f"₹{r['tax_saving']:,.0f}" if r.get("tax_saving",0)>0 else "—"
            self.tax_tree.insert("","end", tags=(tag,), values=(
                r.get("symbol",""),
                f"{'+'if r['pnl']>=0 else ''}₹{r['pnl']:,.0f}",
                f"{r.get('holding_days',0)}d",
                tt,
                f"₹{r.get('tax_now',0):,.0f}",
                save,
                r.get("advice","")[:40],
            ))
        if summary:
            self.tax_summary_lbl.config(
                text=f"Total Tax: STCG ₹{summary.get('stcg_tax',0):,.0f}  "
                     f"LTCG ₹{summary.get('ltcg_tax',0):,.0f}  "
                     f"Potential saving ₹{summary.get('potential_saving',0):,.0f}")
        self.tax_btn.set_busy(False)
        self._log_gui("Tax P&L calculated.")

    def _send_tax_report(self):
        threading.Thread(target=self._do_send_tax, daemon=True).start()

    def _do_send_tax(self):
        try:
            from data_fetcher import get_portfolio_pnl
            from tax import calculate_portfolio_tax, total_tax_summary
            from formatter import format_tax_report
            pnl     = get_portfolio_pnl(config.PORTFOLIO)
            results = calculate_portfolio_tax(config.PORTFOLIO, pnl)
            summary = total_tax_summary(results)
            ok = sender.send_long(format_tax_report(results, summary))
            log_queue.put(("log", f"Tax report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Tax send: {e}")

    # ── Golden Rules methods ──────────────────────────────────────────────────

    def _refresh_golden_rules(self):
        self._log_gui("Checking golden rules…")
        threading.Thread(target=self._fetch_golden_rules, daemon=True).start()

    def _fetch_golden_rules(self):
        try:
            from rules import check_golden_rules
            log_queue.put(("golden_rules", check_golden_rules(config.PORTFOLIO, config.WATCHLIST)))
        except Exception as e:
            log.error(f"Rules: {e}"); log_queue.put(("golden_rules", None))

    def _update_golden_rules_ui(self, result):
        # Update dashboard rules panel too
        try:
            if result:
                verdict = result["verdict"]
                col = C["green"] if "SAFE" in verdict else (C["red"] if "AVOID" in verdict or "STAY" in verdict else C["amber"])
                self.dash_rules_lbl.config(text=verdict, fg=col)
                passed = result["passed"]; total = result["total"]
                self.dash_rules_detail.config(
                    text=f"{passed}/{total} rules passed — {result.get('explanation','')[:80]}")
        except Exception:
            pass
        self.rules_text.config(state="normal"); self.rules_text.delete("1.0","end")
        if not result:
            self.rules_text.insert("end","Could not check rules.")
            self.rules_text.config(state="disabled"); return
        lines = [
            f"VERDICT: {result['verdict']}  ({result['passed']}/{result['total']} passed)",
            result.get("explanation",""), "─"*40,
        ]
        for r in result.get("rules",[]):
            icon = "✅" if r.get("pass") else ("❌" if r.get("pass") is False else "⚪")
            lines.append(f"{icon} {r['rule'][:38]}")
            lines.append(f"   {r.get('value','')}")
        self.rules_text.insert("end","\n".join(lines))
        self.rules_text.config(state="disabled")
        self._log_gui(f"Golden rules: {result['verdict']}")

    def _send_golden_rules(self):
        threading.Thread(target=self._do_send_rules, daemon=True).start()

    def _do_send_rules(self):
        try:
            from rules import check_golden_rules
            from formatter import format_golden_rules
            ok = sender.send_long(format_golden_rules(
                check_golden_rules(config.PORTFOLIO, config.WATCHLIST)))
            log_queue.put(("log", f"Rules {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Rules send: {e}")

    # ── Rebalance methods ─────────────────────────────────────────────────────

    def _refresh_rebalance(self):
        self._log_gui("Analysing rebalance…")
        threading.Thread(target=self._fetch_rebalance, daemon=True).start()

    def _fetch_rebalance(self):
        try:
            from data_fetcher import get_portfolio_pnl
            from rebalance import get_rebalance_suggestions
            pnl   = get_portfolio_pnl(config.PORTFOLIO)
            total = sum(r.get("market_value",0) for r in pnl)
            log_queue.put(("rebalance", get_rebalance_suggestions(pnl, total)))
        except Exception as e:
            log.error(f"Rebalance: {e}"); log_queue.put(("rebalance",{}))

    def _update_rebalance_ui(self, result):
        if not result: return
        health = result.get("health","—")
        h_col  = {"HEALTHY":C["green"],"NEEDS TRIM":C["amber"],"REBALANCE NOW":C["red"]}.get(health,C["muted"])
        self.reb_summary_lbl.config(
            text=f"Status: {health}  |  Cash: {result.get('cash_pct',0):.1f}%",fg=h_col)
        for i in self.reb_tree.get_children(): self.reb_tree.delete(i)
        for p in result.get("positions",[]):
            tag  = "over" if p["overweight"] else ("tiny" if p["tiny"] else "ok")
            flag = "⚠️ TOO LARGE" if p["overweight"] else ("🔸 TINY" if p["tiny"] else "✅ OK")
            self.reb_tree.insert("","end", tags=(tag,), values=(
                p["symbol"], f"{p['pct']:.1f}%", flag))
        self.reb_tree.insert("","end", values=("CASH", f"{result.get('cash_pct',0):.1f}%",""))
        # Actions
        self.reb_actions_text.config(state="normal"); self.reb_actions_text.delete("1.0","end")
        actions = result.get("actions",[])
        if actions:
            lines = ["SUGGESTED ACTIONS:", "─"*35]
            for a in actions:
                lines.append(f"• {a['action']} {a['symbol']}")
                lines.append(f"  {a['reason']}")
                if a.get("amount"): lines.append(f"  Amount: ₹{a['amount']:,.0f}")
            self.reb_actions_text.insert("end","\n".join(lines))
        else:
            self.reb_actions_text.insert("end","✅ Portfolio is well balanced.")
        self.reb_actions_text.config(state="disabled")
        self._log_gui(f"Rebalance: {health}")

    def _send_rebalance_report(self):
        threading.Thread(target=self._do_send_rebalance, daemon=True).start()

    def _do_send_rebalance(self):
        try:
            from data_fetcher import get_portfolio_pnl
            from rebalance import get_rebalance_suggestions
            from formatter import format_rebalance_report
            pnl   = get_portfolio_pnl(config.PORTFOLIO)
            total = sum(r.get("market_value",0) for r in pnl)
            ok    = sender.send_long(format_rebalance_report(get_rebalance_suggestions(pnl, total)))
            log_queue.put(("log", f"Rebalance report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Rebalance send: {e}")

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

        # ── Dashboard widgets ─────────────────────────────────────────────
        try:
            self.dash_day_pnl.config(
                text=f"{'+'if tot_day>=0 else ''}₹{tot_day:,.0f}", fg=_col(tot_day))
            self.dash_total_pnl.config(
                text=f"{'+'if tot_pnl>=0 else ''}₹{tot_pnl:,.0f}", fg=_col(tot_pnl))
            self.dash_port_val.config(text=f"₹{tot_val:,.0f}", fg=C["text"])

            # Dashboard portfolio tree
            for i in self.dash_port_tree.get_children():
                self.dash_port_tree.delete(i)
            for r in rows:
                sym = r["symbol"].replace(".NS","")
                dp  = r.get("day_pnl",0)
                tp  = r.get("total_pnl",0)
                sig = r.get("ta_signal","") if r.get("ta_signal") else ""
                tag = "up" if dp >= 0 else "dn"
                self.dash_port_tree.insert("","end", tags=(tag,), values=(
                    sym, f"₹{r['price']:,.2f}",
                    f"{'+'if dp>=0 else ''}₹{dp:,.0f}",
                    f"{'+'if tp>=0 else ''}₹{tp:,.0f}",
                    sig or "—",
                ))
            self.dash_port_tree.tag_configure("up",  foreground=C["green"])
            self.dash_port_tree.tag_configure("dn",  foreground=C["red"])

            # Update news pane
            self._refresh_dashboard_news()
        except Exception:
            pass

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

        # ── Dashboard widgets ─────────────────────────────────────────────
        try:
            for i in self.dash_idx_tree.get_children(): self.dash_idx_tree.delete(i)
            for name, d in indices.items():
                tag = "up" if d["pct"] >= 0 else "dn"
                self.dash_idx_tree.insert("","end", tags=(tag,), values=(
                    name, f"{d['price']:,.2f}",
                    f"{'+'if d['change']>=0 else ''}{d['change']:,.2f}",
                    f"{'+'if d['pct']>=0 else ''}{d['pct']:.2f}%",
                ))
            self.dash_idx_tree.tag_configure("up", foreground=C["green"])
            self.dash_idx_tree.tag_configure("dn", foreground=C["red"])

            # Market mood banner
            nifty = indices.get("NIFTY 50",{})
            pct   = nifty.get("pct",0)
            if pct > 0.5:
                mood_text = f"📈  MARKET RISING  NIFTY {nifty.get('price',0):,.0f}  (+{pct:.2f}%)"
                mood_bg   = C["green_dim"]; mood_fg = C["green"]
            elif pct < -0.5:
                mood_text = f"📉  MARKET FALLING  NIFTY {nifty.get('price',0):,.0f}  ({pct:.2f}%)"
                mood_bg   = C["red_dim"];   mood_fg = C["red"]
            else:
                mood_text = f"➡️  MARKET FLAT  NIFTY {nifty.get('price',0):,.0f}  ({pct:+.2f}%)"
                mood_bg   = C["bg3"];       mood_fg = C["muted"]
            self.mood_banner.config(text=mood_text, bg=mood_bg, fg=mood_fg)
        except Exception:
            pass

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
        # Update dashboard top signals
        try:
            for i in self.dash_sig_tree.get_children():
                self.dash_sig_tree.delete(i)
            top = [s for s in sigs if s["severity"] in ("CRITICAL","HIGH")][:8]
            for s in top:
                self.dash_sig_tree.insert("","end", tags=(s["severity"],), values=(
                    s["severity"], s["symbol"][:8], s["summary"][:80]))
        except Exception:
            pass

    def _refresh_dashboard_news(self):
        threading.Thread(target=self._fetch_dashboard_news, daemon=True).start()

    def _fetch_dashboard_news(self):
        try:
            news = get_news_headlines(config.WATCHLIST, max_per_stock=1)
            log_queue.put(("dashboard_news", news))
        except Exception as e:
            log.debug(f"Dashboard news: {e}")

    def _update_dashboard_news(self, news: list):
        try:
            self.dash_news_text.config(state="normal")
            self.dash_news_text.delete("1.0","end")
            for n in news[:6]:
                sym = n["symbol"].replace(".NS","")
                self.dash_news_text.insert("end", f"[{sym}] ", "sym")
                self.dash_news_text.insert("end", f"{n['title'][:70]}…  ")
                self.dash_news_text.insert("end", f"{n['age_hours']:.0f}h ago\n", "green" if n.get("score",0)>0 else "red")
            self.dash_news_text.config(state="disabled")
        except Exception:
            pass

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
                elif kind == "dashboard_news": self._update_dashboard_news(data)
                elif kind == "breakout":      self._update_breakout_ui(data)
                elif kind == "screener":      self._update_screener_ui(data)
                elif kind == "earnings_history": self._update_eh_ui(data)
                elif kind == "peer":          self._update_peer_ui(data)
                elif kind == "vwap":          self._update_vwap_ui(data)
                elif kind == "paper_portfolio": self._update_paper_portfolio_ui(data)
                elif kind == "tax":           self._update_tax_ui(data)
                elif kind == "golden_rules":  self._update_golden_rules_ui(data)
                elif kind == "rebalance":     self._update_rebalance_ui(data)
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

    # ── Sentiment methods ─────────────────────────────────────────────────────

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
        vix = sent.get("vix",{}); pcr = sent.get("pcr",{}); ad = sent.get("ad",{})
        mood = sent.get("mood","NEUTRAL")
        v = vix.get("vix",0)
        vix_col = C["red"] if v>20 else (C["amber"] if v>15 else C["green"])
        self.vix_val_lbl.config(text=f"{v:.2f}", fg=vix_col)
        self.vix_level_lbl.config(text=vix.get("level","—"))
        self.vix_mean_lbl.config(text=vix.get("meaning","—"))
        self.vix_act_lbl.config(text=f"→ {vix.get('action','—')}")
        p = pcr.get("pcr",0)
        pcr_col = C["green"] if p>1.2 else (C["red"] if p<0.8 else C["muted"])
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
        # Dashboard VIX
        try:
            self.dash_vix.config(text=f"{v:.1f}", fg=vix_col)
            self.dash_pcr.config(text=f"{p:.2f}", fg=pcr_col)
        except Exception: pass
        self._log_gui(f"Sentiment refreshed. Mood: {mood}")

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
            ok1    = sender.send_long(format_sentiment_report(sent))
            ok2    = sender.send_long(format_sector_rotation(sector, rsigs))
            log_queue.put(("log", f"Sentiment {'sent ✅' if ok1 and ok2 else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Sentiment send: {e}")

    # ── Options methods ───────────────────────────────────────────────────────

    def _refresh_options(self):
        self._log_gui("Scanning unusual options…")
        threading.Thread(target=self._fetch_options, daemon=True).start()

    def _fetch_options(self):
        try:
            from sources.options import scan_unusual_activity
            log_queue.put(("options", scan_unusual_activity(config.WATCHLIST)))
        except Exception as e:
            log.error(f"Options scan: {e}"); log_queue.put(("options",[]))

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

    # ── Promoter methods ──────────────────────────────────────────────────────

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
            log.error(f"Promoter fetch: {e}"); log_queue.put(("promoter",([],[])))

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

    # ── Fundamentals methods ──────────────────────────────────────────────────

    def _refresh_fundamentals(self):
        self.fund_refresh_btn.set_busy(True)
        self.fund_status_lbl.config(text="Scanning…", fg=C["muted"])
        self._log_gui("Running fundamentals screener…")
        threading.Thread(target=self._fetch_fundamentals, daemon=True).start()

    def _fetch_fundamentals(self):
        try:
            from sources.fundamentals import get_watchlist_fundamentals
            log_queue.put(("fundamentals", get_watchlist_fundamentals(config.WATCHLIST)))
        except Exception as e:
            log.error(f"Fundamentals: {e}"); log_queue.put(("fundamentals",[]))

    def _update_fundamentals_ui(self, data: list):
        for i in self.fund_tree.get_children(): self.fund_tree.delete(i)
        sig_map = {"STRONG BUY":"🚀 STRONG BUY","BUY":"📈 BUY","HOLD":"⏸ HOLD",
                   "SELL":"📉 SELL","STRONG SELL":"🔻 STRONG SELL"}
        for r in data:
            sym = r["symbol"]; sig = r.get("overall","HOLD")
            self.fund_tree.insert("","end", tags=(sig,), values=(
                sym, f"₹{r.get('price',0):,.2f}",
                f"{r['pe']:.1f}"     if r.get("pe")           else "—",
                f"{r['sector_pe']}"  if r.get("sector_pe")    else "—",
                f"{r['roe']:.1f}%"   if r.get("roe")          else "—",
                f"{r['debt_eq']:.0f}%" if r.get("debt_eq") is not None else "—",
                f"{r['rev_growth']:+.1f}%" if r.get("rev_growth") else "—",
                f"{r['profit_margin']:.1f}%" if r.get("profit_margin") else "—",
                sig_map.get(sig,sig), str(r.get("score",0)),
            ))
        self.fund_refresh_btn.set_busy(False)
        self.fund_status_lbl.config(text=f"{len(data)} stocks screened.", fg=C["green"])
        self._log_gui(f"Fundamentals done — {len(data)} stocks.")

    def _send_fundamentals(self):
        threading.Thread(target=self._do_send_fundamentals, daemon=True).start()

    def _do_send_fundamentals(self):
        try:
            from sources.fundamentals import get_watchlist_fundamentals
            from formatter import format_fundamentals_report
            ok = sender.send_long(format_fundamentals_report(get_watchlist_fundamentals(config.WATCHLIST)))
            log_queue.put(("log", f"Fundamentals report {'sent ✅' if ok else 'failed ❌'}"))
        except Exception as e:
            log.error(f"Fundamentals send: {e}")

    def _fund_deep_dive(self):
        sym = self.fund_sym_var.get().strip().upper()
        if not sym: return
        if not sym.endswith(".NS"): sym += ".NS"
        self._log_gui(f"Fundamentals deep dive: {sym}…")
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
            "─"*42,
            f"P/E:           {r.get('pe','—')}  (Sector avg {r.get('sector_pe','—')})",
            f"P/E Flag:      {r.get('pe_flag','—')}",
            f"ROE:           {r.get('roe','—')}%  {r.get('roe_flag','')}",
            f"Debt/Equity:   {r.get('debt_eq','—')}%  {r.get('debt_flag','')}",
            f"Rev Growth:    {r.get('rev_growth','—')}%",
            f"Profit Margin: {r.get('profit_margin','—')}%",
            f"FCF:           {r.get('fcf_flag','—')}",
            f"Beta:          {r.get('beta','—')}",
            f"Dividend:      {r.get('div_yield','—')}%",
            f"Analyst:       {r.get('analyst_rec','—')}",
            f"Target Price:  ₹{r.get('target_price','—')}  ({r.get('upside','—')}% upside)",
        ]
        self.fund_detail_text.insert("end","\n".join(lines))
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
            ("DXY Dollar",    "DXY",       ""),
            ("India 10Y",     "INDIA_10Y", "%"),
            ("Brent Crude",   "CRUDE_WTI", "$"),
            ("Gold",          "GOLD",      "$"),
            ("Copper",        "COPPER",    "$"),
            ("US VIX",        "SP500_VIX", ""),
        ]
        lines = []
        for label,key,unit in rows:
            d   = data.get(key,{}); val = d.get("price",0); pct = d.get("pct",0)
            arrow = "▲" if pct>0 else ("▼" if pct<0 else "─")
            lines.append(f"{label:<18} {unit}{val:<10} {arrow}{pct:+.2f}%")
        spread = macro.get("spread",0); inv = macro.get("inverted",False)
        lines.append(f"{'Yield Curve':<18} {spread:.3f}%  {'⚠ INVERTED' if inv else 'Normal'}")
        self.macro_detail_text.insert("end","\n".join(lines))
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
        sym = self.j_sym_var.get().strip().upper()
        entry_s = self.j_entry_var.get().strip()
        qty_s   = self.j_qty_var.get().strip()
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
        self._log_gui(f"Trade #{tid} logged: {sym} {self.j_side_var.get()} {qty}@{entry}")

    def _close_trade_entry(self):
        tid_s  = self.j_close_id_var.get().strip()
        exit_s = self.j_exit_var.get().strip()
        if not tid_s or not exit_s: return
        try:
            tid    = int(tid_s)
            exit_p = float(exit_s.replace(",",""))
        except ValueError: return
        from sources.journal import close_trade
        result = close_trade(tid, exit_p, exit_reason=self.j_exit_reason_var.get())
        if result:
            pnl    = result.get("pnl",0); status = result.get("status","—")
            col    = C["green"] if pnl>=0 else C["red"]
            self.j_status_lbl.config(
                text=f"#{tid} closed: {status}  ₹{pnl:+,.2f}", fg=col)
            self.root.after(4000, lambda: self.j_status_lbl.config(text=""))
            self._refresh_journal_ui()

    def _open_close_dialog(self, event):
        item = self.open_tree.focus()
        if not item: return
        row = self.open_tree.item(item)["values"]
        if row: self.j_close_id_var.set(str(row[0]))

    def _refresh_journal_ui(self):
        from sources.journal import get_open_trades, get_closed_trades, get_performance_stats
        for i in self.open_tree.get_children(): self.open_tree.delete(i)
        for t in get_open_trades():
            self.open_tree.insert("","end", values=(
                t["id"], t["symbol"].replace(".NS",""),
                t.get("side","BUY"), f"₹{t['entry_price']:,.2f}", t["qty"],
                f"₹{t['stop_loss']:,.2f}" if t.get("stop_loss") else "—",
                f"₹{t['target']:,.2f}"    if t.get("target")    else "—",
                t["entry_date"], (t.get("reason","")[:30]) or "—",
            ))
        for i in self.closed_tree.get_children(): self.closed_tree.delete(i)
        for t in get_closed_trades(limit=30):
            tag = t.get("status","BREAK_EVEN")
            self.closed_tree.insert("","end", tags=(tag,), values=(
                t["id"], t["symbol"].replace(".NS",""),
                f"₹{t['pnl']:+,.2f}" if t.get("pnl") is not None else "—",
                f"{t['pnl_pct']:+.2f}%" if t.get("pnl_pct") is not None else "—",
                tag,
            ))
        stats = get_performance_stats()
        self.stats_text.config(state="normal")
        self.stats_text.delete("1.0","end")
        if stats.get("total",0) == 0:
            self.stats_text.insert("end","No closed trades yet.\nStart logging trades!")
        else:
            lines = [
                f"Grade:        {stats.get('grade','—')}",
                f"Total Trades  {stats['total']}",
                f"Wins          {stats['wins']} ({stats['win_rate']:.1f}%)",
                f"Losses        {stats['losses']}",
                "─"*32,
                f"Avg Win       ₹{stats['avg_win']:,.2f}",
                f"Avg Loss      ₹{stats['avg_loss']:,.2f}",
                f"R:R Ratio     {stats['rr_ratio']:.2f}",
                f"Expectancy    ₹{stats['expectancy']:,.2f}/trade",
                "─"*32,
                f"Total P&L     ₹{stats['total_pnl']:,.2f}",
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
