#!/usr/bin/env python3
"""
gen_graph_python.py — Codebase Memory Graph Generator for Python
=================================================================
Supports: FastAPI · Django · Flask · SQLAlchemy · Pydantic · Celery

Parses Python source files and extracts:
  Classes (services, repositories, models, middleware)
  Functions / route handlers (FastAPI/Flask/Django views)
  Dependencies via __init__ parameters and imports
  Pydantic BaseModel subclasses (schemas/DTOs)
  FastAPI router decorators (@router.get, @router.post, etc.)
  Django class-based views and DRF ViewSets
  Celery tasks (@app.task, @shared_task)
  Docstrings → node summaries

Usage:
    python gen_graph_python.py                        # current directory
    python gen_graph_python.py --root ./app           # specific folder
    python gen_graph_python.py --output graph.json    # custom output
    python gen_graph_python.py --exclude "**/tests/**"
    python gen_graph_python.py --tree                 # print node tree
    python gen_graph_python.py --watch                # watch mode

Requirements: Python 3.9+  (no third-party packages)
"""

from __future__ import annotations

import argparse
import ast
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
    module: str = ""          # dotted module path e.g. app.services.auth_service


@dataclass
class GraphNode:
    id: str
    kind: str                 # router | service | repository | model | middleware
                              # dependency | task | viewset | view | class | function
    name: str
    location: NodeLocation
    summary: str = ""
    visibility: str = "public"
    is_async: bool = False
    is_abstract: bool = False
    decorators: list[str] = field(default_factory=list)
    base_classes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    http_method: str = ""     # GET POST PUT PATCH DELETE
    route_path: str = ""
    parameters: list[dict] = field(default_factory=list)
    return_type: str = ""


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str                 # imports | instantiates | depends_on | inherits
                              # has_route | calls | registers
    label: str = ""


@dataclass
class GraphStats:
    total_files: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    routers: int = 0
    services: int = 0
    repositories: int = 0
    models: int = 0
    middleware: int = 0
    tasks: int = 0
    dependencies: int = 0
    views: int = 0


# ─────────────────────────────────────────────
# Classification helpers
# ─────────────────────────────────────────────

# Decorator name → kind
DECORATOR_KIND = {
    "router.get": "route",        "router.post": "route",
    "router.put": "route",        "router.patch": "route",
    "router.delete": "route",     "app.get": "route",
    "app.post": "route",          "app.put": "route",
    "app.route": "route",         "app.task": "task",
    "shared_task": "task",        "celery.task": "task",
    "pytest.fixture": "fixture",  "property": "property",
    "staticmethod": "staticmethod",
    "classmethod": "classmethod",
}

HTTP_VERB_MAP = {
    "get": "GET", "post": "POST", "put": "PUT",
    "patch": "PATCH", "delete": "DELETE",
}

# Base class name → node kind
BASE_CLASS_KIND = {
    "BaseModel": "model",          "BaseSettings": "config",
    "BaseHTTPMiddleware": "middleware",
    "APIRouter": "router",
    "APIView": "view",             "GenericAPIView": "view",
    "ModelViewSet": "viewset",     "ReadOnlyModelViewSet": "viewset",
    "ViewSet": "viewset",          "CreateAPIView": "view",
    "ListAPIView": "view",         "RetrieveAPIView": "view",
    "View": "view",                "TemplateView": "view",
    "ListView": "view",            "DetailView": "view",
    "CreateView": "view",          "UpdateView": "view",
    "DeleteView": "view",          "FormView": "view",
    "AsyncSession": "repository",  "Session": "repository",
    "Exception": "exception",      "ValueError": "exception",
    "Enum": "enum",
}

def classify_kind(
    name: str,
    decorators: list[str],
    base_classes: list[str],
    is_func: bool,
) -> str:
    # Route handlers by decorator
    for d in decorators:
        for pat, kind in DECORATOR_KIND.items():
            if d.startswith(pat):
                return kind

    # Class: check base classes first
    if not is_func:
        for base in base_classes:
            for bname, kind in BASE_CLASS_KIND.items():
                if base == bname or base.endswith("." + bname):
                    return kind
        # Naming convention
        n = name.lower()
        if n.endswith("service"):        return "service"
        if n.endswith("repository") or n.endswith("repo"): return "repository"
        if n.endswith("middleware"):      return "middleware"
        if n.endswith("router"):          return "router"
        if n.endswith("view") or n.endswith("viewset"): return "view"
        if n.endswith("schema") or n.endswith("model") or n.endswith("dto"): return "model"
        if n.endswith("task"):            return "task"
        if n.endswith("factory"):         return "factory"
        if n.endswith("manager"):         return "manager"
        return "class"

    # Function/coroutine naming convention
    n = name.lower()
    if any(n.startswith(p) for p in ("get_", "find_", "fetch_")): return "query"
    if any(n.startswith(p) for p in ("create_", "insert_", "save_")): return "command"
    if n.startswith("get_current") or "dependency" in n: return "dependency"
    return "function"


