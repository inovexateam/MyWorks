# .NET Migration Kit — GitHub Copilot

## Setup (5 minutes)
```bash
git clone https://your-org/your-aspnet-app.git
cd your-aspnet-app
# Copy this .github/ folder into repo root
git add .github/ && git commit -m "chore: add migration kit"
# Edit nuget.config — replace Artifactory URL placeholder
code .
```

## Start migration (single prompt)
Open Copilot Chat → select **Agent** mode → paste:
```
Read .github/plugins/migration-bundle.md and .github/memory/CODEBASE-MAP.md.
Read .github/memory/signals.json.
Run full migration for all projects.
```

That's it. Copilot runs discovery, builds the map, scaffolds src-core/, and migrates every file in dependency order using only the agents your code needs.

## Direct .aspx → React or Angular migration

Set your target framework **before** starting WebApp migration:

Edit `.github/memory/signals.json`:
```json
"spaFramework": "React"    // or "Angular" or "Razor"
```

Then run migration-bundle — Copilot will:
1. Extract AST from each .aspx (controls, events, data bindings, session reads)
2. Generate React/Angular component + TypeScript types + data hooks
3. Generate .NET 8 API controller with all endpoints the page needs
4. Wire up routing (React Router / Angular Router)
5. Create Layout component from MasterPage

| .aspx pattern | Generated output |
|---|---|
| GridView + Search + UpdatePanel | List component with fetch, pagination, search state |
| Form + Validators | Edit component with validation, error display |
| Button_Click | onClick handler or form onSubmit |
| Page_Load(!IsPostBack) | useEffect (React) / ngOnInit (Angular) |
| Session["key"] | JWT claims via /api/auth/me |
| MasterPage | Layout component wrapping router |
| .ascx UserControl | Standalone React/Angular component |


## Resume after break
```
Read .github/memory/CODEBASE-MAP.md and .github/memory/signals.json.
Continue from the last ⏳ QUEUE or 🔄 WIP file.
```

## Manual interventions (4 total)
| When | What |
|------|------|
| After discovery | Review 🚧 BLOCK entries — decide Crystal Reports replacement |
| After structure created | Replace Artifactory URL in nuget.config |
| After each project | `dotnet build src-core/[Project].Core/` — must be 0 errors |
| Ping/OIDC flagged | Get ClientId, ClientSecret, Authority from identity team → Key Vault |

## Token savings
| Situation | Cost |
|---|---|
| ✅ DONE file (hash match) | ~20 tokens |
| New file analysis | ~1,500 tokens |
| Signal not triggered | 0 tokens |
| 70% done on 200-file solution | ~69% saving vs restart |

## Kit structure
```
.github/
├── copilot-instructions.md    ← auto-loaded, signal routing table
├── nuget.config               ← Artifactory only
├── README.md                  ← this file
├── agents/                    ← 16 specialist agents
├── skills/                    ← 6 reusable skills
├── plugins/                   ← migration-bundle, diagnostic, release, security
├── rules/                     ← coding standards, security policies
├── memory/
│   ├── CODEBASE-MAP.md        ← live progress (committed to git)
│   ├── signals.json           ← technology flags from discovery
│   └── ast/                   ← per-screen AST JSON (WebForms)
└── workflows/
    └── migration-ci.yml       ← real GitHub Actions CI
```
