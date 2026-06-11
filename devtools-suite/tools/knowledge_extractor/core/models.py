"""
Core data models for the Implicit Knowledge Extractor.

The central insight: knowledge lives in git history, not documentation.
Every commit is a breadcrumb. The pattern of who changed what, when,
and what they changed it alongside reveals who truly understands each module.

Key concepts:
  - Expertise score: weighted contribution depth (recent changes worth more)
  - Bus factor: how many people need to leave before a module is orphaned
  - Knowledge gap: a module with bus factor 1 or primary expert on notice
  - Co-change coupling: files often changed together imply hidden knowledge dependency
"""

from dataclasses import dataclass, field
from typing import Optional
import hashlib


@dataclass
class Developer:
    """One contributor in the repo."""
    login:       str          # git author email or username
    name:        str          # display name from git config
    commits:     int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    first_commit: str = ""    # ISO date
    last_commit:  str = ""    # ISO date
    active: bool = True       # still in the team (heuristic: commit in last 90 days)

    def display(self) -> str:
        return self.name or self.login


@dataclass
class ModuleExpertise:
    """How well one developer knows one module."""
    developer:       str      # developer login
    module:          str      # module path
    score:           float    # 0–100 expertise score
    commit_count:    int      # raw commits touching this module
    lines_owned:     int      # lines attributed via blame
    recency_days:    int      # days since last commit to this module
    churn_rate:      float    # fraction of own lines subsequently re-edited (low = stable knowledge)
    is_primary:      bool     # highest scorer for this module
    is_sole_owner:   bool     # only person who has touched this module


@dataclass
class Module:
    """A logical code module — directory or package."""
    path:            str       # repo-relative directory path
    language:        str       # dominant language
    total_lines:     int       # current LOC
    total_commits:   int       # lifetime commits touching this module
    first_commit:    str       # when this module was created
    last_commit:     str       # most recent activity

    # Expertise map: developer login → ModuleExpertise
    expertise:       dict[str, ModuleExpertise] = field(default_factory=dict)

    # Co-changed modules (often changed in the same commit)
    co_changes:      dict[str, int] = field(default_factory=dict)  # module → count

    # Computed risk
    bus_factor:      int = 0
    risk_level:      str = "low"    # 'critical', 'high', 'medium', 'low'
    primary_expert:  str = ""       # login of top scorer
    knowledge_gap:   bool = False   # True if bus_factor <= 1

    def experts_ranked(self) -> list[ModuleExpertise]:
        return sorted(self.expertise.values(), key=lambda e: -e.score)

    def to_dict(self) -> dict:
        experts = self.experts_ranked()
        return {
            "path": self.path,
            "language": self.language,
            "total_lines": self.total_lines,
            "total_commits": self.total_commits,
            "bus_factor": self.bus_factor,
            "risk_level": self.risk_level,
            "primary_expert": self.primary_expert,
            "knowledge_gap": self.knowledge_gap,
            "experts": [
                {
                    "developer": e.developer,
                    "score": round(e.score, 1),
                    "commits": e.commit_count,
                    "recency_days": e.recency_days,
                    "is_primary": e.is_primary,
                    "is_sole_owner": e.is_sole_owner,
                }
                for e in experts[:6]
            ],
            "co_changes": sorted(self.co_changes.items(), key=lambda x: -x[1])[:5],
        }


@dataclass
class KnowledgeGap:
    """A specific knowledge risk that needs attention."""
    module:          str
    risk_level:      str     # 'critical', 'high', 'medium'
    description:     str
    primary_expert:  str     # the person who holds the knowledge
    secondary:       list[str]   # people with partial knowledge
    recommendation:  str
    bus_factor:      int


@dataclass
class PairingRecommendation:
    """A suggested pairing to spread knowledge."""
    teacher:         str      # who has deep knowledge
    learner:         str      # who should learn
    module:          str      # what to learn about
    priority:        str      # 'urgent', 'high', 'medium'
    reason:          str


@dataclass
class KnowledgeReport:
    """Full knowledge extraction result."""
    modules:             list[Module]
    developers:          list[Developer]
    gaps:                list[KnowledgeGap]
    pairings:            list[PairingRecommendation]
    critical_modules:    list[Module]     # bus_factor == 1
    orphaned_modules:    list[Module]     # sole owner no longer active
    files_analyzed:      int
    commits_analyzed:    int
    date_range:          str              # "YYYY-MM-DD to YYYY-MM-DD"

    def summary(self) -> str:
        return (
            f"{self.files_analyzed} files · "
            f"{self.commits_analyzed} commits · "
            f"{len(self.modules)} modules · "
            f"{len(self.critical_modules)} critical (bus factor 1) · "
            f"{len(self.orphaned_modules)} orphaned"
        )
