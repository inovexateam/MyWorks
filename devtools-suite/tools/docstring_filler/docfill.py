"""
Docstring Auto-Filler — CLI entry point.

Usage:
  python docfill.py                          # scan + preview (dry run)
  python docfill.py --apply                  # scan + write to files
  python docfill.py --repo /path             # specific repo
  python docfill.py --lang csharp            # single language
  python docfill.py --limit 50               # cap at N symbols
  python docfill.py --min-confidence 0.7     # skip low-confidence
  python docfill.py --json                   # JSON output
  python docfill.py --report                 # HTML coverage report

Set OPENAI_API_KEY (or GITHUB_TOKEN for Copilot) to enable AI generation.
Without a key, falls back to rule-based generation.
"""

import argparse
import json
import os
import sys
from datetime import datetime

from scanner.doc_scanner import scan_repo
from generator.doc_generator import generate_batch
from generator.file_patcher import apply_all
from reporters.html_reporter import generate_html_report
from core.models import MissingDoc, GeneratedDoc

RESET = '\033[0m'; BOLD = '\033[1m'
RED   = '\033[91m'; AMBER = '\033[93m'; GREEN = '\033[92m'; MUTED = '\033[90m'


def print_summary(missing: list[MissingDoc], generated: list[GeneratedDoc], stats: dict):
    by_lang: dict[str, int] = {}
    for m in missing:
        by_lang[m.language] = by_lang.get(m.language, 0) + 1

    ai_count   = sum(1 for g in generated if g.confidence >= 0.7)
    rule_count = len(generated) - ai_count

    print(f"\n{BOLD}{'─'*55}{RESET}")
    print(f"{BOLD}  Docstring Auto-Filler{RESET}  {MUTED}{datetime.now().strftime('%Y-%m-%d %H:%M')}{RESET}")
    print(f"{'─'*55}")
    print(f"  Missing docs:      {RED}{len(missing)}{RESET}")
    for lang, count in by_lang.items():
        print(f"    {lang:12}   {count}")
    print(f"  Generated:         {GREEN}{len(generated)}{RESET}  "
          f"({ai_count} AI, {rule_count} rule-based)")
    if stats.get("docs_applied"):
        print(f"  Applied:           {GREEN}{stats['docs_applied']}{RESET}  "
              f"across {stats['files_modified']} files")
    print()


def main():
    parser = argparse.ArgumentParser(prog='docfill', description='Docstring Auto-Filler')
    parser.add_argument('--repo',           default='.')
    parser.add_argument('--apply',          action='store_true', help='Write to files (default: dry run)')
    parser.add_argument('--lang',           choices=['csharp','java','angular','all'], default='all')
    parser.add_argument('--limit',          type=int, default=100, help='Max symbols to process')
    parser.add_argument('--min-confidence', type=float, default=0.0)
    parser.add_argument('--json',           action='store_true')
    parser.add_argument('--report',         action='store_true', help='Generate HTML coverage report')
    parser.add_argument('--report-path',    default='docstring-report.html')
    parser.add_argument('--model',          default='gpt-4o-mini')
    args = parser.parse_args()

    repo_path  = os.path.abspath(args.repo)
    api_key    = os.environ.get("OPENAI_API_KEY") or os.environ.get("GITHUB_TOKEN", "")
    verbose    = not args.json

    # ── Scan ──────────────────────────────────────────────────────────────────
    if verbose:
        print(f"\n{BOLD}Docstring Auto-Filler{RESET}  {MUTED}{repo_path}{RESET}")
        print(f"{MUTED}Scanning for missing docs...{RESET}")

    missing = scan_repo(repo_path, verbose=verbose)

    if args.lang != 'all':
        lang_map = {'csharp': 'csharp', 'java': 'java', 'angular': 'angular'}
        missing = [m for m in missing if m.language == lang_map.get(args.lang)]

    if verbose:
        print(f"  {len(missing)} symbols missing documentation")

    if not missing:
        print(f"{GREEN}All public symbols are documented!{RESET}")
        sys.exit(0)

    # ── Generate ──────────────────────────────────────────────────────────────
    if verbose:
        mode = "AI (model: " + args.model + ")" if api_key else "rule-based (no API key)"
        print(f"{MUTED}Generating docstrings [{mode}]...{RESET}")

    generated = generate_batch(
        missing, api_key=api_key, model=args.model,
        max_symbols=args.limit, verbose=verbose,
    )

    # ── Apply / dry run ───────────────────────────────────────────────────────
    dry_run = not args.apply
    stats   = apply_all(generated, repo_path, dry_run=dry_run,
                        min_confidence=args.min_confidence)

    # ── Output ────────────────────────────────────────────────────────────────
    if args.json:
        data = {
            "generated":    datetime.utcnow().isoformat(),
            "missing_count": len(missing),
            "generated_count": len(generated),
            "applied":      stats.get("docs_applied", 0),
            "files_modified": stats.get("files_modified", 0),
            "dry_run":      dry_run,
            "symbols": [
                {
                    "name":       g.symbol.name,
                    "file":       g.symbol.file,
                    "line":       g.symbol.line,
                    "kind":       g.symbol.kind,
                    "language":   g.symbol.language,
                    "confidence": g.confidence,
                    "docstring":  g.docstring,
                }
                for g in generated
            ],
        }
        print(json.dumps(data, indent=2))
        return

    print_summary(missing, generated, stats)

    if dry_run and generated:
        print(f"{AMBER}Dry run — use --apply to write to files{RESET}\n")
        # Show first few previews
        for doc in generated[:3]:
            print(f"  {MUTED}{doc.symbol.file}:{doc.symbol.line}{RESET}  {doc.symbol.name}")
            for line in doc.docstring.split('\n'):
                print(f"  {GREEN}+{RESET} {line}")
            print()
        if len(generated) > 3:
            print(f"  {MUTED}...and {len(generated)-3} more{RESET}\n")

    if args.report or args.apply:
        report_path = os.path.join(repo_path, args.report_path)
        generate_html_report(missing, generated, stats, report_path)
        print(f"  {MUTED}Report:{RESET} file://{report_path}\n")


if __name__ == '__main__':
    main()