def build_tags(kind: str, name: str, decorators: list[str], module: str, is_async: bool) -> list[str]:
    tags = [kind]
    if is_async: tags.append("async")
    for d in decorators:
        if any(v in d for v in ("get", "post", "put", "patch", "delete")):
            tags.append("api-endpoint")
    if "auth" in name.lower() or "auth" in module: tags.append("auth")
    if "order" in name.lower() or "order" in module: tags.append("orders")
    if "payment" in name.lower() or "payment" in module: tags.append("payments")
    if "user" in name.lower() or "user" in module: tags.append("user")
    # Add module path segments
    for seg in module.split("."):
        if seg not in ("app", "src", "main", "core", "__init__"):
            tags.append(seg)
    return list(dict.fromkeys(tags))


# ─────────────────────────────────────────────
# Module path helper
# ─────────────────────────────────────────────

def file_to_module(filepath: Path, root: Path) -> str:
    rel = filepath.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].replace(".py", "")
    return ".".join(parts)


# ─────────────────────────────────────────────
# AST-based parser — the real engine
# ─────────────────────────────────────────────

def get_docstring(node: ast.AST) -> str:
    """Extract first docstring from a class or function body."""
    if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        return node.body[0].value.value.strip().split("\n")[0]
    return ""


def get_decorator_names(decorator_list: list[ast.expr]) -> list[str]:
    """Convert decorator AST nodes to dotted string names."""
    names = []
    for d in decorator_list:
        if isinstance(d, ast.Name):
            names.append(d.id)
        elif isinstance(d, ast.Attribute):
            names.append(f"{_attr_to_str(d)}")
        elif isinstance(d, ast.Call):
            if isinstance(d.func, ast.Name):
                names.append(d.func.id)
            elif isinstance(d.func, ast.Attribute):
                names.append(_attr_to_str(d.func))
    return names


def _attr_to_str(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_attr_to_str(node.value)}.{node.attr}"
    return "?"


def get_base_names(bases: list[ast.expr]) -> list[str]:
    return [_attr_to_str(b) for b in bases if isinstance(b, (ast.Name, ast.Attribute))]


def get_init_deps(classnode: ast.ClassDef) -> list[dict]:
    """Find __init__ or __init__ equivalent and extract typed parameters as deps."""
    for node in ast.walk(classnode):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
            params = []
            for arg in node.args.args:
                if arg.arg == "self":
                    continue
                ann = ""
                if arg.annotation:
                    ann = _attr_to_str(arg.annotation) if isinstance(arg.annotation, (ast.Name, ast.Attribute)) else ""
                params.append({"name": arg.arg, "type": ann})
            return params
    return []


def get_http_info(decorators: list[str]) -> tuple[str, str]:
    """Extract HTTP method and route path from decorator list."""
    for d in decorators:
        for verb in ("get", "post", "put", "patch", "delete"):
            if f".{verb}" in d or d == verb:
                return verb.upper(), ""
    return "", ""


def get_annotations(funcnode) -> tuple[list[dict], str]:
    """Extract function parameter types and return type annotation."""
    params = []
    for arg in funcnode.args.args:
        if arg.arg in ("self", "cls"):
            continue
        ann = ""
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                ann = arg.annotation.id
            elif isinstance(arg.annotation, ast.Attribute):
                ann = _attr_to_str(arg.annotation)
            elif isinstance(arg.annotation, ast.Subscript):
                ann = _attr_to_str(arg.annotation.value) if isinstance(arg.annotation.value, (ast.Name, ast.Attribute)) else ""
        params.append({"name": arg.arg, "type": ann})

    ret = ""
    if funcnode.returns:
        if isinstance(funcnode.returns, ast.Name):
            ret = funcnode.returns.id
        elif isinstance(funcnode.returns, ast.Attribute):
            ret = _attr_to_str(funcnode.returns)
        elif isinstance(funcnode.returns, ast.Subscript):
            ret = _attr_to_str(funcnode.returns.value) if isinstance(funcnode.returns.value, (ast.Name, ast.Attribute)) else ""

    return params, ret


