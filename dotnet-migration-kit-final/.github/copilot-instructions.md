# Copilot Agent Instructions — .NET Migration Kit

## Read this file first. Every session. One time. ~200 tokens.

---

## How this kit works — NOT phases

This kit does NOT follow a fixed P0→P6 phase sequence.
Migration order is computed from your actual project — signals in
migration-state.json activate only the agents your code needs.

```
Session start:
  1. Read .github/memory/CODEBASE-MAP.md         (~200 tokens)
  2. Read .github/memory/migration-state.json     (~50 tokens — if exists)
  3. For each file you are about to work on:
       get hash = git rev-parse HEAD:<filepath>
       if map shows ✅ DONE + same hash → skip (~20 tokens, not ~1,500)
  4. Load exactly ONE agent or skill file. Work. Update map. Stop.
     Never preload all agents. Never load what the signals don't trigger.
```

---

## Signal-driven agent activation

Read migration-state.json flags. Load only what is true.

```
hasOracle: true          → agents/agent-oracle-db2-migrator.md
hasDB2: true             → agents/agent-oracle-db2-migrator.md
hasVBNet: true           → agents/agent-vbnet-migrator.md
hasConsoleApps: true     → agents/agent-console-worker-migrator.md
hasWebAPI2: true         → agents/agent-webapi2-migrator.md
hasWCF: true             → agents/agent-soap-wcf-migrator.md
hasSOAP: true            → agents/agent-soap-wcf-migrator.md
hasRedis: true           → agents/agent-redis-venafi-migrator.md
hasVenafi: true          → agents/agent-redis-venafi-migrator.md
hasLDAP: true            → agents/agent-code-refactor.md (LDAP rules inside)
hasPingFederate: true    → agents/agent-code-refactor.md (Ping OIDC rules inside)
hasEF6: true             → agents/agent-data-migrator.md
hasEDMX: true            → agents/agent-data-migrator.md
hasADONet: true          → agents/agent-data-migrator.md
hasWebForms: true        → skills/roslyn-ast-analysis.md THEN agents/agent-ui-adapter.md
hasCrystalReports: true  → 🚧 BLOCK — human decision required (see memory/CODEBASE-MAP.md)
```

If migration-state.json does not exist yet:
→ Load skills/discovery-scan.md. Run scan. Write migration-state.json. Then re-read this file.

---

## Dependency graph — compute migration order

Do not use a fixed order. Compute it from the actual project:

```
1. Read all .csproj files in src-framework/
2. Build: for each project, which projects does it reference?
3. Find leaves — projects with no internal dependencies → migrate first
4. Topological sort remaining projects
5. Write computed order to CODEBASE-MAP.md header comment
6. Follow that order. Not P1→P2→P3.
```

Typical result for most solutions:
```
Utilities → DAC → BC → SAC → BPC → WebApp
(but always verify — your solution may differ)
```

---

## What to load for each file type

One file. Load it. Do the work. Update the map.

| What you're doing | Load this |
|---|---|
| First run — no migration-state.json | skills/discovery-scan.md |
| Analysing complexity of a .cs file | skills/code-analysis.md |
| Package / NuGet dependency work | skills/dependency-mapping.md |
| AST extraction from .aspx BEFORE migrating UI | skills/roslyn-ast-analysis.md |
| Security review of migrated file | skills/security-review.md |
| Migrating any .cs class file | agents/agent-code-refactor.md |
| Migrating .aspx or .ascx | agents/agent-ui-adapter.md |
| EF6, EDMX, ADO.NET data layer | agents/agent-data-migrator.md |
| Oracle or DB2 connections | agents/agent-oracle-db2-migrator.md |
| Redis or Venafi | agents/agent-redis-venafi-migrator.md |
| VB.NET (.vb) files | agents/agent-vbnet-migrator.md |
| Console/batch app | agents/agent-console-worker-migrator.md |
| Web API 2 controllers | agents/agent-webapi2-migrator.md |
| SOAP, ASMX, WCF | agents/agent-soap-wcf-migrator.md |
| File > 500 LOC | agents/agent-complexity-decomposer.md |
| Clean Architecture scaffold (once) | agents/agent-clean-arch-scaffolder.md |
| Security audit | agents/agent-security-audit.md |
| Running / writing tests | agents/agent-test-runner.md |
| Fix deprecated APIs post-migration | plugins/p4-auto-fixer.md |
| Final summary report | plugins/p6-migration-summary.md |
| Something is broken | plugins/diagnostic-bundle.md |
| Automate full project | plugins/migration-bundle.md |

---

## BLOCK handling — never stall

When a file is 🚧 BLOCK in CODEBASE-MAP.md:
```
1. Log: "SKIPPING [file] — BLOCK: [reason]"
2. Continue to next ⏳ QUEUE file immediately
3. Do NOT stop the entire session
4. Include all BLOCK files in the final summary
```

---

## Packages — Artifactory only

All packages from your org's Artifactory NuGet feed.
Config: .github/nuget.config (copy into src-core/ root)
Never add nuget.org as a source.

---

## Output style

Terse by default: migrated code + 5-bullet summary.
No phase labels. No P0/P1/P2 tags. Just work.
