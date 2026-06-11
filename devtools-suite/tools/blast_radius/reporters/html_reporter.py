"""
Generates a rich interactive HTML flame-graph report.
Self-contained single file — no server needed, open in any browser.
Two views: force-directed graph (default) and sortable table.
"""

import json
from datetime import datetime
from core.dependency_graph import BlastRadiusResult, BlastNode


def node_to_dict(node: BlastNode, depth: int = 0) -> dict:
    risk = node.risk_score
    color = (
        "#E24B4A" if risk >= 70 else
        "#EF9F27" if risk >= 40 else
        "#378ADD" if risk >= 20 else
        "#1D9E75"
    )
    label = "critical" if risk >= 70 else "high" if risk >= 40 else "medium" if risk >= 20 else "low"
    return {
        "id": f"{node.symbol_name}::{node.file}::{depth}",
        "name": node.symbol_name,
        "file": node.file,
        "kind": node.kind,
        "risk": risk,
        "label": label,
        "covered": node.has_test_coverage,
        "color": color,
        "depth": depth,
        "children": [node_to_dict(c, depth + 1) for c in node.direct_callers[:10]]
    }


def generate_html_report(result: BlastRadiusResult, output_path: str = "blast-radius.html"):
    graph_data = [node_to_dict(n) for n in result.blast_nodes]
    risk = result.risk_summary

    table_rows = []
    for n in result.blast_nodes:
        label = "critical" if n.risk_score >= 70 else "high" if n.risk_score >= 40 else "medium" if n.risk_score >= 20 else "low"
        for caller in n.direct_callers:
            c_label = "critical" if caller.risk_score >= 70 else "high" if caller.risk_score >= 40 else "medium" if caller.risk_score >= 20 else "low"
            table_rows.append({
                "changed": n.symbol_name,
                "changed_file": n.file,
                "affected": caller.symbol_name,
                "affected_file": caller.file,
                "risk": caller.risk_score,
                "risk_label": c_label,
                "covered": caller.has_test_coverage,
            })
    table_rows.sort(key=lambda r: -r["risk"])

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blast Radius — {now}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
:root{{--bg:#0d1117;--s1:#161b22;--s2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#848d97;
  --red:#f85149;--amb:#e3b341;--blu:#58a6ff;--grn:#3fb950;
  --rs:#3d1a1a;--as:#3d2e0a;--bs:#0d2038;--gs:#0d2b1a;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);height:100vh;display:flex;flex-direction:column}}
header{{padding:14px 24px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center;flex-shrink:0}}
header h1{{font-size:16px;font-weight:600;letter-spacing:-.3px}}
.meta{{color:var(--mu);font-size:12px;display:flex;gap:18px}}
.badge{{display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600}}
.badge.critical{{background:var(--rs);color:var(--red)}}
.badge.high{{background:var(--as);color:var(--amb)}}
.badge.medium{{background:var(--bs);color:var(--blu)}}
.badge.low{{background:var(--gs);color:var(--grn)}}
.body{{display:flex;flex:1;overflow:hidden}}
.sidebar{{width:240px;background:var(--s1);border-right:1px solid var(--bd);overflow-y:auto;padding:14px;flex-shrink:0;display:flex;flex-direction:column;gap:12px}}
.panel{{background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:12px}}
.panel-title{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--mu);margin-bottom:8px}}
.stat{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--bd);font-size:13px}}
.stat:last-child{{border:none}}
.stat-val{{font-weight:600}}
.risk-meter{{display:flex;gap:4px;margin-bottom:6px}}
.risk-seg{{flex:1;height:6px;border-radius:3px;cursor:pointer;transition:opacity .15s}}
.risk-seg:hover{{opacity:.7}}
.file-chip{{background:var(--s2);border-radius:4px;padding:3px 7px;font-size:11px;font-family:monospace;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--mu)}}
.uncov{{display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid var(--bd);font-size:12px}}
.uncov:last-child{{border:none}}
.dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.main{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
.tabs{{display:flex;padding:0 20px;border-bottom:1px solid var(--bd);gap:0;flex-shrink:0}}
.tab{{padding:10px 16px;font-size:13px;cursor:pointer;border-bottom:2px solid transparent;color:var(--mu);transition:color .15s}}
.tab.active{{color:var(--tx);border-bottom-color:var(--blu)}}
.tab:hover{{color:var(--tx)}}
.view{{flex:1;overflow:hidden;display:none}}
.view.active{{display:flex;flex-direction:column}}
#graph-view{{position:relative}}
svg#graph{{width:100%;height:100%}}
.tooltip{{position:absolute;background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:10px 14px;pointer-events:none;opacity:0;transition:opacity .12s;max-width:280px;font-size:12px;line-height:1.6;z-index:10}}
.tooltip .tn{{font-weight:600;font-size:13px;margin-bottom:3px}}
.legend{{position:absolute;bottom:14px;right:14px;background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:10px 14px;font-size:11px}}
.leg-item{{display:flex;align-items:center;gap:7px;padding:2px 0}}
.leg-dot{{width:9px;height:9px;border-radius:50%}}
#table-view{{overflow-y:auto;padding:16px 20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 12px;color:var(--mu);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--bd);cursor:pointer;user-select:none}}
th:hover{{color:var(--tx)}}
td{{padding:9px 12px;border-bottom:1px solid var(--bd)}}
tr:hover td{{background:var(--s1)}}
.mono{{font-family:monospace;font-size:11px;color:var(--mu)}}
.risk-bar-wrap{{display:flex;align-items:center;gap:8px}}
.risk-bar-bg{{width:60px;height:5px;background:var(--s2);border-radius:3px;overflow:hidden}}
.risk-bar-fill{{height:100%;border-radius:3px;transition:width .3s}}
.cov-yes{{color:var(--grn);font-size:11px}}
.cov-no{{color:var(--red);font-size:11px}}
</style>
</head>
<body>
<header>
  <h1>Blast Radius Visualizer</h1>
  <div class="meta">
    <span>{now}</span>
    <span>{result.total_files_affected} files affected</span>
    <span>{result.total_symbols_affected} symbols impacted</span>
    <span class="badge critical">{risk.get('critical',0)} critical</span>
    <span class="badge high">{risk.get('high',0)} high</span>
  </div>
</header>
<div class="body">
  <aside class="sidebar">
    <div class="panel">
      <div class="panel-title">Risk overview</div>
      <div class="risk-meter">
        <div class="risk-seg" style="background:var(--red);flex:{max(risk.get('critical',0),1)}" title="Critical" onclick="filterTable('critical')"></div>
        <div class="risk-seg" style="background:var(--amb);flex:{max(risk.get('high',0),1)}" title="High" onclick="filterTable('high')"></div>
        <div class="risk-seg" style="background:var(--blu);flex:{max(risk.get('medium',0),1)}" title="Medium" onclick="filterTable('medium')"></div>
        <div class="risk-seg" style="background:var(--grn);flex:{max(risk.get('low',0),1)}" title="Low" onclick="filterTable('low')"></div>
      </div>
      <div class="stat"><span>Critical</span><span class="stat-val" style="color:var(--red)">{risk.get('critical',0)}</span></div>
      <div class="stat"><span>High</span><span class="stat-val" style="color:var(--amb)">{risk.get('high',0)}</span></div>
      <div class="stat"><span>Medium</span><span class="stat-val" style="color:var(--blu)">{risk.get('medium',0)}</span></div>
      <div class="stat"><span>Low</span><span class="stat-val" style="color:var(--grn)">{risk.get('low',0)}</span></div>
    </div>
    <div class="panel">
      <div class="panel-title">Changed symbols</div>
      {''.join(f'<div class="file-chip">{s.name} <span style="opacity:.5">({s.kind})</span></div>' for s in result.changed_symbols[:12])}
    </div>
    <div class="panel">
      <div class="panel-title">Uncovered paths</div>
      {''.join(f'<div class="uncov"><div class="dot" style="background:var(--red)"></div><span>{n.symbol_name}</span></div>' for n in result.uncovered_symbols[:8]) or '<div class="uncov"><div class="dot" style="background:var(--grn)"></div><span>All paths covered</span></div>'}
    </div>
  </aside>
  <main class="main">
    <div class="tabs">
      <div class="tab active" onclick="switchTab('graph')">Flame graph</div>
      <div class="tab" onclick="switchTab('table')">Impact table</div>
    </div>
    <div class="view active" id="graph-view">
      <svg id="graph"></svg>
      <div class="tooltip" id="tip">
        <div class="tn" id="tip-name"></div>
        <div id="tip-file" style="color:var(--mu);margin-bottom:5px"></div>
        <div id="tip-risk"></div>
        <div id="tip-cov" style="margin-top:3px"></div>
      </div>
      <div class="legend">
        <div class="leg-item"><div class="leg-dot" style="background:var(--red)"></div>Critical (&ge;70)</div>
        <div class="leg-item"><div class="leg-dot" style="background:var(--amb)"></div>High (40-69)</div>
        <div class="leg-item"><div class="leg-dot" style="background:var(--blu)"></div>Medium (20-39)</div>
        <div class="leg-item"><div class="leg-dot" style="background:var(--grn)"></div>Low (&lt;20)</div>
        <div class="leg-item" style="margin-top:5px;color:var(--mu)">Dashed = no test coverage</div>
      </div>
    </div>
    <div class="view" id="table-view">
      <table id="impact-table">
        <thead>
          <tr>
            <th onclick="sortTable('changed')">Changed symbol</th>
            <th onclick="sortTable('affected')">Affected symbol</th>
            <th onclick="sortTable('risk')">Risk score</th>
            <th onclick="sortTable('covered')">Coverage</th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
  </main>
</div>
<script>
const GRAPH = {json.dumps(graph_data, indent=2)};
const TABLE = {json.dumps(table_rows, indent=2)};

let activeFilter = null;
let sortKey = 'risk';
let sortAsc = false;

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', ['graph','table'][i] === name));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(name+'-view').classList.add('active');
  if (name === 'graph') renderGraph();
  if (name === 'table') renderTable();
}}

