# Plugin: Migration Bundle

## Identity
Full automated migration for one project or entire solution.
Signal-driven — activates only agents your code needs.
Single-click entry point for the entire migration.

## Copilot prompt — start here
```
Read .github/plugins/migration-bundle.md and .github/memory/CODEBASE-MAP.md.
Read .github/memory/signals.json.
Run full migration for: [project name OR "all"].
```

---

## Execution sequence

### Bootstrap (first run only)
```
signals.json._status = "NOT_RUN"?
  → Read .github/agents/agent-discovery.md
  → Run full solution scan
  → Writes signals.json + CODEBASE-MAP.md
  → Continue below
```

### Project structure (once per solution)
```
src-core/ missing?
  → Read .github/agents/agent-clean-arch-scaffolder.md
  → Create SDK-style .csproj projects mirroring src-framework/
  → Create Domain/Application/Infrastructure/Presentation layers
  → Copy nuget.config into src-core/
  → Continue
```

### For each project (in dependencyOrder from signals.json)

**Per-file loop:**
```
FOR each ⏳ QUEUE file in project:

  1. Hash check:
     Run: git log -1 --format="%H" -- <filepath>
     Match + ✅ in CODEBASE-MAP.md → log "SKIP [file]" → next file

  2. BLOCK check:
     🚧 in CODEBASE-MAP.md → log "SKIP BLOCKED [file] — [reason]" → next file

  3. Agent selection (load ONE):
     .vb extension               → Read .github/agents/agent-vbnet.md
     hasConsoleApps + Main()     → Read .github/agents/agent-console-worker.md
     hasWebAPI2 + ApiController  → Read .github/agents/agent-webapi2.md
     hasOracle + OracleConn      → Read .github/agents/agent-oracle-db2.md
     hasDB2 + DB2Conn            → Read .github/agents/agent-oracle-db2.md
     hasEF6/hasEDMX/hasADONet    → Read .github/agents/agent-data-migrator.md
     hasWCF/hasSOAP              → Read .github/agents/agent-soap-wcf.md
     hasWebForms + .aspx file:
       Step 1: Read .github/agents/agent-roslyn-ast.md (extract AST JSON)
       Step 2: Check signals.json spaFramework field:
         "React"   → Read .github/agents/agent-spa-react.md
         "Angular" → Read .github/agents/agent-spa-angular.md
         "Razor"   → Read .github/agents/agent-ui-adapter.md
         not set   → use suggestedPath from each screen's AST JSON
     hasLDAP/hasApigee/hasPing/
     hasRedis/hasVenafi          → Read .github/agents/agent-enterprise-integrations.md
     file > 500 LOC              → Read .github/agents/agent-complexity-decomposer.md FIRST
     default .cs                 → Read .github/agents/agent-code-refactor.md

  4. Migrate file using loaded agent rules

  5. Update CODEBASE-MAP.md:
     ✅ DONE | [PROJECT] | [filepath] | [hash] | [agent] | [cov%] |
```

**Project gate (after all files in project):**
```
Run: dotnet build src-core/[Project].Core/ --configuration Release
0 errors? → continue to next project
Errors?   → show errors, pause, wait for fix, then continue
```

### Post-migration (after all projects complete)
```
Read .github/agents/agent-security-audit.md — security sweep (hash-cached)
Read .github/agents/agent-test-runner.md — run full test suite
Run: dotnet list src-core/ package --vulnerable --include-transitive
Run: grep -r "using System.Web" src-core/ --include="*.cs" → must be empty
Write .github/memory/migration-summary.md
```

---

## Error recovery
```
Agent fails on a file:
  Mark 🔄 WIP in map → retry once → skip if fails again
  > 3 consecutive failures → Read .github/plugins/diagnostic-bundle.md

Build gate fails:
  Show exact errors
  Pause — do not proceed to next project
  Fix errors → re-run build gate → continue
```

---

## Single-project shortcut prompts

### Run one project
```
Read .github/memory/CODEBASE-MAP.md and .github/memory/signals.json.
Migrate all ⏳ QUEUE files in [DAC/BC/SAC/BPC/Utilities/WebApp].
Signal-driven agent selection per copilot-instructions.md.
Update map after each file. Run dotnet build when project complete.
```

### Resume after context limit
```
Read .github/memory/CODEBASE-MAP.md and .github/memory/signals.json.
Continue from the last ⏳ QUEUE or 🔄 WIP file.
Load the correct agent for that file type.
```

### Check status
```
Read .github/memory/CODEBASE-MAP.md.
Count: ✅ DONE, ⏳ QUEUE, 🚧 BLOCK, 🔄 WIP.
Run: dotnet build src-core/ --configuration Release 2>&1 | tail -3
Show 5-line summary.
```
