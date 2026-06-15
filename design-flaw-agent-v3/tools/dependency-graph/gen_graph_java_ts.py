#!/usr/bin/env python3
"""
gen_graph_java_ts.py — Entity-level graph for Java/Spring and Angular/TypeScript
==================================================================================
Brings Java and Angular/TS up to parity with gen_graph.py's C# entity-level
extraction (item #7). Produces the SAME node/edge schema as gen_graph.py
(version 1.0) so the chat mode and prioritization scripts can consume both
outputs uniformly:

  nodes: [{id, kind, name, file, lines, namespace, tags, ...}]
  edges: [{source, target, kind, label?}]

Java kinds:   controller, service, repository_interface, repository, entity,
              configuration, component, class, interface
Angular kinds: component, service, module, directive, pipe, guard, interceptor,
              class, interface

Edges:
  - injects        (constructor/field injection — @Autowired, Angular DI)
  - implements      (implements / interface)
  - inherits        (extends class)
  - extends         (interface extends)
  - has_route       (Angular: component <- route path, from routing module)
  - calls_endpoint  (Angular service method <- HTTP verb + path, if detectable)

Usage:
    python3 gen_graph_java_ts.py <repo_root> --lang java --out java-graph.json
    python3 gen_graph_java_ts.py <repo_root> --lang ts --out ts-graph.json
    python3 gen_graph_java_ts.py <repo_root> --lang both --out combined-graph.json
    python3 gen_graph_java_ts.py <repo_root> --lang java --changed-files changed.txt --out java-graph.json

No external dependencies — stdlib only.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_IGNORE_DIRS = {
    "node_modules", "bin", "obj", "dist", "build", ".git", ".vs",
    "target", "out", ".angular", "coverage", "__pycache__", ".idea", ".vscode",
}

# ---------------------------------------------------------------------------
# Java patterns
# ---------------------------------------------------------------------------

JAVA_PACKAGE_RE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)
JAVA_IMPORT_RE = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;', re.MULTILINE)

JAVA_CLASS_RE = re.compile(
    r'(?P<annots>(?:@\w+(?:\([^)]*\))?\s*)*)'
    r'(?P<vis>public|private|protected)?\s*'
    r'(?P<mods>(?:abstract|final|static)\s+)*'
    r'(?P<kind>class|interface|enum|record)\s+'
    r'(?P<name>\w+)'
    r'(?:<[^>]+>)?'
    r'(?:\s+extends\s+(?P<extends>[\w<>,\s\.]+?))?'
    r'(?:\s+implements\s+(?P<implements>[\w<>,\s\.]+?))?'
    r'\s*\{',
    re.MULTILINE,
)

JAVA_AUTOWIRED_FIELD_RE = re.compile(
    r'@Autowired\s*(?:\n\s*)?(?:private|protected|public)?\s*(?:final\s+)?(\w+)\s+(\w+)\s*;'
)
# Constructor injection: final fields set via constructor (Lombok @RequiredArgsConstructor
# or explicit constructor) — heuristic: any `private final <Type> <name>;` field
JAVA_FINAL_FIELD_RE = re.compile(r'private\s+final\s+(\w+)\s+(\w+)\s*;')

JAVA_REQUEST_MAPPING_RE = re.compile(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)')
JAVA_ENTITY_RE = re.compile(r'@Entity\b')
JAVA_TABLE_RE = re.compile(r'@Table\s*\(\s*name\s*=\s*"([^"]+)"')

# ---------------------------------------------------------------------------
# Angular / TypeScript patterns
# ---------------------------------------------------------------------------

TS_IMPORT_RE = re.compile(
    r'^\s*import\s+(?:type\s+)?(?:[\w*\s{},]+from\s+)?["\']([^"\']+)["\']',
    re.MULTILINE,
)

TS_DECORATOR_CLASS_RE = re.compile(
    r'@(Component|Injectable|NgModule|Directive|Pipe)\s*\((?P<args>(?:[^()]|\([^()]*\))*)\)\s*'
    r'export\s+class\s+(?P<name>\w+)'
    r'(?:\s+implements\s+(?P<implements>[\w,\s]+?))?'
    r'(?:\s+extends\s+(?P<extends>\w+))?'
    r'\s*\{',
    re.MULTILINE | re.DOTALL,
)

# Plain (undecorated) exported classes — guards, generic helper classes
TS_PLAIN_CLASS_RE = re.compile(
    r'^export\s+class\s+(?P<name>\w+)'
    r'(?:\s+implements\s+(?P<implements>[\w,\s]+?))?'
    r'(?:\s+extends\s+(?P<extends>\w+))?'
    r'\s*\{',
    re.MULTILINE,
)

TS_CONSTRUCTOR_PARAM_RE = re.compile(r'constructor\s*\((?P<params>[^)]*)\)')

# HTTP calls inside service methods: this.http.get<Foo>('/api/orders')
TS_HTTP_CALL_RE = re.compile(
    r'\.(get|post|put|delete|patch)\s*[<(]\s*[\w<>\[\]]*\s*>?\s*\(\s*[`\'"]([^`\'"]+)[`\'"]',
    re.IGNORECASE,
)

# Routing: { path: 'orders', component: OrderListComponent }
TS_ROUTE_RE = re.compile(
    r'path\s*:\s*[\'"]([^\'"]*)[\'"]\s*,\s*component\s*:\s*(\w+)'
)

NG_DECORATOR_KIND_MAP = {
    "Component": "component",
    "Injectable": "service",
    "NgModule": "module",
    "Directive": "directive",
    "Pipe": "pipe",
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def discover_files(root, exts):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]
        for f in filenames:
            ext = os.path.splitext(f)[1]
            if ext in exts:
                if ext in (".ts", ".tsx") and (f.endswith(".d.ts") or ".spec." in f or ".test." in f):
                    continue
                found.append(os.path.join(dirpath, f))
    return found


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def line_number(text, pos):
    return text[:pos].count("\n") + 1


def count_block_lines(text, brace_pos):
    depth = 0
    for i in range(brace_pos, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return line_number(text, i)
    return line_number(text, len(text) - 1)


def split_types(raw):
    """Split a comma-separated type list, respecting generic <...> nesting
    so `JpaRepository<Order, Long>` isn't split into two types."""
    if not raw:
        return []
    parts = []
    depth = 0
    current = []
    for ch in raw:
        if ch == '<':
            depth += 1
            current.append(ch)
        elif ch == '>':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current))
    return [re.sub(r'\s+', ' ', p).strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Java classification
# ---------------------------------------------------------------------------

def classify_java_kind(name, annots, kind_keyword, extends, implements):
    annots_l = annots.lower()
    name_l = name.lower()

    if "@restcontroller" in annots_l or "@controller" in annots_l:
        return "controller"
    if "@entity" in annots_l:
        return "entity"
    if "@configuration" in annots_l:
        return "configuration"
    if "@repository" in annots_l:
        return "repository"
    if "@service" in annots_l:
        return "service"
    if "@component" in annots_l:
        return "component"

    if kind_keyword == "interface":
        if name_l.endswith("repository"):
            return "repository_interface"
        if name_l.endswith("service"):
            return "service_interface"
        return "interface"

    if name_l.endswith("repository") or name_l.endswith("repo"):
        return "repository"
    if name_l.endswith("service") or name_l.endswith("serviceimpl"):
        return "service"
    if name_l.endswith("controller"):
        return "controller"
    if name_l.endswith("dto") or name_l.endswith("request") or name_l.endswith("response"):
        return "model"
    return "class"


def parse_java_file(filepath, root):
    nodes = []
    edges = []
    text = read_text(filepath)
    if not text:
        return nodes, edges

    rel = os.path.relpath(filepath, root).replace("\\", "/")
    pkg_match = JAVA_PACKAGE_RE.search(text)
    package = pkg_match.group(1) if pkg_match else ""

    for m in JAVA_CLASS_RE.finditer(text):
        name = m.group("name")
        annots = m.group("annots") or ""
        kind_keyword = m.group("kind")
        extends = split_types(m.group("extends"))
        implements = split_types(m.group("implements"))

        kind = classify_java_kind(name, annots, kind_keyword, extends, implements)
        node_id = f"{package}.{name}" if package else name
        start_line = line_number(text, m.start())
        brace_pos = text.find('{', m.end() - 1)
        end_line = count_block_lines(text, brace_pos) if brace_pos != -1 else start_line

        tags = [kind]
        if "@transactional" in text[m.start():m.start() + 2000].lower():
            tags.append("transactional")
        if JAVA_REQUEST_MAPPING_RE.search(text[m.start():brace_pos] if brace_pos > 0 else ""):
            tags.append("api-endpoint")

        table_name = None
        tbl_m = JAVA_TABLE_RE.search(text[max(0, m.start() - 200):m.start()])
        if tbl_m:
            table_name = tbl_m.group(1)

        node = {
            "id": node_id, "kind": kind, "name": name,
            "file": rel, "lines": [start_line, end_line], "namespace": package,
            "tags": tags,
        }
        if extends:
            node["base_types"] = extends
        if implements:
            node["interfaces"] = implements
        if table_name:
            node["db_table"] = table_name
        nodes.append(node)

        for b in extends:
            edges.append({"source": node_id, "target": b, "kind": "inherits"})
        for i in implements:
            edges.append({"source": node_id, "target": i, "kind": "implements"})

        # field injection (@Autowired or constructor-injected final fields)
        body_end = brace_pos if brace_pos != -1 else len(text)
        body = text[m.start():body_end + 2000] if body_end else ""
        for fm in JAVA_AUTOWIRED_FIELD_RE.finditer(body):
            ftype, fname = fm.group(1), fm.group(2)
            edges.append({"source": node_id, "target": ftype, "kind": "injects", "label": fname})
        for fm in JAVA_FINAL_FIELD_RE.finditer(body):
            ftype, fname = fm.group(1), fm.group(2)
            if ftype[0].isupper():
                edges.append({"source": node_id, "target": ftype, "kind": "injects", "label": fname})

    return nodes, edges


# ---------------------------------------------------------------------------
# Angular / TS classification
# ---------------------------------------------------------------------------

def parse_ts_file(filepath, root):
    nodes = []
    edges = []
    text = read_text(filepath)
    if not text:
        return nodes, edges

    rel = os.path.relpath(filepath, root).replace("\\", "/")
    folder = os.path.dirname(rel)

    seen_names = set()

    for m in TS_DECORATOR_CLASS_RE.finditer(text):
        name = m.group("name")
        decorator = m.group(0).split("(")[0].lstrip("@")
        kind = NG_DECORATOR_KIND_MAP.get(decorator, "class")
        implements_ = split_types(m.group("implements"))
        extends_ = [m.group("extends")] if m.group("extends") else []

        start_line = line_number(text, m.start())
        brace_pos = text.find('{', m.end() - 1)
        end_line = count_block_lines(text, brace_pos) if brace_pos != -1 else start_line

        node_id = f"{folder}/{name}".replace("\\", "/")
        seen_names.add(name)

        tags = [kind]
        if "providedIn" in m.group("args") if m.group("args") else False:
            tags.append("root-provided")

        node = {
            "id": node_id, "kind": kind, "name": name,
            "file": rel, "lines": [start_line, end_line], "namespace": folder,
            "tags": tags,
        }
        if implements_:
            node["interfaces"] = implements_
        if extends_:
            node["base_types"] = extends_
        nodes.append(node)

        for i in implements_:
            edges.append({"source": node_id, "target": i, "kind": "implements"})
        for b in extends_:
            edges.append({"source": node_id, "target": b, "kind": "inherits"})

        # constructor DI
        ctor_search_region = text[m.start():brace_pos + 2000] if brace_pos != -1 else text[m.start():]
        ctor_m = TS_CONSTRUCTOR_PARAM_RE.search(ctor_search_region)
        if ctor_m:
            for p in ctor_m.group("params").split(","):
                p = p.strip()
                # private readonly orderService: OrderService
                tm = re.search(r':\s*(\w+)', p)
                if tm:
                    ptype = tm.group(1)
                    pname_m = re.match(r'(?:private|public|protected|readonly|\s)*(\w+)\s*:', p)
                    pname = pname_m.group(1) if pname_m else ""
                    edges.append({"source": node_id, "target": ptype, "kind": "injects", "label": pname})

        # HTTP calls -> external endpoint nodes (only for service-kind)
        if kind == "service":
            method_region = text[m.start():brace_pos + 4000] if brace_pos != -1 else text[m.start():]
            for hm in TS_HTTP_CALL_RE.finditer(method_region):
                verb, path = hm.group(1).upper(), hm.group(2)
                edges.append({"source": node_id, "target": f"HTTP {verb} {path}",
                               "kind": "calls_endpoint", "label": verb})

    # Plain exported classes not caught by decorator regex (guards, helpers)
    for m in TS_PLAIN_CLASS_RE.finditer(text):
        name = m.group("name")
        if name in seen_names:
            continue
        implements_ = split_types(m.group("implements"))
        extends_ = [m.group("extends")] if m.group("extends") else []
        start_line = line_number(text, m.start())
        brace_pos = text.find('{', m.end() - 1)
        end_line = count_block_lines(text, brace_pos) if brace_pos != -1 else start_line

        kind = "class"
        name_l = name.lower()
        if name_l.endswith("guard"):
            kind = "guard"
        elif name_l.endswith("interceptor"):
            kind = "interceptor"
        elif "interface" in implements_ and name_l.endswith("able"):
            kind = "class"

        node_id = f"{folder}/{name}".replace("\\", "/")
        node = {
            "id": node_id, "kind": kind, "name": name,
            "file": rel, "lines": [start_line, end_line], "namespace": folder,
            "tags": [kind],
        }
        if implements_:
            node["interfaces"] = implements_
        if extends_:
            node["base_types"] = extends_
        nodes.append(node)

        for i in implements_:
            edges.append({"source": node_id, "target": i, "kind": "implements"})
        for b in extends_:
            edges.append({"source": node_id, "target": b, "kind": "inherits"})

    # Routing edges (only meaningful in routing module files)
    if "routing" in rel.lower() or "routes" in rel.lower():
        for rm in TS_ROUTE_RE.finditer(text):
            path, component = rm.group(1), rm.group(2)
            edges.append({"source": f"Route:/{path}", "target": component, "kind": "has_route"})

    return nodes, edges


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph(root, lang, changed_files=None):
    all_nodes = []
    all_edges = []

    if lang in ("java", "both"):
        files = discover_files(root, {".java"})
        if changed_files:
            files = [f for f in files if os.path.relpath(f, root).replace("\\", "/") in changed_files]
        for f in files:
            n, e = parse_java_file(f, root)
            all_nodes.extend(n)
            all_edges.extend(e)

    if lang in ("ts", "both"):
        files = discover_files(root, {".ts", ".tsx"})
        if changed_files:
            files = [f for f in files if os.path.relpath(f, root).replace("\\", "/") in changed_files]
        for f in files:
            n, e = parse_ts_file(f, root)
            all_nodes.extend(n)
            all_edges.extend(e)

    # Resolve short-name edge targets to node ids where possible
    short_index = {}
    for n in all_nodes:
        short_index.setdefault(n["name"], n["id"])
        for iface in n.get("interfaces", []):
            short_index.setdefault(iface, n["id"])

    resolved_edges = []
    seen = set()
    for e in all_edges:
        target = e["target"]
        if target in short_index:
            target = short_index[target]
        key = (e["source"], target, e["kind"], e.get("label", ""))
        if key in seen or e["source"] == target:
            continue
        seen.add(key)
        e2 = dict(e)
        e2["target"] = target
        resolved_edges.append(e2)

    stats = defaultdict(int)
    for n in all_nodes:
        stats[n["kind"]] += 1

    content = json.dumps(sorted(all_nodes, key=lambda x: x["id"]), sort_keys=True)
    graph_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    return {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "gen_graph_java_ts.py",
        "language": lang,
        "hash": graph_hash,
        "stats": {"total_nodes": len(all_nodes), "total_edges": len(resolved_edges), **dict(stats)},
        "nodes": sorted(all_nodes, key=lambda x: x["id"]),
        "edges": resolved_edges,
    }


def main():
    parser = argparse.ArgumentParser(description="Entity-level graph for Java/Spring and Angular/TS")
    parser.add_argument("repo_root")
    parser.add_argument("--lang", choices=["java", "ts", "both"], default="both")
    parser.add_argument("--out", default="java-ts-graph.json")
    parser.add_argument("--changed-files", default=None,
                         help="Text file of changed paths (relative to repo_root, one per line) for incremental runs")
    args = parser.parse_args()

    root = os.path.abspath(args.repo_root)
    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    changed = None
    if args.changed_files and os.path.exists(args.changed_files):
        with open(args.changed_files) as fh:
            changed = {line.strip().replace("\\", "/") for line in fh if line.strip()}
        print(f"Incremental run: {len(changed)} changed files")

    graph = build_graph(root, args.lang, changed)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, indent=2)

    print(f"Wrote {args.out}")
    print(f"  Nodes: {graph['stats']['total_nodes']}")
    print(f"  Edges: {graph['stats']['total_edges']}")
    for k, v in graph["stats"].items():
        if k not in ("total_nodes", "total_edges"):
            print(f"    {k:25s}: {v}")


if __name__ == "__main__":
    main()
