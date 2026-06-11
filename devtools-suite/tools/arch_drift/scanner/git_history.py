"""
Git history scanner.
Walks back through git history N commits at a time, running the violation
engine at each checkpoint to build a DriftTimeline.

This is what makes the Drift Detector unique: not just "does drift exist now"
but "when did it start, and is it getting better or worse?"
"""

import subprocess
import os
import json
from datetime import datetime
from pathlib import Path
from core.models import DriftScore, DriftTimeline, Violation
from rules.loader import CompiledArchRules
from scanner.import_graph import build_import_graph
from scanner.violation_engine import evaluate_all

TIMELINE_CACHE = ".arch-drift-timeline.json"


def get_commit_log(repo_path: str, max_commits: int = 30) -> list[dict]:
    """Return list of {sha, date, message} for last N commits."""
    try:
        result = subprocess.run(
            ['git', 'log', f'--max-count={max_commits}', '--format=%H|%ci|%s'],
            cwd=repo_path, capture_output=True, text=True
        )
        commits = []
        for line in result.stdout.strip().split('\n'):
            if '|' not in line:
                continue
            parts = line.split('|', 2)
            if len(parts) >= 2:
                commits.append({
                    'sha': parts[0].strip(),
                    'date': parts[1].strip()[:10],
                    'message': parts[2].strip() if len(parts) > 2 else '',
                })
        return commits
    except Exception:
        return []


def get_current_sha(repo_path: str) -> str:
    try:
        r = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                           cwd=repo_path, capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return 'HEAD'


def checkout_commit(repo_path: str, sha: str):
    """Detach HEAD to a specific commit (read-only analysis)."""
    subprocess.run(['git', 'checkout', '--detach', sha],
                   cwd=repo_path, capture_output=True)


def restore_head(repo_path: str, original_branch: str):
    """Restore the original branch after history scan."""
    subprocess.run(['git', 'checkout', original_branch],
                   cwd=repo_path, capture_output=True)


def get_current_branch(repo_path: str) -> str:
    try:
        r = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                           cwd=repo_path, capture_output=True, text=True)
        branch = r.stdout.strip()
        return branch if branch != 'HEAD' else 'main'
    except Exception:
        return 'main'


def load_cached_timeline(repo_path: str) -> DriftTimeline | None:
    """Load previously computed timeline from cache."""
    cache_path = Path(repo_path) / TIMELINE_CACHE
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text())
        timeline = DriftTimeline(repo_path=data['repo_path'], rule_file=data['rule_file'])
        for snap in data.get('snapshots', []):
            timeline.snapshots.append(DriftScore(**snap))
        return timeline
    except Exception:
        return None


def save_timeline(timeline: DriftTimeline, repo_path: str):
    cache_path = Path(repo_path) / TIMELINE_CACHE
    data = {
        'repo_path': timeline.repo_path,
        'rule_file': timeline.rule_file,
        'snapshots': [
            {
                'commit_sha': s.commit_sha,
                'commit_date': s.commit_date,
                'total_violations': s.total_violations,
                'errors': s.errors,
                'warnings': s.warnings,
                'infos': s.infos,
                'score': s.score,
            }
            for s in timeline.snapshots
        ]
    }
    cache_path.write_text(json.dumps(data, indent=2))


def build_timeline(
    rules: CompiledArchRules,
    repo_path: str,
    rule_file: str,
    max_commits: int = 20,
    verbose: bool = False,
) -> DriftTimeline:
    """
    Walk back through git history and compute a drift score at each commit.
    Returns a DriftTimeline with one DriftScore per commit.

    WARNING: This temporarily checks out historical commits — do not run
    on a repo with uncommitted changes.
    """
    timeline = DriftTimeline(repo_path=repo_path, rule_file=rule_file)
    original_branch = get_current_branch(repo_path)
    commits = get_commit_log(repo_path, max_commits)

    if not commits:
        if verbose:
            print("  No git history found — scanning current state only")
        return timeline

    if verbose:
        print(f"  Scanning {len(commits)} commits for drift history...")

    for i, commit in enumerate(commits):
        sha  = commit['sha']
        date = commit['date']
        try:
            if i > 0:
                checkout_commit(repo_path, sha)

            graph      = build_import_graph(repo_path)
            violations = evaluate_all(rules, graph)
            score      = DriftScore.from_violations(sha[:8], date, violations)
            timeline.snapshots.insert(0, score)  # chronological order

            if verbose:
                print(f"  {date} {sha[:8]}  score={score.score:3}  violations={score.total_violations}")

        except Exception as e:
            if verbose:
                print(f"  Skipping {sha[:8]}: {e}")
            continue
        finally:
            if i > 0:
                restore_head(repo_path, original_branch)

    return timeline


def scan_current_state(
    rules: CompiledArchRules,
    repo_path: str,
    prev_violations: list[Violation] | None = None,
) -> tuple[list[Violation], list[Violation], list[Violation]]:
    """
    Scan the current working tree state.
    Returns (all_violations, new_violations, resolved_violations).
    """
    graph      = build_import_graph(repo_path)
    violations = evaluate_all(rules, graph)

    if prev_violations is None:
        return violations, violations, []

    prev_ids = {v.id for v in prev_violations}
    curr_ids = {v.id for v in violations}

    new_violations      = [v for v in violations if v.id not in prev_ids]
    resolved_violations = [v for v in prev_violations if v.id not in curr_ids]

    return violations, new_violations, resolved_violations


def load_previous_violations(repo_path: str) -> list[Violation]:
    """Load violations from the last saved scan (for diffing)."""
    state_path = Path(repo_path) / '.arch-drift-state.json'
    if not state_path.exists():
        return []
    try:
        data = json.loads(state_path.read_text())
        return [Violation.from_dict(v) for v in data.get('violations', [])]
    except Exception:
        return []


def save_violations(violations: list[Violation], repo_path: str):
    """Persist current violations for next-run diffing."""
    state_path = Path(repo_path) / '.arch-drift-state.json'
    data = {
        'generated': datetime.utcnow().isoformat(),
        'total': len(violations),
        'violations': [v.to_dict() for v in violations],
    }
    state_path.write_text(json.dumps(data, indent=2))
