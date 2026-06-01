# CLAUDE.md — ASP.NET Framework → .NET 8 Migration Orchestrator

## Mission
Migrate a large ASP.NET Framework 4.7.1/4.8 web application (WebApp + BC + BPC + SAC + DAC + Utilities) to .NET 8, preserving 100% functionality and meeting or exceeding all existing security standards.

---

## Quick Start

```
New session? Start here:

1. Activate a mode:
   /analysis-mode          ← First time or reviewing progress
   /migration-mode         ← Ready to migrate code
   /testing-mode           ← Verify migrated code
   /release-mode [v] [env] ← Shipping a release

2. Or run a bundle:
   /migration-bundle [project]   ← Full automated migration
   /security-bundle              ← Full security sweep
   /diagnostic-bundle [symptom]  ← Something went wrong

3. Or ask naturally:
   "Migrate this file" → I'll activate migration-mode
   "What's left to do?" → I'll show checklist progress
   "Why is this test failing?" → I'll run diagnostic-bundle
   "Is this ready to ship?" → I'll run release-bundle
```

---

## Project Map

```
YourSolution/
├── src/
│   ├── Utilities/          Migrate first — no internal deps
│   ├── DAC/                Data Access — EF6 → EF Core (agent-data-migrator)
│   ├── BC/                 Business Components — depends on DAC
│   ├── SAC/                Service Access — depends on BC
│   ├── BPC/                Business Process — depends on BC + SAC
│   └── WebApp/             UI layer — migrate last
│
├── tests/
│   ├── UnitTests/          One test project per src project
│   ├── IntegrationTests/   WebApplicationFactory-based
│   └── E2ETests/           Playwright browser tests
│
└── .github/                ← YOU ARE HERE
    ├── skills/             Capabilities any agent can invoke
    ├── agents/             Specialist agents for each task type
    ├── hooks/              Git + CI automation
    ├── rules/              Non-negotiable guardrails
    ├── plugins/            Multi-agent orchestration workflows
    ├── prompts/            Task-specific instruction sets
    ├── chatmodes/          Conversation mode definitions
    ├── workflows/          GitHub Actions CI pipeline
    ├── memory/             Persistent state across sessions
    └── output-styles/      Response format control
```

---

## Agent Directory

| Agent | When to Use | Invokes |
|-------|-------------|---------|
| `agent-code-refactor` | Migrating any `.cs` class file | code-analysis, pattern-recognition |
| `agent-dependency-resolver` | Package updates, NuGet conflicts | dependency-mapping |
| `agent-ui-adapter` | Migrating `.aspx` / `.ascx` pages | code-analysis, pattern-recognition |
| `agent-data-migrator` | EF6 → EF Core, EDMX removal | code-analysis, dependency-mapping |
| `agent-test-runner` | Running/writing tests | (reads all agents' outputs) |
| `agent-security-audit` | Security review (runs on all files) | security-review |
| `agent-complexity-decomposer` | Files > 500 LOC | code-analysis |
| `diagnostic-bundle` | Something is broken | All agents as needed |

**Escalation rule:** If ANY agent hits a blocker it can't resolve in 2 attempts → escalate to human via diagnostic-bundle format.

---

## Skill Directory

| Skill | When to Invoke |
|-------|---------------|
| `code-analysis` | Before migrating any file |
| `dependency-mapping` | Before touching any .csproj |
| `pattern-recognition` | When pattern is ambiguous |
| `migration-checklist` | After every completion, before every PR |
| `security-review` | After every migration, before every merge |

---

## Non-Negotiable Rules (Summary)

```
1. Migrate in order: Utilities → DAC → BC → SAC → BPC → WebApp
2. Never commit System.Web.* to a Core project
3. Never commit secrets to any file
4. Zero System.Web in migrated code — enforced by pre-commit hook
5. All tests must pass before PR merges
6. agent-security-audit reviews every PR
7. Business logic is frozen during migration (no new features)
8. Large files (>500 LOC): decompose before migrating
9. One file per branch (migration/[project]/[classname])
10. No guessing — escalate when uncertain
```

Full rules: `.github/rules/`

---

## Migration Checklist Progress

See: `.github/memory/known-issues-and-state.md` for current state.

Phases: P0 (Assessment) → P1 (Structure) → P2 (Host) → P3 (DI) → P4 (Data) → P5 (Auth) → P6 (Session) → P7 (UI) → P8 (Security) → P9 (Testing) → P10 (Deploy)

Full checklist: `.github/skills/migration-checklist.md`

---

## Common Commands Reference

```bash
# Build
dotnet build --configuration Release

# All unit tests
dotnet test --filter "Category!=Integration&Category!=E2E"

# Security test category only
dotnet test --filter "Category=Security"

# Feature parity tests
dotnet test --filter "Category=FeatureParity"

# With coverage
dotnet test --collect:"XPlat Code Coverage"

# Vulnerable packages
dotnet list package --vulnerable --include-transitive

# Code format check
dotnet format --verify-no-changes

# EF Core migration
dotnet ef migrations add [Name] --project src/DAC --startup-project src/WebApp
dotnet ef database update --project src/DAC --startup-project src/WebApp

# Generate idempotent SQL script (for DBA review)
dotnet ef migrations script --idempotent --output migration-script.sql

# Secret scan
trufflehog filesystem .
```

---

## Getting Help

```
"I don't know what to do next"
→ /analysis-mode — let's map the current state

"This is broken and I don't know why"
→ /diagnostic-bundle [paste error]

"What does this rule mean?"
→ Ask — I'll explain the rule and its rationale

"I think a rule is wrong for our situation"
→ Explain the context — rules can be documented exceptions
   with justification. Nothing is changed without documentation.

"The migration seems stuck"
→ Share the blocker — I'll identify the escalation path
```
