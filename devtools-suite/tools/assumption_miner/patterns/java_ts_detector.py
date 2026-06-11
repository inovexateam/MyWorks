"""
Java and Angular/TypeScript assumption detectors.
Same detection philosophy as csharp_detector.py, language-specific patterns.
"""

import re
from pathlib import Path
from core.models import Assumption, AssumptionKind, RiskLevel, CodeLocation


# ════════════════════════════════════════════════════════════════
# JAVA DETECTORS
# ════════════════════════════════════════════════════════════════

JAVA_NULL_PATTERNS = [
    re.compile(r'Objects\.requireNonNull\s*\(\s*(\w[\w.]*)'),
    re.compile(r'if\s*\(\s*(\w[\w.]*)\s*==\s*null\s*\)'),
    re.compile(r'@NonNull\s+\w+\s+(\w+)'),
    re.compile(r'@NotNull\s+\w+\s+(\w+)'),
    re.compile(r'assert\s+(\w[\w.]*)\s*!=\s*null'),
    re.compile(r'Optional\.of\s*\(\s*(\w[\w.]*)'),   # of() throws on null, unlike ofNullable
]

JAVA_NON_EMPTY = [
    re.compile(r'(\w[\w.]*)\s*\.get\s*\(\s*0\s*\)'),
    re.compile(r'(\w[\w.]*)\s*\.iterator\s*\(\s*\)\s*\.next\s*\(\)'),
    re.compile(r'(\w[\w.]*)\s*\.getFirst\s*\(\)'),
]

JAVA_RANGE = [
    re.compile(r'if\s*\(\s*(\w[\w.]*)\s*<\s*0\s*\)'),
    re.compile(r'if\s*\(\s*(\w[\w.]*)\s*>\s*(\d+)\s*\)'),
    re.compile(r'Math\.min\s*\(\s*(\w[\w.]*)\s*,\s*(\d+)'),
    re.compile(r'Math\.max\s*\(\s*(\w[\w.]*)\s*,\s*(\d+)'),
    re.compile(r'(\w[\w.]*)\s*%\s*(\d+)'),
]

JAVA_ORDERING = [
    re.compile(r'if\s*\(\s*!?\s*initialized\s*\)'),
    re.compile(r'throw new IllegalStateException'),
    re.compile(r'//\s*(must.*call|call.*first|requires.*init)', re.I),
    re.compile(r'@PostConstruct'),
    re.compile(r'@PreDestroy'),
]

JAVA_COMMENT = [
    re.compile(r'//\s*(assume[sd]?\s+.{5,80})', re.I),
    re.compile(r'//\s*(always\s+.{5,60})', re.I),
    re.compile(r'//\s*(never\s+.{5,60})', re.I),
    re.compile(r'//\s*(invariant\s*:\s*.{5,60})', re.I),
    re.compile(r'//\s*(pre-?condition\s*:\s*.{5,60})', re.I),
    re.compile(r'\*\s+(assumes?|invariant|precondition)\s*:\s*(.{5,80})', re.I),
]

JAVA_ENV = [
    re.compile(r'System\.getenv\("([^"]+)"\)'),
    re.compile(r'System\.getProperty\("([^"]+)"\)'),
    re.compile(r'new Date\(\)'),            # local timezone assumption
    re.compile(r'LocalDateTime\.now\(\)'),  # vs ZonedDateTime
    re.compile(r'TimeZone\.getDefault\(\)'),
    re.compile(r'Locale\.getDefault\(\)'),
]


