#!/usr/bin/env python3
"""
run_review.py — Orchestrator: incremental scanning + blast-radius prioritization
====================================================================================
Ties together gen_graph.py, gen_graph_java_ts.py, dep-graph.py, and
pattern_detect.py, addressing:

  #2 Incremental scanning — only re-scan files changed since a given git ref
     (default: origin/main...HEAD, or all files on first run).
  #8 Prioritization by blast radius — findings are scored not just by
     severity but by how many other modules/files depend on the affected
     file (fan-in from the dependency graph). A god-class with 50 dependents
     ranks above one with 2.

Output: review-summary.json — a single file the Copilot agentic chat mode
can load to get prioritized, graph-backed findings in one shot.

Usage:
    # Full scan (first run)
    python3 run_review.py <repo_root> --out review-summary.json

    # Incremental — only files changed vs main
    python3 run_review.py <repo_root> --out review-summary.json --since origin/main

    # Incremental — only files changed vs a specific commit/branch
    python3 run_review.py <repo_root> --out review-summary.json --since HEAD~5

No external dependencies — stdlib only. Shells out to `git` if --since is used.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SEVERITY_WEIGHTS = {"Critical": 100, "Major": 50, "Minor": 10}

# Pattern type -> (severity, category) mapping for scoring patterns.json findings
PATTERN_SEVERITY = {
    "n_plus_one_query": ("Major", "Data access design"),
    "blocking_on_async": ("Critical", "Async/concurrency"),
    "async_void": ("Major", "Async/concurrency"),
    "empty_catch": ("Major", "Error handling design"),
    "undisposed_resource": ("Major", "Resource leak"),
    "rxjs_subscription_leak": ("Major", "Resource leak"),
    "god_method": ("Minor", "SRP / god method"),
}


def run_git(args, cwd):
    try:
        result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_changed_files(repo_root, since_ref):
    # Try as a working-tree/staged diff against the ref first (covers
    # uncommitted changes against HEAD or any commit/branch).
    out = run_git(["diff", "--name-only", since_ref], repo_root)
    if out is None or out == "":
        # Try merge-base triple-dot form (covers branch comparisons like origin/main)
        out2 = run_git(["diff", "--name-only", f"{since_ref}...HEAD"], repo_root)
        if out2:
            out = out2
    if out is None:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def run_tool(args, description):
    print(f"--> {description}")
    result = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    if result.returncode != 0 and result.returncode not in (0,):
        print(f"    (exit {result.returncode}) {result.stderr.strip()[:300]}")
    else:
        for line in result.stdout.strip().splitlines()[-6:]:
            print(f"    {line}")
    return result.returncode


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_fan_in_index(dep_graph, entity_graphs):
    """Build a map of file -> fan-in count (how many other files/namespaces
    depend on it), combining dep-graph.json (file/namespace level) and any
    entity-level graphs (gen_graph / gen_graph_java_ts) for injects edges."""
    fan_in = defaultdict(set)

    if dep_graph:
        for v in dep_graph.get("cross_layer_violations", []):
            fan_in[v.get("to_namespace", "")].add(v["from"])
        # node_layers_sample doesn't carry edges, skip

    for g in entity_graphs:
        if not g:
            continue
        # Map node id -> file
        id_to_file = {n["id"]: n.get("file", "") for n in g.get("nodes", [])}
        for e in g.get("edges", []):
            if e["kind"] in ("injects", "inherits", "implements", "has_entity"):
                target_file = id_to_file.get(e["target"])
                source_file = id_to_file.get(e["source"])
                if target_file and source_file:
                    fan_in[target_file].add(source_file)

    return {k: len(v) for k, v in fan_in.items()}


def score_finding(severity, fan_in_count):
    base = SEVERITY_WEIGHTS.get(severity, 10)
    # blast radius multiplier: log-ish scaling so 0 vs 1 dependent matters
    # less than 10 vs 50, but huge fan-in doesn't dwarf everything else.
    multiplier = 1 + min(fan_in_count, 50) / 10
    return round(base * multiplier, 1)


def main():
    parser = argparse.ArgumentParser(description="Run full/incremental design review and produce prioritized summary")
    parser.add_argument("repo_root")
    parser.add_argument("--out", default="review-summary.json")
    parser.add_argument("--since", default=None,
                         help="Git ref to diff against for incremental scanning (e.g. origin/main, HEAD~5)")
    parser.add_argument("--god-method-lines", type=int, default=60)
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    if not os.path.isdir(repo_root):
        print(f"Error: {repo_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    changed_files = None
    changed_files_path = None
    if args.since:
        changed_files = get_changed_files(repo_root, args.since)
        if changed_files is None:
            print(f"Warning: could not compute git diff against '{args.since}'; running full scan")
        elif not changed_files:
            print(f"No files changed vs '{args.since}'. Nothing to scan.")
            with open(args.out, "w") as fh:
                json.dump({"summary": {"note": "no changes"}, "findings": []}, fh, indent=2)
            return
        else:
            changed_files_path = os.path.join(repo_root, ".review_changed_files.txt")
            with open(changed_files_path, "w") as fh:
                fh.write("\n".join(changed_files))
            print(f"Incremental scan: {len(changed_files)} changed files")

    out_dir = os.path.dirname(os.path.abspath(args.out)) or repo_root
    os.makedirs(out_dir, exist_ok=True)

    cs_graph_path = os.path.join(out_dir, "codebase-graph.json")
    java_ts_graph_path = os.path.join(out_dir, "java-ts-graph.json")
    dep_graph_path = os.path.join(out_dir, "dep-graph.json")
    patterns_path = os.path.join(out_dir, "patterns.json")

    # 1. C# entity graph (full scan only — gen_graph.py doesn't support --changed-files)
    has_cs = any(f.endswith(".cs") for _, _, files in os.walk(repo_root) for f in files)
    if has_cs:
        run_tool([os.path.join(SCRIPT_DIR, "dependency-graph", "gen_graph.py"), "--root", repo_root,
                  "--output", cs_graph_path], "Building C# entity graph")

    # 2. Java/TS entity graph (supports incremental)
    has_java = any(f in ("pom.xml", "build.gradle") for _, _, files in os.walk(repo_root) for f in files)
    has_ts = any(f.endswith((".ts", ".tsx")) for _, _, files in os.walk(repo_root) for f in files)
    if has_java or has_ts:
        lang = "both" if (has_java and has_ts) else ("java" if has_java else "ts")
        ja_args = [os.path.join(SCRIPT_DIR, "dependency-graph", "gen_graph_java_ts.py"), repo_root, "--lang", lang,
                   "--out", java_ts_graph_path]
        if changed_files_path:
            ja_args += ["--changed-files", changed_files_path]
        run_tool(ja_args, "Building Java/Angular entity graph")

    # 3. Cross-language dependency/layer graph (full scan only — folder-level analysis)
    run_tool([os.path.join(SCRIPT_DIR, "dependency-graph", "dep-graph.py"), repo_root, "--out", dep_graph_path],
             "Building cross-language dependency graph")

    # 4. Behavioral pattern detection (supports incremental)
    pd_args = [os.path.join(SCRIPT_DIR, "dependency-graph", "pattern_detect.py"), repo_root,
               "--out", patterns_path, "--god-method-lines", str(args.god_method_lines)]
    if changed_files_path:
        pd_args += ["--changed-files", changed_files_path]
    run_tool(pd_args, "Detecting behavioral patterns (N+1, blocking async, leaks, etc.)")

    # 5. Combine + prioritize
    cs_graph = load_json(cs_graph_path)
    java_ts_graph = load_json(java_ts_graph_path)
    dep_graph = load_json(dep_graph_path)
    patterns = load_json(patterns_path)

    fan_in = build_fan_in_index(dep_graph, [cs_graph, java_ts_graph])

    findings = []

    # Behavioral pattern findings
    if patterns:
        for f in patterns.get("findings", []):
            severity, category = PATTERN_SEVERITY.get(f["type"], ("Minor", "Other"))
            fi = fan_in.get(f["file"], 0)
            findings.append({
                "title": f["type"].replace("_", " ").title(),
                "location": f"{f['file']}:{f.get('line', f.get('lines', ['?'])[0])}",
                "category": category,
                "severity": severity,
                "fan_in": fi,
                "score": score_finding(severity, fi),
                "detail": f["detail"],
                "method": f.get("method", ""),
            })

    # Cross-layer violations from dep-graph
    if dep_graph:
        for v in dep_graph.get("cross_layer_violations", []):
            fi = fan_in.get(v.get("to_namespace", ""), 0)
            findings.append({
                "title": f"Layering violation: {v['from_layer']} -> {v['to_layer']}",
                "location": v["from"],
                "category": "Layering / dependency direction",
                "severity": "Major",
                "fan_in": fi,
                "score": score_finding("Major", fi),
                "detail": v["reason"],
                "method": "",
            })
        for cyc in dep_graph.get("cycles", []):
            findings.append({
                "title": "Circular dependency",
                "location": " -> ".join(cyc["namespaces"]),
                "category": "Layering / dependency direction",
                "severity": "Major",
                "fan_in": 0,
                "score": score_finding("Major", 0),
                "detail": "Circular dependency detected between modules/namespaces",
                "method": "",
            })
        for hc in dep_graph.get("high_coupling_modules", []):
            findings.append({
                "title": f"High coupling module: {hc['namespace_or_folder']}",
                "location": hc["namespace_or_folder"],
                "category": "Coupling / god module",
                "severity": "Minor" if hc["total_coupling"] < 15 else "Major",
                "fan_in": hc["fan_in"],
                "score": score_finding("Minor" if hc["total_coupling"] < 15 else "Major", hc["fan_in"]),
                "detail": f"fan_in={hc['fan_in']}, fan_out={hc['fan_out']}, total={hc['total_coupling']}",
                "method": "",
            })

    findings.sort(key=lambda x: -x["score"])

    summary = {
        "scan_type": "incremental" if changed_files else "full",
        "changed_files": changed_files,
        "total_findings": len(findings),
        "graphs_used": {
            "csharp_entity_graph": cs_graph is not None,
            "java_ts_entity_graph": java_ts_graph is not None,
            "dependency_graph": dep_graph is not None,
            "behavioral_patterns": patterns is not None,
        },
        "findings": findings,
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    if changed_files_path and os.path.exists(changed_files_path):
        os.remove(changed_files_path)

    print(f"\nWrote {args.out}")
    print(f"  Total prioritized findings: {len(findings)}")
    print(f"  Top 5 by score:")
    for f in findings[:5]:
        print(f"    [{f['score']:6.1f}] {f['severity']:8s} {f['title']} ({f['location']})")


if __name__ == "__main__":
    main()
