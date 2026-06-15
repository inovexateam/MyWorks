#!/usr/bin/env python3
"""
gen_graph.py — Codebase Memory Graph Generator for .NET / C# / ASP.NET Core
=============================================================================
Parses your C# source files using regex-based AST analysis and builds a
structured graph of classes, interfaces, methods, controllers, services,
repositories, and their relationships — committed to git as codebase-graph.json.

Usage:
    python gen_graph.py                        # scan current directory
    python gen_graph.py --root ./src           # scan specific folder
    python gen_graph.py --output graph.json    # custom output path
    python gen_graph.py --exclude **/obj/**    # exclude patterns
    python gen_graph.py --summary              # print stats only
    python gen_graph.py --watch                # watch mode (re-runs on change)

Requirements:
    Python 3.9+   (no third-party packages needed)
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
from typing import Any


# ─────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────

@dataclass
class NodeLocation:
    file: str
    lines: list[int]        # [start, end]
    namespace: str = ""


@dataclass
class GraphNode:
    id: str
    kind: str               # class | interface | method | controller | service
                            # repository | dbcontext | middleware | model | enum
    name: str
    location: NodeLocation
    summary: str = ""
    visibility: str = "public"
    is_abstract: bool = False
    is_static: bool = False
    is_async: bool = False
    base_types: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    return_type: str = ""
    parameters: list[dict] = field(default_factory=list)
    generic_params: list[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str               # inherits | implements | injects | calls | uses
                            # has_action | registers | configures
    label: str = ""


@dataclass
class GraphStats:
    total_files: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    controllers: int = 0
    services: int = 0
    repositories: int = 0
    models: int = 0
    interfaces: int = 0
    middlewares: int = 0
    dbcontexts: int = 0


# ─────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────

# XML doc comment on line immediately above
RE_XML_SUMMARY = re.compile(
    r'///\s*<summary>(.*?)</summary>',
    re.DOTALL
)

# Namespace
RE_NAMESPACE = re.compile(
    r'^\s*namespace\s+([\w.]+)',
    re.MULTILINE
)

# Class / struct / record
RE_CLASS = re.compile(
    r'(?P<attrs>(?:\s*\[[^\]]+\]\s*)*)'             # optional attributes
    r'\s*(?P<vis>public|internal|protected|private)?\s*'
    r'(?P<mods>(?:(?:abstract|sealed|static|partial|readonly)\s+)*)'
    r'(?P<kind>class|struct|record)\s+'
    r'(?P<name>\w+)'
    r'(?:<(?P<generics>[^>]+)>)?'                   # generic params
    r'(?:\s*:\s*(?P<bases>[^{]+))?'                 # base types
    r'\s*[{]',
    re.MULTILINE
)

# Interface
RE_INTERFACE = re.compile(
    r'(?P<attrs>(?:\s*\[[^\]]+\]\s*)*)'
    r'\s*(?P<vis>public|internal)?\s*interface\s+'
    r'(?P<name>\w+)'
    r'(?:<(?P<generics>[^>]+)>)?'
    r'(?:\s*:\s*(?P<bases>[^{]+))?'
    r'\s*[{]',
    re.MULTILINE
)

# Method / action
RE_METHOD = re.compile(
    r'(?P<attrs>(?:\s*\[[^\]]+\]\s*\n?)*)'
    r'\s*(?P<vis>public|protected|private|internal|protected\s+internal)?\s*'
    r'(?P<mods>(?:(?:static|async|virtual|override|abstract|sealed|new)\s+)*)'
    r'(?P<ret>[\w<>\[\]?,\s]+?)\s+'
    r'(?P<name>[A-Z]\w*)'
    r'\s*(?:<(?P<generics>[^>]+)>)?\s*'
    r'\((?P<params>[^)]*)\)',
    re.MULTILINE
)

# Constructor injection via constructor params
RE_CTOR = re.compile(
    r'(?:public|protected|private)\s+\w+\s*\((?P<params>[^)]+)\)',
    re.MULTILINE
)

# Interface fields (private readonly _field)
RE_FIELD = re.compile(
    r'private\s+readonly\s+(?P<type>I\w+)\s+(?P<name>_\w+)',
    re.MULTILINE
)

# Attribute extraction
RE_ATTR_STRIP = re.compile(r'\[([^\]]+)\]')

# HttpVerb attributes
RE_HTTP_VERB = re.compile(r'Http(Get|Post|Put|Patch|Delete|Head|Options)')

# Route attribute
RE_ROUTE = re.compile(r'Route\s*\(\s*["\']([^"\']+)["\']')

# DI registration in Program.cs / Startup.cs
RE_DI_ADD = re.compile(
    r'\.Add(?:Scoped|Singleton|Transient)'
    r'(?:<(?P<iface>[\w.]+)\s*,\s*(?P<impl>[\w.]+)>)?'
    r'\s*\(',
    re.MULTILINE
)

# EF DbSet
RE_DBSET = re.compile(
    r'public\s+DbSet<(?P<entity>\w+)>\s+(?P<prop>\w+)',
    re.MULTILINE
)

# using directives
RE_USING = re.compile(r'^\s*using\s+([\w.]+);', re.MULTILINE)

# Calls inside method bodies: await X.MethodAsync / X.Method(
RE_CALL = re.compile(r'(?:await\s+)?(\w+)\.(\w+(?:Async)?)\s*[(<]')


# ─────────────────────────────────────────────
# Classifier helpers
# ─────────────────────────────────────────────

def classify_node_kind(name: str, base_types: list[str], attrs: list[str], bases_raw: str) -> str:
    name_l = name.lower()
    bases_l = (bases_raw or "").lower()

    if "ApiController" in attrs or "Controller" in attrs:
        return "controller"
    if "ControllerBase" in bases_l or "controller" in name_l:
        return "controller"
    if "DbContext" in (bases_raw or ""):
        return "dbcontext"
    if "IHostedService" in bases_l or "BackgroundService" in bases_l:
        return "backgroundservice"
    if name_l.endswith("middleware") or "RequestDelegate" in bases_l:
        return "middleware"
    if name_l.endswith("repository") or name_l.endswith("repo"):
        return "repository"
    if name_l.endswith("service"):
        return "service"
    if name_l.endswith("context") and "db" in name_l:
        return "dbcontext"
    if name_l.endswith("hub"):
        return "hub"
    if name_l.endswith("validator"):
        return "validator"
    if name_l.endswith("handler"):
        return "handler"
    if name_l.endswith("factory"):
        return "factory"
    if name_l.endswith("model") or name_l.endswith("dto") or name_l.endswith("request") or name_l.endswith("response"):
        return "model"
    return "class"


def classify_interface_kind(name: str) -> str:
    n = name.lower()
    if n.endswith("service"):     return "service_interface"
    if n.endswith("repository") or n.endswith("repo"): return "repository_interface"
    if n.endswith("context"):     return "context_interface"
    return "interface"


def build_tags(kind: str, name: str, attrs: list[str], is_async: bool, namespace: str) -> list[str]:
    tags = [kind]
    if is_async:
        tags.append("async")
    if any("Authorize" in a for a in attrs):
        tags.append("authorized")
    if any("AllowAnonymous" in a for a in attrs):
        tags.append("anonymous")
    if any(h in a for a in attrs for h in ("HttpGet","HttpPost","HttpPut","HttpPatch","HttpDelete")):
        tags.append("api-endpoint")
    if "controller" in kind:
        tags.append("web")
    if "repository" in kind:
        tags.append("data-access")
    if "service" in kind:
        tags.append("business-logic")
    if "dbcontext" in kind:
        tags.append("database")
    if "middleware" in kind:
        tags.append("pipeline")
    ns_parts = namespace.lower().split(".")
    for p in ns_parts:
        if p not in ("com","net","org","app","system","microsoft","aspnet","core"):
            tags.append(p)
    return list(dict.fromkeys(tags))  # deduplicate preserving order


# ─────────────────────────────────────────────
# File parser
# ─────────────────────────────────────────────

def extract_xml_summary(text: str, pos: int) -> str:
    """Look backward from pos for /// <summary>...</summary>."""
    preceding = text[:pos].rstrip()
    lines = preceding.split("\n")
    doc_lines = []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("///"):
            content = re.sub(r'///\s*</?summary>', '', stripped).strip()
            content = re.sub(r'///\s*', '', content).strip()
            if content:
                doc_lines.insert(0, content)
        else:
            break
    return " ".join(doc_lines).strip()


