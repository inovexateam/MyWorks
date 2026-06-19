# OraQuery — VS Code Extension Roadmap

## Where we are

- Existing deliverable: standalone HTML tool (`oracle_sql_builder.html`) — visual Oracle SQL query builder with drag-and-drop canvas, 22 Oracle-specific validation rules, CTEs, window functions, PIVOT/UNPIVOT, hints, templates.
- Decision: pivot to a **VS Code extension** (webview panel) instead of continuing the standalone HTML file. Reasons: lives where the team already works, gets Copilot Chat integration, removes the "why not just use SQL Developer" objection.
- Distribution: **internal `.vsix`** only, shared manually with the team. No Marketplace publish.
- Live DB connection: **deferred**. Not building a new Oracle connector yet. Will reuse the team's existing Oracle extension's connection *if/when it exposes a public API* (unconfirmed — see Open Risk below).
- Current scope without live connection: visual query builder + Oracle validation linter + Copilot Chat Participant integration. Schema can be loaded the same way the HTML tool does today (JSON/DDL paste), not from a live DB.

## Why this over "just ask Copilot"

| | Copilot alone | OraQuery extension |
|---|---|---|
| SQL generation | Yes | Yes, via `@oraquery` chat participant |
| Oracle-specific validation (ORA-00937, ROWNUM anti-pattern, NULL=NULL trap, etc.) | No | Yes — 22 rules |
| Visual JOIN graph before running | No | Yes |
| Iterative editing (add a WHERE clause without re-prompting) | No — re-prompt each time | Yes — click-driven |
| Live execution | Depends on separate tooling | Deferred (Phase 3) |

Verdict: complementary to Copilot, not a replacement. Value is real but partial until live execution lands.

## Open risk (blocks real timeline)

**Unknown: does the team's Oracle VS Code extension expose a public extension API?**
- Most DB extensions do not export `vscode.extensions.getExtension(id).exports`.
- This determines whether Phase 3 (live connection) is a 1-day integration or a 3-4 day separate-connector build.
- **Action needed from you:** confirm exact extension name/publisher (check Extensions panel) so this can be checked against its docs/source before Phase 3 is scoped.

## Phased Plan

### Phase 1 — Extension scaffold (no DB, no Copilot yet)
- `npm init` TypeScript VS Code extension project
- Register command `OraQuery: Open Builder` → opens Webview Panel
- Port existing HTML/CSS/JS into `webview/` folder
- Replace `localStorage`/`fetch` calls with `acquireVsCodeApi()` message passing
- Schema loading via JSON paste / DDL paste (same as today — no live DB)
- Package as `.vsix`, install locally, verify parity with the standalone HTML tool
- **Deliverable:** working `.vsix`, feature-equivalent to current HTML tool, running inside VS Code

### Phase 2 — Copilot Chat Participant
- Register a Chat Participant (`@oraquery`) via `vscode.chat.createChatParticipant`
- User can type `@oraquery build a query joining employees and departments by department_id`
- Participant either:
  - (a) returns SQL directly in chat, or
  - (b) pushes a message to the open webview to pre-populate the visual canvas (tables, columns, join) so the user can refine + validate visually
- Validation rules run automatically on whatever Copilot drafts — this is the main value-add over raw Copilot output
- **Deliverable:** `@oraquery` working in Copilot Chat sidebar, wired to the webview

### Phase 2.5 — SQL Reverse-Engineering (parse existing queries into the canvas)
- **Why this matters most:** most DBA/dev time isn't writing new queries — it's untangling legacy ones. Nobody's tool does this well. Doesn't need live DB connection or Copilot — self-contained, scopeable work.
- Paste in an existing (possibly messy, 100-300 line) SQL query
- Parse it into the visual canvas: tables placed, joins drawn, WHERE/GROUP BY/HAVING/CTEs populated into their respective panels
- Run the existing 22 validation rules against it automatically — surface every anti-pattern in the legacy query
- Output a "cleaned" version side-by-side (consistent formatting, suggested fixes applied)
- Needs a real SQL parser (not regex) — evaluate `node-sql-parser` (has partial Oracle dialect support) vs. a custom recursive-descent parser scoped to the subset of Oracle SQL this tool already generates (much smaller, easier — only needs to round-trip what OraQuery itself can produce, not arbitrary SQL)
- **Deliverable:** "Import SQL" button — paste query → canvas populates → validation panel lights up
- **Effort:** 3-5 days depending on parser scope

