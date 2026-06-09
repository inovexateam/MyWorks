# Copilot: Analysis Mode

## Activate with this prompt
```
Read .github/copilot-instructions.md. Enter analysis mode: scan
this solution and produce a migration assessment. Read-only —
no code changes. Load .github/skills/discovery-scan.md.
```

## What Copilot does in this mode
- Scans all .cs, .vb, .aspx, .asmx, .csproj files
- Detects all technology signals
- Computes dependency order from .csproj graph
- Writes migration-state.json + CODEBASE-MAP.md
- Produces assessment table: project, LOC, signals, risk, hours

## Assessment output format
```markdown
## Migration Assessment: [Solution]

| Project | LOC | Signals | Risk | Est. Hours |
|---------|-----|---------|------|------------|
| Utilities | 2,400 | none | LOW | 4 |
| DAC | 8,700 | hasEF6, hasADONet | HIGH | 20 |
| BC | 12,000 | hasLog4Net, hasLDAP | MEDIUM | 12 |
| WebApp | 35,000 | hasWebForms, hasPingFederate | CRITICAL | 60 |

Dependency order: Utilities → DAC → BC → WebApp
Blocked (need decision): [list]
Total estimated: [X] hours
```

## Exit analysis mode
```
Analysis complete. Start migration:
Read .github/memory/CODEBASE-MAP.md. Migrate all ⏳ QUEUE
files in [first project from ORDER line].
```
