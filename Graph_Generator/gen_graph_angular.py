#!/usr/bin/env python3
"""
gen_graph_angular.py — Codebase Memory Graph Generator for Angular
===================================================================
Supports: Angular 14+ · NgRx · Angular Material · RxJS patterns

Parses TypeScript/Angular source files and extracts:
  @Injectable services and their constructor dependencies
  @Component (selector, templateUrl, inputs/outputs)
  @Directive, @Pipe, @NgModule declarations
  Guards (CanActivate, CanDeactivate, CanLoad)
  HTTP Interceptors (HttpInterceptor)
  @NgRx Store: Actions, Reducers, Effects, Selectors
  Interface and model definitions
  JSDoc /** */ comment summaries
  Import-based dependency edges

Usage:
    python gen_graph_angular.py                          # current directory
    python gen_graph_angular.py --root ./src/app         # Angular src folder
    python gen_graph_angular.py --output graph.json
    python gen_graph_angular.py --exclude "**/spec/**"
    python gen_graph_angular.py --tree
    python gen_graph_angular.py --watch

Requirements: Python 3.9+  (no third-party packages)
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────

@dataclass
class NodeLocation:
    file: str
    lines: list[int]
    module: str = ""


@dataclass
class GraphNode:
    id: str
    kind: str             # service | component | guard | interceptor | pipe
                          # directive | module | model | interface | effect
                          # reducer | action | selector | store
    name: str
    location: NodeLocation
    summary: str = ""
    selector: str = ""    # Angular component/directive selector
    decorators: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    provided_in: str = ""


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str             # injects | imports | implements | extends
                          # declares | provides | uses_in_template
    label: str = ""


@dataclass
class GraphStats:
    total_files: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    services: int = 0
    components: int = 0
    guards: int = 0
    interceptors: int = 0
    pipes: int = 0
    directives: int = 0
    modules: int = 0
    models: int = 0
    store: int = 0


# ─────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────

# JSDoc comment immediately before declaration
RE_JSDOC = re.compile(r'/\*\*(.*?)\*/', re.DOTALL)
RE_JSDOC_CLEAN = re.compile(r'^\s*\*\s?', re.MULTILINE)

# Angular decorators
RE_DECORATOR = re.compile(
    r'@(Injectable|Component|Directive|Pipe|NgModule|Input|Output|HostListener|ViewChild|ContentChild)'
    r'(?:\s*\(([^)]*)\))?',
    re.MULTILINE
)

# Class declaration
RE_CLASS = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'(?P<decs>(?:@[\w]+(?:\([^)]*\))?\s*\n?\s*)*)'
    r'\s*export\s+(?:abstract\s+)?(?:default\s+)?class\s+(?P<name>\w+)'
    r'(?:<[^>]+>)?'
    r'(?:\s+extends\s+(?P<extends>[\w<>., ]+?))?'
    r'(?:\s+implements\s+(?P<implements>[\w<>., ]+?))?'
    r'\s*\{',
    re.DOTALL | re.MULTILINE
)

# Interface declaration
RE_INTERFACE = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'export\s+interface\s+(?P<name>\w+)'
    r'(?:<[^>]+>)?'
    r'(?:\s+extends\s+(?P<extends>[\w<>., ]+?))?'
    r'\s*\{',
    re.DOTALL | re.MULTILINE
)

# Type alias
RE_TYPE_ALIAS = re.compile(
    r'export\s+type\s+(?P<name>\w+)\s*(?:<[^>]+>)?\s*=',
    re.MULTILINE
)

# Enum
RE_ENUM = re.compile(
    r'export\s+enum\s+(?P<name>\w+)\s*\{',
    re.MULTILINE
)

# Constructor parameters
RE_CTOR = re.compile(
    r'constructor\s*\((?P<params>[^)]*)\)',
    re.MULTILINE | re.DOTALL
)

# Constructor param: private/public/protected + optional modifier + type
RE_CTOR_PARAM = re.compile(
    r'(?:private|public|protected|readonly)\s+'
    r'(?:readonly\s+)?'
    r'(?P<name>\w+)\s*:\s*(?P<type>[\w<>[\]| ,]+)',
)

# Import statement
RE_IMPORT = re.compile(
    r"import\s+(?:type\s+)?(?:\*\s+as\s+\w+|\{[^}]+\}|\w+)\s+from\s+['\"](?P<path>[^'\"]+)['\"]",
    re.MULTILINE
)

# @Component selector
RE_SELECTOR = re.compile(r"selector\s*:\s*['\"]([^'\"]+)['\"]")

# @Injectable providedIn
RE_PROVIDED_IN = re.compile(r"providedIn\s*:\s*['\"]([^'\"]+)['\"]")

# @Input / @Output decorators on fields
RE_INPUT  = re.compile(r'@Input\(\)\s+(\w+)', re.MULTILINE)
RE_OUTPUT = re.compile(r'@Output\(\)\s+(\w+)', re.MULTILINE)

# NgRx patterns
RE_CREATEACTION   = re.compile(r'createAction\s*\(', re.MULTILINE)
RE_CREATEREDUCER  = re.compile(r'createReducer\s*\(', re.MULTILINE)
RE_CREATEEFFECT   = re.compile(r'createEffect\s*\(', re.MULTILINE)
RE_CREATESELECTOR = re.compile(r'createSelector\s*\(', re.MULTILINE)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def extract_jsdoc(text: str, pos: int) -> str:
    preceding = text[:pos].rstrip()
    start = preceding.rfind("/**")
    if start == -1: return ""
    end = preceding.rfind("*/")
    if end == -1 or end < start: return ""
    raw = preceding[start:end+2]
    cleaned = RE_JSDOC_CLEAN.sub("", raw)
    cleaned = re.sub(r'/\*\*|\*/', "", cleaned)
    cleaned = re.sub(r'@\w+.*', "", cleaned)
    return " ".join(cleaned.split()).strip()


def line_number(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def count_block_end(text: str, start: int) -> int:
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return line_number(text, i)
    return line_number(text, len(text) - 1)


def parse_type_list(raw: str | None) -> list[str]:
    if not raw: return []
    return [p.split("<")[0].strip() for p in raw.split(",") if p.strip()]


def get_all_decorators(raw_block: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r'@(\w+)', raw_block)]


def classify_angular_kind(
    name: str,
    decorators: list[str],
    implements_list: list[str],
    extends_list: list[str],
    is_interface: bool,
    file_path: str,
    has_ngrx: dict,
) -> str:
    dec_set = set(decorators)

    if is_interface:
        n = name.lower()
        if n.endswith("state"):   return "store"
        if n.endswith("action"):  return "action"
        return "interface"

    if "Component"   in dec_set: return "component"
    if "Injectable"  in dec_set:
        for iface in implements_list:
            if "Guard" in iface or "CanActivate" in iface or "CanDeactivate" in iface: return "guard"
            if "Interceptor" in iface or "HttpInterceptor" in iface: return "interceptor"
        n = name.lower()
        if "guard"       in n: return "guard"
        if "interceptor" in n: return "interceptor"
        if "resolver"    in n: return "resolver"
        if "store"       in n or "facade" in n: return "store"
        return "service"
    if "Directive"   in dec_set: return "directive"
    if "Pipe"        in dec_set: return "pipe"
    if "NgModule"    in dec_set: return "module"

    # NgRx file-level
    if has_ngrx.get("effect"):    return "effect"
    if has_ngrx.get("reducer"):   return "reducer"
    if has_ngrx.get("action"):    return "action"
    if has_ngrx.get("selector"):  return "selector"

    for iface in implements_list:
        if "CanActivate" in iface or "Guard" in iface: return "guard"
        if "HttpInterceptor" in iface: return "interceptor"
        if "Resolve"  in iface: return "resolver"

    n = name.lower()
    if n.endswith("service"):     return "service"
    if n.endswith("guard"):       return "guard"
    if n.endswith("interceptor"): return "interceptor"
    if n.endswith("pipe"):        return "pipe"
    if n.endswith("directive"):   return "directive"
    if n.endswith("component"):   return "component"
    if n.endswith("module"):      return "module"
    if n.endswith("effect"):      return "effect"
    if n.endswith("reducer"):     return "reducer"
    if n.endswith("model") or n.endswith("dto"): return "model"

    # File path hints
    fp = file_path.lower()
    if "guard" in fp:       return "guard"
    if "interceptor" in fp: return "interceptor"
    if "service" in fp:     return "service"
    if "component" in fp:   return "component"
    if "model" in fp:       return "model"
    if "store" in fp or "ngrx" in fp: return "store"

    return "class"


def build_tags(kind: str, name: str, decorators: list[str], file_path: str) -> list[str]:
    tags = [kind]
    n = name.lower()
    fp = file_path.lower()
    if "auth"    in n or "auth"    in fp: tags.append("auth")
    if "order"   in n or "order"   in fp: tags.append("orders")
    if "user"    in n or "user"    in fp: tags.append("user")
    if "payment" in n or "payment" in fp: tags.append("payments")
    if "http"    in n or "http"    in fp: tags.append("http")
    if kind == "guard":       tags.append("security")
    if kind == "interceptor": tags.append("http")
    if kind == "component":   tags.append("ui")
    if kind in ("effect","reducer","action","selector"): tags.append("ngrx")
    # Path segments
    parts = file_path.replace("\\","/").split("/")
    for p in parts[:-1]:
        if p not in ("src","app","main","angular","dist","node_modules"):
            tags.append(p)
    return list(dict.fromkeys(tags))


def file_to_module(filepath: Path, root: Path) -> str:
    rel = filepath.relative_to(root)
    parts = list(rel.parts)
    parts[-1] = parts[-1].replace(".ts","").replace(".component","").replace(".service","")
    return ".".join(parts)


def resolve_import(short: str, imports_map: dict[str, str], module: str) -> str:
    return imports_map.get(short, f"{module}.{short}")


# ─────────────────────────────────────────────
# Per-file parser
# ─────────────────────────────────────────────

def parse_ts_file(filepath: Path, root: Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return nodes, edges

    rel_path = str(filepath.relative_to(root)).replace("\\", "/")
    module = file_to_module(filepath, root)

    # Build import map: symbol → source path
    imports_map: dict[str, str] = {}
    local_imports: list[str] = []
    for m in RE_IMPORT.finditer(text):
        path = m.group("path")
        # Extract imported names from the full match
        full = m.group(0)
        names_part = re.search(r'\{([^}]+)\}', full)
        if names_part:
            for name in names_part.group(1).split(","):
                name = name.strip().split(" as ")[-1].strip()
                imports_map[name] = path
                if path.startswith("."):
                    local_imports.append(name)

    # Detect NgRx patterns
    has_ngrx = {
        "action":   bool(RE_CREATEACTION.search(text)),
        "reducer":  bool(RE_CREATEREDUCER.search(text)),
        "effect":   bool(RE_CREATEEFFECT.search(text)),
        "selector": bool(RE_CREATESELECTOR.search(text)),
    }

    # ── Classes ──
    for m in RE_CLASS.finditer(text):
        raw_decs = m.group("decs") or ""
        decorators = get_all_decorators(raw_decs)
        name = m.group("name")
        extends_list = parse_type_list(m.group("extends"))
        implements_list = parse_type_list(m.group("implements"))

        kind = classify_angular_kind(name, decorators, implements_list, extends_list, False, rel_path, has_ngrx)
        node_id = f"{module}.{name}"
        summary = extract_jsdoc(text, m.start())
        start_line = line_number(text, m.start())
        end_line = count_block_end(text, m.start())

        # Selector
        selector_m = RE_SELECTOR.search(raw_decs)
        selector = selector_m.group(1) if selector_m else ""

        # providedIn
        provided_m = RE_PROVIDED_IN.search(raw_decs)
        provided_in = provided_m.group(1) if provided_m else ""

        # Class body for inputs/outputs/ctor
        body_start = text.find("{", m.start())
        body = text[body_start: body_start + 6000] if body_start != -1 else ""
        inputs  = RE_INPUT.findall(body)
        outputs = RE_OUTPUT.findall(body)

        node = GraphNode(
            id=node_id,
            kind=kind,
            name=name,
            location=NodeLocation(file=rel_path, lines=[start_line, end_line], module=module),
            summary=summary,
            selector=selector,
            decorators=decorators,
            implements=implements_list,
            extends=extends_list,
            tags=build_tags(kind, name, decorators, rel_path),
            inputs=inputs,
            outputs=outputs,
            provided_in=provided_in,
        )
        nodes.append(node)

        # Inheritance edges
        for base in extends_list:
            edges.append(GraphEdge(source=node_id, target=resolve_import(base, imports_map, module), kind="extends"))
        for iface in implements_list:
            edges.append(GraphEdge(source=node_id, target=resolve_import(iface, imports_map, module), kind="implements"))

        # Constructor injection edges
        ctor_m = RE_CTOR.search(body)
        if ctor_m:
            for pm in RE_CTOR_PARAM.finditer(ctor_m.group("params")):
                ptype = pm.group("type").split("<")[0].strip()
                if ptype in ("string","number","boolean","any","void","Router","ActivatedRoute"):
                    continue
                target = resolve_import(ptype, imports_map, module)
                edges.append(GraphEdge(source=node_id, target=target, kind="injects", label=pm.group("name")))

    # ── Interfaces ──
    for m in RE_INTERFACE.finditer(text):
        name = m.group("name")
        kind = classify_angular_kind(name, [], [], [], True, rel_path, {})
        node_id = f"{module}.{name}"
        summary = extract_jsdoc(text, m.start())
        start_line = line_number(text, m.start())
        end_line = count_block_end(text, m.start())

        node = GraphNode(
            id=node_id,
            kind=kind,
            name=name,
            location=NodeLocation(file=rel_path, lines=[start_line, end_line], module=module),
            summary=summary,
            tags=build_tags(kind, name, [], rel_path),
        )
        nodes.append(node)

    # ── Type aliases ──
    for m in RE_TYPE_ALIAS.finditer(text):
        name = m.group("name")
        node_id = f"{module}.{name}"
        nodes.append(GraphNode(
            id=node_id, kind="type", name=name,
            location=NodeLocation(file=rel_path, lines=[line_number(text, m.start()), line_number(text, m.start())], module=module),
            tags=build_tags("type", name, [], rel_path),
        ))

    # ── Enums ──
    for m in RE_ENUM.finditer(text):
        name = m.group("name")
        node_id = f"{module}.{name}"
        nodes.append(GraphNode(
            id=node_id, kind="enum", name=name,
            location=NodeLocation(file=rel_path, lines=[line_number(text, m.start()), line_number(text, m.start())+5], module=module),
            tags=build_tags("enum", name, [], rel_path),
        ))

    # ── Local import edges ──
    for m in RE_IMPORT.finditer(text):
        path = m.group("path")
        if not path.startswith("."): continue
        # Resolve relative path to module id
        base_parts = module.split(".")[:-1]
        for seg in path.replace(".ts","").split("/"):
            if seg == "..":
                base_parts = base_parts[:-1]
            elif seg and seg != ".":
                base_parts.append(seg)
        target_module = ".".join(base_parts)
        if target_module != module:
            edges.append(GraphEdge(source=module, target=target_module, kind="imports"))

    return nodes, edges


# ─────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────

DEFAULT_EXCLUDES = [
    "**/*.spec.ts", "**/*.test.ts",
    "**/node_modules/**", "**/dist/**",
    "**/.angular/**", "**/coverage/**",
    "**/*.d.ts", "**/polyfills.ts",
    "**/environments/**",
]


def should_exclude(path: Path, root: Path, patterns: list[str]) -> bool:
    rel = str(path.relative_to(root)).replace("\\", "/")
    for pat in patterns:
        clean = pat.strip("*/")
        if fnmatch.fnmatch(rel, pat.lstrip("*/")):
            return True
        if clean and clean in rel:
            return True
    return False


def build_graph(root: Path, extra_excludes: list[str]) -> dict:
    all_nodes: list[GraphNode] = []
    all_edges: list[GraphEdge] = []
    excludes = DEFAULT_EXCLUDES + extra_excludes

    ts_files = sorted(root.rglob("*.ts"))
    processed = 0

    for tf in ts_files:
        if should_exclude(tf, root, excludes):
            continue
        n, e = parse_ts_file(tf, root)
        all_nodes.extend(n)
        all_edges.extend(e)
        processed += 1

    seen: dict[str, GraphNode] = {}
    for n in all_nodes:
        if n.id not in seen:
            seen[n.id] = n
        else:
            existing = seen[n.id]
            if len(n.summary) > len(existing.summary):
                existing.summary = n.summary
            existing.tags = list(dict.fromkeys(existing.tags + n.tags))

    final_nodes = list(seen.values())

    seen_edges: set[tuple] = set()
    final_edges: list[GraphEdge] = []
    for e in all_edges:
        key = (e.source, e.target, e.kind)
        if key not in seen_edges and e.source != e.target:
            seen_edges.add(key)
            final_edges.append(e)

    stats = GraphStats(
        total_files=processed,
        total_nodes=len(final_nodes),
        total_edges=len(final_edges),
        services=sum(1 for n in final_nodes if n.kind == "service"),
        components=sum(1 for n in final_nodes if n.kind == "component"),
        guards=sum(1 for n in final_nodes if n.kind == "guard"),
        interceptors=sum(1 for n in final_nodes if n.kind == "interceptor"),
        pipes=sum(1 for n in final_nodes if n.kind == "pipe"),
        directives=sum(1 for n in final_nodes if n.kind == "directive"),
        modules=sum(1 for n in final_nodes if n.kind == "module"),
        models=sum(1 for n in final_nodes if n.kind in ("model","interface","type")),
        store=sum(1 for n in final_nodes if n.kind in ("store","effect","reducer","action","selector")),
    )

    content = json.dumps([asdict(n) for n in sorted(final_nodes, key=lambda x: x.id)], sort_keys=True)
    graph_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    return {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "gen_graph_angular.py",
        "language": "typescript",
        "framework": "angular",
        "hash": graph_hash,
        "stats": asdict(stats),
        "nodes": [_node_to_dict(n) for n in sorted(final_nodes, key=lambda x: x.id)],
        "edges": [{"source": e.source, "target": e.target, "kind": e.kind, **({"label": e.label} if e.label else {})} for e in final_edges],
    }


def _node_to_dict(n: GraphNode) -> dict:
    d = {
        "id": n.id, "kind": n.kind, "name": n.name,
        "file": n.location.file, "lines": n.location.lines,
        "module": n.location.module, "summary": n.summary, "tags": n.tags,
    }
    if n.selector:     d["selector"] = n.selector
    if n.decorators:   d["decorators"] = n.decorators
    if n.implements:   d["implements"] = n.implements
    if n.extends:      d["extends"] = n.extends
    if n.inputs:       d["inputs"] = n.inputs
    if n.outputs:      d["outputs"] = n.outputs
    if n.provided_in:  d["provided_in"] = n.provided_in
    return d


# ─────────────────────────────────────────────
# CLI + reporting
# ─────────────────────────────────────────────

COLORS = {"green":"\033[92m","yellow":"\033[93m","cyan":"\033[96m","gray":"\033[90m","reset":"\033[0m","bold":"\033[1m"}
def c(text: str, color: str) -> str:
    return f"{COLORS.get(color,'')}{text}{COLORS['reset']}" if sys.stdout.isatty() else text


def print_summary(graph: dict) -> None:
    s = graph["stats"]
    print()
    print(c("  CodeGraph — Angular Codebase Map", "bold"))
    print(c(f"  Generated : {graph['generated'][:19].replace('T',' ')} UTC", "gray"))
    print(c(f"  Hash      : {graph['hash']}", "gray"))
    print()
    print(c(f"  {'Files scanned:':<24} {s['total_files']}", "cyan"))
    print(c(f"  {'Nodes extracted:':<24} {s['total_nodes']}", "cyan"))
    print(c(f"  {'Edges mapped:':<24} {s['total_edges']}", "cyan"))
    print()
    for label, key in [("Services","services"),("Components","components"),("Guards","guards"),
                       ("Interceptors","interceptors"),("Pipes","pipes"),("Directives","directives"),
                       ("Modules","modules"),("Models/Interfaces","models"),("NgRx store","store")]:
        print(c(f"  {label+':':<24} {s[key]}", "green"))
    print()


def print_node_tree(graph: dict) -> None:
    groups: dict[str, list] = {}
    for n in graph["nodes"]:
        groups.setdefault(n["kind"], []).append(n)
    for kind, nlist in sorted(groups.items()):
        print(c(f"\n  [{kind.upper()}]", "yellow"))
        for n in sorted(nlist, key=lambda x: x["name"]):
            s = f" — {n['summary'][:60]}" if n.get("summary") else ""
            print(f"    {c(n['id'],'cyan')}{c(s,'gray')}")


def watch_mode(root: Path, output: Path, extra: list[str]) -> None:
    print(c(f"  Watching {root} … (Ctrl-C to stop)", "yellow"))
    last = {str(f): f.stat().st_mtime for f in root.rglob("*.ts")}
    _run(root, output, extra, quiet=False)
    while True:
        time.sleep(2)
        cur = {str(f): f.stat().st_mtime for f in root.rglob("*.ts")}
        if cur != last:
            last = cur
            _run(root, output, extra, quiet=True)
            print(c(f"  Graph updated → {output}", "green"))


def _run(root: Path, output: Path, extra: list[str], quiet: bool) -> None:
    graph = build_graph(root, extra)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    if not quiet:
        print_summary(graph)
        print(c(f"  Written → {output}", "green"))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate codebase memory graph for Angular projects.")
    parser.add_argument("--root", "-r", default=".", help="Root directory (usually src/app)")
    parser.add_argument("--output", "-o", default="codebase-graph.json")
    parser.add_argument("--exclude", "-e", action="append", default=[], metavar="PATTERN")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--tree", action="store_true")
    parser.add_argument("--watch", "-w", action="store_true")
    parser.add_argument("--minify", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(c(f"  Error: path not found: {root}", "gray"), file=sys.stderr)
        return 1

    output = Path(args.output)
    if args.watch:
        watch_mode(root, output, args.exclude)
        return 0

    print(c(f"\n  Scanning {root} …", "cyan"))
    graph = build_graph(root, args.exclude)
    print_summary(graph)
    if args.tree:
        print_node_tree(graph)
        print()
    if not args.summary:
        indent = None if args.minify else 2
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(graph, indent=indent), encoding="utf-8")
        size_kb = output.stat().st_size / 1024
        print(c(f"  Written → {output}  ({size_kb:.1f} KB)", "green"))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())