def scan_java_file(filepath: str) -> list[Assumption]:
    try:
        lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    except Exception:
        return []

    assumptions = []
    rel = filepath

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        in_comment = stripped.startswith('//') or stripped.startswith('*')

        # Null
        if not in_comment:
            for pat in JAVA_NULL_PATTERNS:
                m = pat.search(line)
                if m:
                    symbol = m.group(1) if m.lastindex else "param"
                    assumptions.append(Assumption(
                        statement=f"'{symbol}' assumed non-null",
                        location=CodeLocation(file=rel, line=i, snippet=stripped),
                        kind=AssumptionKind.NULL_SAFETY,
                        symbol=symbol, confidence=0.85))
                    break

        # Non-empty
        if not in_comment:
            for pat in JAVA_NON_EMPTY:
                m = pat.search(line)
                if m:
                    symbol = m.group(1)
                    context = ' '.join(lines[max(0, i-4):i-1])
                    if not re.search(r'isEmpty\(\)|\.size\(\)\s*[>!]|hasNext\(\)', context):
                        assumptions.append(Assumption(
                            statement=f"'{symbol}' assumed non-empty before direct access",
                            location=CodeLocation(file=rel, line=i, snippet=stripped),
                            kind=AssumptionKind.NON_EMPTY,
                            symbol=symbol, confidence=0.75))
                    break

        # Range
        if not in_comment:
            for pat in JAVA_RANGE:
                m = pat.search(line)
                if m:
                    symbol = m.group(1)
                    bound = m.group(2) if m.lastindex >= 2 else "N"
                    assumptions.append(Assumption(
                        statement=f"'{symbol}' assumed within range (bound: {bound})",
                        location=CodeLocation(file=rel, line=i, snippet=stripped),
                        kind=AssumptionKind.RANGE,
                        symbol=symbol, confidence=0.70))
                    break

        # Ordering
        for pat in JAVA_ORDERING:
            if pat.search(line):
                sym_m = re.search(r'\b([a-z]\w+)\b', line)
                symbol = sym_m.group(1) if sym_m else "component"
                assumptions.append(Assumption(
                    statement=f"Assumes specific initialization ordering for '{symbol}'",
                    location=CodeLocation(file=rel, line=i, snippet=stripped),
                    kind=AssumptionKind.ORDERING,
                    symbol=symbol, confidence=0.72))
                break

        # Comments
        for pat in JAVA_COMMENT:
            m = pat.search(line)
            if m:
                stmt = (m.group(1) or m.group(2)).strip()
                assumptions.append(Assumption(
                    statement=stmt,
                    location=CodeLocation(file=rel, line=i, snippet=stripped),
                    kind=AssumptionKind.COMMENT_EXPLICIT,
                    symbol="explicit", confidence=0.95,
                    risk=RiskLevel.HIGH))
                break

        # Environment
        if not in_comment:
            for pat in JAVA_ENV:
                m = pat.search(line)
                if m:
                    val = m.group(1) if m.lastindex else "env"
                    stmt = (f"Assumes env var '{val}' is set"
                            if 'getenv' in line or 'getProperty' in line
                            else f"Assumes local timezone/locale is correct")
                    assumptions.append(Assumption(
                        statement=stmt,
                        location=CodeLocation(file=rel, line=i, snippet=stripped),
                        kind=AssumptionKind.ENVIRONMENT,
                        symbol=val, confidence=0.78))
                    break

    # Deduplicate
    seen, unique = set(), []
    for a in assumptions:
        key = (a.location.line, a.kind)
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


# ════════════════════════════════════════════════════════════════
# ANGULAR / TYPESCRIPT DETECTORS
# ════════════════════════════════════════════════════════════════

TS_NULL_PATTERNS = [
    re.compile(r'(\w[\w.]*)\s*!\s*\.'),              # non-null assertion: x!.y
    re.compile(r'(\w[\w.]*)\s*!\s*\['),              # x![i]
    re.compile(r'if\s*\(\s*!?\s*(\w[\w.]*)\s*\)'),  # if (!x) or if (x)
    re.compile(r'(\w[\w.]*)\s*\?\?'),                # nullish coalescing implies nullable
    re.compile(r'throw new Error.*null|undefined'),
]

TS_NON_EMPTY = [
    re.compile(r'(\w[\w.]*)\[0\]'),
    re.compile(r'(\w[\w.]*)\s*\.\s*find\s*\('),         # .find() can return undefined
    re.compile(r'(\w[\w.]*)\s*\.\s*shift\s*\(\)'),
]

TS_COMMENT = [
    re.compile(r'//\s*(assume[sd]?\s+.{5,80})', re.I),
    re.compile(r'//\s*(always\s+.{5,60})', re.I),
    re.compile(r'//\s*(never\s+.{5,60})', re.I),
    re.compile(r'//\s*(TODO.*assume|FIXME.*assume)', re.I),
    re.compile(r'//\s*(invariant\s*:\s*.{5,60})', re.I),
]

TS_ENV = [
    re.compile(r'environment\.(production|apiUrl|[\w]+)'),   # Angular environment file
    re.compile(r'process\.env\.(\w+)'),
    re.compile(r'localStorage\.getItem\("([^"]+)"\)'),
    re.compile(r'new Date\(\)'),
    re.compile(r'Intl\.DateTimeFormat\(\)\.resolvedOptions\(\)\.timeZone'),
]

