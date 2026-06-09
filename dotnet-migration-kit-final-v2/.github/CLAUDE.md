# copilot-instructions.md
# .NET Framework → .NET 8 Migration Kit — GitHub Copilot Agent Mode

## Token-first protocol — every session
```
1. Read .github/memory/CODEBASE-MAP.md (~200 tokens)
2. Read .github/memory/migration-state.json if exists (~50 tokens)
3. For each file to process: check git hash vs stored hash
   Match → "cache HIT [file]" → skip (~20 tokens)
   Differ → load ONE skill/agent file → process → update map
4. NEVER load all skill/agent files. ONE file per task.
```

## Phase order (follow exactly)
```
P0 → skill: discovery-scan           → writes migration-state.json
P1 → create src-core/ structure
P2 → migrate class libraries (order: Utilities → DAC → BC → SAC → BPC)
P2 → agent-vbnet-migrator            (if migration-state.json: hasVBNet)
P2 → agent-console-worker-migrator   (if hasConsoleApps)
P3 → agent-oracle-db2-migrator       (if hasOracle OR hasDB2)
P3 → agent-redis-venafi-migrator     (if hasRedis OR hasVenafi)
P3 → agent-soap-wcf-migrator         (if hasWCF OR hasSOAP)
P3 → agent-ping-oidc                 (if hasPingFederate)
P2 → agent-ui-adapter                (WebForms last — after all libs done)
     skill: roslyn-ast-analysis      (run before ui-adapter for each screen)
P4 → plugins/p4-auto-fixer
P5 → agent-test-runner
P6 → plugins/p6-migration-summary
```

## Load exactly ONE file per task
| Task | Load this file |
|---|---|
| First scan / inventory | skills/discovery-scan.md |
| Analysing .cs file | skills/code-analysis.md |
| Packages / NuGet | skills/dependency-mapping.md |
| Security review | skills/security-review.md |
| AST extraction from .aspx | skills/roslyn-ast-analysis.md |
| Migrating .cs class | agents/agent-code-refactor.md |
| Migrating .aspx/.ascx | agents/agent-ui-adapter.md |
| EF6 / EDMX / ADO.NET | agents/agent-data-migrator.md |
| Oracle / DB2 | agents/agent-oracle-db2-migrator.md |
| Redis / Venafi | agents/agent-redis-venafi-migrator.md |
| VB.NET → C# | agents/agent-vbnet-migrator.md |
| Console → Worker | agents/agent-console-worker-migrator.md |
| SOAP / ASMX / WCF | agents/agent-soap-wcf-migrator.md |
| File > 500 LOC | agents/agent-complexity-decomposer.md |
| Post-migration security | agents/agent-security-audit.md |
| Tests | agents/agent-test-runner.md |
| Auto-fix deprecated APIs | plugins/p4-auto-fixer.md |
| Final summary report | plugins/p6-migration-summary.md |
| Something broken | plugins/diagnostic-bundle.md |
| Full project automation | plugins/migration-bundle.md |

## Project types → agents
```
ASP.NET WebForms (.aspx)   → roslyn-ast-analysis THEN agent-ui-adapter
ASP.NET MVC               → agent-code-refactor
Web API 2                 → agent-webapi2-migrator
ASMX / SOAP              → agent-soap-wcf-migrator
WCF                      → agent-soap-wcf-migrator
Console / Batch           → agent-console-worker-migrator
Class Libraries           → agent-code-refactor
VB.NET                   → agent-vbnet-migrator (output C#)
EF6 / EDMX               → agent-data-migrator
Oracle ODP.NET            → agent-oracle-db2-migrator
DB2                      → agent-oracle-db2-migrator
Redis                    → agent-redis-venafi-migrator
Venafi certificates       → agent-redis-venafi-migrator
```

## Migration order (non-negotiable)
```
1. Utilities (no deps)
2. DAC (data access)
3. BC (business)
4. SAC (service access)
5. BPC (business process)
6. WebApp / SOAP / Console (surface layers last)
```

## Packages: Artifactory only
```
https://artifactory.yourorg.com/artifactory/api/nuget/nuget-virtual
No nuget.org. nuget.config in repo root enforces this.
```

## Output mode
/terse by default — code + 5-line summary. No prose.

## Additional agents (added from enterprise recipe)
| Task | Load this file |
|---|---|
| Web API 2 → Core controllers | agents/agent-webapi2-migrator.md |
| Clean Architecture scaffold | agents/agent-clean-arch-scaffolder.md |
