# GITHUB-COPILOT.md — .NET Migration Orchestrator

## ⚡ CONTEXT-FIRST PROTOCOL — READ BEFORE ANYTHING ELSE

```
STEP 1 (always):  Read memory/CODEBASE-MAP.md   (~200 tokens)
STEP 2 (decide):  Is the target file ✅ DONE with matching hash?
                    YES → say "cache HIT" and skip. Cost: 20 tokens.
                    NO  → load ONLY the skill/agent you need (see map below)
STEP 3 (never):   Do NOT load all skill files. Do NOT load all agent files.
                  Load exactly one. Do your work. Update the map. Stop.
```

**Every unnecessary file load costs tokens. With large repos, loading all context at once wastes the budget before writing a line.**

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

---

## GitHub Copilot Usage Instructions

1. Open the repo in VS Code.
2. Use GitHub Copilot Chat.
3. Select `/migration-mode` for active migration work.
4. Start with the highest-level analysis prompt, not by editing code immediately.
5. Always begin with `memory/CODEBASE-MAP.md` and the migration checklist.
6. Use prompt files from `.github/prompts/` based on the task.
7. When the guide refers to migration rules, use `rules/migration-and-security-rules.md`.
8. For token-conscious sessions, use `agents/token-saver.agent.md` or invoke the agent `token-saver`.

---

## Recommended Starting Flow

1. Start in Chat and say:

```
I want to migrate this .NET Framework project to .NET Core/.NET 8.
First, read `.github/memory/CODEBASE-MAP.md`, then tell me the best next file to migrate.
```

2. If the tool supports modes, activate:

```
/migration-mode
```

3. If you want assessment before migration, use:

```
/analysis-mode
```

4. If you want package / dependency work, use:

```
/testing-mode
```
```

5. Once you have the recommended next file, use the migration prompt form:

```
Use `.github/prompts/migrate-framework-to-core.md` if the file is framework code.
Use `.github/prompts/refactor-ui.md` if the file is UI or WebForms.
Use `.github/prompts/update-dependencies-run-tests-analyze.md` if the task is package updates, tests, or analysis.

Agent invocation example:

```
INVOKE agent: token-saver
TARGET: <file-or-folder-path>
MODE: terse
OUTPUT: inline
```
```

---

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

---

## Starting Point for Copilot

1. Read `.github/memory/CODEBASE-MAP.md`.
2. Read `.github/chatmodes/migration-mode.md`.
3. Ask Copilot for the highest priority file or project area.
4. Confirm the migration plan for that file before changing it.
5. Use the appropriate `.github/agents/` or `.github/skills/` file if the prompt says it is needed.

---

## Final Recommended Flow

1. `Open project in VS Code`
2. `Read memory/CODEBASE-MAP.md`
3. `Activate /migration-mode`
4. `Ask: "What is the next migration task?"`
5. `Use the right prompt from .github/prompts/`
6. `Review the plan`
7. `Migrate the file`
8. `Run tests`
9. `Run security review`
10. `Move to the next file`

---

## Note

This repo is configured for GitHub Copilot usage. Do not use Claude-specific naming or instructions.
