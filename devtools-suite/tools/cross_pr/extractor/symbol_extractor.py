"""
Symbol extractor.
Given a PR diff, identifies which named symbols (methods, classes,
functions, Angular components) were changed — not just which files.

This is what elevates Cross-PR Intelligence above a simple file-diff comparison.
Two PRs can touch the same file on different functions and be perfectly safe.
Two PRs touching the same function is a guaranteed conflict.
"""

import re
from pathlib import Path
from core.models import PRSnapshot, SymbolChange


# ── Language-specific symbol patterns ─────────────────────────────────────────

CSHARP_SYMBOLS = [
    (re.compile(r'^\+\s*(?:public|private|protected|internal|static|async|override|virtual|abstract)'
                r'[\w\s<>\[\]?,]*\s+(\w+)\s*\('), 'method'),
    (re.compile(r'^\+\s*(?:public|internal|private)?\s*(?:partial\s+)?(?:class|interface|record|struct|enum)\s+(\w+)'), 'class'),
    (re.compile(r'^\+\s*(?:public|private|protected)?\s*(?:static\s+)?(?:readonly\s+)?(?:\w+[\w<>\[\]?]*)\s+(\w+)\s*\{'), 'property'),
]

JAVA_SYMBOLS = [
    (re.compile(r'^\+\s*(?:public|private|protected|static|final|synchronized|native|abstract)'
                r'[\w\s<>\[\]?,@]*\s+(\w+)\s*\('), 'method'),
    (re.compile(r'^\+\s*(?:public|private|protected)?\s*(?:abstract\s+|final\s+)?(?:class|interface|enum|record)\s+(\w+)'), 'class'),
    (re.compile(r'^\+\s*@(?:Override|Bean|PostConstruct|PreDestroy)\s*$'), 'annotation'),
]

ANGULAR_SYMBOLS = [
    (re.compile(r'^\+\s*(?:public|private|protected|async|static|readonly)?\s*(\w+)\s*\([^)]*\)\s*(?::\s*\w[\w<>\[\]|?]*\s*)?(?:\{|=>)'), 'method'),
    (re.compile(r'^\+\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface)\s+(\w+)'), 'class'),
    (re.compile(r'^\+\s*(?:export\s+)?(?:const|function|async function)\s+(\w+)'), 'function'),
    (re.compile(r'^\+\s*@(?:Component|Injectable|Directive|Pipe|NgModule)\s*\('), 'decorator'),
]

PATTERNS = {
    '.cs':  CSHARP_SYMBOLS,
    '.java': JAVA_SYMBOLS,
    '.ts':  ANGULAR_SYMBOLS,
    '.tsx': ANGULAR_SYMBOLS,
}

SKIP_KEYWORDS = {
    'if', 'else', 'while', 'for', 'foreach', 'switch', 'catch', 'finally',
    'return', 'new', 'var', 'let', 'const', 'get', 'set', 'add', 'remove',
    'true', 'false', 'null', 'undefined', 'this', 'base', 'super',
}


def extract_symbols_from_pr(pr: PRSnapshot) -> list[SymbolChange]:
    """
    Parse the raw diff of a PR and extract every named symbol that was changed.
    Attaches symbols back to the PR snapshot.
    """
    if not pr.raw_diff:
        return []

    symbols: list[SymbolChange] = []

    # Split diff into per-file sections
    file_sections = re.split(r'diff --git a/.+ b/(.+)\n', pr.raw_diff)

    for i in range(1, len(file_sections), 2):
        filepath = file_sections[i].strip()
        diff_content = file_sections[i + 1] if i + 1 < len(file_sections) else ""
        ext = Path(filepath).suffix.lower()
        patterns = PATTERNS.get(ext, [])
        if not patterns:
            continue

        language = {'.cs': 'csharp', '.java': 'java', '.ts': 'angular', '.tsx': 'angular'}.get(ext, 'unknown')

        # Track current line number in the new file
        current_line = 1
        lines = diff_content.split('\n')

        for line in lines:
            # Update line counter from hunk headers
            m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
            if m:
                current_line = int(m.group(1))
                continue

            # Only look at added/modified lines
            if not line.startswith('+') or line.startswith('+++'):
                if not line.startswith('-'):
                    current_line += 1
                continue

            # Try every pattern for this language
            for pattern, kind in patterns:
                match = pattern.match(line)
                if not match:
                    continue
                name = match.group(1) if match.lastindex else "unknown"
                if name.lower() in SKIP_KEYWORDS or len(name) <= 1:
                    continue
                if kind == 'annotation' or kind == 'decorator':
                    # Use the next non-empty line's identifier
                    name = _peek_class_name(lines, lines.index(line))
                    if not name:
                        continue

                # Determine change type
                change_type = 'added' if _is_new_symbol(lines, lines.index(line)) else 'modified'

                symbols.append(SymbolChange(
                    name=name,
                    kind=kind,
                    file=filepath,
                    line_start=current_line,
                    line_end=current_line + _estimate_symbol_length(lines, lines.index(line)),
                    change_type=change_type,
                    language=language,
                ))
                break  # one match per line is enough

            current_line += 1

    # Deduplicate: same name + file + kind
    seen = set()
    unique = []
    for s in symbols:
        key = (s.name, s.file, s.kind)
        if key not in seen:
            seen.add(key)
            unique.append(s)

    pr.symbols = unique
    return unique


def _peek_class_name(lines: list[str], decorator_idx: int) -> str:
    """Look ahead past a @Component/@Injectable to find the class name."""
    for line in lines[decorator_idx + 1: decorator_idx + 5]:
        m = re.search(r'class\s+(\w+)', line)
        if m:
            return m.group(1)
    return ""


def _is_new_symbol(lines: list[str], idx: int) -> bool:
    """Heuristic: if the surrounding context has mostly + lines, it's a new symbol."""
    context = lines[max(0, idx - 3): idx + 3]
    plus_count = sum(1 for l in context if l.startswith('+'))
    return plus_count >= len(context) * 0.7


def _estimate_symbol_length(lines: list[str], start_idx: int) -> int:
    """Rough estimate of how many lines a symbol spans (brace counting)."""
    depth = 0
    for i, line in enumerate(lines[start_idx:start_idx + 80]):
        depth += line.count('{') - line.count('}')
        if i > 0 and depth <= 0:
            return i
    return 10  # default estimate


# ── Import graph builder (lightweight, for semantic dep detection) ─────────────

IMPORT_PATTERNS = {
    '.cs': re.compile(r'^\s*using\s+([\w.]+)\s*;', re.MULTILINE),
    '.java': re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;', re.MULTILINE),
    '.ts': re.compile(r"""^\s*import\s+(?:type\s+)?(?:\{[^}]*\}|[\w*]+)\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE),
    '.tsx': re.compile(r"""^\s*import\s+(?:type\s+)?(?:\{[^}]*\}|[\w*]+)\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE),
}


def extract_imports_from_diff(diff_content: str, filepath: str) -> set[str]:
    """Extract all imports referenced in the diff (added or unchanged context)."""
    ext = Path(filepath).suffix.lower()
    pat = IMPORT_PATTERNS.get(ext)
    if not pat:
        return set()
    return set(pat.findall(diff_content))
