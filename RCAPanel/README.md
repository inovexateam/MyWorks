# RCA Copilot Extension

Multi-agent Root Cause Analysis inside **GitHub Copilot Chat**.  
No API keys. No external services. Runs on your Copilot subscription.

---

## What it does

Opens a **live agent dashboard** alongside Copilot Chat showing:
- Agent pipeline progress (Triage → Investigator → Code Analyst → Log Analyst → Synthesizer)
- Confidence bars per root cause candidate
- Immediate action + permanent fix per cause

All analysis is done by Copilot's GPT-4o model via the VS Code Language Model API (`vscode.lm`).

---

## Requirements

- VS Code `1.90+`
- **GitHub Copilot** extension installed and signed in
- Node.js `18+` (to build)

No OpenAI key. No Anthropic key. No Azure key.

---

## Install (dev mode)

```bash
git clone https://github.com/your-org/rca-copilot-extension
cd rca-copilot-extension
npm install
npm run compile
```

Then in VS Code:
1. Open the cloned folder
2. Press `F5` — this opens an **Extension Development Host** window
3. In that window, open Copilot Chat (`Ctrl+Shift+I`)
4. Type `@rca` to start

---

## Usage

### Full RCA session (all agents)

```
@rca /start Memory leak on checkout-service. OOM crashes every 6h.
repo: https://github.com/org/repo
error: java.lang.OutOfMemoryError: Java heap space
```

The agent dashboard opens automatically on the right. Watch each agent fire in sequence.

### Analyze the open file

```
@rca /analyze
```

Or right-click anywhere in the editor → **RCA: Analyze Current File**

### Analyze a selection

Select suspicious code → right-click → **RCA: Analyze Selected Code**

### Investigate a GitHub repo

```
@rca /investigate https://github.com/org/repo
```

Fetches real commit history. Flags suspicious commits (dependency bumps, removed error handling, cache config changes).

### Analyze logs / stack trace

```
@rca /logs
java.lang.OutOfMemoryError: Java heap space
  at java.util.Arrays.copyOf(Arrays.java:3236)
  at com.example.OrderService.buildCache(OrderService.java:142)
  ...
```

### Generate postmortem

```
@rca /report
```

Synthesizes all agent findings from the session into a Google SRE-style postmortem.

---

## Agent pipeline

```
@rca /start  ──▶  Triage ──▶  Orchestrator
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
         Investigator        Code Analyst        Log Analyst
         (GitHub API)        (any language)      (logs/traces)
              │                   │                   │
              └───────────────────▼───────────────────┘
                              Synthesizer
                       (ranked RCA + postmortem)
```

Each agent updates the **visual dashboard** in real time.

---

## Visual dashboard

Opens automatically as a side panel when any `@rca` command runs.

| Section | Shows |
|---|---|
| Incident | What was described |
| Agent Pipeline | Each agent: waiting / running (animated) / done / skipped |
| Root Cause Candidates | Ranked cards with confidence bars, severity badges, immediate action, permanent fix |

---

## Optional: GitHub token (private repos)

For private repos or to avoid rate limits on the GitHub API:

1. VS Code Settings → search `rca.githubToken`
2. Paste a GitHub PAT with `repo` scope

Without this, the Investigator agent still works on all **public** repos.

---

## Packaging for your team

```bash
npm install -g @vscode/vsce
vsce package
# produces rca-copilot-extension-1.0.0.vsix
```

Share the `.vsix` file. Install via:
```
Extensions panel → ⋯ → Install from VSIX
```

---

## File structure

```
src/
  extension.ts      ← Entry point, @rca chat participant, commands
  agents.ts         ← All 5 agents (triage, investigator, code, logs, synthesizer)
  copilot-llm.ts    ← VS Code LM API wrapper (uses Copilot, zero keys)
  rca-panel.ts      ← WebviewPanel visualizer (pipeline + confidence bars)
  session-store.ts  ← In-memory session state across turns
```

---

## Demo script (for team presentation)

Use `spring-petclinic` (real public Java Spring repo) as the demo target.

**Step 1** — Triage (30 sec)
```
@rca /start Memory leak. Pods OOM-killed every 6h. Heap grows unbounded.
repo: https://github.com/spring-projects/spring-petclinic
error: java.lang.OutOfMemoryError: Java heap space
```

**Step 2** — Watch the dashboard: Triage fires → Investigator pulls real commits → Code Analyst reads the file open in editor → Synthesizer streams the report.

**Step 3** — Postmortem export
```
@rca /report
```

---

## Extending

**Add a new agent:** create a `runXxxAgent()` in `agents.ts`, call it in `extension.ts`, add a panel status update in `rca-panel.ts`.

**Add a new command:** add to `contributes.chatParticipants.commands` in `package.json`, add the `else if (cmd === "xxx")` branch in `extension.ts`.

**Add Jira/PagerDuty/Datadog:** fetch from their APIs in the relevant agent. Use `vscode.workspace.getConfiguration("rca")` to store API tokens in VS Code settings.
