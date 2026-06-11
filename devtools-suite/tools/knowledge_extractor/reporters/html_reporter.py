"""
HTML dashboard for the Implicit Knowledge Extractor.
Three views:
  1. Bus factor heatmap — modules colored by risk, click for expert breakdown
  2. Developer map — who knows what, breadth vs depth
  3. Pairing recommendations — who should teach whom
"""

import json
from datetime import datetime
from core.models import KnowledgeReport


RISK_COLORS = {
    'critical': {'bg': '#3d1a1a', 'fg': '#f85149', 'border': '#7d2020'},
    'high':     {'bg': '#3d2e0a', 'fg': '#e3b341', 'border': '#7d5a10'},
    'medium':   {'bg': '#0d2038', 'fg': '#58a6ff', 'border': '#1a4070'},
    'low':      {'bg': '#0d2b1a', 'fg': '#3fb950', 'border': '#1a5030'},
}

PRIORITY_COLORS = {
    'urgent': '#f85149',
    'high':   '#e3b341',
    'medium': '#58a6ff',
}


def generate_html_report(report: KnowledgeReport, output_path: str = "knowledge-report.html"):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    modules_json = json.dumps([m.to_dict() for m in report.modules], indent=2)

    devs_json = json.dumps([
        {
            "login": d.login,
            "name": d.name or d.login,
            "active": d.active,
            "commits": d.commits,
            "last_commit": d.last_commit,
            "modules_known": sum(
                1 for m in report.modules
                if d.login in m.expertise and m.expertise[d.login].score > 10
            ),
        }
        for d in sorted(report.developers, key=lambda d: -d.commits)
        if d.commits > 0
    ], indent=2)

    pairings_json = json.dumps([
        {
            "teacher": p.teacher,
            "learner": p.learner,
            "module":  p.module,
            "priority": p.priority,
            "reason":  p.reason,
        }
        for p in report.pairings
    ], indent=2)

    gaps_json = json.dumps([
        {
            "module":         g.module,
            "risk_level":     g.risk_level,
            "description":    g.description,
            "primary_expert": g.primary_expert,
            "secondary":      g.secondary,
            "recommendation": g.recommendation,
            "bus_factor":     g.bus_factor,
        }
        for g in report.gaps
    ], indent=2)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Knowledge Map — {now}</title>
