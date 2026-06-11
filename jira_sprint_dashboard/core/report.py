"""
Report orchestrator: pulls JIRA data, computes analytics, generates charts,
and optionally emails the report. Used by both the GUI app and the scheduler.
"""
import os
from datetime import datetime
import pandas as pd

from core.jira_client import JiraClient
from core import analytics, charts


class SprintReportData:
    """Holds all computed data for a single sprint, ready for rendering."""
    def __init__(self):
        self.sprint = None
        self.issues = []
        self.days = []
        self.ideal = []
        self.actual = []
        self.churn_df = pd.DataFrame()
        self.summary_df = pd.DataFrame()
        self.scope_changes = []
        self.health = {}
        self.total_points = 0.0


def fetch_and_compute(board_id: int, story_point_field: str = "customfield_10016",
                       client: JiraClient = None) -> SprintReportData:
    client = client or JiraClient()
    data = SprintReportData()

    sprint = client.get_active_sprint(board_id)
    if not sprint:
        raise RuntimeError("No active sprint found for this board.")
    data.sprint = sprint

    issues = client.get_sprint_issues(board_id, sprint["id"], story_point_field)
    data.issues = issues
    data.total_points = sum(i.story_points for i in issues)

    start = datetime.strptime(sprint["startDate"][:19], "%Y-%m-%dT%H:%M:%S")
    end = datetime.strptime(sprint["endDate"][:19], "%Y-%m-%dT%H:%M:%S")
    data.days = analytics.build_date_range(start, end)

    data.ideal = analytics.compute_ideal_burndown(data.total_points, data.days)
    data.actual = analytics.compute_actual_burndown(issues, data.days, data.total_points)
    data.churn_df = analytics.compute_daily_churn_by_assignee(issues, data.days)
    data.summary_df = analytics.compute_assignee_summary(issues)
    data.scope_changes = analytics.compute_scope_changes(issues, start)

    today_idx = max(0, min((datetime.now() - start).days, len(data.days) - 1))
    data.health = analytics.compute_sprint_health(data.ideal, data.actual, today_idx)

    return data


def generate_charts(data: SprintReportData, output_dir: str, dark: bool = True) -> dict:
    os.makedirs(output_dir, exist_ok=True)
    paths = {}

    fig = charts.plot_burndown(data.days, data.ideal, data.actual, data.sprint["name"], dark)
    p = os.path.join(output_dir, "burndown.png")
    charts.save_fig(fig, p)
    paths["Burndown Chart"] = p

    fig = charts.plot_daily_churn(data.churn_df, data.sprint["name"], dark)
    p = os.path.join(output_dir, "daily_churn.png")
    charts.save_fig(fig, p)
    paths["Daily Completed Points by Teammate"] = p

    fig = charts.plot_assignee_summary(data.summary_df, data.sprint["name"], dark)
    p = os.path.join(output_dir, "assignee_summary.png")
    charts.save_fig(fig, p)
    paths["Workload Breakdown"] = p

    return paths


def summary_html_table(data: SprintReportData) -> str:
    health_color = {"On Track / Ahead": "#3fb950", "Slightly Behind": "#d29922", "At Risk": "#f85149"}
    color = health_color.get(data.health["status"], "#888")

    rows = "".join(
        f"<tr><td>{r['Assignee']}</td><td>{r['Committed (SP)']}</td>"
        f"<td>{r['Done (SP)']}</td><td>{r['In Progress (SP)']}</td>"
        f"<td>{r['To Do (SP)']}</td><td>{r['% Complete']}%</td></tr>"
        for _, r in data.summary_df.iterrows()
    )

    table_style = "border-collapse:collapse;width:100%;font-size:13px;"
    cell_style = "border:1px solid #ddd;padding:6px 10px;text-align:center;"

    return f"""
    <p><b>Sprint:</b> {data.sprint['name']} &nbsp; | &nbsp;
       <b>Total Points:</b> {data.total_points} &nbsp; | &nbsp;
       <b>Status:</b> <span style="color:{color};font-weight:bold;">{data.health['status']}</span>
       (Remaining: {data.health['remaining_actual']} vs Ideal: {data.health['remaining_ideal']})</p>
    <table style="{table_style}">
      <tr style="background:#f0f0f0;">
        <th style="{cell_style}">Assignee</th><th style="{cell_style}">Committed</th>
        <th style="{cell_style}">Done</th><th style="{cell_style}">In Progress</th>
        <th style="{cell_style}">To Do</th><th style="{cell_style}">% Complete</th>
      </tr>
      {rows}
    </table>
    """
