"""
Assumption Miner — CLI entry point.

Usage:
  python assume_miner.py scan .                     # scan entire repo
  python assume_miner.py scan . --pr main           # find contradictions vs main branch
  python assume_miner.py report                     # open last HTML report
  python assume_miner.py show --risk high           # list high-risk assumptions
  python assume_miner.py show --kind null_safety    # filter by kind
  python assume_miner.py diff HEAD~1                # what assumptions changed in last commit
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path

from patterns.csharp_detector import scan_csharp_file
from patterns.java_ts_detector import scan_java_file, scan_typescript_file
from registry.registry import AssumptionRegistry, find_contradictions, compute_risk
from reporters.html_reporter import generate_html_report
from core.models import RiskLevel, AssumptionKind, ScanResult

SUPPORTED = {
    '.cs': scan_csharp_file,
    '.java': scan_java_file,
    '.ts': scan_typescript_file,
    '.tsx': scan_typescript_file,
}

SKIP_DIRS = {'node_modules', '.git', 'bin', 'obj', 'dist', '.angular', 'build', 'out', 'target'}

RISK_COLORS = {
    RiskLevel.CRITICAL: '\033[91m',  # red
    RiskLevel.HIGH:     '\033[93m',  # yellow
    RiskLevel.MEDIUM:   '\033[94m',  # blue
    RiskLevel.LOW:      '\033[92m',  # green
}
RESET = '\033[0m'


def get_git_sha(repo_path: str) -> str:
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                                cwd=repo_path, capture_output=True, text=True)
        return result.stdout.strip()
    except Exception:
        return "unknown"


def get_changed_files(base_branch: str, repo_path: str) -> list[str]:
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', f'origin/{base_branch}...HEAD'],
            cwd=repo_path, capture_output=True, text=True
        )
        return [f for f in result.stdout.strip().split('\n') if f.strip()]
    except Exception:
        return []


def scan_repo(repo_path: str) -> list:
    all_assumptions = []
    file_count = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            ext = Path(file).suffix.lower()
            scanner = SUPPORTED.get(ext)
            if not scanner:
                continue
            filepath = os.path.join(root, file)
            rel = os.path.relpath(filepath, repo_path)
            assumptions = scanner(filepath)
            # fix relative paths
            for a in assumptions:
                a.location.file = rel
            all_assumptions.extend(assumptions)
            file_count += 1
            if file_count % 10 == 0:
                print(f"\r  Scanned {file_count} files, {len(all_assumptions)} assumptions found...", end='')

    print(f"\r  Scanned {file_count} files total.{' ' * 30}")
    return all_assumptions, file_count


def cmd_scan(args):
    repo_path = os.path.abspath(args.path)
    print(f"\nAssumption Miner — scanning {repo_path}")
    print("─" * 50)

    # Scan
    all_assumptions, file_count = scan_repo(repo_path)

    # Load/update registry
    registry = AssumptionRegistry(repo_path)
    sha = get_git_sha(repo_path)
    stats = registry.merge_scan(all_assumptions, sha)

    # Compute risk for each
    for a in registry.all():
        a.risk = compute_risk(a, repo_path)

    # Find contradictions if PR mode
    contradictions = []
    if args.pr:
        print(f"\nChecking for contradictions vs '{args.pr}' branch...")
        changed = get_changed_files(args.pr, repo_path)
        print(f"  {len(changed)} changed files in this PR")
        contradictions = find_contradictions(registry, changed, repo_path)
        for c in contradictions:
            c.assumption.risk = RiskLevel.CRITICAL

    registry.save()

    # Build result
    result = ScanResult(
        assumptions=registry.all(),
        contradictions=contradictions,
        files_scanned=file_count,
        total_assumptions=len(registry.all()),
        by_kind={k.value: sum(1 for a in registry.all() if a.kind == k) for k in AssumptionKind},
        by_risk={r.value: sum(1 for a in registry.all() if a.risk == r) for r in RiskLevel},
    )

    # Print summary
    print(f"\n{result.summary()}")
    print(f"  Added: {stats['added']} · Unchanged: {stats['unchanged']} · Resolved: {stats['removed']}")

    if contradictions:
        print(f"\n{'─'*50}")
        print(f"  {RISK_COLORS[RiskLevel.CRITICAL]}CONTRADICTIONS FOUND: {len(contradictions)}{RESET}")
        for c in contradictions:
            print(f"\n  [{c.severity.upper()}] {c.assumption.statement}")
            print(f"    Assumption in: {c.assumption.location.file}:{c.assumption.location.line}")
            print(f"    Contradicted:  {c.contradiction_file}:{c.contradiction_line}")
            print(f"    Code: {c.contradiction_snippet[:80]}")

    # Generate report
    report_path = os.path.join(repo_path, 'assumption-report.html')
    generate_html_report(result, report_path)
    print(f"\nReport: file://{report_path}")

    return len(contradictions)


def cmd_show(args):
    registry = AssumptionRegistry(args.path if hasattr(args, 'path') else '.')
    assumptions = registry.all()

    if args.risk:
        risk = RiskLevel(args.risk)
        assumptions = [a for a in assumptions if a.risk == risk]

    if args.kind:
        kind = AssumptionKind(args.kind)
        assumptions = [a for a in assumptions if a.kind == kind]

    assumptions.sort(key=lambda a: list(RiskLevel).index(a.risk))

    print(f"\n{len(assumptions)} assumptions\n{'─'*60}")
    for a in assumptions:
        color = RISK_COLORS.get(a.risk, '')
        print(f"\n{color}[{a.risk.value.upper()}]{RESET} {a.statement}")
        print(f"  {a.location.file}:{a.location.line} · kind={a.kind.value} · confidence={a.confidence:.0%}")
        if a.location.snippet:
            print(f"  > {a.location.snippet[:100]}")


def main():
    parser = argparse.ArgumentParser(prog='assume-miner', description='Assumption Miner')
    sub = parser.add_subparsers(dest='command')

    p_scan = sub.add_parser('scan', help='Scan repo and update registry')
    p_scan.add_argument('path', nargs='?', default='.', help='Repo root')
    p_scan.add_argument('--pr', metavar='BRANCH', help='Find contradictions vs this branch')
    p_scan.add_argument('--report', default='assumption-report.html', help='Output report path')

    p_show = sub.add_parser('show', help='Show assumptions from registry')
    p_show.add_argument('path', nargs='?', default='.', help='Repo root')
    p_show.add_argument('--risk', choices=[r.value for r in RiskLevel], help='Filter by risk')
    p_show.add_argument('--kind', choices=[k.value for k in AssumptionKind], help='Filter by kind')

    args = parser.parse_args()

    if args.command == 'scan':
        contradictions = cmd_scan(args)
        sys.exit(1 if contradictions > 0 else 0)  # exit 1 = CI fails on contradictions
    elif args.command == 'show':
        cmd_show(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
