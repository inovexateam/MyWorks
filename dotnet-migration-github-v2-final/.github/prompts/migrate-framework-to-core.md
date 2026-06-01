# Prompt: Migrate Framework to Core

## Purpose
This prompt gives any agent (or human using Copilot) precise, step-by-step instructions to migrate a single class or file from ASP.NET Framework 4.7.1/4.8 to .NET 8. Use it as your primary instruction set when opening a Framework file.

---

## How to Use This Prompt

Paste this prompt along with the file content you want to migrate:

```
Using the instructions in migrate-framework-to-core.md, migrate the following file.
Preserve all business logic exactly. Do not change method signatures unless 
a Framework type forces it. Document every change with an inline comment.

[PASTE FILE CONTENT HERE]
```

---

## The Migration Prompt

```
You are a senior .NET 8 migration engineer. Migrate the following ASP.NET Framework 
4.7.1/4.8 code to .NET 8, following these exact steps:

═══════════════════════════════════════════════════════════
STEP 1 — ANALYSE BEFORE TOUCHING ANYTHING
═══════════════════════════════════════════════════════════
Read the entire file. Identify:
  a) Every System.Web.* reference
  b) Every ConfigurationManager.* call
  c) Every static HttpContext.Current usage
  d) Every synchronous I/O method (DB, file, network)
  e) Every third-party package reference
  f) The class's primary responsibility in 1 sentence

List your findings as a pre-migration report before writing any code.

═══════════════════════════════════════════════════════════
STEP 2 — PLAN THE MIGRATION
═══════════════════════════════════════════════════════════
For each finding from Step 1, state:
  - What Core equivalent you will use
  - Whether the method signature changes
  - Whether callers need updating

Only proceed to Step 3 after this plan is written.

═══════════════════════════════════════════════════════════
STEP 3 — APPLY MIGRATION RULES (in order)
═══════════════════════════════════════════════════════════

RULE A — Namespace updates
  Remove all: using System.Web.*
  Remove all: using System.Configuration.*
  Add only the Core namespaces actually needed.

RULE B — ConfigurationManager → IConfiguration
  Every: ConfigurationManager.ConnectionStrings["X"].ConnectionString
  Becomes: _configuration.GetConnectionString("X")  [inject IConfiguration]
  
  Every: ConfigurationManager.AppSettings["X"]
  Becomes: _configuration["Section:Key"]
  
  Add constructor parameter: IConfiguration configuration
  Add field: private readonly IConfiguration _configuration;

RULE C — HttpContext.Current → IHttpContextAccessor
  Every: HttpContext.Current.User
  Becomes: _httpContextAccessor.HttpContext?.User
  
  Every: HttpContext.Current.Session["X"]
  Becomes: _httpContextAccessor.HttpContext?.Session.GetString("X")
  
  Add constructor parameter: IHttpContextAccessor httpContextAccessor
  Add field: private readonly IHttpContextAccessor _httpContextAccessor;
  Note in comment: Register AddHttpContextAccessor() in Program.cs

RULE D — Logging replacement
  If log4net: Remove ILog field and LogManager.GetLogger(...)
  Add: private readonly ILogger<[ClassName]> _logger;
  Add constructor parameter: ILogger<[ClassName]> logger
  Replace: log.Error("msg", ex)  →  _logger.LogError(ex, "msg")
  Replace: log.Info("msg")       →  _logger.LogInformation("msg")
  Replace: log.Debug("msg")      →  _logger.LogDebug("msg")
  Replace: log.Warn("msg")       →  _logger.LogWarning("msg")
  Use structured logging: _logger.LogError(ex, "Failed for {Id}", id)
  NEVER use string interpolation in log calls.

RULE E — Async modernization
  For every method that calls a DB, file system, or network:
    Add Async suffix to method name
    Change return type T → Task<T>, void → Task
    Add parameter: CancellationToken cancellationToken = default
    Await all inner calls
    Add .ConfigureAwait(false) on all awaits (library code)
  
  If caller is a controller/page method:
    Also make the caller async (propagate up the chain)

RULE F — Null safety
  File must compile with <Nullable>enable</Nullable>
  Add ? to every reference type that can legitimately be null
  Add ArgumentNullException.ThrowIfNull(param) at start of public methods
  Replace: if (x == null) throw new ArgumentNullException(...)
  With:    ArgumentNullException.ThrowIfNull(x)

RULE G — Modern C# syntax
  Use file-scoped namespace: namespace MyApp.Services;
  Use primary constructor if only constructor (C# 12)
  Use collection expressions where applicable: [] instead of new List<T>()
  Use target-typed new: MyClass obj = new() instead of new MyClass()
  Use pattern matching switch expressions where switch statements exist

RULE H — Exception handling
  Replace: throw new HttpException(404, "msg")
  With:    In controllers: return NotFound() | In services: throw new NotFoundException("msg")
  
  Replace: throw new HttpException(403, "msg")  
  With:    In controllers: return Forbid() | In services: throw new UnauthorizedException("msg")

═══════════════════════════════════════════════════════════
STEP 4 — PRODUCE THE MIGRATED CODE
═══════════════════════════════════════════════════════════
Write the complete migrated file.
For every change made, add an inline comment:
  // MIGRATED: [old code] → [new code] | Reason: [why]

Example:
  // MIGRATED: ConfigurationManager.AppSettings["Timeout"] → _configuration["App:Timeout"]
  // Reason: ConfigurationManager removed in .NET Core; IConfiguration is the replacement
  var timeout = _configuration["App:Timeout"];

═══════════════════════════════════════════════════════════
STEP 5 — PRODUCE THE POST-MIGRATION SUMMARY
═══════════════════════════════════════════════════════════
After the code, write:

## Migration Summary: [FileName]
- Changes made: [count]
- Methods made async: [list]  
- Breaking API changes: [list with callers affected]
- New DI dependencies added: [list — these need registering in Program.cs]
- Checklist items completed: [e.g., P1.2, P3.6]
- Tests required: [list test scenarios]
- Any blockers or open questions: [list]
```

---

## Targeted Variants

### Variant: Class Library Only (No HttpContext)
Use when migrating BC, BPC, Utilities projects that have no web context:
```
Skip Rules C (HttpContext) and H (HTTP exceptions).
Focus on Rules A, B, D, E, F, G only.
```

### Variant: Data Access Layer Only
Use when migrating DAC project:
```
In addition to all rules above, also apply:
RULE I — EF6 → EF Core
  See agent-data-migrator.md for complete EF migration rules
  Key points:
  - Replace ObjectContext with DbContext
  - Replace .Include("string") with .Include(lambda)
  - Add async to all repository methods
  - Replace Database.ExecuteSqlCommand with ExecuteSqlRaw/Interpolated
```

### Variant: Web Page Only (.aspx)
Use when migrating WebForms pages:
```
Skip Rules B-H (not applicable to .aspx markup).
Instead: See agent-ui-adapter.md and prompt/refactor-ui.md
The .aspx.cs code-behind: Apply all rules above to the PageModel.
```
