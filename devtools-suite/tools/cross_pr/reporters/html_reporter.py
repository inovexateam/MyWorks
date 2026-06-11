"""
HTML dashboard for Cross-PR Dependency Intelligence.
Shows a PR conflict matrix, sortable overlap table, and per-PR conflict cards.
"""

import json
from datetime import datetime
from core.models import PRSnapshot, Overlap, ConflictReport, Severity, OverlapKind


SEV_COLOR = {
    'critical': '#E24B4A',
    'high':     '#EF9F27',
    'medium':   '#378ADD',
    'low':      '#1D9E75',
}

KIND_LABEL = {
    'line_collision':  'Line collision',
    'symbol_conflict': 'Symbol conflict',
    'semantic_dep':    'Semantic dep',
    'shared_file':     'Shared file',
    'import_chain':    'Import chain',
}


def _matrix_cell_color(sev: str | None) -> str:
    if sev == 'critical': return '#3d1a1a'
    if sev == 'high':     return '#3d2e0a'
    if sev == 'medium':   return '#0d2038'
    if sev == 'low':      return '#0d2b1a'
    return 'transparent'

def _matrix_text_color(sev: str | None) -> str:
    if sev == 'critical': return '#f85149'
    if sev == 'high':     return '#e3b341'
    if sev == 'medium':   return '#58a6ff'
    if sev == 'low':      return '#3fb950'
    return '#555'


