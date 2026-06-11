"""
Git history miner — Layer 1.
Three independent data sources, all from git:

1. Commit log:  who changed which files, when, how many lines
2. Blame:       who owns which lines RIGHT NOW (current state)
3. Co-change:   which files are always changed together (hidden coupling)

All three are needed. Commit log alone misses current ownership (someone
may have rewritten code they never originally wrote). Blame alone misses
historical context. Co-change reveals hidden dependencies no tool else sees.
"""

import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from core.models import Developer, Module, ModuleExpertise

SKIP_DIRS = {'.git', 'node_modules', 'bin', 'obj', 'dist', '.angular', 'build', 'target', 'coverage'}
SUPPORTED_EXT = {'.cs', '.java', '.ts', '.tsx', '.py', '.js', '.go', '.rb', '.php', '.cpp', '.h'}
ACTIVE_DAYS_THRESHOLD = 180    # developer is "active" if committed in last 6 months


def _git(args: list[str], repo_path: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            ['git'] + args, cwd=repo_path,
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout
    except Exception:
        return ""


# ── 1. Commit log ─────────────────────────────────────────────────────────────

COMMIT_LOG_FORMAT = "%H|%ae|%an|%ad|%s"

def fetch_commit_log(repo_path: str, max_commits: int = 5000) -> list[dict]:
    """
    Returns list of {sha, author_email, author_name, date, subject, files}.
    Uses a separator-based format so header lines are unambiguous.
    """
    SEP = "---COMMIT---"
    raw = _git([
        'log', f'--max-count={max_commits}',
        f'--format={SEP}%n%ae|%an|%ad|%s',
        '--date=short',
        '--name-only',
    ], repo_path)

    commits = []
    current = None

    for line in raw.split('\n'):
        if line.strip() == SEP:
            if current and current.get('files'):
                commits.append(current)
            current = None
            continue

        if current is None:
            if '|' in line:
                parts = line.split('|', 3)
                if len(parts) >= 3:
                    current = {
                        'email':   parts[0].lower().strip(),
                        'name':    parts[1].strip(),
                        'date':    parts[2].strip()[:10],
                        'subject': parts[3].strip() if len(parts) > 3 else '',
                        'files':   [],
                    }
            continue

        line = line.strip()
        if line:
            ext = Path(line).suffix.lower()
            if ext in SUPPORTED_EXT:
                current['files'].append(line)

    if current and current.get('files'):
        commits.append(current)

    return commits


def build_developer_registry(commits: list[dict]) -> dict[str, Developer]:
    """Build Developer objects from commit history."""
    devs: dict[str, Developer] = {}
    cutoff = (datetime.now() - timedelta(days=ACTIVE_DAYS_THRESHOLD)).strftime('%Y-%m-%d')

    for c in commits:
        email = c['email']
        if email not in devs:
            devs[email] = Developer(login=email, name=c['name'])
        dev = devs[email]
        dev.commits += 1
        if not dev.first_commit or c['date'] < dev.first_commit:
            dev.first_commit = c['date']
        if not dev.last_commit or c['date'] > dev.last_commit:
            dev.last_commit = c['date']

    # Mark active/inactive
    for dev in devs.values():
        dev.active = dev.last_commit >= cutoff if dev.last_commit else False

    return devs


# ── 2. Blame (current line ownership) ─────────────────────────────────────────

def blame_file(filepath: str, repo_path: str) -> dict[str, int]:
    """
    Returns {author_email: line_count} for the current state of a file.
    Uses git blame with email extraction.
    """
    raw = _git(['blame', '--line-porcelain', filepath], repo_path, timeout=15)
    if not raw:
        return {}

    counts: dict[str, int] = defaultdict(int)
    current_email = None

    for line in raw.split('\n'):
        if line.startswith('author-mail '):
            current_email = line.split('<')[1].rstrip('>').lower() if '<' in line else ""
        elif line.startswith('\t') and current_email:
            counts[current_email] += 1
            current_email = None

    return dict(counts)


def blame_module(module_path: str, repo_path: str) -> dict[str, int]:
    """
    Aggregate blame across all supported files in a module directory.
    Returns {author_email: total_lines}.
    """
    totals: dict[str, int] = defaultdict(int)
    full_path = os.path.join(repo_path, module_path)

    for root, dirs, files in os.walk(full_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if Path(fname).suffix.lower() not in SUPPORTED_EXT:
                continue
            rel = os.path.relpath(os.path.join(root, fname), repo_path)
            file_blame = blame_file(rel, repo_path)
            for email, count in file_blame.items():
                totals[email] += count

    return dict(totals)


# ── 3. Co-change graph ────────────────────────────────────────────────────────

def build_co_change_graph(commits: list[dict], module_map: dict[str, str]) -> dict[str, dict[str, int]]:
    """
    For every pair of modules changed in the same commit, increment co_change[a][b].
    module_map: file_path → module_path (directory).

    Returns {module_a: {module_b: co_change_count}}.
    This reveals hidden coupling: if PaymentService and OrderService
    are always committed together, they share implicit knowledge.
    """
    co_change: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for commit in commits:
        # Get unique modules touched in this commit
        modules_in_commit = set()
        for filepath in commit['files']:
            module = module_map.get(filepath, os.path.dirname(filepath))
            if module:
                modules_in_commit.add(module)

        modules_list = sorted(modules_in_commit)
        for i, mod_a in enumerate(modules_list):
            for mod_b in modules_list[i + 1:]:
                co_change[mod_a][mod_b] += 1
                co_change[mod_b][mod_a] += 1

    return {k: dict(v) for k, v in co_change.items()}


# ── 4. Module discovery ───────────────────────────────────────────────────────

def discover_modules(repo_path: str, granularity: str = "directory") -> list[str]:
    """
    Discover logical modules. Granularity options:
      'directory': each directory with source files = one module
      'package':   use namespace/package declarations (C# namespace, Java package)
      'top_level': only top-level source directories

    Returns list of module paths (repo-relative).
    """
    modules = set()

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        rel_root = os.path.relpath(root, repo_path).replace('\\', '/')
        if rel_root == '.':
            rel_root = ''

        has_source = any(Path(f).suffix.lower() in SUPPORTED_EXT for f in files)
        if not has_source:
            continue

        if granularity == 'top_level':
            parts = rel_root.split('/')
            modules.add(parts[0] if parts[0] else rel_root)
        else:
            modules.add(rel_root)

    return sorted(m for m in modules if m)


def build_file_to_module_map(modules: list[str], repo_path: str) -> dict[str, str]:
    """Map each file path to its containing module."""
    file_map = {}
    for module in modules:
        full = os.path.join(repo_path, module)
        for root, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if Path(fname).suffix.lower() in SUPPORTED_EXT:
                    rel = os.path.relpath(os.path.join(root, fname), repo_path).replace('\\', '/')
                    file_map[rel] = module
    return file_map


def count_module_lines(module_path: str, repo_path: str) -> int:
    """Count LOC in a module."""
    total = 0
    full = os.path.join(repo_path, module_path)
    for root, dirs, files in os.walk(full):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if Path(fname).suffix.lower() not in SUPPORTED_EXT:
                continue
            try:
                content = Path(os.path.join(root, fname)).read_text(encoding='utf-8', errors='ignore')
                total += len([l for l in content.split('\n') if l.strip()])
            except Exception:
                pass
    return total


def detect_language(module_path: str, repo_path: str) -> str:
    """Return dominant language in a module by file count."""
    counts: dict[str, int] = defaultdict(int)
    full = os.path.join(repo_path, module_path)
    for root, dirs, files in os.walk(full):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            ext = Path(fname).suffix.lower()
            lang = {'.cs': 'C#', '.java': 'Java', '.ts': 'TypeScript',
                    '.tsx': 'TypeScript', '.py': 'Python', '.js': 'JavaScript',
                    '.go': 'Go', '.rb': 'Ruby'}.get(ext, '')
            if lang:
                counts[lang] += 1
    return max(counts, key=counts.get) if counts else 'unknown'
