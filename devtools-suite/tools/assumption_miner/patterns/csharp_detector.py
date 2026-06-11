"""
C# assumption pattern detectors.
Uses regex on raw source lines (fast) + Roslyn-style heuristics where needed.
Each detector returns a list of Assumption objects for a single file.
"""

import re
from pathlib import Path
from core.models import Assumption, AssumptionKind, RiskLevel, CodeLocation


# ── Null safety ────────────────────────────────────────────────────────────────

NULL_GUARD_PATTERNS = [
    # if (x == null) throw / return / continue
    re.compile(r'if\s*\(\s*(\w[\w.]*)\s*==\s*null\s*\)'),
    re.compile(r'if\s*\(\s*null\s*==\s*(\w[\w.]*)\s*\)'),
    # ArgumentNullException
    re.compile(r'ArgumentNullException.*?nameof\((\w+)\)'),
    re.compile(r'throw new ArgumentNullException\s*\(\s*"(\w+)"'),
    # null-forgiving operator: x!
    re.compile(r'(\w[\w.]*)\s*!\.'),
    # C# null coalescing with throw: x ?? throw
    re.compile(r'(\w[\w.]*)\s*\?\?\s*throw'),
    # Debug.Assert(x != null)
    re.compile(r'Debug\.Assert\s*\(\s*(\w[\w.]*)\s*!=\s*null'),
    # Contract.Requires(x != null)
    re.compile(r'Contract\.Requires\s*\(\s*(\w[\w.]*)\s*!=\s*null'),
]

