"""
Risk engine for Blast Radius Visualizer.

Risk score formula (0-100):
  base  = min(direct_callers * 8, 40)        # fan-out
        + min(indirect_callers * 3, 20)       # downstream depth
        + depth_penalty                        # how far downstream
        + critical_path_bonus                  # controller / gateway / service layer
  final = base * 2  if no test coverage
          base * 1  if covered

Thresholds:
  >= 70 → CRITICAL  (red)
  40-69 → HIGH      (amber)
  20-39 → MEDIUM    (blue)
  <  20 → LOW       (green)
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# Files whose names contain these strings are considered "critical path"
CRITICAL_PATH_MARKERS = [
    'Controller', 'Gateway', 'Middleware', 'Interceptor',
    'Handler', 'Facade', 'Orchestrator', 'Coordinator',
    'Service',   # broad but important
    'Repository', 'DataAccess', 'Persistence',
    'Guard', 'Filter', 'Validator',
    'EventBus', 'MessageBus', 'Publisher', 'Consumer',
    'Startup', 'Program', 'Bootstrap', 'AppModule',
]

# File-level risk multiplier
CRITICAL_PATH_BONUS = 15
MISSING_COVERAGE_MULTIPLIER = 1.8


@dataclass
class RiskScore:
    value: int                  # 0-100
    label: str                  # 'critical' | 'high' | 'medium' | 'low'
    color: str                  # hex
    reasons: list[str] = field(default_factory=list)

    @classmethod
    def from_value(cls, value: int, reasons: list[str]) -> 'RiskScore':
        value = max(0, min(100, value))
        if value >= 70:
            return cls(value, 'critical', '#E24B4A', reasons)
        elif value >= 40:
            return cls(value, 'high', '#EF9F27', reasons)
        elif value >= 20:
            return cls(value, 'medium', '#378ADD', reasons)
        else:
            return cls(value, 'low', '#1D9E75', reasons)


def is_critical_path_file(filepath: str) -> tuple[bool, str]:
    """Returns (is_critical, reason_string)."""
    basename = Path(filepath).stem
    for marker in CRITICAL_PATH_MARKERS:
        if marker.lower() in basename.lower():
            return True, f"in {marker} layer"
    return False, ""


def has_test_for_symbol(symbol_name: str, repo_path: str) -> bool:
    """
    Scans all test files for any reference to symbol_name.
    Fast path: checks common test directories first.
    """
    test_dirs = ['tests', 'test', '__tests__', 'spec', 'specs', 'Tests', 'Test']
    search_dirs = []

    for td in test_dirs:
        candidate = os.path.join(repo_path, td)
        if os.path.isdir(candidate):
            search_dirs.append(candidate)

    # If no dedicated test dir, scan whole repo for test files
    if not search_dirs:
        search_dirs = [repo_path]

    pattern = re.compile(rf'\b{re.escape(symbol_name)}\b', re.IGNORECASE)
    test_extensions = {'.cs', '.java', '.ts', '.tsx', '.js', '.spec.ts', '.test.ts'}
    test_name_markers = {'test', 'spec', 'fixture', 'mock', 'stub', 'fake'}

    for search_dir in search_dirs:
        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', 'bin', 'obj'}]
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext not in test_extensions:
                    continue
                name_lower = fname.lower()
                if not any(m in name_lower for m in test_name_markers):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = Path(fpath).read_text(encoding='utf-8', errors='ignore')
                    if pattern.search(content):
                        return True
                except Exception:
                    continue
    return False


def score_symbol(
    symbol_name: str,
    symbol_file: str,
    direct_caller_count: int,
    indirect_caller_count: int,
    depth: int,
    has_coverage: bool,
    repo_path: str = ".",
) -> RiskScore:
    """
    Compute a risk score for a single changed symbol.
    """
    reasons = []
    base = 0

    # Fan-out: more direct callers = higher blast
    fan_out = min(direct_caller_count * 8, 40)
    base += fan_out
    if direct_caller_count > 0:
        reasons.append(f"{direct_caller_count} direct caller{'s' if direct_caller_count != 1 else ''}")

    # Indirect reach
    indirect = min(indirect_caller_count * 3, 20)
    base += indirect
    if indirect_caller_count > 0:
        reasons.append(f"{indirect_caller_count} indirect caller{'s' if indirect_caller_count != 1 else ''}")

    # Depth penalty (deeper = harder to trace)
    depth_penalty = min(depth * 5, 15)
    base += depth_penalty

    # Critical path bonus
    is_critical, crit_reason = is_critical_path_file(symbol_file)
    if is_critical:
        base += CRITICAL_PATH_BONUS
        reasons.append(crit_reason)

    # Coverage multiplier
    if not has_coverage:
        base = int(base * MISSING_COVERAGE_MULTIPLIER)
        reasons.append("no test coverage")
    else:
        reasons.append("has test coverage")

    return RiskScore.from_value(base, reasons)


def score_caller(
    caller_file: str,
    is_test_file: bool,
    has_coverage: bool,
    depth: int,
) -> RiskScore:
    """Score a caller node (not the root changed symbol)."""
    reasons = []
    base = 10  # baseline for being a caller at all

    if depth == 1:
        base += 15  # direct callers matter more
        reasons.append("direct caller")
    else:
        base += 5
        reasons.append(f"depth-{depth} caller")

    is_critical, crit_reason = is_critical_path_file(caller_file)
    if is_critical:
        base += 20
        reasons.append(crit_reason)

    if is_test_file:
        base = 5
        reasons = ["test file — impact expected"]
    elif not has_coverage:
        base = int(base * MISSING_COVERAGE_MULTIPLIER)
        reasons.append("no test coverage")

    return RiskScore.from_value(base, reasons)


def summarize_risk(scores: list[RiskScore]) -> dict:
    return {
        'critical': sum(1 for s in scores if s.label == 'critical'),
        'high':     sum(1 for s in scores if s.label == 'high'),
        'medium':   sum(1 for s in scores if s.label == 'medium'),
        'low':      sum(1 for s in scores if s.label == 'low'),
        'max':      max((s.value for s in scores), default=0),
        'avg':      int(sum(s.value for s in scores) / len(scores)) if scores else 0,
    }
