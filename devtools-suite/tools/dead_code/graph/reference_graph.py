"""
Reference graph — Layer 3.
Two passes:

Pass 1 — Reference scanner:
  For every symbol, count how many other files/symbols reference it by name.
  Uses fast regex over the full file content (not just diffs).

Pass 2 — Reachability BFS:
  Starting from known entry points (Main, Program.cs, app.module.ts, etc.),
  walk the call graph. Any symbol unreachable from an entry point is dead.

The combination of (zero references) AND (unreachable from entry) gives
HIGH confidence. Either alone gives MEDIUM confidence.
"""

import os
import re
from pathlib import Path
from collections import deque
from core.models import SymbolDef, SymbolKind
from scanner.symbol_extractor import SKIP_DIRS, LANG_EXT, is_test_file, is_generated_file


# ── Entry point detection ──────────────────────────────────────────────────────

ENTRY_POINT_FILES = {
    'program.cs', 'startup.cs', 'main.cs',
    'main.java', 'application.java',
    'main.ts', 'app.module.ts', 'app.component.ts',
    'index.ts', 'index.js',
}

ENTRY_POINT_PATTERNS = [
    re.compile(r'static\s+void\s+Main\s*\('),      # C# entry
    re.compile(r'public\s+static\s+void\s+main\s*\('),  # Java entry
    re.compile(r'bootstrapModule|platformBrowser|bootstrapApplication'),  # Angular
    re.compile(r'^export\s+default', re.MULTILINE),  # TS barrel exports
    re.compile(r'\[ApiController\]|\[Route\]'),      # ASP.NET controllers
    re.compile(r'@SpringBootApplication'),            # Spring Boot
    re.compile(r'@NgModule\s*\('),                   # Angular modules
]


def find_entry_points(symbols: list[SymbolDef], repo_path: str) -> set[str]:
    """
    Return set of symbol IDs that are entry points or directly reachable roots.
    Entry points include: Main methods, controllers, Angular modules, exports.
    """
    entry_ids: set[str] = set()

    for sym in symbols:
        fname_lower = Path(sym.file).name.lower()

        # File-level entry points
        if fname_lower in ENTRY_POINT_FILES:
            entry_ids.add(sym.id)
            continue

        # Controllers are always entry points (called by the framework)
        if (sym.kind == SymbolKind.CLASS and
            any(x in sym.name for x in ['Controller', 'Handler', 'Gateway', 'Consumer'])):
            entry_ids.add(sym.id)
            continue

        # Angular components / services registered in modules
        if sym.kind in (SymbolKind.COMPONENT, SymbolKind.SERVICE):
            entry_ids.add(sym.id)
            continue

        # Attributes/annotations suggest framework-called
        if sym.has_attribute and sym.kind in (SymbolKind.CLASS, SymbolKind.METHOD):
            entry_ids.add(sym.id)
            continue

        # Interfaces — always keep (may be implemented externally)
        if sym.kind == SymbolKind.INTERFACE:
            entry_ids.add(sym.id)
            continue

        # Public static Main / main
        if sym.name in ('Main', 'main') and sym.is_static:
            entry_ids.add(sym.id)
            continue

    return entry_ids


# ── Reference scanner ─────────────────────────────────────────────────────────

def build_reference_map(
    symbols: list[SymbolDef],
    repo_path: str,
    verbose: bool = False,
) -> dict[str, int]:
    """
    For every symbol, count how many source files reference its name.
    Returns {symbol_id: reference_count}.

    Strategy: index all symbol names, then do a single pass over every file.
    Avoids O(symbols × files) complexity by building a name → [symbol_ids] index first.
    """
    # Build name index: name → list of symbol IDs (names can collide)
    name_index: dict[str, list[str]] = {}
    for sym in symbols:
        name_index.setdefault(sym.name, []).append(sym.id)
        # Also index by class.name for methods
        if sym.class_name and sym.class_name != sym.name:
            qualified = f"{sym.class_name}.{sym.name}"
            name_index.setdefault(qualified, []).append(sym.id)

    ref_count: dict[str, int] = {sym.id: 0 for sym in symbols}
    ref_files:  dict[str, set[str]] = {sym.id: set() for sym in symbols}

    file_count = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in LANG_EXT:
                continue
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, repo_path).replace('\\', '/')

            try:
                content = Path(full).read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue

            # Check each known name against this file's content
            for name, sym_ids in name_index.items():
                # Fast pre-check before regex
                if name not in content:
                    continue
                # Whole-word match to avoid substring false positives
                pattern = re.compile(r'\b' + re.escape(name) + r'\b')
                if pattern.search(content):
                    for sid in sym_ids:
                        ref_count[sid] += 1
                        ref_files[sid].add(rel)

            file_count += 1
            if verbose and file_count % 20 == 0:
                print(f"\r  Reference scan: {file_count} files...", end='', flush=True)

    if verbose:
        print(f"\r  Reference scan complete: {file_count} files.          ")

    # Attach counts back to symbols
    for sym in symbols:
        sym.reference_count = ref_count.get(sym.id, 0)
        sym.referencing_files = list(ref_files.get(sym.id, set()))

    return ref_count


# ── Reachability BFS ──────────────────────────────────────────────────────────

def build_call_graph(symbols: list[SymbolDef], repo_path: str) -> dict[str, set[str]]:
    """
    Build a simplified call graph: symbol_id → set of symbol_ids it references.
    Used for BFS reachability from entry points.

    Approach: for each file, find which symbol names appear in which method bodies.
    This is approximate (alias tracking is hard) but catches the common cases.
    """
    # sym_id → [file it lives in]
    id_to_file: dict[str, str] = {sym.id: sym.file for sym in symbols}

    # name → sym_ids
    name_to_ids: dict[str, list[str]] = {}
    for sym in symbols:
        name_to_ids.setdefault(sym.name, []).append(sym.id)

    # Read each source file, find which symbols it references
    graph: dict[str, set[str]] = {sym.id: set() for sym in symbols}

    # Group symbols by file for efficient lookup
    file_to_syms: dict[str, list[SymbolDef]] = {}
    for sym in symbols:
        file_to_syms.setdefault(sym.file, []).append(sym)

    for rel_file, file_syms in file_to_syms.items():
        full_path = os.path.join(repo_path, rel_file)
        try:
            content = Path(full_path).read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        for sym in file_syms:
            # Find references to other symbols within this symbol's definition scope
            for name, target_ids in name_to_ids.items():
                if name == sym.name:
                    continue
                if re.search(r'\b' + re.escape(name) + r'\b', content):
                    graph[sym.id].update(target_ids)

    return graph


def reachability_bfs(
    entry_ids: set[str],
    call_graph: dict[str, set[str]],
) -> set[str]:
    """
    BFS from all entry points. Returns set of reachable symbol IDs.
    Any symbol NOT in this set is unreachable = dead.
    """
    visited: set[str] = set()
    queue: deque[str] = deque(entry_ids)

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in call_graph.get(current, set()):
            if neighbor not in visited:
                queue.append(neighbor)

    return visited
