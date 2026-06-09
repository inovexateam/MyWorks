# Prompt: VB.NET Migration + Console → Worker

## Purpose
Targeted prompts for the two Phase 2 agents added from the enterprise recipe.
Both are conditional — only activate when migration-state.json confirms presence.

---

## VB.NET → C# Prompt

```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-vbnet-migrator.md.

Check .github/memory/migration-state.json — if hasVBNet is false, stop and
say "No VB.NET files detected in migration-state.json".

For each ⏳ QUEUE file with .vb extension:
  1. Check git hash vs stored hash — skip if ✅ DONE matches
  2. Translate VB.NET syntax to C# .NET 8 exactly per agent rules
  3. Output to matching src-core/ project as .cs file
  4. Preserve ALL logic — translation only, zero semantic changes
  5. Update CODEBASE-MAP.md to ✅ DONE with new hash

Stop when all .vb files are processed. Show count of files converted.
```

### Key translation reminder
```
Dim x As Integer   → int x
If ... Then/End If → if { }
AndAlso / OrElse   → && / ||
String.Format      → $"" interpolation
Microsoft.VisualBasic.* → remove, use C# equivalents
```

---

## Console → Worker Service Prompt

```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-console-worker-migrator.md.

Check .github/memory/migration-state.json — if hasConsoleApps is false, stop.

For each ⏳ QUEUE console application project:
  1. Check git hash — skip if already done
  2. Replace static void Main with Host.CreateDefaultBuilder
  3. Convert service/worker class to BackgroundService subclass
  4. Replace Thread.Sleep with await Task.Delay(n, stoppingToken)
  5. Add ILogger<T>, IConfiguration via constructor injection
  6. Replace ConfigurationManager with IOptions<T> pattern
  7. If cron/scheduled pattern detected → Hangfire RecurringJob
  8. Update CODEBASE-MAP.md after each project

Run dotnet build on each converted project after conversion.
Show build result. Stop and report on build failure.
```

---

## Web API 2 Prompt

```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-webapi2-migrator.md.

For each ⏳ QUEUE file containing ApiController or System.Web.Http:
  1. Check hash — skip if ✅ DONE
  2. Replace ApiController with ControllerBase
  3. Replace IHttpActionResult with ActionResult<T>
  4. Replace RoutePrefix with [Route("api/[controller]")]
  5. Replace WebApiConfig.Register → Program.cs AddControllers()
  6. Convert DelegatingHandlers to middleware
  7. Add [ApiController] attribute
  8. Make all actions async with CancellationToken
  9. Update CODEBASE-MAP.md after each file
```
