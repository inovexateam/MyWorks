"""
Implicit Knowledge Extractor — CLI entry point.

Usage:
  python knowledge_extractor.py                    # scan current repo
  python knowledge_extractor.py --repo /path       # specific repo
  python knowledge_extractor.py --wiki             # generate per-module markdown wiki
  python knowledge_extractor.py --json             # JSON output for CI
  python knowledge_extractor.py --gaps             # show only knowledge gaps
  python knowledge_extractor.py --pairings         # show pairing recommendations
  python knowledge_extractor.py --granularity top  # coarser module grouping
  python knowledge_extractor.py --max-commits 2000 # limit history depth
"""

import argparse
import json
import os
import sys
from datetime import datetime

from miner.git_miner import (
    fetch_commit_log, build_developer_registry,
    discover_modules, build_file_to_module_map,
    blame_module, build_co_change_graph,
)
from graph.ownership_graph import build_ownership_graph, build_report
from wiki.wiki_generator import generate_full_wiki
from reporters.html_reporter import generate_html_report
from core.models import KnowledgeReport

RESET = '\033[0m'; BOLD = '\033[1m'
RED   = '\033[91m'; AMBER = '\033[93m'; BLUE = '\033[94m'; GREEN = '\033[92m'; MUTED = '\033[90m'

RISK_COLOR = {'critical': RED, 'high': AMBER, 'medium': BLUE, 'low': GREEN}


def print_summary(report: KnowledgeReport):
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}  Implicit Knowledge Extractor{RESET}  {MUTED}{datetime.now().strftime('%Y-%m-%d %H:%M')}{RESET}")
    print(f"{'─'*60}")
    print(f"  Commits analyzed:  {report.commits_analyzed:,}")
    print(f"  Modules:           {len(report.modules)}")
    print(f"  Developers:        {len([d for d in report.developers if d.active])} active")
    print(f"  Critical modules:  {RED}{len(report.critical_modules)}{RESET}  (bus factor 1)")
    print(f"  Orphaned modules:  {RED}{len(report.orphaned_modules)}{RESET}  (sole owner inactive)")
    print(f"  Knowledge gaps:    {AMBER}{len(report.gaps)}{RESET}")
    print(f"  Pairings:          {GREEN}{len(report.pairings)}{RESET}  recommended")
    print()


def print_gaps(report: KnowledgeReport):
    if not report.gaps:
        print(f"  {GREEN}No critical knowledge gaps detected.{RESET}")
        return
    for g in report.gaps[:15]:
        color = RISK_COLOR.get(g.risk_level, MUTED)
        print(f"  {color}[{g.risk_level.upper():8}]{RESET}  {g.module}")
        print(f"  {MUTED}{g.description}{RESET}")
        print(f"  {g.recommendation[:100]}")
        print()


def print_pairings(report: KnowledgeReport):
    if not report.pairings:
        print(f"  {GREEN}No pairing recommendations.{RESET}")
        return
    prio_color = {'urgent': RED, 'high': AMBER, 'medium': BLUE}
    for p in report.pairings[:15]:
        color = prio_color.get(p.priority, MUTED)
        print(f"  {color}[{p.priority.upper():6}]{RESET}  {p.teacher}  →  {p.learner}")
        print(f"  {MUTED}Module: {p.module}{RESET}")
        print()


def main():
    parser = argparse.ArgumentParser(prog='knowledge-extractor')
    parser.add_argument('--repo',         default='.', help='Repo root')
    parser.add_argument('--wiki',         action='store_true', help='Generate per-module wiki')
    parser.add_argument('--json',         action='store_true', help='JSON output')
    parser.add_argument('--gaps',         action='store_true', help='Show knowledge gaps')
    parser.add_argument('--pairings',     action='store_true', help='Show pairing recommendations')
    parser.add_argument('--report',       default='knowledge-report.html')
    parser.add_argument('--no-report',    action='store_true')
    parser.add_argument('--no-blame',     action='store_true', help='Skip blame (faster)')
    parser.add_argument('--granularity',  choices=['directory','top_level'], default='directory')
    parser.add_argument('--max-commits',  type=int, default=3000)
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    verbose   = not args.json

    if verbose:
        print(f"\n{BOLD}Implicit Knowledge Extractor{RESET}  {MUTED}{repo_path}{RESET}")
        print(f"{MUTED}Mining git history...{RESET}")

    # ── Mine ──────────────────────────────────────────────────────────────────
    commits = fetch_commit_log(repo_path, max_commits=args.max_commits)
    if not commits:
        print(f"{RED}No git history found.{RESET}")
        sys.exit(1)

    if verbose:
        print(f"  {len(commits)} commits found")

    developers = build_developer_registry(commits)
    modules    = discover_modules(repo_path, granularity=args.granularity)
    file_map   = build_file_to_module_map(modules, repo_path)

    if verbose:
        print(f"  {len(modules)} modules, {len(developers)} developers")
        print(f"{MUTED}Building ownership graph...{RESET}")

    # ── Blame ─────────────────────────────────────────────────────────────────
    module_blame = {}
    if not args.no_blame:
        if verbose:
            print(f"{MUTED}Running blame (may take a moment)...{RESET}")
        for i, mod in enumerate(modules[:50]):  # cap at 50 modules for blame
            module_blame[mod] = blame_module(mod, repo_path)
            if verbose and i % 10 == 0:
                print(f"\r  Blame: {i}/{min(len(modules),50)}...", end='', flush=True)
        if verbose:
            print(f"\r  Blame complete.                 ")

    # ── Co-change graph ───────────────────────────────────────────────────────
    co_changes = build_co_change_graph(commits, file_map)

    # ── Ownership graph ───────────────────────────────────────────────────────
    module_objects = build_ownership_graph(
        commits, module_blame, file_map, modules, repo_path, verbose=verbose
    )

    # Date range
    dates = [c['date'] for c in commits if c.get('date')]
    date_range = f"{min(dates)} to {max(dates)}" if dates else "unknown"

    report = build_report(
        module_objects, developers, co_changes,
        len(commits), len(file_map), date_range
    )

    # ── Output ────────────────────────────────────────────────────────────────
    if args.json:
        data = {
            'generated': datetime.utcnow().isoformat(),
            'commits_analyzed': len(commits),
            'files_analyzed': len(file_map),
            'date_range': date_range,
            'critical_count': len(report.critical_modules),
            'gaps_count': len(report.gaps),
            'pairings_count': len(report.pairings),
            'modules': [m.to_dict() for m in report.modules],
            'gaps': [{'module': g.module, 'risk': g.risk_level, 'description': g.description,
                      'primary': g.primary_expert, 'recommendation': g.recommendation}
                     for g in report.gaps],
            'pairings': [{'teacher': p.teacher, 'learner': p.learner,
                          'module': p.module, 'priority': p.priority} for p in report.pairings],
        }
        print(json.dumps(data, indent=2))
    else:
        print_summary(report)

        if args.gaps or not (args.pairings or args.wiki):
            print(f"{BOLD}Knowledge gaps:{RESET}\n")
            print_gaps(report)

        if args.pairings or not (args.gaps or args.wiki):
            print(f"{BOLD}Pairing recommendations:{RESET}\n")
            print_pairings(report)

        if args.wiki:
            generate_full_wiki(report, commits, file_map, os.path.join(repo_path, 'knowledge-wiki'))

        if not args.no_report:
            report_path = os.path.join(repo_path, args.report)
            generate_html_report(report, report_path)
            print(f"  {MUTED}Report:{RESET} file://{report_path}\n")


if __name__ == '__main__':
    main()
