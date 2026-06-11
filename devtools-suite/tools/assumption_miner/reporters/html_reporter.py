"""
Generates a rich interactive HTML report — the Assumption Registry browser.
Dark themed, filterable by risk/kind, shows all assumptions with code snippets.
"""

import json
from datetime import datetime
from core.models import ScanResult, RiskLevel, AssumptionKind


RISK_COLORS = {
    'critical': '#E24B4A',
    'high':     '#EF9F27',
    'medium':   '#378ADD',
    'low':      '#1D9E75',
}

KIND_LABELS = {
    'null_safety':       'Null safety',
    'non_empty':         'Non-empty',
    'range':             'Range',
    'ordering':          'Ordering',
    'type_narrowing':    'Type cast',
    'format':            'Format',
    'invariant':         'Invariant',
    'comment_explicit':  'Explicit comment',
    'external_contract': 'External contract',
    'environment':       'Environment',
}


def generate_html_report(result: ScanResult, output_path: str = "assumption-report.html"):
    assumptions_json = json.dumps([
        {
            'id': a.id,
            'statement': a.statement,
            'file': a.location.file,
            'line': a.location.line,
            'snippet': a.location.snippet,
            'kind': a.kind.value,
            'risk': a.risk.value,
            'confidence': round(a.confidence * 100),
            'has_test': a.has_test,
            'symbol': a.symbol,
            'contradicted_by': a.contradicted_by,
        }
        for a in result.assumptions
    ], indent=2)

    contradictions_json = json.dumps([
        {
            'statement': c.assumption.statement,
            'assumption_file': c.assumption.location.file,
            'assumption_line': c.assumption.location.line,
            'contradiction_file': c.contradiction_file,
            'contradiction_line': c.contradiction_line,
            'snippet': c.contradiction_snippet,
            'severity': c.severity,
        }
        for c in result.contradictions
    ], indent=2)

    by_kind = result.by_kind
    by_risk = result.by_risk

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Assumption Registry — {datetime.now().strftime('%Y-%m-%d')}</title>
<style>
:root {{
  --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a;
  --border: #2a2d3e; --text: #e2e8f0; --muted: #64748b;
  --red: #E24B4A; --amber: #EF9F27; --green: #1D9E75; --blue: #378ADD;
  --red-s: rgba(226,75,74,.15); --amber-s: rgba(239,159,39,.15);
  --green-s: rgba(29,158,117,.15); --blue-s: rgba(55,138,221,.15);
  --mono: 'Cascadia Code', 'Fira Code', monospace;
}}
* {{ box-sizing:border-box; margin:0; padding:0 }}
body {{ background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif; font-size:14px; }}
header {{ padding:20px 28px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }}
header h1 {{ font-size:18px; font-weight:600 }}
.meta {{ color:var(--muted); font-size:13px }}
.layout {{ display:grid; grid-template-columns:260px 1fr; height:calc(100vh - 65px) }}
.sidebar {{ background:var(--surface); border-right:1px solid var(--border); padding:16px; overflow-y:auto; display:flex; flex-direction:column; gap:14px }}
.panel {{ background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:14px }}
.panel-title {{ font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.7px; color:var(--muted); margin-bottom:10px }}
.risk-row {{ display:flex; justify-content:space-between; align-items:center; padding:7px 0; border-bottom:1px solid var(--border); cursor:pointer }}
.risk-row:last-child {{ border:none }}
.risk-row:hover {{ opacity:.8 }}
.risk-badge {{ padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600 }}
.kind-row {{ display:flex; justify-content:space-between; align-items:center; padding:5px 0; cursor:pointer; font-size:13px }}
.kind-row:hover {{ opacity:.8 }}
.count {{ color:var(--muted); font-size:12px }}
.contradiction-banner {{ background:var(--red-s); border:1px solid var(--red); border-radius:8px; padding:12px 14px; margin-bottom:8px }}
.contradiction-banner .ctitle {{ color:var(--red); font-weight:600; font-size:13px; margin-bottom:4px }}
.contradiction-banner .cmeta {{ font-size:12px; color:var(--muted) }}
.main {{ display:flex; flex-direction:column; overflow:hidden }}
.toolbar {{ padding:12px 20px; border-bottom:1px solid var(--border); display:flex; gap:10px; align-items:center }}
.toolbar input {{ background:var(--surface); border:1px solid var(--border); border-radius:7px; padding:7px 12px; color:var(--text); font-size:13px; flex:1 }}
.toolbar input:focus {{ outline:none; border-color:var(--blue) }}
.btn-clear {{ background:var(--surface); border:1px solid var(--border); border-radius:7px; padding:7px 12px; color:var(--muted); font-size:13px; cursor:pointer }}
.btn-clear:hover {{ color:var(--text) }}
#count-label {{ color:var(--muted); font-size:13px; white-space:nowrap }}
.list {{ flex:1; overflow-y:auto; padding:12px 20px; display:flex; flex-direction:column; gap:8px }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; cursor:pointer; transition:border-color .15s }}
.card:hover {{ border-color:var(--blue) }}
.card.contradiction {{ border-color:var(--red) !important }}
.card-header {{ display:flex; align-items:flex-start; gap:10px; margin-bottom:6px }}
.card-statement {{ font-size:14px; line-height:1.4; flex:1 }}
.card-meta {{ font-size:12px; color:var(--muted); display:flex; gap:14px; flex-wrap:wrap }}
.card-snippet {{ margin-top:8px; background:var(--bg); border-radius:6px; padding:8px 10px; font-family:var(--mono); font-size:12px; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap }}
.pill {{ padding:2px 7px; border-radius:4px; font-size:11px; font-weight:500 }}
.pill.critical {{ background:var(--red-s); color:var(--red) }}
.pill.high {{ background:var(--amber-s); color:var(--amber) }}
.pill.medium {{ background:var(--blue-s); color:var(--blue) }}
.pill.low {{ background:var(--green-s); color:var(--green) }}
.tested {{ color:var(--green); font-size:11px }}
.untested {{ color:var(--red); font-size:11px }}
.empty {{ text-align:center; padding:60px 20px; color:var(--muted) }}
</style>
</head>
<body>
<header>
  <h1>Assumption Registry</h1>
  <div class="meta">
    {result.files_scanned} files · {result.total_assumptions} assumptions · 
    {len(result.contradictions)} contradictions · {datetime.now().strftime('%Y-%m-%d %H:%M')}
  </div>
