"""
HTML report for Dead Code Analyzer.
Two panels: a file-sized treemap (D3) showing which files have the most dead code,
and a filterable dead symbol browser.
"""

import json
from datetime import datetime
from core.models import ScanResult, Confidence


CONF_COLOR = {
    'high':   '#E24B4A',
    'medium': '#EF9F27',
    'low':    '#378ADD',
}

KIND_ICON = {
    'class': 'C', 'method': 'M', 'function': 'F',
    'interface': 'I', 'component': '@', 'service': 'S',
    'enum': 'E', 'constant': 'K', 'property': 'P', 'field': 'f',
}


def generate_html_report(result: ScanResult, output_path: str = "dead-code-report.html"):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    dead_json = json.dumps([d.to_dict() for d in result.dead_symbols], indent=2)

    # Build treemap data: group dead symbols by file
    file_groups: dict[str, list] = {}
    for d in result.dead_symbols:
        file_groups.setdefault(d.symbol.file, []).append(d)

    treemap_data = {
        "name": "repo",
        "children": [
            {
                "name": fpath,
                "value": sum(max(d.symbol.lines_of_code, 5) for d in syms),
                "dead_count": len(syms),
                "high": sum(1 for d in syms if d.confidence.value == 'high'),
                "symbols": [d.symbol.name for d in syms[:5]],
            }
            for fpath, syms in sorted(file_groups.items(), key=lambda x: -len(x[1]))
        ]
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dead Code Report — {now}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
:root{{--bg:#0d1117;--s1:#161b22;--s2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#848d97;
  --red:#f85149;--amb:#e3b341;--blu:#58a6ff;--grn:#3fb950;
  --rs:#3d1a1a;--as:#3d2e0a;--bs:#0d2038;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);min-height:100vh}}
header{{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}}
header h1{{font-size:16px;font-weight:600}}
.stats{{display:flex;gap:16px;font-size:12px;color:var(--mu);align-items:center}}
.badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.bh{{background:var(--rs);color:var(--red)}}
.bm{{background:var(--as);color:var(--amb)}}
.bl{{background:var(--bs);color:var(--blu)}}
.bg{{background:#0d2b1a;color:#3fb950}}
.treemap-wrap{{padding:16px 24px}}
.treemap-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--mu);margin-bottom:10px}}
#treemap{{width:100%;height:240px;background:var(--s1);border-radius:10px;overflow:hidden}}
.tm-cell{{cursor:pointer;transition:opacity .15s}}
.tm-cell:hover{{opacity:.85}}
.section{{padding:0 24px 24px}}
.section-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--mu);margin-bottom:12px;margin-top:20px}}
.toolbar{{display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap}}
.toolbar input{{background:var(--s2);border:1px solid var(--bd);border-radius:7px;padding:6px 12px;color:var(--tx);font-size:13px;flex:1;min-width:180px}}
.toolbar input:focus{{outline:none;border-color:var(--blu)}}
.flt{{padding:4px 10px;border-radius:6px;border:1px solid var(--bd);background:var(--s2);color:var(--mu);font-size:11px;cursor:pointer}}
.flt.on{{border-color:var(--blu);color:var(--tx)}}
#cnt{{color:var(--mu);font-size:12px;white-space:nowrap}}
.dlist{{display:flex;flex-direction:column;gap:6px}}
.dc{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:12px 14px}}
.dc-top{{display:flex;gap:8px;align-items:flex-start;margin-bottom:5px}}
.dc-kind{{width:20px;height:20px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0;background:var(--s2);color:var(--mu)}}
.dc-name{{font-family:monospace;font-size:13px;font-weight:500;flex:1}}
.dc-file{{font-size:11px;font-family:monospace;color:var(--mu);margin-bottom:4px}}
.dc-exp{{font-size:12px;color:var(--mu);line-height:1.5}}
.dc-sup{{font-size:11px;color:var(--amb);margin-top:4px}}
.age{{font-size:11px;color:var(--mu)}}
.safe-tag{{background:#0d2b1a;color:#3fb950;font-size:10px;font-weight:700;padding:1px 6px;border-radius:4px}}
.empty{{text-align:center;padding:40px;color:var(--mu)}}
</style>
</head>
<body>
<header>
  <h1>Dead Code Analyzer</h1>
  <div class="stats">
    <span>{now}</span>
    <span>{result.files_scanned} files · {result.symbols_found} symbols</span>
    <span class="badge bh">{result.by_confidence.get('high',0)} high confidence</span>
    <span class="badge bm">{result.by_confidence.get('medium',0)} medium</span>
    <span class="badge bg">~{result.lines_recoverable} LOC recoverable</span>
  </div>
</header>

<div class="treemap-wrap">
  <div class="treemap-title">Dead code by file — area = recoverable lines</div>
  <div id="treemap"></div>
</div>

<div class="section">
  <div class="section-title">Dead symbols</div>
  <div class="toolbar">
    <input type="text" id="search" placeholder="Search by name, file…" oninput="render()">
    <button class="flt on"  onclick="setFlt('all',this)">All</button>
    <button class="flt"     onclick="setFlt('high',this)">High confidence</button>
    <button class="flt"     onclick="setFlt('medium',this)">Medium</button>
    <button class="flt"     onclick="setFlt('safe',this)">Safe to delete</button>
    <button class="flt"     onclick="setFlt('class',this)">Classes</button>
    <button class="flt"     onclick="setFlt('method',this)">Methods</button>
    <span id="cnt"></span>
  </div>
  <div class="dlist" id="dlist"></div>
</div>

<script>
const DATA = {dead_json};
const TREEMAP_DATA = {json.dumps(treemap_data)};
const CONF_COLOR = {json.dumps(CONF_COLOR)};
const KIND_ICON  = {json.dumps(KIND_ICON)};
let activeFlt = 'all';
let activeFile = null;

function setFlt(f, btn) {{
  activeFlt = f; activeFile = null;
  document.querySelectorAll('.flt').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  render();
}}

function render() {{
  const q = document.getElementById('search').value.toLowerCase();
  let items = DATA;
  if (activeFile)     items = items.filter(d => d.file === activeFile);
  if (activeFlt === 'high')   items = items.filter(d => d.confidence === 'high');
  if (activeFlt === 'medium') items = items.filter(d => d.confidence === 'medium');
  if (activeFlt === 'safe')   items = items.filter(d => d.safe_to_delete);
  if (activeFlt === 'class')  items = items.filter(d => d.kind === 'class');
  if (activeFlt === 'method') items = items.filter(d => d.kind === 'method');
  if (q) items = items.filter(d =>
    d.name.toLowerCase().includes(q) ||
    d.file.toLowerCase().includes(q) ||
    (d.namespace||'').toLowerCase().includes(q)
  );
  document.getElementById('cnt').textContent = items.length + ' shown';
  const list = document.getElementById('dlist');
  if (!items.length) {{
    list.innerHTML = '<div class="empty">No dead symbols match these filters.</div>';
    return;
  }}
  list.innerHTML = items.slice(0,100).map(d => {{
    const color = CONF_COLOR[d.confidence] || '#848d97';
    const icon  = KIND_ICON[d.kind] || '?';
    const age   = d.git_age_days > 0 ? `<span class="age">Last changed ${d.git_age_days}d ago</span>` : '';
    const safe  = d.safe_to_delete ? '<span class="safe-tag">safe to delete</span>' : '';
    const sups  = d.suppressions?.length ? `<div class="dc-sup">Caution: ${{d.suppressions[0]}}</div>` : '';
    return `<div class="dc">
      <div class="dc-top">
        <div class="dc-kind">${{icon}}</div>
        <span class="dc-name">${{d.name}}</span>
        <span class="badge" style="background:${{color}}22;color:${{color}};font-size:10px">${{d.confidence}} ${{d.confidence_pct}}%</span>
        ${{safe}}
      </div>
      <div class="dc-file">${{d.file}}:${{d.line}} · ${{d.kind}} ${{d.class_name ? '· in ' + d.class_name : ''}}</div>
      <div class="dc-exp">${{d.explanation}}</div>
      ${{sups}}
      ${{age}}
    </div>`;
  }}).join('');
  if (items.length > 100) {{
    list.innerHTML += `<div class="empty">Showing 100 of ${{items.length}}. Use filters to narrow down.</div>`;
  }}
}}
render();

// D3 Treemap
const container = document.getElementById('treemap');
const W = container.clientWidth || 680;
const H = 240;

const svg = d3.select('#treemap').append('svg')
  .attr('width', W).attr('height', H);

const root = d3.hierarchy(TREEMAP_DATA)
  .sum(d => d.value || 0)
  .sort((a, b) => b.value - a.value);

d3.treemap().size([W, H]).padding(2)(root);

const COLORS = ['#3d1a1a','#3d2e0a','#0d2038','#0d2b1a'];
const TEXT_C = ['#f85149','#e3b341','#58a6ff','#3fb950'];

svg.selectAll('g').data(root.leaves()).join('g')
  .attr('transform', d => `translate(${{d.x0}},${{d.y0}})`)
  .attr('class', 'tm-cell')
  .on('click', (e, d) => {{
    activeFile = d.data.name;
    activeFlt = 'all';
    document.querySelectorAll('.flt').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.flt')[0].classList.add('on');
    render();
  }})
  .call(g => {{
    const ci = d => Math.min(d.data.high || 0, 3);
    g.append('rect')
      .attr('width',  d => Math.max(d.x1 - d.x0, 0))
      .attr('height', d => Math.max(d.y1 - d.y0, 0))
      .attr('rx', 4)
      .attr('fill',   d => COLORS[ci(d)])
      .attr('stroke', d => TEXT_C[ci(d)])
      .attr('stroke-width', 0.5);
    g.append('text')
      .attr('x', 6).attr('y', 14)
      .attr('fill', d => TEXT_C[ci(d)])
      .attr('font-size', 11)
      .attr('font-family', 'monospace')
      .text(d => {{
        const w = d.x1 - d.x0;
        const name = d.data.name.split('/').pop();
        return w > 60 ? name.slice(0, Math.floor(w / 7)) : '';
      }});
    g.append('text')
      .attr('x', 6).attr('y', 27)
      .attr('fill', d => TEXT_C[ci(d)])
      .attr('font-size', 10)
      .attr('opacity', .7)
      .text(d => d.x1 - d.x0 > 80 ? `${{d.data.dead_count}} dead` : '');
  }});
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
    return output_path
