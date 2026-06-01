# CLAUDE.md — .NET Migration Orchestrator

## ⚡ TOKEN-FIRST PROTOCOL — READ BEFORE ANYTHING ELSE

```
STEP 1 (always):  Read memory/CODEBASE-MAP.md   (~200 tokens)
STEP 2 (decide):  Is the target file ✅ DONE with matching hash?
                    YES → say "cache HIT" and skip. Cost: 20 tokens.
                    NO  → load ONLY the skill/agent you need (see map below)
STEP 3 (never):   Do NOT load all skill files. Do NOT load all agent files.
                  Load exactly one. Do your work. Update the map. Stop.
```

**Every unnecessary file load costs 600–1,500 tokens. With hundreds of projects,
loading all context at once burns your entire Copilot budget before writing a line.**

---

## What to Load — Decision Table

| You are doing | Load this ONE file |
|---|---|
| Analysing a .cs class | `skills/code-analysis.md` |
| Updating packages / .csproj | `skills/dependency-mapping.md` |
| Security review | `skills/security-review.md` |
| Migrating a .cs class | `agents/agent-code-refactor.md` |
| Migrating .aspx / .ascx | `agents/agent-ui-adapter.md` |
| EF6 / EDMX / data access | `agents/agent-data-migrator.md` |
| File > 500 LOC | `agents/agent-complexity-decomposer.md` |
| NuGet / blocked package | `agents/agent-dependency-resolver.md` |
| Running / writing tests | `agents/agent-test-runner.md` |
| Post-migration security | `agents/agent-security-audit.md` |
| Something is broken | `plugins/diagnostic-bundle.md` |
| Full project run | `plugins/migration-bundle.md` |
| Shipping a release | `plugins/release-bundle.md` |
| Security sweep | `plugins/security-bundle.md` |

---

## Project Types → Migration Approach

```
ASP.NET WebForms (.aspx)   → Razor Pages (agent-ui-adapter)
ASP.NET MVC               → ASP.NET Core MVC (agent-code-refactor)
ASMX / SOAP Services      → Minimal API or gRPC (agent-code-refactor + decision needed)
WCF Services              → CoreWCF or gRPC (escalate — needs arch decision)
Class Libraries           → Retarget to netstandard2.0 or net8 (agent-code-refactor)
EF6 / EDMX Models         → EF Core Code-First (agent-data-migrator)
```

---

## Migration Order (non-negotiable)

```
1. Shared class libraries with no internal deps  (Utilities, Contracts)
2. DAC — data access layer
3. BC, SAC — business + service layers
4. BPC — business process layer
5. WebApp / SOAP / WCF — surface layers last
```

## Secrets & Packages

All packages via Artifactory only:
`https://artifactory.yourorg.com/artifactory/api/nuget/nuget-virtual`

Approved packages listed in `memory/CODEBASE-MAP.md` (PKG section).
Security tools: use org-hosted scanner or `dotnet list package --vulnerable` (built-in, zero external fetch).

## Output Mode Default

Use `/terse` unless asked otherwise. Code + 5-bullet summary. No prose.
Switch to `/verbose` only for onboarding or complex architectural decisions.

---

## Quick Commands

```
/analysis-mode          — map the codebase, no code written
/migration-mode [file]  — migrate one file
/testing-mode           — run or write tests
/release-mode v1.0 stg  — release validation
/terse                  — code-only output
/summary                — status in 10 lines
/diagnostic-bundle [err]— something broke
```

Full docs only if needed: `.github/skills/` · `.github/agents/` · `.github/plugins/`
