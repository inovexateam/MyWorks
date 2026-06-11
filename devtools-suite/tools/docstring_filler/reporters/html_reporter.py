"""HTML report: doc coverage by file + generated docstring preview."""

import json
from datetime import datetime
from core.models import MissingDoc, GeneratedDoc


def generate_html_report(
    missing: list[MissingDoc],
    generated: list[GeneratedDoc],
    stats: dict,
    output_path: str = "docstring-report.html",
):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    applied = stats.get("docs_applied", 0)

    # Coverage by file
    by_file: dict[str, dict] = {}
    for m in missing:
        by_file.setdefault(m.file, {"missing": 0, "generated": 0})
        by_file[m.file]["missing"] += 1

    gen_map = {g.symbol.id(): g for g in generated}
    for m in missing:
        if m.id() in gen_map:
            by_file[m.file]["generated"] += 1

    gen_json = json.dumps([
        {
            "name": g.symbol.name,
            "kind": g.symbol.kind,
            "file": g.symbol.file,
            "line": g.symbol.line,
            "language": g.symbol.language,
            "confidence": round(g.confidence * 100),
            "docstring": g.docstring,
        }
        for g in generated
    ], indent=2)

    file_rows = "".join(
        f'<tr onclick="filterFile({json.dumps(f)})" style="cursor:pointer">'
        f'<td class="mono">{f}</td>'
        f'<td>{d["missing"]}</td>'
        f'<td>{d["generated"]}</td>'
        f'<td><div class="bar-bg"><div class="bar-fill" style="width:{round(d["generated"]/d["missing"]*100) if d["missing"] else 0}%"></div></div></td>'
        f'</tr>'
        for f, d in sorted(by_file.items(), key=lambda x: -x[1]["missing"])
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Docstring Coverage — {now}</title>
<style>
:root{{--bg:#0d1117;--s1:#161b22;--s2:#21262d;--bd:#30363d;--tx:#e6edf3;--mu:#848d97;
  --red:#f85149;--grn:#3fb950;--blu:#58a6ff;--amb:#e3b341;
  font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx)}}
header{{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}}
header h1{{font-size:16px;font-weight:600}}
.stats{{display:flex;gap:16px;font-size:12px;color:var(--mu)}}
.layout{{display:grid;grid-template-columns:380px 1fr;height:calc(100vh - 57px)}}
.left{{border-right:1px solid var(--bd);overflow-y:auto}}
.right{{overflow-y:auto;padding:16px 20px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 12px;color:var(--mu);font-size:11px;border-bottom:1px solid var(--bd)}}
td{{padding:8px 12px;border-bottom:1px solid var(--bd)}}
tr:hover td{{background:var(--s1)}}
.mono{{font-family:monospace;font-size:11px}}
.bar-bg{{height:5px;background:var(--s2);border-radius:3px;width:80px}}
.bar-fill{{height:100%;background:var(--grn);border-radius:3px}}
.toolbar{{padding:12px 16px;border-bottom:1px solid var(--bd);display:flex;gap:8px}}
.toolbar input{{background:var(--s2);border:1px solid var(--bd);border-radius:6px;padding:5px 10px;color:var(--tx);font-size:12px;flex:1}}
.toolbar input:focus{{outline:none;border-color:var(--blu)}}
.flt{{padding:4px 10px;border-radius:6px;border:1px solid var(--bd);background:var(--s2);color:var(--mu);font-size:11px;cursor:pointer}}
.flt.on{{border-color:var(--blu);color:var(--tx)}}
#cnt{{color:var(--mu);font-size:12px}}
.doc-card{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:12px 14px;margin-bottom:8px}}
.dc-top{{display:flex;gap:8px;align-items:center;margin-bottom:6px}}
.dc-name{{font-family:monospace;font-size:13px;font-weight:500}}
.dc-file{{font-size:11px;color:var(--mu);margin-bottom:6px}}
.dc-doc{{font-family:monospace;font-size:11px;background:var(--s2);border-radius:6px;padding:8px;white-space:pre;overflow-x:auto;color:var(--grn)}}
.badge{{padding:2px 7px;border-radius:4px;font-size:10px;font-weight:600}}
.ai{{background:#0d2038;color:#58a6ff}}.rb{{background:#0d2b1a;color:#3fb950}}
</style>
</head>
<body>
<header>
  <h1>Docstring Auto-Filler</h1>
  <div class="stats">
    <span>{now}</span>
    <span style="color:var(--red)">{len(missing)} missing</span>
    <span style="color:var(--grn)">{len(generated)} generated</span>
    <span>{applied} applied</span>
  </div>
</header>
<div class="layout">
  <div class="left">
    <table>
      <thead><tr><th>File</th><th>Missing</th><th>Gen</th><th>Coverage</th></tr></thead>
      <tbody>{file_rows}</tbody>
    </table>
  </div>
  <div class="right">
    <div class="toolbar">
      <input type="text" id="search" placeholder="Search symbol, file…" oninput="render()">
      <button class="flt on" onclick="setFlt('all',this)">All</button>
      <button class="flt" onclick="setFlt('class',this)">Classes</button>
      <button class="flt" onclick="setFlt('method',this)">Methods</button>
      <button class="flt" onclick="setFlt('ai',this)">AI-generated</button>
      <span id="cnt"></span>
    </div>
    <div id="list"></div>
  </div>
</div>
<script>
const DATA = {gen_json};
let activeFlt = 'all';
let activeFile = null;
let activeSearch = '';

function setFlt(f,btn){{
  activeFlt=f; activeFile=null;
  document.querySelectorAll('.flt').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  render();
}}

function filterFile(f){{
  activeFile=f; activeFlt='all';
  document.querySelectorAll('.flt').forEach(b=>b.classList.remove('on'));
  document.querySelectorAll('.flt')[0].classList.add('on');
  render();
}}

function render(){{
  activeSearch = document.getElementById('search').value.toLowerCase();
  let items = DATA;
  if(activeFile) items = items.filter(d=>d.file===activeFile);
  if(activeFlt==='class')  items=items.filter(d=>d.kind==='class');
  if(activeFlt==='method') items=items.filter(d=>['method','function'].includes(d.kind));
  if(activeFlt==='ai')     items=items.filter(d=>d.confidence>=70);
  if(activeSearch) items=items.filter(d=>
    d.name.toLowerCase().includes(activeSearch)||
    d.file.toLowerCase().includes(activeSearch)
  );
  document.getElementById('cnt').textContent=items.length+' shown';
  const list=document.getElementById('list');
  list.innerHTML=items.slice(0,80).map(d=>{{
    const tag=d.confidence>=70?'<span class="badge ai">AI</span>':'<span class="badge rb">rule</span>';
    const escaped=d.docstring.replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return `<div class="doc-card">
      <div class="dc-top">${{tag}}<span class="dc-name">${{d.name}}</span><span style="color:var(--mu);font-size:11px">${{d.kind}}</span><span style="margin-left:auto;font-size:11px;color:var(--mu)">${{d.confidence}}% confidence</span></div>
      <div class="dc-file">${{d.file}}:${{d.line}}</div>
      <div class="dc-doc">${{escaped}}</div>
    </div>`;
  }}).join('');
  if(items.length>80) list.innerHTML+=`<div style="text-align:center;padding:20px;color:var(--mu)">Showing 80 of ${{items.length}}</div>`;
}}
render();
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Report → {output_path}")
