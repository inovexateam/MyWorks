"""
Core data models for the Dead Code Analyzer.

Key design decision: confidence scoring.
A symbol with zero references might still be legitimately live —
through reflection, dependency injection, serialization, or external APIs.
We never just say "this is dead". We say "this looks dead, confidence 87%."
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import hashlib


class SymbolKind(str, Enum):
    CLASS      = "class"
    METHOD     = "method"
    FUNCTION   = "function"
    PROPERTY   = "property"
    FIELD      = "field"
    INTERFACE  = "interface"
    COMPONENT  = "component"    # Angular @Component
    SERVICE    = "service"      # Angular @Injectable
    ENUM       = "enum"
    CONSTANT   = "constant"


class DeadReason(str, Enum):
    NO_REFERENCES     = "no_references"      # zero callers found anywhere
    UNREACHABLE       = "unreachable"        # reachability BFS can't reach it from entry points
    PRIVATE_NO_CALL   = "private_no_call"    # private/internal, not called within own class
    UNUSED_EXPORT     = "unused_export"      # exported but never imported by any other file
    OBSOLETE_BRANCH   = "obsolete_branch"    # only referenced in code that is itself dead
    EMPTY_CATCH       = "empty_catch"        # method body is empty / only throws NotImplemented


class Confidence(str, Enum):
    HIGH   = "high"    # 85–100% — safe to delete
    MEDIUM = "medium"  # 60–84%  — investigate before deleting
    LOW    = "low"     # < 60%   — probably live (reflection, DI, etc.) — leave alone


@dataclass
class SymbolDef:
    """A named code symbol found in the codebase."""
    name:          str
    kind:          SymbolKind
    file:          str
    line:          int
    language:      str
    is_public:     bool = True
    is_static:     bool = False
    is_abstract:   bool = False
    is_override:   bool = False
    is_test:       bool = False
    namespace:     str = ""
    class_name:    str = ""       # containing class, if any
    lines_of_code: int = 0
    has_attribute: bool = False   # has [Attribute] / @Annotation decoration

    # Computed after reference scan
    reference_count: int = 0
    referencing_files: list[str] = field(default_factory=list)

    # Unique stable ID
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            raw = f"{self.file}:{self.line}:{self.name}:{self.kind}"
            self.id = hashlib.sha1(raw.encode()).hexdigest()[:12]

    def fqn(self) -> str:
        """Fully-qualified name for display."""
        parts = []
        if self.namespace:
            parts.append(self.namespace)
        if self.class_name and self.class_name != self.name:
            parts.append(self.class_name)
        parts.append(self.name)
        return ".".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "file": self.file,
            "line": self.line,
            "language": self.language,
            "is_public": self.is_public,
            "namespace": self.namespace,
            "class_name": self.class_name,
            "lines_of_code": self.lines_of_code,
            "reference_count": self.reference_count,
        }


@dataclass
class DeadSymbol:
    """A symbol determined to be dead (or likely dead)."""
    symbol:       SymbolDef
    reason:       DeadReason
    confidence:   Confidence
    confidence_pct: int          # 0–100
    explanation:  str            # human-readable why
    safe_to_delete: bool = False # True only at HIGH confidence
    git_age_days: int = 0        # days since last meaningful change
    suppressions: list[str] = field(default_factory=list)  # reasons NOT to delete

    def to_dict(self) -> dict:
        return {
            **self.symbol.to_dict(),
            "reason": self.reason.value,
            "confidence": self.confidence.value,
            "confidence_pct": self.confidence_pct,
            "explanation": self.explanation,
            "safe_to_delete": self.safe_to_delete,
            "git_age_days": self.git_age_days,
            "suppressions": self.suppressions,
        }


@dataclass
class ScanResult:
    dead_symbols:    list[DeadSymbol]
    files_scanned:   int
    symbols_found:   int
    dead_count:      int
    safe_to_delete:  int
    lines_recoverable: int       # estimated LOC that could be removed
    by_kind:         dict        # kind → count
    by_confidence:   dict        # confidence → count
    by_language:     dict        # language → count

    def summary(self) -> str:
        return (
            f"{self.files_scanned} files · "
            f"{self.symbols_found} symbols · "
            f"{self.dead_count} dead "
            f"({self.safe_to_delete} safe to delete) · "
            f"~{self.lines_recoverable} recoverable LOC"
        )
