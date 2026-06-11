"""
Cross-PR Dependency Intelligence — CLI entry point.

Usage:
  python cross_pr.py                          # scan all open PRs
  python cross_pr.py --pr 42                  # check PR #42 specifically
  python cross_pr.py --json                   # JSON output for CI
  python cross_pr.py --comment 42             # print GitHub PR comment for PR #42
  python cross_pr.py --threshold critical     # exit 1 only on critical conflicts
  python cross_pr.py --report report.html     # custom report path

Environment:
  GITHUB_TOKEN   GitHub personal access token (repo scope)
  GITHUB_REPO    owner/repo-name
"""

import argparse
import json
import os
import sys
from datetime import datetime

from fetcher.github_fetcher import GitHubClient, get_token_and_repo
from extractor.symbol_extractor import extract_symbols_from_pr
from engine.overlap_engine import analyze_all, build_conflict_reports
from reporters.html_reporter import generate_html_report
from core.models import Severity, PRSnapshot, Overlap

RESET = '\033[0m'; BOLD = '\033[1m'
RED   = '\033[91m'; AMBER = '\033[93m'; BLUE = '\033[94m'; GREEN = '\033[92m'; MUTED = '\033[90m'

SEV_COLOR = {'critical': RED, 'high': AMBER, 'medium': BLUE, 'low': GREEN}
SEV_ICON  = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}


