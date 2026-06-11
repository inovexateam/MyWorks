"""
Blast Radius Visualizer — CLI entry point

Usage:
  python blast_radius.py                          # analyse uncommitted changes
  python blast_radius.py --pr main                # analyse PR vs main branch
  python blast_radius.py --file src/OrderSvc.cs  # single-file mode
  python blast_radius.py --json                   # JSON output for CI
  python blast_radius.py --threshold 50           # exit 1 if max risk >= threshold

Examples:
  python blast_radius.py --pr main --json > blast.json
  python blast_radius.py --threshold 70           # fail CI on critical risk
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

from core.diff_parser import get_uncommitted_diff, get_pr_diff, DiffResult
from core.dependency_graph import build_blast_radius, BlastRadiusResult
from core.risk_engine import (
    score_symbol, score_caller, summarize_risk,
    has_test_for_symbol, is_critical_path_file, RiskScore
)
from reporters.html_reporter import generate_html_report


# ── Terminal colours ───────────────────────────────────────────────────────────

RESET  = '\033[0m'
BOLD   = '\033[1m'
RED    = '\033[91m'
AMBER  = '\033[93m'
BLUE   = '\033[94m'
GREEN  = '\033[92m'
MUTED  = '\033[90m'
WHITE  = '\033[97m'

RISK_COLOR = {
    'critical': RED,
    'high':     AMBER,
    'medium':   BLUE,
    'low':      GREEN,
}


def risk_bar(score: int, width: int = 20) -> str:
    """Returns a compact ASCII risk bar: ████████░░░░░░░░░░░░ 42"""
    filled = int(score / 100 * width)
    color = RED if score >= 70 else AMBER if score >= 40 else BLUE if score >= 20 else GREEN
    bar = color + '█' * filled + MUTED + '░' * (width - filled) + RESET
    return f"{bar} {score}"


def print_header(result: BlastRadiusResult, repo_path: str):
    print()
    print(f"{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}  Blast Radius Visualizer{RESET}  {MUTED}{datetime.now().strftime('%Y-%m-%d %H:%M')}{RESET}")
    print(f"{BOLD}{'─' * 60}{RESET}")
    print(f"  Repo:     {MUTED}{repo_path}{RESET}")
    print(f"  Changed:  {WHITE}{result.total_symbols_affected} symbols{RESET} across {WHITE}{len(result.changed_symbols)} files{RESET}")
    print(f"  Affected: {WHITE}{result.total_files_affected} files{RESET} | {WHITE}{result.total_symbols_affected} symbols{RESET} impacted")
    print()


def print_risk_summary(risk: dict):
    print(f"  {BOLD}Risk summary{RESET}")
    if risk['critical'] > 0:
        print(f"    {RED}● Critical{RESET}  {risk['critical']}")
    if risk['high'] > 0:
        print(f"    {AMBER}● High{RESET}     {risk['high']}")
    if risk['medium'] > 0:
        print(f"    {BLUE}● Medium{RESET}   {risk['medium']}")
    if risk['low'] > 0:
        print(f"    {GREEN}● Low{RESET}      {risk['low']}")
    print(f"    {MUTED}Max score: {risk['max']}/100 · Avg: {risk['avg']}/100{RESET}")
    print()


def print_blast_nodes(result: BlastRadiusResult, repo_path: str):
    for node in result.blast_nodes:
        score = node.risk_score
        risk_label = 'critical' if score >= 70 else 'high' if score >= 40 else 'medium' if score >= 20 else 'low'
        color = RISK_COLOR[risk_label]

        print(f"  {color}{BOLD}[{risk_label.upper()}]{RESET}  {WHITE}{node.symbol_name}{RESET}  {MUTED}{node.file}{RESET}")
        print(f"  {MUTED}kind={node.kind}  score={RESET}{risk_bar(score)}")

        cov = f"{GREEN}✓ covered{RESET}" if node.has_test_coverage else f"{RED}✗ no tests{RESET}"
        print(f"  coverage: {cov}")

        if node.direct_callers:
            print(f"  {MUTED}Direct callers ({len(node.direct_callers)}):{RESET}")
            for caller in node.direct_callers[:6]:
                c_score = caller.risk_score
                c_color = RISK_COLOR['critical' if c_score >= 70 else 'high' if c_score >= 40 else 'medium' if c_score >= 20 else 'low']
                cov_icon = f"{GREEN}✓{RESET}" if caller.has_test_coverage else f"{RED}✗{RESET}"
                print(f"    {cov_icon} {c_color}●{RESET}  {caller.symbol_name}  {MUTED}{caller.file}:{RESET}")
            if len(node.direct_callers) > 6:
                print(f"    {MUTED}... and {len(node.direct_callers) - 6} more{RESET}")

        print()


def print_uncovered_warning(result: BlastRadiusResult):
    if not result.uncovered_symbols:
        print(f"  {GREEN}✓ All impacted symbols have test coverage{RESET}")
        return

    print(f"  {RED}{BOLD}⚠  Uncovered impact paths ({len(result.uncovered_symbols)}){RESET}")
    print(f"  {MUTED}These callers have no tests — changes here could silently break behaviour:{RESET}")
    for node in result.uncovered_symbols[:8]:
        print(f"    {RED}✗{RESET}  {node.symbol_name}  {MUTED}{node.file}{RESET}")
    print()


def print_critical_paths(result: BlastRadiusResult):
    if not result.critical_paths:
        return
    print(f"  {RED}{BOLD}Critical paths detected{RESET}")
    for path in result.critical_paths[:3]:
        chain = '  →  '.join(n.symbol_name for n in path)
        print(f"    {RED}▶{RESET}  {chain}")
    print()


def build_json_output(result: BlastRadiusResult, repo_path: str) -> dict:
    risk_summary = summarize_risk([
        type('RS', (), {'value': n.risk_score,
                        'label': 'critical' if n.risk_score >= 70 else 'high' if n.risk_score >= 40 else 'medium' if n.risk_score >= 20 else 'low'})()
        for n in result.blast_nodes
    ])
    return {
        'generated': datetime.utcnow().isoformat(),
        'repo': repo_path,
        'summary': {
            'files_changed': len(result.changed_symbols),
            'files_affected': result.total_files_affected,
            'symbols_affected': result.total_symbols_affected,
            'uncovered_paths': len(result.uncovered_symbols),
            'risk': risk_summary,
        },
        'blast_nodes': [
            {
                'symbol': n.symbol_name,
                'file': n.file,
                'kind': n.kind,
                'risk_score': n.risk_score,
                'risk_label': 'critical' if n.risk_score >= 70 else 'high' if n.risk_score >= 40 else 'medium' if n.risk_score >= 20 else 'low',
                'has_test_coverage': n.has_test_coverage,
                'direct_callers': len(n.direct_callers),
                'indirect_callers': len(n.indirect_callers),
                'callers': [
                    {'symbol': c.symbol_name, 'file': c.file, 'has_test': c.has_test_coverage}
                    for c in n.direct_callers
                ],
            }
            for n in result.blast_nodes
        ],
        'uncovered_paths': [
            {'symbol': n.symbol_name, 'file': n.file}
            for n in result.uncovered_symbols
        ],
        'critical_paths': [
            [n.symbol_name for n in path]
            for path in result.critical_paths
        ],
    }


def generate_pr_comment(result: BlastRadiusResult, pr_branch: str) -> str:
    risk_summary = {
        'critical': sum(1 for n in result.blast_nodes if n.risk_score >= 70),
        'high':     sum(1 for n in result.blast_nodes if 40 <= n.risk_score < 70),
    }

    severity = "🔴 Critical" if risk_summary['critical'] > 0 else "🟡 High" if risk_summary['high'] > 0 else "🟢 Low"

    lines = [
        f"## Blast Radius Report — {severity}",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files changed | {len(result.changed_symbols)} |",
        f"| Files affected | {result.total_files_affected} |",
        f"| Symbols impacted | {result.total_symbols_affected} |",
        f"| Uncovered paths | {len(result.uncovered_symbols)} |",
        f"| Critical risk symbols | {risk_summary['critical']} |",
        f"",
    ]

    if result.blast_nodes:
        lines.append("### Changed symbols")
        for node in result.blast_nodes[:10]:
            label = '🔴' if node.risk_score >= 70 else '🟡' if node.risk_score >= 40 else '🔵' if node.risk_score >= 20 else '🟢'
            cov = '✅' if node.has_test_coverage else '❌'
            lines.append(f"- {label} `{node.symbol_name}` — score {node.risk_score}/100 — {len(node.direct_callers)} callers — coverage {cov}")
            lines.append(f"  `{node.file}`")

    if result.uncovered_symbols:
        lines += [
            "",
            "### ⚠️ Uncovered impact paths",
            "These callers have no tests and will be silently affected:",
        ]
        for n in result.uncovered_symbols[:5]:
            lines.append(f"- `{n.symbol_name}` in `{n.file}`")

    if result.critical_paths:
        lines += ["", "### Critical dependency chains"]
        for path in result.critical_paths[:3]:
            chain = ' → '.join(f'`{n.symbol_name}`' for n in path)
            lines.append(f"- {chain}")

    lines += [
        "",
        "---",
        "*Generated by Blast Radius Visualizer · See full flame graph in Actions artifacts*",
    ]

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog='blast-radius',
        description='Blast Radius Visualizer — see what your change breaks before pushing'
    )
    parser.add_argument('--repo', default='.', help='Repo root (default: current directory)')
    parser.add_argument('--pr', metavar='BRANCH', help='Analyse PR diff vs this base branch')
    parser.add_argument('--file', metavar='FILE', help='Analyse a single file change')
    parser.add_argument('--json', action='store_true', help='Output JSON instead of terminal UI')
    parser.add_argument('--report', metavar='PATH', default='blast-radius.html', help='HTML report output path')
    parser.add_argument('--threshold', type=int, default=0, help='Exit 1 if max risk score >= threshold')
    parser.add_argument('--no-report', action='store_true', help='Skip HTML report generation')
    parser.add_argument('--pr-comment', action='store_true', help='Print a GitHub PR comment to stdout')
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)

    # ── Get the diff ──────────────────────────────────────────────────────────
    if args.pr:
        diff_result = get_pr_diff(args.pr, repo_path)
        if not args.json:
            print(f"\n{MUTED}Analysing PR vs '{args.pr}'...{RESET}")
    else:
        diff_result = get_uncommitted_diff(repo_path)
        if not args.json:
            print(f"\n{MUTED}Analysing uncommitted changes...{RESET}")

    if not diff_result.changed_symbols and not diff_result.changed_files:
        print(f"{GREEN}No changed symbols detected. Nothing to analyse.{RESET}")
        sys.exit(0)

    if not args.json:
        print(f"{MUTED}Found {len(diff_result.changed_symbols)} changed symbols in {len(diff_result.changed_files)} files{RESET}")
        print(f"{MUTED}Tracing dependencies across repo...{RESET}")

    # ── Build blast radius ────────────────────────────────────────────────────
    result = build_blast_radius(diff_result.changed_symbols, repo_path)

    # Re-score with full risk engine (the dependency graph has a simpler scorer)
    for node in result.blast_nodes:
        rs = score_symbol(
            symbol_name=node.symbol_name,
            symbol_file=node.file,
            direct_caller_count=len(node.direct_callers),
            indirect_caller_count=len(node.indirect_callers),
            depth=node.depth,
            has_coverage=node.has_test_coverage,
            repo_path=repo_path,
        )
        node.risk_score = rs.value

    # ── Output ────────────────────────────────────────────────────────────────
    if args.json:
        data = build_json_output(result, repo_path)
        print(json.dumps(data, indent=2))
    elif args.pr_comment:
        print(generate_pr_comment(result, args.pr or 'HEAD'))
    else:
        print_header(result, repo_path)

        all_scores = [
            type('RS', (), {'value': n.risk_score,
                            'label': 'critical' if n.risk_score >= 70 else 'high' if n.risk_score >= 40 else 'medium' if n.risk_score >= 20 else 'low'})()
            for n in result.blast_nodes
        ]
        print_risk_summary(summarize_risk(all_scores))
        print_blast_nodes(result, repo_path)
        print_uncovered_warning(result)
        print_critical_paths(result)

        if not args.no_report:
            report_path = os.path.join(repo_path, args.report)
            generate_html_report(result, report_path)
            print(f"  {MUTED}Full report:{RESET} file://{report_path}")
            print()

    # ── Exit code for CI ──────────────────────────────────────────────────────
    if args.threshold > 0:
        max_score = max((n.risk_score for n in result.blast_nodes), default=0)
        if max_score >= args.threshold:
            if not args.json:
                print(f"\n{RED}✗ Max risk score {max_score} ≥ threshold {args.threshold} — failing CI{RESET}")
            sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
