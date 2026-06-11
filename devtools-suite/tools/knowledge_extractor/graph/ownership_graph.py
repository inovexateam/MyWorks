"""
Ownership graph builder — Layer 2.
Takes raw git data and produces scored expertise per developer per module.

Expertise score formula (0–100):
  score = commit_weight × recency_decay × depth_bonus × stability_bonus

  commit_weight:   log(1 + commits_to_module) × 10   — diminishing returns on raw count
  recency_decay:   e^(-days_since_last_commit / 180)  — recent activity worth more
  depth_bonus:     lines_owned / total_module_lines   — what fraction you actually own
  stability_bonus: 1 - churn_rate                     — low churn = stable understanding

Bus factor: how many top contributors represent ≥ 70% of total commits to the module.
  bus_factor = 1 → critical risk (one person departure breaks the team)
  bus_factor = 2 → high risk
  bus_factor ≥ 3 → acceptable
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta
from core.models import (
    Developer, Module, ModuleExpertise,
    KnowledgeGap, PairingRecommendation, KnowledgeReport
)


RECENCY_HALFLIFE_DAYS = 180   # expertise halves every 6 months of inactivity
BUS_FACTOR_COVERAGE   = 0.70  # who covers >= 70% of commits
CRITICAL_BUS_FACTOR   = 1
HIGH_RISK_BUS_FACTOR  = 2


def compute_expertise_score(
    commit_count:  int,
    total_commits: int,
    lines_owned:   int,
    total_lines:   int,
    days_since:    int,
) -> float:
    """
    Returns expertise score 0–100.
    All factors multiply: zero in any = dramatically lower score.
    """
    if total_commits == 0 or commit_count == 0:
        return 0.0

    # Commit weight: logarithmic — 10 commits not 10× better than 1
    commit_frac   = commit_count / total_commits
    commit_weight = math.log1p(commit_count * 10) / math.log1p(total_commits * 10 + 1)

    # Recency decay: exponential
    recency = math.exp(-days_since / RECENCY_HALFLIFE_DAYS)

    # Line depth: fraction of current file actually owned
    depth = (lines_owned / total_lines) if total_lines > 0 else 0.0
    # Cap depth contribution — owning 100% of a tiny file isn't worth max score
    depth = min(depth * 1.5, 1.0)

    # Combined, mapped to 0–100
    raw = commit_weight * 0.5 + recency * 0.3 + depth * 0.2
    return min(raw * 100, 100.0)


def compute_bus_factor(expertise_map: dict[str, ModuleExpertise], total_commits: int) -> int:
    """
    Bus factor = fewest people whose combined commits cover BUS_FACTOR_COVERAGE of total.
    """
    if not expertise_map or total_commits == 0:
        return 0

    sorted_exp = sorted(expertise_map.values(), key=lambda e: -e.commit_count)
    cumulative = 0
    bus_factor  = 0

    for exp in sorted_exp:
        cumulative += exp.commit_count
        bus_factor += 1
        if cumulative / total_commits >= BUS_FACTOR_COVERAGE:
            break

    return bus_factor


def days_since_date(date_str: str) -> int:
    """Return days since a YYYY-MM-DD date string."""
    if not date_str:
        return 999
    try:
        dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
        return max(0, (datetime.now() - dt).days)
    except Exception:
        return 999


def build_ownership_graph(
    commits:      list[dict],
    module_blame: dict[str, dict[str, int]],   # module → {email: lines}
    file_to_module: dict[str, str],
    modules:      list[str],
    repo_path:    str,
    verbose:      bool = False,
) -> list[Module]:
    """
    Main ownership graph builder.
    For each module: compute expertise per developer, bus factor, risk level.
    """
    from miner.git_miner import count_module_lines, detect_language

    # Build: module → developer → commit_count, last_commit_date
    module_dev_commits: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'last': ''}))
    module_total_commits: dict[str, int] = defaultdict(int)
    module_first_commit:  dict[str, str] = {}
    module_last_commit:   dict[str, str] = {}

    for commit in commits:
        date = commit['date']
        email = commit['email']
        touched_modules = set()

        for filepath in commit['files']:
            mod = file_to_module.get(filepath)
            if mod:
                touched_modules.add(mod)

        for mod in touched_modules:
            entry = module_dev_commits[mod][email]
            entry['count'] += 1
            if not entry['last'] or date > entry['last']:
                entry['last'] = date
            module_total_commits[mod] += 1
            if mod not in module_first_commit or date < module_first_commit[mod]:
                module_first_commit[mod] = date
            if mod not in module_last_commit or date > module_last_commit[mod]:
                module_last_commit[mod] = date

    # Build Module objects
    module_objects: list[Module] = []

    for i, mod_path in enumerate(modules):
        if verbose and i % 10 == 0:
            print(f"\r  Scoring modules: {i}/{len(modules)}...", end='', flush=True)

        total_lines   = count_module_lines(mod_path, repo_path)
        language      = detect_language(mod_path, repo_path)
        total_commits = module_total_commits.get(mod_path, 0)
        blame_map     = module_blame.get(mod_path, {})
        dev_commits   = module_dev_commits.get(mod_path, {})

        if total_commits == 0:
            continue

        expertise_map: dict[str, ModuleExpertise] = {}

        all_devs = set(dev_commits.keys()) | set(blame_map.keys())
        for email in all_devs:
            c_data    = dev_commits.get(email, {'count': 0, 'last': ''})
            c_count   = c_data['count']
            last_date = c_data.get('last', '')
            lines     = blame_map.get(email, 0)
            days      = days_since_date(last_date)

            score = compute_expertise_score(
                c_count, total_commits, lines, max(total_lines, 1), days
            )

            if score < 1.0 and c_count == 0:
                continue

            expertise_map[email] = ModuleExpertise(
                developer=email,
                module=mod_path,
                score=score,
                commit_count=c_count,
                lines_owned=lines,
                recency_days=days,
                churn_rate=0.0,    # simplified — full impl would track line re-edits
                is_primary=False,
                is_sole_owner=len(all_devs) == 1,
            )

        if not expertise_map:
            continue

        # Mark primary
        top = max(expertise_map.values(), key=lambda e: e.score)
        top.is_primary = True

        bus_factor = compute_bus_factor(expertise_map, total_commits)
        risk_level = (
            'critical' if bus_factor <= CRITICAL_BUS_FACTOR else
            'high'     if bus_factor <= HIGH_RISK_BUS_FACTOR else
            'medium'   if bus_factor <= 3 else
            'low'
        )

        module_objects.append(Module(
            path=mod_path,
            language=language,
            total_lines=total_lines,
            total_commits=total_commits,
            first_commit=module_first_commit.get(mod_path, ''),
            last_commit=module_last_commit.get(mod_path, ''),
            expertise=expertise_map,
            bus_factor=bus_factor,
            risk_level=risk_level,
            primary_expert=top.developer,
            knowledge_gap=bus_factor <= CRITICAL_BUS_FACTOR,
        ))

    if verbose:
        print(f"\r  Scored {len(module_objects)} modules.                    ")

    return module_objects


# ── Knowledge gap + pairing generators ────────────────────────────────────────

def identify_gaps(
    modules: list[Module],
    developers: dict[str, Developer],
) -> list[KnowledgeGap]:
    gaps = []

    for mod in modules:
        if mod.risk_level not in ('critical', 'high'):
            continue

        experts = mod.experts_ranked()
        if not experts:
            continue

        primary = experts[0]
        secondary = [e.developer for e in experts[1:3]]

        # Check if primary is still active
        dev = developers.get(primary.developer)
        primary_inactive = dev and not dev.active

        if mod.risk_level == 'critical' or primary_inactive:
            risk = 'critical' if (mod.bus_factor == 1 and primary_inactive) else mod.risk_level
            gaps.append(KnowledgeGap(
                module=mod.path,
                risk_level=risk,
                description=(
                    f"Bus factor {mod.bus_factor} — "
                    + ("primary expert no longer active" if primary_inactive
                       else f"only {mod.bus_factor} developer(s) understand this module")
                ),
                primary_expert=primary.developer,
                secondary=secondary,
                recommendation=_gap_recommendation(mod, primary_inactive),
                bus_factor=mod.bus_factor,
            ))

    gaps.sort(key=lambda g: ['critical', 'high', 'medium'].index(g.risk_level))
    return gaps


def _gap_recommendation(mod: Module, primary_inactive: bool) -> str:
    if primary_inactive:
        return (
            f"Primary expert is no longer active. Assign {mod.path} to a new owner "
            f"immediately. Schedule knowledge-transfer sessions from any remaining contributors."
        )
    if mod.bus_factor == 1:
        return (
            f"Only one person understands {mod.path}. Add a second reviewer to all PRs "
            f"touching this module and schedule a pairing session."
        )
    return (
        f"Bus factor {mod.bus_factor} — schedule pairing sessions to spread knowledge "
        f"to at least one more team member."
    )


def generate_pairings(
    modules: list[Module],
    developers: dict[str, Developer],
    max_pairings: int = 20,
) -> list[PairingRecommendation]:
    """
    For each high-risk module, recommend who should teach whom.
    Learner = active developer with lowest score in this module.
    Teacher = active developer with highest score.
    """
    pairings = []
    seen = set()

    for mod in sorted(modules, key=lambda m: (m.bus_factor, -m.total_lines)):
        if mod.risk_level not in ('critical', 'high', 'medium'):
            continue

        active_experts = [
            e for e in mod.experts_ranked()
            if developers.get(e.developer, Developer(login=e.developer, name=e.developer)).active
            and e.score > 5
        ]
        all_active_devs = [d for d in developers.values() if d.active]

        if len(active_experts) < 1:
            continue

        teacher = active_experts[0]

        # Find active devs with low/zero score in this module — potential learners
        learner_candidates = []
        for dev in all_active_devs:
            existing_score = mod.expertise.get(dev.login, ModuleExpertise(
                developer=dev.login, module=mod.path, score=0,
                commit_count=0, lines_owned=0, recency_days=999,
                churn_rate=0, is_primary=False, is_sole_owner=False
            )).score
            if existing_score < 20 and dev.login != teacher.developer:
                learner_candidates.append((dev.login, existing_score))

        if not learner_candidates:
            continue

        # Best learner = lowest score (most to gain)
        learner_login = min(learner_candidates, key=lambda x: x[1])[0]
        key = (teacher.developer, learner_login, mod.path)
        if key in seen:
            continue
        seen.add(key)

        priority = 'urgent' if mod.risk_level == 'critical' else 'high' if mod.risk_level == 'high' else 'medium'

        pairings.append(PairingRecommendation(
            teacher=teacher.developer,
            learner=learner_login,
            module=mod.path,
            priority=priority,
            reason=(
                f"{teacher.developer} has score {teacher.score:.0f}/100 in {mod.path}. "
                f"{learner_login} has minimal exposure. "
                f"Bus factor is {mod.bus_factor}."
            ),
        ))

        if len(pairings) >= max_pairings:
            break

    return pairings


def build_report(
    modules:      list[Module],
    developers:   dict[str, Developer],
    co_changes:   dict[str, dict[str, int]],
    commits_count: int,
    files_count:   int,
    date_range:    str,
) -> KnowledgeReport:
    """Assemble the full knowledge report."""

    # Attach co-changes to modules
    mod_map = {m.path: m for m in modules}
    for mod_path, co in co_changes.items():
        if mod_path in mod_map:
            mod_map[mod_path].co_changes = co

    active_devs = {k: v for k, v in developers.items() if v.active}

    critical = [m for m in modules if m.risk_level == 'critical']
    orphaned = [
        m for m in modules
        if m.primary_expert and not developers.get(m.primary_expert, Developer(login='', name='')).active
        and m.bus_factor <= 1
    ]

    gaps     = identify_gaps(modules, developers)
    pairings = generate_pairings(modules, developers)

    return KnowledgeReport(
        modules=sorted(modules, key=lambda m: (
            ['critical','high','medium','low'].index(m.risk_level), m.path
        )),
        developers=list(developers.values()),
        gaps=gaps,
        pairings=pairings,
        critical_modules=critical,
        orphaned_modules=orphaned,
        files_analyzed=files_count,
        commits_analyzed=commits_count,
        date_range=date_range,
    )
