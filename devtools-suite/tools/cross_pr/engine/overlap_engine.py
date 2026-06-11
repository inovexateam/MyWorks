"""
Overlap engine — the core of Cross-PR Intelligence.

Three detectors, each catching a different kind of cross-PR dependency:

1. LINE COLLISION  — two PRs edit the exact same line ranges in the same file.
   Guaranteed merge conflict. Severity: CRITICAL.

2. SYMBOL CONFLICT — two PRs modify the same named symbol (method, class, function).
   Not necessarily a line conflict (e.g. both added lines in the same method),
   but semantically guaranteed to need coordination.
   Severity: HIGH.

3. SEMANTIC DEP    — PR A adds a call to a function that PR B is simultaneously
   changing. If B renames/removes/restructures that function, A breaks.
   This is the one nobody else detects.
   Severity: HIGH.

4. SHARED FILE     — both PRs touch the same file, without any deeper conflict.
   Low confidence — may be intentional or harmless.
   Severity: LOW.
"""

from core.models import (
    PRSnapshot, Overlap, OverlapKind, Severity,
    ConflictReport, SymbolChange, FileChange
)
from extractor.symbol_extractor import extract_imports_from_diff


# ── Line collision detector ────────────────────────────────────────────────────

def _ranges_overlap(a: list[tuple[int,int]], b: list[tuple[int,int]]) -> list[tuple[int,int]]:
    """Return list of (start, end) overlapping intervals between two sorted range lists."""
    overlaps = []
    for (a_start, a_end) in a:
        for (b_start, b_end) in b:
            lo = max(a_start, b_start)
            hi = min(a_end, b_end)
            if lo <= hi:
                overlaps.append((lo, hi))
    return overlaps


def detect_line_collisions(prs: list[PRSnapshot]) -> list[Overlap]:
    """
    For every pair of PRs, find files where both PRs changed the same line ranges.
    These are guaranteed merge conflicts.
    """
    overlaps = []

    for i, pr_a in enumerate(prs):
        for pr_b in prs[i + 1:]:
            # Build file → changed_lines maps
            files_a = {f.path: f for f in pr_a.changed_files}
            files_b = {f.path: f for f in pr_b.changed_files}

            shared_files = set(files_a.keys()) & set(files_b.keys())

            for filepath in shared_files:
                file_a = files_a[filepath]
                file_b = files_b[filepath]

                if not file_a.changed_lines or not file_b.changed_lines:
                    continue

                colliding = _ranges_overlap(file_a.changed_lines, file_b.changed_lines)
                if not colliding:
                    continue

                ranges_str = ", ".join(f"L{s}-{e}" for s, e in colliding[:3])
                overlaps.append(Overlap(
                    pr_a=pr_a.number,
                    pr_b=pr_b.number,
                    kind=OverlapKind.LINE_COLLISION,
                    severity=Severity.CRITICAL,
                    description=(
                        f"Both PRs edit the same lines ({ranges_str}) in `{filepath}`. "
                        f"This will produce a merge conflict."
                    ),
                    file=filepath,
                    line_range_a=colliding[0],
                    line_range_b=colliding[0],
                    merge_order_matters=True,
                ))

    return overlaps


# ── Symbol conflict detector ───────────────────────────────────────────────────

