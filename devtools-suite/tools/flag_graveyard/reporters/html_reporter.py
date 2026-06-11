"""
HTML dashboard for the Feature Flag Graveyard Hunter.
Shows a graveyard table with age, state, usage count, and cleanup plan preview.
"""

import json
from datetime import datetime
from core.models import GraveyardReport, FlagState


STATE_COLOR = {
    'always_on':  {'bg': '#3d2e0a', 'fg': '#e3b341'},
    'always_off': {'bg': '#3d1a1a', 'fg': '#f85149'},
    'unknown':    {'bg': '#0d2038', 'fg': '#58a6ff'},
}

COMPLEXITY_COLOR = {
    'simple':  {'bg': '#0d2b1a', 'fg': '#3fb950'},
    'medium':  {'bg': '#3d2e0a', 'fg': '#e3b341'},
    'complex': {'bg': '#3d1a1a', 'fg': '#f85149'},
}


def generate_html_report(report: GraveyardReport, output_path: str = "flag-graveyard-report.html"):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    flags_json = json.dumps([f.to_dict() for f in report.flags], indent=2)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flag Graveyard — {now}</title>
<style>
:root{{--bg:#0d1117;--s1:#161b22;--s2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#848d97;
  --red:#f85149;--amb:#e3b341;--blu:#58a6ff;--grn:#3fb950;
  --rs:#3d1a1a;--as:#3d2e0a;--bs:#0d2038;--gs:#0d2b1a;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx)}}
header{{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}}
header h1{{font-size:16px;font-weight:600}}
.stats{{display:flex;gap:14px;font-size:12px;color:var(--mu);align-items:center;flex-wrap:wrap}}
.badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;padding:16px 24px}}
.stat-card{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:14px}}
.stat-val{{font-size:28px;font-weight:600;line-height:1}}
.stat-lbl{{font-size:11px;color:var(--mu);margin-top:4px}}
.section{{padding:0 24px 24px}}
.toolbar{{display:flex;gap:8px;margin:16px 0 12px;align-items:center;flex-wrap:wrap}}
.toolbar input{{background:var(--s2);border:1px solid var(--bd);border-radius:7px;padding:6px 12px;color:var(--tx);font-size:13px;flex:1;min-width:160px}}
.toolbar input:focus{{outline:none;border-color:var(--blu)}}
.flt{{padding:4px 10px;border-radius:6px;border:1px solid var(--bd);background:var(--s2);color:var(--mu);font-size:11px;cursor:pointer}}
.flt.on{{border-color:var(--blu);color:var(--tx)}}
#cnt{{color:var(--mu);font-size:12px;white-space:nowrap}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 12px;color:var(--mu);font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--bd);cursor:pointer;user-select:none;white-space:nowrap}}
th:hover{{color:var(--tx)}}
td{{padding:9px 12px;border-bottom:1px solid var(--bd);vertical-align:top}}
tr:hover td{{background:var(--s1)}}
tr.selected td{{background:var(--s2)}}
.mono{{font-family:monospace;font-size:12px}}
.age{{color:var(--mu);font-size:12px}}
.old{{color:var(--red)}}
.plan-panel{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:20px;margin:16px 24px;display:none}}
.plan-panel.show{{display:block}}
.plan-title{{font-size:14px;font-weight:600;margin-bottom:12px}}
.files-list{{display:flex;flex-direction:column;gap:3px;margin-top:8px}}
.file-chip{{background:var(--s2);border-radius:4px;padding:3px 8px;font-size:11px;font-family:monospace;color:var(--mu)}}
.checklist{{margin-top:12px;font-size:13px;line-height:1.8}}
.empty{{text-align:center;padding:40px;color:var(--mu)}}
</style>
</head>
<body>
<header>
  <h1>Feature Flag Graveyard Hunter</h1>
  <div class="stats">
    <span>{now}</span>
    <span>{report.files_scanned} files · {report.total_flags} flags</span>
    <span class="badge" style="background:var(--as);color:var(--amb)">{report.always_on} always-on</span>
    <span class="badge" style="background:var(--rs);color:var(--red)">{report.always_off} always-off</span>
    <span class="badge" style="background:var(--gs);color:var(--grn)">~{report.dead_lines} LOC removable</span>
  </div>
</header>

<div class="grid">
  <div class="stat-card">
    <div class="stat-val" style="color:var(--amb)">{report.graveyard_count}</div>
    <div class="stat-lbl">Graveyard flags</div>
  </div>
  <div class="stat-card">
    <div class="stat-val" style="color:var(--grn)">{sum(1 for f in report.flags if f.cleanup_complexity == 'simple')}</div>
    <div class="stat-lbl">Simple cleanup</div>
  </div>
  <div class="stat-card">
    <div class="stat-val" style="color:var(--amb)">{sum(1 for f in report.flags if f.cleanup_complexity == 'medium')}</div>
    <div class="stat-lbl">Medium cleanup</div>
  </div>
  <div class="stat-card">
    <div class="stat-val" style="color:var(--red)">{sum(1 for f in report.flags if f.cleanup_complexity == 'complex')}</div>
    <div class="stat-lbl">Complex cleanup</div>
  </div>
  <div class="stat-card">
    <div class="stat-val">{report.files_affected}</div>
    <div class="stat-lbl">Files affected</div>
  </div>
  <div class="stat-card">
    <div class="stat-val" style="color:var(--grn)">~{report.dead_lines}</div>
    <div class="stat-lbl">Removable LOC</div>
  </div>
</div>

