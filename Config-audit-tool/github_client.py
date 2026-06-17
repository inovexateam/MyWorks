"""
GitHub client with strictly in-memory token handling.

Design intent (per org constraint: PAT expires every 24h):
- Token is NEVER written to disk, never logged, never put in a cookie.
- Held only in a process-local Python variable for the lifetime of the
  Flask server process. Restarting the app clears it.
- Every API call goes through `request()` so a 401/403 can be detected
  in one place and surfaced to the UI as "token expired, please re-enter"
  instead of crashing the scan.
"""

import base64
import fnmatch
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

GITHUB_API = "https://api.github.com"


class TokenExpiredError(Exception):
    """Raised when GitHub rejects the current token (401/403)."""
    pass


class RepoNotFoundError(Exception):
    pass


@dataclass
class RepoRef:
    owner: str
    repo: str
    ref: str = "main"  # branch/tag/sha
    raw_url: str = ""

    @property
    def full_name(self):
        return f"{self.owner}/{self.repo}"


def parse_github_url(url: str) -> RepoRef:
    """
    Accepts:
      https://github.com/org/repo
      https://github.com/org/repo.git
      https://github.com/org/repo/tree/branch-name
      git@github.com:org/repo.git
    """
    url = url.strip().rstrip("/")
    ref = "main"

    if url.startswith("git@github.com:"):
        path = url.split("git@github.com:", 1)[1]
        path = path[:-4] if path.endswith(".git") else path
        owner, repo = path.split("/", 1)
        return RepoRef(owner=owner, repo=repo, ref=ref, raw_url=url)

    m = re.search(r"github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?/?$", url)
    if not m:
        raise ValueError(f"Could not parse GitHub URL: {url}")
    owner, repo, branch = m.group(1), m.group(2), m.group(3)
    if branch:
        ref = branch
    return RepoRef(owner=owner, repo=repo, ref=ref, raw_url=url)


class GitHubSession:
    """
    Holds the PAT in memory only. One instance lives for the Flask
    process's lifetime; `set_token` / `clear_token` let the UI refresh
    it without restarting the server.
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._username: Optional[str] = None
        self._set_at: Optional[float] = None

    def set_token(self, token: str):
        self._token = token.strip()
        self._set_at = time.time()
        self._username = None  # re-validate on next check

    def clear_token(self):
        self._token = None
        self._username = None
        self._set_at = None

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    @property
    def age_seconds(self) -> float:
        return time.time() - self._set_at if self._set_at else 0

    def _headers(self):
        if not self._token:
            raise TokenExpiredError("No token set.")
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def validate(self) -> dict:
        """Calls /user to confirm the token works. Raises TokenExpiredError if not."""
        resp = requests.get(f"{GITHUB_API}/user", headers=self._headers(), timeout=15)
        if resp.status_code in (401, 403):
            raise TokenExpiredError("GitHub rejected the token (expired or insufficient scope).")
        resp.raise_for_status()
        data = resp.json()
        self._username = data.get("login")
        return data

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{GITHUB_API}{path}"
        resp = requests.request(method, url, headers=self._headers(), timeout=30, **kwargs)
        if resp.status_code in (401, 403):
            # 403 can also be rate-limit; distinguish via message
            body = resp.text.lower()
            if resp.status_code == 401 or "bad credentials" in body or "expired" in body:
                raise TokenExpiredError("GitHub token expired or invalid. Please re-enter your PAT.")
        return resp

    def get_default_branch(self, ref: RepoRef) -> str:
        resp = self.request("GET", f"/repos/{ref.owner}/{ref.repo}")
        if resp.status_code == 404:
            raise RepoNotFoundError(f"Repo not found or no access: {ref.full_name}")
        resp.raise_for_status()
        return resp.json().get("default_branch", "main")

    def get_tree(self, ref: RepoRef) -> list[dict]:
        """Full recursive file tree for the repo at ref.ref."""
        resp = self.request(
            "GET", f"/repos/{ref.owner}/{ref.repo}/git/trees/{ref.ref}", params={"recursive": "1"}
        )
        if resp.status_code == 404:
            raise RepoNotFoundError(
                f"Branch/ref '{ref.ref}' not found in {ref.full_name}"
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("truncated"):
            pass  # noted in UI layer; large monorepos may need path-scoped calls
        return [item for item in data.get("tree", []) if item["type"] == "blob"]

    def get_file_content(self, ref: RepoRef, path: str) -> str:
        resp = self.request(
            "GET", f"/repos/{ref.owner}/{ref.repo}/contents/{path}", params={"ref": ref.ref}
        )
        if resp.status_code == 404:
            raise RepoNotFoundError(f"File not found: {path} in {ref.full_name}")
        resp.raise_for_status()
        data = resp.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data.get("content", "")


# Module-level singleton — the one in-memory token holder for this process.
session = GitHubSession()


RELEVANT_EXTENSIONS = (
    ".yaml", ".yml", ".java", ".cs", ".cshtml", ".properties",
    ".json", ".tpl", ".gotmpl", ".config",
)


def filter_relevant_files(tree_items: list[dict], extra_globs: Optional[list[str]] = None) -> list[str]:
    paths = [item["path"] for item in tree_items]
    out = [p for p in paths if p.lower().endswith(RELEVANT_EXTENSIONS)]
    if extra_globs:
        for g in extra_globs:
            out += [p for p in paths if fnmatch.fnmatch(p, g) and p not in out]
    return out
