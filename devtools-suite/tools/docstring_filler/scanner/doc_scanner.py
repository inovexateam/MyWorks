"""
Scanner: finds public symbols with missing or incomplete docstrings.
Supports C# (XML doc), Java (Javadoc), TypeScript/Angular (JSDoc).
"""

import os
import re
from pathlib import Path
from core.models import MissingDoc

SKIP_DIRS = {'node_modules', '.git', 'bin', 'obj', 'dist', '.angular',
             'build', 'target', 'coverage', 'migrations', 'generated'}

# ── C# ─────────────────────────────────────────────────────────────────────────

CS_SUMMARY = re.compile(r'///\s*<summary>')
CS_SYMBOL  = re.compile(
    r'^\s*(public|protected|internal)\s+'
    r'(?:static\s+|virtual\s+|override\s+|async\s+|abstract\s+)*'
    r'(?:[\w<>\[\]?,]+\s+)?'
    r'(\w+)\s*[({<]'
)
CS_SKIP = re.compile(r'\b(if|else|while|for|foreach|switch|catch|using|lock|return|new)\b')


def scan_csharp(filepath: str, rel: str) -> list[MissingDoc]:
    lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    results = []
    current_class = ""

    for i, line in enumerate(lines):
        # Track class context
        m = re.search(r'\b(?:class|interface|record|struct)\s+(\w+)', line)
        if m:
            current_class = m.group(1)

        m = CS_SYMBOL.match(line)
        if not m or CS_SKIP.search(line):
            continue

        name = m.group(2)
        if name[0].islower() and name not in ('get', 'set'):  # skip private-style
            continue

        # Check preceding lines for XML doc
        prev_lines = lines[max(0, i-5):i]
        has_doc = any(CS_SUMMARY.search(pl) for pl in prev_lines)
        has_partial = any('///' in pl for pl in prev_lines) and not has_doc

        if not has_doc:
            body = '\n'.join(lines[i:i+12])
            results.append(MissingDoc(
                name=name, kind=_cs_kind(line), file=rel, line=i+1,
                language='csharp', signature=line.strip()[:200],
                body_snippet=body[:400], class_context=current_class,
                has_partial=has_partial,
                existing_doc='\n'.join(l for l in prev_lines if '///' in l),
            ))

    return results


def _cs_kind(line: str) -> str:
    if re.search(r'\bclass\b|\binterface\b|\brecord\b', line): return 'class'
    if re.search(r'\b\w+\s+\w+\s*{', line): return 'property'
    return 'method'


# ── Java ───────────────────────────────────────────────────────────────────────

JAVA_JAVADOC = re.compile(r'/\*\*')
JAVA_SYMBOL  = re.compile(
    r'^\s*(public|protected)\s+'
    r'(?:static\s+|final\s+|synchronized\s+|abstract\s+)*'
    r'(?:[\w<>\[\]?,]+\s+)?'
    r'(\w+)\s*[({<]'
)
JAVA_SKIP = re.compile(r'\b(if|else|while|for|switch|catch|try|return|new)\b')


def scan_java(filepath: str, rel: str) -> list[MissingDoc]:
    lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    results = []
    current_class = ""

    for i, line in enumerate(lines):
        m = re.search(r'\b(?:class|interface|enum|record)\s+(\w+)', line)
        if m:
            current_class = m.group(1)

        m = JAVA_SYMBOL.match(line)
        if not m or JAVA_SKIP.search(line):
            continue

        name = m.group(2)
        prev_lines = lines[max(0, i-8):i]
        has_doc = any(JAVA_JAVADOC.search(pl) for pl in prev_lines)

        if not has_doc:
            body = '\n'.join(lines[i:i+12])
            results.append(MissingDoc(
                name=name, kind=_java_kind(line), file=rel, line=i+1,
                language='java', signature=line.strip()[:200],
                body_snippet=body[:400], class_context=current_class,
                has_partial=False,
            ))

    return results


def _java_kind(line: str) -> str:
    if re.search(r'\bclass\b|\binterface\b|\benum\b', line): return 'class'
    return 'method'


# ── TypeScript ─────────────────────────────────────────────────────────────────

TS_JSDOC  = re.compile(r'/\*\*')
TS_SYMBOL = re.compile(
    r'^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+)?'
    r'(?:static\s+|async\s+|readonly\s+|abstract\s+)*'
    r'(?:'
    r'(?:function\s+(\w+))'
    r'|(?:class\s+(\w+))'
    r'|(?:(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\()'
    r'|(?:(\w+)\s*\([^)]{0,80}\)\s*(?::\s*[\w<>|?[\]]+)?\s*\{)'
    r')'
)
TS_SKIP = re.compile(r'\b(if|else|while|for|switch|catch|=>)\b')


def scan_typescript(filepath: str, rel: str) -> list[MissingDoc]:
    lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    results = []
    current_class = ""

    for i, line in enumerate(lines):
        m_cls = re.search(r'\bclass\s+(\w+)', line)
        if m_cls:
            current_class = m_cls.group(1)

        m = TS_SYMBOL.match(line)
        if not m or TS_SKIP.search(line):
            continue

        # Pick which capture group matched
        name = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if not name or name[0].islower() and current_class == '':
            continue  # skip private-looking top-level functions

        prev_lines = lines[max(0, i-5):i]
        has_doc = any(TS_JSDOC.search(pl) for pl in prev_lines)

        if not has_doc:
            body = '\n'.join(lines[i:i+12])
            kind = 'class' if m.group(2) else 'function' if m.group(1) or m.group(3) else 'method'
            results.append(MissingDoc(
                name=name, kind=kind, file=rel, line=i+1,
                language='angular', signature=line.strip()[:200],
                body_snippet=body[:400], class_context=current_class,
                has_partial=False,
            ))

    return results


# ── Orchestrator ───────────────────────────────────────────────────────────────

EXT_MAP = {
    '.cs': scan_csharp,
    '.java': scan_java,
    '.ts': scan_typescript,
    '.tsx': scan_typescript,
}


def scan_repo(repo_path: str, only_public: bool = True, verbose: bool = False) -> list[MissingDoc]:
    results = []
    file_count = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            ext = Path(fname).suffix.lower()
            scanner = EXT_MAP.get(ext)
            if not scanner:
                continue
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, repo_path).replace('\\', '/')
            # skip test files
            if any(t in rel.lower() for t in ['test', 'spec', 'fixture']):
                continue
            try:
                found = scanner(full, rel)
                results.extend(found)
                file_count += 1
                if verbose and file_count % 20 == 0:
                    print(f"\r  {file_count} files, {len(results)} missing docs...", end='', flush=True)
            except Exception:
                continue

    if verbose:
        print(f"\r  {file_count} files, {len(results)} missing docs.        ")

    return results
