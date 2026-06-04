#!/usr/bin/env python3
"""
gen_graph_java.py — Codebase Memory Graph Generator for Java / Spring Boot
===========================================================================
Parses Java source files and builds a structured graph of classes, interfaces,
controllers, services, repositories, entities, filters, and their relationships.
Designed for Spring Boot / Spring MVC / JPA projects.

Usage:
    python gen_graph_java.py                          # scan current directory
    python gen_graph_java.py --root ./src             # scan specific folder
    python gen_graph_java.py --output graph.json      # custom output path
    python gen_graph_java.py --exclude "**/test/**"   # exclude patterns
    python gen_graph_java.py --tree                   # print node tree
    python gen_graph_java.py --summary                # stats only
    python gen_graph_java.py --watch                  # watch mode

Requirements:
    Python 3.9+  (no third-party packages needed)

Supports:
    Spring Boot / Spring MVC (@RestController, @Controller)
    Spring Data JPA (@Repository, extends JpaRepository)
    Spring Services (@Service, @Component)
    Spring Security (@PreAuthorize, @Secured)
    Spring Config (@Configuration, @Bean)
    Constructor injection, @Autowired field injection
    Jakarta / javax Servlet Filters (@Component + implements Filter)
    Javadoc /** */ comment extraction
    Generic types (Repository<User, UUID>)
    @Entity JPA models
    @Bean wiring in @Configuration classes
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
# Data models  (identical shape to gen_graph.py)
# ─────────────────────────────────────────────

@dataclass
class NodeLocation:
    file: str
    lines: list[int]
    package: str = ""


@dataclass
class GraphNode:
    id: str
    kind: str           # controller | service | repository | entity | config
                        # filter | component | interface | model | enum
    name: str
    location: NodeLocation
    summary: str = ""
    visibility: str = "public"
    is_abstract: bool = False
    is_interface: bool = False
    base_types: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    generic_params: list[str] = field(default_factory=list)
    methods: list[dict] = field(default_factory=list)


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str       # injects | implements | extends | has_mapping
                    # has_entity | registers_bean | uses | depends_on
    label: str = ""


@dataclass
class GraphStats:
    total_files: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    controllers: int = 0
    services: int = 0
    repositories: int = 0
    entities: int = 0
    components: int = 0
    filters: int = 0
    configs: int = 0
    interfaces: int = 0


# ─────────────────────────────────────────────
# Java-specific regex patterns
# ─────────────────────────────────────────────

# Package declaration
RE_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)

# Import statements (for resolving short names)
RE_IMPORT = re.compile(r'^\s*import\s+([\w.]+(?:\.\*)?)\s*;', re.MULTILINE)

# All annotations above a declaration (may be multi-line)
RE_ANNOTATION = re.compile(r'@([\w]+)(?:\s*\([^)]*\))?', re.MULTILINE)

# Class / interface / enum declaration
RE_CLASS = re.compile(
    r'(?P<javadoc>/\*\*.*?\*/\s*)?'                         # optional Javadoc
    r'(?P<annots>(?:@[\w]+(?:\s*\([^)]*\))?\s*\n?\s*)*)'   # annotations block
    r'\s*(?P<vis>public|protected|private)?\s*'
    r'(?P<mods>(?:(?:abstract|final|static)\s+)*)'
    r'(?P<kind>class|interface|enum|record)\s+'
    r'(?P<name>\w+)'
    r'(?:<(?P<generics>[^>]+)>)?'                           # <T, K>
    r'(?:\s+extends\s+(?P<extends>[\w<>, .]+?))?'          # extends BaseClass
    r'(?:\s+implements\s+(?P<implements>[\w<>, .]+?))?'    # implements IFace
    r'\s*\{',
    re.DOTALL | re.MULTILINE
)

# Method declaration
RE_METHOD = re.compile(
    r'(?P<annots>(?:\s*@[\w]+(?:\s*\([^)]*\))?\s*\n?\s*)*)'
    r'\s*(?P<vis>public|protected|private)?\s*'
    r'(?P<mods>(?:(?:static|final|synchronized|default|abstract)\s+)*)'
    r'(?P<ret>[\w<>\[\]?,\s.]+?)\s+'
    r'(?P<name>[a-z]\w*)\s*'
    r'\((?P<params>[^)]*)\)',
    re.MULTILINE
)

# Constructor
RE_CTOR = re.compile(
    r'(?:public|protected)\s+(?P<cname>\w+)\s*\((?P<params>[^)]*)\)',
    re.MULTILINE
)

# @Autowired field injection
RE_AUTOWIRED_FIELD = re.compile(
    r'@Autowired\s+(?:private\s+)?(?:final\s+)?'
    r'(?P<type>[\w<>]+)\s+(?P<name>\w+)\s*;',
    re.MULTILINE
)

# @Inject field injection (Jakarta / javax)
RE_INJECT_FIELD = re.compile(
    r'@(?:Inject|Resource)\s+(?:private\s+)?(?:final\s+)?'
    r'(?P<type>[\w<>]+)\s+(?P<name>\w+)\s*;',
    re.MULTILINE
)

# Private final field (for constructor injection detection)
RE_PRIVATE_FINAL = re.compile(
    r'private\s+final\s+(?P<type>[\w<>]+)\s+(?P<name>\w+)\s*;',
    re.MULTILINE
)

# @Bean method in @Configuration
RE_BEAN = re.compile(
    r'@Bean\s+(?:public\s+)?(?P<ret>[\w<>]+)\s+(?P<name>\w+)\s*\(',
    re.MULTILINE
)

# Spring HTTP mapping annotations
RE_HTTP_MAPPING = re.compile(
    r'@(Get|Post|Put|Patch|Delete|Request)Mapping'
    r'(?:\s*\(\s*(?:value\s*=\s*)?["\']?([^)"\']*)["\']?\s*\))?',
    re.MULTILINE
)

# @RequestMapping at class level (base path)
RE_REQUEST_MAPPING = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\']',
    re.MULTILINE
)

# @Entity, @Table
RE_ENTITY = re.compile(r'@Entity\b', re.MULTILINE)

# Javadoc extraction
RE_JAVADOC = re.compile(r'/\*\*(.*?)\*/', re.DOTALL)
RE_JAVADOC_CLEAN = re.compile(r'^\s*\*\s?', re.MULTILINE)


# ─────────────────────────────────────────────
# Spring annotation → kind classifier
# ─────────────────────────────────────────────

# Priority-ordered annotation → kind mapping
ANNOTATION_KIND_MAP = [
    ({"RestController", "Controller"},              "controller"),
    ({"Service"},                                   "service"),
    ({"Repository"},                                "repository"),
    ({"Entity"},                                    "entity"),
    ({"Configuration"},                             "config"),
    ({"Component"},                                 "component"),
    ({"ControllerAdvice", "RestControllerAdvice"},  "advice"),
]

# Interface kind by naming convention
INTERFACE_CONVENTION = [
    ("Repository",  "repository_interface"),
    ("Service",     "service_interface"),
    ("Mapper",      "mapper_interface"),
    ("Client",      "client_interface"),
    ("Gateway",     "gateway_interface"),
]

def classify_java_kind(
    name: str,
    annotations: list[str],
    is_interface: bool,
    extends_list: list[str],
    implements_list: list[str],
    is_enum: bool,
) -> str:
    ann_set = set(annotations)

    # Annotation wins first
    for ann_group, kind in ANNOTATION_KIND_MAP:
        if ann_set & ann_group:
            return kind

    # Interface: check what it extends
    if is_interface:
        for base in extends_list:
            if "JpaRepository" in base or "CrudRepository" in base \
                    or "MongoRepository" in base or "PagingAndSortingRepository" in base:
                return "repository_interface"
        for suffix, kind in INTERFACE_CONVENTION:
            if name.endswith(suffix):
                return kind
        return "interface"

    # Enum
    if is_enum:
        return "enum"

    # Filter / Interceptor by implements
    for iface in implements_list:
        clean = iface.split("<")[0].strip()
        if clean in ("Filter", "HandlerInterceptor", "OncePerRequestFilter"):
            return "filter"

    # Base class
    for base in extends_list:
        clean = base.split("<")[0].strip()
        if clean == "OncePerRequestFilter":
            return "filter"
        if clean in ("RuntimeException", "Exception", "IllegalArgumentException"):
            return "exception"

    # Naming convention fallback
    n = name.lower()
    if n.endswith("controller"):  return "controller"
    if n.endswith("service"):     return "service"
    if n.endswith("serviceimpl"): return "service"
    if n.endswith("repository") or n.endswith("repo"): return "repository"
    if n.endswith("filter") or n.endswith("interceptor"): return "filter"
    if n.endswith("config") or n.endswith("configuration"): return "config"
    if n.endswith("dto") or n.endswith("request") or n.endswith("response"): return "model"
    if n.endswith("entity"):      return "entity"
    if n.endswith("mapper"):      return "mapper"
    if n.endswith("handler"):     return "handler"
    if n.endswith("listener"):    return "listener"
    if n.endswith("scheduler"):   return "scheduler"
    if n.endswith("factory"):     return "factory"
    if n.endswith("util") or n.endswith("utils") or n.endswith("helper"): return "util"

    return "class"


def build_tags(
    kind: str,
    name: str,
    annotations: list[str],
    package: str,
) -> list[str]:
    tags = [kind]
    ann_set = set(annotations)

    if "PreAuthorize" in ann_set or "Secured" in ann_set:
        tags.append("secured")
    if "Transactional" in ann_set:
        tags.append("transactional")
    if "Async" in ann_set:
        tags.append("async")
    if "Scheduled" in ann_set:
        tags.append("scheduled")
    if "Cacheable" in ann_set or "CacheEvict" in ann_set:
        tags.append("cached")
    if kind in ("controller",):
        tags.append("web")
        tags.append("api-endpoint")
    if kind in ("repository", "repository_interface"):
        tags.append("data-access")
    if kind == "entity":
        tags.append("database")
        tags.append("jpa")
    if kind == "filter":
        tags.append("pipeline")
    if kind == "service":
        tags.append("business-logic")

    # Add meaningful package segments as tags
    for seg in package.split("."):
        if seg not in ("com", "org", "net", "app", "java", "javax",
                       "jakarta", "spring", "springframework", "main"):
            tags.append(seg)

    return list(dict.fromkeys(tags))


# ─────────────────────────────────────────────
# Javadoc extractor
# ─────────────────────────────────────────────

def extract_javadoc(text: str, pos: int) -> str:
    """Look backward from pos to find the nearest /** ... */ block."""
    preceding = text[:pos].rstrip()
    # Find last /** block
    start = preceding.rfind("/**")
    if start == -1:
        return ""
    end = preceding.rfind("*/")
    if end == -1 or end < start:
        return ""
    raw = preceding[start:end + 2]
    # Strip * prefixes and @tags
    lines = RE_JAVADOC_CLEAN.sub("", raw)
    lines = re.sub(r'/\*\*|\*/', "", lines)
    lines = re.sub(r'@\w+.*', "", lines)  # strip @param, @return etc
    return " ".join(lines.split()).strip()


# ─────────────────────────────────────────────
# Type / name helpers
# ─────────────────────────────────────────────

def parse_type_list(raw: str | None) -> list[str]:
    """Split 'BaseClass, IFace1, IFace2' into clean list."""
    if not raw:
        return []
    return [p.split("<")[0].strip() for p in raw.split(",") if p.strip()]


def line_number(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def count_block_end(text: str, start: int) -> int:
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return line_number(text, i)
    return line_number(text, len(text) - 1)


def parse_params(raw: str) -> list[dict]:
    params = []
    for p in raw.split(","):
        p = p.strip()
        if not p:
            continue
        # Remove annotations like @RequestBody, @PathVariable
        p = re.sub(r'@\w+(?:\([^)]*\))?\s*', "", p).strip()
        # Remove final keyword
        p = re.sub(r'\bfinal\b', "", p).strip()
        parts = p.split()
        if len(parts) >= 2:
            ptype = parts[-2].split("<")[0]  # strip generics
            pname = parts[-1]
            params.append({"type": ptype, "name": pname})
    return params


def extract_annotations(raw: str) -> list[str]:
    return [m.group(1) for m in RE_ANNOTATION.finditer(raw or "")]


def resolve_type(short: str, package: str, imports: list[str]) -> str:
    """Best-effort qualified name resolution."""
    short_clean = short.split("<")[0].strip()
    if "." in short_clean:
        return short_clean
    for imp in imports:
        if imp.endswith("." + short_clean):
            return imp
        if imp.endswith(".*"):
            base = imp[:-2]
            return f"{base}.{short_clean}"
    return f"{package}.{short_clean}" if package else short_clean


# ─────────────────────────────────────────────
# Per-file parser
# ─────────────────────────────────────────────

def parse_java_file(filepath: Path, root: Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return nodes, edges

    rel_path = str(filepath.relative_to(root)).replace("\\", "/")

    # Package
    pm = RE_PACKAGE.search(text)
    package = pm.group(1) if pm else ""

    # Imports
    imports = RE_IMPORT.findall(text)

    # ── Classes / Interfaces / Enums ──
    for m in RE_CLASS.finditer(text):
        raw_annots = m.group("annots") or ""
        annotations = extract_annotations(raw_annots)
        name = m.group("name")
        kind_raw = m.group("kind")          # class | interface | enum | record
        mods_raw = (m.group("mods") or "").lower()
        extends_raw = m.group("extends")
        implements_raw = m.group("implements")
        generics = [g.strip() for g in (m.group("generics") or "").split(",") if g.strip()]

        extends_list  = parse_type_list(extends_raw)
        implements_list = parse_type_list(implements_raw)

        is_interface = kind_raw == "interface"
        is_enum = kind_raw == "enum"
        is_abstract = "abstract" in mods_raw or is_interface

        kind = classify_java_kind(
            name, annotations, is_interface,
            extends_list, implements_list, is_enum
        )

        node_id = f"{package}.{name}" if package else name
        summary = extract_javadoc(text, m.start())
        start_line = line_number(text, m.start())
        end_line = count_block_end(text, m.start())

        node = GraphNode(
            id=node_id,
            kind=kind,
            name=name,
            location=NodeLocation(
                file=rel_path,
                lines=[start_line, end_line],
                package=package
            ),
            summary=summary,
            visibility=m.group("vis") or "package-private",
            is_abstract=is_abstract,
            is_interface=is_interface,
            base_types=extends_list,
            interfaces=implements_list,
            annotations=annotations,
            generic_params=generics,
            tags=build_tags(kind, name, annotations, package),
        )
        nodes.append(node)

        # ── Inheritance edges ──
        for base in extends_list:
            target = resolve_type(base, package, imports)
            edges.append(GraphEdge(source=node_id, target=target, kind="extends"))

        for iface in implements_list:
            target = resolve_type(iface, package, imports)
            edges.append(GraphEdge(source=node_id, target=target, kind="implements"))

        # Slice class body for dependency analysis
        # (work within the file after the opening brace)
        body_start = text.find("{", m.start())
        if body_start == -1:
            continue
        # Rough body: next 3000 chars is enough for field/ctor scanning
        body = text[body_start: body_start + 6000]

        # ── Constructor injection ──
        for ctor in RE_CTOR.finditer(body):
            if ctor.group("cname") != name:
                continue
            for p in parse_params(ctor.group("params")):
                ptype = p["type"]
                if ptype in ("String", "int", "long", "boolean", "double",
                             "Integer", "Long", "Boolean", "List", "Map", "Optional"):
                    continue
                target = resolve_type(ptype, package, imports)
                edges.append(GraphEdge(
                    source=node_id, target=target,
                    kind="injects", label=p["name"]
                ))
            break  # primary constructor only

        # ── @Autowired field injection ──
        for f in RE_AUTOWIRED_FIELD.finditer(body):
            target = resolve_type(f.group("type"), package, imports)
            edges.append(GraphEdge(source=node_id, target=target,
                                   kind="injects", label=f.group("name")))

        # ── @Inject field injection ──
        for f in RE_INJECT_FIELD.finditer(body):
            target = resolve_type(f.group("type"), package, imports)
            edges.append(GraphEdge(source=node_id, target=target,
                                   kind="injects", label=f.group("name")))

        # ── HTTP action methods (controllers only) ──
        if kind == "controller":
            for mm in RE_METHOD.finditer(body):
                method_annots = extract_annotations(mm.group("annots") or "")
                http_ann = [a for a in method_annots
                            if a in ("GetMapping","PostMapping","PutMapping",
                                     "PatchMapping","DeleteMapping","RequestMapping")]
                if not http_ann:
                    continue
                mname = mm.group("name")
                method_id = f"{node_id}.{mname}"
                msummary = extract_javadoc(body, mm.start())
                mstart = start_line + line_number(body, mm.start()) - 1
                mnode = GraphNode(
                    id=method_id,
                    kind="action",
                    name=mname,
                    location=NodeLocation(
                        file=rel_path,
                        lines=[mstart, mstart + 8],
                        package=package
                    ),
                    summary=msummary,
                    annotations=method_annots,
                    tags=build_tags("action", mname, method_annots, package),
                )
                nodes.append(mnode)
                edges.append(GraphEdge(
                    source=node_id, target=method_id,
                    kind="has_mapping", label=", ".join(http_ann)
                ))

        # ── @Bean registrations in @Configuration ──
        if kind == "config":
            for bm in RE_BEAN.finditer(body):
                bean_type = bm.group("ret")
                bean_name = bm.group("name")
                target = resolve_type(bean_type, package, imports)
                edges.append(GraphEdge(
                    source=node_id, target=target,
                    kind="registers_bean", label=bean_name
                ))

    return nodes, edges


# ─────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────

DEFAULT_EXCLUDES = [
    "**/target/**",
    "**/build/**",
    "**/.git/**",
    "**/test/**",
    "**/Test*.java",
    "**/*Test.java",
    "**/*Tests.java",
    "**/node_modules/**",
    "**/generated-sources/**",
    "**/generated/**",
]


def should_exclude(path: Path, root: Path, patterns: list[str]) -> bool:
    rel = str(path.relative_to(root)).replace("\\", "/")
    for pat in patterns:
        pat_clean = pat.strip("*/")
        if fnmatch.fnmatch(rel, pat.lstrip("*/")):
            return True
        if pat_clean and pat_clean in rel:
            return True
    return False


def build_graph(root: Path, extra_excludes: list[str]) -> dict:
    all_nodes: list[GraphNode] = []
    all_edges: list[GraphEdge] = []
    excludes = DEFAULT_EXCLUDES + extra_excludes

    java_files = sorted(root.rglob("*.java"))
    processed = 0

    for jf in java_files:
        if should_exclude(jf, root, excludes):
            continue
        n, e = parse_java_file(jf, root)
        all_nodes.extend(n)
        all_edges.extend(e)
        processed += 1

    # Deduplicate nodes by id
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
    known_ids = {n.id for n in final_nodes}

    # Short-name → id index for edge resolution
    short_index: dict[str, str] = {}
    for n in final_nodes:
        short_index[n.name] = n.id
        for iface in n.interfaces:
            short_index[iface] = n.id

    # Resolve and deduplicate edges
    seen_edges: set[tuple] = set()
    final_edges: list[GraphEdge] = []
    for e in all_edges:
        target = e.target
        if target not in known_ids:
            tshort = target.split(".")[-1]
            if tshort in short_index:
                target = short_index[tshort]

        key = (e.source, target, e.kind)
        if key not in seen_edges and e.source != target:
            seen_edges.add(key)
            final_edges.append(GraphEdge(
                source=e.source, target=target,
                kind=e.kind, label=e.label
            ))

    # Stats
    stats = GraphStats(
        total_files=processed,
        total_nodes=len(final_nodes),
        total_edges=len(final_edges),
        controllers=sum(1 for n in final_nodes if n.kind == "controller"),
        services=sum(1 for n in final_nodes if n.kind == "service"),
        repositories=sum(1 for n in final_nodes if "repository" in n.kind),
        entities=sum(1 for n in final_nodes if n.kind == "entity"),
        components=sum(1 for n in final_nodes if n.kind == "component"),
        filters=sum(1 for n in final_nodes if n.kind == "filter"),
        configs=sum(1 for n in final_nodes if n.kind == "config"),
        interfaces=sum(1 for n in final_nodes if "interface" in n.kind),
    )

    content = json.dumps(
        [asdict(n) for n in sorted(final_nodes, key=lambda x: x.id)],
        sort_keys=True
    )
    graph_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    return {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "gen_graph_java.py",
        "language": "java",
        "framework": "spring",
        "hash": graph_hash,
        "stats": asdict(stats),
        "nodes": [_node_to_dict(n) for n in sorted(final_nodes, key=lambda x: x.id)],
        "edges": [_edge_to_dict(e) for e in final_edges],
    }


def _node_to_dict(n: GraphNode) -> dict:
    d = {
        "id": n.id,
        "kind": n.kind,
        "name": n.name,
        "file": n.location.file,
        "lines": n.location.lines,
        "package": n.location.package,
        "summary": n.summary,
        "visibility": n.visibility,
        "tags": n.tags,
    }
    if n.is_abstract:      d["is_abstract"] = True
    if n.is_interface:     d["is_interface"] = True
    if n.base_types:       d["base_types"] = n.base_types
    if n.interfaces:       d["interfaces"] = n.interfaces
    if n.annotations:      d["annotations"] = n.annotations
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
    "green":  "\033[92m", "yellow": "\033[93m",
    "cyan":   "\033[96m", "gray":   "\033[90m",
    "reset":  "\033[0m",  "bold":   "\033[1m",
}

def c(text: str, color: str) -> str:
    return f"{COLORS.get(color,'')}{text}{COLORS['reset']}" if sys.stdout.isatty() else text


def print_summary(graph: dict) -> None:
    s = graph["stats"]
    print()
    print(c("  CodeGraph — Java / Spring Boot Codebase Map", "bold"))
    print(c(f"  Generated : {graph['generated'][:19].replace('T',' ')} UTC", "gray"))
    print(c(f"  Hash      : {graph['hash']}", "gray"))
    print()
    print(c(f"  {'Files scanned:':<24} {s['total_files']}", "cyan"))
    print(c(f"  {'Nodes extracted:':<24} {s['total_nodes']}", "cyan"))
    print(c(f"  {'Edges mapped:':<24} {s['total_edges']}", "cyan"))
    print()
    print(c(f"  {'Controllers:':<24} {s['controllers']}", "green"))
    print(c(f"  {'Services:':<24} {s['services']}", "green"))
    print(c(f"  {'Repositories:':<24} {s['repositories']}", "green"))
    print(c(f"  {'Entities:':<24} {s['entities']}", "green"))
    print(c(f"  {'Interfaces:':<24} {s['interfaces']}", "green"))
    print(c(f"  {'Filters:':<24} {s['filters']}", "green"))
    print(c(f"  {'Config classes:':<24} {s['configs']}", "green"))
    print(c(f"  {'Components:':<24} {s['components']}", "green"))
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


# ─────────────────────────────────────────────
# Watch mode
# ─────────────────────────────────────────────

def get_mtimes(root: Path) -> dict[str, float]:
    return {str(f): f.stat().st_mtime for f in root.rglob("*.java")}


def watch_mode(root: Path, output: Path, extra: list[str]) -> None:
    print(c(f"  Watching {root} … (Ctrl-C to stop)", "yellow"))
    last = get_mtimes(root)
    _run(root, output, extra, quiet=False)
    while True:
        time.sleep(2)
        cur = get_mtimes(root)
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


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a codebase memory graph for Java / Spring Boot projects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", "-r", default=".", help="Root directory to scan")
    parser.add_argument("--output", "-o", default="codebase-graph.json", help="Output JSON file")
    parser.add_argument("--exclude", "-e", action="append", default=[], metavar="PATTERN")
    parser.add_argument("--summary", action="store_true", help="Print stats only")
    parser.add_argument("--tree", action="store_true", help="Print node tree")
    parser.add_argument("--watch", "-w", action="store_true", help="Watch mode")
    parser.add_argument("--minify", action="store_true", help="Minify JSON")
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