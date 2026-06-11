"""
JIRA Sprint Dashboard - Tkinter GUI

Dark "terminal" aesthetic. Shows:
 - Sprint burndown chart (ideal vs actual)
 - Daily completed points by teammate (stacked bars)
 - Workload breakdown per assignee (Done/In Progress/To Do)
 - Sprint health summary + scope-change alerts
 - Connection setup (PAT via env or manual entry)
 - Manual "Send Email Now" trigger
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from dotenv import load_dotenv

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.jira_client import JiraClient
from core import report
from core.emailer import send_sprint_report_email

load_dotenv()

BG = "#0d1117"
PANEL = "#161b22"
ACCENT = "#58a6ff"
TEXT = "#c9d1d9"
GREEN = "#3fb950"
RED = "#f85149"
AMBER = "#d29922"


class SprintDashboardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JIRA Sprint Dashboard")
        self.geometry("1200x800")
        self.configure(bg=BG)

        self.client = None
        self.report_data = None
        self.chart_paths = {}

        self._build_style()
        self._build_layout()
        self._try_autoload_connection()

    # ---------------- UI Setup ----------------

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=BG, foreground=ACCENT, font=("Segoe UI", 14, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT)
        style.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL,
                         rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#21262d", foreground=ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#21262d", foreground=TEXT, padding=[12, 6])
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", ACCENT)])

    def _build_layout(self):
        # Top connection bar
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="JIRA Sprint Dashboard", style="Header.TLabel").pack(side="left")

        conn_frame = ttk.Frame(top)
        conn_frame.pack(side="right")

        ttk.Label(conn_frame, text="Base URL:").grid(row=0, column=0, padx=4)
        self.url_var = tk.StringVar(value=os.environ.get("JIRA_BASE_URL", ""))
        ttk.Entry(conn_frame, textvariable=self.url_var, width=28).grid(row=0, column=1, padx=4)

        ttk.Label(conn_frame, text="Email:").grid(row=0, column=2, padx=4)
        self.email_var = tk.StringVar(value=os.environ.get("JIRA_EMAIL", ""))
        ttk.Entry(conn_frame, textvariable=self.email_var, width=18).grid(row=0, column=3, padx=4)

        ttk.Label(conn_frame, text="PAT:").grid(row=0, column=4, padx=4)
        self.pat_var = tk.StringVar(value=os.environ.get("JIRA_PAT", ""))
        ttk.Entry(conn_frame, textvariable=self.pat_var, width=18, show="•").grid(row=0, column=5, padx=4)

        ttk.Label(conn_frame, text="Board ID:").grid(row=0, column=6, padx=4)
        self.board_var = tk.StringVar(value=os.environ.get("JIRA_BOARD_ID", ""))
        ttk.Entry(conn_frame, textvariable=self.board_var, width=8).grid(row=0, column=7, padx=4)

        self.connect_btn = ttk.Button(conn_frame, text="Connect & Load", command=self.on_load)
        self.connect_btn.grid(row=0, column=8, padx=8)

        self.email_btn = ttk.Button(conn_frame, text="Send Email Now", command=self.on_send_email, state="disabled")
        self.email_btn.grid(row=0, column=9, padx=4)

        # Status bar
        self.status_var = tk.StringVar(value="Not connected.")
        ttk.Label(self, textvariable=self.status_var, foreground=AMBER).pack(anchor="w", padx=12)

        # Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_overview = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.tab_burndown = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.tab_churn = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.tab_workload = ttk.Frame(self.notebook, style="Panel.TFrame")

        self.notebook.add(self.tab_overview, text="Overview")
        self.notebook.add(self.tab_burndown, text="Burndown")
        self.notebook.add(self.tab_churn, text="Daily Churn")
        self.notebook.add(self.tab_workload, text="Workload")

        self._build_overview_tab()

    def _build_overview_tab(self):
        frame = self.tab_overview

        self.health_label = ttk.Label(frame, text="Connect to JIRA to load sprint data.",
                                       font=("Segoe UI", 12, "bold"), background=PANEL, foreground=TEXT)
        self.health_label.pack(anchor="w", padx=16, pady=(16, 8))

        self.scope_label = ttk.Label(frame, text="", background=PANEL, foreground=AMBER, justify="left")
        self.scope_label.pack(anchor="w", padx=16, pady=(0, 8))

        # Summary table
        cols = ("Assignee", "Committed (SP)", "Done (SP)", "In Progress (SP)", "To Do (SP)", "% Complete")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor="center", width=130)
        self.tree.pack(fill="both", expand=True, padx=16, pady=8)

    # ---------------- Logic ----------------

    def _try_autoload_connection(self):
        if os.environ.get("JIRA_BASE_URL") and os.environ.get("JIRA_PAT") and os.environ.get("JIRA_BOARD_ID"):
            self.status_var.set("Found credentials in environment. Click 'Connect & Load' to fetch sprint.")

    def on_load(self):
        self.connect_btn.config(state="disabled")
        self.status_var.set("Connecting and fetching sprint data...")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            base_url = self.url_var.get().strip()
            email = self.email_var.get().strip()
            pat = self.pat_var.get().strip()
            board_id = int(self.board_var.get().strip())

            self.client = JiraClient(base_url=base_url, email=email, pat=pat)
            self.client.test_connection()

            sp_field = os.environ.get("JIRA_STORY_POINTS_FIELD", "customfield_10016")
            self.report_data = report.fetch_and_compute(board_id, sp_field, self.client)

            out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "_cache")
            self.chart_paths = report.generate_charts(self.report_data, out_dir, dark=True)

            self.after(0, self._render_results)
        except Exception as e:
            self.after(0, lambda: self._on_error(e))

    def _on_error(self, e):
        self.status_var.set(f"Error: {e}")
        messagebox.showerror("Connection / Fetch Error", str(e))
        self.connect_btn.config(state="normal")

    def _render_results(self):
        data = self.report_data
        self.status_var.set(f"Loaded sprint: {data.sprint['name']} | Total points: {data.total_points}")
        self.connect_btn.config(state="normal")
        self.email_btn.config(state="normal")

        # Health
        status = data.health["status"]
        color = {"On Track / Ahead": GREEN, "Slightly Behind": AMBER, "At Risk": RED}.get(status, TEXT)
        self.health_label.config(
            text=(f"Sprint: {data.sprint['name']}   |   Status: {status}   |   "
                  f"Remaining: {data.health['remaining_actual']} (Ideal: {data.health['remaining_ideal']})"),
            foreground=color)

        if data.scope_changes:
            names = ", ".join(c["key"] for c in data.scope_changes[:8])
            self.scope_label.config(text=f"⚠ Possible scope changes detected on: {names}")
        else:
            self.scope_label.config(text="No scope changes detected.")

        # Table
        for row in self.tree.get_children():
            self.tree.delete(row)
        for _, r in data.summary_df.iterrows():
            self.tree.insert("", "end", values=(
                r["Assignee"], r["Committed (SP)"], r["Done (SP)"],
                r["In Progress (SP)"], r["To Do (SP)"], f"{r['% Complete']}%"
            ))

        # Charts
        self._render_chart(self.tab_burndown, self.chart_paths["Burndown Chart"])
        self._render_chart(self.tab_churn, self.chart_paths["Daily Completed Points by Teammate"])
        self._render_chart(self.tab_workload, self.chart_paths["Workload Breakdown"])

    def _render_chart(self, tab, image_path):
        for widget in tab.winfo_children():
            widget.destroy()

        from PIL import Image, ImageTk
        img = Image.open(image_path)
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(tab, image=photo, bg=PANEL)
        label.image = photo
        label.pack(fill="both", expand=True, padx=10, pady=10)

    def on_send_email(self):
        if not self.report_data:
            return
        self.email_btn.config(state="disabled")
        self.status_var.set("Sending email...")
        threading.Thread(target=self._send_email_worker, daemon=True).start()

    def _send_email_worker(self):
        try:
            html = report.summary_html_table(self.report_data)
            send_sprint_report_email(self.chart_paths, html, self.report_data.sprint["name"])
            self.after(0, lambda: self.status_var.set("Email sent successfully."))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Email Error", str(e)))
            self.after(0, lambda: self.status_var.set("Email failed."))
        finally:
            self.after(0, lambda: self.email_btn.config(state="normal"))


if __name__ == "__main__":
    app = SprintDashboardApp()
    app.mainloop()
