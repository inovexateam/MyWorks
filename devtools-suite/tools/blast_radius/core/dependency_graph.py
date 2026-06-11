"""
Builds a dependency graph by scanning the entire codebase.
Finds every caller of every changed symbol to compute blast radius.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
from typing import Optional
from core.diff_parser import ChangedSymbol


@dataclass
class Dependency:
    caller_file: str
    caller_symbol: str
    callee_symbol: str
    line: int
    has_tests: bool = False
    risk_level: str = "medium"   # 'low', 'medium', 'high', 'critical'


@dataclass
class BlastNode:
    symbol_name: str
    file: str
    kind: str
    language: str
    direct_callers: list['BlastNode'] = field(default_factory=list)
    indirect_callers: list['BlastNode'] = field(default_factory=list)
    has_test_coverage: bool = False
    risk_score: int = 0
    depth: int = 0


@dataclass
class BlastRadiusResult:
    changed_symbols: list[ChangedSymbol]
    blast_nodes: list[BlastNode]
    total_files_affected: int
    total_symbols_affected: int
    uncovered_symbols: list[BlastNode]       # no test coverage
    critical_paths: list[list[BlastNode]]    # deep dependency chains
    risk_summary: dict = field(default_factory=dict)


SUPPORTED_EXTENSIONS = {'.cs', '.java', '.ts', '.tsx'}

# Patterns to find usages of a symbol in different languages
def build_usage_patterns(symbol_name: str) -> list[str]:
    return [
        rf'\b{re.escape(symbol_name)}\s*\(',           # method/function call
        rf'new\s+{re.escape(symbol_name)}\s*[(<]',     # instantiation
        rf':\s*{re.escape(symbol_name)}\b',             # type annotation / inheritance
        rf'<{re.escape(symbol_name)}>',                 # generic usage
        rf'typeof\s*\(\s*{re.escape(symbol_name)}\)',  # typeof
        rf'inject\({re.escape(symbol_name)}\)',         # Angular inject
        rf'{re.escape(symbol_name)}\.subscribe',        # Observable chain
        rf'private\s+\w+:\s+{re.escape(symbol_name)}', # DI injection
    ]


def is_test_file(filepath: str) -> bool:
    name = filepath.lower()
    return any(x in name for x in [
        'test', 'spec', '.test.', '.spec.', 'tests/', '__tests__',
        'unittest', 'integration'
    ])


def has_test_for_symbol(symbol_name: str, repo_path: str) -> bool:
    """Quick scan: does any test file reference this symbol?"""
    patterns = [
        re.compile(rf'\b{re.escape(symbol_name)}\b', re.IGNORECASE)
    ]
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in {'node_modules', '.git', 'bin', 'obj', 'dist'}]
        for file in files:
            if not is_test_file(file):
                continue
            filepath = os.path.join(root, file)
            try:
                content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
                for pat in patterns:
                    if pat.search(content):
                        return True
            except Exception:
                continue
    return False


def find_all_usages(symbol: ChangedSymbol, repo_path: str) -> list[Dependency]:
    """
    Scans entire repo to find every file/symbol that references this changed symbol.
    """
    usage_patterns = [re.compile(p) for p in build_usage_patterns(symbol.name)]
    dependencies = []

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in {'node_modules', '.git', 'bin', 'obj', 'dist', '.angular'}]
        for file in files:
            ext = Path(file).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, repo_path)

            # Skip the file that defines the symbol itself
            if rel_path == symbol.file or os.path.abspath(filepath) == os.path.abspath(
                    os.path.join(repo_path, symbol.file)):
                continue

            try:
                lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
                for line_num, line in enumerate(lines, 1):
                    for pat in usage_patterns:
                        if pat.search(line):
                            # Extract the containing symbol name
                            caller = extract_containing_symbol(lines, line_num - 1)
                            dep = Dependency(
                                caller_file=rel_path,
                                caller_symbol=caller or rel_path,
                                callee_symbol=symbol.name,
                                line=line_num,
                                has_tests=is_test_file(file),
                            )
                            dependencies.append(dep)
                            break  # one match per line is enough
            except Exception:
                continue

    return dependencies


def extract_containing_symbol(lines: list[str], target_line: int) -> Optional[str]:
    """Walk backwards from target_line to find the enclosing method/class."""
    method_patterns = [
        re.compile(r'\b(public|private|protected|internal)\b.*\b(\w+)\s*\('),
        re.compile(r'\b(class|interface|struct)\s+(\w+)'),
        re.compile(r'export\s+(class|function|const)\s+(\w+)'),
    ]
    for i in range(target_line, max(0, target_line - 40), -1):
        line = lines[i] if i < len(lines) else ""
        for pat in method_patterns:
            m = pat.search(line)
            if m:
                return m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
    return None


def compute_risk_score(node: BlastNode) -> int:
    """
    Risk = depth * callers * (2x if no test coverage)
    Score 0-100.
    """
    base = min(len(node.direct_callers) * 10 + node.depth * 5, 80)
    if not node.has_test_coverage:
        base = min(base * 2, 100)
    return base


def build_blast_radius(changed_symbols: list[ChangedSymbol], repo_path: str = ".") -> BlastRadiusResult:
    """
    For each changed symbol, find all callers recursively up to depth 3.
    Returns a full blast radius graph.
    """
    blast_nodes = []
    all_affected_files = set()
    uncovered = []
    critical_paths = []

    for symbol in changed_symbols:
        # Level 1: direct callers
        direct_deps = find_all_usages(symbol, repo_path)
        has_coverage = has_test_for_symbol(symbol.name, repo_path)

        root_node = BlastNode(
            symbol_name=symbol.name,
            file=symbol.file,
            kind=symbol.kind,
            language=symbol.language,
            has_test_coverage=has_coverage,
            depth=0
        )

        caller_nodes = []
        for dep in direct_deps:
            all_affected_files.add(dep.caller_file)
            caller_node = BlastNode(
                symbol_name=dep.caller_symbol,
                file=dep.caller_file,
                kind='unknown',
                language='unknown',
                has_test_coverage=dep.has_tests,
                depth=1
            )
            caller_node.risk_score = compute_risk_score(caller_node)
            caller_nodes.append(caller_node)

            if not dep.has_tests and not has_coverage:
                uncovered.append(caller_node)

        root_node.direct_callers = caller_nodes
        root_node.risk_score = compute_risk_score(root_node)

        if root_node.risk_score >= 70:
            critical_paths.append([root_node] + caller_nodes[:3])

        blast_nodes.append(root_node)

    return BlastRadiusResult(
        changed_symbols=changed_symbols,
        blast_nodes=blast_nodes,
        total_files_affected=len(all_affected_files),
        total_symbols_affected=sum(len(n.direct_callers) for n in blast_nodes),
        uncovered_symbols=uncovered[:10],
        critical_paths=critical_paths,
        risk_summary={
            'critical': sum(1 for n in blast_nodes if n.risk_score >= 70),
            'high': sum(1 for n in blast_nodes if 40 <= n.risk_score < 70),
            'medium': sum(1 for n in blast_nodes if 20 <= n.risk_score < 40),
            'low': sum(1 for n in blast_nodes if n.risk_score < 20),
        }
    )
