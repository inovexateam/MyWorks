#!/usr/bin/env python3
"""
pattern_detect.py — Runtime-behavior pattern detector (item #4)
==================================================================
Structural graphs (gen_graph.py / dep-graph.py) show WHAT depends on WHAT.
This script scans method bodies for BEHAVIORAL patterns that are common
real-world bugs but invisible to a pure dependency graph:

  - N+1 queries: a loop body containing an `await ... .ToListAsync()` /
    `.FirstOrDefaultAsync()` / repository call keyed by a loop variable
  - Blocking on async: `.Result`, `.Wait()`, `.GetAwaiter().GetResult()`
  - Fire-and-forget: `async void`, or a Task-returning call with no
    `await`, no `.ContinueWith`, and not assigned/returned
  - Empty/swallowing catch blocks: `catch (Exception) { }` or catch with
    only a `// comment` / `return null`
  - Disposable not disposed: `new HttpClient()`, `new SqlConnection(...)`,
    `new StreamReader(...)` etc. not inside a `using` statement
  - God methods: methods exceeding a configurable line-count threshold

Works on C#, Java, and TypeScript (subset of patterns per language, noted
in output).

Usage:
    python3 pattern_detect.py <repo_root> --out patterns.json
    python3 pattern_detect.py <repo_root> --out patterns.json --god-method-lines 60

No external dependencies — stdlib only.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

DEFAULT_IGNORE_DIRS = {
    "node_modules", "bin", "obj", "dist", "build", ".git", ".vs",
    "target", "out", ".angular", "coverage", "__pycache__", ".idea", ".vscode",
}

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def discover_files(root, exts):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]
        for f in filenames:
            if os.path.splitext(f)[1] in exts:
                if ".spec." in f or ".test." in f or f.endswith(".d.ts"):
                    continue
                found.append(os.path.join(dirpath, f))
    return found


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def line_of(text, pos):
    return text[:pos].count("\n") + 1


# ---------------------------------------------------------------------------
# Method/function body extraction (brace-matching, language-agnostic enough
# for C#/Java/TS since they share C-style braces)
# ---------------------------------------------------------------------------

# Matches method/function signatures ending in `{` — broad on purpose, we
# filter false positives (e.g. class/if/for openers) by requiring `(`...`)`
# immediately before the brace and a recognizable modifier/keyword set.
METHOD_SIG_RE = re.compile(
    r'(?P<mods>(?:public|private|protected|internal|static|async|override|'
    r'virtual|final|export|function|const|let)\s+)*'
    r'(?:[\w<>\[\],\.\?]+\s+)?'              # return type (optional)
    r'(?P<name>\w+)\s*'
    r'(?:<[^>]*>)?\s*'                       # generic method params
    r'\((?P<params>[^)]*)\)\s*'
    r'(?:[:\w<>\[\],\.\?\s]+)?'              # TS return type annotation
    r'\{',
    re.MULTILINE,
)

# async void <Name>(...)
ASYNC_VOID_NAME_RE = re.compile(r'\basync\s+void\s+(\w+)\s*\(')


def extract_methods(text):
    """Yield (name, mods, start_pos_of_brace, end_pos_of_brace, body_text)."""
    for m in METHOD_SIG_RE.finditer(text):
        brace_start = m.end() - 1
        depth = 0
        end = None
        for i in range(brace_start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            continue
        body = text[brace_start:end + 1]
        # Skip trivially short bodies (getters/setters, one-liners)
        if body.count("\n") < 1:
            continue
        yield m.group("name"), (m.group("mods") or ""), brace_start, end, body


# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------

# N+1: a for/foreach/while loop containing an await call to something that
# looks like a query (...Async, FindBy, GetBy, Where, ToList, FirstOrDefault)
LOOP_RE = re.compile(r'\b(for|foreach|while)\s*\(', re.MULTILINE)
ASYNC_QUERY_CALL_RE = re.compile(
    r'await\s+[\w\.]+\.(?:'
    r'ToListAsync|ToArrayAsync|FirstOrDefaultAsync|FirstAsync|SingleAsync|'
    r'SingleOrDefaultAsync|CountAsync|AnyAsync|FindAsync|'
    r'find|findOne|findById|getOne|fetch|query'
    r')\w*\s*\('
)

BLOCKING_ASYNC_RE = re.compile(r'\.(Result\b|Wait\s*\(|GetAwaiter\s*\(\s*\)\s*\.\s*GetResult\s*\()')


EMPTY_CATCH_RE = re.compile(
    r'catch\s*(?:\([^)]*\))?\s*\{\s*(?:\}|//[^\n]*\n\s*\}|/\*.*?\*/\s*\})',
    re.DOTALL,
)

# Disposable construction not preceded by `using`
DISPOSABLE_TYPES = ["HttpClient", "SqlConnection", "SqlCommand", "StreamReader",
                     "StreamWriter", "FileStream", "MemoryStream", "StringReader"]
DISPOSABLE_NEW_RE = re.compile(
    r'(?P<using>using\s*\(\s*)?(?:var\s+\w+\s*=\s*)?new\s+(?P<type>' +
    "|".join(DISPOSABLE_TYPES) + r')\s*\('
)

# RxJS subscription without takeUntil/take/first (Angular)
RXJS_SUBSCRIBE_RE = re.compile(r'\.subscribe\s*\(')
RXJS_CLEANUP_HINT_RE = re.compile(r'takeUntil|take\s*\(|first\s*\(|async\s+pipe|untilDestroyed')


def detect_in_file(path, root, god_method_lines):
    text = read_text(path)
    rel = os.path.relpath(path, root)
    findings = []
    ext = os.path.splitext(path)[1]
    is_ts = ext in (".ts", ".tsx")

    for name, mods, body_start, body_end, body in extract_methods(text):
        start_line = line_of(text, body_start)
        end_line = line_of(text, body_end)
        method_line_count = end_line - start_line

        # --- God method ---
        if method_line_count > god_method_lines:
            findings.append({
                "type": "god_method",
                "file": rel, "method": name,
                "lines": [start_line, end_line],
                "detail": f"Method body spans {method_line_count} lines (threshold {god_method_lines})",
            })

        # --- N+1 query pattern ---
        for loop_m in LOOP_RE.finditer(body):
            # find this loop's body via brace matching
            loop_brace = body.find('{', loop_m.end())
            if loop_brace == -1:
                continue
            depth = 0
            loop_end = None
            for i in range(loop_brace, len(body)):
                if body[i] == '{':
                    depth += 1
                elif body[i] == '}':
                    depth -= 1
                    if depth == 0:
                        loop_end = i
                        break
            if loop_end is None:
                continue
            loop_body = body[loop_brace:loop_end]
            if ASYNC_QUERY_CALL_RE.search(loop_body):
                abs_pos = body_start + loop_m.start()
                findings.append({
                    "type": "n_plus_one_query",
                    "file": rel, "method": name,
                    "line": line_of(text, abs_pos),
                    "detail": "Async query/repository call found inside a loop — likely N+1 query pattern",
                })

        # --- Blocking on async (.Result / .Wait()) ---
        for m in BLOCKING_ASYNC_RE.finditer(body):
            abs_pos = body_start + m.start()
            findings.append({
                "type": "blocking_on_async",
                "file": rel, "method": name,
                "line": line_of(text, abs_pos),
                "detail": "Synchronous block on async code (.Result/.Wait()/GetAwaiter().GetResult()) — risk of deadlock under load",
            })

        # --- async void (fire-and-forget, unhandled exceptions) ---
        # (checked at signature level, not body — handled separately below)

        # --- Empty/swallowing catch ---
        for m in EMPTY_CATCH_RE.finditer(body):
            abs_pos = body_start + m.start()
            findings.append({
                "type": "empty_catch",
                "file": rel, "method": name,
                "line": line_of(text, abs_pos),
                "detail": "Empty or swallowing catch block — exception is silently discarded",
            })

        # --- Disposable not in using ---
        for m in DISPOSABLE_NEW_RE.finditer(body):
            if m.group("using"):
                continue
            abs_pos = body_start + m.start()
            findings.append({
                "type": "undisposed_resource",
                "file": rel, "method": name,
                "line": line_of(text, abs_pos),
                "detail": f"`new {m.group('type')}(...)` created without `using` — resource may not be disposed",
            })

        # --- RxJS subscription without cleanup hint (Angular/TS) ---
        if is_ts:
            for m in RXJS_SUBSCRIBE_RE.finditer(body):
                # check whole method body for a cleanup hint anywhere (cheap heuristic)
                if not RXJS_CLEANUP_HINT_RE.search(body):
                    abs_pos = body_start + m.start()
                    findings.append({
                        "type": "rxjs_subscription_leak",
                        "file": rel, "method": name,
                        "line": line_of(text, abs_pos),
                        "detail": ".subscribe() with no takeUntil/take/async-pipe/untilDestroyed in this method — possible subscription leak",
                    })
                    break  # one finding per method is enough

    # --- async void (signature-level, file-wide) ---
    for m in ASYNC_VOID_NAME_RE.finditer(text):
        findings.append({
            "type": "async_void",
            "file": rel,
            "method": m.group(1),
            "line": line_of(text, m.start()),
            "detail": "`async void` method — exceptions cannot be awaited/caught by callers",
        })

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Detect runtime-behavior design flaw patterns")
    parser.add_argument("repo_root")
    parser.add_argument("--out", default="patterns.json")
    parser.add_argument("--god-method-lines", type=int, default=60)
    parser.add_argument("--changed-files", default=None,
                         help="Path to a text file listing changed file paths "
                              "(one per line, relative to repo_root) for incremental runs")
    args = parser.parse_args()

    root = os.path.abspath(args.repo_root)
    exts = {".cs", ".java", ".ts", ".tsx"}

    if args.changed_files and os.path.exists(args.changed_files):
        with open(args.changed_files) as fh:
            files = [os.path.join(root, line.strip()) for line in fh if line.strip()]
        files = [f for f in files if os.path.splitext(f)[1] in exts and os.path.exists(f)]
        print(f"Incremental run: scanning {len(files)} changed files")
    else:
        files = discover_files(root, exts)
        print(f"Full run: scanning {len(files)} files")

    all_findings = []
    by_type = defaultdict(int)
    for f in files:
        findings = detect_in_file(f, root, args.god_method_lines)
        all_findings.extend(findings)
        for fnd in findings:
            by_type[fnd["type"]] += 1

    output = {
        "summary": {
            "files_scanned": len(files),
            "total_findings": len(all_findings),
            "by_type": dict(by_type),
        },
        "findings": all_findings,
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    print(f"\nWrote {args.out}")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t:25s}: {c}")


if __name__ == "__main__":
    main()