def print_overlap(o: Overlap, all_prs: dict):
    color = SEV_COLOR.get(o.severity.value, MUTED)
    other_pr = all_prs.get(o.pr_b if o.pr_a != o.pr_b else o.pr_a)
    other_str = f"PR #{other_pr.number} ({other_pr.title[:35]})" if other_pr else f"PR #{o.pr_b}"
    print(f"  {color}[{o.severity.value.upper():8}]{RESET}  {o.kind.value.replace('_',' ').title()}")
    print(f"  {MUTED}With: {other_str}{RESET}")
    print(f"  {o.description}")
    if o.merge_order_matters:
        print(f"  {AMBER}⚠  Merge order matters{RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(prog='cross-pr', description='Cross-PR Dependency Intelligence')
    parser.add_argument('--repo',      default='', help='owner/repo (or set GITHUB_REPO)')
    parser.add_argument('--token',     default='', help='GitHub token (or set GITHUB_TOKEN)')
    parser.add_argument('--pr',        type=int, default=0, help='Focus on a specific PR number')
    parser.add_argument('--json',      action='store_true', help='JSON output')
    parser.add_argument('--comment',   type=int, default=0, help='Print PR comment for PR #N')
    parser.add_argument('--report',    default='cross-pr-report.html', help='HTML report path')
    parser.add_argument('--no-report', action='store_true', help='Skip HTML report')
    parser.add_argument('--threshold', choices=['critical', 'high', 'medium', 'low'], default='critical',
                        help='Exit code 1 if any overlap at this severity or above')
    parser.add_argument('--post-comments', action='store_true',
                        help='Post PR comments via GitHub API (requires write permissions)')
    args = parser.parse_args()

    # ── Resolve token and repo ─────────────────────────────────────────────────
    token = args.token or os.environ.get("GITHUB_TOKEN", "")
    repo  = args.repo  or os.environ.get("GITHUB_REPO", "")

    if not token or not repo:
        print(f"{RED}Error: GITHUB_TOKEN and GITHUB_REPO must be set.{RESET}")
        print(f"  export GITHUB_TOKEN=ghp_...")
        print(f"  export GITHUB_REPO=owner/repo-name")
        sys.exit(1)

    # ── Fetch ─────────────────────────────────────────────────────────────────
    client = GitHubClient(token, repo)
    if not args.json:
        print(f"\n{BOLD}Cross-PR Dependency Intelligence{RESET}  {MUTED}{repo}{RESET}")
        print(f"{MUTED}Fetching open PRs...{RESET}")

    prs = client.fetch_all_open_prs(verbose=not args.json)

    if not prs:
        if not args.json:
            print(f"{GREEN}No open PRs found.{RESET}")
        sys.exit(0)

    # Filter to specific PR if requested
    focus_pr = None
    if args.pr:
        focus_pr = next((p for p in prs if p.number == args.pr), None)
        if not focus_pr:
            print(f"{RED}PR #{args.pr} not found in open PRs.{RESET}")
            sys.exit(1)

    # ── Extract symbols ────────────────────────────────────────────────────────
    if not args.json:
        print(f"{MUTED}Extracting symbols from diffs...{RESET}")
    for pr in prs:
        extract_symbols_from_pr(pr)

    total_symbols = sum(len(pr.symbols) for pr in prs)
    if not args.json:
        print(f"  {total_symbols} symbols extracted across {len(prs)} PRs")

    # ── Analyze ───────────────────────────────────────────────────────────────
    if not args.json:
        print(f"{MUTED}Running overlap analysis...{RESET}")

    overlaps = analyze_all(prs)
    reports  = build_conflict_reports(prs, overlaps)
    pr_map   = {pr.number: pr for pr in prs}

    # ── Output ────────────────────────────────────────────────────────────────
    if args.json:
        data = {
            'generated': datetime.utcnow().isoformat(),
            'repo': repo,
            'pr_count': len(prs),
            'overlap_count': len(overlaps),
            'critical': sum(1 for o in overlaps if o.severity.value == 'critical'),
            'high':     sum(1 for o in overlaps if o.severity.value == 'high'),
            'overlaps': [o.to_dict() for o in overlaps],
            'prs': [{
                'number': pr.number,
                'title': pr.title,
                'author': pr.author,
                'conflicts_with': reports[pr.number].affected_prs,
                'severity': max(
                    (o.severity.value for o in reports[pr.number].overlaps),
                    key=lambda s: ['critical','high','medium','low'].index(s),
                    default='none'
                ),
            } for pr in prs],
        }
        print(json.dumps(data, indent=2))

    elif args.comment:
        report = reports.get(args.comment)
        if report:
            print(report.to_github_comment(pr_map))
        else:
            print(f"PR #{args.comment} not found.")

    else:
        # Human-readable terminal output
        crit_count = sum(1 for o in overlaps if o.severity.value == 'critical')
        high_count = sum(1 for o in overlaps if o.severity.value == 'high')
        print(f"\n{'─'*60}")
        print(f"  {len(prs)} PRs · {len(overlaps)} overlaps · {RED}{crit_count} critical{RESET} · {AMBER}{high_count} high{RESET}")
        print(f"{'─'*60}\n")

        # If focusing on one PR
        if focus_pr:
            report = reports[focus_pr.number]
            print(f"  PR #{focus_pr.number}: {focus_pr.title}")
            print(f"  {report.recommendation}\n")
            for o in report.overlaps:
                print_overlap(o, pr_map)
        else:
            # Show all overlaps, critical/high only by default
            shown = [o for o in overlaps if o.severity.value in ('critical', 'high')]
            if not shown:
                shown = overlaps[:10]
            for o in shown[:20]:
                print_overlap(o, pr_map)
            if len(overlaps) > 20:
                print(f"  {MUTED}... {len(overlaps)-20} more overlaps in the HTML report{RESET}\n")

        if not args.no_report:
            generate_html_report(prs, overlaps, reports, args.report)
            print(f"  {MUTED}Report:{RESET} file://{os.path.abspath(args.report)}\n")

    # ── Post PR comments ───────────────────────────────────────────────────────
    if args.post_comments:
        _post_pr_comments(client, prs, reports, pr_map)

    # ── Exit code ──────────────────────────────────────────────────────────────
    threshold_order = ['critical', 'high', 'medium', 'low']
    threshold_idx   = threshold_order.index(args.threshold)
    for o in overlaps:
        if threshold_order.index(o.severity.value) <= threshold_idx:
            sys.exit(1)


def _post_pr_comments(client, prs, reports, pr_map):
    """Post conflict reports as PR comments via the GitHub API."""
    import urllib.request, urllib.error
    for pr in prs:
        report = reports.get(pr.number)
        if not report or not report.overlaps:
            continue
        comment_body = report.to_github_comment(pr_map)
        payload = json.dumps({"body": comment_body}).encode()
        url = f"https://api.github.com/repos/{client.repo}/issues/{pr.number}/comments"
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {client.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "cross-pr-intelligence/1.0")
        try:
            with urllib.request.urlopen(req, timeout=10):
                print(f"  Posted comment on PR #{pr.number}")
        except Exception as e:
            print(f"  Failed to comment on PR #{pr.number}: {e}")


if __name__ == '__main__':
    main()
