# Skill: Dependency Mapping

## Identity
You are a dependency intelligence engine for .NET ecosystems. You build complete, layered dependency graphs across NuGet packages, project references, and runtime bindings — and produce Core-compatible migration paths for every dependency found.

## Trigger Conditions
- Any agent starting work on a `.csproj` or `packages.config` file
- When a build fails due to missing/incompatible assembly references
- Before `agent-dependency-resolver` begins work
- When a new third-party library is encountered that hasn't been catalogued

---

## Dependency Categories

### 1. NuGet Package Analysis

For every package in `packages.config` or `*.csproj`:

```
RESOLVE:
  PackageId
  CurrentVersion
  TargetFramework (net471, net48, etc.)
  .NET Core / .NET 8 Support Status:
    ✅ SUPPORTED    - Package has netstandard2.0+ or net6+ target
    ⚠️ PARTIAL      - Works but with reduced functionality
    🔄 REPLACED     - Different package replaces this
    ❌ UNSUPPORTED  - No Core support, needs custom solution
    🏚️ ABANDONED    - No maintenance, needs OSS alternative
```

### 2. Known Migration Mappings (Maintained Library)

| Framework Package | Core/Modern Equivalent | Notes |
|---|---|---|
| `EntityFramework 6.x` | `Microsoft.EntityFrameworkCore 8.x` | API changes in LINQ, migrations |
| `Unity (IoC)` | Built-in `Microsoft.Extensions.DependencyInjection` | Register in Program.cs |
| `Autofac` | `Autofac.Extensions.DependencyInjection` | Mostly compatible |
| `Ninject` | Built-in DI or Autofac | Ninject has limited Core support |
| `log4net` | `Microsoft.Extensions.Logging` + Serilog/NLog | log4net works via adapter |
| `NLog` | `NLog.Extensions.Logging` | Native Core support |
| `Serilog` | `Serilog.AspNetCore` | Excellent Core support |
| `AutoMapper` | `AutoMapper` (12+) | Core-compatible, minor API changes |
| `FluentValidation` | `FluentValidation.AspNetCore` | Full support |
| `Newtonsoft.Json` | `System.Text.Json` (built-in) or keep Newtonsoft | STJ preferred for perf |
| `RestSharp` | `HttpClient` / `RestSharp 110+` | Built-in HttpClient preferred |
| `ELMAH` | `Sentry` / custom middleware | ELMAH has limited Core support |
| `WebActivatorEx` | Middleware pipeline in Program.cs | Direct replacement |
| `Microsoft.AspNet.Identity` | `Microsoft.AspNetCore.Identity` | Major API redesign |
| `Owin` | ASP.NET Core middleware | Full rewrite required |
| `SignalR (old)` | `Microsoft.AspNetCore.SignalR` | API compatible, hub model same |
| `Web API 2` | ASP.NET Core controllers | Unified MVC/API |
| `MiniProfiler` | `MiniProfiler.AspNetCore.Mvc` | Direct support |
| `StackExchange.Redis` | `StackExchange.Redis` | No change needed |
| `Dapper` | `Dapper` | Fully compatible |
| `Hangfire` | `Hangfire.AspNetCore` | Direct Core support |
| `Quartz.NET` | `Quartz.AspNetCore` | Core-native hosting |
| `iTextSharp` | `iText7` | Major API rewrite |
| `NPOI` | `NPOI` | Compatible via netstandard |
| `EPPlus` | `EPPlus 7+` | License change — verify |
| `Crystal Reports` | ❌ No Core support | Migrate to SSRS/FastReport/Telerik |
| `Telerik UI for ASP.NET AJAX` | `Telerik UI for Blazor/MVC` | License + rewrite required |
| `DevExpress WebForms` | `DevExpress ASP.NET Core` | Paid migration path |

### 3. Project Reference Dependency Graph

Map cross-project references in solution:

```
your-solution.sln
├── WebApp (ASP.NET WebForms)
│   ├── → BPC (Business Process Components)
│   ├── → BC (Business Components)
│   └── → Utilities
├── BPC
│   ├── → BC
│   ├── → DAC (Data Access Components)
│   └── → SAC (Service Access Components)
├── BC
│   ├── → DAC
│   └── → Utilities
├── DAC
│   ├── → Utilities
│   └── [EntityFramework 6.x]
├── SAC
│   ├── → BC
│   └── [RestSharp / HttpClient]
└── Utilities
    └── [No internal dependencies]
```

**Migration Order Rule**: Always migrate leaf nodes first (no internal deps → most dependents)
`Utilities → DAC → BC → SAC → BPC → WebApp`

### 4. Assembly Binding Redirects

Scan `Web.config` / `App.config` for `<assemblyBinding>`:
- Flag all redirects
- Identify which are still needed in Core
- Core does not use binding redirects — flag for removal

### 5. GAC Dependencies

Flag any Global Assembly Cache references:
- COM Interop dependencies → assess if replaceable
- Windows-only assemblies → flag for Linux/container incompatibility
- Strong-named assemblies → verify Core compatibility

---

## Dependency Risk Matrix

```
For each dependency, output:
{
  "package": "EntityFramework",
  "currentVersion": "6.4.4",
  "coreEquivalent": "Microsoft.EntityFrameworkCore",
  "coreVersion": "8.0.x",
  "migrationComplexity": "HIGH",
  "breakingChanges": [
    "Lazy loading requires explicit configuration",
    "ObjectContext removed, DbContext only",
    "Database.ExecuteSqlCommand → ExecuteSqlRaw",
    "Include() uses string or lambda, not magic strings"
  ],
  "estimatedHours": 16,
  "agentAssigned": "agent-dependency-resolver",
  "testRequired": true
}
```

---

## Circular Dependency Detection

```
ALGORITHM:
1. Build directed graph G where edge A→B means "A depends on B"
2. Run DFS with visited + recursion stack
3. Flag any back-edges as circular dependencies
4. Report cycle path: e.g., BC → DAC → BC (CIRCULAR)
5. Recommend: Extract shared interface to a new "Contracts" project
```

---

## Output Format

```markdown
## Dependency Map: [ProjectName]

### NuGet Dependencies ([count] total)
| Package | Version | Core Status | Replacement | Complexity | Hours |
|---------|---------|-------------|-------------|------------|-------|

### Project Reference Graph
[ASCII tree showing dependencies]

### Migration Order (Recommended)
1. [Project] — [Reason]
2. ...

### Circular Dependencies
[None found | List of cycles with resolution recommendations]

### GAC / COM / Windows-only Dependencies
[List with compatibility warnings]

### Binding Redirects to Remove
[List from Web.config]

### Total Estimated Migration Hours: [X]
```

---

## How Agents Use This Skill

```
Load: skills/dependency-mapping.md
TARGET: [solution | project | packages.config]
MODE: [full | nuget-only | project-graph | circular-check]
```