TS_TYPE_NARROWING = [
    re.compile(r'(<([A-Z]\w+)>)\s*(\w[\w.]*)'),             # <Type>variable
    re.compile(r'(\w[\w.]*)\s+as\s+([A-Z]\w+)'),
    re.compile(r'(\w[\w.]*)\s+instanceof\s+([A-Z]\w+)'),
]

TS_SUBSCRIPTION = [
    # subscribe() without takeUntil or take() is an assumption the component lives forever
    re.compile(r'\.subscribe\s*\('),
]


def scan_typescript_file(filepath: str) -> list[Assumption]:
    try:
        lines = Path(filepath).read_text(encoding='utf-8', errors='ignore').split('\n')
    except Exception:
        return []

    assumptions = []
    rel = filepath

    has_take_until = any('takeUntil' in l or 'take(' in l or 'takeWhile' in l for l in lines)

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        in_comment = stripped.startswith('//')

        # Null assertions
        if not in_comment:
            for pat in TS_NULL_PATTERNS:
                m = pat.search(line)
                if m:
                    symbol = m.group(1) if m.lastindex else "value"
                    if symbol in {'true', 'false', 'null', 'undefined', 'this'}:
                        continue
                    assumptions.append(Assumption(
                        statement=f"'{symbol}' assumed to be defined/non-null",
                        location=CodeLocation(file=rel, line=i, snippet=stripped),
                        kind=AssumptionKind.NULL_SAFETY,
                        symbol=symbol, confidence=0.82))
                    break

        # Non-empty
        if not in_comment:
            context = ' '.join(lines[max(0, i-3):i-1])
            for pat in TS_NON_EMPTY:
                m = pat.search(line)
                if m and not re.search(r'\.length\s*[>!]|Array\.isArray', context):
                    symbol = m.group(1)
                    assumptions.append(Assumption(
                        statement=f"'{symbol}' assumed non-empty before index/find access",
                        location=CodeLocation(file=rel, line=i, snippet=stripped),
                        kind=AssumptionKind.NON_EMPTY,
                        symbol=symbol, confidence=0.72))
                    break

        # Subscriptions without teardown
        if not in_comment and TS_SUBSCRIPTION[0].search(line) and not has_take_until:
            assumptions.append(Assumption(
                statement="Observable subscription has no takeUntil — assumes component lives forever",
                location=CodeLocation(file=rel, line=i, snippet=stripped),
                kind=AssumptionKind.ORDERING,
                symbol="subscription", confidence=0.80,
                risk=RiskLevel.HIGH))

        # Comments
        for pat in TS_COMMENT:
            m = pat.search(line)
            if m:
                assumptions.append(Assumption(
                    statement=m.group(1).strip(),
                    location=CodeLocation(file=rel, line=i, snippet=stripped),
                    kind=AssumptionKind.COMMENT_EXPLICIT,
                    symbol="explicit", confidence=0.95,
                    risk=RiskLevel.HIGH))
                break

        # Environment
        if not in_comment:
            for pat in TS_ENV:
                m = pat.search(line)
                if m:
                    val = m.group(1) if m.lastindex else "env"
                    assumptions.append(Assumption(
                        statement=f"Assumes environment config '{val}' is correctly set",
                        location=CodeLocation(file=rel, line=i, snippet=stripped),
                        kind=AssumptionKind.ENVIRONMENT,
                        symbol=val, confidence=0.75))
                    break

        # Type narrowing
        if not in_comment:
            for pat in TS_TYPE_NARROWING:
                m = pat.search(line)
                if m:
                    type_name = m.group(2) if m.lastindex >= 2 else m.group(1)
                    symbol = m.group(1)
                    if type_name.lower() in {'string', 'number', 'boolean', 'any', 'unknown'}:
                        continue
                    assumptions.append(Assumption(
                        statement=f"'{symbol}' cast/narrowed to '{type_name}' — assumes runtime type matches",
                        location=CodeLocation(file=rel, line=i, snippet=stripped),
                        kind=AssumptionKind.TYPE_NARROWING,
                        symbol=symbol, confidence=0.78))
                    break

    seen, unique = set(), []
    for a in assumptions:
        key = (a.location.line, a.kind)
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique
