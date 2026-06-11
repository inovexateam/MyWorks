"""
Symbol extractor — Layer 2.
Walks every .cs, .java, .ts/.tsx file and extracts all symbol definitions
with full metadata: name, kind, visibility, line number, containing class, LOC.

This is the "what exists" pass. The reference scanner handles "who uses it".
"""

import os
import re
from pathlib import Path
from core.models import SymbolDef, SymbolKind

SKIP_DIRS = {
    'node_modules', '.git', 'bin', 'obj', 'dist', '.angular',
    'build', 'out', 'target', 'generated', 'gen', 'migrations',
    '__pycache__', 'coverage', '.nyc_output', 'TestResults'
}

SUPPORTED_EXT = {'.cs', '.java', '.ts', '.tsx'}

# Patterns that suggest reflection/DI usage (suppress dead warnings)
REFLECTION_HINTS = re.compile(
    r'Activator\.Create|typeof\s*\(|GetType\(\)|Assembly\.'
    r'|@Injectable|@Component|@Pipe|@Directive'
    r'|@Bean|@Autowired|@Component\b|@Service\b|@Repository\b'
    r'|JsonProperty|JsonIgnore|XmlElement'
    r'|services\.AddScoped|services\.AddSingleton|services\.AddTransient',
    re.IGNORECASE
)


# ── C# symbol extraction ───────────────────────────────────────────────────────

CS_NAMESPACE   = re.compile(r'^\s*namespace\s+([\w.]+)', re.MULTILINE)
CS_CLASS       = re.compile(r'^\s*((?:public|internal|private|protected|static|abstract|sealed|partial)\s+)*(?:class|interface|record|struct|enum)\s+(\w+)', re.MULTILINE)
CS_METHOD      = re.compile(r'^\s*((?:public|private|protected|internal|static|virtual|override|abstract|async|new)\s+)+(?:[\w<>\[\]?,]+\s+)+(\w+)\s*\(')
CS_PROPERTY    = re.compile(r'^\s*((?:public|private|protected|internal|static)\s+)+(?:[\w<>\[\]?,]+\s+)+(\w+)\s*\{')
CS_FIELD       = re.compile(r'^\s*((?:public|private|protected|internal|static|readonly|const)\s+)+(?:[\w<>\[\]?,]+\s+)+(\w+)\s*[=;,]')
CS_ATTRIBUTE   = re.compile(r'^\s*\[(\w+)')


def extract_csharp(filepath: str, rel_path: str) -> list[SymbolDef]:
    try:
        content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return []

    lines = content.split('\n')
    ns_match = CS_NAMESPACE.search(content)
    namespace = ns_match.group(1) if ns_match else ""

    symbols = []
    current_class = ""
    brace_depth = 0
    class_brace_entry = -1
    has_reflection = bool(REFLECTION_HINTS.search(content))

    prev_line_attr = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        brace_depth += stripped.count('{') - stripped.count('}')

        # Track current class context
        m = CS_CLASS.match(line)
        if m:
            mods  = (m.group(1) or "").lower()
            name  = m.group(2)
            kind  = _cs_class_kind(line)
            pub   = 'public' in mods or 'internal' in mods
            sym = SymbolDef(
                name=name, kind=kind, file=rel_path, line=i,
                language='csharp', is_public=pub,
                is_abstract='abstract' in mods,
                namespace=namespace, class_name=name,
                has_attribute=has_reflection,
                lines_of_code=_estimate_block_lines(lines, i - 1),
            )
            symbols.append(sym)
            current_class = name
            class_brace_entry = brace_depth
            continue

        # Methods
        m = CS_METHOD.match(line)
        if m and current_class:
            mods = (m.group(1) or "").lower()
            name = m.group(2)
            if name in {'if', 'while', 'for', 'foreach', 'switch', 'catch', 'using', 'lock'}:
                continue
            sym = SymbolDef(
                name=name, kind=SymbolKind.METHOD, file=rel_path, line=i,
                language='csharp',
                is_public='public' in mods or 'internal' in mods,
                is_static='static' in mods,
                is_override='override' in mods,
                is_abstract='abstract' in mods,
                namespace=namespace, class_name=current_class,
                has_attribute=prev_line_attr or has_reflection,
                lines_of_code=_estimate_block_lines(lines, i - 1),
            )
            symbols.append(sym)

        prev_line_attr = bool(CS_ATTRIBUTE.match(stripped))

    return symbols


def _cs_class_kind(line: str) -> SymbolKind:
    if 'interface' in line: return SymbolKind.INTERFACE
    if 'enum'      in line: return SymbolKind.ENUM
    return SymbolKind.CLASS


# ── Java symbol extraction ─────────────────────────────────────────────────────

JAVA_PACKAGE   = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)
JAVA_CLASS     = re.compile(r'^\s*((?:public|protected|private|static|final|abstract)\s+)*(?:class|interface|enum|record)\s+(\w+)')
JAVA_METHOD    = re.compile(r'^\s*((?:public|protected|private|static|final|synchronized|abstract|native|default)\s+)+(?:[\w<>\[\]?,]+\s+)+(\w+)\s*\(')
JAVA_ANNOTATION= re.compile(r'^\s*@(\w+)')


def extract_java(filepath: str, rel_path: str) -> list[SymbolDef]:
    try:
        content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return []

    lines = content.split('\n')
    pkg_match = JAVA_PACKAGE.search(content)
    namespace = pkg_match.group(1) if pkg_match else ""
    has_reflection = bool(REFLECTION_HINTS.search(content))

    symbols = []
    current_class = ""
    prev_ann = False

    for i, line in enumerate(lines, 1):
        m = JAVA_CLASS.match(line)
        if m:
            mods = (m.group(1) or "").lower()
            name = m.group(2)
            sym = SymbolDef(
                name=name, kind=_java_kind(line), file=rel_path, line=i,
                language='java', is_public='public' in mods,
                is_abstract='abstract' in mods,
                namespace=namespace, class_name=name,
                has_attribute=has_reflection,
                lines_of_code=_estimate_block_lines(lines, i - 1),
            )
            symbols.append(sym)
            current_class = name
            continue

        m = JAVA_METHOD.match(line)
        if m and current_class:
            mods = (m.group(1) or "").lower()
            name = m.group(2)
            if name in {'if', 'while', 'for', 'switch', 'catch', 'try', 'return'}:
                continue
            sym = SymbolDef(
                name=name, kind=SymbolKind.METHOD, file=rel_path, line=i,
                language='java',
                is_public='public' in mods,
                is_static='static' in mods,
                is_override=prev_ann and 'override' in (m.group(1) or "").lower(),
                is_abstract='abstract' in mods,
                namespace=namespace, class_name=current_class,
                has_attribute=prev_ann or has_reflection,
                lines_of_code=_estimate_block_lines(lines, i - 1),
            )
            symbols.append(sym)

        prev_ann = bool(JAVA_ANNOTATION.match(line.strip()))

    return symbols


def _java_kind(line: str) -> SymbolKind:
    if 'interface' in line: return SymbolKind.INTERFACE
    if 'enum'      in line: return SymbolKind.ENUM
    return SymbolKind.CLASS


# ── Angular/TypeScript extraction ──────────────────────────────────────────────

TS_CLASS    = re.compile(r'^\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface)\s+(\w+)')
TS_FUNCTION = re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)')
TS_CONST    = re.compile(r'^\s*export\s+const\s+(\w+)')
TS_METHOD   = re.compile(r'^\s*((?:public|private|protected|static|async|readonly|abstract)\s+)*(\w+)\s*\([^)]*\)\s*(?::\s*[\w<>\[\]|?]+\s*)?(?:\{|=>)')
TS_DECORATOR= re.compile(r'^\s*@(\w+)\s*[\(\{]?')
TS_EXPORT_DEFAULT = re.compile(r'^\s*export\s+default\s+(\w+)')


def extract_typescript(filepath: str, rel_path: str) -> list[SymbolDef]:
    try:
        content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return []

    lines = content.split('\n')
    namespace = os.path.dirname(rel_path).replace('\\', '/')
    has_reflection = bool(REFLECTION_HINTS.search(content))
    is_component = '@Component' in content
    is_service   = '@Injectable' in content

    symbols = []
    current_class = ""
    pending_decorator = ""

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Decorators
        m = TS_DECORATOR.match(stripped)
        if m:
            pending_decorator = m.group(1)
            continue

        # Class / interface
        m = TS_CLASS.match(line)
        if m:
            name = m.group(1)
            kind = SymbolKind.COMPONENT if pending_decorator in ('Component','NgModule') \
                   else SymbolKind.SERVICE if pending_decorator == 'Injectable' \
                   else SymbolKind.INTERFACE if 'interface' in line \
                   else SymbolKind.CLASS
            sym = SymbolDef(
                name=name, kind=kind, file=rel_path, line=i,
                language='angular', is_public='export' in line,
                namespace=namespace, class_name=name,
                has_attribute=bool(pending_decorator) or has_reflection,
                lines_of_code=_estimate_block_lines(lines, i - 1),
            )
            symbols.append(sym)
            current_class = name
            pending_decorator = ""
            continue

        # Exported functions
        m = TS_FUNCTION.match(line)
        if m:
            name = m.group(1)
            sym = SymbolDef(
                name=name, kind=SymbolKind.FUNCTION, file=rel_path, line=i,
                language='angular', is_public='export' in line,
                namespace=namespace,
                lines_of_code=_estimate_block_lines(lines, i - 1),
            )
            symbols.append(sym)
            pending_decorator = ""
            continue

        # Exported constants
        m = TS_CONST.match(line)
        if m:
            name = m.group(1)
            sym = SymbolDef(
                name=name, kind=SymbolKind.CONSTANT, file=rel_path, line=i,
                language='angular', is_public=True,
                namespace=namespace,
            )
            symbols.append(sym)
            continue

        # Methods inside classes
        if current_class:
            m = TS_METHOD.match(line)
            if m:
                name = m.group(2) if m.group(2) else ""
                mods = (m.group(1) or "").lower()
                if name and name not in {'if', 'while', 'for', 'switch', 'catch', 'constructor'}:
                    sym = SymbolDef(
                        name=name, kind=SymbolKind.METHOD, file=rel_path, line=i,
                        language='angular',
                        is_public='public' in mods or ('private' not in mods and 'protected' not in mods),
                        is_static='static' in mods,
                        namespace=namespace, class_name=current_class,
                        lines_of_code=_estimate_block_lines(lines, i - 1),
                    )
                    symbols.append(sym)

        pending_decorator = ""

    return symbols


# ── Helpers ───────────────────────────────────────────────────────────────────

def _estimate_block_lines(lines: list[str], start: int) -> int:
    """Count lines until brace depth returns to 0 after the opening brace."""
    depth = 0
    for i, line in enumerate(lines[start:start + 200]):
        depth += line.count('{') - line.count('}')
        if i > 0 and depth <= 0:
            return i
    return 10


def is_test_file(filepath: str) -> bool:
    lower = filepath.lower()
    return any(x in lower for x in ['test', 'spec', 'fixture', 'mock', 'stub', 'fake'])


def is_generated_file(filepath: str) -> bool:
    lower = filepath.lower()
    return any(x in lower for x in [
        '.generated.', '.g.cs', '.designer.cs', 'assemblyinfo',
        'migrations/', 'scaffolded', '.pb.', 'swagger', 'openapi'
    ])


LANG_EXT = {'.cs': 'csharp', '.java': 'java', '.ts': 'angular', '.tsx': 'angular'}
EXTRACTORS = {'csharp': extract_csharp, 'java': extract_java, 'angular': extract_typescript}


def scan_all_symbols(repo_path: str, verbose: bool = False) -> tuple[list[SymbolDef], int]:
    """
    Walk the entire repo and return (all_symbols, file_count).
    Skips test files, generated files, and non-source dirs.
    """
    all_symbols: list[SymbolDef] = []
    file_count = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            ext = Path(fname).suffix.lower()
            lang = LANG_EXT.get(ext)
            if not lang:
                continue

            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, repo_path).replace('\\', '/')

            if is_test_file(rel) or is_generated_file(rel):
                continue

            syms = EXTRACTORS[lang](full, rel)
            all_symbols.extend(syms)
            file_count += 1

            if verbose and file_count % 20 == 0:
                print(f"\r  {file_count} files, {len(all_symbols)} symbols...", end='', flush=True)

    if verbose:
        print(f"\r  {file_count} files, {len(all_symbols)} symbols total.       ")

    return all_symbols, file_count
