# .NET Framework → .NET 8 Migration Kit

Drop the `.github/` folder into your repo root. That's the entire tool.

---

## 5-minute setup

```bash
# 1. Clone your existing ASP.NET app
git clone https://your-org/your-app.git
cd your-app

# 2. Copy this .github/ folder into the root
cp -r /path/to/migration-kit/.github ./

# 3. Configure Artifactory (edit this one line)
sed -i 's|https://artifactory.yourorg.com|https://YOUR-REAL-ARTIFACTORY-URL|g' \
  .github/nuget.config

# 4. Open in VS Code
code .

# 5. In VS Code, open Claude Code chat and type exactly:
@claude start migration
```

Step 5 triggers the entire workflow automatically.

---

## What happens after "@claude start migration"

Claude reads `CLAUDE.md`, scans your solution, and does this — in order, with no further input:

```
1. Scans all .cs, .aspx, .ascx, .asmx files
2. Detects: System.Web, ADO.NET, LDAP, Apigee, Ping/SAML, Crystal Reports
3. Writes CODEBASE-MAP.md (your persistent progress file)
4. Creates the new src-core/ project structure
5. Migrates Utilities → DAC → BC → SAC → BPC (in order)
6. Stops before WebApp and shows you a summary
7. Lists any blocked items needing your decision
```

You intervene at 4 specific points (see below). Everything else is automatic.

---

## The 4 manual interventions

| When | What you do | Time |
|------|-------------|------|
| After scan | Review BLOCK entries in CODEBASE-MAP.md — make decisions on Crystal Reports, Apigee contracts, Ping config | 30 min |
| After project structure created | Add your real Artifactory URL + credentials to nuget.config | 5 min |
| After each project completes | Run `dotnet build src-core/` — must be 0 errors before next project | 2 min |
| After Ping/OIDC flagged | Provide client ID, client secret, discovery URL from your identity team | 10 min |

Total manual time: under 1 hour on a typical large application.

---

## Checking token savings (takes 10 seconds)

```bash
# Count cache hits vs remaining work
grep "✅ DONE" .github/memory/CODEBASE-MAP.md | wc -l   # hits
grep "⏳ QUEUE" .github/memory/CODEBASE-MAP.md | wc -l  # remaining
grep "🚧 BLOCK" .github/memory/CODEBASE-MAP.md | wc -l  # blocked

# Simple math:
# hits × 20 tokens = cache hit cost
# remaining × 1500 tokens = full analysis cost
# Without map: (hits + remaining) × 1500
# Saving = 1 - (hits×20 + remaining×1500) / ((hits+remaining)×1500)
```

On a 200-file app at 70% cache hit rate: ~130K tokens saved per session.

---

## Resuming after a break (next session)

```bash
# In VS Code Claude Code chat:
@claude resume migration
```

That's it. Claude reads the map, sees what's done, picks up from the next QUEUE item. No re-analysis of completed files.

---

## Your specific patterns — migration paths

| Pattern in your app | Migration path |
|---------------------|---------------|
| LDAP / DirectoryServices | `Novell.Directory.Ldap.NETStandard` (Artifactory) |
| ADO.NET SqlConnection | Dapper (minimal change) or EF Core |
| Apigee HTTP calls | `IHttpClientFactory` typed client, secrets in Key Vault |
| Ping login / SAML | OIDC middleware: `AddOpenIdConnect`, Ping as IdP |
| FormsAuthentication | Cookie auth or ASP.NET Core Identity |
| `.aspx` pages | Razor Pages (all server controls mapped in agent-ui-adapter) |
| `.ascx` user controls | Partial Views or View Components |
| `.asmx` SOAP services | Minimal API or CoreWCF |
| `web.config` | `appsettings.json` + env vars + Azure Key Vault |
| Crystal Reports | Needs decision — 4 options in `.github/agents/agent-dependency-resolver.md` |
| UpdatePanel | AJAX partial views or Blazor |
| ViewState | Eliminated — state moves to TempData / Session / re-query |

---

## Folder structure created

```
your-repo/
├── src-framework/     ← your original app, never touched
│   └── (all your existing projects)
├── src-core/          ← new .NET 8 app built here
│   ├── WebApp.Core/
│   ├── BC.Core/
│   ├── DAC.Core/
│   ├── SAC.Core/
│   ├── BPC.Core/
│   └── YourApp.Core.sln
├── .github/           ← this tool
│   ├── CLAUDE.md      ← the entry point (always loaded first, ~200 tokens)
│   ├── memory/
│   │   └── CODEBASE-MAP.md   ← your live progress file
│   ├── agents/        ← loaded on-demand only
│   ├── skills/        ← loaded on-demand only
│   └── plugins/       ← orchestration workflows
└── nuget.config       ← Artifactory only, no nuget.org
```

---

## Token efficiency explained simply

Every Copilot/Claude session has a token budget. The old recipe approach loads
all instructions into every session, which on a large app consumes 30K–80K tokens
before writing a single line of code.

This tool loads one 200-token map file first. If a file is already done (cached),
it skips it for ~20 tokens instead of ~1,500. On a 200-file app that's 60% migrated,
that's ~130K tokens saved per session.

The map file is just a text file — `CODEBASE-MAP.md`. Commit it to git. It's your
team's shared progress tracker. When Alice migrates DAC on Tuesday and Bob starts
Wednesday, Bob's session reads the map and continues from where Alice left off
without re-checking anything.

---

## Running multiple projects in one VS Code session

Open the full solution folder (`code .` from repo root). Claude Code can see all
projects. The map has entries for all projects. Type:

```
@claude run migration-bundle for project: DAC
```

When DAC finishes:
```
@claude run migration-bundle for project: BC
```

Each command is independent. Each one reads the map, works only on that project's
QUEUE entries, updates the map when done.

---

## FAQ

**Does it need the app to be running?**
No. Source files on disk only.

**Does it need the old app to compile?**
No. Claude reads `.cs` files as text.

**What if a file is partially migrated when a session times out?**
The map shows it as 🔄 WIP. Next session picks up from that file.

**What about our org's static analysis rules?**
Add your Roslyn analyzer package from Artifactory to `.csproj`.
Violations appear as build errors — already caught in the CI pipeline.
Results cached per file by git hash in CODEBASE-MAP.md.

**Will the new app be a completely separate codebase?**
Yes — `src-core/` is a new project. Old app in `src-framework/` is untouched
until you're ready to decommission it. Both exist in the same repo.
