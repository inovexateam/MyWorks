#!/usr/bin/env python3
"""
DevTools Suite — unified CLI.

Usage:
  python devtools.py blast-radius   [--pr main] [--report] [--json]
  python devtools.py assumption     [scan .] [--pr main] [show --risk high]
  python devtools.py arch-drift     [--init] [--pr main] [--timeline]
  python devtools.py cross-pr       [--pr 42] [--comment 42] [--json]
  python devtools.py dead-code      [--confidence high] [--no-graph]
  python devtools.py flag-graveyard [--plans] [--show simple]
  python devtools.py knowledge      [--wiki] [--gaps] [--pairings]
  python devtools.py docfill        [--apply] [--min-confidence 0.7]
  python devtools.py all            # run all tools, generate all reports
"""

import sys
import os

TOOLS = {
    "blast-radius":   ("tools.blast_radius.blast_radius",   "main"),
    "assumption":     ("tools.assumption_miner.assume_miner", "main"),
    "arch-drift":     ("tools.arch_drift.arch_drift",        "main"),
    "cross-pr":       ("tools.cross_pr.cross_pr",            "main"),
    "dead-code":      ("tools.dead_code.dead_code",          "main"),
    "flag-graveyard": ("tools.flag_graveyard.flag_graveyard","main"),
    "knowledge":      ("tools.knowledge_extractor.knowledge_extractor", "main"),
    "docfill":        ("tools.docstring_filler.docfill",     "main"),
}

ALL_QUICK = [
    ("blast-radius",   ["--no-report", "--json"]),
    ("dead-code",      ["--no-report", "--json"]),
    ("flag-graveyard", ["--no-report", "--json"]),
    ("knowledge",      ["--no-report", "--json"]),
    ("docfill",        ["--json"]),
]

BOLD = "\033[1m"; RESET = "\033[0m"; BLU = "\033[94m"; MU = "\033[90m"; GRN = "\033[92m"

def usage():
    print(f"""
{BOLD}DevTools Suite{RESET}  — 8 tools for C#, Java & Angular

{BLU}Tools:{RESET}
  blast-radius    Trace blast radius of your changes
  assumption      Surface implicit code assumptions
  arch-drift      Detect architectural drift over time
  cross-pr        Find cross-PR dependency conflicts
  dead-code       Find and remove unreachable code
  flag-graveyard  Hunt dead feature flags
  knowledge       Map who knows what (bus factor)
  docfill         Auto-fill missing docstrings
  all             Quick scan with all tools

{BLU}Examples:{RESET}
  python devtools.py blast-radius --pr main
  python devtools.py assumption scan . --pr main
  python devtools.py arch-drift --init
  python devtools.py dead-code --confidence high
  python devtools.py flag-graveyard --plans
  python devtools.py knowledge --wiki
  python devtools.py docfill --apply --min-confidence 0.7
  python devtools.py all
""")

def run_tool(name: str, args: list[str]):
    mod_path, fn_name = TOOLS[name]
    # Add tool's own directory to sys.path so internal imports work
    parts = mod_path.split(".")
    tool_dir = os.path.join(os.path.dirname(__file__), *parts[:2])
    if tool_dir not in sys.path:
        sys.path.insert(0, tool_dir)

    # Also ensure project root is in path
    root = os.path.dirname(__file__)
    if root not in sys.path:
        sys.path.insert(0, root)

    old_argv = sys.argv
    sys.argv = [mod_path] + args
    try:
        import importlib
        mod = importlib.import_module(mod_path)
        importlib.reload(mod)
        getattr(mod, fn_name)()
    except SystemExit:
        pass
    finally:
        sys.argv = old_argv
        # Remove tool dir from path to avoid collisions
        if tool_dir in sys.path:
            sys.path.remove(tool_dir)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        usage()
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "all":
        print(f"\n{BOLD}Running all tools...{RESET}\n")
        for name, quick_args in ALL_QUICK:
            print(f"{BLU}▶ {name}{RESET}")
            try:
                run_tool(name, quick_args)
            except Exception as e:
                print(f"  {MU}skipped: {e}{RESET}")
        print(f"\n{GRN}Done. Open individual HTML reports or index.html{RESET}\n")
        return

    if cmd not in TOOLS:
        print(f"Unknown tool: {cmd}\nRun: python devtools.py --help")
        sys.exit(1)

    run_tool(cmd, args)


if __name__ == "__main__":
    main()
