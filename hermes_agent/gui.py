"""
Hermes Agent — Tkinter GUI
A local dashboard that runs all Hermes tasks with a live interface.
Telegram alerts still fire exactly as before — GUI is the control panel.

Run:
    python gui.py
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

# ── Add parent dir to path so imports work ───────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

import config
from data_fetcher import (
    get_indices,
    get_portfolio_pnl,
    get_fii_dii_data,
    get_news_headlines,
    get_52w_analysis,
    get_earnings_calendar,
)
from formatter import (
    format_morning_brief,
    format_52w_report,
    format_earnings_reminder,
)
from telegram_sender import TelegramSender
from alert_watcher import AlertWatcher

# ── Colours — dark terminal palette ──────────────────────────────────────────
C = {
    "bg":        "#0b0d0f",
    "bg2":       "#111417",
    "bg3":       "#181c20",
    "bg4":       "#1e2328",
    "border":    "#2a2f36",
    "text":      "#e8eaed",
    "muted":     "#7a8290",
    "dim":       "#4a5260",
    "green":     "#22c55e",
    "red":       "#ef4444",
    "amber":     "#f59e0b",
    "blue":      "#3b82f6",
    "purple":    "#a78bfa",
    "teal":      "#2dd4bf",
    "green_dim": "#14532d",
    "red_dim":   "#450a0a",
    "amber_dim": "#451a03",
}

IST = pytz.timezone("Asia/Kolkata")

# ── Queue for thread-safe log messages ───────────────────────────────────────
log_queue: queue.Queue = queue.Queue()


class QueueLogHandler(logging.Handler):
    """Sends log records into the GUI log queue."""
    def emit(self, record):
        msg = self.format(record)
        log_queue.put(("log", msg))


# ── Setup logging ─────────────────────────────────────────────────────────────
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

# ── Telegram sender (global, shared) ─────────────────────────────────────────
sender = TelegramSender(
    token   = config.TELEGRAM_BOT_TOKEN,
    chat_id = config.TELEGRAM_CHAT_ID,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper widgets
# ─────────────────────────────────────────────────────────────────────────────

class SectionLabel(tk.Label):
    def __init__(self, parent, text, **kw):
        super().__init__(
            parent, text=text.upper(),
            bg=C["bg"], fg=C["dim"],
            font=("Courier", 8, "normal"),
            anchor="w", **kw,
        )


class Card(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(
            parent,
            bg=C["bg2"],
            highlightbackground=C["border"],
            highlightthickness=1,
            padx=10, pady=8,
            **kw,
        )


class HermesButton(tk.Button):
    def __init__(self, parent, text, command, accent=False, **kw):
        colour = C["green"] if accent else C["muted"]
        super().__init__(
            parent, text=text, command=command,
            bg=C["bg3"], fg=colour,
            activebackground=C["bg4"], activeforeground=C["text"],
            relief="flat",
            highlightbackground=C["border"], highlightthickness=1,
            font=("Courier", 9, "bold"),
            padx=10, pady=4,
            cursor="hand2",
            **kw,
        )

    def set_busy(self, busy: bool):
        self.config(state="disabled" if busy else "normal",
                    fg=C["dim"] if busy else (C["green"] if "SEND" in str(self["text"]) or "BRIEF" in str(self["text"]) else C["muted"]))


# ─────────────────────────────────────────────────────────────────────────────
#  Main Application
# ─────────────────────────────────────────────────────────────────────────────

class HermesGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Hermes Agent")
        self.root.configure(bg=C["bg"])
        self.root.minsize(980, 700)

        # State
        self.alert_vars: dict[str, tk.BooleanVar] = {}   # key → armed?
        self.portfolio_data: list = []
        self.indices_data:   dict = {}
        self.running = True

        # Alert watcher (initialised after GUI)
        self.watcher = AlertWatcher(
            alerts       = config.PRICE_ALERTS,
            sender       = sender,
            poll_seconds = config.ALERT_POLL_SECONDS,
        )

        self._build_ui()
        self._start_background_threads()
        self._poll_queue()

        # Initial data load
        self.root.after(500, self._refresh_portfolio)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg=C["bg"], pady=10, padx=16)
        topbar.pack(fill="x")

        tk.Label(topbar, text="H", bg=C["bg"], fg=C["green"],
                 font=("Courier", 20, "bold")).pack(side="left")
        tk.Label(topbar, text="ERMES", bg=C["bg"], fg=C["text"],
                 font=("Courier", 20, "bold")).pack(side="left")
        tk.Label(topbar, text=" / agent", bg=C["bg"], fg=C["muted"],
                 font=("Courier", 11)).pack(side="left", padx=(4, 0))

        right = tk.Frame(topbar, bg=C["bg"])
        right.pack(side="right")

        self.status_dot = tk.Label(right, text="●", bg=C["bg"], fg=C["green"],
                                   font=("Courier", 12))
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(right, text="INITIALISING…", bg=C["bg"],
                                     fg=C["muted"], font=("Courier", 9))
        self.status_label.pack(side="left", padx=(4, 12))

        self.clock_label = tk.Label(right, text="", bg=C["bg"],
                                    fg=C["muted"], font=("Courier", 9))
        self.clock_label.pack(side="left")

        # ── Divider ──────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")

        # ── Main area: left panel + right log ────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=0, pady=0)

        left = tk.Frame(body, bg=C["bg"], padx=16, pady=12)
        left.pack(side="left", fill="both", expand=True)

        right_panel = tk.Frame(body, bg=C["bg"], padx=0, pady=0, width=320)
        right_panel.pack(side="right", fill="y")
        right_panel.pack_propagate(False)

        # ── Notebook tabs (left panel) ────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Hermes.TNotebook",
                         background=C["bg"], borderwidth=0, tabmargins=0)
        style.configure("Hermes.TNotebook.Tab",
                         background=C["bg3"], foreground=C["muted"],
                         font=("Courier", 9, "bold"),
                         padding=[14, 6],
                         borderwidth=0)
        style.map("Hermes.TNotebook.Tab",
                  background=[("selected", C["bg4"])],
                  foreground=[("selected", C["text"])])

        self.notebook = ttk.Notebook(left, style="Hermes.TNotebook")
        self.notebook.pack(fill="both", expand=True)

        self._build_tab_portfolio()
        self._build_tab_indices()
        self._build_tab_alerts()
        self._build_tab_52w()
        self._build_tab_earnings()

        # ── Right panel: controls + log ───────────────────────────────────────
        self._build_right_panel(right_panel)

        # Start clock only after all widgets are created
        self._tick_clock()

    # ── Tab: Portfolio ────────────────────────────────────────────────────────

    def _build_tab_portfolio(self):
        frame = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(frame, text="  Portfolio  ")

        SectionLabel(frame, "Live Portfolio P&L").pack(anchor="w", pady=(10, 4))

        # Summary cards
        cards = tk.Frame(frame, bg=C["bg"])
        cards.pack(fill="x", pady=(0, 10))

        self.pnl_day_val   = self._metric_card(cards, "Day P&L",     "—")
        self.pnl_total_val = self._metric_card(cards, "Overall P&L", "—")
        self.pnl_value_val = self._metric_card(cards, "Market Value","—")

        # Table
        cols = ("Symbol", "Price", "Chg%", "Qty", "Avg", "Day P&L", "Total P&L", "Value")
        self.port_tree = self._make_tree(frame, cols, heights=10)
        self.port_tree.pack(fill="both", expand=True, pady=(0, 8))

        for col in cols:
            self.port_tree.heading(col, text=col)
            self.port_tree.column(col, anchor="center", width=90, minwidth=70)
        self.port_tree.column("Symbol", anchor="w", width=110)

        # Refresh button
        btn_row = tk.Frame(frame, bg=C["bg"])
        btn_row.pack(fill="x")
        self.refresh_btn = HermesButton(btn_row, "↻  REFRESH NOW", self._refresh_portfolio, accent=True)
        self.refresh_btn.pack(side="left")
        self.last_refresh_lbl = tk.Label(btn_row, text="", bg=C["bg"],
                                          fg=C["dim"], font=("Courier", 8))
        self.last_refresh_lbl.pack(side="left", padx=10)

    def _metric_card(self, parent, label, value):
        f = Card(parent)
        f.pack(side="left", padx=(0, 8), pady=2)
        tk.Label(f, text=label, bg=C["bg2"], fg=C["muted"],
                 font=("Courier", 8)).pack(anchor="w")
        val_lbl = tk.Label(f, text=value, bg=C["bg2"], fg=C["text"],
                           font=("Courier", 14, "bold"))
        val_lbl.pack(anchor="w")
        return val_lbl

    # ── Tab: Indices ──────────────────────────────────────────────────────────

    def _build_tab_indices(self):
        frame = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(frame, text="  Indices  ")

        SectionLabel(frame, "Market Indices").pack(anchor="w", pady=(10, 4))

        cols = ("Index", "Price", "Change", "Change %")
        self.idx_tree = self._make_tree(frame, cols, heights=6)
        self.idx_tree.pack(fill="x", pady=(0, 10))
        for col in cols:
            self.idx_tree.heading(col, text=col)
            w = 200 if col == "Index" else 120
            self.idx_tree.column(col, anchor="center", width=w)
        self.idx_tree.column("Index", anchor="w")

        SectionLabel(frame, "FII / DII Flow").pack(anchor="w", pady=(8, 4))
        self.fii_frame = tk.Frame(frame, bg=C["bg"])
        self.fii_frame.pack(fill="x")
        self.fii_labels: dict[str, tk.Label] = {}
        for key, lbl in [("fii_net","FII Net"), ("dii_net","DII Net"),
                          ("fii_buy","FII Buy"), ("fii_sell","FII Sell"),
                          ("dii_buy","DII Buy"), ("dii_sell","DII Sell")]:
            row = tk.Frame(self.fii_frame, bg=C["bg"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{lbl}:", bg=C["bg"], fg=C["muted"],
                     font=("Courier", 9), width=12, anchor="w").pack(side="left")
            lbl_val = tk.Label(row, text="—", bg=C["bg"], fg=C["text"],
                               font=("Courier", 9, "bold"))
            lbl_val.pack(side="left")
            self.fii_labels[key] = lbl_val

        HermesButton(frame, "↻  REFRESH INDICES", self._refresh_indices).pack(anchor="w", pady=10)

    # ── Tab: Price Alerts ─────────────────────────────────────────────────────

    def _build_tab_alerts(self):
        frame = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(frame, text="  Alerts  ")

        # ── Add / Edit form at top ────────────────────────────────────────────
        SectionLabel(frame, "Add / Edit Alert").pack(anchor="w", pady=(10, 4))

        form_card = Card(frame)
        form_card.pack(fill="x", pady=(0, 8))

        # Row 1: Symbol + Condition + Level
        row1 = tk.Frame(form_card, bg=C["bg2"])
        row1.pack(fill="x", pady=(0, 6))

        tk.Label(row1, text="Symbol", bg=C["bg2"], fg=C["muted"],
                 font=("Courier", 8), width=8, anchor="w").pack(side="left")
        self.alert_sym_var = tk.StringVar()
        sym_entry = tk.Entry(row1, textvariable=self.alert_sym_var,
                             bg=C["bg3"], fg=C["text"], insertbackground=C["text"],
                             relief="flat", font=("Courier", 10), width=14,
                             highlightbackground=C["border"], highlightthickness=1)
        sym_entry.pack(side="left", padx=(0, 12))
        sym_entry.insert(0, "RELIANCE.NS")

        tk.Label(row1, text="Condition", bg=C["bg2"], fg=C["muted"],
                 font=("Courier", 8), width=10, anchor="w").pack(side="left")
        self.alert_cond_var = tk.StringVar(value="below")
        cond_menu = ttk.Combobox(row1, textvariable=self.alert_cond_var,
                                  values=["below", "above"], state="readonly",
                                  width=8, font=("Courier", 10))
        cond_menu.pack(side="left", padx=(0, 12))

        tk.Label(row1, text="Level ₹", bg=C["bg2"], fg=C["muted"],
                 font=("Courier", 8), width=8, anchor="w").pack(side="left")
        self.alert_level_var = tk.StringVar()
        level_entry = tk.Entry(row1, textvariable=self.alert_level_var,
                               bg=C["bg3"], fg=C["text"], insertbackground=C["text"],
                               relief="flat", font=("Courier", 10), width=10,
                               highlightbackground=C["border"], highlightthickness=1)
        level_entry.pack(side="left", padx=(0, 12))

        # Row 2: Cooldown + buttons
        row2 = tk.Frame(form_card, bg=C["bg2"])
        row2.pack(fill="x")

        tk.Label(row2, text="Cooldown (h)", bg=C["bg2"], fg=C["muted"],
                 font=("Courier", 8), width=13, anchor="w").pack(side="left")
        self.alert_cool_var = tk.StringVar(value="4")
        cool_entry = tk.Entry(row2, textvariable=self.alert_cool_var,
                              bg=C["bg3"], fg=C["text"], insertbackground=C["text"],
                              relief="flat", font=("Courier", 10), width=6,
                              highlightbackground=C["border"], highlightthickness=1)
        cool_entry.pack(side="left", padx=(0, 16))

        self.alert_editing_idx = None  # None = adding new, int = editing existing

        self.alert_save_btn = HermesButton(row2, "＋  ADD ALERT",
                                            self._save_alert, accent=True)
        self.alert_save_btn.pack(side="left", padx=(0, 6))

        HermesButton(row2, "✕  CLEAR FORM", self._clear_alert_form).pack(side="left")

        self.form_status_lbl = tk.Label(row2, text="", bg=C["bg2"],
                                         fg=C["green"], font=("Courier", 8))
        self.form_status_lbl.pack(side="left", padx=10)

        # ── Alert list ────────────────────────────────────────────────────────
        SectionLabel(frame, "Active Alert Rules").pack(anchor="w", pady=(6, 4))

        list_frame = tk.Frame(frame, bg=C["bg"])
        list_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_frame, bg=C["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.alert_inner = tk.Frame(canvas, bg=C["bg"])
        self.alert_inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.alert_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._populate_alert_rows()

        # ── Recent fires log ──────────────────────────────────────────────────
        SectionLabel(frame, "Recent Alert Fires").pack(anchor="w", pady=(8, 2))
        self.alert_log = scrolledtext.ScrolledText(
            frame, height=4, bg=C["bg3"], fg=C["amber"],
            font=("Courier", 8), relief="flat",
            insertbackground=C["text"], state="disabled",
            highlightbackground=C["border"], highlightthickness=1,
        )
        self.alert_log.pack(fill="x", pady=(0, 8))

    def _save_alert(self):
        """Validate form and add or update an alert in config.PRICE_ALERTS."""
        sym   = self.alert_sym_var.get().strip().upper()
        cond  = self.alert_cond_var.get().strip()
        level_str = self.alert_level_var.get().strip()
        cool_str  = self.alert_cool_var.get().strip()

        # Validate
        if not sym:
            self._form_status("Symbol is required.", error=True); return
        try:
            level = float(level_str.replace(",", ""))
            if level <= 0:
                raise ValueError
        except ValueError:
            self._form_status("Level must be a positive number.", error=True); return
        try:
            cooldown = float(cool_str)
            if cooldown < 0:
                raise ValueError
        except ValueError:
            self._form_status("Cooldown must be a number ≥ 0.", error=True); return

        # Normalise symbol — append .NS if missing and not an index alias
        if sym not in ("NIFTY50", "BANKNIFTY", "SENSEX") and not sym.endswith(".NS") and not sym.startswith("^"):
            sym = sym + ".NS"

        new_alert = {
            "symbol":        sym,
            "condition":     cond,
            "level":         level,
            "cooldown_hours": cooldown,
        }

        if self.alert_editing_idx is not None:
            # Update existing
            config.PRICE_ALERTS[self.alert_editing_idx] = new_alert
            self._form_status(f"Alert updated: {sym} {cond} {level:,.2f}")
            self.alert_editing_idx = None
            self.alert_save_btn.config(text="＋  ADD ALERT")
        else:
            # Check for duplicate
            for a in config.PRICE_ALERTS:
                if a["symbol"] == sym and a["condition"] == cond and a["level"] == level:
                    self._form_status("Duplicate alert already exists.", error=True)
                    return
            config.PRICE_ALERTS.append(new_alert)
            self._form_status(f"Alert added: {sym} {cond} ₹{level:,.2f}")

        self._clear_alert_form()
        self._populate_alert_rows()
        self._save_alerts_to_config()
        log.info(f"Alert saved: {new_alert}")

    def _edit_alert(self, idx: int):
        """Load an existing alert into the form for editing."""
        alert = config.PRICE_ALERTS[idx]
        self.alert_sym_var.set(alert["symbol"])
        self.alert_cond_var.set(alert["condition"])
        self.alert_level_var.set(str(alert["level"]))
        self.alert_cool_var.set(str(alert["cooldown_hours"]))
        self.alert_editing_idx = idx
        self.alert_save_btn.config(text="✎  SAVE CHANGES")
        self._form_status(f"Editing: {alert['symbol']} — make changes and click Save.")

    def _delete_alert(self, idx: int):
        """Delete an alert after confirmation."""
        alert = config.PRICE_ALERTS[idx]
        sym   = alert["symbol"].replace(".NS", "")
        if messagebox.askyesno("Delete Alert",
                                f"Delete alert:\n{sym} {alert['condition']} ₹{alert['level']:,.2f}?"):
            config.PRICE_ALERTS.pop(idx)
            self._populate_alert_rows()
            self._save_alerts_to_config()
            self._form_status(f"Deleted alert for {sym}.")
            if self.alert_editing_idx == idx:
                self._clear_alert_form()

    def _clear_alert_form(self):
        self.alert_sym_var.set("")
        self.alert_cond_var.set("below")
        self.alert_level_var.set("")
        self.alert_cool_var.set("4")
        self.alert_editing_idx = None
        self.alert_save_btn.config(text="＋  ADD ALERT")
        self.form_status_lbl.config(text="")

    def _form_status(self, msg: str, error: bool = False):
        self.form_status_lbl.config(
            text=msg, fg=C["red"] if error else C["green"])
        self.root.after(4000, lambda: self.form_status_lbl.config(text=""))

    def _save_alerts_to_config(self):
        """Persist current PRICE_ALERTS to data/alerts.json."""
        try:
            from store import save as _store_save
            _store_save("alerts", config.PRICE_ALERTS)
            log.info("data/alerts.json updated.")
        except Exception as e:
            log.error(f"Failed to save alerts: {e}")

    def _populate_alert_rows(self):
        """Render one row per alert rule with arm/disarm, edit, delete."""
        for widget in self.alert_inner.winfo_children():
            widget.destroy()
        self.alert_vars.clear()

        if not config.PRICE_ALERTS:
            tk.Label(self.alert_inner, text="No alerts configured. Add one above.",
                     bg=C["bg"], fg=C["dim"], font=("Courier", 9)).pack(pady=20)
            return

        for i, alert in enumerate(config.PRICE_ALERTS):
            key       = f"{alert['symbol']}_{alert['condition']}_{alert['level']}"
            var       = tk.BooleanVar(value=True)
            self.alert_vars[key] = var

            row = Card(self.alert_inner)
            row.pack(fill="x", pady=3)

            direction = "▼ BELOW" if alert["condition"] == "below" else "▲ ABOVE"
            dir_col   = C["red"]   if alert["condition"] == "below" else C["green"]
            sym_clean = alert["symbol"].replace(".NS", "")

            # Left: symbol + detail
            left = tk.Frame(row, bg=C["bg2"])
            left.pack(side="left", fill="x", expand=True)

            tk.Label(left, text=sym_clean, bg=C["bg2"], fg=C["text"],
                     font=("Courier", 11, "bold")).pack(anchor="w")
            tk.Label(left,
                     text=f"{direction}  ₹{alert['level']:,.2f}  ·  cooldown {alert['cooldown_hours']}h",
                     bg=C["bg2"], fg=dir_col,
                     font=("Courier", 8)).pack(anchor="w")

            # Right: status label + toggle + edit + delete
            right_f = tk.Frame(row, bg=C["bg2"])
            right_f.pack(side="right")

            status_lbl = tk.Label(right_f, text="ARMED", bg=C["bg2"],
                                   fg=C["green"], font=("Courier", 8, "bold"))
            status_lbl.pack(side="left", padx=(0, 6))

            def _make_toggle(v, lbl, r):
                def toggle():
                    if v.get():
                        lbl.config(text="ARMED", fg=C["green"])
                        r.config(highlightbackground=C["border"])
                    else:
                        lbl.config(text="OFF",   fg=C["dim"])
                        r.config(highlightbackground=C["dim"])
                return toggle

            cb = tk.Checkbutton(
                right_f, variable=var,
                bg=C["bg2"], activebackground=C["bg2"],
                selectcolor=C["green_dim"], fg=C["green"],
                command=_make_toggle(var, status_lbl, row),
            )
            cb.pack(side="left", padx=(0, 4))

            # Edit button
            edit_btn = tk.Button(
                right_f, text="✎",
                bg=C["bg3"], fg=C["blue"],
                relief="flat", font=("Courier", 10),
                cursor="hand2", padx=4,
                command=lambda idx=i: self._edit_alert(idx),
            )
            edit_btn.pack(side="left", padx=(0, 4))

            # Delete button
            del_btn = tk.Button(
                right_f, text="✕",
                bg=C["bg3"], fg=C["red"],
                relief="flat", font=("Courier", 10),
                cursor="hand2", padx=4,
                command=lambda idx=i: self._delete_alert(idx),
            )
            del_btn.pack(side="left")

    # ── Tab: 52W Range ────────────────────────────────────────────────────────

    def _build_tab_52w(self):
        frame = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(frame, text="  52W Range  ")

        SectionLabel(frame, "52-Week Range Analysis — end of day").pack(anchor="w", pady=(10, 4))

        cols = ("Symbol", "Price", "52W Low", "52W High", "% from Low", "% from High", "Range Bar", "Status")
        self.w52_tree = self._make_tree(frame, cols, heights=12)
        self.w52_tree.pack(fill="both", expand=True, pady=(0, 8))

        widths = [100, 80, 80, 80, 90, 95, 130, 80]
        for col, w in zip(cols, widths):
            self.w52_tree.heading(col, text=col)
            self.w52_tree.column(col, anchor="center", width=w, minwidth=60)
        self.w52_tree.column("Symbol", anchor="w")
        self.w52_tree.column("Range Bar", anchor="w")

        self.w52_tree.tag_configure("danger", foreground=C["red"])
        self.w52_tree.tag_configure("warn",   foreground=C["amber"])
        self.w52_tree.tag_configure("safe",   foreground=C["green"])

        HermesButton(frame, "↻  RUN 52W ANALYSIS", self._refresh_52w).pack(anchor="w")

    # ── Tab: Earnings ─────────────────────────────────────────────────────────

    def _build_tab_earnings(self):
        frame = tk.Frame(self.notebook, bg=C["bg"])
        self.notebook.add(frame, text="  Earnings  ")

        SectionLabel(frame, "Upcoming Earnings — your watchlist").pack(anchor="w", pady=(10, 4))

        cols = ("Symbol", "Date", "Days Out", "Reminder")
        self.earn_tree = self._make_tree(frame, cols, heights=12)
        self.earn_tree.pack(fill="both", expand=True, pady=(0, 8))

        for col in cols:
            self.earn_tree.heading(col, text=col)
            self.earn_tree.column(col, anchor="center", width=140, minwidth=80)
        self.earn_tree.column("Symbol", anchor="w", width=120)

        self.earn_tree.tag_configure("urgent", foreground=C["red"])
        self.earn_tree.tag_configure("soon",   foreground=C["amber"])
        self.earn_tree.tag_configure("ok",     foreground=C["text"])

        HermesButton(frame, "↻  FETCH EARNINGS CALENDAR", self._refresh_earnings).pack(anchor="w")

    # ── Right panel: controls + log ───────────────────────────────────────────

    def _build_right_panel(self, parent):
        tk.Frame(parent, bg=C["border"], width=1).pack(side="left", fill="y")

        inner = tk.Frame(parent, bg=C["bg"], padx=14, pady=12)
        inner.pack(fill="both", expand=True)

        # Market status card
        SectionLabel(inner, "Market Status").pack(anchor="w", pady=(0, 4))
        status_card = Card(inner)
        status_card.pack(fill="x", pady=(0, 10))

        self.market_status_dot = tk.Label(status_card, text="●", bg=C["bg2"],
                                           font=("Courier", 12))
        self.market_status_dot.pack(side="left")
        self.market_status_lbl = tk.Label(status_card, text="Checking…",
                                           bg=C["bg2"], fg=C["muted"],
                                           font=("Courier", 9, "bold"))
        self.market_status_lbl.pack(side="left", padx=(6, 0))

        # Manual triggers
        SectionLabel(inner, "Manual Triggers").pack(anchor="w", pady=(6, 4))

        self.brief_btn = HermesButton(inner, "📨  SEND MORNING BRIEF",
                                       self._trigger_brief, accent=True)
        self.brief_btn.pack(fill="x", pady=2)

        self.w52_btn = HermesButton(inner, "📐  SEND 52W REPORT",
                                     self._trigger_52w)
        self.w52_btn.pack(fill="x", pady=2)

        self.earn_btn = HermesButton(inner, "🗓  SEND EARNINGS UPDATE",
                                      self._trigger_earnings)
        self.earn_btn.pack(fill="x", pady=2)

        self.test_btn = HermesButton(inner, "🔌  TEST TELEGRAM",
                                      self._test_telegram)
        self.test_btn.pack(fill="x", pady=2)

        # Next scheduled events
        SectionLabel(inner, "Next Scheduled").pack(anchor="w", pady=(12, 4))
        sched_card = Card(inner)
        sched_card.pack(fill="x", pady=(0, 10))
        for label, val in [
            ("Morning Brief", config.MORNING_BRIEF_TIME + " IST"),
            ("52W Report",    config.AFTER_MARKET_TIME  + " IST"),
            ("Alert Poll",    f"every {config.ALERT_POLL_SECONDS}s"),
        ]:
            row = tk.Frame(sched_card, bg=C["bg2"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, bg=C["bg2"], fg=C["muted"],
                     font=("Courier", 8), width=14, anchor="w").pack(side="left")
            tk.Label(row, text=val, bg=C["bg2"], fg=C["teal"],
                     font=("Courier", 8, "bold")).pack(side="left")

        # Log console
        SectionLabel(inner, "Live Log").pack(anchor="w", pady=(4, 2))
        self.log_box = scrolledtext.ScrolledText(
            inner, bg=C["bg3"], fg=C["text"],
            font=("Courier", 7), relief="flat",
            insertbackground=C["text"], state="disabled",
            highlightbackground=C["border"], highlightthickness=1,
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True)

        # Tag colours for log levels
        self.log_box.tag_config("INFO",    foreground=C["text"])
        self.log_box.tag_config("WARNING", foreground=C["amber"])
        self.log_box.tag_config("ERROR",   foreground=C["red"])
        self.log_box.tag_config("DEBUG",   foreground=C["dim"])
        self.log_box.tag_config("SUCCESS", foreground=C["green"])

        tk.Button(inner, text="Clear Log", command=self._clear_log,
                  bg=C["bg3"], fg=C["dim"], relief="flat",
                  font=("Courier", 7), padx=4, pady=2,
                  cursor="hand2").pack(anchor="e", pady=(2, 0))

    # ── Tree helper ───────────────────────────────────────────────────────────

    def _make_tree(self, parent, cols, heights=8) -> ttk.Treeview:
        style = ttk.Style()
        style.configure("Hermes.Treeview",
                         background=C["bg2"], foreground=C["text"],
                         fieldbackground=C["bg2"],
                         rowheight=24,
                         font=("Courier", 9),
                         borderwidth=0)
        style.configure("Hermes.Treeview.Heading",
                         background=C["bg3"], foreground=C["muted"],
                         font=("Courier", 8, "bold"),
                         relief="flat")
        style.map("Hermes.Treeview",
                  background=[("selected", C["bg4"])],
                  foreground=[("selected", C["text"])])

        tree = ttk.Treeview(parent, columns=cols, show="headings",
                             style="Hermes.Treeview", height=heights)
        return tree

    # ── Clock ─────────────────────────────────────────────────────────────────

    def _tick_clock(self):
        now = datetime.now(IST).strftime("%d %b %Y  %H:%M:%S IST")
        self.clock_label.config(text=now)
        self._update_market_status()
        self.root.after(1000, self._tick_clock)

    def _update_market_status(self):
        now = datetime.now(IST)
        is_weekday = now.weekday() < 5
        t = now.time()
        from datetime import time as dtime
        open_t  = dtime(config.MARKET_OPEN_HOUR,  config.MARKET_OPEN_MINUTE)
        close_t = dtime(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)
        open = is_weekday and open_t <= t <= close_t

        if open:
            self.market_status_dot.config(fg=C["green"])
            self.market_status_lbl.config(text="MARKET OPEN", fg=C["green"])
            self.status_dot.config(fg=C["green"])
            self.status_label.config(text="LIVE · NSE")
        else:
            self.market_status_dot.config(fg=C["red"])
            self.market_status_lbl.config(text="MARKET CLOSED", fg=C["red"])
            self.status_dot.config(fg=C["amber"])
            self.status_label.config(text="PRE/POST MARKET")

    # ── Data refresh methods ──────────────────────────────────────────────────

    def _refresh_portfolio(self):
        self.refresh_btn.set_busy(True)
        self._log_gui("Fetching portfolio data…")
        threading.Thread(target=self._fetch_portfolio, daemon=True).start()

    def _fetch_portfolio(self):
        try:
            rows = get_portfolio_pnl(config.PORTFOLIO)
            log_queue.put(("portfolio", rows))
        except Exception as e:
            log.error(f"Portfolio fetch error: {e}")
            log_queue.put(("portfolio", []))

    def _update_portfolio_ui(self, rows: list):
        self.portfolio_data = rows

        # Clear tree
        for item in self.port_tree.get_children():
            self.port_tree.delete(item)

        total_day   = 0
        total_pnl   = 0
        total_value = 0

        for r in rows:
            sym   = r["symbol"].replace(".NS", "")
            pct   = r.get("pct", 0)
            dp    = r.get("day_pnl", 0)
            tp    = r.get("total_pnl", 0)
            mv    = r.get("market_value", 0)

            total_day   += dp
            total_pnl   += tp
            total_value += mv

            tag = "up" if pct >= 0 else "dn"
            self.port_tree.insert("", "end", values=(
                sym,
                f"₹{r['price']:,.2f}",
                f"{'+'if pct>=0 else ''}{pct:.2f}%",
                r["qty"],
                f"₹{r['avg_price']:,.2f}",
                f"{'+'if dp>=0 else ''}₹{dp:,.0f}",
                f"{'+'if tp>=0 else ''}₹{tp:,.0f}",
                f"₹{mv:,.0f}",
            ), tags=(tag,))

        self.port_tree.tag_configure("up", foreground=C["green"])
        self.port_tree.tag_configure("dn", foreground=C["red"])

        # Summary cards
        day_col   = C["green"] if total_day   >= 0 else C["red"]
        total_col = C["green"] if total_pnl   >= 0 else C["red"]

        self.pnl_day_val.config(
            text=f"{'+'if total_day>=0 else ''}₹{total_day:,.0f}",
            fg=day_col)
        self.pnl_total_val.config(
            text=f"{'+'if total_pnl>=0 else ''}₹{total_pnl:,.0f}",
            fg=total_col)
        self.pnl_value_val.config(text=f"₹{total_value:,.0f}", fg=C["text"])

        now = datetime.now(IST).strftime("%H:%M:%S")
        self.last_refresh_lbl.config(text=f"Last updated {now} IST")
        self.refresh_btn.set_busy(False)
        self._log_gui(f"Portfolio refreshed — {len(rows)} holdings loaded.")

    def _refresh_indices(self):
        self._log_gui("Fetching indices + FII/DII…")
        threading.Thread(target=self._fetch_indices, daemon=True).start()

    def _fetch_indices(self):
        try:
            indices = get_indices()
            fii     = get_fii_dii_data()
            log_queue.put(("indices", (indices, fii)))
        except Exception as e:
            log.error(f"Indices fetch error: {e}")

    def _update_indices_ui(self, data):
        indices, fii = data

        for item in self.idx_tree.get_children():
            self.idx_tree.delete(item)

        for name, d in indices.items():
            tag = "up" if d["pct"] >= 0 else "dn"
            self.idx_tree.insert("", "end", values=(
                name,
                f"₹{d['price']:,.2f}",
                f"{'+'if d['change']>=0 else ''}{d['change']:,.2f}",
                f"{'+'if d['pct']>=0 else ''}{d['pct']:.2f}%",
            ), tags=(tag,))

        self.idx_tree.tag_configure("up", foreground=C["green"])
        self.idx_tree.tag_configure("dn", foreground=C["red"])

        def _inr(v):
            if abs(v) >= 1e7: return f"₹{v/1e7:.2f} Cr"
            if abs(v) >= 1e5: return f"₹{v/1e5:.2f} L"
            return f"₹{v:,.2f}"

        for key, lbl in self.fii_labels.items():
            val = fii.get(key, 0)
            col = C["green"] if val >= 0 else C["red"]
            lbl.config(text=_inr(val), fg=col)

        self._log_gui("Indices + FII/DII refreshed.")

    def _refresh_52w(self):
        self._log_gui("Running 52W analysis…")
        threading.Thread(target=self._fetch_52w, daemon=True).start()

    def _fetch_52w(self):
        try:
            data = get_52w_analysis(config.WATCHLIST, config.DANGER_ZONE_PCT)
            log_queue.put(("w52", data))
        except Exception as e:
            log.error(f"52W fetch error: {e}")

    def _update_52w_ui(self, data: list):
        for item in self.w52_tree.get_children():
            self.w52_tree.delete(item)

        for s in data:
            sym     = s["symbol"].replace(".NS", "")
            bar_len = round(s["position_pct"] / 100 * 12)
            bar     = "█" * bar_len + "░" * (12 - bar_len)
            status  = "⚠ DANGER" if s["danger"] else ("NEAR HIGH" if s["pct_from_high"] < 5 else "OK")
            tag     = "danger" if s["danger"] else ("warn" if s["pct_from_high"] < 10 else "safe")

            self.w52_tree.insert("", "end", values=(
                sym,
                f"₹{s['price']:,.2f}",
                f"₹{s['week52l']:,.2f}",
                f"₹{s['week52h']:,.2f}",
                f"{s['pct_from_low']:.1f}%",
                f"{s['pct_from_high']:.1f}%",
                bar,
                status,
            ), tags=(tag,))

        self._log_gui(f"52W analysis done — {len(data)} stocks.")

    def _refresh_earnings(self):
        self._log_gui("Fetching earnings calendar…")
        threading.Thread(target=self._fetch_earnings, daemon=True).start()

    def _fetch_earnings(self):
        try:
            data = get_earnings_calendar(config.WATCHLIST)
            log_queue.put(("earnings", data))
        except Exception as e:
            log.error(f"Earnings fetch error: {e}")

    def _update_earnings_ui(self, data: list):
        for item in self.earn_tree.get_children():
            self.earn_tree.delete(item)

        for e in data:
            sym  = e["symbol"].replace(".NS", "")
            days = e["days_out"]
            tag  = "urgent" if days <= 3 else ("soon" if days <= 7 else "ok")
            remind = "⚠ YES — SEND REMINDER" if e.get("reminder") else "—"
            self.earn_tree.insert("", "end", values=(
                sym,
                str(e["date"]),
                f"{days}d",
                remind,
            ), tags=(tag,))

        self._log_gui(f"Earnings calendar loaded — {len(data)} events.")

    # ── Manual Telegram triggers ──────────────────────────────────────────────

    def _trigger_brief(self):
        self.brief_btn.set_busy(True)
        self._log_gui("Sending morning brief to Telegram…")
        threading.Thread(target=self._do_brief, daemon=True).start()

    def _do_brief(self):
        try:
            indices    = get_indices()
            port_pnl   = get_portfolio_pnl(config.PORTFOLIO)
            fii        = get_fii_dii_data()
            news       = get_news_headlines(config.WATCHLIST, max_per_stock=2)
            earnings   = get_earnings_calendar(config.WATCHLIST)
            soon       = [e for e in earnings if e["days_out"] <= config.EARNINGS_REMINDER_DAYS]
            msg        = format_morning_brief(indices, port_pnl, fii, news, soon)
            ok         = sender.send_long(msg)
            log_queue.put(("brief_done", ok))
        except Exception as e:
            log.error(f"Brief trigger error: {e}")
            log_queue.put(("brief_done", False))

    def _trigger_52w(self):
        self.w52_btn.set_busy(True)
        self._log_gui("Sending 52W report to Telegram…")
        threading.Thread(target=self._do_52w_send, daemon=True).start()

    def _do_52w_send(self):
        try:
            data = get_52w_analysis(config.WATCHLIST, config.DANGER_ZONE_PCT)
            msg  = format_52w_report(data)
            ok   = sender.send_long(msg)
            log_queue.put(("w52_send_done", ok))
        except Exception as e:
            log.error(f"52W send error: {e}")
            log_queue.put(("w52_send_done", False))

    def _trigger_earnings(self):
        self.earn_btn.set_busy(True)
        self._log_gui("Sending earnings update to Telegram…")
        threading.Thread(target=self._do_earnings_send, daemon=True).start()

    def _do_earnings_send(self):
        try:
            data = get_earnings_calendar(config.WATCHLIST)
            msg  = format_earnings_reminder(data)
            ok   = sender.send_long(msg)
            log_queue.put(("earn_send_done", ok))
        except Exception as e:
            log.error(f"Earnings send error: {e}")
            log_queue.put(("earn_send_done", False))

    def _test_telegram(self):
        self.test_btn.set_busy(True)
        self._log_gui("Testing Telegram connection…")
        threading.Thread(target=self._do_test_telegram, daemon=True).start()

    def _do_test_telegram(self):
        ok = sender.test_connection()
        if ok:
            sender.send("🟢 *Hermes GUI* connected and running\\!", parse_mode="MarkdownV2")
        log_queue.put(("telegram_test", ok))

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log_gui(self, msg: str, level: str = "INFO"):
        now = datetime.now(IST).strftime("%H:%M:%S")
        log_queue.put(("log", f"{now} [GUI] {level} — {msg}"))

    def _append_log(self, msg: str):
        self.log_box.config(state="normal")
        # Pick colour tag based on level keyword
        tag = "INFO"
        if "ERROR"   in msg: tag = "ERROR"
        elif "WARNING" in msg: tag = "WARNING"
        elif "DEBUG"  in msg: tag = "DEBUG"
        elif "✅" in msg or "SUCCESS" in msg or "sent" in msg.lower(): tag = "SUCCESS"

        self.log_box.insert("end", msg + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

        # Keep log from growing forever
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 500:
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "50.0")
            self.log_box.config(state="disabled")

    def _append_alert_log(self, msg: str):
        self.alert_log.config(state="normal")
        self.alert_log.insert("end", msg + "\n")
        self.alert_log.see("end")
        self.alert_log.config(state="disabled")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    # ── Queue polling (bridges threads → UI) ─────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                item = log_queue.get_nowait()
                kind, data = item

                if kind == "log":
                    self._append_log(data)

                elif kind == "portfolio":
                    self._update_portfolio_ui(data)

                elif kind == "indices":
                    self._update_indices_ui(data)

                elif kind == "w52":
                    self._update_52w_ui(data)

                elif kind == "earnings":
                    self._update_earnings_ui(data)

                elif kind == "brief_done":
                    self.brief_btn.set_busy(False)
                    msg = "✅ Morning brief sent to Telegram!" if data else "❌ Brief send failed — check log."
                    self._log_gui(msg, "INFO" if data else "ERROR")

                elif kind == "w52_send_done":
                    self.w52_btn.set_busy(False)
                    self._log_gui("✅ 52W report sent!" if data else "❌ 52W send failed.")

                elif kind == "earn_send_done":
                    self.earn_btn.set_busy(False)
                    self._log_gui("✅ Earnings update sent!" if data else "❌ Earnings send failed.")

                elif kind == "telegram_test":
                    self.test_btn.set_busy(False)
                    if data:
                        self._log_gui("✅ Telegram connected successfully!")
                        messagebox.showinfo("Hermes", "Telegram connected! Check your chat for the test message.")
                    else:
                        self._log_gui("❌ Telegram connection FAILED. Check config.py.", "ERROR")
                        messagebox.showerror("Hermes", "Telegram connection failed.\nCheck BOT_TOKEN and CHAT_ID in config.py.")

                elif kind == "alert_fired":
                    sym, cond, level, price = data
                    msg = f"{datetime.now(IST).strftime('%H:%M:%S')} — {sym} {cond} ₹{level:,.2f} @ ₹{price:,.2f}"
                    self._append_alert_log(msg)

        except queue.Empty:
            pass

        if self.running:
            self.root.after(100, self._poll_queue)

    # ── Background threads ────────────────────────────────────────────────────

    def _start_background_threads(self):
        # Scheduler thread
        self._setup_schedule()
        sched_thread = threading.Thread(
            target=self._run_schedule, daemon=True, name="Scheduler")
        sched_thread.start()

        # Alert watcher thread (wraps the existing AlertWatcher)
        alert_thread = threading.Thread(
            target=self._run_alerts, daemon=True, name="AlertWatcher")
        alert_thread.start()

        # Auto-refresh portfolio every 5 minutes during market hours
        refresh_thread = threading.Thread(
            target=self._auto_refresh_loop, daemon=True, name="AutoRefresh")
        refresh_thread.start()

        log.info("All background threads started.")

    def _setup_schedule(self):
        schedule.clear()
        schedule.every().day.at(config.MORNING_BRIEF_TIME).do(self._trigger_brief)
        schedule.every().day.at(config.AFTER_MARKET_TIME).do(self._trigger_52w)

    def _run_schedule(self):
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def _run_alerts(self):
        """Run the alert watcher but route fired alerts also to the GUI."""
        _orig_poll = self.watcher.poll_once

        def _patched_poll():
            for alert in self.watcher.alerts:
                if not self.watcher._on_cooldown(alert):
                    key = self.watcher._alert_key(alert)
                    prev_key = self.watcher._prev_key(alert)
                    sym = alert["symbol"]
                    from data_fetcher import get_price
                    price = get_price(sym)
                    if price is None:
                        continue
                    prev = self.watcher.state.get(prev_key)
                    if prev is not None:
                        prev = float(prev)
                    # Check if armed in GUI
                    gui_key = f"{alert['symbol']}_{alert['condition']}_{alert['level']}"
                    var = self.alert_vars.get(gui_key)
                    if var and not var.get():
                        continue  # disarmed in GUI — skip
                    if self.watcher._crossed(alert, prev, price):
                        from formatter import format_price_alert
                        msg = format_price_alert(sym, alert["condition"], alert["level"], price)
                        sent = sender.send(msg)
                        if sent:
                            self.watcher._mark_fired(alert)
                            log_queue.put(("alert_fired", (sym, alert["condition"], alert["level"], price)))
                    self.watcher.state[prev_key] = price
            self.watcher._save_state()

        self.watcher.poll_once = _patched_poll
        self.watcher.run(self._is_market_open)

    def _is_market_open(self) -> bool:
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        t = now.time()
        from datetime import time as dtime
        return dtime(config.MARKET_OPEN_HOUR, config.MARKET_OPEN_MINUTE) <= t <= \
               dtime(config.MARKET_CLOSE_HOUR, config.MARKET_CLOSE_MINUTE)

    def _auto_refresh_loop(self):
        """Refresh portfolio data every 5 minutes during market hours."""
        while self.running:
            time.sleep(300)
            if self._is_market_open():
                log_queue.put(("log", "Auto-refreshing portfolio…"))
                try:
                    rows = get_portfolio_pnl(config.PORTFOLIO)
                    log_queue.put(("portfolio", rows))
                except Exception as e:
                    log.error(f"Auto-refresh error: {e}")

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        self.running = False
        self.root.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.title("Hermes Agent")
    try:
        root.iconbitmap("")   # suppress default icon errors on Linux
    except Exception:
        pass
    app = HermesGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
