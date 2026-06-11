"""
Core data models for the Architectural Drift Detector.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import hashlib


class RuleKind(str, Enum):
    LAYER_DEPENDENCY  = "layer_dependency"
    NAMING            = "naming"
    NO_DEPENDENCY     = "no_dependency"
    NO_CIRCULAR       = "no_circular"
    MAX_COUPLING      = "max_coupling"
    DOMAIN_ISOLATION  = "domain_isolation"


class Severity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    ERROR    = "error"


@dataclass
class Violation:
    rule_kind:    RuleKind
    severity:     Severity
    message:      str
    file:         str
    line:         int
    from_layer:   str
    to_layer:     str
    import_path:  str
    rule_name:    str = ""
    introduced_in: str = ""
    age_commits:  int = 0
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            raw = f"{self.file}:{self.import_path}:{self.rule_kind}"
            self.id = hashlib.sha1(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d['rule_kind'] = self.rule_kind.value
        d['severity']  = self.severity.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Violation':
        d['rule_kind'] = RuleKind(d['rule_kind'])
        d['severity']  = Severity(d['severity'])
        return cls(**d)


@dataclass
class DriftScore:
    commit_sha:    str
    commit_date:   str
    total_violations: int
    errors:        int
    warnings:      int
    infos:         int
    score:         int

    @classmethod
    def from_violations(cls, sha: str, date: str, violations: list) -> 'DriftScore':
        errors   = sum(1 for v in violations if v.severity == Severity.ERROR)
        warnings = sum(1 for v in violations if v.severity == Severity.WARNING)
        infos    = sum(1 for v in violations if v.severity == Severity.INFO)
        score    = min(errors * 10 + warnings * 3 + infos, 100)
        return cls(sha, date, len(violations), errors, warnings, infos, score)


@dataclass
class DriftTimeline:
    repo_path:   str
    rule_file:   str
    snapshots:   list = field(default_factory=list)

    def latest_score(self) -> Optional[DriftScore]:
        return self.snapshots[-1] if self.snapshots else None

    def trend(self) -> str:
        if len(self.snapshots) < 2:
            return 'stable'
        delta = self.snapshots[-1].score - self.snapshots[-2].score
        if delta > 5:  return 'degrading'
        if delta < -5: return 'improving'
        return 'stable'


@dataclass
class ScanResult:
    violations:        list
    new_violations:    list
    resolved:          list
    drift_score:       DriftScore
    files_scanned:     int
    layers_found:      dict
    import_edges:      int
    circular_chains:   list

    def summary(self) -> str:
        return (
            f"Scanned {self.files_scanned} files · "
            f"{len(self.violations)} violations "
            f"({self.drift_score.errors} errors, {self.drift_score.warnings} warnings) · "
            f"score {self.drift_score.score}/100 · "
            f"{len(self.new_violations)} new · {len(self.resolved)} resolved"
        )
