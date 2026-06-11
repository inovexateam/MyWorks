/**
 * rca-panel.ts
 * WebviewPanel that opens alongside Copilot Chat.
 * Shows: live agent pipeline, confidence bars, root cause cards, postmortem export.
 */

import * as vscode from "vscode";

export interface AgentStatus {
  id: string;
  label: string;
  status: "waiting" | "running" | "done" | "skipped";
  summary?: string;
}

export interface RootCause {
  rank: number;
  title: string;
  confidence: number;
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  immediateAction: string;
  permanentFix: string;
}

export class RCAPanel {
  static currentPanel: RCAPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private _agents: AgentStatus[] = [
    { id: "triage",      label: "Triage",       status: "waiting" },
    { id: "investigator",label: "Investigator",  status: "waiting" },
    { id: "code",        label: "Code Analyst",  status: "waiting" },
    { id: "logs",        label: "Log Analyst",   status: "waiting" },
    { id: "synthesizer", label: "Synthesizer",   status: "waiting" },
  ];
  private _causes: RootCause[] = [];
  private _incident = "";
  private _sessionId = "";

  static show(context: vscode.ExtensionContext): RCAPanel {
    if (RCAPanel.currentPanel) {
      RCAPanel.currentPanel._panel.reveal(vscode.ViewColumn.Beside);
      return RCAPanel.currentPanel;
    }
    const panel = vscode.window.createWebviewPanel(
      "rcaPanel",
      "RCA — Agent Dashboard",
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true }
    );
    RCAPanel.currentPanel = new RCAPanel(panel);
    panel.onDidDispose(() => { RCAPanel.currentPanel = undefined; });
    return RCAPanel.currentPanel;
  }

  private constructor(panel: vscode.WebviewPanel) {
    this._panel = panel;
    this._render();
  }

  setIncident(incident: string, sessionId: string) {
    this._incident = incident;
    this._sessionId = sessionId;
    this._render();
  }

  setAgentStatus(id: string, status: AgentStatus["status"], summary?: string) {
    const agent = this._agents.find(a => a.id === id);
    if (agent) { agent.status = status; agent.summary = summary; }
    this._render();
  }

  setCauses(causes: RootCause[]) {
    this._causes = causes;
    this._render();
  }

  private _render() {
    this._panel.webview.html = getWebviewHTML(
      this._incident,
      this._sessionId,
      this._agents,
      this._causes
    );
  }
}

// ─── HTML ────────────────────────────────────────────────────────────────────

