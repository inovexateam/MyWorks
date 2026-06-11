"""
Generates the Architectural Drift Detector HTML report.
Two panels: a drift score timeline (Chart.js line graph) and a
filterable violation browser.
"""

import json
from datetime import datetime
from core.models import ScanResult, DriftTimeline, Severity, RuleKind


SEV_COLOR = {
    'error':   '#E24B4A',
    'warning': '#EF9F27',
    'info':    '#378ADD',
}

KIND_LABEL = {
    'layer_dependency': 'Layer boundary',
    'naming':           'Naming',
    'no_dependency':    'Forbidden dep',
    'no_circular':      'Circular dep',
    'max_coupling':     'Coupling',
    'domain_isolation': 'Domain isolation',
}


def generate_html_report(
    result: ScanResult,
    timeline: DriftTimeline | None,
    output_path: str = "arch-drift-report.html",
):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # Build timeline chart data
    if timeline and timeline.snapshots:
        chart_labels = json.dumps([s.commit_date + ' ' + s.commit_sha[:6] for s in timeline.snapshots])
        chart_errors  = json.dumps([s.errors   for s in timeline.snapshots])
        chart_warnings= json.dumps([s.warnings for s in timeline.snapshots])
        chart_scores  = json.dumps([s.score    for s in timeline.snapshots])
    else:
        chart_labels  = json.dumps([now])
        chart_errors  = json.dumps([result.drift_score.errors])
        chart_warnings= json.dumps([result.drift_score.warnings])
        chart_scores  = json.dumps([result.drift_score.score])

    # Build violation table data
    violations_json = json.dumps([
        {
            'id':          v.id,
            'kind':        v.rule_kind.value,
            'kind_label':  KIND_LABEL.get(v.rule_kind.value, v.rule_kind.value),
            'severity':    v.severity.value,
            'message':     v.message,
            'file':        v.file,
            'line':        v.line,
            'from_layer':  v.from_layer,
            'to_layer':    v.to_layer,
            'import_path': v.import_path,
            'is_new':      v.id in {n.id for n in result.new_violations},
            'age':         v.age_commits,
        }
        for v in result.violations
    ], indent=2)

    trend = timeline.trend() if timeline else 'stable'
    trend_icon  = {'degrading': '▲', 'improving': '▼', 'stable': '●'}[trend]
    trend_color = {'degrading': '#E24B4A', 'improving': '#1D9E75', 'stable': '#EF9F27'}[trend]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arch Drift Report — {now}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{{--bg:#0d1117;--s1:#161b22;--s2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#848d97;
  --red:#f85149;--amb:#e3b341;--blu:#58a6ff;--grn:#3fb950;
  --rs:#3d1a1a;--as:#3d2e0a;--bs:#0d2038;--gs:#0d2b1a;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx)}}
header{{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}}
header h1{{font-size:16px;font-weight:600}}
.meta{{color:var(--mu);font-size:12px;display:flex;gap:16px;align-items:center}}
.trend{{font-weight:700;font-size:14px}}
.score-big{{font-size:28px;font-weight:700}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 24px}}
.card{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:16px}}
.card-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--mu);margin-bottom:12px}}
.stat-row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--bd);font-size:13px}}
.stat-row:last-child{{border:none}}
.badge{{padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;display:inline-block}}
.e{{background:var(--rs);color:var(--red)}}.w{{background:var(--as);color:var(--amb)}}.i{{background:var(--bs);color:var(--blu)}}
.chart-wrap{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:16px;margin:0 24px 16px}}
.chart-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--mu);margin-bottom:12px}}
.violations{{padding:0 24px 24px}}
.toolbar{{display:flex;gap:10px;margin-bottom:12px;align-items:center}}
.toolbar input{{background:var(--s2);border:1px solid var(--bd);border-radius:7px;padding:7px 12px;color:var(--tx);font-size:13px;flex:1}}
.toolbar input:focus{{outline:none;border-color:var(--blu)}}
.filter-btn{{padding:5px 12px;border-radius:6px;border:1px solid var(--bd);background:var(--s2);color:var(--mu);font-size:12px;cursor:pointer;transition:all .15s}}
.filter-btn.active{{border-color:var(--blu);color:var(--tx)}}
#count{{color:var(--mu);font-size:12px;white-space:nowrap}}
.vlist{{display:flex;flex-direction:column;gap:6px}}
.vcard{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:12px 14px}}
.vcard.is-new{{border-left:3px solid var(--red)}}
.vcard-top{{display:flex;align-items:flex-start;gap:8px;margin-bottom:6px}}
.vmsg{{flex:1;font-size:13px;line-height:1.4}}
.vfile{{font-size:11px;font-family:monospace;color:var(--mu)}}
.layer-arrow{{color:var(--mu);font-size:11px;margin-top:4px}}
.new-tag{{background:var(--rs);color:var(--red);font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px;white-space:nowrap}}
.layer-chip{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:11px;background:var(--s2);color:var(--mu)}}
.empty{{text-align:center;padding:40px;color:var(--mu)}}
canvas{{max-height:200px}}
</style>
</head>
<body>
<header>
  <h1>Architectural Drift Detector</h1>
  <div class="meta">
    <span>{now}</span>
    <span>{result.files_scanned} files · {result.import_edges} import edges</span>
    <span class="score-big" style="color:{SEV_COLOR.get('error','#fff') if result.drift_score.score >= 40 else '#1D9E75'}">{result.drift_score.score}</span>
    <span>/ 100</span>
    <span class="trend" style="color:{trend_color}">{trend_icon} {trend}</span>
  </div>
