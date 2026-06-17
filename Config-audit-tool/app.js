// ============================================================
// Config Audit — frontend logic
// No frameworks needed for a single-page tool like this; keeps
// the whole thing inspectable in one file, matching the tool's
// own "everything traceable" ethos.
// ============================================================

const el = (id) => document.getElementById(id);

let currentResult = null;
let activeFilter = "ALL";
let activeRole = "ALL";
let searchTerm = "";

// ---------- Auth ----------
el("connect-btn").addEventListener("click", connect);
el("token-input").addEventListener("keydown", (e) => { if (e.key === "Enter") connect(); });
el("disconnect-btn").addEventListener("click", disconnect);

async function connect() {
  const token = el("token-input").value.trim();
  el("auth-error").textContent = "";
  if (!token) {
    el("auth-error").textContent = "Paste your PAT to connect.";
    return;
  }
  el("connect-btn").disabled = true;
  el("connect-btn").textContent = "Connecting…";
  try {
    const resp = await fetch("/api/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const data = await resp.json();
    if (!data.ok) {
      el("auth-error").textContent = data.error || "Could not connect.";
      return;
    }
    el("auth-disconnected").classList.add("hidden");
    el("auth-connected").classList.remove("hidden");
    el("auth-username").textContent = data.username;
    el("scan-btn").disabled = false;
    el("token-input").value = "";
  } catch (err) {
    el("auth-error").textContent = "Network error reaching the local server.";
  } finally {
    el("connect-btn").disabled = false;
    el("connect-btn").textContent = "Connect";
  }
}

async function disconnect() {
  await fetch("/api/disconnect", { method: "POST" });
  el("auth-connected").classList.add("hidden");
  el("auth-disconnected").classList.remove("hidden");
  el("scan-btn").disabled = true;
}

function showReauthPrompt(message) {
  // Token expired mid-scan: surface inline, don't crash the UI.
  el("auth-connected").classList.add("hidden");
  el("auth-disconnected").classList.remove("hidden");
  el("auth-error").textContent = message || "Your token expired — please paste a fresh one.";
  el("scan-btn").disabled = true;
  el("scan-error").textContent = "Session expired during the scan. Reconnect above, then run the audit again.";
}

// ---------- Scan ----------
el("scan-btn").addEventListener("click", runScan);

async function runScan() {
  const code_url = el("code-url").value.trim();
  const component_cd_url = el("component-cd-url").value.trim();
  const app_cd_url = el("app-cd-url").value.trim();
  el("scan-error").textContent = "";

  if (!code_url || !component_cd_url || !app_cd_url) {
    el("scan-error").textContent = "All three repo URLs are required.";
    return;
  }

  el("empty-state").classList.add("hidden");
  el("results-state").classList.add("hidden");
  el("loading-state").classList.remove("hidden");
  el("scan-btn").disabled = true;

  const messages = [
    "Fetching repository trees…",
    "Resolving app-cd and component-cd values…",
    "Scanning Helm templates for references…",
    "Scanning Java and C# source for config reads…",
    "Classifying keys and checking env drift…",
  ];
  let mi = 0;
  const interval = setInterval(() => {
    mi = (mi + 1) % messages.length;
    el("loading-text").textContent = messages[mi];
  }, 1800);

  try {
    const resp = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code_url, component_cd_url, app_cd_url }),
    });
    const data = await resp.json();
    clearInterval(interval);

    if (!data.ok) {
      el("loading-state").classList.add("hidden");
      if (data.code === "token_expired") {
        showReauthPrompt(data.error);
        el("empty-state").classList.remove("hidden");
      } else {
        el("scan-error").textContent = data.error || "Scan failed.";
        el("empty-state").classList.remove("hidden");
      }
      return;
    }

    currentResult = data.result;
    renderResults(currentResult);
    el("loading-state").classList.add("hidden");
    el("results-state").classList.remove("hidden");
    el("summary-panel").classList.remove("hidden");
  } catch (err) {
    clearInterval(interval);
    el("loading-state").classList.add("hidden");
    el("empty-state").classList.remove("hidden");
    el("scan-error").textContent = "Network error during scan.";
  } finally {
    el("scan-btn").disabled = false;
  }
}

// ---------- Rendering ----------
function renderResults(result) {
  renderSummary(result);
  renderFindings(result.findings, result.drift);
}

