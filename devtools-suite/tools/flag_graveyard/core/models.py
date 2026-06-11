"""
Core data models for the Feature Flag Graveyard Hunter.

A feature flag becomes a graveyard candidate when:
  1. It's permanently ON  (hardcoded true, env=1, always returns true)
  2. It's permanently OFF (hardcoded false, removed from config, always returns false)
  3. It's old enough that the team has probably forgotten about it

The danger: dead flags leave dead code branches in the codebase forever.
An always-true flag means the else-branch is zombie code.
An always-false flag means the if-branch is zombie code.
Both make the codebase harder to understand and refactor.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import hashlib


class FlagState(str, Enum):
    ALWAYS_ON    = "always_on"     # hardcoded true / 100% rollout / env var = "1"/"true"
    ALWAYS_OFF   = "always_off"    # hardcoded false / 0% rollout / removed from config
    DYNAMIC      = "dynamic"       # legitimately varies at runtime — skip
    UNKNOWN      = "unknown"       # can't determine — flag for manual review


class FlagKind(str, Enum):
    CODE_CONSTANT  = "code_constant"    # const bool FLAG_X = true;
    CONFIG_VALUE   = "config_value"     # appsettings.json / application.yml
    ENV_VAR        = "env_var"          # FEATURE_ENABLE_X=true
    LAUNCHDARKLY   = "launchdarkly"     # LaunchDarkly / Unleash / Split.io
    CUSTOM_SERVICE = "custom_service"   # IFeatureService.IsEnabled("x")
    INLINE_CHECK   = "inline_check"     # if (someVar == "feature-x")


class CleanupAction(str, Enum):
    REMOVE_ALWAYS_TRUE_FLAG  = "remove_always_true_flag"   # inline the true branch, delete flag
    REMOVE_ALWAYS_FALSE_FLAG = "remove_always_false_flag"  # inline the false branch, delete flag
    REMOVE_BOTH_BRANCHES     = "remove_both_branches"      # flag check has no remaining code
    MANUAL_REVIEW            = "manual_review"             # too complex for automated cleanup


@dataclass
class FlagUsage:
    """One location in the codebase where a flag is used."""
    flag_name:      str
    file:           str
    line:           int
    language:       str
    usage_pattern:  str           # the raw code snippet
    branch_kind:    str           # 'if_true', 'if_false', 'ternary', 'switch'
    has_else:       bool = False
    true_branch_lines:  int = 0   # LOC in the enabled branch
    false_branch_lines: int = 0   # LOC in the disabled branch


@dataclass
class FlagDefinition:
    """A feature flag found in the codebase."""
    name:           str
    kind:           FlagKind
    state:          FlagState
    source_file:    str           # where the flag is defined/configured
    source_line:    int
    language:       str

    # Usage locations across the codebase
    usages:         list[FlagUsage] = field(default_factory=list)

    # Metadata
    git_age_days:   int = 0       # days since the flag was introduced
    last_changed_days: int = 0    # days since last modification
    introduced_by:  str = ""      # git author who introduced it
    ticket_ref:     str = ""      # extracted JIRA/GitHub issue reference

    # Cleanup plan
    cleanup_action: CleanupAction = CleanupAction.MANUAL_REVIEW
    cleanup_complexity: str = "medium"   # 'simple', 'medium', 'complex'

    # Stable ID
    id: str = field(default="")

    def __post_init__(self):
        if not self.id:
            raw = f"{self.name}:{self.source_file}:{self.kind}"
            self.id = hashlib.sha1(raw.encode()).hexdigest()[:10]

    def total_usages(self) -> int:
        return len(self.usages)

    def affected_files(self) -> set[str]:
        return {u.file for u in self.usages}

    def dead_lines(self) -> int:
        """Estimate of LOC that can be removed when this flag is cleaned up."""
        if self.state == FlagState.ALWAYS_ON:
            return sum(u.false_branch_lines for u in self.usages)
        elif self.state == FlagState.ALWAYS_OFF:
            return sum(u.true_branch_lines for u in self.usages)
        return 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "state": self.state.value,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "language": self.language,
            "usage_count": self.total_usages(),
            "affected_files": list(self.affected_files()),
            "git_age_days": self.git_age_days,
            "last_changed_days": self.last_changed_days,
            "introduced_by": self.introduced_by,
            "ticket_ref": self.ticket_ref,
            "cleanup_action": self.cleanup_action.value,
            "cleanup_complexity": self.cleanup_complexity,
            "dead_lines": self.dead_lines(),
        }


@dataclass
class GraveyardReport:
    """Full scan result."""
    flags:             list[FlagDefinition]
    total_flags:       int
    graveyard_count:   int         # always_on + always_off
    always_on:         int
    always_off:        int
    files_affected:    int
    dead_lines:        int         # total recoverable LOC
    files_scanned:     int
    by_language:       dict = field(default_factory=dict)
    by_kind:           dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.files_scanned} files · "
            f"{self.total_flags} flags found · "
            f"{self.graveyard_count} graveyard "
            f"({self.always_on} always-on, {self.always_off} always-off) · "
            f"~{self.dead_lines} dead LOC"
        )
