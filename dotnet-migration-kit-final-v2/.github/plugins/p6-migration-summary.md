# Plugin: P6 — Migration Summary

## Identity
Final report generated after all phases complete. Shows what was migrated,
what was skipped, warnings, and deployment readiness.

## Invoke
```
Read .github/plugins/p6-migration-summary.md
```
Auto-triggered at end of release-bundle.

## Token rule
Reads only: migration-state.json, CODEBASE-MAP.md, auto-fix-report.json,
test results. Does not re-read source files.

## Report generation

Copilot reads all memory files and computes:

### From CODEBASE-MAP.md
```bash
DONE=$(grep -c "✅ DONE" .github/memory/CODEBASE-MAP.md)
BLOCKED=$(grep -c "🚧 BLOCK" .github/memory/CODEBASE-MAP.md)
SKIPPED=$(grep -c "⏭ SKIP" .github/memory/CODEBASE-MAP.md)
QUEUE=$(grep -c "⏳ QUEUE" .github/memory/CODEBASE-MAP.md)
```

### From migration-state.json
```
totalAspxPages → screensMigrated
totalSoapServices → soapServicesMigrated
totalConsoleProjects → workerServicesMigrated
```

### Output: migration-summary.json
```json
{
  "completedAt": "ISO-timestamp",
  "screensMigrated": 23,
  "apisMigrated": 41,
  "workerServicesMigrated": 5,
  "vbFilesConverted": 0,
  "oracleFilesUpdated": 0,
  "db2FilesUpdated": 0,
  "filesBlocked": 3,
  "filesSkipped": 7,
  "warnings": [
    "ReportService.cs blocked — Crystal Reports replacement not chosen",
    "LegacyOrmContext.cs blocked — OpenAccess ORM has no Core equivalent",
    "12 TODO-MIGRATION markers need human review"
  ],
  "buildStatus": "PASS",
  "testsPassing": 147,
  "testsFailing": 0,
  "coveragePercent": 74,
  "securityScanStatus": "PASS",
  "deploymentReady": true
}
```

### Output: MIGRATION-SUMMARY.md (human-readable)
```markdown
# Migration Summary — [ProjectName]

**Completed:** [date]
**Duration:** [X days]

## What was migrated
| Category | Count |
|----------|-------|
| WebForms pages → Razor/React/Angular | 23 |
| Web API 2 controllers → ASP.NET Core | 41 |
| Console apps → Worker Services | 5 |
| SOAP services → Minimal API | 3 |
| VB.NET files → C# | 0 |
| Oracle connections updated | 0 |

## What was blocked (needs human decision)
| File | Reason | Options |
|------|--------|---------|
| src/DAC/ReportService.cs | Crystal Reports | See crystal-reports section |
| src/DAC/LegacyOrmContext.cs | OpenAccess ORM | Rewrite with EF Core |

## TODO-MIGRATION markers (12 total)
Review each before production deployment.
Run: `grep -r "TODO-MIGRATION" src-core/ --include="*.cs"`

## Build & Test
- Build: ✅ 0 errors
- Unit tests: 147 passing / 0 failing
- Coverage: 74%
- Security scan: ✅ PASS

## Token savings achieved
- Files skipped via cache: [N]
- Estimated tokens saved: [N]K

## Next steps
1. Resolve [N] BLOCK items
2. Review all TODO-MIGRATION markers
3. Run: dotnet build src-core/ → 0 errors
4. Deploy to staging: /release-bundle v1.0.0 staging
```

## Copilot prompt
```
Read .github/memory/CODEBASE-MAP.md, .github/memory/migration-state.json,
and .github/memory/auto-fix-report.json.
Generate the migration summary report.
Write to .github/memory/migration-summary.json
and .github/memory/MIGRATION-SUMMARY.md.
Show the summary in chat when done.
```
