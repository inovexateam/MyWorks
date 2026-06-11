/**
 * extension.ts — VS Code extension entry point
 *
 * Registers:
 *   - @rca chat participant (Copilot Chat integration)
 *   - rca.startAnalysis / analyzeFile / analyzeSelection commands
 *   - RCAPanel webview (live agent + confidence visualizer)
 */

import * as vscode from "vscode";
import { RCAPanel } from "./rca-panel.js";
import { sessionStore } from "./session-store.js";
import {
  runTriageAgent,
  runInvestigatorAgent,
  runCodeAnalystAgent,
  runLogAnalystAgent,
  runSynthesizerAgent,
} from "./agents.js";

export function activate(context: vscode.ExtensionContext) {

  // ── 1. Copilot Chat participant ─────────────────────────────────────────

  const participant = vscode.chat.createChatParticipant(
    "rca.agent",
    async (request, chatContext, stream, token) => {

      const cmd = request.command ?? "start";
      const userText = request.prompt.trim();

      // Open / reveal the visual panel on every interaction
      const panel = RCAPanel.show(context);

      // ── /start — full orchestrated RCA ──────────────────────────────────
      if (cmd === "start") {
        if (!userText) {
          stream.markdown("**Describe the incident:**\n```\n@rca /start Memory leak on checkout-service, OOM every 6h\n  repo: https://github.com/org/repo\n  error: java.lang.OutOfMemoryError\n```");
          return;
        }

        // Parse optional repo: and error: lines from prompt
        const repoMatch = userText.match(/repo[_\s]*:?\s*(https?:\/\/\S+)/i);
        const errorMatch = userText.match(/error[_\s]*:?\s*(.+)/i);
        const incident = userText.split(/\n/)[0];
        const repoUrl = repoMatch?.[1];
        const errorMsg = errorMatch?.[1];

        const sessionId = sessionStore.create({ incident, severity: "P2", repoUrl });
        panel.setIncident(incident, sessionId);

        stream.markdown(`## 🔍 RCA Session \`${sessionId}\`\n\n`);

        // TRIAGE
        panel.setAgentStatus("triage", "running");
        const triage = await runTriageAgent({ incident, errorMessage: errorMsg, token, stream });
        sessionStore.addEvidence(sessionId, "triage", triage);
        panel.setAgentStatus("triage", "done", `${triage.category} / ${triage.severity}`);

        stream.markdown(`\n**Triage →** \`${triage.detectedStack}\` · ${triage.category} · ${triage.severity}\n\n`);

        // INVESTIGATOR
        if (repoUrl && triage.needsInvestigator) {
          panel.setAgentStatus("investigator", "running");
          const inv = await runInvestigatorAgent({ repoUrl, token, stream });
          sessionStore.addEvidence(sessionId, "investigator", inv);
          panel.setAgentStatus("investigator", "done", `${inv.suspiciousCommits.length} suspicious commits`);
        } else {
          panel.setAgentStatus("investigator", "skipped");
        }

        // CODE ANALYST — use active editor file if no specific file
        if (triage.needsCodeAnalyst) {
          panel.setAgentStatus("code", "running");
          const editor = vscode.window.activeTextEditor;
          const code = editor?.document.getText() ?? "";
          const filePath = editor?.document.fileName;
          const langHint = editor?.document.languageId;

          if (code) {
            const ca = await runCodeAnalystAgent({ code, filePath, languageHint: langHint, incidentContext: incident, token, stream });
            sessionStore.addEvidence(sessionId, "code", ca);
            panel.setAgentStatus("code", "done", `${ca.causes.length} candidates`);
            // Push causes to visualizer
            panel.setCauses(ca.causes.map(c => ({
              rank: c.rank, title: c.title, confidence: c.confidence,
              severity: c.severity, category: c.category,
              immediateAction: c.immediateAction, permanentFix: c.permanentFix,
            })));
          } else {
            panel.setAgentStatus("code", "skipped", "No file open in editor");
          }
        }

        // LOG ANALYST — if logs pasted inline
        if (triage.needsLogAnalyst && userText.includes("\n")) {
          panel.setAgentStatus("logs", "running");
          const la = await runLogAnalystAgent({ logs: userText, token, stream });
          sessionStore.addEvidence(sessionId, "logs", la);
          panel.setAgentStatus("logs", "done", la.summary.slice(0, 60));
        } else {
          panel.setAgentStatus("logs", "skipped");
        }

        // SYNTHESIZER
        panel.setAgentStatus("synthesizer", "running");
        stream.markdown("\n---\n## 📋 Root Cause Analysis\n\n");
        const session = sessionStore.get(sessionId)!;
        const inv = session.evidence.find(e => e.agent === "investigator")?.data as any;
        const ca  = session.evidence.find(e => e.agent === "code")?.data as any;
        const la  = session.evidence.find(e => e.agent === "logs")?.data as any;

        await runSynthesizerAgent({ incident, triage, investigator: inv, codeAnalysis: ca, logAnalysis: la, token, stream });
        panel.setAgentStatus("synthesizer", "done");
        sessionStore.complete(sessionId);

        stream.markdown(`\n\n---\n*Session \`${sessionId}\` · Use \`@rca /report\` to export as postmortem*`);
      }

      // ── /analyze — code analyst only on current file ────────────────────
      else if (cmd === "analyze") {
        const editor = vscode.window.activeTextEditor;
        if (!editor) { stream.markdown("Open a file in the editor first."); return; }

        panel.setAgentStatus("code", "running");
        const ca = await runCodeAnalystAgent({
          code: editor.document.getText(),
          filePath: editor.document.fileName,
          languageHint: editor.document.languageId,
          incidentContext: userText || undefined,
          token, stream,
        });

        panel.setAgentStatus("code", "done", `${ca.causes.length} candidates`);
        panel.setCauses(ca.causes.map(c => ({
          rank: c.rank, title: c.title, confidence: c.confidence,
          severity: c.severity, category: c.category,
          immediateAction: c.immediateAction, permanentFix: c.permanentFix,
        })));

        stream.markdown(`\n## Code Analysis — \`${ca.language}\` / \`${ca.framework}\`\n\n`);
        ca.causes.forEach(c => {
          stream.markdown(`### #${c.rank} ${c.title} — **${c.confidence}% confidence**\n`);
          stream.markdown(`${c.explanation}\n\n> **Evidence:** ${c.evidence}\n\n`);
          stream.markdown(`- ⚡ **Now:** ${c.immediateAction}\n- 🔧 **Fix:** ${c.permanentFix}\n\n`);
        });
      }

      // ── /investigate — investigator agent only ──────────────────────────
      else if (cmd === "investigate") {
        const repoUrl = userText.match(/https?:\/\/\S+/)?.[0];
        if (!repoUrl) { stream.markdown("Provide a GitHub URL: `@rca /investigate https://github.com/org/repo`"); return; }

        panel.setAgentStatus("investigator", "running");
        const inv = await runInvestigatorAgent({ repoUrl, focus: userText, token, stream });
        panel.setAgentStatus("investigator", "done", `${inv.suspiciousCommits.length} suspicious commits`);

        stream.markdown(`## Investigator — \`${inv.repo}\`\n\n`);
        stream.markdown(`**Stack:** ${inv.stackManifest}\n**Language:** ${inv.language}\n\n`);
        if (inv.suspiciousCommits.length) {
          stream.markdown(`### ⚠️ Suspicious commits\n`);
          inv.suspiciousCommits.forEach(c => {
            stream.markdown(`- \`${c.sha}\` ${c.message} — *${c.reason}*\n`);
          });
        }
        stream.markdown(`\n**Files to inspect next:** ${inv.filesToInspect.map(f => `\`${f}\``).join(", ")}\n`);
        stream.markdown(`\n${inv.summary}`);
      }

      // ── /logs — log analyst only ────────────────────────────────────────
      else if (cmd === "logs") {
        if (!userText) { stream.markdown("Paste log content after `/logs`:\n````\n@rca /logs\n<paste stack trace here>\n````"); return; }
        panel.setAgentStatus("logs", "running");
        const la = await runLogAnalystAgent({ logs: userText, token, stream });
        panel.setAgentStatus("logs", "done", la.summary.slice(0, 60));

        stream.markdown(`## Log Analysis\n\n`);
        stream.markdown(`**Top error:** ${la.topError}\n**Error rate:** ${la.errorRate}\n**Suspected service:** ${la.suspectedService}\n\n`);
        if (la.timelineEvents.length) {
          stream.markdown(`### Timeline\n`);
          la.timelineEvents.forEach(e => stream.markdown(`- \`${e.time}\` ${e.event}\n`));
        }
        stream.markdown(`\n${la.summary}`);
      }

      // ── /report — synthesizer on latest session ─────────────────────────
      else if (cmd === "report") {
        const latest = sessionStore.latest();
        if (!latest) { stream.markdown("No active session. Run `@rca /start` first."); return; }

        panel.setAgentStatus("synthesizer", "running");
        stream.markdown(`## 📄 Postmortem — Session \`${latest.id}\`\n\n`);

        const triage = latest.evidence.find(e => e.agent === "triage")?.data as any;
        const inv    = latest.evidence.find(e => e.agent === "investigator")?.data as any;
        const ca     = latest.evidence.find(e => e.agent === "code")?.data as any;
        const la     = latest.evidence.find(e => e.agent === "logs")?.data as any;

        await runSynthesizerAgent({
          incident: latest.incident, triage, investigator: inv,
          codeAnalysis: ca, logAnalysis: la, format: "postmortem", token, stream,
        });
        panel.setAgentStatus("synthesizer", "done");
      }
    }
  );

  participant.iconPath = new vscode.ThemeIcon("search-fuzzy");

  // ── 2. Editor commands ──────────────────────────────────────────────────

  context.subscriptions.push(
    vscode.commands.registerCommand("rca.analyzeFile", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return vscode.window.showErrorMessage("Open a file first.");
      vscode.commands.executeCommand("workbench.panel.chat.view.copilot.focus");
      vscode.commands.executeCommand("workbench.action.chat.open", {
        query: `@rca /analyze Analyze this file for root causes`,
      });
    }),

    vscode.commands.registerCommand("rca.analyzeSelection", async () => {
      const editor = vscode.window.activeTextEditor;
      const sel = editor?.document.getText(editor.selection);
      if (!sel) return vscode.window.showErrorMessage("Select some code first.");
      vscode.commands.executeCommand("workbench.action.chat.open", {
        query: `@rca /analyze\n\`\`\`\n${sel.slice(0, 2000)}\n\`\`\``,
      });
    }),

    vscode.commands.registerCommand("rca.startAnalysis", async () => {
      const incident = await vscode.window.showInputBox({
        prompt: "Describe the production incident",
        placeHolder: "e.g. Memory leak on checkout-service, OOM crashes every 6h",
      });
      if (!incident) return;
      vscode.commands.executeCommand("workbench.action.chat.open", {
        query: `@rca /start ${incident}`,
      });
    }),

    participant
  );
}

export function deactivate() {}
