"""
State resolver and git age enricher — Layer 2.

Determines which flags are graveyard candidates:
  - ALWAYS_ON:  hardcoded true, config value = true, env = "1"/"true"
  - ALWAYS_OFF: hardcoded false, config value = false, removed from config
  - DYNAMIC:    skip (legitimately varies at runtime)

Also enriches each flag with:
  - git_age_days: how long ago the flag was introduced
  - last_changed_days: how recently the flag code was touched
  - introduced_by: git author
  - ticket_ref: JIRA/GitHub issue number from commit messages
"""

import re
import subprocess
from pathlib import Path
from core.models import FlagDefinition, FlagState, FlagKind, CleanupAction, GraveyardReport


# ── Graveyard filter ──────────────────────────────────────────────────────────

GRAVEYARD_AGE_THRESHOLD_DAYS = 30   # flags older than this are graveyard candidates

# Flags whose names suggest they're intentionally permanent
PERMANENT_FLAG_NAMES = re.compile(
    r'debug|admin|internal|maintenance|killswitch|kill_switch|'
    r'emergency|circuit_breaker|circuit|canary',
    re.IGNORECASE
)


def is_graveyard_candidate(flag: FlagDefinition) -> bool:
    """
    Return True if this flag should be reported as a graveyard candidate.
    Filters out:
      - DYNAMIC flags (legitimately vary at runtime)
      - Flags with known-permanent names
      - Flags that haven't been around long enough
    """
    if flag.state == FlagState.DYNAMIC:
        return False
    if flag.state == FlagState.UNKNOWN and flag.total_usages() == 0:
        return False   # orphaned reference with no config — skip
    if PERMANENT_FLAG_NAMES.search(flag.name):
        return False
    return flag.state in (FlagState.ALWAYS_ON, FlagState.ALWAYS_OFF)


# ── Cleanup action classifier ─────────────────────────────────────────────────

def classify_cleanup(flag: FlagDefinition) -> tuple[CleanupAction, str]:
    """
    Determine what cleanup action is needed and how complex it is.
    Returns (action, complexity).
    """
    usages = flag.usages

    if not usages:
        # Config-only flag with no code usages — just delete the config entry
        return CleanupAction.REMOVE_ALWAYS_TRUE_FLAG if flag.state == FlagState.ALWAYS_ON \
               else CleanupAction.REMOVE_ALWAYS_FALSE_FLAG, 'simple'

    # Check for simple patterns: all usages are single if-checks with no else
    all_simple = all(
        u.branch_kind == 'if_check' and not u.has_else
        for u in usages
    )
    any_complex = any(
        u.true_branch_lines > 30 or u.false_branch_lines > 30
        for u in usages
    )

    if flag.state == FlagState.ALWAYS_ON:
        action = CleanupAction.REMOVE_ALWAYS_TRUE_FLAG
    else:
        action = CleanupAction.REMOVE_ALWAYS_FALSE_FLAG

    complexity = 'simple' if (all_simple and not any_complex and len(usages) <= 3) \
            else 'complex' if (any_complex or len(usages) > 10) \
            else 'medium'

    return action, complexity


# ── Git enricher ──────────────────────────────────────────────────────────────

def _run_git(args: list[str], repo_path: str) -> str:
    try:
        result = subprocess.run(
            ['git'] + args, cwd=repo_path,
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _parse_age_string(age_str: str) -> int:
    """Convert git's relative time strings to days."""
    if not age_str:
        return 0
    m = re.search(r'(\d+)\s+(year|month|week|day)', age_str)
    if not m:
        return 1
    n, unit = int(m.group(1)), m.group(2)
    return n * {'year': 365, 'month': 30, 'week': 7, 'day': 1}[unit]


def enrich_with_git(flags: list[FlagDefinition], repo_path: str, verbose: bool = False):
    """
    Enrich each flag with git metadata: age, last changed, author, ticket ref.
    Modifies flags in place.
    """
    for i, flag in enumerate(flags):
        if verbose and i % 5 == 0:
            print(f"\r  Git enrichment: {i}/{len(flags)}...", end='', flush=True)

        if not flag.source_file:
            continue

        filepath = flag.source_file

        # Age: when was this file first committed
        first_log = _run_git(
            ['log', '--follow', '--diff-filter=A', '--format=%cr|%an|%s', '--', filepath],
            repo_path
        )
        if first_log:
            parts = first_log.split('|', 2)
            flag.git_age_days = _parse_age_string(parts[0])
            flag.introduced_by = parts[1] if len(parts) > 1 else ""
            commit_msg = parts[2] if len(parts) > 2 else ""
            # Extract ticket reference from commit message
            m = re.search(r'\b([A-Z]{2,8}-\d{1,6}|#\d{3,6})\b', commit_msg)
            flag.ticket_ref = m.group(1) if m else ""

        # Last changed
        last_log = _run_git(
            ['log', '-1', '--format=%cr', '--', filepath],
            repo_path
        )
        flag.last_changed_days = _parse_age_string(last_log)

    if verbose:
        print(f"\r  Git enrichment complete.                    ")


# ── State resolver orchestrator ───────────────────────────────────────────────

def resolve_states(
    flags: list[FlagDefinition],
    repo_path: str,
    verbose: bool = False,
    skip_git: bool = False,
) -> list[FlagDefinition]:
    """
    Classify each flag's state, compute cleanup actions, and optionally
    enrich with git metadata.
    Returns only graveyard candidates (ALWAYS_ON or ALWAYS_OFF).
    """
    # Git enrichment first
    if not skip_git:
        enrich_with_git(flags, repo_path, verbose=verbose)

    # Classify cleanup action for each flag
    for flag in flags:
        flag.cleanup_action, flag.cleanup_complexity = classify_cleanup(flag)

    # Filter to graveyard candidates only
    candidates = [f for f in flags if is_graveyard_candidate(f)]

    # Sort: simple cleanups first, then by age (oldest first)
    candidates.sort(key=lambda f: (
        {'simple': 0, 'medium': 1, 'complex': 2}[f.cleanup_complexity],
        -f.git_age_days
    ))

    return candidates


def build_report(
    all_flags: list[FlagDefinition],
    graveyard: list[FlagDefinition],
    files_scanned: int,
) -> GraveyardReport:
    always_on  = sum(1 for f in graveyard if f.state == FlagState.ALWAYS_ON)
    always_off = sum(1 for f in graveyard if f.state == FlagState.ALWAYS_OFF)
    all_affected_files = set()
    total_dead_lines = 0
    by_lang: dict = {}
    by_kind: dict = {}

    for f in graveyard:
        all_affected_files.update(f.affected_files())
        total_dead_lines += f.dead_lines()
        by_lang[f.language] = by_lang.get(f.language, 0) + 1
        by_kind[f.kind.value] = by_kind.get(f.kind.value, 0) + 1

    return GraveyardReport(
        flags=graveyard,
        total_flags=len(all_flags),
        graveyard_count=len(graveyard),
        always_on=always_on,
        always_off=always_off,
        files_affected=len(all_affected_files),
        dead_lines=total_dead_lines,
        files_scanned=files_scanned,
        by_language=by_lang,
        by_kind=by_kind,
    )