def detect_null_assumptions(lines: list[str], filepath: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('*'):
            continue
        for pat in NULL_GUARD_PATTERNS:
            m = pat.search(line)
            if m:
                symbol = m.group(1) if m.lastindex else "unknown"
                assumptions.append(Assumption(
                    statement=f"'{symbol}' is assumed to never be null here",
                    location=CodeLocation(file=filepath, line=i, snippet=stripped),
                    kind=AssumptionKind.NULL_SAFETY,
                    symbol=symbol,
                    confidence=0.85,
                ))
                break
    return assumptions


# ── Non-empty collection ───────────────────────────────────────────────────────

NON_EMPTY_PATTERNS = [
    # .First() without .Any() check before it
    re.compile(r'(\w[\w.]*)\s*\.\s*First\(\)'),
    re.compile(r'(\w[\w.]*)\s*\.\s*Single\(\)'),
    re.compile(r'(\w[\w.]*)\s*\[0\]'),
    re.compile(r'(\w[\w.]*)\s*\.Last\(\)'),
]

def detect_non_empty_assumptions(lines: list[str], filepath: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        # Only flag if there is no null/empty guard in the 3 lines above
        context_above = ' '.join(lines[max(0, i-4):i-1])
        has_guard = re.search(r'\.Any\(|\.Count\s*[>!]|\.Length\s*[>!]|if\s*\(.*empty', context_above, re.I)
        for pat in NON_EMPTY_PATTERNS:
            m = pat.search(line)
            if m and not has_guard:
                symbol = m.group(1)
                assumptions.append(Assumption(
                    statement=f"'{symbol}' is assumed to be non-empty (no guard before access)",
                    location=CodeLocation(file=filepath, line=i, snippet=stripped),
                    kind=AssumptionKind.NON_EMPTY,
                    symbol=symbol,
                    confidence=0.75,
                ))
                break
    return assumptions


# ── Range assumptions ──────────────────────────────────────────────────────────

RANGE_PATTERNS = [
    # if (x < 0) throw / return  → assumes x should be >= 0
    re.compile(r'if\s*\(\s*(\w[\w.]*)\s*<\s*0\s*\)'),
    re.compile(r'if\s*\(\s*(\w[\w.]*)\s*>\s*(\d+)\s*\)'),
    re.compile(r'if\s*\(\s*(\w[\w.]*)\s*<=\s*0\s*\)'),
    # Math.Clamp, Math.Min/Max used as implicit range enforcement
    re.compile(r'Math\.Clamp\s*\(\s*(\w[\w.]*)'),
    re.compile(r'Math\.Min\s*\(\s*(\w[\w.]*)\s*,\s*(\d+)'),
    re.compile(r'Math\.Max\s*\(\s*(\w[\w.]*)\s*,\s*(\d+)'),
    # Modulo: x % N implies x could be out of range
    re.compile(r'(\w[\w.]*)\s*%\s*(\d+)'),
]

def detect_range_assumptions(lines: list[str], filepath: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        for pat in RANGE_PATTERNS:
            m = pat.search(line)
            if m:
                symbol = m.group(1)
                bound = m.group(2) if m.lastindex and m.lastindex >= 2 else "bound"
                assumptions.append(Assumption(
                    statement=f"'{symbol}' is assumed to be within a bounded range (checked against {bound})",
                    location=CodeLocation(file=filepath, line=i, snippet=stripped),
                    kind=AssumptionKind.RANGE,
                    symbol=symbol,
                    confidence=0.70,
                ))
                break
    return assumptions


# ── Type narrowing ─────────────────────────────────────────────────────────────

TYPE_CAST_PATTERNS = [
    # (SpecificType)variable
    re.compile(r'\(([A-Z]\w+)\)\s*(\w[\w.]*)'),
    # variable as SpecificType (then used directly without null check)
    re.compile(r'(\w[\w.]*)\s+as\s+([A-Z]\w+)'),
    # is pattern: variable is SpecificType specific
    re.compile(r'(\w[\w.]*)\s+is\s+([A-Z]\w+)\s+(\w+)'),
]

def detect_type_assumptions(lines: list[str], filepath: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('//') or 'is not' in line:
            continue
        for pat in TYPE_CAST_PATTERNS:
            m = pat.search(line)
            if m:
                type_name = m.group(1) if m.lastindex >= 1 else "Type"
                symbol = m.group(2) if m.lastindex >= 2 else "obj"
                # Skip primitive casts (int, string, bool, etc.)
                if type_name.lower() in {'int', 'string', 'bool', 'long', 'double', 'float', 'object', 'var'}:
                    continue
                assumptions.append(Assumption(
                    statement=f"'{symbol}' is assumed to always be of type '{type_name}'",
                    location=CodeLocation(file=filepath, line=i, snippet=stripped),
                    kind=AssumptionKind.TYPE_NARROWING,
                    symbol=symbol,
                    confidence=0.80,
                ))
                break
    return assumptions


# ── Ordering assumptions ───────────────────────────────────────────────────────

ORDERING_INDICATORS = [
    re.compile(r'//\s*(must be called|always called|call.*first|requires.*init|depends on)', re.I),
    re.compile(r'if\s*\(\s*!?\s*_?isInit(?:ialized)?\s*\)'),
    re.compile(r'if\s*\(\s*_?initialized\s*==\s*false\s*\)'),
    re.compile(r'throw new InvalidOperationException'),
    re.compile(r'Debug\.Assert\s*\(\s*_?\w+\s*!=\s*null'),
]

def detect_ordering_assumptions(lines: list[str], filepath: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        for pat in ORDERING_INDICATORS:
            m = pat.search(line)
            if m:
                # Try to find what's being protected
                context = lines[max(0, i-2):i+2]
                symbol_match = re.search(r'(\w[\w.]*)(?:\s*\(|\s*!=\s*null)', ' '.join(context))
                symbol = symbol_match.group(1) if symbol_match else "this"
                assumptions.append(Assumption(
                    statement=f"Assumes a specific initialization or call ordering for '{symbol}'",
                    location=CodeLocation(file=filepath, line=i, snippet=stripped),
                    kind=AssumptionKind.ORDERING,
                    symbol=symbol,
                    confidence=0.72,
                ))
                break
    return assumptions


# ── Explicit comment assumptions ───────────────────────────────────────────────

COMMENT_ASSUMPTION_PATTERNS = [
    re.compile(r'//\s*(assume[sd]?\s+.{5,80})', re.I),
    re.compile(r'//\s*(always\s+.{5,60})', re.I),
    re.compile(r'//\s*(never\s+.{5,60})', re.I),
    re.compile(r'//\s*(guaranteed\s+.{5,60})', re.I),
    re.compile(r'//\s*(must\s+.{5,60})', re.I),
    re.compile(r'//\s*(invariant\s*:\s*.{5,60})', re.I),
    re.compile(r'//\s*(pre-?condition\s*:\s*.{5,60})', re.I),
    re.compile(r'//\s*(TODO.*assume|HACK.*assume)', re.I),
]

def detect_comment_assumptions(lines: list[str], filepath: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines, 1):
        for pat in COMMENT_ASSUMPTION_PATTERNS:
            m = pat.search(line)
            if m:
                statement = m.group(1).strip()
                # Find the symbol on the next non-comment line
                next_lines = [l for l in lines[i:i+3] if not l.strip().startswith('//')]
                sym_match = re.search(r'\b([a-z]\w*)\b', next_lines[0]) if next_lines else None
                symbol = sym_match.group(1) if sym_match else "unknown"
                assumptions.append(Assumption(
                    statement=statement,
                    location=CodeLocation(file=filepath, line=i, snippet=line.strip()),
                    kind=AssumptionKind.COMMENT_EXPLICIT,
                    symbol=symbol,
                    confidence=0.95,  # developer wrote it explicitly
                    risk=RiskLevel.HIGH,  # explicit comment = someone was worried
                ))
                break
    return assumptions


# ── Environment assumptions ────────────────────────────────────────────────────

ENV_PATTERNS = [
    re.compile(r'TimeZoneInfo\.FindSystemTimeZoneById\("([^"]+)"\)'),
    re.compile(r'CultureInfo\("([^"]+)"\)'),
    re.compile(r'Environment\.GetEnvironmentVariable\("([^"]+)"\)'),
    re.compile(r'DateTime\.Now'),      # vs DateTime.UtcNow — timezone assumption
    re.compile(r'Directory\.GetCurrentDirectory\(\)'),
    re.compile(r'\.OSVersion|RuntimeInformation\.IsOSPlatform'),
]

def detect_environment_assumptions(lines: list[str], filepath: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        for pat in ENV_PATTERNS:
            m = pat.search(line)
            if m:
                value = m.group(1) if m.lastindex else "env value"
                symbol = value
                statement = f"Assumes environment/platform: '{value}' is available or set"
                if 'DateTime.Now' in line:
                    statement = "Uses DateTime.Now — assumes local timezone is correct (consider UtcNow)"
                    symbol = "DateTime.Now"
                assumptions.append(Assumption(
                    statement=statement,
                    location=CodeLocation(file=filepath, line=i, snippet=stripped),
                    kind=AssumptionKind.ENVIRONMENT,
                    symbol=symbol,
                    confidence=0.78,
                ))
                break
    return assumptions


# ── Main scanner for one C# file ───────────────────────────────────────────────

def scan_csharp_file(filepath: str) -> list[Assumption]:
    try:
        lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    except Exception:
        return []

    all_assumptions = []
    rel = filepath

    all_assumptions += detect_null_assumptions(lines, rel)
    all_assumptions += detect_non_empty_assumptions(lines, rel)
    all_assumptions += detect_range_assumptions(lines, rel)
    all_assumptions += detect_type_assumptions(lines, rel)
    all_assumptions += detect_ordering_assumptions(lines, rel)
    all_assumptions += detect_comment_assumptions(lines, rel)
    all_assumptions += detect_environment_assumptions(lines, rel)

    # Deduplicate by (line, kind) — same line can't have two of the same kind
    seen = set()
    unique = []
    for a in all_assumptions:
        key = (a.location.line, a.kind)
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique
