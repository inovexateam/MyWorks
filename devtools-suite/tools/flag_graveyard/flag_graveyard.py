"""
Feature Flag Graveyard Hunter — CLI entry point.

Usage:
  python flag_graveyard.py                    # scan current repo
  python flag_graveyard.py --repo /path       # specific repo
  python flag_graveyard.py --plans            # generate cleanup plan files
  python flag_graveyard.py --show always_on   # filter by state
  python flag_graveyard.py --json             # JSON output for CI
  python flag_graveyard.py --no-git           # skip git enrichment (faster)
  python flag_graveyard.py --threshold 20     # exit 1 if graveyard >= threshold
"""

import argparse
import json
import os
import sys
from datetime import datetime

from scanner.flag_scanner import scan_all_flags
from resolver.state_resolver import resolve_states, build_report
from cleanup.cleanup_generator import scaffold_all_prs, generate_pr_description
from reporters.html_reporter import generate_html_report
from core.models import FlagState

RESET = '\033[0m'; BOLD = '\033[1m'
RED   = '\033[91m'; AMBER = '\033[93m'; BLUE = '\033[94m'; GREEN = '\033[92m'; MUTED = '\033[90m'

STATE_COLOR = {
    FlagState.ALWAYS_ON:  AMBER,
    FlagState.ALWAYS_OFF: RED,
    FlagState.UNKNOWN:    BLUE,
}
CMPLX_COLOR = {'simple': GREEN, 'medium': AMBER, 'complex': RED}


def print_flag(flag, verbose: bool = False):
    sc = STATE_COLOR.get(flag.state, MUTED)
    cc = CMPLX_COLOR.get(flag.cleanup_complexity, MUTED)
    age = f"{flag.git_age_days}d" if flag.git_age_days else "?"
    ticket = f"  {BLUE}{flag.ticket_ref}{RESET}" if flag.ticket_ref else ""
    print(f"  {sc}[{flag.state.value.replace('_',' ').upper():12}]{RESET}  "
          f"{flag.name:<35}  {cc}[{flag.cleanup_complexity}]{RESET}  "
          f"{MUTED}age={age}  uses={flag.total_usages()}{RESET}{ticket}")
    if verbose:
        print(f"  {MUTED}{flag.source_file}:{flag.source_line}{RESET}")
        if flag.affected_files():
            print(f"  {MUTED}Affects: {', '.join(list(flag.affected_files())[:3])}{RESET}")


def print_summary(report):
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}  Feature Flag Graveyard Hunter{RESET}  {MUTED}{datetime.now().strftime('%Y-%m-%d %H:%M')}{RESET}")
    print(f"{'─'*60}")
    print(f"  Files scanned:     {report.files_scanned}")
    print(f"  Flags found:       {report.total_flags}")
    print(f"  Graveyard total:   {AMBER}{report.graveyard_count}{RESET}")
    print(f"    Always-on:       {AMBER}{report.always_on}{RESET}  (inline true branch, remove check)")
    print(f"    Always-off:      {RED}{report.always_off}{RESET}  (remove entire block)")
    simple = sum(1 for f in report.flags if f.cleanup_complexity == 'simple')
    print(f"  Simple cleanups:   {GREEN}{simple}{RESET}  (safe to automate)")
    print(f"  Removable LOC:     ~{report.dead_lines}")
    print(f"  Files affected:    {report.files_affected}")
    print()


def main():
    parser = argparse.ArgumentParser(prog='flag-graveyard', description='Feature Flag Graveyard Hunter')
    parser.add_argument('--repo',      default='.', help='Repo root')
    parser.add_argument('--show',      choices=['all', 'always_on', 'always_off', 'simple'],
                        default='all', help='Filter output')
    parser.add_argument('--plans',     action='store_true', help='Generate cleanup plan files')
    parser.add_argument('--json',      action='store_true', help='JSON output')
    parser.add_argument('--report',    default='flag-graveyard-report.html')
    parser.add_argument('--no-report', action='store_true')
    parser.add_argument('--no-git',    action='store_true', help='Skip git enrichment')
    parser.add_argument('--threshold', type=int, default=0,
                        help='Exit 1 if graveyard count >= threshold')
    parser.add_argument('--verbose',   action='store_true')
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    verbose   = args.verbose and not args.json

    # ── Scan ──────────────────────────────────────────────────────────────────
    if not args.json:
        print(f"\n{BOLD}Feature Flag Graveyard Hunter{RESET}  {MUTED}{repo_path}{RESET}")
        print(f"{MUTED}Scanning flags...{RESET}")

    all_flags, usages, file_count = scan_all_flags(repo_path, verbose=not args.json)

    if not args.json:
        print(f"  {len(all_flags)} flags found in {file_count} files")
        print(f"{MUTED}Resolving states...{RESET}")

    graveyard = resolve_states(all_flags, repo_path, verbose=not args.json, skip_git=args.no_git)
    report    = build_report(all_flags, graveyard, file_count)

    # ── Output ────────────────────────────────────────────────────────────────
    if args.json:
        data = {
            'generated': datetime.utcnow().isoformat(),
            'files_scanned': file_count,
            'total_flags': report.total_flags,
            'graveyard_count': report.graveyard_count,
            'always_on': report.always_on,
            'always_off': report.always_off,
            'dead_lines': report.dead_lines,
            'flags': [f.to_dict() for f in graveyard],
        }
        print(json.dumps(data, indent=2))

    else:
        print_summary(report)

        to_show = graveyard
        if args.show == 'always_on':  to_show = [f for f in graveyard if f.state == FlagState.ALWAYS_ON]
        if args.show == 'always_off': to_show = [f for f in graveyard if f.state == FlagState.ALWAYS_OFF]
        if args.show == 'simple':     to_show = [f for f in graveyard if f.cleanup_complexity == 'simple']

        for flag in to_show[:25]:
            print_flag(flag, verbose=verbose)
        if len(to_show) > 25:
            print(f"\n  {MUTED}... {len(to_show)-25} more. See HTML report.{RESET}")
        print()

        if args.plans:
            plans_dir = scaffold_all_prs(graveyard, repo_path, repo_path)
            print(f"  {GREEN}✓{RESET}  Cleanup plans → {plans_dir}/")

        if not args.no_report:
            report_path = os.path.join(repo_path, args.report)
            generate_html_report(report, report_path)
            print(f"  {MUTED}Report:{RESET} file://{report_path}\n")

    # ── Exit code ──────────────────────────────────────────────────────────────
    if args.threshold > 0 and report.graveyard_count >= args.threshold:
        if not args.json:
            print(f"{RED}Graveyard count {report.graveyard_count} >= threshold {args.threshold}{RESET}")
        sys.exit(1)


if __name__ == '__main__':
    main()
