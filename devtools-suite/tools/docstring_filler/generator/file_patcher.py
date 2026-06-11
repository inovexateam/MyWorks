"""
File patcher: inserts generated docstrings into source files at the correct line.
Applies changes in reverse line order so earlier insertions don't shift later line numbers.
Always writes to a copy first, then replaces — never corrupts originals.
"""

import os
import shutil
from pathlib import Path
from core.models import GeneratedDoc


def _indent_docstring(docstring: str, reference_line: str) -> str:
    """Match the indentation of the declaration line."""
    indent = len(reference_line) - len(reference_line.lstrip())
    prefix = ' ' * indent
    return '\n'.join(prefix + line if line.strip() else line
                     for line in docstring.split('\n'))


def apply_to_file(
    filepath: str,
    docs: list[GeneratedDoc],
    dry_run: bool = False,
) -> tuple[int, str]:
    """
    Apply docstrings to one file.
    Returns (count_applied, diff_preview).
    """
    content = Path(filepath).read_text(encoding='utf-8', errors='ignore')
    lines   = content.split('\n')

    # Sort by line descending so insertions don't shift later lines
    sorted_docs = sorted(docs, key=lambda d: -d.symbol.line)

    applied = 0
    diff_lines = []

    for doc in sorted_docs:
        insert_at = doc.symbol.line - 1  # 0-indexed
        if insert_at < 0 or insert_at > len(lines):
            continue

        ref_line = lines[insert_at] if insert_at < len(lines) else ""
        indented = _indent_docstring(doc.docstring, ref_line)
        new_lines = indented.split('\n')

        diff_lines.append(f"@@ {doc.symbol.file}:{doc.symbol.line} {doc.symbol.name} @@")
        for dl in new_lines:
            diff_lines.append(f"+ {dl}")

        if not dry_run:
            lines = lines[:insert_at] + new_lines + lines[insert_at:]

        applied += 1

    if not dry_run and applied > 0:
        # Write to temp, then replace
        tmp = filepath + ".docpatch.tmp"
        try:
            Path(tmp).write_text('\n'.join(lines), encoding='utf-8')
            shutil.move(tmp, filepath)
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise e

    return applied, '\n'.join(diff_lines)


def apply_all(
    generated: list[GeneratedDoc],
    repo_path: str,
    dry_run: bool = False,
    min_confidence: float = 0.0,
) -> dict:
    """
    Apply all generated docstrings grouped by file.
    Returns stats dict.
    """
    # Group by file
    by_file: dict[str, list[GeneratedDoc]] = {}
    for doc in generated:
        if doc.confidence < min_confidence:
            continue
        by_file.setdefault(doc.symbol.file, []).append(doc)

    stats = {"files_modified": 0, "docs_applied": 0, "diffs": []}

    for rel_file, docs in by_file.items():
        full = os.path.join(repo_path, rel_file)
        if not os.path.exists(full):
            continue
        count, diff = apply_to_file(full, docs, dry_run=dry_run)
        if count > 0:
            stats["files_modified"] += 1
            stats["docs_applied"]   += count
            stats["diffs"].append({"file": rel_file, "count": count, "diff": diff})

    return stats
