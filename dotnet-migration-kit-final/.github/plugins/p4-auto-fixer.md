# Plugin: P4 — Auto Fixer

## Identity
Runs after all code migration completes. Fixes deprecated APIs, adds nullability,
inserts TODO-MIGRATION markers, cleans analyzer warnings. No logic changes.

## Invoke
```
Read .github/plugins/p4-auto-fixer.md
```
OR automatically triggered at end of migration-bundle.

## Token rule
Read CODEBASE-MAP.md. Only run on files marked 🔧 NEEDS-FIX or newly migrated files.
Skip ✅ DONE files that already passed auto-fix.

## Fix catalogue

### Fix 1 — BinaryFormatter removal
```csharp
// ❌ Removed in .NET 8 (security vulnerability)
var formatter = new BinaryFormatter();
formatter.Serialize(stream, obj);
var result = (MyType)formatter.Deserialize(stream);

// ✅ Replace with System.Text.Json
var json = JsonSerializer.Serialize(obj);
await File.WriteAllTextAsync(path, json);
var result = JsonSerializer.Deserialize<MyType>(json);
// TODO-MIGRATION: Verify serialized data format compatibility with existing stored data
```

### Fix 2 — Nullable enable + annotations
```xml
<!-- Add to every .csproj in src-core/ -->
<Nullable>enable</Nullable>
```
```csharp
// Auto-add ? where compiler warns nullable reference not annotated
public string Name { get; set; }        // → public string? Name { get; set; }
public User GetUser(int id) { ... }     // → public User? GetUser(int id) { ... }
// ArgumentNullException.ThrowIfNull(param) at top of every public method
```

### Fix 3 — Thread.Sleep → Task.Delay
```csharp
// ❌ Blocks thread pool thread
Thread.Sleep(1000);
Thread.Sleep(TimeSpan.FromSeconds(5));

// ✅ Non-blocking
await Task.Delay(1000, cancellationToken);
await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);
```

### Fix 4 — Obsolete HttpContext patterns
```csharp
// ❌
HttpContext.Current.Request.Url
HttpContext.Current.Response.Redirect("/path")

// ✅ (should already be fixed by code-refactor — flag if still present)
// TODO-MIGRATION: HttpContext.Current found — inject IHttpContextAccessor
```

### Fix 5 — SuppressMessage / pragma warning cleanup
```csharp
// Remove: #pragma warning disable CS0618 (obsolete member warnings from Framework)
// Remove: [SuppressMessage("Microsoft.Security", "CA...")] if CA rule no longer exists
// Keep: legitimate suppressions with documented reason
```

### Fix 6 — Task.Factory.StartNew → Task.Run
```csharp
// ❌
Task.Factory.StartNew(() => DoWork());

// ✅
Task.Run(() => DoWork(), cancellationToken);
```

### Fix 7 — String.Format → interpolation
```csharp
// ❌
string msg = String.Format("Hello {0}, you have {1} items", name, count);

// ✅
string msg = $"Hello {name}, you have {count} items";
```

### Fix 8 — Collection initialization modernization
```csharp
// ❌
var list = new List<string>();
var dict = new Dictionary<string, int>();

// ✅ (C# 12 collection expressions)
List<string> list = [];
Dictionary<string, int> dict = [];
```

### Fix 9 — TODO-MIGRATION markers (do NOT auto-fix — mark only)
```
Insert // TODO-MIGRATION: [reason] comment before any:
- Business logic that was changed structurally (not just syntax)
- Any // MIGRATED: comment from agent-code-refactor that changed behaviour
- Any file that had Crystal Reports, COM, or GAC dependencies removed
- Any method that changed from sync to async (callers may need updating)
- ViewState logic that was removed (verify replacement works)
```

## Output: auto-fix-report.json
```json
{
  "fixedAt": "ISO-timestamp",
  "filesFixed": 24,
  "binaryFormatterRemoved": 2,
  "nullableAnnotationsAdded": 156,
  "threadSleepReplaced": 8,
  "todoMarkersInserted": 12,
  "buildWarningsBefore": 47,
  "buildWarningsAfter": 3
}
```

## Copilot prompt
```
Read .github/memory/CODEBASE-MAP.md and .github/plugins/p4-auto-fixer.md.
Run the auto-fixer on all migrated files in src-core/.
Fix BinaryFormatter, Thread.Sleep, nullable annotations, String.Format.
Insert TODO-MIGRATION comments where logic changed structurally.
Run dotnet build after fixes — target must be 0 errors, warnings ≤ 5.
Write results to .github/memory/auto-fix-report.json.
```