<style>
:root{{--bg:#0d1117;--s1:#161b22;--s2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#848d97;
  --red:#f85149;--amb:#e3b341;--blu:#58a6ff;--grn:#3fb950;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx)}}
header{{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}}
header h1{{font-size:16px;font-weight:600}}
.stats{{display:flex;gap:14px;font-size:12px;color:var(--mu);align-items:center;flex-wrap:wrap}}
.badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.nav{{display:flex;border-bottom:1px solid var(--bd);padding:0 24px}}
.nav-btn{{padding:12px 16px;font-size:13px;cursor:pointer;border-bottom:2px solid transparent;color:var(--mu)}}
.nav-btn.on{{color:var(--tx);border-bottom-color:var(--blu)}}
.nav-btn:hover{{color:var(--tx)}}
.pane{{padding:20px 24px;display:none}}
.pane.on{{display:block}}
.heatmap{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:24px}}
.hm-cell{{border-radius:8px;padding:12px 14px;cursor:pointer;border:1px solid transparent;transition:opacity .15s}}
.hm-cell:hover{{opacity:.85}}
.hm-cell.critical{{background:#3d1a1a;border-color:#7d2020}}
.hm-cell.high{{background:#3d2e0a;border-color:#7d5a10}}
.hm-cell.medium{{background:#0d2038;border-color:#1a4070}}
.hm-cell.low{{background:#0d2b1a;border-color:#1a5030}}
.hm-name{{font-family:monospace;font-size:12px;font-weight:500;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.hm-meta{{font-size:11px;opacity:.7;display:flex;gap:10px}}
.detail-panel{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:18px;margin-top:16px}}
.dp-title{{font-size:14px;font-weight:500;margin-bottom:12px;font-family:monospace}}
.exp-bar-wrap{{margin-bottom:8px}}
.exp-name{{font-size:12px;color:var(--mu);margin-bottom:3px;display:flex;justify-content:space-between}}
.exp-bar-bg{{height:6px;background:var(--s2);border-radius:3px;overflow:hidden}}
.exp-bar-fill{{height:100%;border-radius:3px}}
.dev-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}}
.dev-card{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:14px}}
.dev-name{{font-weight:500;font-size:13px;margin-bottom:4px}}
.dev-meta{{font-size:11px;color:var(--mu);margin-bottom:8px}}
.dev-bar{{height:5px;background:var(--s2);border-radius:3px;overflow:hidden;margin-top:4px}}
.dev-bar-fill{{height:100%;background:var(--blu);border-radius:3px}}
.pairing-list{{display:flex;flex-direction:column;gap:8px}}
.pc{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:12px 14px}}
.pc-top{{display:flex;gap:8px;align-items:center;margin-bottom:6px}}
.pc-arrow{{color:var(--mu);font-size:16px}}
.pc-mod{{font-size:11px;font-family:monospace;color:var(--mu);margin-bottom:4px}}
.pc-reason{{font-size:12px;color:var(--mu);line-height:1.5}}
.gap-list{{display:flex;flex-direction:column;gap:8px;margin-bottom:20px}}
.gc{{background:var(--s1);border-radius:8px;padding:12px 14px}}
.gc.critical{{border:1px solid #7d2020}}
.gc.high{{border:1px solid #7d5a10}}
.gc.medium{{border:1px solid #1a4070}}
.gc-mod{{font-family:monospace;font-size:13px;font-weight:500;margin-bottom:5px}}
.gc-desc{{font-size:12px;color:var(--mu);line-height:1.5}}
.gc-rec{{font-size:12px;margin-top:6px;padding:8px;background:var(--s2);border-radius:6px}}
.section-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--mu);margin:20px 0 12px}}
.inactive{{opacity:.5;font-style:italic}}
</style>
</head>
<body>
<header>
  <h1>Implicit Knowledge Extractor</h1>
  <div class="stats">
    <span>{now}</span>
    <span>{report.commits_analyzed:,} commits · {report.files_analyzed} files</span>
    <span class="badge" style="background:#3d1a1a;color:#f85149">{len(report.critical_modules)} critical</span>
    <span class="badge" style="background:#3d2e0a;color:#e3b341">{len([m for m in report.modules if m.risk_level=='high'])} high risk</span>
    <span class="badge" style="background:#0d2b1a;color:#3fb950">{len(report.pairings)} pairings recommended</span>
  </div>
</header>
<div class="nav">
  <div class="nav-btn on" onclick="showPane('heatmap',this)">Bus factor map</div>
  <div class="nav-btn" onclick="showPane('devs',this)">Developer map</div>
  <div class="nav-btn" onclick="showPane('gaps',this)">Knowledge gaps</div>
  <div class="nav-btn" onclick="showPane('pairings',this)">Pairing plan</div>
</div>

<div class="pane on" id="pane-heatmap">
  <div class="section-title">All modules — click any to see expert breakdown</div>
  <div class="heatmap" id="heatmap"></div>
  <div class="detail-panel" id="detail-panel" style="display:none">
    <div class="dp-title" id="dp-title"></div>
    <div id="dp-body"></div>
  </div>
</div>

<div class="pane" id="pane-devs">
  <div class="section-title">Active developers — breadth and depth</div>
  <div class="dev-grid" id="dev-grid"></div>
</div>

<div class="pane" id="pane-gaps">
  <div class="section-title">Knowledge gaps requiring action</div>
  <div class="gap-list" id="gap-list"></div>
</div>

<div class="pane" id="pane-pairings">
  <div class="section-title">Recommended pairing sessions</div>
  <div class="pairing-list" id="pairing-list"></div>
</div>

<script>
const MODULES   = {modules_json};
const DEVS      = {devs_json};
const PAIRINGS  = {pairings_json};
const GAPS      = {gaps_json};
const RISK_C    = {json.dumps(RISK_COLORS)};
const PRIO_C    = {json.dumps(PRIORITY_COLORS)};
const MAX_DEVS  = Math.max(...DEVS.map(d => d.modules_known), 1);
const MAX_COMMITS = Math.max(...DEVS.map(d => d.commits), 1);

function showPane(id, btn) {{
  document.querySelectorAll('.pane').forEach(p => p.classList.remove('on'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('on'));
  document.getElementById('pane-' + id).classList.add('on');
  btn.classList.add('on');
}}

function renderHeatmap() {{
  const hm = document.getElementById('heatmap');
  hm.innerHTML = MODULES.map(m => `
    <div class="hm-cell ${{m.risk_level}}" onclick="showDetail('${{m.path}}')">
      <div class="hm-name">${{m.path}}</div>
      <div class="hm-meta">
        <span>bus ${{m.bus_factor}}</span>
        <span>${{m.total_commits}} commits</span>
        <span>${{m.total_lines}} LOC</span>
      </div>
    </div>`).join('');
}}

function showDetail(path) {{
  const m = MODULES.find(x => x.path === path);
  if (!m) return;
  const panel = document.getElementById('detail-panel');
  panel.style.display = 'block';
  document.getElementById('dp-title').textContent = path;
  const expertBars = (m.experts||[]).map(e => {{
    const pct = Math.round(e.score);
    const color = e.is_primary ? 'var(--amb)' : 'var(--blu)';
    const tag = e.is_sole_owner ? ' (sole owner)' : e.is_primary ? ' (primary)' : '';
    return `<div class="exp-bar-wrap">
      <div class="exp-name"><span>${{e.developer}}${{tag}}</span><span>${{pct}}/100</span></div>
      <div class="exp-bar-bg"><div class="exp-bar-fill" style="width:${{pct}}%;background:${{color}}"></div></div>
    </div>`;
  }}).join('');
  const coCh = (m.co_changes||[]).map(([mod, cnt]) =>
    `<span style="font-size:11px;font-family:monospace;color:var(--mu)">${{mod}} (${{cnt}})</span>`
  ).join(', ');
  document.getElementById('dp-body').innerHTML = `
    ${{expertBars}}
    ${{coCh ? `<div style="margin-top:12px;font-size:11px;color:var(--mu)">Often changed with: ${{coCh}}</div>` : ''}}
  `;
}}

function renderDevs() {{
  const grid = document.getElementById('dev-grid');
  grid.innerHTML = DEVS.filter(d => d.active).map(d => {{
    const breadthPct = Math.round(d.modules_known / MAX_DEVS * 100);
    const commitPct  = Math.round(d.commits / MAX_COMMITS * 100);
    return `<div class="dev-card">
      <div class="dev-name">${{d.name}}</div>
      <div class="dev-meta">${{d.commits}} commits · ${{d.modules_known}} modules · last ${{d.last_commit||'?'}}</div>
      <div style="font-size:11px;color:var(--mu);margin-bottom:2px">Breadth (${{d.modules_known}} modules)</div>
      <div class="dev-bar"><div class="dev-bar-fill" style="width:${{breadthPct}}%;background:var(--grn)"></div></div>
      <div style="font-size:11px;color:var(--mu);margin-top:6px;margin-bottom:2px">Volume (${{d.commits}} commits)</div>
      <div class="dev-bar"><div class="dev-bar-fill" style="width:${{commitPct}}%;background:var(--blu)"></div></div>
    </div>`;
  }}).join('');
}}

function renderGaps() {{
  const list = document.getElementById('gap-list');
  if (!GAPS.length) {{
    list.innerHTML = '<div style="color:var(--mu);padding:20px">No critical knowledge gaps detected.</div>';
    return;
  }}
  list.innerHTML = GAPS.map(g => {{
    const rc = RISK_C[g.risk_level] || RISK_C.medium;
    return `<div class="gc ${{g.risk_level}}">
      <div class="gc-mod" style="color:${{rc.fg}}">${{g.module}}</div>
      <div class="gc-desc">${{g.description}}</div>
      <div style="font-size:11px;color:var(--mu);margin-top:4px">
        Primary: ${{g.primary_expert}}
        ${{g.secondary?.length ? ' · Secondary: ' + g.secondary.join(', ') : ''}}
      </div>
      <div class="gc-rec">${{g.recommendation}}</div>
    </div>`;
  }}).join('');
}}

function renderPairings() {{
  const list = document.getElementById('pairing-list');
  if (!PAIRINGS.length) {{
    list.innerHTML = '<div style="color:var(--mu);padding:20px">No pairing recommendations generated.</div>';
    return;
  }}
  list.innerHTML = PAIRINGS.map(p => {{
    const pc = PRIO_C[p.priority] || '#58a6ff';
    return `<div class="pc">
      <div class="pc-top">
        <span class="badge" style="background:${{pc}}22;color:${{pc}}">${{p.priority}}</span>
        <strong style="font-size:13px">${{p.teacher}}</strong>
        <span class="pc-arrow">→</span>
        <strong style="font-size:13px">${{p.learner}}</strong>
      </div>
      <div class="pc-mod">${{p.module}}</div>
      <div class="pc-reason">${{p.reason}}</div>
    </div>`;
  }}).join('');
}}

renderHeatmap();
renderDevs();
renderGaps();
renderPairings();
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
    return output_path