def parse_imports(tree: ast.Module) -> list[tuple[str, str]]:
    """Return list of (module, name) import pairs."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, alias.asname or alias.name.split(".")[-1]))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append((f"{mod}.{alias.name}", alias.asname or alias.name))
    return imports


# ─────────────────────────────────────────────
# File parser
# ─────────────────────────────────────────────

def parse_python_file(filepath: Path, root: Path) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return nodes, edges

    rel_path = str(filepath.relative_to(root)).replace("\\", "/")
    module = file_to_module(filepath, root)
    imports = parse_imports(tree)

    # Build a short-name → module index from imports
    import_index: dict[str, str] = {name: mod for mod, name in imports}

    # ── Top-level classes ──
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        decorators = get_decorator_names(node.decorator_list)
        base_classes = get_base_names(node.bases)
        kind = classify_kind(node.name, decorators, base_classes, is_func=False)
        node_id = f"{module}.{node.name}"
        summary = get_docstring(node)
        is_abstract = any("ABC" in b or "abstract" in b.lower() for b in base_classes)

        gnode = GraphNode(
            id=node_id,
            kind=kind,
            name=node.name,
            location=NodeLocation(file=rel_path, lines=[node.lineno, node.end_lineno or node.lineno], module=module),
            summary=summary,
            is_abstract=is_abstract,
            decorators=decorators,
            base_classes=base_classes,
            tags=build_tags(kind, node.name, decorators, module, False),
        )
        nodes.append(gnode)

        # Inheritance edges
        for base in base_classes:
            target = import_index.get(base, base)
            edges.append(GraphEdge(source=node_id, target=target, kind="inherits"))

        # Constructor dependency edges (__init__ typed params)
        for dep in get_init_deps(node):
            if not dep["type"] or dep["type"] in ("str", "int", "bool", "dict", "list", "None"):
                continue
            target = import_index.get(dep["type"], f"{module}.{dep['type']}")
            edges.append(GraphEdge(source=node_id, target=target, kind="depends_on", label=dep["name"]))

        # ── Methods inside the class ──
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if child.name.startswith("_") and child.name != "__init__":
                continue

            m_decorators = get_decorator_names(child.decorator_list)
            m_kind = classify_kind(child.name, m_decorators, [], is_func=True)
            http_method, route_path = get_http_info(m_decorators)
            params, ret = get_annotations(child)
            m_id = f"{node_id}.{child.name}"
            m_summary = get_docstring(child)

            mnode = GraphNode(
                id=m_id,
                kind=m_kind,
                name=child.name,
                location=NodeLocation(file=rel_path, lines=[child.lineno, child.end_lineno or child.lineno], module=module),
                summary=m_summary,
                is_async=isinstance(child, ast.AsyncFunctionDef),
                decorators=m_decorators,
                http_method=http_method,
                route_path=route_path,
                parameters=params,
                return_type=ret,
                tags=build_tags(m_kind, child.name, m_decorators, module, isinstance(child, ast.AsyncFunctionDef)),
            )
            nodes.append(mnode)
            edges.append(GraphEdge(source=node_id, target=m_id, kind="has_method"))

    # ── Top-level functions (route handlers, dependencies, tasks) ──
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decorators = get_decorator_names(node.decorator_list)
        # Only index decorated functions at top level (routes, tasks, deps)
        if not decorators:
            continue

        kind = classify_kind(node.name, decorators, [], is_func=True)
        if kind == "function":
            continue  # skip plain undecorated

        node_id = f"{module}.{node.name}"
        summary = get_docstring(node)
        http_method, route_path = get_http_info(decorators)
        params, ret = get_annotations(node)

        gnode = GraphNode(
            id=node_id,
            kind=kind,
            name=node.name,
            location=NodeLocation(file=rel_path, lines=[node.lineno, node.end_lineno or node.lineno], module=module),
            summary=summary,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            decorators=decorators,
            http_method=http_method,
            route_path=route_path,
            parameters=params,
            return_type=ret,
            tags=build_tags(kind, node.name, decorators, module, isinstance(node, ast.AsyncFunctionDef)),
        )
        nodes.append(gnode)

        # FastAPI Depends() edges
        for arg in node.args.args:
            if arg.annotation and isinstance(arg.annotation, ast.Subscript):
                # Depends(SomeService) pattern
                pass

    # ── Import edges (cross-module) ──
    for mod, name in imports:
        if not mod or mod.startswith("fastapi") or mod.startswith("starlette") \
                or mod.startswith("django") or mod.startswith("flask") \
                or mod.startswith("pydantic") or mod.startswith("sqlalchemy"):
            continue
        # Only emit edges for imports that match known local modules
        target_id = mod if mod else name
        edges.append(GraphEdge(source=module, target=target_id, kind="imports"))

    return nodes, edges


# ─────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────

DEFAULT_EXCLUDES = [
    "**/tests/**", "**/test_*.py", "**/*_test.py",
    "**/__pycache__/**", "**/*.pyc",
    "**/migrations/**", "**/alembic/**",
    "**/venv/**", "**/.venv/**", "**/env/**",
    "**/node_modules/**", "**/.git/**",
    "**/conftest.py", "**/setup.py", "**/setup.cfg",
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

    py_files = sorted(root.rglob("*.py"))
    processed = 0

    for pf in py_files:
        if should_exclude(pf, root, excludes):
            continue
        n, e = parse_python_file(pf, root)
        all_nodes.extend(n)
        all_edges.extend(e)
        processed += 1

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
    known_ids = {n.id for n in final_nodes}

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
        routers=sum(1 for n in final_nodes if n.kind == "router"),
        services=sum(1 for n in final_nodes if n.kind == "service"),
        repositories=sum(1 for n in final_nodes if n.kind == "repository"),
        models=sum(1 for n in final_nodes if n.kind == "model"),
        middleware=sum(1 for n in final_nodes if n.kind == "middleware"),
        tasks=sum(1 for n in final_nodes if n.kind == "task"),
        dependencies=sum(1 for n in final_nodes if n.kind == "dependency"),
        views=sum(1 for n in final_nodes if n.kind in ("view", "viewset")),
    )

    content = json.dumps([asdict(n) for n in sorted(final_nodes, key=lambda x: x.id)], sort_keys=True)
    graph_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    return {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "gen_graph_python.py",
        "language": "python",
        "hash": graph_hash,
        "stats": asdict(stats),
        "nodes": [_node_to_dict(n) for n in sorted(final_nodes, key=lambda x: x.id)],
        "edges": [{"source": e.source, "target": e.target, "kind": e.kind, **({"label": e.label} if e.label else {})} for e in final_edges],
    }


def _node_to_dict(n: GraphNode) -> dict:
    d = {
        "id": n.id,
        "kind": n.kind,
        "name": n.name,
        "file": n.location.file,
        "lines": n.location.lines,
        "module": n.location.module,
        "summary": n.summary,
        "tags": n.tags,
    }
    if n.is_async:        d["is_async"] = True
    if n.is_abstract:     d["is_abstract"] = True
    if n.decorators:      d["decorators"] = n.decorators
    if n.base_classes:    d["base_classes"] = n.base_classes
    if n.http_method:     d["http_method"] = n.http_method
    if n.route_path:      d["route_path"] = n.route_path
    if n.parameters:      d["parameters"] = n.parameters
    if n.return_type:     d["return_type"] = n.return_type
    return d


# ─────────────────────────────────────────────
# CLI + reporting  (same pattern as .NET/Java)
# ─────────────────────────────────────────────

COLORS = {"green":"\033[92m","yellow":"\033[93m","cyan":"\033[96m","gray":"\033[90m","reset":"\033[0m","bold":"\033[1m"}
def c(text: str, color: str) -> str:
    return f"{COLORS.get(color,'')}{text}{COLORS['reset']}" if sys.stdout.isatty() else text


def print_summary(graph: dict) -> None:
    s = graph["stats"]
    print()
    print(c("  CodeGraph — Python Codebase Map", "bold"))
    print(c(f"  Generated : {graph['generated'][:19].replace('T',' ')} UTC", "gray"))
    print(c(f"  Hash      : {graph['hash']}", "gray"))
    print()
    print(c(f"  {'Files scanned:':<24} {s['total_files']}", "cyan"))
    print(c(f"  {'Nodes extracted:':<24} {s['total_nodes']}", "cyan"))
    print(c(f"  {'Edges mapped:':<24} {s['total_edges']}", "cyan"))
    print()
    for label, key in [("Routes/handlers","routers"),("Services","services"),
                       ("Repositories","repositories"),("Models/Schemas","models"),
                       ("Middleware","middleware"),("Celery tasks","tasks"),
                       ("Dependencies","dependencies"),("Views/ViewSets","views")]:
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
    last = {str(f): f.stat().st_mtime for f in root.rglob("*.py")}
    _run(root, output, extra, quiet=False)
    while True:
        time.sleep(2)
        cur = {str(f): f.stat().st_mtime for f in root.rglob("*.py")}
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
    parser = argparse.ArgumentParser(description="Generate codebase memory graph for Python projects.")
    parser.add_argument("--root", "-r", default=".", help="Root directory to scan")
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