def detect_symbol_conflicts(prs: list[PRSnapshot]) -> list[Overlap]:
    """
    For every pair of PRs, find symbols that both PRs modify.
    Both PRs changing OrderService.ProcessPayment() is a conflict even if
    they happen to touch different line numbers within it.
    """
    overlaps = []

    for i, pr_a in enumerate(prs):
        for pr_b in prs[i + 1:]:
            # Build symbol name → SymbolChange maps (keyed by name + file)
            syms_a = {(s.name, s.file): s for s in pr_a.symbols}
            syms_b = {(s.name, s.file): s for s in pr_b.symbols}

            shared = set(syms_a.keys()) & set(syms_b.keys())

            for key in shared:
                sym_a = syms_a[key]
                sym_b = syms_b[key]
                name, filepath = key

                # Determine severity: both modifying = HIGH, one deleting = CRITICAL
                sev = Severity.CRITICAL if (
                    sym_a.change_type == 'deleted' or sym_b.change_type == 'deleted'
                ) else Severity.HIGH

                overlaps.append(Overlap(
                    pr_a=pr_a.number,
                    pr_b=pr_b.number,
                    kind=OverlapKind.SYMBOL_CONFLICT,
                    severity=sev,
                    description=(
                        f"Both PRs modify `{name}` ({sym_a.kind}) in `{filepath}`. "
                        f"PR #{pr_a.number} marks it as '{sym_a.change_type}', "
                        f"PR #{pr_b.number} as '{sym_b.change_type}'."
                    ),
                    file=filepath,
                    symbol=name,
                    merge_order_matters=sev == Severity.CRITICAL,
                ))

    return overlaps


# ── Semantic dependency detector ───────────────────────────────────────────────

def detect_semantic_deps(prs: list[PRSnapshot]) -> list[Overlap]:
    """
    The most sophisticated detector.

    For each PR B that changes a symbol X, check if any other PR A
    adds a *call* to X (i.e. PR A references the symbol name in its diff).

    If PR B renames, removes, or substantially changes X,
    PR A will silently break unless they're coordinated.
    """
    overlaps = []

    for pr_b in prs:
        # Symbols that PR B changes
        if not pr_b.symbols:
            continue

        changed_symbol_names = {s.name for s in pr_b.symbols}

        for pr_a in prs:
            if pr_a.number == pr_b.number:
                continue

            # Look in PR A's diff for references to the symbols PR B changes
            for sym_b in pr_b.symbols:
                if sym_b.change_type not in ('modified', 'deleted'):
                    continue

                # Check if PR A's diff contains the symbol name as a usage
                # (not just a definition — we look for call patterns)
                if _pr_references_symbol(pr_a, sym_b):
                    # Avoid duplicate with already-found symbol conflicts
                    already_flagged = any(
                        o.pr_a in {pr_a.number, pr_b.number} and
                        o.pr_b in {pr_a.number, pr_b.number} and
                        o.symbol == sym_b.name and
                        o.kind == OverlapKind.SYMBOL_CONFLICT
                        for o in overlaps
                    )
                    if already_flagged:
                        continue

                    sev = Severity.CRITICAL if sym_b.change_type == 'deleted' else Severity.HIGH
                    overlaps.append(Overlap(
                        pr_a=pr_a.number,
                        pr_b=pr_b.number,
                        kind=OverlapKind.SEMANTIC_DEP,
                        severity=sev,
                        description=(
                            f"PR #{pr_a.number} calls `{sym_b.name}` "
                            f"which PR #{pr_b.number} is "
                            f"{'deleting' if sym_b.change_type == 'deleted' else 'changing'}. "
                            f"Merging out of order may break PR #{pr_a.number}."
                        ),
                        file=sym_b.file,
                        symbol=sym_b.name,
                        merge_order_matters=True,
                    ))

    return overlaps


def _pr_references_symbol(pr: PRSnapshot, sym: SymbolChange) -> bool:
    """
    Check whether a PR's diff contains a usage (not definition) of a symbol.
    We look for: name( or .name or new Name or <Name> patterns in added lines.
    """
    if not pr.raw_diff:
        return False

    patterns = [
        f"{sym.name}(",          # method call
        f".{sym.name}",          # member access
        f"new {sym.name}",       # instantiation
        f": {sym.name}",         # type annotation
        f"<{sym.name}>",         # generic
        f"inject({sym.name})",   # Angular DI
    ]

    for line in pr.raw_diff.split('\n'):
        if not line.startswith('+') or line.startswith('+++'):
            continue
        for pat in patterns:
            if pat in line:
                # Make sure it's not a definition line in the PR itself
                if sym.name in {s.name for s in pr.symbols}:
                    continue
                return True
    return False