function getWebviewHTML(
  incident: string,
  sessionId: string,
  agents: AgentStatus[],
  causes: RootCause[]
): string {
  const agentHTML = agents.map(a => {
    const icons: Record<AgentStatus["status"], string> = {
      waiting: "⬜", running: "🔄", done: "✅", skipped: "⏭️"
    };
    const cls = `agent-card status-${a.status}`;
    return `
      <div class="${cls}">
        <span class="agent-icon">${icons[a.status]}</span>
        <div class="agent-info">
          <div class="agent-name">${a.label}</div>
          ${a.summary ? `<div class="agent-summary">${a.summary}</div>` : ""}
        </div>
      </div>`;
  }).join("");

  const causeHTML = causes.length === 0
    ? `<div class="empty">Waiting for analysis...</div>`
    : causes.map(c => {
        const pct = c.confidence;
        const barColor = pct >= 75 ? "#4caf82" : pct >= 45 ? "#e8a838" : "#e05252";
        const sevColor: Record<string, string> = {
          critical: "#e05252", high: "#e8a838", medium: "#5b9cf6", low: "#4caf82"
        };
        return `
        <div class="cause-card">
          <div class="cause-header">
            <span class="rank">#${c.rank}</span>
            <span class="cause-title">${c.title}</span>
            <span class="sev-badge" style="background:${sevColor[c.severity] ?? "#888"}22;color:${sevColor[c.severity] ?? "#888"}">${c.severity}</span>
          </div>
          <div class="conf-row">
            <div class="conf-bar-bg">
              <div class="conf-bar-fill" style="width:${pct}%;background:${barColor}"></div>
            </div>
            <span class="conf-label" style="color:${barColor}">${pct}%</span>
          </div>
          <div class="cause-detail-grid">
            <div class="cause-detail">
              <div class="detail-label">⚡ Immediate action</div>
              <div class="detail-val">${c.immediateAction}</div>
            </div>
            <div class="cause-detail">
              <div class="detail-label">🔧 Permanent fix</div>
              <div class="detail-val">${c.permanentFix}</div>
            </div>
          </div>
        </div>`;
      }).join("");

  return /* html */`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RCA Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--vscode-font-family, system-ui);
    font-size: 13px;
    color: var(--vscode-foreground);
    background: var(--vscode-editor-background);
    padding: 16px;
    line-height: 1.5;
  }
  h2 { font-size: 14px; font-weight: 600; margin-bottom: 12px; opacity: 0.7; text-transform: uppercase; letter-spacing: .06em; }
  .section { margin-bottom: 24px; }
  .incident-box {
    background: var(--vscode-textBlockQuote-background, #1e1e2e);
    border-left: 3px solid var(--vscode-focusBorder, #5b9cf6);
    padding: 10px 14px; border-radius: 4px; font-size: 13px;
    margin-bottom: 6px;
  }
  .session-id { font-size: 11px; opacity: 0.45; font-family: monospace; }

  /* Agent pipeline */
  .agent-pipeline { display: flex; flex-direction: column; gap: 6px; }
  .agent-card {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 12px; border-radius: 6px;
    border: 1px solid transparent;
    transition: all .2s;
  }
  .status-waiting  { opacity: 0.4; }
  .status-running  { border-color: #5b9cf6; background: #5b9cf610; animation: pulse 1.2s ease-in-out infinite; }
  .status-done     { border-color: #4caf8240; background: #4caf8210; }
  .status-skipped  { opacity: 0.3; text-decoration: line-through; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }
  .agent-icon { font-size: 16px; flex-shrink: 0; }
  .agent-name { font-weight: 500; font-size: 13px; }
  .agent-summary { font-size: 11px; opacity: 0.65; margin-top: 2px; }

  /* Cause cards */
  .cause-card {
    background: var(--vscode-textBlockQuote-background, #1e1e2e);
    border: 1px solid var(--vscode-panel-border, #333);
    border-radius: 8px; padding: 12px 14px; margin-bottom: 10px;
  }
  .cause-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
  .rank { font-size: 11px; font-weight: 700; opacity: .5; }
  .cause-title { font-weight: 600; font-size: 13px; flex: 1; }
  .sev-badge { font-size: 10px; padding: 2px 8px; border-radius: 100px; font-weight: 600; flex-shrink: 0; }
  .conf-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .conf-bar-bg { flex: 1; height: 5px; background: #ffffff12; border-radius: 100px; overflow: hidden; }
  .conf-bar-fill { height: 5px; border-radius: 100px; transition: width .6s ease; }
  .conf-label { font-size: 12px; font-weight: 700; min-width: 36px; text-align: right; }
  .cause-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .cause-detail { background: #ffffff08; border-radius: 4px; padding: 8px; }
  .detail-label { font-size: 10px; opacity: .5; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 3px; }
  .detail-val { font-size: 12px; }
  .empty { opacity: 0.35; font-size: 12px; padding: 12px 0; }
</style>
</head>
<body>

<div class="section">
  <h2>🚨 Incident</h2>
  <div class="incident-box">${incident || "No incident described yet. Use @rca /start in Copilot Chat."}</div>
  ${sessionId ? `<div class="session-id">Session: ${sessionId}</div>` : ""}
</div>

<div class="section">
  <h2>🤖 Agent Pipeline</h2>
  <div class="agent-pipeline">${agentHTML}</div>
</div>

<div class="section">
  <h2>🎯 Root Cause Candidates</h2>
  ${causeHTML}
</div>

</body>
</html>`;
}