### Phase 2.6 — Closed-loop auto-fix (generate → validate → auto-fix → re-validate)
- **Why this changes the product, not just adds to it:** every phase above still depends on a human noticing the validation panel and fixing it manually — same failure mode as raw Copilot output. Most people won't check. This removes that dependency entirely.
- `@oraquery` generates SQL via Copilot → validator runs silently, immediately, no user action
- **Deterministic rules auto-fix without asking:** NULL=NULL → IS NULL, ROWNUM → FETCH FIRST, missing GROUP BY column → added, duplicate alias → renamed, etc.
- **Judgment-call rules block and surface inline in chat** (not buried in a side panel): cartesian product risk, many-to-many duplicate rows, non-deterministic window function — these need a human decision, not a silent fix
- User only ever sees the final, already-corrected SQL — never the broken intermediate version
- Reframes the pitch from "visual query builder" to "the thing that makes Copilot's SQL not embarrassing" — a fundamentally stronger sell to the team
- **Deliverable:** Copilot Chat responses from `@oraquery` are pre-validated and auto-corrected before they ever reach the user
- **Effort:** 2-3 days (builds directly on existing validation engine — mostly classification of rules into auto-fixable vs. blocking, plus the auto-fix transforms themselves)

### Phase 3 — Live DB connection (blocked on Open Risk above)
- **If existing Oracle extension has a public API:** call it directly for schema introspection + query execution. ~1 day.
- **If not:** build a minimal standalone connection using `oracledb` npm package, scoped to read-only schema introspection + query execution. Needs its own credential prompt/secure storage (`vscode.SecretStorage`). ~3-4 days.
- Either way: webview gets real row counts, real column comments/nullability, "Run Query" button with results grid.
- **Deliverable:** schema auto-loads from live connection, queries can be executed and previewed in-panel.

### Phase 4 — Polish & rollout
- Explain Plan visualizer (render Oracle execution plan as a tree in the webview)
- Query history persisted via `vscode.Memento` (workspace or global state) instead of browser localStorage
- Internal docs / README for teammates: how to install the `.vsix`, how to use `@oraquery`
- Gather feedback from 2-3 teammates before wider internal rollout

## What's explicitly NOT in scope right now
- Marketplace publishing
- Building a new Oracle connector from scratch (unless Phase 3 forces it)
- Multi-database support (Postgres/MySQL etc.) — Oracle only
- Authentication/SSO — relies on existing Oracle extension's session or local creds

## Immediate next step
1. You confirm the exact Oracle extension name/publisher.
2. I check whether it exposes a public API.
3. Based on that, Phase 3 gets a real time estimate, and we lock the overall timeline.
4. Phase 1 scaffolding can start in parallel — it doesn't depend on the DB connection answer.

## Future ideas (not yet scheduled)
- Structural diff between two query versions (for PR review on SQL changes)
- Cost/performance prediction without running the query (extend cartesian-product estimator to flag missing-index joins, full table scans)
- Team query library with tagging/search (shared workspace-level query bank)

## Estimated effort (rough, pending Phase 3 risk resolution)
| Phase | Effort |
|---|---|
| 1 — Scaffold + webview port | 2-3 days |
| 2 — Copilot Chat Participant | 1-2 days |
| 2.5 — SQL reverse-engineering | 3-5 days |
| 2.6 — Closed-loop auto-fix | 2-3 days |
| 3 — Live connection | 1 day (best case) to 4 days (worst case) |
| 4 — Polish/rollout | 1-2 days |
| **Total** | **10-19 days**, depending on Phase 2.5/3 scope |
