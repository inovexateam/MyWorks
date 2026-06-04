# CodeGraph — .NET Codebase Memory for GitHub Copilot

Saves 80–95% of Copilot token usage by giving it a structural map of your
codebase so it loads only the 5–12 relevant files per query instead of everything.

---

## Setup (10 minutes per repo)

### 1. Copy files into your repo root
```
your-repo/
├── gen_graph.py                          ← graph generator
├── codebase-graph.json                   ← generated output (commit this)
├── .github/
│   ├── workflows/
│   │   └── update-graph.yml              ← auto-regenerate on push
│   └── copilot-instructions.md           ← tells Copilot to use the graph
```

### 2. Generate the graph locally first
```bash
python gen_graph.py
```
Requires Python 3.9+. No pip installs needed.

### 3. Commit everything
```bash
git add gen_graph.py codebase-graph.json .github/
git commit -m "feat: add codebase memory graph for Copilot"
git push
```

From this point, every push to main auto-regenerates the graph via CI.

---

## CLI options
```bash
python gen_graph.py                          # scan current directory
python gen_graph.py --root ./src             # scan specific folder
python gen_graph.py --output graph.json      # custom output path
python gen_graph.py --exclude "**/Tests/**"  # exclude patterns (repeatable)
python gen_graph.py --tree                   # print node tree after generating
python gen_graph.py --summary                # stats only, don't write file
python gen_graph.py --watch                  # re-run on every .cs file change
python gen_graph.py --minify                 # compact JSON output
```

---

## What gets extracted

| Node kind | Detected by |
|---|---|
| `controller` | `[ApiController]` attribute or `: ControllerBase` |
| `service` | class name ends with `Service` |
| `repository` | class name ends with `Repository` or `Repo` |
| `middleware` | class name ends with `Middleware` |
| `dbcontext` | extends `DbContext` |
| `model` | class name ends with `Dto`, `Request`, `Response`, `Model` |
| `interface` | `interface` keyword |
| `action` | `[HttpGet/Post/Put/Patch/Delete]` attribute on controller method |

| Edge kind | Detected by |
|---|---|
| `injects` | Constructor parameter of type `IXxx` |
| `implements` | `: IXxx` in class declaration |
| `inherits` | `: BaseClass` in class declaration |
| `has_action` | HTTP verb attribute on method inside controller |
| `has_entity` | `DbSet<T>` property in DbContext |
| `registers` | `.AddScoped<IFoo, Foo>()` in Program.cs / Startup.cs |

---

## Excluded by default
- `**/obj/**`, `**/bin/**`, `**/publish/**`
- `**/Migrations/**`
- `**/*.Designer.cs`, `**/*.g.cs`, `**/*.g.i.cs`
- `**/.git/**`, `**/.vs/**`

---

## Requirements
- Python 3.9+
- No third-party packages

---

## Tested on
- ASP.NET Core Web API
- .NET 6 / 7 / 8 / 9
- Clean Architecture projects
- CQRS / MediatR projects
- EF Core projects