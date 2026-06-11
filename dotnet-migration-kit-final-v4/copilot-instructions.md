# .NET Migration Kit — GitHub Copilot Agent Instructions
# Auto-loaded in Agent mode before every conversation.

## Session start — every time
1. Read .github/memory/CODEBASE-MAP.md
2. Read .github/memory/signals.json (if exists)
3. Hash check every file before working:
   git log -1 --format="%H" -- <filepath>
   Match + ✅ in map → SKIP (20 tokens). Differ → work (1,500 tokens).

## Signal → agent routing (load ONE agent per file)
| File type / signal true | Load this agent |
|---|---|
| No signals.json / first run | agents/agent-discovery.md |
| src-core/ missing | agents/agent-clean-arch-scaffolder.md |
| Any .cs class (default) | agents/agent-code-refactor.md |
| hasEF6 OR hasEDMX OR hasADONet | agents/agent-data-migrator.md |
| hasOracle OR hasDB2 | agents/agent-oracle-db2.md |
| hasVBNet (.vb files) | agents/agent-vbnet.md |
| hasConsoleApps | agents/agent-console-worker.md |
| hasWebAPI2 | agents/agent-webapi2.md |
| hasWCF OR hasSOAP | agents/agent-soap-wcf.md |
| hasLDAP OR hasApigee OR hasPingFederate OR hasRedis OR hasVenafi | agents/agent-enterprise-integrations.md |
| File > 500 LOC | agents/agent-complexity-decomposer.md FIRST |
| .aspx/.ascx — AST not extracted | agents/agent-roslyn-ast.md |
| .aspx/.ascx — AST exists, suggestedPath=ReactSPA | agents/agent-spa-react.md |
| .aspx/.ascx — AST exists, suggestedPath=AngularSPA | agents/agent-spa-angular.md |
| .aspx/.ascx — AST exists, suggestedPath=RazorPage | agents/agent-ui-adapter.md |
| Security review | agents/agent-security-audit.md |
| Tests | agents/agent-test-runner.md |
| Broken / error | plugins/diagnostic-bundle.md |
| Full project automation | plugins/migration-bundle.md |

## UI migration path selection
Read signals.json for spaFramework flag:
  spaFramework: "React"   → all .aspx → agent-spa-react.md
  spaFramework: "Angular" → all .aspx → agent-spa-angular.md
  spaFramework: "Razor"   → all .aspx → agent-ui-adapter.md
  spaFramework not set    → use suggestedPath from AST JSON per screen

Set spaFramework in signals.json before starting WebApp migration.

## Migration order
From CODEBASE-MAP.md ORDER line (computed from .csproj graph by agent-discovery).
Typical: Utilities → DAC → BC → SAC → BPC → WebApp. Always leaves-first.

## BLOCK = skip and continue
🚧 in map → log "SKIPPING [file] — [reason]" → next file. Never stall.

## After every file
Update CODEBASE-MAP.md: ✅ DONE | PROJECT | filepath | hash | agent | cov% |
After every project: dotnet build src-core/[Project].Core/ — 0 errors required.

## Packages
Artifactory only. nuget.config in repo root disables nuget.org.