</header>
<div class="layout">
  <aside class="sidebar">
    <div class="panel">
      <div class="panel-title">By risk</div>
      {''.join(f'''<div class="risk-row" onclick="filterRisk('{r}')">
        <span>{r.title()}</span>
        <span class="risk-badge pill {r}" style="">{by_risk.get(r, 0)}</span>
      </div>''' for r in ['critical','high','medium','low'])}
      <div class="risk-row" onclick="filterRisk(null)" style="margin-top:4px">
        <span style="color:var(--muted)">Show all</span>
      </div>
    </div>
    <div class="panel">
      <div class="panel-title">By kind</div>
      {''.join(f'''<div class="kind-row" onclick="filterKind('{k}')">
        <span>{KIND_LABELS.get(k, k)}</span>
        <span class="count">{by_kind.get(k, 0)}</span>
      </div>''' for k in KIND_LABELS if by_kind.get(k, 0) > 0)}
    </div>
    {'<div class="panel"><div class="panel-title">Contradictions</div>' + 
     ''.join(f'''<div class="contradiction-banner">
       <div class="ctitle">{c.assumption.statement[:60]}...</div>
       <div class="cmeta">{c.contradiction_file}:{c.contradiction_line}</div>
     </div>''' for c in result.contradictions) + '</div>'
     if result.contradictions else ''}
  </aside>
  <main class="main">
    <div class="toolbar">
      <input type="text" id="search" placeholder="Search assumptions..." oninput="filterSearch(this.value)">
      <button class="btn-clear" onclick="clearFilters()">Clear filters</button>
      <span id="count-label"></span>
    </div>
    <div class="list" id="list"></div>
  </main>
</div>
<script>
const DATA = {assumptions_json};
const CONTRADICTIONS = {contradictions_json};

let activeRisk = null;
let activeKind = null;
let activeSearch = '';

function filterRisk(r) {{ activeRisk = r; render(); }}
function filterKind(k) {{ activeKind = k; render(); }}
function filterSearch(s) {{ activeSearch = s.toLowerCase(); render(); }}
function clearFilters() {{
  activeRisk = null; activeKind = null; activeSearch = '';
  document.getElementById('search').value = '';
  render();
}}

const CONTRA_IDS = new Set(CONTRADICTIONS.map(c => c.assumption_file + ':' + c.assumption_line));

function render() {{
  let items = DATA;
  if (activeRisk) items = items.filter(a => a.risk === activeRisk);
  if (activeKind) items = items.filter(a => a.kind === activeKind);
  if (activeSearch) items = items.filter(a =>
    a.statement.toLowerCase().includes(activeSearch) ||
    a.file.toLowerCase().includes(activeSearch) ||
    a.symbol.toLowerCase().includes(activeSearch)
  );
  items.sort((a,b) => {{
    const order = ['critical','high','medium','low'];
    return order.indexOf(a.risk) - order.indexOf(b.risk);
  }});
  const list = document.getElementById('list');
  document.getElementById('count-label').textContent = items.length + ' shown';
  if (!items.length) {{
    list.innerHTML = '<div class="empty">No assumptions match these filters.</div>';
    return;
  }}
  list.innerHTML = items.map(a => {{
    const isContra = CONTRA_IDS.has(a.file + ':' + a.line);
    const kindLabel = {json.dumps(KIND_LABELS)};
    return `<div class="card ${{isContra ? 'contradiction' : ''}}">
      <div class="card-header">
        <span class="pill ${{a.risk}}">${{a.risk}}</span>
        <span class="card-statement">${{a.statement}}</span>
        <span class="${{a.has_test ? 'tested' : 'untested'}}">${{a.has_test ? '✓ tested' : '✗ no test'}}</span>
      </div>
      <div class="card-meta">
        <span>${{a.file}}:${{a.line}}</span>
        <span>${{kindLabel[a.kind] || a.kind}}</span>
        <span>confidence ${{a.confidence}}%</span>
        ${{isContra ? '<span style="color:var(--red)">⚡ contradicted in this PR</span>' : ''}}
      </div>
      ${{a.snippet ? `<div class="card-snippet">${{a.snippet.replace(/</g,'&lt;')}}</div>` : ''}}
    </div>`;
  }}).join('');
}}

render();
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
    return output_path