<div class="section">
  <div class="toolbar">
    <input type="text" id="search" placeholder="Search flag name, file…" oninput="render()">
    <button class="flt on" onclick="setFlt('all',this)">All</button>
    <button class="flt" onclick="setFlt('always_on',this)">Always on</button>
    <button class="flt" onclick="setFlt('always_off',this)">Always off</button>
    <button class="flt" onclick="setFlt('simple',this)">Simple</button>
    <button class="flt" onclick="setFlt('old',this)">Oldest first</button>
    <span id="cnt"></span>
  </div>
  <table>
    <thead>
      <tr>
        <th onclick="sort('name')">Flag name</th>
        <th onclick="sort('state')">State</th>
        <th onclick="sort('cleanup_complexity')">Cleanup</th>
        <th onclick="sort('git_age_days')">Age</th>
        <th onclick="sort('usage_count')">Usages</th>
        <th onclick="sort('dead_lines')">Dead LOC</th>
        <th>Introduced by</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>

<div class="plan-panel" id="plan-panel">
  <div class="plan-title" id="plan-title"></div>
  <div id="plan-body"></div>
</div>

<script>
const DATA = {flags_json};
const STATE_COLOR = {json.dumps(STATE_COLOR)};
const CPLX_COLOR  = {json.dumps(COMPLEXITY_COLOR)};
let activeFlt = 'all';
let sortKey = 'git_age_days';
let sortAsc = false;
let selectedId = null;

function setFlt(f, btn) {{
  activeFlt = f;
  document.querySelectorAll('.flt').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  render();
}}

function sort(key) {{
  if (sortKey === key) sortAsc = !sortAsc;
  else {{ sortKey = key; sortAsc = false; }}
  render();
}}

function render() {{
  const q = document.getElementById('search').value.toLowerCase();
  let items = [...DATA];
  if (activeFlt === 'always_on')  items = items.filter(f => f.state === 'always_on');
  if (activeFlt === 'always_off') items = items.filter(f => f.state === 'always_off');
  if (activeFlt === 'simple')     items = items.filter(f => f.cleanup_complexity === 'simple');
  if (activeFlt === 'old')        items.sort((a,b) => b.git_age_days - a.git_age_days);
  else items.sort((a,b) => {{
    const va = a[sortKey] ?? 0, vb = b[sortKey] ?? 0;
    const d = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
    return sortAsc ? d : -d;
  }});
  if (q) items = items.filter(f =>
    f.name.includes(q) ||
    f.source_file.includes(q) ||
    (f.ticket_ref||'').includes(q) ||
    (f.introduced_by||'').includes(q)
  );
  document.getElementById('cnt').textContent = items.length + ' flags';
  const tbody = document.getElementById('tbody');
  if (!items.length) {{
    tbody.innerHTML = '<tr><td colspan="7" class="empty">No flags match these filters.</td></tr>';
    return;
  }}
  const sc = STATE_COLOR;
  const cc = CPLX_COLOR;
  tbody.innerHTML = items.map(f => {{
    const sc_ = sc[f.state] || sc.unknown;
    const cc_ = cc[f.cleanup_complexity] || cc.medium;
    const ageClass = f.git_age_days > 180 ? 'age old' : 'age';
    const ticket = f.ticket_ref ? ` <span style="color:var(--blu);font-size:11px">${{f.ticket_ref}}</span>` : '';
    return `<tr class="${{f.id === selectedId ? 'selected' : ''}}" onclick="selectFlag('${{f.id}}')" style="cursor:pointer">
      <td><span class="mono">${{f.name}}</span>${{ticket}}<div style="font-size:11px;color:var(--mu)">${{f.source_file}}</div></td>
      <td><span class="badge" style="background:${{sc_.bg}};color:${{sc_.fg}}">${{f.state.replace('_',' ')}}</span></td>
      <td><span class="badge" style="background:${{cc_.bg}};color:${{cc_.fg}}">${{f.cleanup_complexity}}</span></td>
      <td class="${{ageClass}}">${{f.git_age_days || '?'}}d</td>
      <td>${{f.usage_count}}</td>
      <td>${{f.dead_lines}}</td>
      <td style="color:var(--mu);font-size:12px">${{f.introduced_by || '—'}}</td>
    </tr>`;
  }}).join('');
}}

function selectFlag(id) {{
  const flag = DATA.find(f => f.id === id);
  if (!flag) return;
  selectedId = id;
  render();
  const panel = document.getElementById('plan-panel');
  panel.classList.add('show');
  document.getElementById('plan-title').textContent = `Cleanup plan: ${{flag.name}}`;
  const action = flag.state === 'always_on'
    ? 'Inline the enabled branch · remove else block · delete flag'
    : 'Remove the if block · keep else branch · delete flag';
  const files = (flag.affected_files||[]).map(f => `<div class="file-chip">${{f}}</div>`).join('');
  const checks = [
    `Remove flag definition from <code>${{flag.source_file}}</code>`,
    ...((flag.affected_files||[]).slice(0,6).map(f => `Clean up <code>${{f}}</code>`)),
    'Remove from feature flag management system',
    'Run test suite',
    `Grep for remaining references: <code>${{flag.name}}</code>`,
  ].map(c => `<div>☐ ${{c}}</div>`).join('');
  document.getElementById('plan-body').innerHTML = `
    <div style="color:var(--mu);font-size:13px;margin-bottom:10px">${{action}}</div>
    <div style="font-size:12px;color:var(--mu);margin-bottom:6px">Affected files</div>
    <div class="files-list">${{files || '<div class="file-chip">Config only</div>'}}</div>
    <div class="checklist">${{checks}}</div>
  `;
}}

render();
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
    return output_path
