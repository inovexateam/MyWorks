"""
Builds a directed import graph from a C#, Java, or Angular/TypeScript codebase.
For each file, extracts every import/using/require statement and maps it to
a normalized namespace or file path.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


SKIP_DIRS = {'node_modules', '.git', 'bin', 'obj', 'dist', '.angular', 'build', 'out', 'target', '__pycache__'}
SUPPORTED_EXT = {'.cs', '.java', '.ts', '.tsx'}

# ── Import extractors per language ────────────────────────────────────────────

# C#: using Namespace.Sub.Class;
CSHARP_USING = re.compile(r'^\s*using\s+([\w.]+)\s*;', re.MULTILINE)
CSHARP_NAMESPACE = re.compile(r'^\s*namespace\s+([\w.]+)', re.MULTILINE)

# Java: import com.example.service.OrderService;
JAVA_IMPORT = re.compile(r'^\s*import\s+(static\s+)?([\w.]+)(?:\.\*)?\s*;', re.MULTILINE)
JAVA_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)

# TypeScript/Angular: import { X } from './path' or '@scope/pkg'
TS_IMPORT = re.compile(r"""^\s*import\s+(?:type\s+)?(?:\{[^}]*\}|[\w*]+|\*\s+as\s+\w+)\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE)
TS_REQUIRE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", re.MULTILINE)


@dataclass
class ImportEdge:
    source_file:  str      # relative path of the importing file
    source_ns:    str      # namespace/module of the importer
    target_ns:    str      # what's being imported (namespace or path)
    raw_import:   str      # the exact import statement text
    line:         int      # line number
    language:     str


@dataclass
class FileNode:
    path:      str         # relative path
    namespace: str         # detected namespace/module
    language:  str
    imports:   list[ImportEdge] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)


@dataclass
class ImportGraph:
    nodes:  dict[str, FileNode] = field(default_factory=dict)   # rel_path → FileNode
    edges:  list[ImportEdge] = field(default_factory=list)

    def total_edges(self) -> int:
        return len(self.edges)

    def imports_of(self, file_path: str) -> list[ImportEdge]:
        node = self.nodes.get(file_path)
        return node.imports if node else []

    def detect_circular_chains(self) -> list[list[str]]:
        """DFS-based cycle detection on the namespace import graph."""
        # Build namespace → [imported namespaces] adjacency
        adj: dict[str, set[str]] = {}
        for edge in self.edges:
            adj.setdefault(edge.source_ns, set()).add(edge.target_ns)

        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: list[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for neighbor in adj.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle — extract it
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if cycle not in cycles:
                        cycles.append(cycle)
            path.pop()
            rec_stack.discard(node)

        for ns in list(adj.keys()):
            if ns not in visited:
                dfs(ns, [])

        return cycles[:20]  # cap at 20 cycles


def _detect_language(path: str) -> Optional[str]:
    ext = Path(path).suffix.lower()
    return {'.cs': 'csharp', '.java': 'java', '.ts': 'angular', '.tsx': 'angular'}.get(ext)


def _extract_csharp(content: str, rel_path: str) -> FileNode:
    ns_match = CSHARP_NAMESPACE.search(content)
    namespace = ns_match.group(1) if ns_match else Path(rel_path).stem

    imports = []
    for i, line in enumerate(content.split('\n'), 1):
        m = CSHARP_USING.match(line)
        if m:
            imports.append(ImportEdge(
                source_file=rel_path, source_ns=namespace,
                target_ns=m.group(1), raw_import=line.strip(), line=i, language='csharp'
            ))

    classes = re.findall(r'\b(?:class|interface|record|struct|enum)\s+(\w+)', content)
    return FileNode(path=rel_path, namespace=namespace, language='csharp',
                    imports=imports, class_names=classes[:20])


def _extract_java(content: str, rel_path: str) -> FileNode:
    pkg_match = JAVA_PACKAGE.search(content)
    namespace = pkg_match.group(1) if pkg_match else Path(rel_path).stem

    imports = []
    for i, line in enumerate(content.split('\n'), 1):
        m = re.match(r'^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;', line)
        if m:
            imports.append(ImportEdge(
                source_file=rel_path, source_ns=namespace,
                target_ns=m.group(1), raw_import=line.strip(), line=i, language='java'
            ))

    classes = re.findall(r'\b(?:class|interface|enum|record)\s+(\w+)', content)
    return FileNode(path=rel_path, namespace=namespace, language='java',
                    imports=imports, class_names=classes[:20])


def _resolve_ts_import(raw_path: str, source_file: str) -> str:
    """
    Resolve a TS import to a normalized form:
    - @angular/core → @angular/core  (external — keep as-is)
    - ./service → normalized relative path
    - ../domain/model → normalized relative path
    """
    if raw_path.startswith('.'):
        # Relative import — resolve relative to source file
        source_dir = os.path.dirname(source_file)
        resolved = os.path.normpath(os.path.join(source_dir, raw_path))
        return resolved.replace('\\', '/')
    return raw_path  # absolute/package import


def _extract_typescript(content: str, rel_path: str) -> FileNode:
    # Derive module namespace from path: src/app/orders/order.service.ts → src/app/orders
    namespace = os.path.dirname(rel_path).replace('\\', '/')

    imports = []
    for i, line in enumerate(content.split('\n'), 1):
        m = re.match(r"""\s*import\s+(?:type\s+)?(?:\{[^}]*\}|[\w*]+|\*\s+as\s+\w+)\s+from\s+['"]([^'"]+)['"]""", line)
        if m:
            resolved = _resolve_ts_import(m.group(1), rel_path)
            imports.append(ImportEdge(
                source_file=rel_path, source_ns=namespace,
                target_ns=resolved, raw_import=line.strip(), line=i, language='angular'
            ))
        else:
            # require()
            m2 = TS_REQUIRE.search(line)
            if m2:
                resolved = _resolve_ts_import(m2.group(1), rel_path)
                imports.append(ImportEdge(
                    source_file=rel_path, source_ns=namespace,
                    target_ns=resolved, raw_import=line.strip(), line=i, language='angular'
                ))

    classes = re.findall(r'\b(?:class|interface)\s+(\w+)', content)
    decorators = re.findall(r'@(Component|Injectable|Directive|Pipe|NgModule)\(', content)
    return FileNode(path=rel_path, namespace=namespace, language='angular',
                    imports=imports, class_names=classes[:20] + decorators)


EXTRACTORS = {'csharp': _extract_csharp, 'java': _extract_java, 'angular': _extract_typescript}


def build_import_graph(repo_path: str, max_files: int = 5000) -> ImportGraph:
    """
    Walk the entire repo and build a directed import graph.
    Returns an ImportGraph with all nodes and edges populated.
    """
    graph = ImportGraph()
    file_count = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in SUPPORTED_EXT:
                continue

            full_path = os.path.join(root, fname)
            rel_path  = os.path.relpath(full_path, repo_path).replace('\\', '/')
            language  = _detect_language(fname)

            # Skip test files for architecture analysis
            if any(t in rel_path.lower() for t in ['test', 'spec', 'fixture', 'mock', 'stub']):
                continue

            try:
                content = Path(full_path).read_text(encoding='utf-8', errors='ignore')
                node = EXTRACTORS[language](content, rel_path)
                graph.nodes[rel_path] = node
                graph.edges.extend(node.imports)
                file_count += 1
                if file_count >= max_files:
                    break
            except Exception:
                continue

        if file_count >= max_files:
            break

    return graph