</header>

<div class="grid">
  <div class="card">
    <div class="card-title">Violations</div>
    <div class="stat-row"><span>Errors</span><span class="badge e">{result.drift_score.errors}</span></div>
    <div class="stat-row"><span>Warnings</span><span class="badge w">{result.drift_score.warnings}</span></div>
    <div class="stat-row"><span>Info</span><span class="badge i">{result.drift_score.infos}</span></div>
    <div class="stat-row"><span>New this run</span><span style="color:var(--red);font-weight:600">{len(result.new_violations)}</span></div>
    <div class="stat-row"><span>Resolved</span><span style="color:var(--grn);font-weight:600">{len(result.resolved)}</span></div>
  </div>
  <div class="card">
    <div class="card-title">Layers detected</div>
    {''.join(f'<div class="stat-row"><span class="layer-chip">{layer}</span><span style="color:var(--mu);font-size:12px">{len(files)} files</span></div>' for layer, files in result.layers_found.items())}
    {'<div class="stat-row"><span style="color:var(--red);font-size:12px">Circular chains detected</span><span style="color:var(--red)">' + str(len(result.circular_chains)) + '</span></div>' if result.circular_chains else ''}
  </div>
</div>

<div class="chart-wrap">
  <div class="chart-title">Drift score over time</div>
  <canvas id="drift-chart"></canvas>
</div>

<div class="violations">
  <div class="toolbar">
    <input type="text" id="search" placeholder="Search violations…" oninput="filter()">
    <button class="filter-btn active" onclick="setKind(null,this)">All</button>
    <button class="filter-btn" onclick="setKind('layer_dependency',this)">Layer</button>
    <button class="filter-btn" onclick="setKind('no_dependency',this)">Forbidden</button>
    <button class="filter-btn" onclick="setKind('naming',this)">Naming</button>
    <button class="filter-btn" onclick="setKind('domain_isolation',this)">Domain</button>
    <button class="filter-btn" onclick="setKind('no_circular',this)">Circular</button>
    <span id="count"></span>
  </div>
  <div class="vlist" id="vlist"></div>
</div>

<script>
const VIOLATIONS = {violations_json};
let activeKind = null;
let activeSearch = '';

function setKind(kind, btn) {{
  activeKind = kind;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  filter();
}}

function filter() {{
  activeSearch = document.getElementById('search').value.toLowerCase();
  let items = VIOLATIONS;
  if (activeKind) items = items.filter(v => v.kind === activeKind);
  if (activeSearch) items = items.filter(v =>
    v.message.toLowerCase().includes(activeSearch) ||
    v.file.toLowerCase().includes(activeSearch) ||
    v.from_layer.toLowerCase().includes(activeSearch)
  );
  document.getElementById('count').textContent = items.length + ' shown';
  const SEV_COLORS = {{error:'var(--red)',warning:'var(--amb)',info:'var(--blu)'}};
  const list = document.getElementById('vlist');
  if (!items.length) {{
    list.innerHTML = '<div class="empty">No violations match these filters.</div>';
    return;
  }}
  list.innerHTML = items.map(v => `
    <div class="vcard ${{v.is_new ? 'is-new' : ''}}">
      <div class="vcard-top">
        <span class="badge ${{v.severity[0]}}">${{v.severity}}</span>
        <span class="vmsg">${{v.message}}</span>
        ${{v.is_new ? '<span class="new-tag">NEW</span>' : ''}}
      </div>
      <div class="vfile">${{v.file}}${{v.line ? ':' + v.line : ''}}</div>
      ${{v.from_layer && v.to_layer ? `<div class="layer-arrow">${{v.from_layer}} → ${{v.to_layer}}</div>` : ''}}
      ${{v.import_path ? `<div class="vfile" style="margin-top:3px">${{v.import_path.slice(0,100)}}</div>` : ''}}
    </div>`).join('');
}}

filter();

// Chart.js timeline
const ctx = document.getElementById('drift-chart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: {chart_labels},
    datasets: [
      {{
        label: 'Drift score',
        data: {chart_scores},
        borderColor: '#E24B4A',
        backgroundColor: 'rgba(232,74,74,.1)',
        tension: .3, fill: true, pointRadius: 3,
      }},
      {{
        label: 'Errors',
        data: {chart_errors},
        borderColor: '#EF9F27',
        backgroundColor: 'transparent',
        tension: .3, pointRadius: 2, borderDash: [4,3],
      }},
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color: '#848d97', font: {{ size: 11 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#848d97', font: {{ size: 10 }}, maxTicksLimit: 10 }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#848d97', font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }}, min: 0, max: 100 }},
    }}
  }}
}});
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
    return output_path
