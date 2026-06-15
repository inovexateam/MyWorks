#!/usr/bin/env python3
"""
dep-graph.py — Lightweight multi-language dependency graph builder.

Produces a JSON graph of module/namespace-level dependencies for:
  - .NET / C# (via `using` statements + namespace declarations)
  - Java (via `import` statements + package declarations)
  - Angular / TypeScript (via ES `import` statements + folder structure)

This is NOT a full compiler-level analysis (that requires Roslyn/JavaParser/
ts-morph with project loading). It's a fast, dependency-free, regex/AST-lite
scanner that gives "ground truth" structural facts:
  - which file imports/depends on which
  - which layer/module each file belongs to (inferred from path)
  - detected cross-layer or cyclic dependencies

The output JSON is meant to be attached to a Copilot Chat conversation
(or read by the chat mode) so the LLM reasons about REAL edges instead of
inferring them from limited context.

Usage:
    python3 dep-graph.py <repo_root> [--out graph.json] [--layers core,domain,application,infrastructure,api,controllers]

No external dependencies — stdlib only.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Language configs
# ---------------------------------------------------------------------------

CS_EXT = {".cs"}
JAVA_EXT = {".java"}
TS_EXT = {".ts", ".tsx"}

CS_USING_RE = re.compile(r'^\s*using\s+([\w\.]+)\s*;', re.MULTILINE)
CS_NAMESPACE_RE = re.compile(r'^\s*namespace\s+([\w\.]+)', re.MULTILINE)

JAVA_IMPORT_RE = re.compile(r'^\s*import\s+(?:static\s+)?([\w\.]+)(?:\.\*)?\s*;', re.MULTILINE)
JAVA_PACKAGE_RE = re.compile(r'^\s*package\s+([\w\.]+)\s*;', re.MULTILINE)

TS_IMPORT_RE = re.compile(
    r'^\s*import\s+(?:type\s+)?(?:[\w*\s{},]+from\s+)?["\']([^"\']+)["\']',
    re.MULTILINE,
)

DEFAULT_IGNORE_DIRS = {
    "node_modules", "bin", "obj", "dist", "build", ".git", ".vs",
    "target", "out", ".angular", "coverage", "__pycache__", ".idea", ".vscode",
}

# Default layer keywords (path segment -> layer name), used to flag
# cross-layer dependency violations heuristically.
DEFAULT_LAYER_ORDER = ["controllers", "api", "application", "service", "services",
                       "domain", "core", "infrastructure", "repository", "repositories",
                       "data", "shared", "feature", "features"]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files(root):
    found = {"cs": [], "java": [], "ts": []}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]
        for f in filenames:
            ext = os.path.splitext(f)[1]
            full = os.path.join(dirpath, f)
            if ext in CS_EXT:
                found["cs"].append(full)
            elif ext in JAVA_EXT:
                found["java"].append(full)
            elif ext in TS_EXT and not f.endswith(".d.ts") and ".spec." not in f and ".test." not in f:
                found["ts"].append(full)
    return found


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Per-language extraction
# ---------------------------------------------------------------------------

def extract_cs(files, root):
    nodes = {}
    edges = []
    namespace_to_files = defaultdict(list)

    for path in files:
        text = read_text(path)
        ns_match = CS_NAMESPACE_RE.search(text)
        namespace = ns_match.group(1) if ns_match else "(global)"
        rel = os.path.relpath(path, root)
        nodes[rel] = {"namespace": namespace, "language": "csharp"}
        namespace_to_files[namespace].append(rel)

        for m in CS_USING_RE.finditer(text):
            target_ns = m.group(1)
            if target_ns.startswith(("System", "Microsoft", "Newtonsoft", "AutoMapper",
                                      "FluentValidation", "Xunit", "Moq", "NUnit")):
                continue
            edges.append({"from": rel, "from_namespace": namespace,
                           "to_namespace": target_ns, "kind": "using"})
    return nodes, edges, namespace_to_files


def extract_java(files, root):
    nodes = {}
    edges = []
    package_to_files = defaultdict(list)

    for path in files:
        text = read_text(path)
        pkg_match = JAVA_PACKAGE_RE.search(text)
        package = pkg_match.group(1) if pkg_match else "(default)"
        rel = os.path.relpath(path, root)
        nodes[rel] = {"namespace": package, "language": "java"}
        package_to_files[package].append(rel)

        for m in JAVA_IMPORT_RE.finditer(text):
            target_pkg = m.group(1)
            if target_pkg.startswith(("java.", "javax.", "org.springframework",
                                       "lombok", "org.junit", "org.mockito", "jakarta.")):
                continue
            edges.append({"from": rel, "from_namespace": package,
                           "to_namespace": target_pkg, "kind": "import"})
    return nodes, edges, package_to_files


def extract_ts(files, root):
    nodes = {}
    edges = []

    for path in files:
        text = read_text(path)
        rel = os.path.relpath(path, root)
        folder = os.path.dirname(rel)
        nodes[rel] = {"namespace": folder, "language": "typescript"}

        for m in TS_IMPORT_RE.finditer(text):
            target = m.group(1)
            if not target.startswith("."):
                continue  # skip node_modules / absolute package imports
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            resolved_rel = os.path.relpath(resolved, root)
            edges.append({"from": rel, "from_namespace": folder,
                           "to_namespace": os.path.dirname(resolved_rel), "kind": "import",
                           "to_file_hint": resolved_rel})
    return nodes, edges, None


# ---------------------------------------------------------------------------
# Layer inference + cross-layer / cycle detection
# ---------------------------------------------------------------------------

def infer_layer(path_or_ns):
    lowered = path_or_ns.lower().replace("\\", "/")
    for layer in DEFAULT_LAYER_ORDER:
        if f"/{layer}/" in f"/{lowered}/" or lowered.startswith(layer) or f".{layer}." in lowered:
            return layer
    return "(unclassified)"


def layer_rank(layer):
    order = {
        "controllers": 0, "api": 0,
        "application": 1, "service": 1, "services": 1, "feature": 1, "features": 1,
        "domain": 2, "core": 2,
        "infrastructure": 3, "repository": 3, "repositories": 3, "data": 3,
        "shared": 1,
        "(unclassified)": -1,
    }
    return order.get(layer, -1)


def find_cross_layer_violations(edges, node_layers):
    """A 'violation' here = a dependency that points from a lower-numbered
    (outer) layer's dependency on something it shouldn't reach, OR a higher
    layer depending back on a lower-numbered (outer) layer -> inverted
    dependency direction (the classic 'domain depends on infrastructure'
    or 'core depends on UI' smell)."""
    violations = []
    for e in edges:
        from_layer = node_layers.get(e["from"], "(unclassified)")
        to_ns_or_file = e.get("to_file_hint") or e["to_namespace"]
        to_layer = infer_layer(to_ns_or_file)

        fr, tr = layer_rank(from_layer), layer_rank(to_layer)
        if fr == -1 or tr == -1:
            continue
        # Inverted dependency: an inner layer (domain/core, rank 2) depends
        # on an outer layer (controllers/api, rank 0) or infrastructure (3)
        if from_layer in ("domain", "core") and to_layer in ("controllers", "api", "infrastructure", "repository", "repositories", "data"):
            violations.append({**e, "from_layer": from_layer, "to_layer": to_layer,
                                "reason": "Inner layer (domain/core) depends on outer/infrastructure layer"})
        # Controller depending directly on repository/data, skipping service layer
        elif from_layer in ("controllers", "api") and to_layer in ("repository", "repositories", "data"):
            violations.append({**e, "from_layer": from_layer, "to_layer": to_layer,
                                "reason": "Controller/API depends directly on data/repository layer, bypassing service layer"})
    return violations


def find_simple_cycles(edges, max_report=30):
    """Detect cycles at namespace/folder granularity using DFS. Returns a
    list of cycles (list of namespace names), capped at max_report."""
    graph = defaultdict(set)
    for e in edges:
        a, b = e["from_namespace"], e.get("to_namespace") or e.get("to_file_hint")
        if a and b and a != b:
            graph[a].add(b)

    visited = set()
    stack = []
    on_stack = set()
    cycles = []

    def dfs(node):
        if len(cycles) >= max_report:
            return
        visited.add(node)
        stack.append(node)
        on_stack.add(node)
        for nxt in graph.get(node, []):
            if nxt in on_stack:
                idx = stack.index(nxt)
                cycle = stack[idx:] + [nxt]
                if cycle not in cycles:
                    cycles.append(cycle)
            elif nxt not in visited:
                dfs(nxt)
        stack.pop()
        on_stack.discard(node)

    for n in list(graph.keys()):
        if n not in visited:
            dfs(n)
    return cycles[:max_report]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build a lightweight cross-language dependency graph")
    parser.add_argument("repo_root", help="Path to repo root (or subfolder to scan)")
    parser.add_argument("--out", default="dep-graph.json", help="Output JSON path")
    args = parser.parse_args()

    root = os.path.abspath(args.repo_root)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    files = discover_files(root)
    print(f"Found: {len(files['cs'])} C# files, {len(files['java'])} Java files, {len(files['ts'])} TS files")

    all_nodes = {}
    all_edges = []

    if files["cs"]:
        nodes, edges, _ = extract_cs(files["cs"], root)
        all_nodes.update(nodes)
        all_edges.extend(edges)
    if files["java"]:
        nodes, edges, _ = extract_java(files["java"], root)
        all_nodes.update(nodes)
        all_edges.extend(edges)
    if files["ts"]:
        nodes, edges, _ = extract_ts(files["ts"], root)
        all_nodes.update(nodes)
        all_edges.extend(edges)

    node_layers = {path: infer_layer(path) for path in all_nodes}

    violations = find_cross_layer_violations(all_edges, node_layers)
    cycles = find_simple_cycles(all_edges)

    # Build a per-namespace fan-in/fan-out summary (god-module hint)
    fan_out = defaultdict(set)
    fan_in = defaultdict(set)
    for e in all_edges:
        to_key = e.get("to_namespace") or e.get("to_file_hint") or ""
        fan_out[e["from_namespace"]].add(to_key)
        fan_in[to_key].add(e["from_namespace"])

    coupling_summary = []
    for ns in set(list(fan_out.keys()) + list(fan_in.keys())):
        out_c, in_c = len(fan_out.get(ns, [])), len(fan_in.get(ns, []))
        if out_c + in_c >= 8:  # arbitrary "worth looking at" threshold
            coupling_summary.append({"namespace_or_folder": ns, "fan_out": out_c, "fan_in": in_c,
                                      "total_coupling": out_c + in_c})
    coupling_summary.sort(key=lambda x: -x["total_coupling"])

    output = {
        "summary": {
            "total_files": len(all_nodes),
            "total_edges": len(all_edges),
            "cross_layer_violations": len(violations),
            "cycles_detected": len(cycles),
            "high_coupling_modules": len(coupling_summary),
        },
        "layer_inference_note": (
            "Layers were inferred from path/namespace keywords "
            f"({', '.join(DEFAULT_LAYER_ORDER)}). Review 'node_layers' for "
            "accuracy on your project structure before trusting violations."
        ),
        "cross_layer_violations": violations[:100],
        "cycles": [{"namespaces": c} for c in cycles],
        "high_coupling_modules": coupling_summary[:25],
        "node_layers_sample": dict(list(node_layers.items())[:50]),
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    print(f"\nWrote {args.out}")
    print(f"  Cross-layer violations: {len(violations)}")
    print(f"  Dependency cycles:      {len(cycles)}")
    print(f"  High-coupling modules:  {len(coupling_summary)}")
    print("\nAttach this JSON to Copilot Chat (Design Flaw Reviewer mode) for")
    print("ground-truth-backed analysis instead of context-window guessing.")


if __name__ == "__main__":
    main()
