# .NET Migration Kit — Copilot Instructions
# Auto-loaded in Agent mode. Keep reading this file only. Load prompts on demand.

## Every session
1. Read .github/memory/MAP.md (~200 tokens)
2. Read .github/memory/signals.json (~50 tokens)
3. Hash check before any file: git log -1 --format="%H" -- <filepath>
   Match + ✅ in MAP → skip (20 tokens). Differ → work (1,500 tokens).

## Signal → prompt routing
Only load prompts for true signals. False signal = 0 tokens.

| Condition | Load this prompt |
|---|---|
| First run (no signals.json data) | prompts/00-discovery.md |
| src-core/ doesn't exist | prompts/01-structure.md |
| Standard .cs file | prompts/02-migrate-cs.md |
| hasEF6 OR hasEDMX OR hasADONet OR hasOracle OR hasDB2 | prompts/03-data-layer.md |
| hasLDAP OR hasApigee OR hasPingFederate OR hasRedis OR hasVenafi OR hasWCF OR hasSOAP | prompts/04-enterprise-integrations.md |
| hasWebForms (.aspx/.ascx) | prompts/05-webforms-ui.md |
| hasWebAPI2 | prompts/06-webapi2.md |
| hasVBNet | prompts/07-vbnet.md |
| hasConsoleApps | prompts/08-console-worker.md |
| Post-migration cleanup | prompts/09-security-autofix.md |
| New session / context limit hit | prompts/10-resume.md |
| Security design review | prompts/11-security-design-review.md |
| hasCrystalReports 🚧 | prompts/12-crystal-reports.md |

## Migration order
Computed from .csproj dependency graph — written to MAP.md ORDER line on first run.
Never fixed. Always: leaves first. Typical: Utilities → DAC → BC → SAC → BPC → WebApp.

## BLOCK = skip and continue
🚧 in MAP.md → log "SKIPPING [file] — [reason]" → next file. Never stall entire session.

## Artifactory only
All packages via nuget.config. nuget.org is disabled.
Secrets: ARTIFACTORY_USER + ARTIFACTORY_TOKEN as env vars / GitHub Secrets only.

## After every file
Update MAP.md: ✅ DONE | [PROJECT] | [filepath] | [hash] | [prompt-used] | [cov%] |
After every project: dotnet build src-core/[Project].Core/ — must be 0 errors.