# ── Shared file detector (low confidence) ─────────────────────────────────────

def detect_shared_files(prs: list[PRSnapshot], existing_overlaps: list[Overlap]) -> list[Overlap]:
    """
    Detect PRs that share files but don't have deeper conflicts.
    Excluded: files already covered by higher-severity overlaps.
    """
    already_covered = {(min(o.pr_a, o.pr_b), max(o.pr_a, o.pr_b), o.file)
                       for o in existing_overlaps}

    overlaps = []
    for i, pr_a in enumerate(prs):
        for pr_b in prs[i + 1:]:
            shared = pr_a.file_paths() & pr_b.file_paths()
            for filepath in shared:
                key = (min(pr_a.number, pr_b.number), max(pr_a.number, pr_b.number), filepath)
                if key in already_covered:
                    continue
                overlaps.append(Overlap(
                    pr_a=pr_a.number,
                    pr_b=pr_b.number,
                    kind=OverlapKind.SHARED_FILE,
                    severity=Severity.LOW,
                    description=(
                        f"Both PRs touch `{filepath}` but no deeper conflict detected. "
                        f"May still need coordination."
                    ),
                    file=filepath,
                ))
    return overlaps


# ── Main orchestrator ──────────────────────────────────────────────────────────

def analyze_all(prs: list[PRSnapshot]) -> list[Overlap]:
    """
    Run all detectors in priority order.
    Returns deduplicated list of overlaps sorted by severity.
    """
    all_overlaps: list[Overlap] = []

    all_overlaps += detect_line_collisions(prs)
    all_overlaps += detect_symbol_conflicts(prs)
    all_overlaps += detect_semantic_deps(prs)
    all_overlaps += detect_shared_files(prs, all_overlaps)

    # Deduplicate by stable ID
    seen = set()
    unique = []
    for o in all_overlaps:
        if o.id not in seen:
            seen.add(o.id)
            unique.append(o)

    # Sort: critical first
    order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
    unique.sort(key=lambda o: order.index(o.severity))

    return unique


def build_conflict_reports(prs: list[PRSnapshot], overlaps: list[Overlap]) -> dict[int, ConflictReport]:
    """
    For each PR, build a ConflictReport with all overlaps that involve it.
    """
    reports: dict[int, ConflictReport] = {}
    pr_map = {pr.number: pr for pr in prs}

    for pr in prs:
        my_overlaps = [o for o in overlaps if pr.number in (o.pr_a, o.pr_b)]
        affected = list({o.pr_b if o.pr_a == pr.number else o.pr_a for o in my_overlaps})

        sev_summary = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for o in my_overlaps:
            sev_summary[o.severity.value] += 1

        # Generate recommendation
        if sev_summary['critical'] > 0:
            rec = (
                f"**Action required before merging.** This PR has {sev_summary['critical']} "
                f"critical conflict(s) — guaranteed merge conflicts. "
                f"Coordinate with PR #{', #'.join(str(n) for n in affected)} before merging."
            )
        elif sev_summary['high'] > 0:
            rec = (
                f"**Review before merging.** This PR has semantic dependencies on "
                f"{sev_summary['high']} other PR(s). Agree on merge order with "
                f"PR #{', #'.join(str(n) for n in affected)}."
            )
        elif my_overlaps:
            rec = (
                f"Low-risk overlap with PR #{', #'.join(str(n) for n in affected)}. "
                f"Notify the authors but merging in any order should be safe."
            )
        else:
            rec = "No conflicts detected. Safe to merge independently."

        reports[pr.number] = ConflictReport(
            pr=pr,
            overlaps=my_overlaps,
            affected_prs=affected,
            severity_summary=sev_summary,
            recommendation=rec,
        )

    return reports