function renderSummary(result) {
  const counts = result.summary.by_classification || {};
  const cells = [
    { key: "FULLY_DEAD", label: "Fully dead", cls: "dead" },
    { key: "DEAD_HELM", label: "Dead in Helm", cls: "warn" },
    { key: "DEAD_CODE", label: "Dead in code", cls: "warn" },
    { key: "LIVE", label: "Live", cls: "live" },
  ];
  el("summary-grid").innerHTML = cells.map(c => `
    <div class="summary-cell ${c.cls}">
      <span class="num">${counts[c.key] || 0}</span>
      <span class="lbl">${c.label}</span>
    </div>
  `).join("") + `
    <div class="summary-cell warn">
      <span class="num">${result.summary.drift_count || 0}</span>
      <span class="lbl">Env drift</span>
    </div>
    <div class="summary-cell">
      <span class="num">${result.summary.total_keys || 0}</span>
      <span class="lbl">Total keys</span>
    </div>
  `;

  el("env-chips").innerHTML = (result.envs_detected || [])
    .map(e => `<span class="env-chip">${escapeHtml(e)}</span>`).join("");

  const roles = result.summary.by_role || {};
  el("role-breakdown").innerHTML = `
    <div class="role-pill"><strong>${roles.APP_CONFIG || 0}</strong>app config</div>
    <div class="role-pill"><strong>${roles.INFRA || 0}</strong>infra</div>
  `;
}

el("search-input").addEventListener("input", (e) => {
  searchTerm = e.target.value.trim().toLowerCase();
  if (currentResult) renderFindings(currentResult.findings, currentResult.drift);
});

document.querySelectorAll(".tab[data-filter]").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab[data-filter]").forEach(t => t.classList.remove("tab-active"));
    tab.classList.add("tab-active");
    activeFilter = tab.dataset.filter;
    if (currentResult) renderFindings(currentResult.findings, currentResult.drift);
  });
});

document.querySelectorAll(".tab-role").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab-role").forEach(t => t.classList.remove("tab-active"));
    tab.classList.add("tab-active");
    activeRole = tab.dataset.role;
    if (currentResult) renderFindings(currentResult.findings, currentResult.drift);
  });
});

function renderFindings(findings, drift) {
  const listEl = el("findings-list");
  const driftEl = el("drift-list");

  if (activeFilter === "DRIFT") {
    listEl.classList.add("hidden");
    driftEl.classList.remove("hidden");
    renderDrift(drift);
    return;
  }
  listEl.classList.remove("hidden");
  driftEl.classList.add("hidden");

  let filtered = findings;
  if (activeFilter !== "ALL") {
    filtered = filtered.filter(f => f.classification === activeFilter);
  }
  if (activeRole !== "ALL") {
    filtered = filtered.filter(f => f.key_role === activeRole);
  }
  if (searchTerm) {
    filtered = filtered.filter(f => f.dotted_path.toLowerCase().includes(searchTerm));
  }

  if (filtered.length === 0) {
    listEl.innerHTML = `<div class="empty-filtered">No keys match this filter.</div>`;
    return;
  }

  listEl.innerHTML = filtered.map((f, i) => `
    <div class="finding-row cls-${f.classification}" data-idx="${findings.indexOf(f)}" tabindex="0">
      <span class="pill pill-env">${escapeHtml(f.env)}</span>
      <span class="role-tag role-${f.key_role}">${f.key_role === "INFRA" ? "infra" : "app"}</span>
      <span class="finding-key">${escapeHtml(f.dotted_path)}</span>
      <span class="finding-meta">${escapeHtml(shortPath(f.defined_in.file_path))}:${f.defined_in.line}</span>
      <span class="pill pill-${f.classification}">${classLabel(f.classification)}</span>
    </div>
  `).join("");

  listEl.querySelectorAll(".finding-row").forEach(row => {
    row.addEventListener("click", () => openDrawer(findings[parseInt(row.dataset.idx)]));
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter") openDrawer(findings[parseInt(row.dataset.idx)]);
    });
  });
}

function renderDrift(drift) {
  const driftEl = el("drift-list");
  let filtered = drift || [];
  if (searchTerm) {
    filtered = filtered.filter(d => d.dotted_path.toLowerCase().includes(searchTerm));
  }
  if (filtered.length === 0) {
    driftEl.innerHTML = `<div class="empty-filtered">No drift detected across environments — all keys are consistent.</div>`;
    return;
  }
  driftEl.innerHTML = filtered.map(d => `
    <div class="drift-row">
      <div class="drift-key">${escapeHtml(d.dotted_path)}</div>
      <div class="drift-envs">
        ${d.present_in.map(e => `<span class="drift-env-tag present">✓ ${escapeHtml(e)}</span>`).join("")}
        ${d.missing_in.map(e => `<span class="drift-env-tag missing">✕ ${escapeHtml(e)}</span>`).join("")}
      </div>
    </div>
  `).join("");
}

function classLabel(cls) {
  return ({
    FULLY_DEAD: "Fully dead",
    DEAD_HELM: "Dead in Helm",
    DEAD_CODE: "Dead in code",
    LIVE: "Live",
  })[cls] || cls;
}

function shortPath(p) {
  if (!p) return "—";
  return p.length > 46 ? "…" + p.slice(-44) : p;
}

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[c]);
}

// ---------- Evidence drawer (signature element) ----------
el("drawer-close").addEventListener("click", closeDrawer);
el("drawer-overlay").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

function openDrawer(finding) {
  el("drawer-badge").textContent = classLabel(finding.classification);
  el("drawer-badge").className = "badge pill-" + finding.classification;
  el("drawer-key").textContent = finding.dotted_path;
  el("drawer-env").innerHTML = `environment: ${escapeHtml(finding.env)} &nbsp;·&nbsp; <span class="role-tag role-${finding.key_role}">${finding.key_role === "INFRA" ? "infra-only" : "app config"}</span>`;

  // Trace chain: Define -> Template -> Code
  const defined = finding.defined_in;
  const hasTemplate = finding.template_hits && finding.template_hits.length > 0;
  const hasCode = finding.code_hits && finding.code_hits.length > 0;

  el("trace-chain").innerHTML = `
    <div class="trace-node node-active">
      <div class="trace-node-label">Defined</div>
      <div class="trace-node-value">${escapeHtml(shortPath(defined.file_path))}:${defined.line}</div>
    </div>
    <div class="trace-connector">→</div>
    <div class="trace-node ${hasTemplate ? "node-active" : "node-missing"}">
      <div class="trace-node-label">Templated</div>
      <div class="trace-node-value">${hasTemplate ? escapeHtml(shortPath(finding.template_hits[0].file_path)) + ":" + finding.template_hits[0].line : "not referenced"}</div>
    </div>
    <div class="trace-connector">→</div>
    <div class="trace-node ${hasCode ? "node-active" : "node-missing"}">
      <div class="trace-node-label">Read in code</div>
      <div class="trace-node-value">${hasCode ? escapeHtml(shortPath(finding.code_hits[0].file_path)) + ":" + finding.code_hits[0].line : "not referenced"}</div>
    </div>
  `;

  el("evidence-defined").innerHTML = `
    <span class="evidence-path">${escapeHtml(defined.file_path)}</span>
    <span class="evidence-line">:${defined.line}</span>
  `;

  el("template-count").textContent = finding.template_hits.length;
  el("evidence-template").innerHTML = finding.template_hits.length
    ? finding.template_hits.map(h => `
        <div class="evidence-row">
          <span class="evidence-path">${escapeHtml(h.file_path)}</span>
          <span class="evidence-line">:${h.line}</span>
        </div>`).join("")
    : `<div class="evidence-empty">No Helm template references this key — it never reaches a running container.</div>`;

  el("code-count").textContent = finding.code_hits.length;
  el("evidence-code").innerHTML = finding.code_hits.length
    ? finding.code_hits.map(h => `
        <div class="evidence-row">
          <span class="evidence-path">${escapeHtml(h.file_path)} <span style="color:var(--text-faint)">[${h.layer}]</span></span>
          <span class="evidence-line">:${h.line}</span>
        </div>`).join("")
    : `<div class="evidence-empty">No application code reads this key.</div>`;

  el("drawer-overlay").classList.remove("hidden");
  el("evidence-drawer").classList.remove("hidden");
}

function closeDrawer() {
  el("drawer-overlay").classList.add("hidden");
  el("evidence-drawer").classList.add("hidden");
}

// ---------- Periodic token-age check (soft warning, not enforced) ----------
setInterval(async () => {
  try {
    const resp = await fetch("/api/status");
    const data = await resp.json();
    if (data.connected && data.token_age_seconds > 23 * 3600) {
      el("auth-error").textContent = "Heads up — this token is nearing your org's 24h expiry.";
    }
  } catch (e) { /* local server not reachable; ignore */ }
}, 60000);
