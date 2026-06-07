#!/usr/bin/env python3
"""
gen_graph_typescript.py — Codebase Memory Graph Generator for TypeScript / Node.js
====================================================================================
Supports: Express · NestJS · Fastify · Prisma · TypeORM · Inversify

Parses TypeScript source files and extracts:
  Classes — controllers, services, repositories, middleware, utils
  NestJS decorators — @Controller, @Injectable, @Module, @Guard, @Interceptor
  Express route handlers — router.get/post/put/patch/delete
  Constructor injection (typed parameters) → dependency edges
  Interface and type alias definitions
  Enum declarations
  Module-level function exports (middleware factories, config loaders)
  JSDoc /** */ → node summaries
  Import-based cross-module edges
  app.ts / main.ts bootstrap wiring

Usage:
    python gen_graph_typescript.py                        # current directory
    python gen_graph_typescript.py --root ./src           # specific folder
    python gen_graph_typescript.py --output graph.json    # custom output
    python gen_graph_typescript.py --exclude "**/test/**"
    python gen_graph_typescript.py --tree
    python gen_graph_typescript.py --watch

Requirements: Python 3.9+  (no third-party packages)
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
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
    kind: str               # controller | service | repository | middleware
                            # model | interface | enum | util | config
                            # guard | interceptor | module | pipe | function
                            # decorator | type | resolver | gateway
    name: str
    location: NodeLocation
    summary: str = ""
    is_abstract: bool = False
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    http_method: str = ""
    route_path: str = ""
    return_type: str = ""
    parameters: list[dict] = field(default_factory=list)
    exported: bool = True


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str               # injects | imports | implements | extends
                            # has_route | uses | registers | declares
    label: str = ""


@dataclass
class GraphStats:
    total_files: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    controllers: int = 0
    services: int = 0
    repositories: int = 0
    middleware: int = 0
    models: int = 0
    interfaces: int = 0
    utils: int = 0
    configs: int = 0
    guards: int = 0


# ─────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────

# JSDoc block before a declaration
RE_JSDOC = re.compile(r'/\*\*(.*?)\*/', re.DOTALL)
RE_JSDOC_CLEAN = re.compile(r'^\s*\*\s?', re.MULTILINE)

# NestJS / TypeScript decorators
RE_DECORATOR = re.compile(
    r'@(Controller|Injectable|Module|Guard|Interceptor|Pipe|Resolver|Gateway'
    r'|Get|Post|Put|Patch|Delete|Options|Head|All'
    r'|UseGuards|UseInterceptors|UsePipes'
    r'|Entity|Column|PrimaryGeneratedColumn|OneToMany|ManyToOne'
    r'|InjectRepository|Inject'
    r'|MessagePattern|EventPattern|GrpcMethod)'
    r'(?:\s*\([^)]*\))?',
    re.MULTILINE
)

# Class declaration
RE_CLASS = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'(?P<decs>(?:@[\w]+(?:\s*\([^)]*\))?\s*\n?\s*)*)'
    r'\s*export\s+(?P<abstract>abstract\s+)?(?:default\s+)?class\s+(?P<name>\w+)'
    r'(?:<[^>]+>)?'
    r'(?:\s+extends\s+(?P<extends>[\w<>, .]+?))?'
    r'(?:\s+implements\s+(?P<implements>[\w<>, .]+?))?'
    r'\s*\{',
    re.DOTALL | re.MULTILINE
)

# Interface declaration
RE_INTERFACE = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'export\s+interface\s+(?P<name>\w+)'
    r'(?:<[^>]+>)?'
    r'(?:\s+extends\s+(?P<extends>[\w<>, .]+?))?'
    r'\s*\{',
    re.DOTALL | re.MULTILINE
)

# Type alias
RE_TYPE = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'export\s+type\s+(?P<name>\w+)\s*(?:<[^>]+>)?\s*=',
    re.MULTILINE | re.DOTALL
)

# Enum
RE_ENUM = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'export\s+enum\s+(?P<name>\w+)\s*\{',
    re.MULTILINE | re.DOTALL
)

# Export function / const arrow function
RE_EXPORT_FUNC = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'export\s+(?:async\s+)?function\s+(?P<name>\w+)\s*\(',
    re.MULTILINE | re.DOTALL
)

RE_EXPORT_ARROW = re.compile(
    r'(?P<jsdoc>/\*\*.*?\*/\s*)?'
    r'export\s+(?:const|let)\s+(?P<name>\w+)\s*[=:][^=\n]*(?:async\s*)?\(',
    re.MULTILINE | re.DOTALL
)

# Constructor block
RE_CTOR = re.compile(
    r'constructor\s*\((?P<params>[^)]*)\)',
    re.MULTILINE | re.DOTALL
)

# Constructor param with access modifier (indicates injection)
RE_CTOR_PARAM = re.compile(
    r'(?:private|public|protected|readonly)(?:\s+readonly)?\s+'
    r'(?P<name>\w+)\s*:\s*(?P<type>[\w<>[\]|& ,]+)',
)

# Express router patterns
RE_ROUTER_METHOD = re.compile(
    r'(?:router|app)\s*\.\s*(?P<method>get|post|put|patch|delete|all|use)'
    r'\s*\(\s*[\'"](?P<path>[^\'"]*)[\'"]',
    re.MULTILINE | re.IGNORECASE
)

# Import statement — captures path and named imports
RE_IMPORT = re.compile(
    r"import\s+(?:type\s+)?(?P<clause>[^'\"]+?)\s+from\s+['\"](?P<path>[^'\"]+)['\"]",
    re.MULTILINE
)

# require() patterns
RE_REQUIRE = re.compile(
    r"(?:const|let|var)\s+\{?(?P<names>[^}=]+)\}?\s*=\s*require\(['\"](?P<path>[^'\"]+)['\"]\)",
    re.MULTILINE
)

# Prisma model (schema.prisma — optional)
RE_PRISMA_MODEL = re.compile(r'^model\s+(\w+)\s*\{', re.MULTILINE)

# TypeORM @Entity
RE_TYPEORM_ENTITY = re.compile(r'@Entity\s*\(', re.MULTILINE)

# NestJS @Module providers/controllers arrays
RE_MODULE_PROVIDERS = re.compile(
    r'providers\s*:\s*\[([^\]]+)\]', re.MULTILINE | re.DOTALL
)
RE_MODULE_CONTROLLERS = re.compile(
    r'controllers\s*:\s*\[([^\]]+)\]', re.MULTILINE | re.DOTALL
)


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
    result = " ".join(cleaned.split()).strip()
    # Return only first sentence
    return result.split(". ")[0].rstrip(".")


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


def get_decorators(raw: str) -> list[str]:
    return [m.group(1) for m in RE_DECORATOR.finditer(raw or "")]


def file_to_module(filepath: Path, root: Path) -> str:
    rel = filepath.relative_to(root)
    parts = list(rel.parts)
    parts[-1] = re.sub(r'\.(ts|js|tsx|jsx)$', '', parts[-1])
    # Remove index
    if parts[-1] == "index": parts = parts[:-1]
    return ".".join(parts) if parts else "root"


def build_import_index(text: str) -> dict[str, str]:
    """Map exported name → source path from all import statements."""
    index: dict[str, str] = {}
    for m in RE_IMPORT.finditer(text):
        path = m.group("path")
        clause = m.group("clause")
        # Named imports { Foo, Bar }
        named = re.findall(r'\b(\w+)\b', re.sub(r'^\s*\*\s+as\s+\w+', '', clause))
        for name in named:
            if name not in ("type", "as", "from"):
                index[name] = path
    for m in RE_REQUIRE.finditer(text):
        path = m.group("path")
        for name in re.findall(r'\b(\w+)\b', m.group("names")):
            index[name] = path
    return index


def resolve(short: str, import_index: dict[str, str], module: str) -> str:
    """Resolve a short class name to its qualified module id."""
    short_clean = short.split("<")[0].strip()
    if short_clean in import_index:
        path = import_index[short_clean]
        if path.startswith("."):
            # Relative → resolve against current module
            base = module.split(".")[:-1]
            for seg in path.replace(".ts","").split("/"):
                if seg == "..": base = base[:-1]
                elif seg and seg != ".": base.append(seg)
            return ".".join(base) + "." + short_clean
        else:
            # External package — use short name as-is
            return short_clean
    return f"{module}.{short_clean}"


# ─────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────

# NestJS decorator → kind (priority ordered)
NESTJS_DEC_KIND = [
    ({"Controller"},                   "controller"),
    ({"Injectable"},                   "service"),
    ({"Module"},                       "module"),
    ({"Guard"},                        "guard"),
    ({"Interceptor"},                  "interceptor"),
    ({"Pipe"},                         "pipe"),
    ({"Resolver"},                     "resolver"),
    ({"Gateway"},                      "gateway"),
    ({"Entity"},                       "entity"),
]

HTTP_VERBS = {"Get","Post","Put","Patch","Delete","Options","Head","All"}

def classify_kind(
    name: str,
    decorators: list[str],
    implements_list: list[str],
    extends_list: list[str],
    is_interface: bool,
    is_abstract: bool,
    file_path: str,
    is_func: bool = False,
) -> str:
    if is_interface:
        n = name.lower()
        if n.endswith("repository"):  return "repository_interface"
        if n.endswith("service"):     return "service_interface"
        if n.endswith("config"):      return "config"
        return "interface"

    dec_set = set(decorators)

    # NestJS decorator wins first
    for dec_group, kind in NESTJS_DEC_KIND:
        if dec_set & dec_group:
            return kind

    # Has HTTP verb decorators → NestJS controller method (handled inline)
    # Implements-based
    for iface in implements_list:
        i = iface.split("<")[0]
        if i in ("CanActivate","CanDeactivate","CanLoad","CanActivateChild"): return "guard"
        if i in ("NestInterceptor","HttpInterceptor"): return "interceptor"
        if i in ("PipeTransform"):  return "pipe"
        if i in ("ExceptionFilter"): return "exception_filter"

    n = name.lower()
    fp = file_path.lower()

    # Naming convention
    if n.endswith("controller"):        return "controller"
    if n.endswith("service"):           return "service"
    if n.endswith("repository") or n.endswith("repo"): return "repository"
    if n.endswith("middleware"):        return "middleware"
    if n.endswith("guard"):             return "guard"
    if n.endswith("interceptor"):       return "interceptor"
    if n.endswith("module"):            return "module"
    if n.endswith("resolver"):          return "resolver"
    if n.endswith("gateway"):           return "gateway"
    if n.endswith("factory"):           return "factory"
    if n.endswith("helper") or n.endswith("util") or n.endswith("utils"): return "util"
    if n.endswith("config"):            return "config"
    if n.endswith("logger"):            return "util"
    if n.endswith("client"):            return "util"
    if n.endswith("provider"):          return "service"
    if n.endswith("handler"):           return "handler"
    if n.endswith("adapter"):           return "adapter"
    if n.endswith("dto") or n.endswith("model"): return "model"

    # File path hints
    if "middleware" in fp:  return "middleware"
    if "guard" in fp:       return "guard"
    if "interceptor" in fp: return "interceptor"
    if "util" in fp or "helper" in fp: return "util"
    if "config" in fp:      return "config"
    if "model" in fp:       return "model"
    if "type" in fp:        return "type"

    if is_func:             return "function"
    if is_abstract:         return "abstract"
    return "class"


def build_tags(kind: str, name: str, decorators: list[str], file_path: str, is_async: bool) -> list[str]:
    tags = [kind]
    n = name.lower(); fp = file_path.lower()
    if is_async: tags.append("async")
    if "auth"    in n or "auth"    in fp: tags.append("auth")
    if "user"    in n or "user"    in fp: tags.append("user")
    if "order"   in n or "order"   in fp: tags.append("orders")
    if "payment" in n or "payment" in fp: tags.append("payments")
    if "email"   in n or "email"   in fp: tags.append("email")
    if "redis"   in n or "redis"   in fp: tags.append("cache")
    if "jwt"     in n or "jwt"     in fp: tags.append("jwt")
    if "log"     in n or "log"     in fp: tags.append("logging")
    if "notif"   in n or "notif"   in fp: tags.append("notifications")
    if kind in ("controller","resolver","gateway"): tags.append("api")
    if kind in ("repository","entity"):  tags.append("data-access")
    if kind == "middleware": tags.append("pipeline")
    if kind in ("guard","interceptor"):  tags.append("security")
    # Path segments as tags
    parts = fp.replace("\\","/").split("/")
    for p in parts[:-1]:
        if p not in ("src","dist","node_modules","app","main","lib"):
            tags.append(p)
    return list(dict.fromkeys(tags))


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
    import_index = build_import_index(text)

    # ── Classes ──
    for m in RE_CLASS.finditer(text):
        raw_decs = m.group("decs") or ""
        decorators = get_decorators(raw_decs)
        name = m.group("name")
        is_abstract = bool(m.group("abstract"))
        extends_list = parse_type_list(m.group("extends"))
        implements_list = parse_type_list(m.group("implements"))

        kind = classify_kind(name, decorators, implements_list, extends_list,
                             False, is_abstract, rel_path)
        node_id = f"{module}.{name}"
        summary = extract_jsdoc(text, m.start())
        start_line = line_number(text, m.start())
        end_line = count_block_end(text, m.start())

        node = GraphNode(
            id=node_id, kind=kind, name=name,
            location=NodeLocation(file=rel_path, lines=[start_line, end_line], module=module),
            summary=summary, is_abstract=is_abstract,
            decorators=decorators,
            implements=implements_list, extends=extends_list,
            tags=build_tags(kind, name, decorators, rel_path, False),
        )
        nodes.append(node)

        # Inheritance edges
        for base in extends_list:
            target = resolve(base, import_index, module)
            edges.append(GraphEdge(source=node_id, target=target, kind="extends"))
        for iface in implements_list:
            target = resolve(iface, import_index, module)
            edges.append(GraphEdge(source=node_id, target=target, kind="implements"))

        # ── Constructor injection ──
        body_start = text.find("{", m.start())
        body = text[body_start: body_start + 8000] if body_start != -1 else ""
        ctor_m = RE_CTOR.search(body)
        if ctor_m:
            for pm in RE_CTOR_PARAM.finditer(ctor_m.group("params")):
                ptype = pm.group("type").split("<")[0].strip()
                # Skip primitives and common non-injectable types
                if ptype in ("string","number","boolean","any","void","never",
                             "object","unknown","null","undefined",
                             "Record","Array","Promise","Observable"):
                    continue
                target = resolve(ptype, import_index, module)
                edges.append(GraphEdge(
                    source=node_id, target=target,
                    kind="injects", label=pm.group("name")
                ))

        # ── NestJS HTTP method decorators on class methods ──
        if kind in ("controller", "resolver", "gateway"):
            for mm in re.finditer(
                r'(?P<decs>(?:@[\w]+(?:\([^)]*\))?\s*\n?\s*)*)'
                r'\s*(?:async\s+)?(?P<name>\w+)\s*\([^)]*\)',
                body
            ):
                m_decs = get_decorators(mm.group("decs"))
                verb_decs = [d for d in m_decs if d in HTTP_VERBS]
                if not verb_decs:
                    continue
                m_name = mm.group("name")
                if m_name in ("constructor",):
                    continue
                m_id = f"{node_id}.{m_name}"
                m_sum = extract_jsdoc(body, mm.start())
                m_start = start_line + line_number(body, mm.start()) - 1
                # Extract route path from decorator arg
                route_match = re.search(
                    r'@(?:' + '|'.join(HTTP_VERBS) + r')\s*\(\s*[\'"]([^\'"]*)[\'"]',
                    mm.group("decs")
                )
                route_path = route_match.group(1) if route_match else ""
                mnode = GraphNode(
                    id=m_id, kind="route", name=m_name,
                    location=NodeLocation(file=rel_path, lines=[m_start, m_start+8], module=module),
                    summary=m_sum, is_async=True,
                    decorators=m_decs,
                    http_method=verb_decs[0].upper(),
                    route_path=route_path,
                    tags=build_tags("route", m_name, m_decs, rel_path, True),
                )
                nodes.append(mnode)
                edges.append(GraphEdge(source=node_id, target=m_id, kind="has_route",
                                       label=verb_decs[0]))

        # ── Express router patterns inside class body ──
        for rm in RE_ROUTER_METHOD.finditer(body):
            verb = rm.group("method").upper()
            path = rm.group("path")
            r_id = f"{node_id}.{verb.lower()}_{path.replace('/','_').strip('_') or 'root'}"
            if not any(n.id == r_id for n in nodes):
                rnode = GraphNode(
                    id=r_id, kind="route", name=f"{verb} {path}",
                    location=NodeLocation(file=rel_path,
                        lines=[start_line + line_number(body, rm.start()) - 1,
                               start_line + line_number(body, rm.start())],
                        module=module),
                    http_method=verb, route_path=path,
                    tags=build_tags("route", path, [], rel_path, False),
                )
                nodes.append(rnode)
                edges.append(GraphEdge(source=node_id, target=r_id, kind="has_route", label=verb))

    # ── Interfaces ──
    for m in RE_INTERFACE.finditer(text):
        name = m.group("name")
        extends_list = parse_type_list(m.group("extends"))
        kind = classify_kind(name, [], [], extends_list, True, False, rel_path)
        node_id = f"{module}.{name}"
        summary = extract_jsdoc(text, m.start())
        start_line = line_number(text, m.start())
        end_line = count_block_end(text, m.start())
        nodes.append(GraphNode(
            id=node_id, kind=kind, name=name,
            location=NodeLocation(file=rel_path, lines=[start_line, end_line], module=module),
            summary=summary, extends=extends_list,
            tags=build_tags(kind, name, [], rel_path, False),
        ))
        for base in extends_list:
            target = resolve(base, import_index, module)
            edges.append(GraphEdge(source=node_id, target=target, kind="extends"))

    # ── Type aliases ──
    for m in RE_TYPE.finditer(text):
        name = m.group("name")
        node_id = f"{module}.{name}"
        summary = extract_jsdoc(text, m.start())
        nodes.append(GraphNode(
            id=node_id, kind="type", name=name,
            location=NodeLocation(file=rel_path,
                lines=[line_number(text, m.start()), line_number(text, m.start())],
                module=module),
            summary=summary,
            tags=build_tags("type", name, [], rel_path, False),
        ))

    # ── Enums ──
    for m in RE_ENUM.finditer(text):
        name = m.group("name")
        node_id = f"{module}.{name}"
        summary = extract_jsdoc(text, m.start())
        nodes.append(GraphNode(
            id=node_id, kind="enum", name=name,
            location=NodeLocation(file=rel_path,
                lines=[line_number(text, m.start()), line_number(text, m.start())+5],
                module=module),
            summary=summary,
            tags=build_tags("enum", name, [], rel_path, False),
        ))

    # ── Exported functions (middleware factories, config loaders, utils) ──
    for m in list(RE_EXPORT_FUNC.finditer(text)) + list(RE_EXPORT_ARROW.finditer(text)):
        name = m.group("name")
        if not name or name[0].isupper():
            continue  # skip class-like names (handled above)
        node_id = f"{module}.{name}"
        if any(n.id == node_id for n in nodes):
            continue
        summary = extract_jsdoc(text, m.start())
        is_async = "async" in text[max(0, m.start()-5): m.start()+50]
        kind = classify_kind(name, [], [], [], False, False, rel_path, is_func=True)
        nodes.append(GraphNode(
            id=node_id, kind=kind, name=name,
            location=NodeLocation(file=rel_path,
                lines=[line_number(text, m.start()), line_number(text, m.start())+10],
                module=module),
            summary=summary, is_async=is_async, exported=True,
            tags=build_tags(kind, name, [], rel_path, is_async),
        ))

    # ── Top-level Express router patterns (outside classes) ──
    for rm in RE_ROUTER_METHOD.finditer(text):
        verb = rm.group("method").upper()
        path = rm.group("path")
        r_id = f"{module}.route_{verb.lower()}_{path.replace('/','_').lstrip('_') or 'root'}"
        if any(n.id == r_id for n in nodes):
            continue
        rnode = GraphNode(
            id=r_id, kind="route", name=f"{verb} {path}",
            location=NodeLocation(file=rel_path,
                lines=[line_number(text, rm.start()), line_number(text, rm.start())],
                module=module),
            http_method=verb, route_path=path,
            tags=build_tags("route", path, [], rel_path, False),
        )
        nodes.append(rnode)
        edges.append(GraphEdge(source=module, target=r_id, kind="has_route", label=verb))

    # ── Import edges (local files only) ──
    for m in RE_IMPORT.finditer(text):
        path = m.group("path")
        if not path.startswith("."): continue
        base = module.split(".")[:-1]
        for seg in path.replace(".ts","").split("/"):
            if seg == "..": base = base[:-1]
            elif seg and seg != ".": base.append(seg)
        target_module = ".".join(base)
        if target_module and target_module != module:
            edges.append(GraphEdge(source=module, target=target_module, kind="imports"))

    return nodes, edges


# ─────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────

DEFAULT_EXCLUDES = [
    "**/*.spec.ts", "**/*.test.ts", "**/*.e2e.ts",
    "**/node_modules/**", "**/dist/**", "**/build/**",
    "**/*.d.ts", "**/coverage/**",
    "**/__tests__/**", "**/__mocks__/**",
    "**/jest.config*", "**/webpack.config*",
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

    # Also scan .prisma files for model names
    for pf in root.rglob("*.prisma"):
        try:
            prisma_text = pf.read_text(encoding="utf-8", errors="replace")
            rel = str(pf.relative_to(root)).replace("\\", "/")
            for mm in RE_PRISMA_MODEL.finditer(prisma_text):
                name = mm.group(1)
                node_id = f"prisma.{name}"
                all_nodes.append(GraphNode(
                    id=node_id, kind="model", name=name,
                    location=NodeLocation(file=rel, lines=[line_number(prisma_text, mm.start()), line_number(prisma_text, mm.start())+5], module="prisma"),
                    summary=f"Prisma model for {name} table",
                    tags=["model","database","prisma"],
                ))
        except Exception:
            pass

    # Deduplicate nodes
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

    # Deduplicate edges
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
        controllers=sum(1 for n in final_nodes if n.kind == "controller"),
        services=sum(1 for n in final_nodes if n.kind in ("service","service_interface")),
        repositories=sum(1 for n in final_nodes if "repository" in n.kind),
        middleware=sum(1 for n in final_nodes if n.kind == "middleware"),
        models=sum(1 for n in final_nodes if n.kind in ("model","entity","type","enum")),
        interfaces=sum(1 for n in final_nodes if "interface" in n.kind),
        utils=sum(1 for n in final_nodes if n.kind in ("util","function")),
        configs=sum(1 for n in final_nodes if n.kind == "config"),
        guards=sum(1 for n in final_nodes if n.kind in ("guard","interceptor")),
    )

    content = json.dumps(
        [asdict(n) for n in sorted(final_nodes, key=lambda x: x.id)], sort_keys=True
    )
    graph_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    return {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "gen_graph_typescript.py",
        "language": "typescript",
        "framework": "node/express/nestjs",
        "hash": graph_hash,
        "stats": asdict(stats),
        "nodes": [_node_to_dict(n) for n in sorted(final_nodes, key=lambda x: x.id)],
        "edges": [
            {"source": e.source, "target": e.target, "kind": e.kind,
             **({"label": e.label} if e.label else {})}
            for e in final_edges
        ],
    }


def _node_to_dict(n: GraphNode) -> dict:
    d = {
        "id": n.id, "kind": n.kind, "name": n.name,
        "file": n.location.file, "lines": n.location.lines,
        "module": n.location.module, "summary": n.summary, "tags": n.tags,
    }
    if n.is_abstract:    d["is_abstract"] = True
    if n.is_async:       d["is_async"] = True
    if n.decorators:     d["decorators"] = n.decorators
    if n.implements:     d["implements"] = n.implements
    if n.extends:        d["extends"] = n.extends
    if n.http_method:    d["http_method"] = n.http_method
    if n.route_path:     d["route_path"] = n.route_path
    if n.return_type:    d["return_type"] = n.return_type
    if n.parameters:     d["parameters"] = n.parameters
    return d


# ─────────────────────────────────────────────
# CLI + reporting
# ─────────────────────────────────────────────

COLORS = {
    "green":"\033[92m","yellow":"\033[93m","cyan":"\033[96m",
    "gray":"\033[90m","reset":"\033[0m","bold":"\033[1m",
}

def c(text: str, color: str) -> str:
    return f"{COLORS.get(color,'')}{text}{COLORS['reset']}" if sys.stdout.isatty() else text


def print_summary(graph: dict) -> None:
    s = graph["stats"]
    print()
    print(c("  CodeGraph — TypeScript / Node.js Codebase Map", "bold"))
    print(c(f"  Generated : {graph['generated'][:19].replace('T',' ')} UTC", "gray"))
    print(c(f"  Hash      : {graph['hash']}", "gray"))
    print()
    print(c(f"  {'Files scanned:':<24} {s['total_files']}", "cyan"))
    print(c(f"  {'Nodes extracted:':<24} {s['total_nodes']}", "cyan"))
    print(c(f"  {'Edges mapped:':<24} {s['total_edges']}", "cyan"))
    print()
    for label, key in [
        ("Controllers","controllers"), ("Services","services"),
        ("Repositories","repositories"), ("Middleware","middleware"),
        ("Models/Types/Enums","models"), ("Interfaces","interfaces"),
        ("Utils/Functions","utils"), ("Config","configs"),
        ("Guards/Interceptors","guards"),
    ]:
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
    parser = argparse.ArgumentParser(
        description="Generate codebase memory graph for TypeScript / Node.js projects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--root", "-r", default=".", help="Root directory to scan (default: .)")
    parser.add_argument("--output", "-o", default="codebase-graph.json")
    parser.add_argument("--exclude", "-e", action="append", default=[], metavar="PATTERN")
    parser.add_argument("--summary", action="store_true", help="Stats only, don't write file")
    parser.add_argument("--tree", action="store_true", help="Print node tree")
    parser.add_argument("--watch", "-w", action="store_true", help="Watch mode")
    parser.add_argument("--minify", action="store_true", help="Minify JSON output")
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