function filterTable(label) {{
  activeFilter = activeFilter === label ? null : label;
  switchTab('table');
}}

// ── Force-directed graph ──────────────────────────────────────────────────────
function renderGraph() {{
  const container = document.getElementById('graph-view');
  const W = container.clientWidth, H = container.clientHeight;
  const svg = d3.select('#graph').attr('viewBox', `0 0 ${{W}} ${{H}}`);
  svg.selectAll('*').remove();

  // Flatten tree into nodes+links
  const nodes = [], links = [];
  function flatten(d, parent) {{
    const n = {{...d, children: undefined}};
    nodes.push(n);
    if (parent) links.push({{source: parent.id, target: n.id}});
    (d.children||[]).forEach(c => flatten(c, n));
  }}
  GRAPH.forEach(r => flatten(r, null));

  // Deduplicate
  const seen = new Set();
  const uniqNodes = nodes.filter(n => {{ if(seen.has(n.id)) return false; seen.add(n.id); return true; }});

  const sim = d3.forceSimulation(uniqNodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(d => d.source.depth===0 ? 130 : 85).strength(.9))
    .force('charge', d3.forceManyBody().strength(-160))
    .force('collision', d3.forceCollide(28))
    .force('center', d3.forceCenter(W/2, H/2))
    .stop();

  for (let i = 0; i < 250; i++) sim.tick();

  const g = svg.append('g');

  // Zoom
  svg.call(d3.zoom().scaleExtent([.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

  // Arrow marker
  svg.append('defs').append('marker').attr('id','arr')
    .attr('viewBox','0 0 10 10').attr('refX',20).attr('refY',5)
    .attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto-start-reverse')
    .append('path').attr('d','M2 1L8 5L2 9').attr('fill','none').attr('stroke','#30363d').attr('stroke-width',1.5);

  // Links
  g.selectAll('line').data(links).join('line')
    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
    .attr('stroke','#30363d').attr('stroke-width',1.2).attr('marker-end','url(#arr)');

  // Nodes
  const tip = document.getElementById('tip');
  const ng = g.selectAll('.ng').data(uniqNodes).join('g')
    .attr('class','ng').attr('transform', d => `translate(${{d.x}},${{d.y}})`)
    .style('cursor','pointer')
    .on('mouseover', (e, d) => {{
      tip.style.opacity = 1;
      document.getElementById('tip-name').textContent = d.name;
      document.getElementById('tip-file').textContent = d.file;
      document.getElementById('tip-risk').innerHTML = `Risk: <strong style="color:${{d.color}}">${{d.risk}}/100 (${{d.label}})</strong>`;
      document.getElementById('tip-cov').textContent = d.covered ? '✅ Test coverage' : '❌ No test coverage';
    }})
    .on('mousemove', e => {{
      const r = container.getBoundingClientRect();
      tip.style.left = (e.clientX - r.left + 14) + 'px';
      tip.style.top  = (e.clientY - r.top  + 14) + 'px';
    }})
    .on('mouseleave', () => tip.style.opacity = 0);

  const radius = d => d.depth === 0 ? 20 : d.depth === 1 ? 13 : 9;

  ng.append('circle')
    .attr('r', d => radius(d))
    .attr('fill', d => d.color + '22')
    .attr('stroke', d => d.color)
    .attr('stroke-width', d => d.depth === 0 ? 2.5 : 1.5)
    .attr('stroke-dasharray', d => d.covered ? 'none' : '4 2');

  ng.append('text')
    .text(d => d.name.length > 14 ? d.name.slice(0,13)+'…' : d.name)
    .attr('text-anchor','middle').attr('dy', d => radius(d) + 11)
    .attr('fill','#848d97').attr('font-size', d => d.depth===0 ? 11 : 9)
    .attr('font-family','monospace');
}}

// ── Impact table ──────────────────────────────────────────────────────────────
function sortTable(key) {{
  if (sortKey === key) sortAsc = !sortAsc; else {{ sortKey = key; sortAsc = false; }}
  renderTable();
}}

function renderTable() {{
  let rows = [...TABLE];
  if (activeFilter) rows = rows.filter(r => r.risk_label === activeFilter);
  rows.sort((a,b) => {{
    const va = a[sortKey], vb = b[sortKey];
    const d = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
    return sortAsc ? d : -d;
  }});
  const COLORS = {{critical:'var(--red)',high:'var(--amb)',medium:'var(--blu)',low:'var(--grn)'}};
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td><strong>${{r.changed}}</strong><div class="mono">${{r.changed_file}}</div></td>
      <td>${{r.affected}}<div class="mono">${{r.affected_file}}</div></td>
      <td>
        <div class="risk-bar-wrap">
          <div class="risk-bar-bg"><div class="risk-bar-fill" style="width:${{r.risk}}%;background:${{COLORS[r.risk_label]}}"></div></div>
          <span style="color:${{COLORS[r.risk_label]}};font-weight:600;font-size:12px">${{r.risk}}</span>
          <span class="badge ${{r.risk_label}}">${{r.risk_label}}</span>
        </div>
      </td>
      <td class="${{r.covered ? 'cov-yes' : 'cov-no'}}">${{r.covered ? '✓ covered' : '✗ no tests'}}</td>
    </tr>`).join('');
}}

// Initial render
renderGraph();
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
    return output_path