def generate_html_report(
    prs: list[PRSnapshot],
    overlaps: list[Overlap],
    reports: dict[int, ConflictReport],
    output_path: str = "cross-pr-report.html",
):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    pr_numbers = [pr.number for pr in prs]

    # Build matrix: pr_a × pr_b → worst severity
    matrix: dict[tuple[int,int], str] = {}
    for o in overlaps:
        key = (o.pr_a, o.pr_b)
        key2 = (o.pr_b, o.pr_a)
        cur = matrix.get(key)
        order = ['critical', 'high', 'medium', 'low']
        if cur is None or order.index(o.severity.value) < order.index(cur):
            matrix[key] = o.severity.value
            matrix[key2] = o.severity.value

    # Build matrix HTML
    matrix_rows = ""
    for pr_a in prs:
        row = f'<tr><td class="pr-label" onclick="filterPR({pr_a.number})">#{pr_a.number}<span class="pr-sub">{pr_a.title[:22]}</span></td>'
        for pr_b in prs:
            if pr_a.number == pr_b.number:
                row += '<td class="diag">—</td>'
            else:
                sev = matrix.get((pr_a.number, pr_b.number))
                bg  = _matrix_cell_color(sev)
                tc  = _matrix_text_color(sev)
                label = sev[:1].upper() if sev else ""
                row += f'<td class="cell" style="background:{bg};color:{tc}" title="PR #{pr_a.number} ↔ PR #{pr_b.number}: {sev or \"no conflict\"}" onclick="filterPair({pr_a.number},{pr_b.number})">{label}</td>'
        row += "</tr>"
        matrix_rows += row

    matrix_headers = "".join(f'<th>#{pr.number}</th>' for pr in prs)

    # Overlap table data
    overlap_json = json.dumps([o.to_dict() for o in overlaps], indent=2)

    # PR cards
    pr_cards = ""
    for pr in prs:
        report = reports.get(pr.number)
        if not report:
            continue
        n_crit = report.severity_summary.get('critical', 0)
        n_high = report.severity_summary.get('high', 0)
        badge = ""
        if n_crit:   badge = f'<span class="badge crit">{n_crit} critical</span>'
        elif n_high: badge = f'<span class="badge high">{n_high} high</span>'
        elif report.overlaps: badge = f'<span class="badge low">{len(report.overlaps)} low</span>'
        else:        badge = f'<span class="badge ok">clean</span>'

        pr_cards += f"""
<div class="pr-card" id="pr-{pr.number}">
  <div class="pc-header">
    <a href="{pr.url}" class="pr-link">PR #{pr.number}</a>
    <span class="pr-title">{pr.title[:60]}</span>
    {badge}
  </div>
  <div class="pc-meta">{pr.author} · {pr.branch} → {pr.base_branch} · {len(pr.changed_files)} files</div>
  <div class="pc-rec">{report.recommendation}</div>
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cross-PR Intelligence — {now}</title>
<style>
:root{{--bg:#0d1117;--s1:#161b22;--s2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#848d97;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);padding:0 0 40px}}
header{{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}}
header h1{{font-size:16px;font-weight:600}}
.meta{{color:var(--mu);font-size:12px;display:flex;gap:16px}}
.section{{padding:20px 24px}}
.section-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--mu);margin-bottom:14px}}
.matrix-wrap{{overflow-x:auto;margin-bottom:24px}}
table.matrix{{border-collapse:collapse;font-size:12px}}
table.matrix th{{color:var(--mu);padding:4px 6px;text-align:center;font-weight:400}}
table.matrix td{{width:36px;height:36px;text-align:center;border:1px solid var(--bd);font-weight:700;font-size:11px;cursor:pointer}}
table.matrix td.diag{{background:var(--s2);color:var(--mu)}}
table.matrix td.pr-label{{width:180px;text-align:left;padding:0 8px;cursor:pointer;color:var(--tx);font-weight:500;white-space:nowrap}}
.pr-label:hover{{color:#58a6ff}}
.pr-sub{{display:block;font-size:10px;font-weight:400;color:var(--mu);overflow:hidden;text-overflow:ellipsis;max-width:160px}}
.cell:hover{{opacity:.8}}
.toolbar{{display:flex;gap:10px;margin-bottom:12px;align-items:center}}
.toolbar input{{background:var(--s2);border:1px solid var(--bd);border-radius:7px;padding:7px 12px;color:var(--tx);font-size:13px;flex:1}}
.toolbar input:focus{{outline:none;border-color:#58a6ff}}
.flt{{padding:5px 10px;border-radius:6px;border:1px solid var(--bd);background:var(--s2);color:var(--mu);font-size:11px;cursor:pointer}}
.flt.on{{border-color:#58a6ff;color:var(--tx)}}
#cnt{{color:var(--mu);font-size:12px}}
.overlap-list{{display:flex;flex-direction:column;gap:6px}}
.oc{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:12px 14px}}
.oc-top{{display:flex;gap:8px;align-items:flex-start;margin-bottom:5px}}
.oc-msg{{flex:1;font-size:13px;line-height:1.4}}
.oc-file{{font-size:11px;font-family:monospace;color:var(--mu)}}
.oc-prs{{font-size:12px;color:#58a6ff;margin-top:3px}}
.badge{{padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600}}
.badge.crit{{background:#3d1a1a;color:#f85149}}
.badge.high{{background:#3d2e0a;color:#e3b341}}
.badge.low{{background:#0d2b1a;color:#3fb950}}
.badge.ok{{background:#0d2b1a;color:#3fb950}}
.badge.sev-critical{{background:#3d1a1a;color:#f85149}}
.badge.sev-high{{background:#3d2e0a;color:#e3b341}}
.badge.sev-medium{{background:#0d2038;color:#58a6ff}}
.badge.sev-low{{background:#0d2b1a;color:#3fb950}}
.order-warn{{color:#e3b341;font-size:11px;margin-top:3px}}
.pr-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:10px}}
.pr-card{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:14px}}
.pc-header{{display:flex;align-items:center;gap:8px;margin-bottom:5px;flex-wrap:wrap}}
.pr-link{{color:#58a6ff;font-weight:600;text-decoration:none}}
.pr-title{{flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.pc-meta{{font-size:11px;color:var(--mu);margin-bottom:6px}}
.pc-rec{{font-size:12px;line-height:1.5}}
.empty{{text-align:center;padding:40px;color:var(--mu)}}
</style>
</head>
<body>
<header>
  <h1>Cross-PR Dependency Intelligence</h1>
  <div class="meta">
    <span>{now}</span>
    <span>{len(prs)} open PRs</span>
    <span>{len(overlaps)} overlaps</span>
    <span>{sum(1 for o in overlaps if o.severity.value == 'critical')} critical</span>
  </div>
</header>

<div class="section">
  <div class="section-title">Conflict matrix — click a cell to filter</div>
  <div class="matrix-wrap">
    <table class="matrix">
      <thead><tr><th></th>{matrix_headers}</tr></thead>
      <tbody>{matrix_rows}</tbody>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-title">All overlaps</div>
  <div class="toolbar">
    <input type="text" id="search" placeholder="Search…" oninput="render()">
    <button class="flt on" onclick="setFlt('all',this)">All</button>
    <button class="flt" onclick="setFlt('critical',this)">Critical</button>
    <button class="flt" onclick="setFlt('high',this)">High</button>
    <button class="flt" onclick="setFlt('symbol_conflict',this)">Symbol</button>
    <button class="flt" onclick="setFlt('semantic_dep',this)">Semantic</button>
    <button class="flt" onclick="setFlt('line_collision',this)">Line</button>
    <span id="cnt"></span>
  </div>
  <div class="overlap-list" id="list"></div>
</div>

<div class="section">
  <div class="section-title">PR summaries</div>
  <div class="pr-cards">{pr_cards}</div>
</div>

<script>
const DATA = {overlap_json};
const KIND_LABEL = {json.dumps(KIND_LABEL)};
let activeFlt = 'all';
let activePR  = null;
let activeSearch = '';

function setFlt(f,btn) {{
  activeFlt = f; activePR = null;
  document.querySelectorAll('.flt').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  render();
}}

function filterPR(n) {{
  activePR = n; activeFlt = 'all';
  document.querySelectorAll('.flt').forEach(b => b.classList.remove('on'));
  document.querySelectorAll('.flt')[0].classList.add('on');
  render();
}}

function filterPair(a,b) {{
  activePR = null; activeFlt = 'all';
  document.getElementById('search').value = '#' + a;
  activeSearch = '#' + a;
  render();
}}

function render() {{
  activeSearch = document.getElementById('search').value.toLowerCase();
  let items = DATA;
  if (activePR) items = items.filter(o => o.pr_a === activePR || o.pr_b === activePR);
  if (activeFlt !== 'all') {{
    items = items.filter(o => o.severity === activeFlt || o.kind === activeFlt);
  }}
  if (activeSearch) items = items.filter(o =>
    o.description.toLowerCase().includes(activeSearch) ||
    o.file.toLowerCase().includes(activeSearch) ||
    ('#' + o.pr_a).includes(activeSearch) ||
    ('#' + o.pr_b).includes(activeSearch) ||
    (o.symbol || '').toLowerCase().includes(activeSearch)
  );
  document.getElementById('cnt').textContent = items.length + ' shown';
  const list = document.getElementById('list');
  if (!items.length) {{
    list.innerHTML = '<div class="empty">No overlaps match these filters.</div>';
    return;
  }}
  list.innerHTML = items.map(o => `
    <div class="oc">
      <div class="oc-top">
        <span class="badge sev-${{o.severity}}">${{o.severity}}</span>
        <span class="badge" style="background:var(--s2);color:var(--mu)">${{KIND_LABEL[o.kind]||o.kind}}</span>
        <span class="oc-msg">${{o.description}}</span>
      </div>
      <div class="oc-file">${{o.file}}${{o.symbol ? ' · <strong>' + o.symbol + '</strong>' : ''}}</div>
      <div class="oc-prs" onclick="filterPair(${{o.pr_a}},${{o.pr_b}})">PR #${{o.pr_a}} ↔ PR #${{o.pr_b}}</div>
      ${{o.merge_order ? '<div class="order-warn">Merge order matters</div>' : ''}}
    </div>`).join('');
}}
render();
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
    return output_path