def parse_attrs(raw_attrs: str) -> list[str]:
    return [m.group(1).split("(")[0].strip() for m in RE_ATTR_STRIP.finditer(raw_attrs or "")]


def parse_params(params_str: str) -> list[dict]:
    params = []
    for p in params_str.split(","):
        p = p.strip()
        if not p:
            continue
        # strip attribute annotations like [FromBody]
        p = re.sub(r'\[[^\]]+\]\s*', '', p).strip()
        parts = p.split()
        if len(parts) >= 2:
            params.append({"type": parts[-2], "name": parts[-1].lstrip('_')})
        elif len(parts) == 1:
            params.append({"type": "object", "name": parts[0]})
    return params


def parse_bases(bases_raw: str | None) -> tuple[list[str], list[str]]:
    """Split base class vs interfaces from the inheritance list."""
    if not bases_raw:
        return [], []
    parts = [p.strip() for p in bases_raw.split(",")]
    base_classes = []
    ifaces = []
    for p in parts:
        p = re.sub(r'\s+', ' ', p).strip()
        if p.startswith("I") and p[1:2].isupper():
            ifaces.append(p)
        elif p:
            base_classes.append(p)
    return base_classes, ifaces


def line_number(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def count_block_lines(text: str, start_pos: int) -> int:
    """Find matching closing brace and return line count."""
    depth = 0
    for i, ch in enumerate(text[start_pos:], start_pos):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return line_number(text, i)
    return line_number(text, len(text) - 1)


def parse_cs_file(filepath: Path, root: Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return nodes, edges

    rel_path = str(filepath.relative_to(root)).replace("\\", "/")

    # Namespace
    ns_match = RE_NAMESPACE.search(text)
    namespace = ns_match.group(1) if ns_match else ""

    # Usings (for resolving short names later)
    usings = RE_USING.findall(text)

    # ── Classes / Structs / Records ──
    for m in RE_CLASS.finditer(text):
        name = m.group("name")
        raw_attrs = m.group("attrs") or ""
        attrs = parse_attrs(raw_attrs)
        mods = (m.group("mods") or "").lower()
        bases_raw = m.group("bases")
        base_classes, ifaces = parse_bases(bases_raw)
        generics = [g.strip() for g in (m.group("generics") or "").split(",") if g.strip()]

        kind = classify_node_kind(name, base_classes + ifaces, attrs, bases_raw or "")
        node_id = f"{namespace}.{name}" if namespace else name
        summary = extract_xml_summary(text, m.start())
        start_line = line_number(text, m.start())
        end_line = count_block_lines(text, m.start())

        vis_raw = m.group("vis") or "public"

        node = GraphNode(
            id=node_id,
            kind=kind,
            name=name,
            location=NodeLocation(file=rel_path, lines=[start_line, end_line], namespace=namespace),
            summary=summary,
            visibility=vis_raw,
            is_abstract="abstract" in mods,
            is_static="static" in mods,
            base_types=base_classes,
            interfaces=ifaces,
            attributes=attrs,
            generic_params=generics,
            tags=build_tags(kind, name, attrs, False, namespace),
        )
        nodes.append(node)

        # inheritance edges
        for b in base_classes:
            edges.append(GraphEdge(source=node_id, target=b, kind="inherits"))
        for iface in ifaces:
            edges.append(GraphEdge(source=node_id, target=iface, kind="implements"))

        # Constructor injection edges
        block_text = text[m.start():]
        for ctor in RE_CTOR.finditer(block_text):
            for p in parse_params(ctor.group("params")):
                ptype = p["type"]
                if ptype.startswith("I") and len(ptype) > 1 and ptype[1].isupper():
                    target_id = _resolve_type(ptype, namespace, usings)
                    edges.append(GraphEdge(source=node_id, target=target_id,
                                           kind="injects", label=p["name"]))
            break  # only first ctor

        # Field injection
        for f in RE_FIELD.finditer(block_text):
            target_id = _resolve_type(f.group("type"), namespace, usings)
            edges.append(GraphEdge(source=node_id, target=target_id, kind="injects"))

        # DbSet properties → entity edges
        if kind == "dbcontext":
            for ds in RE_DBSET.finditer(block_text):
                entity = ds.group("entity")
                target_id = _resolve_type(entity, namespace, usings)
                edges.append(GraphEdge(source=node_id, target=target_id, kind="has_entity"))

    # ── Interfaces ──
    for m in RE_INTERFACE.finditer(text):
        name = m.group("name")
        bases_raw = m.group("bases")
        _, parent_ifaces = parse_bases(bases_raw)
        generics = [g.strip() for g in (m.group("generics") or "").split(",") if g.strip()]

        kind = classify_interface_kind(name)
        node_id = f"{namespace}.{name}" if namespace else name
        summary = extract_xml_summary(text, m.start())
        start_line = line_number(text, m.start())
        end_line = count_block_lines(text, m.start())

        node = GraphNode(
            id=node_id,
            kind=kind,
            name=name,
            location=NodeLocation(file=rel_path, lines=[start_line, end_line], namespace=namespace),
            summary=summary,
            interfaces=parent_ifaces,
            generic_params=generics,
            tags=build_tags(kind, name, [], False, namespace),
        )
        nodes.append(node)

        for iface in parent_ifaces:
            edges.append(GraphEdge(source=node_id, target=iface, kind="extends"))

    # ── Methods (top-level scan for controllers) ──
    # We do a simplified method scan — we only index public controller actions
    # to keep the graph lean. Non-controller methods are inferred via call edges.
    parent_controller = next((n for n in nodes if n.kind == "controller"), None)
    if parent_controller:
        for m in RE_METHOD.finditer(text):
            name = m.group("name")
            raw_attrs = m.group("attrs") or ""
            attrs = parse_attrs(raw_attrs)
            mods = (m.group("mods") or "").lower()
            ret = (m.group("ret") or "").strip()
            params = parse_params(m.group("params") or "")
            generics = [g.strip() for g in (m.group("generics") or "").split(",") if g.strip()]

            # Only index HTTP action methods
            http_verbs = [a for a in attrs if RE_HTTP_VERB.match(a)]
            if not http_verbs:
                continue

            is_async = "async" in mods
            method_id = f"{parent_controller.id}.{name}"
            summary = extract_xml_summary(text, m.start())
            start_line = line_number(text, m.start())

            node = GraphNode(
                id=method_id,
                kind="action",
                name=name,
                location=NodeLocation(file=rel_path, lines=[start_line, start_line + 10], namespace=namespace),
                summary=summary,
                visibility="public",
                is_async=is_async,
                attributes=attrs,
                return_type=ret,
                parameters=params,
                generic_params=generics,
                tags=build_tags("action", name, attrs, is_async, namespace),
            )
            nodes.append(node)
            edges.append(GraphEdge(source=parent_controller.id, target=method_id,
                                   kind="has_action", label=" ".join(http_verbs)))

    # ── DI registrations (Program.cs / Startup.cs) ──
    filename = filepath.name.lower()
    if filename in ("program.cs", "startup.cs"):
        for m in RE_DI_ADD.finditer(text):
            iface = m.group("iface")
            impl = m.group("impl")
            if iface and impl:
                iface_id = _resolve_type(iface, namespace, usings)
                impl_id = _resolve_type(impl, namespace, usings)
                edges.append(GraphEdge(source="DI.Container", target=iface_id,
                                       kind="registers", label=impl))

    return nodes, edges


def _resolve_type(short_name: str, namespace: str, usings: list[str]) -> str:
    """Best-effort: return qualified id for a short type name."""
    # Already qualified
    if "." in short_name:
        return short_name
    # Try to find matching using
    for u in usings:
        if u.endswith(f".{short_name}") or u.split(".")[-1] == short_name:
            return f"{u}.{short_name}" if not u.endswith(short_name) else u
    # Fall back to same namespace
    if namespace:
        return f"{namespace}.{short_name}"
    return short_name


# ─────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────

DEFAULT_EXCLUDES = [
    "**/obj/**", "**/bin/**", "**/publish/**",
    "**/.git/**", "**/.vs/**", "**/node_modules/**",
    "**/*.Designer.cs", "**/*.g.cs", "**/*.g.i.cs",
    "**/Migrations/**", "**/Scaffold-DbContext/**",
    "**/*.AssemblyInfo.cs",
]


def should_exclude(path: Path, root: Path, patterns: list[str]) -> bool:
    rel = str(path.relative_to(root)).replace("\\", "/")
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat.lstrip("*/")):
            return True
        if fnmatch.fnmatch("/" + rel, pat):
            return True
        # simple folder match
        parts = pat.strip("*/")
        if parts and parts in rel:
            return True
    return False


def build_graph(root: Path, extra_excludes: list[str]) -> dict:
    all_nodes: list[GraphNode] = []
    all_edges: list[GraphEdge] = []
    excludes = DEFAULT_EXCLUDES + extra_excludes

    cs_files = sorted(root.rglob("*.cs"))
    processed = 0

    for cs_file in cs_files:
        if should_exclude(cs_file, root, excludes):
            continue
        nodes, edges = parse_cs_file(cs_file, root)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        processed += 1

    # Deduplicate nodes (same id from partial classes)
    seen_ids: dict[str, GraphNode] = {}
    for n in all_nodes:
        if n.id not in seen_ids:
            seen_ids[n.id] = n
        else:
            # Merge: take longer summary, append tags
            existing = seen_ids[n.id]
            if len(n.summary) > len(existing.summary):
                existing.summary = n.summary
            existing.tags = list(dict.fromkeys(existing.tags + n.tags))

    final_nodes = list(seen_ids.values())

    # Resolve edge targets to canonical ids
    known_ids = {n.id for n in final_nodes}
    # Also build short-name → id index
    short_index: dict[str, str] = {}
    for n in final_nodes:
        short_index[n.name] = n.id
        # Interface name → impl id
        for iface in n.interfaces:
            short_index[iface] = n.id

    resolved_edges: list[GraphEdge] = []
    seen_edges: set[tuple] = set()
    for e in all_edges:
        # Try to resolve target
        target = e.target
        if target not in known_ids:
            if target in short_index:
                target = short_index[target]
            elif target.split(".")[-1] in short_index:
                target = short_index[target.split(".")[-1]]

        key = (e.source, target, e.kind)
        if key not in seen_edges and e.source != target:
            seen_edges.add(key)
            resolved_edges.append(GraphEdge(
                source=e.source,
                target=target,
                kind=e.kind,
                label=e.label
            ))

    # Stats
    stats = GraphStats(
        total_files=processed,
        total_nodes=len(final_nodes),
        total_edges=len(resolved_edges),
        controllers=sum(1 for n in final_nodes if n.kind == "controller"),
        services=sum(1 for n in final_nodes if "service" in n.kind),
        repositories=sum(1 for n in final_nodes if "repository" in n.kind),
        models=sum(1 for n in final_nodes if n.kind == "model"),
        interfaces=sum(1 for n in final_nodes if "interface" in n.kind),
        middlewares=sum(1 for n in final_nodes if n.kind == "middleware"),
        dbcontexts=sum(1 for n in final_nodes if n.kind == "dbcontext"),
    )

    # Compute a content hash so consumers can detect changes
    content = json.dumps(
        [asdict(n) for n in sorted(final_nodes, key=lambda x: x.id)],
        sort_keys=True
    )
    graph_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    return {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "gen_graph.py",
        "language": "csharp",
        "hash": graph_hash,
        "stats": asdict(stats),
        "nodes": [_node_to_dict(n) for n in sorted(final_nodes, key=lambda x: x.id)],
        "edges": [_edge_to_dict(e) for e in resolved_edges],
    }


def _node_to_dict(n: GraphNode) -> dict:
    d = {
        "id": n.id,
        "kind": n.kind,
        "name": n.name,
        "file": n.location.file,
        "lines": n.location.lines,
        "namespace": n.location.namespace,
        "summary": n.summary,
        "visibility": n.visibility,
        "tags": n.tags,
    }
    # Only include non-default / non-empty optional fields
    if n.is_abstract:      d["is_abstract"] = True
    if n.is_static:        d["is_static"] = True
    if n.is_async:         d["is_async"] = True
    if n.base_types:       d["base_types"] = n.base_types
    if n.interfaces:       d["interfaces"] = n.interfaces
    if n.attributes:       d["attributes"] = n.attributes
    if n.return_type:      d["return_type"] = n.return_type
    if n.parameters:       d["parameters"] = n.parameters
    if n.generic_params:   d["generic_params"] = n.generic_params
    return d


def _edge_to_dict(e: GraphEdge) -> dict:
    d = {"source": e.source, "target": e.target, "kind": e.kind}
    if e.label:
        d["label"] = e.label
    return d


# ─────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────

COLORS = {
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "cyan":   "\033[96m",
    "gray":   "\033[90m",
    "reset":  "\033[0m",
    "bold":   "\033[1m",
}

def c(text: str, color: str) -> str:
    if sys.stdout.isatty():
        return f"{COLORS.get(color,'')}{text}{COLORS['reset']}"
    return text


def print_summary(graph: dict) -> None:
    s = graph["stats"]
    print()
    print(c("  CodeGraph — .NET Codebase Map", "bold"))
    print(c(f"  Generated: {graph['generated'][:19].replace('T',' ')} UTC", "gray"))
    print(c(f"  Hash:      {graph['hash']}", "gray"))
    print()
    print(c(f"  {'Files scanned:':<22} {s['total_files']}", "cyan"))
    print(c(f"  {'Nodes extracted:':<22} {s['total_nodes']}", "cyan"))
    print(c(f"  {'Edges mapped:':<22} {s['total_edges']}", "cyan"))
    print()
    print(c(f"  {'Controllers:':<22} {s['controllers']}", "green"))
    print(c(f"  {'Services:':<22} {s['services']}", "green"))
    print(c(f"  {'Repositories:':<22} {s['repositories']}", "green"))
    print(c(f"  {'Interfaces:':<22} {s['interfaces']}", "green"))
    print(c(f"  {'Models/DTOs:':<22} {s['models']}", "green"))
    print(c(f"  {'Middlewares:':<22} {s['middlewares']}", "green"))
    print(c(f"  {'DbContexts:':<22} {s['dbcontexts']}", "green"))
    print()


def print_node_tree(graph: dict) -> None:
    """Print a tree of nodes grouped by kind."""
    groups: dict[str, list] = {}
    for n in graph["nodes"]:
        groups.setdefault(n["kind"], []).append(n)

    for kind, nodes in sorted(groups.items()):
        print(c(f"\n  [{kind.upper()}]", "yellow"))
        for n in sorted(nodes, key=lambda x: x["name"]):
            summary = f" — {n['summary'][:60]}" if n.get("summary") else ""
            print(f"    {c(n['id'], 'cyan')}{c(summary, 'gray')}")


# ─────────────────────────────────────────────
# Watch mode
# ─────────────────────────────────────────────

def get_file_hashes(root: Path) -> dict[str, float]:
    return {
        str(f): f.stat().st_mtime
        for f in root.rglob("*.cs")
    }


def watch_mode(root: Path, output: Path, extra_excludes: list[str]) -> None:
    print(c(f"  Watching {root} for changes… (Ctrl-C to stop)", "yellow"))
    last_hashes = get_file_hashes(root)
    _run_and_write(root, output, extra_excludes, quiet=False)

    while True:
        time.sleep(2)
        current = get_file_hashes(root)
        if current != last_hashes:
            changed = [f for f in current if current[f] != last_hashes.get(f)]
            for f in changed:
                print(c(f"  Changed: {f}", "yellow"))
            last_hashes = current
            _run_and_write(root, output, extra_excludes, quiet=True)
            print(c(f"  Graph updated → {output}", "green"))


def _run_and_write(root: Path, output: Path, extra_excludes: list[str], quiet: bool) -> None:
    graph = build_graph(root, extra_excludes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    if not quiet:
        print_summary(graph)
        print(c(f"  Written → {output}", "green"))
        print()


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a codebase memory graph for .NET / C# projects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--root", "-r",
        default=".",
        help="Root directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--output", "-o",
        default="codebase-graph.json",
        help="Output JSON file (default: codebase-graph.json)",
    )
    parser.add_argument(
        "--exclude", "-e",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Additional glob patterns to exclude (repeatable)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print stats summary only (don't write file)",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Print node tree after generating",
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Watch mode: re-generate when .cs files change",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: true)",
    )
    parser.add_argument(
        "--minify",
        action="store_true",
        help="Minify JSON output (overrides --pretty)",
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(c(f"  Error: root path does not exist: {root}", "red"), file=sys.stderr)
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