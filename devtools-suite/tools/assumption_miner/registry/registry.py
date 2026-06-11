"""
Assumption Registry.
Persists all known assumptions to .assumptions.json in the repo root.
On each scan, diffs against the registry to find:
  1. New assumptions (add to registry)
  2. Assumptions that disappeared (symbol deleted — risk resolved or hidden)
  3. Contradictions: new code that violates an existing assumption
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from core.models import Assumption, AssumptionKind, RiskLevel, CodeLocation, ContradictionAlert, ScanResult


REGISTRY_FILENAME = ".assumptions.json"


class AssumptionRegistry:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self.registry_path = os.path.join(repo_path, REGISTRY_FILENAME)
        self._assumptions: dict[str, Assumption] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.registry_path):
            try:
                raw = json.loads(Path(self.registry_path).read_text())
                for item in raw.get("assumptions", []):
                    a = Assumption.from_dict(item)
                    self._assumptions[a.id] = a
            except Exception as e:
                print(f"Warning: could not load registry: {e}")

    def save(self):
        data = {
            "version": "1.0",
            "generated": datetime.utcnow().isoformat(),
            "total": len(self._assumptions),
            "assumptions": [a.to_dict() for a in self._assumptions.values()]
        }
        Path(self.registry_path).write_text(json.dumps(data, indent=2))
        print(f"Registry saved: {len(self._assumptions)} assumptions → {self.registry_path}")

    def all(self) -> list[Assumption]:
        return list(self._assumptions.values())

    def get(self, assumption_id: str) -> Assumption | None:
        return self._assumptions.get(assumption_id)

    def upsert(self, assumption: Assumption):
        if assumption.id in self._assumptions:
            # preserve introduced_in
            existing = self._assumptions[assumption.id]
            assumption.introduced_in = existing.introduced_in
        self._assumptions[assumption.id] = assumption

    def merge_scan(self, new_assumptions: list[Assumption], current_git_sha: str = "") -> dict:
        """
        Merge a fresh scan into the registry.
        Returns stats: added, removed, unchanged.
        """
        new_ids = {a.id for a in new_assumptions}
        existing_ids = set(self._assumptions.keys())

        added = new_ids - existing_ids
        removed = existing_ids - new_ids
        unchanged = new_ids & existing_ids

        for a in new_assumptions:
            if a.id in added:
                a.introduced_in = current_git_sha
            self.upsert(a)

        # Mark removed ones (don't delete — they may be hiding)
        for rid in removed:
            self._assumptions[rid].risk = RiskLevel.LOW  # resolved or hidden

        return {"added": len(added), "removed": len(removed), "unchanged": len(unchanged)}


# ── Contradiction detector ─────────────────────────────────────────────────────

def find_contradictions(
    registry: AssumptionRegistry,
    changed_files: list[str],
    repo_path: str = "."
) -> list[ContradictionAlert]:
    """
    For each assumption in the registry, check if any of the changed files
    contain code that directly contradicts it.
    """
    alerts = []

    for assumption in registry.all():
        if assumption.risk == RiskLevel.LOW:
            continue

        for filepath in changed_files:
            full_path = os.path.join(repo_path, filepath)
            if not os.path.exists(full_path):
                continue

            try:
                lines = Path(full_path).read_text(encoding='utf-8', errors='ignore').split('\n')
            except Exception:
                continue

            contradiction = _check_contradiction(assumption, lines, filepath)
            if contradiction:
                alerts.append(ContradictionAlert(
                    assumption=assumption,
                    contradiction_file=filepath,
                    contradiction_line=contradiction[0],
                    contradiction_snippet=contradiction[1],
                    severity="critical" if assumption.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL} else "high"
                ))

    return alerts


def _check_contradiction(assumption: Assumption, lines: list[str], filepath: str):
    """
    Returns (line_number, snippet) if a contradiction is found, else None.
    Rules by assumption kind:
    """
    symbol = re.escape(assumption.symbol)

    if assumption.kind == AssumptionKind.NULL_SAFETY:
        # Contradiction: same symbol is assigned null OR returned as nullable
        patterns = [
            re.compile(rf'{symbol}\s*=\s*null\b'),
            re.compile(rf'return\s+null\b.*{symbol}|{symbol}.*return\s+null'),
            re.compile(rf'Optional\.empty\(\).*{symbol}|{symbol}.*Optional\.empty'),
            re.compile(rf'{symbol}\s*\?\s*\.'),   # TS optional chaining = could be null
        ]
        for i, line in enumerate(lines, 1):
            for pat in patterns:
                if pat.search(line):
                    return (i, line.strip())

    elif assumption.kind == AssumptionKind.NON_EMPTY:
        # Contradiction: same collection can be empty / cleared
        patterns = [
            re.compile(rf'{symbol}\s*=\s*\[\s*\]'),
            re.compile(rf'{symbol}\s*=\s*new\s+(?:List|ArrayList|Array)\s*[(<]'),
            re.compile(rf'{symbol}\.clear\(\)'),
            re.compile(rf'{symbol}\.removeAll\('),
        ]
        for i, line in enumerate(lines, 1):
            for pat in patterns:
                if pat.search(line):
                    return (i, line.strip())

    elif assumption.kind == AssumptionKind.RANGE:
        # Contradiction: same symbol can receive out-of-range value
        patterns = [
            re.compile(rf'{symbol}\s*=\s*-\d+'),
            re.compile(rf'{symbol}\s*=\s*int\.MinValue'),
            re.compile(rf'{symbol}\s*=\s*Integer\.MIN_VALUE'),
            re.compile(rf'{symbol}\s*-=\s*\d+'),
        ]
        for i, line in enumerate(lines, 1):
            for pat in patterns:
                if pat.search(line):
                    return (i, line.strip())

    elif assumption.kind == AssumptionKind.TYPE_NARROWING:
        # Contradiction: new subclass or interface implementation
        patterns = [
            re.compile(rf'class\s+\w+\s+(?:extends|implements)\s+{symbol}'),
            re.compile(rf'{symbol}\s*=\s*new\s+\w+(?!\s*{symbol})'),
        ]
        for i, line in enumerate(lines, 1):
            for pat in patterns:
                if pat.search(line):
                    return (i, line.strip())

    elif assumption.kind == AssumptionKind.ENVIRONMENT:
        # Contradiction: different timezone, locale, or env var value
        if 'DateTime' in assumption.statement or 'timezone' in assumption.statement.lower():
            for i, line in enumerate(lines, 1):
                if re.search(r'UtcNow|UTC|Utc|ZonedDateTime|ZoneOffset\.UTC', line):
                    return (i, line.strip())

    return None


# ── Risk scorer ────────────────────────────────────────────────────────────────

def compute_risk(assumption: Assumption, repo_path: str = ".") -> RiskLevel:
    """
    Re-score risk after scan. Factors:
    - Has a test → LOW
    - In a critical path file (controller, service, gateway) → bump up
    - Confidence > 0.9 (explicit comment) → HIGH minimum
    - Has contradiction → CRITICAL
    """
    if assumption.contradicted_by:
        return RiskLevel.CRITICAL

    if assumption.has_test:
        return RiskLevel.LOW

    if assumption.confidence >= 0.9:
        return RiskLevel.HIGH

    critical_path_indicators = [
        'Controller', 'Gateway', 'Service', 'Repository',
        'Handler', 'Middleware', 'Interceptor', 'Guard'
    ]
    if any(ind in assumption.location.file for ind in critical_path_indicators):
        return RiskLevel.HIGH

    return RiskLevel.MEDIUM
