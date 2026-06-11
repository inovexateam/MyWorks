"""
GitHub API fetcher.
Pulls all open PRs for a repo, their file diffs, and metadata.
Uses the GitHub REST API with a personal access token.

Authentication: set GITHUB_TOKEN environment variable.
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional
from core.models import PRSnapshot, FileChange


GITHUB_API = "https://api.github.com"
MAX_PRS    = 50    # cap — most repos have fewer open PRs than this
MAX_FILES  = 100   # GitHub caps at 300 files per PR in the API


class GitHubClient:
    def __init__(self, token: str, repo: str):
        """
        token: GitHub personal access token (needs repo scope)
        repo:  'owner/repo-name'
        """
        self.token = token
        self.repo  = repo
        self._rate_remaining = 5000

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{GITHUB_API}{path}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += "?" + query

        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "cross-pr-intelligence/1.0")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                self._rate_remaining = int(resp.headers.get("X-RateLimit-Remaining", 5000))
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"GitHub API {e.code}: {path} — {body[:200]}")

    def _get_diff(self, pr_number: int) -> str:
        """Fetch raw unified diff for a PR."""
        url = f"{GITHUB_API}/repos/{self.repo}/pulls/{pr_number}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github.diff")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "cross-pr-intelligence/1.0")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode(errors='ignore')
        except Exception:
            return ""

    def list_open_prs(self) -> list[dict]:
        """Return all open PRs (including drafts)."""
        prs = []
        page = 1
        while len(prs) < MAX_PRS:
            batch = self._get(
                f"/repos/{self.repo}/pulls",
                {"state": "open", "per_page": "50", "page": str(page)}
            )
            if not batch:
                break
            prs.extend(batch)
            if len(batch) < 50:
                break
            page += 1
            time.sleep(0.1)   # be polite to the rate limiter
        return prs[:MAX_PRS]

    def get_pr_files(self, pr_number: int) -> list[dict]:
        """Return list of changed files for a PR."""
        try:
            return self._get(f"/repos/{self.repo}/pulls/{pr_number}/files",
                             {"per_page": str(MAX_FILES)})
        except Exception:
            return []

    def fetch_all_open_prs(self, verbose: bool = False) -> list[PRSnapshot]:
        """
        Full pipeline: fetch all open PRs, their files, and diffs.
        Returns a list of PRSnapshot objects ready for overlap analysis.
        """
        raw_prs = self.list_open_prs()
        if verbose:
            print(f"  Found {len(raw_prs)} open PRs")

        snapshots = []
        for raw in raw_prs:
            pr_number = raw["number"]
            if verbose:
                print(f"  Fetching PR #{pr_number}: {raw['title'][:50]}", end="\r", flush=True)

            # File list
            raw_files = self.get_pr_files(pr_number)
            changed_files = [_parse_file(f) for f in raw_files]

            # Raw diff (for line-range extraction)
            raw_diff = self._get_diff(pr_number)

            # Enrich file changes with line ranges from diff
            _enrich_line_ranges(changed_files, raw_diff)

            snapshot = PRSnapshot(
                number=pr_number,
                title=raw.get("title", ""),
                author=raw.get("user", {}).get("login", "unknown"),
                branch=raw.get("head", {}).get("ref", ""),
                base_branch=raw.get("base", {}).get("ref", "main"),
                url=raw.get("html_url", ""),
                state="draft" if raw.get("draft") else "open",
                created_at=raw.get("created_at", ""),
                updated_at=raw.get("updated_at", ""),
                changed_files=changed_files,
                raw_diff=raw_diff,
            )
            snapshots.append(snapshot)

            if self._rate_remaining < 10:
                if verbose:
                    print(f"\n  Rate limit low ({self._rate_remaining}) — pausing 60s")
                time.sleep(60)
            else:
                time.sleep(0.05)

        if verbose:
            print(f"\n  Fetched {len(snapshots)} PR snapshots")
        return snapshots


def _parse_file(raw: dict) -> FileChange:
    return FileChange(
        path=raw.get("filename", ""),
        status=raw.get("status", "modified"),
        additions=raw.get("additions", 0),
        deletions=raw.get("deletions", 0),
        old_path=raw.get("previous_filename", ""),
    )


# ── Line-range extraction from unified diff ───────────────────────────────────

HUNK_HEADER = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
FILE_HEADER  = re.compile(r'^(?:\+\+\+|---) [ab]/(.+)$')


def _enrich_line_ranges(files: list[FileChange], raw_diff: str):
    """
    Parse the unified diff and attach (start_line, end_line) tuples
    to each FileChange for the *new* (post-merge) line numbers.
    """
    file_map = {f.path: f for f in files}
    current_file: Optional[FileChange] = None
    current_start = 0
    current_end   = 0
    in_hunk       = False

    for line in raw_diff.split('\n'):
        # File header
        m = FILE_HEADER.match(line)
        if m and line.startswith('+++'):
            path = m.group(1)
            current_file = file_map.get(path)
            in_hunk = False
            continue

        if current_file is None:
            continue

        # Hunk header
        m = HUNK_HEADER.match(line)
        if m:
            if in_hunk and current_start > 0:
                current_file.changed_lines.append((current_start, current_end))
            new_start = int(m.group(3))
            new_count = int(m.group(4)) if m.group(4) else 1
            current_start = new_start
            current_end   = new_start + new_count - 1
            in_hunk = True
            continue

        # Accumulate contiguous added/changed lines
        if in_hunk and line.startswith('+') and not line.startswith('+++'):
            current_end = max(current_end, current_start)

    # Flush last hunk
    if current_file and in_hunk and current_start > 0:
        current_file.changed_lines.append((current_start, current_end))


def get_token_and_repo() -> tuple[str, str]:
    """Read token and repo from environment."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo  = os.environ.get("GITHUB_REPO", "")
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN not set. Export it before running:\n"
            "  export GITHUB_TOKEN=ghp_..."
        )
    if not repo:
        raise EnvironmentError(
            "GITHUB_REPO not set. Export it before running:\n"
            "  export GITHUB_REPO=owner/repo-name"
        )
    return token, repo
