"""
Parses git diffs and extracts changed symbols (classes, methods, functions, components).
Supports C#, Java, and Angular/TypeScript.
"""

import subprocess
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ChangedSymbol:
    name: str
    kind: str          # 'class', 'method', 'function', 'component', 'service', 'interface'
    file: str
    line: int
    language: str
    is_public: bool = True
    change_type: str = "modified"   # 'added', 'removed', 'modified'


@dataclass
class DiffResult:
    changed_files: list[str] = field(default_factory=list)
    changed_symbols: list[ChangedSymbol] = field(default_factory=list)
    raw_diff: str = ""


CSHARP_PATTERNS = [
    (r'^\+?\s*(public|protected|private|internal)[\w\s<>\[\],?]*\s+(\w+)\s*\(', 'method'),
    (r'^\+?\s*(public|internal|private)?\s*(class|interface|record|struct)\s+(\w+)', 'class'),
    (r'^\+?\s*(public|internal)?\s*interface\s+(\w+)', 'interface'),
]

JAVA_PATTERNS = [
    (r'^\+?\s*(public|protected|private)[\w\s<>\[\],?]*\s+(\w+)\s*\(', 'method'),
    (r'^\+?\s*(public|private)?\s*(class|interface|enum|record)\s+(\w+)', 'class'),
    (r'^\+?\s*@Component|@Service|@Repository|@Controller|@RestController', 'component'),
]

ANGULAR_PATTERNS = [
    (r'^\+?\s*(export\s+)?(class|interface)\s+(\w+)', 'class'),
    (r'^\+?\s*@Component\(\{', 'component'),
    (r'^\+?\s*@Injectable\(\{', 'service'),
    (r'^\+?\s*(public|private|protected)?\s*(\w+)\s*\(.*\)\s*[:{]', 'method'),
    (r'^\+?\s*export\s+(function|const|async function)\s+(\w+)', 'function'),
]


def detect_language(filepath: str) -> Optional[str]:
    ext = Path(filepath).suffix.lower()
    return {
        '.cs': 'csharp',
        '.java': 'java',
        '.ts': 'angular',
        '.tsx': 'angular',
    }.get(ext)


def extract_symbols_from_diff(diff_text: str, filepath: str) -> list[ChangedSymbol]:
    language = detect_language(filepath)
    if not language:
        return []

    patterns = {
        'csharp': CSHARP_PATTERNS,
        'java': JAVA_PATTERNS,
        'angular': ANGULAR_PATTERNS,
    }[language]

    symbols = []
    lines = diff_text.split('\n')
    current_line = 0

    for line in lines:
        if line.startswith('@@'):
            match = re.search(r'\+(\d+)', line)
            if match:
                current_line = int(match.group(1))
            continue

        if line.startswith('+') and not line.startswith('+++'):
            for pattern, kind in patterns:
                match = re.search(pattern, line)
                if match:
                    groups = match.groups()
                    name = groups[-1] if groups else 'unknown'
                    is_public = 'public' in line or 'export' in line
                    symbols.append(ChangedSymbol(
                        name=name,
                        kind=kind,
                        file=filepath,
                        line=current_line,
                        language=language,
                        is_public=is_public,
                        change_type='added' if line.startswith('+') else 'modified'
                    ))
            current_line += 1
        elif line.startswith('-') and not line.startswith('---'):
            current_line += 0  # removed lines don't advance
        else:
            current_line += 1

    return symbols


def get_uncommitted_diff(repo_path: str = ".") -> DiffResult:
    """Get diff of all uncommitted local changes (staged + unstaged)."""
    result = DiffResult()

    try:
        # Get list of changed files
        files_output = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD'],
            cwd=repo_path, capture_output=True, text=True
        )
        staged_output = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            cwd=repo_path, capture_output=True, text=True
        )

        changed_files = set(
            files_output.stdout.strip().split('\n') +
            staged_output.stdout.strip().split('\n')
        )
        result.changed_files = [f for f in changed_files if f.strip()]

        # Get full diff
        diff_output = subprocess.run(
            ['git', 'diff', 'HEAD'],
            cwd=repo_path, capture_output=True, text=True
        )
        result.raw_diff = diff_output.stdout

        # Parse each file's diff
        file_diffs = re.split(r'diff --git a/.+ b/(.+)\n', result.raw_diff)
        for i in range(1, len(file_diffs), 2):
            filepath = file_diffs[i].strip()
            diff_content = file_diffs[i + 1] if i + 1 < len(file_diffs) else ""
            symbols = extract_symbols_from_diff(diff_content, filepath)
            result.changed_symbols.extend(symbols)

    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")

    return result


def get_pr_diff(base_branch: str = "main", repo_path: str = ".") -> DiffResult:
    """Get diff between current branch and base branch (simulates a PR)."""
    result = DiffResult()

    try:
        diff_output = subprocess.run(
            ['git', 'diff', f'origin/{base_branch}...HEAD'],
            cwd=repo_path, capture_output=True, text=True
        )
        result.raw_diff = diff_output.stdout

        files_output = subprocess.run(
            ['git', 'diff', '--name-only', f'origin/{base_branch}...HEAD'],
            cwd=repo_path, capture_output=True, text=True
        )
        result.changed_files = [f for f in files_output.stdout.strip().split('\n') if f.strip()]

        file_diffs = re.split(r'diff --git a/.+ b/(.+)\n', result.raw_diff)
        for i in range(1, len(file_diffs), 2):
            filepath = file_diffs[i].strip()
            diff_content = file_diffs[i + 1] if i + 1 < len(file_diffs) else ""
            symbols = extract_symbols_from_diff(diff_content, filepath)
            result.changed_symbols.extend(symbols)

    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")

    return result
