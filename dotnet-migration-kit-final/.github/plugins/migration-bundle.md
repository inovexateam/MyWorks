# Plugin: Migration Bundle (Signal-Driven)

## Identity
Full automated migration for a project. Reads migration-state.json signals
to activate only relevant agents. Skips ✅ DONE files via hash check.
Does NOT follow a fixed phase order — computes order from dependency graph.

**Invoke:** `Run migration-bundle for [project or "all"]`

---

## Token rule — always first
```
1. Read CODEBASE-MAP.md — what's left?
2. Read migration-state.json — which signals are true?
3. If both empty → run discovery-scan first
4. Load ONE agent per file type. Never preload all.
```

---

## Execution model

```
BOOTSTRAP (if first run):
  migration-state.json missing?
    → Load skills/discovery-scan.md
    → Run scan → writes migration-state.json + CODEBASE-MAP.md
    → Re-read copilot-instructions.md

COMPUTE ORDER:
  Read all .csproj references in src-framework/
  Build dependency graph
  Topological sort → migration sequence
  Write to CODEBASE-MAP.md header

SCAFFOLD (once per solution):
  src-core/ missing?
    → Create SDK-style .csproj projects mirroring src-framework/
    → Copy nuget.config into src-core/
    → Load agents/agent-clean-arch-scaffolder.md
    → Create Domain/Application/Infrastructure/Presentation layers
  Already exists? → Skip entirely

FOR EACH PROJECT (in computed order):
  FOR EACH ⏳ QUEUE file in project:

    STEP 1: Hash check
      current = git rev-parse HEAD:<filepath>
      stored  = CODEBASE-MAP.md entry hash
      Match + ✅ DONE? → log "cache HIT [file]" → skip (~20 tokens)

    STEP 2: Signal-driven agent selection
      File is .vb?            → agents/agent-vbnet-migrator.md
      File has static void Main? → agents/agent-console-worker-migrator.md
      File has ApiController? → agents/agent-webapi2-migrator.md
      File has OracleConnection? → agents/agent-oracle-db2-migrator.md
      File has DB2Connection? → agents/agent-oracle-db2-migrator.md
      File has ServiceModel?  → agents/agent-soap-wcf-migrator.md
      File has StackExchange.Redis? → agents/agent-redis-venafi-migrator.md
      File is .aspx/.ascx?    → skills/roslyn-ast-analysis.md THEN agents/agent-ui-adapter.md
      File is EF6/EDMX?       → agents/agent-data-migrator.md
      File > 500 LOC?         → agents/agent-complexity-decomposer.md FIRST
      Default .cs file?       → agents/agent-code-refactor.md

    STEP 3: Migrate
      Load selected agent. Migrate file. Update CODEBASE-MAP.md.

    STEP 4: On BLOCK
      Log skip. Continue next file. Never stall.

  BUILD GATE:
    dotnet build src-core/[Project]/ --configuration Release
    0 errors? → continue to next project
    Errors? → show errors, wait for fix, then continue

POST-MIGRATION (run once after all projects done):
  Load plugins/p4-auto-fixer.md → fix deprecated APIs
  Load agents/agent-test-runner.md → run test suite
  Load agents/agent-security-audit.md → security sweep (hash-cached)
  Load plugins/p6-migration-summary.md → write final report
```

---

## Parallel-safe batches

Files with no cross-dependencies can be batched:
```
Utilities files → no inter-dependency → process up to 3 simultaneously
Shared service files → process sequentially (may share state)
.aspx pages → sequential (each needs AST extraction first)
```

---

## Single-project shorthand

```
# One project, reads signals automatically:
Read .github/memory/CODEBASE-MAP.md and .github/memory/migration-state.json.
Migrate all ⏳ QUEUE files in [DAC/BC/SAC/BPC/Utilities/WebApp].
Use signal-driven agent selection per copilot-instructions.md.
Update map after each file. Run build gate when project complete.

# Resume after context limit:
Read .github/memory/CODEBASE-MAP.md.
Continue from the last ⏳ QUEUE or 🔄 WIP file.
```

---

## Error recovery

```
Agent fails on a file:
  Mark file 🔄 WIP in map
  Retry once
  If retry fails: skip, log, continue
  > 3 consecutive failures: load plugins/diagnostic-bundle.md

Build gate fails:
  Show exact errors
  Do not proceed to next project
  Wait: "Paste these errors — I will fix then continue"
```
