# Prompt: Migrate .cs Files (Standard)

## When to use
Every standard .cs class — business logic, services, repositories, utilities.
Not for: EF6/EDMX (use 03), WebForms (use 06), VB.NET (use 08), Web API 2 (use 09).

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md.
For each ⏳ QUEUE .cs file in [PROJECT NAME]:

STEP 1 — Hash check:
  Run: git log -1 --format="%H" -- <filepath>
  Match MAP.md hash + ✅? → log "SKIP [file]" → next file.

STEP 2 — Migrate:
Apply every rule. No exceptions.

NAMESPACES:
  Remove: System.Web.*, System.Configuration.*
  Add only what's needed from Microsoft.AspNetCore.*, Microsoft.Extensions.*

CONFIGURATION:
  ConfigurationManager.AppSettings["x"]      → _configuration["Section:x"]
  ConfigurationManager.ConnectionStrings["x"] → _configuration.GetConnectionString("x")
  Add constructor param: IConfiguration configuration
  For complex config: create Options class, register Configure<T> in Program.cs

LOGGING:
  log4net ILog field + LogManager.GetLogger → private readonly ILogger<T> _logger
  log.Error("msg", ex) → _logger.LogError(ex, "msg")
  log.Info("msg")      → _logger.LogInformation("msg")
  NEVER: _logger.LogError($"msg {var}") — always structured: _logger.LogError("msg {Var}", var)

HTTP CONTEXT:
  HttpContext.Current.User    → inject IHttpContextAccessor, use _accessor.HttpContext?.User
  HttpContext.Current.Session → _accessor.HttpContext?.Session.GetString("key")
  Register in Program.cs: builder.Services.AddHttpContextAccessor()

ASYNC:
  Every method touching DB, file, network, or external service → make async
  Return type T → Task<T>, void → Task
  Add CancellationToken ct = default parameter
  All awaits get .ConfigureAwait(false) in library projects (not in WebApp)
  NEVER: .Result, .Wait(), .GetAwaiter().GetResult()

DEPENDENCY INJECTION:
  Remove: new ServiceClass() inside other classes
  Remove: ServiceLocator.Current.GetInstance<T>()
  Add: constructor injection with interface
  All constructor params validated: ArgumentNullException.ThrowIfNull(param)

EXCEPTIONS:
  throw new HttpException(404,"msg") → in services: throw new KeyNotFoundException("msg")
  throw new HttpException(403,"msg") → in services: throw new UnauthorizedAccessException("msg")

MODERN C#:
  Namespace → file-scoped: namespace My.App; (no braces)
  string.Format("{0}",x) → $"{x}"
  new List<T>() → []
  Target-typed new: MyClass x = new() not new MyClass()
  Nullable annotations: add ? where reference type can be null

STEP 3 — Update MAP.md:
  ✅ DONE | [PROJECT] | [filepath] | [git hash] | migrate-cs | [cov%] |

STEP 4 — After all files in project:
  Run: dotnet build src-core/[Project].Core/
  0 errors → continue. Errors → show and fix before next file.
```
