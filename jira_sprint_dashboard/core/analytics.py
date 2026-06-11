"""
Burndown & churn analytics computed from sprint issues + changelog.

Key outputs:
 - Ideal burndown line (linear from total points to 0 over sprint days)
 - Actual burndown (remaining points per day, derived from "Done" transitions)
 - Per-person daily completed points ("churn") - a stacked breakdown
 - Scope change tracking (points added/removed mid-sprint)
 - Per-assignee summary (committed vs completed vs in-progress vs todo)
"""
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd

from core.jira_client import IssueRecord


DONE_CATEGORY = "Done"


def build_date_range(start: datetime, end: datetime) -> list[datetime]:
    days = []
    d = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_d = end.replace(hour=0, minute=0, second=0, microsecond=0)
    while d <= end_d:
        days.append(d)
        d += timedelta(days=1)
    return days


def compute_ideal_burndown(total_points: float, days: list[datetime]) -> list[float]:
    n = len(days) - 1
    if n <= 0:
        return [total_points]
    step = total_points / n
    return [round(total_points - step * i, 2) for i in range(len(days))]


def compute_actual_burndown(issues: list[IssueRecord], days: list[datetime], total_points: float) -> list[float]:
    """Remaining points at end-of-day for each day, based on resolution dates."""
    remaining = []
    for day in days:
        eod = day + timedelta(days=1)
        completed = sum(
            i.story_points for i in issues
            if i.resolved_date and i.resolved_date < eod
        )
        remaining.append(round(total_points - completed, 2))
    return remaining


def compute_daily_churn_by_assignee(issues: list[IssueRecord], days: list[datetime]) -> pd.DataFrame:
    """Story points completed per day, broken down by assignee.
    Returns DataFrame indexed by date, columns = assignees, values = points completed that day."""
    assignees = sorted(set(i.assignee for i in issues))
    data = defaultdict(lambda: defaultdict(float))

    for issue in issues:
        if issue.resolved_date and issue.story_points:
            day_key = issue.resolved_date.replace(hour=0, minute=0, second=0, microsecond=0)
            data[day_key][issue.assignee] += issue.story_points

    rows = []
    for day in days:
        row = {"date": day.date()}
        for a in assignees:
            row[a] = data.get(day, {}).get(a, 0.0)
        rows.append(row)

    df = pd.DataFrame(rows).set_index("date")
    return df


def compute_scope_changes(issues: list[IssueRecord], sprint_start: datetime) -> list[dict]:
    """Detect issues added to sprint after start (scope creep) via changelog 'Sprint' field changes
    is not directly available without extra calls; as a proxy, flag issues with no early status history
    before sprint_start (best-effort heuristic)."""
    changes = []
    for issue in issues:
        first_change = min((c["timestamp"] for c in issue.changelog), default=None)
        if first_change and first_change > sprint_start + timedelta(hours=12):
            changes.append({
                "key": issue.key,
                "summary": issue.summary,
                "story_points": issue.story_points,
                "first_activity": first_change,
            })
    return changes


def compute_assignee_summary(issues: list[IssueRecord]) -> pd.DataFrame:
    rows = []
    for assignee in sorted(set(i.assignee for i in issues)):
        sub = [i for i in issues if i.assignee == assignee]
        committed = sum(i.story_points for i in sub)
        done = sum(i.story_points for i in sub if i.status_category == DONE_CATEGORY)
        in_progress = sum(i.story_points for i in sub if i.status_category == "In Progress")
        todo = committed - done - in_progress
        rows.append({
            "Assignee": assignee,
            "Committed (SP)": committed,
            "Done (SP)": done,
            "In Progress (SP)": in_progress,
            "To Do (SP)": max(todo, 0),
            "Issues": len(sub),
            "% Complete": round(100 * done / committed, 1) if committed else 0.0,
        })
    df = pd.DataFrame(rows).sort_values("Committed (SP)", ascending=False)
    return df


def compute_sprint_health(ideal: list[float], actual: list[float], today_idx: int) -> dict:
    """Quick health signal comparing actual vs ideal remaining points at 'today'."""
    if today_idx >= len(actual):
        today_idx = len(actual) - 1
    diff = actual[today_idx] - ideal[today_idx]
    if diff <= 0:
        status = "On Track / Ahead"
    elif diff <= ideal[0] * 0.1:
        status = "Slightly Behind"
    else:
        status = "At Risk"
    return {
        "remaining_actual": actual[today_idx],
        "remaining_ideal": ideal[today_idx],
        "diff": round(diff, 2),
        "status": status,
    }
