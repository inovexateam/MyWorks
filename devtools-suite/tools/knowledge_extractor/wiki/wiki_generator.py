"""
Knowledge wiki generator — Layer 3.
The most human-readable output: per-module narrative pages that answer
"what is this module, who built it, and who to ask about it".

Generated entirely from git history — no documentation required.
"""

import re
from datetime import datetime
from core.models import Module, Developer, KnowledgeReport


# ── Ticket reference extractor ────────────────────────────────────────────────

TICKET_RE = re.compile(r'\b([A-Z]{2,8}-\d{1,6}|#\d{3,6})\b')
FEAT_RE    = re.compile(r'\b(feat|feature|add|implement|introduce|create)\b[:\s]+(.{10,60})', re.IGNORECASE)
FIX_RE     = re.compile(r'\b(fix|bug|patch|resolve|correct)\b[:\s]+(.{10,50})', re.IGNORECASE)


def extract_module_narrative(
    module: Module,
    commits: list[dict],
    developers: dict[str, Developer],
    file_to_module: dict[str, str],
) -> dict:
    """
    Build a rich narrative dict for a module from git history:
      - creation story (who, when, why)
      - key contributors and their contributions
      - notable changes (features added, bugs fixed)
      - related tickets
      - hidden dependencies (co-change partners)
    """
    # Filter commits that touched this module
    module_commits = [
        c for c in commits
        if any(file_to_module.get(f) == module.path for f in c.get('files', []))
    ]

    if not module_commits:
        return {"path": module.path, "narrative": "No git history found."}

    # Sort chronologically
    module_commits.sort(key=lambda c: c.get('date', ''))

    first = module_commits[0]
    creation_author = developers.get(first['email'], None)
    creation_name   = creation_author.name if creation_author else first.get('name', first['email'])
    creation_date   = first.get('date', 'unknown')

    # Extract feature commits
    features = []
    bugfixes  = []
    tickets   = set()

    for c in module_commits[-50:]:  # look at last 50 commits for recent story
        subject = c.get('subject', '')
        m = FEAT_RE.search(subject)
        if m and len(features) < 8:
            features.append(subject[:80])
        m = FIX_RE.search(subject)
        if m and len(bugfixes) < 5:
            bugfixes.append(subject[:80])
        for t in TICKET_RE.findall(subject):
            tickets.add(t)

    # Top contributors
    experts = module.experts_ranked()[:5]
    contributor_lines = []
    for e in experts:
        dev = developers.get(e.developer)
        display = dev.name if dev else e.developer
        age_str = f"{e.recency_days}d ago" if e.recency_days < 999 else "inactive"
        active_str = "(active)" if dev and dev.active else "(inactive)"
        contributor_lines.append(
            f"  {display} {active_str} — score {e.score:.0f}/100, "
            f"{e.commit_count} commits, last active {age_str}"
        )

    # Co-change partners
    co_partners = sorted(module.co_changes.items(), key=lambda x: -x[1])[:3]
    co_lines = [f"  {partner} ({count} co-commits)" for partner, count in co_partners]

    return {
        "path":          module.path,
        "language":      module.language,
        "bus_factor":    module.bus_factor,
        "risk_level":    module.risk_level,
        "created":       creation_date,
        "created_by":    creation_name,
        "last_active":   module.last_commit,
        "total_commits": module.total_commits,
        "total_lines":   module.total_lines,
        "primary_expert": module.primary_expert,
        "contributors":  contributor_lines,
        "features":      features[:5],
        "bugfixes":      bugfixes[:3],
        "tickets":       sorted(tickets)[:8],
        "co_changes":    co_lines,
    }


def render_module_markdown(narrative: dict) -> str:
    """Render a module narrative as markdown."""
    path = narrative['path']
    lines = [
        f"# `{path}`\n",
        f"**Language:** {narrative.get('language','unknown')}  ",
        f"**Bus factor:** {narrative.get('bus_factor','?')}  ",
        f"**Risk:** {narrative.get('risk_level','?').upper()}  ",
        f"**LOC:** {narrative.get('total_lines',0):,}  ",
        f"**Commits:** {narrative.get('total_commits',0):,}\n",
        f"## Origin",
        f"Created by **{narrative.get('created_by','unknown')}** on {narrative.get('created','?')}.",
        f"Last activity: {narrative.get('last_active','?')}\n",
        "## Who to ask",
    ]
    for c in narrative.get('contributors', []):
        lines.append(c)

    if narrative.get('features'):
        lines += ["\n## Recent features"]
        for f in narrative['features']:
            lines.append(f"- {f}")

    if narrative.get('bugfixes'):
        lines += ["\n## Recent fixes"]
        for f in narrative['bugfixes']:
            lines.append(f"- {f}")

    if narrative.get('tickets'):
        lines += ["\n## Related tickets", ", ".join(narrative['tickets'])]

    if narrative.get('co_changes'):
        lines += ["\n## Often changed alongside"]
        for c in narrative['co_changes']:
            lines.append(c)

    return '\n'.join(lines)


def generate_full_wiki(
    report: KnowledgeReport,
    commits: list[dict],
    file_to_module: dict[str, str],
    output_dir: str = "knowledge-wiki",
) -> str:
    """Generate a markdown file per module in output_dir."""
    import os
    from pathlib import Path

    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    dev_map = {d.login: d for d in report.developers}

    for module in report.modules:
        narrative = extract_module_narrative(module, commits, dev_map, file_to_module)
        md = render_module_markdown(narrative)
        safe_name = module.path.replace('/', '_').replace('\\', '_') or 'root'
        (out / f"{safe_name}.md").write_text(md)

    # Generate index
    index_lines = [
        "# Knowledge wiki\n",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"| Module | Risk | Bus factor | Primary expert | LOC |",
        f"|--------|------|------------|----------------|-----|",
    ]
    for m in report.modules:
        risk_icon = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(m.risk_level, '')
        expert = dev_map.get(m.primary_expert)
        expert_str = expert.name if expert else m.primary_expert or '—'
        index_lines.append(
            f"| `{m.path}` | {risk_icon} {m.risk_level} | {m.bus_factor} | {expert_str} | {m.total_lines:,} |"
        )

    (out / "README.md").write_text('\n'.join(index_lines))
    print(f"Wiki generated: {output_dir}/ ({len(report.modules)} modules)")
    return output_dir
