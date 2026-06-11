"""
JIRA API client - handles authentication and data fetching for sprint analytics.
Supports JIRA Cloud (PAT/API token via Basic Auth) and JIRA Server/DC (Bearer PAT).
"""
import os
import requests
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IssueRecord:
    key: str
    summary: str
    story_points: float
    status: str
    status_category: str  # "To Do", "In Progress", "Done"
    assignee: str
    issue_type: str
    resolved_date: Optional[datetime] = None
    changelog: list = field(default_factory=list)


class JiraClient:
    def __init__(self, base_url: str = None, email: str = None, pat: str = None):
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")).rstrip("/")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.pat = pat or os.environ.get("JIRA_PAT", "")
        if not self.base_url or not self.pat:
            raise ValueError("JIRA_BASE_URL and JIRA_PAT must be provided (env or constructor).")
        self.session = requests.Session()
        self._configure_auth()

    def _configure_auth(self):
        """JIRA Cloud uses Basic Auth (email + API token).
        JIRA Server/Data Center uses Bearer token (PAT)."""
        if self.email:
            self.session.auth = (self.email, self.pat)
        else:
            self.session.headers.update({"Authorization": f"Bearer {self.pat}"})
        self.session.headers.update({"Accept": "application/json"})

    def test_connection(self) -> dict:
        r = self.session.get(f"{self.base_url}/rest/api/2/myself", timeout=15)
        r.raise_for_status()
        return r.json()

    # ---------------- Boards / Sprints ----------------

    def get_active_sprint(self, board_id: int) -> Optional[dict]:
        url = f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint"
        r = self.session.get(url, params={"state": "active"}, timeout=15)
        r.raise_for_status()
        values = r.json().get("values", [])
        return values[0] if values else None

    def get_sprint_report(self, board_id: int, sprint_id: int) -> dict:
        """Greenhopper sprint report - gives committed/completed points
        and the official burndown 'changes' data."""
        url = f"{self.base_url}/rest/greenhopper/1.0/rapid/charts/sprintreport"
        r = self.session.get(url, params={"rapidViewId": board_id, "sprintId": sprint_id}, timeout=20)
        r.raise_for_status()
        return r.json()

    # ---------------- Issues ----------------

    def get_sprint_issues(self, board_id: int, sprint_id: int,
                           story_point_field: str = "customfield_10016") -> list[IssueRecord]:
        """Fetch all issues in a sprint with story points, assignee, status, changelog."""
        issues = []
        start_at = 0
        max_results = 50
        while True:
            url = f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}/issue"
            params = {
                "startAt": start_at,
                "maxResults": max_results,
                "fields": f"summary,status,assignee,issuetype,resolutiondate,{story_point_field}",
                "expand": "changelog",
            }
            r = self.session.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            for issue in data.get("issues", []):
                fields = issue["fields"]
                sp = fields.get(story_point_field) or 0
                resolved = fields.get("resolutiondate")
                resolved_dt = None
                if resolved:
                    resolved_dt = datetime.strptime(resolved[:19], "%Y-%m-%dT%H:%M:%S")

                changelog = self._extract_status_changes(issue.get("changelog", {}))

                issues.append(IssueRecord(
                    key=issue["key"],
                    summary=fields.get("summary", ""),
                    story_points=float(sp) if sp else 0.0,
                    status=fields["status"]["name"],
                    status_category=fields["status"]["statusCategory"]["name"],
                    assignee=(fields.get("assignee") or {}).get("displayName", "Unassigned"),
                    issue_type=fields["issuetype"]["name"],
                    resolved_date=resolved_dt,
                    changelog=changelog,
                ))

            start_at += max_results
            if start_at >= data.get("total", 0):
                break
        return issues

    @staticmethod
    def _extract_status_changes(changelog: dict) -> list[dict]:
        """Extract (timestamp, from_status, to_status) transitions from changelog histories."""
        changes = []
        for history in changelog.get("histories", []):
            created = history["created"][:19]
            ts = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S")
            for item in history["items"]:
                if item["field"] == "status":
                    changes.append({
                        "timestamp": ts,
                        "from": item["fromString"],
                        "to": item["toString"],
                    })
        return changes
