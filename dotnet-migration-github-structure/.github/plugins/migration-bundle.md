# Plugin: Migration Bundle

## Identity
This plugin orchestrates the complete migration workflow for a single project or feature. It sequences agent invocations, manages handoffs, and ensures nothing is skipped.

**Invoke with:** `/migration-bundle [target-project]`

---

## What This Plugin Does

Runs the full migration pipeline for a project:
```
agent-complexity-decomposer (if needed)
    ↓
agent-dependency-resolver
    ↓
agent-code-refactor (parallel per class)
    ↓
agent-ui-adapter (WebApp project only)
    ↓
agent-data-migrator (DAC project only)
    ↓
agent-test-runner
    ↓
agent-security-audit
    ↓
[MERGE GATE]
```

---

## Orchestration Script

```
PLUGIN: migration-bundle
INPUT: project = [Utilities | DAC | BC | SAC | BPC | WebApp]

PHASE 0: Pre-flight
  1. Load migration-checklist.md — verify phase is open
  2. Verify all dependencies of [project] are already migrated
  3. If [project] = WebApp, verify BC, BPC, SAC, DAC all complete
  4. Create migration branch: migration/[project]/bundle-[date]

PHASE 1: Analysis
  INVOKE agent-complexity-decomposer
  TARGET: All files in [project] > 500 LOC
  WAIT: Decomposition plans approved
  IF decomposition plans exist:
    → Execute decompositions
    → Re-inventory files (decomposed classes replace original)

PHASE 2: Dependencies  
  INVOKE agent-dependency-resolver
  TARGET: [project].csproj
  WAIT: All packages resolved, .csproj updated
  GATE: Zero vulnerable packages

PHASE 3: Data Layer (DAC only)
  IF project == DAC:
    INVOKE agent-data-migrator
    TARGET: All .edmx files + EF6 contexts
    WAIT: EF Core models generated, migrations created
    GATE: Row count validation passes

PHASE 4: Code Refactor
  FOR each file in [project] (in dependency order):
    INVOKE agent-code-refactor
    TARGET: [file]
    PARALLEL: Up to 3 files at once (if no shared dependencies)
    ON_ERROR: Pause parallel, resolve blocker, resume
  WAIT: All files migrated
  GATE: dotnet build → 0 errors

PHASE 5: UI Adaptation (WebApp only)
  IF project == WebApp:
    INVOKE agent-ui-adapter
    TARGET: All .aspx pages (complexity order: simple → complex)
    WAIT: All pages converted to Razor
    GATE: Zero .aspx files remain

PHASE 6: Testing
  INVOKE agent-test-runner
  TARGET: [project]
  SCOPE: unit + integration
  WAIT: Test run complete
  GATE: 0 failures, coverage ≥ minimum

PHASE 7: Security Audit
  INVOKE agent-security-audit
  TARGET: All migrated files in [project]
  WAIT: Audit complete
  GATE: 0 CRITICAL, 0 HIGH issues

PHASE 8: PR Creation
  IF all gates passed:
    CREATE PR: "Migration: [project] → .NET 8"
    ASSIGN: Lead developer for final review
    ATTACH: Migration summary report
  ELSE:
    CREATE blocking issues for each gate failure
    NOTIFY: Relevant agents for remediation
```

---

## Migration Summary Report (Auto-generated)

```markdown
## Migration Bundle Report: [ProjectName]

**Completed:** [date]
**Duration:** [hours]
**Branch:** migration/[project]/bundle-[date]

### Files Migrated
| File | LOC | Effort | Status |
|------|-----|--------|--------|

### Dependencies Resolved  
| Package | Old | New | Notes |
|---------|-----|-----|-------|

### Checklist Items Completed
- [P1.2] ✅ [P1.7] ✅ [P3.2] ✅ ...

### Test Results
- Unit Tests: [X passed, 0 failed]
- Integration Tests: [X passed, 0 failed]
- Coverage: [X%]

### Security Audit
- OWASP Score: [X/10]
- Vulnerabilities: 0 CRITICAL, 0 HIGH

### Remaining Work
[Any items deferred with justification]
```

---

## Error Recovery

When an agent fails mid-bundle:

```
1. Record: which agent, which file, what error
2. Do NOT revert completed work
3. Attempt agent retry (once)
4. If retry fails: pause bundle, escalate to human
5. Document blocked state in migration-checklist.md
6. Resume from failure point once resolved
```
