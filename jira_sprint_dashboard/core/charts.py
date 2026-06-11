"""
Chart generation using matplotlib (dark theme for terminal/dashboard aesthetic,
also exports clean light versions for email/PDF reports).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from datetime import datetime

DARK_BG = "#0d1117"
DARK_PANEL = "#161b22"
DARK_GRID = "#30363d"
ACCENT_IDEAL = "#58a6ff"
ACCENT_ACTUAL = "#f78166"
TEXT_COLOR = "#c9d1d9"

PALETTE = ["#58a6ff", "#3fb950", "#f78166", "#d29922", "#a371f7",
           "#f85149", "#39c5cf", "#ff7b72", "#79c0ff", "#56d364"]


def _style_dark_axes(ax, title: str):
    ax.set_facecolor(DARK_PANEL)
    ax.figure.set_facecolor(DARK_BG)
    ax.title.set_color(TEXT_COLOR)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(DARK_GRID)
    ax.grid(True, color=DARK_GRID, linestyle="--", linewidth=0.5, alpha=0.7)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)


def plot_burndown(days: list[datetime], ideal: list[float], actual: list[float],
                   sprint_name: str, dark: bool = True) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(9, 5), dpi=100)
    dates = [d.date() for d in days]

    ax.plot(dates, ideal, label="Ideal Burndown", color=ACCENT_IDEAL,
            linestyle="--", linewidth=2, marker="o", markersize=3)
    ax.plot(dates, actual, label="Actual Burndown", color=ACCENT_ACTUAL,
            linewidth=2.5, marker="o", markersize=4)

    ax.fill_between(dates, actual, ideal, where=[a > i for a, i in zip(actual, ideal)],
                     color=ACCENT_ACTUAL, alpha=0.15, interpolate=True, label="Behind schedule")
    ax.fill_between(dates, actual, ideal, where=[a <= i for a, i in zip(actual, ideal)],
                     color="#3fb950", alpha=0.15, interpolate=True, label="Ahead/On track")

    ax.set_ylabel("Remaining Story Points")
    ax.set_xlabel("Sprint Day")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate(rotation=30)

    if dark:
        _style_dark_axes(ax, f"Sprint Burndown — {sprint_name}")
        legend = ax.legend(facecolor=DARK_PANEL, edgecolor=DARK_GRID, labelcolor=TEXT_COLOR)
    else:
        ax.set_title(f"Sprint Burndown — {sprint_name}", fontsize=13, fontweight="bold")
        ax.grid(True, linestyle="--", alpha=0.5)
        legend = ax.legend()

    fig.tight_layout()
    return fig


def plot_daily_churn(df: pd.DataFrame, sprint_name: str, dark: bool = True) -> plt.Figure:
    """Stacked bar chart: story points completed per day, by assignee."""
    fig, ax = plt.subplots(figsize=(9, 5), dpi=100)

    if df.empty or df.sum().sum() == 0:
        ax.text(0.5, 0.5, "No completed work yet", ha="center", va="center",
                color=TEXT_COLOR if dark else "black", fontsize=12)
    else:
        df.plot(kind="bar", stacked=True, ax=ax,
                color=PALETTE[:len(df.columns)], width=0.6, edgecolor="none")

    ax.set_ylabel("Story Points Completed")
    ax.set_xlabel("Date")
    ax.set_xticklabels([str(d) for d in df.index], rotation=30, ha="right")

    if dark:
        _style_dark_axes(ax, f"Daily Completed Points by Teammate — {sprint_name}")
        if not df.empty and df.sum().sum() > 0:
            legend = ax.legend(title="Assignee", facecolor=DARK_PANEL, edgecolor=DARK_GRID,
                                labelcolor=TEXT_COLOR, fontsize=8, title_fontsize=9)
            legend.get_title().set_color(TEXT_COLOR)
    else:
        ax.set_title(f"Daily Completed Points by Teammate — {sprint_name}", fontsize=13, fontweight="bold")
        if not df.empty and df.sum().sum() > 0:
            ax.legend(title="Assignee", fontsize=8)

    fig.tight_layout()
    return fig


def plot_assignee_summary(summary_df: pd.DataFrame, sprint_name: str, dark: bool = True) -> plt.Figure:
    """Horizontal stacked bar: Done / In Progress / To Do per assignee."""
    fig, ax = plt.subplots(figsize=(9, max(4, 0.5 * len(summary_df) + 1)), dpi=100)

    y = summary_df["Assignee"]
    done = summary_df["Done (SP)"]
    inprog = summary_df["In Progress (SP)"]
    todo = summary_df["To Do (SP)"]

    ax.barh(y, done, color="#3fb950", label="Done")
    ax.barh(y, inprog, left=done, color="#d29922", label="In Progress")
    ax.barh(y, todo, left=done + inprog, color="#30363d" if dark else "#cccccc", label="To Do")

    ax.set_xlabel("Story Points")
    ax.invert_yaxis()

    if dark:
        _style_dark_axes(ax, f"Workload Breakdown — {sprint_name}")
        legend = ax.legend(facecolor=DARK_PANEL, edgecolor=DARK_GRID, labelcolor=TEXT_COLOR)
    else:
        ax.set_title(f"Workload Breakdown — {sprint_name}", fontsize=13, fontweight="bold")
        ax.legend()

    fig.tight_layout()
    return fig


def save_fig(fig: plt.Figure, path: str):
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
