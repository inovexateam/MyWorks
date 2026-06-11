# Prompt: Security + Auto-Fix

## When to use
After all projects migrated. Run once on all of src-core/.

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md.

── AUTO-FIX (all src-core/ files) ───────────────────────────────────────

BinaryFormatter (removed in .NET 8):
  Find: new BinaryFormatter()
  Replace: use JsonSerializer.Serialize / Deserialize
  Insert: // TODO-MIGRATION: verify serialized data format compatibility

Thread.Sleep → async:
  Find: Thread.Sleep(\d+) / Thread.Sleep(TimeSpan...)
  Replace: await Task.Delay(n, stoppingToken) / await Task.Delay(ts, ct)

Nullable annotations:
  Run: dotnet build 2>&1 | grep "CS8600\|CS8603\|CS8604"
  For each warning: add ? to the flagged type
  Add ArgumentNullException.ThrowIfNull(param) at top of affected public methods

String interpolation:
  Find: string.Format("...{0}...", x)
  Replace: $"...{x}..."

Task.Factory.StartNew:
  Replace: Task.Run(() => ..., cancellationToken)

Collection expressions:
  new List<T>() → []  (where type is clear from context)

── SECURITY CHECKS ───────────────────────────────────────────────────────

CVE scan (run in terminal):
  dotnet list package --vulnerable --include-transitive
  CVSS ≥ 7.0 → update package before proceeding

Secret detection (run in terminal):
  git diff HEAD -- "*.cs" "*.json" "*.config" | grep "^+" | grep -iv "^+++" \
    | grep -iE "(password\s*=\s*[^$<{\"'][^;]{3,}|api[_-]?key\s*[:=]\s*[a-zA-Z0-9]{16,})" \
    | grep -iv "(//|todo|example|placeholder)"
  Any output → remove secret, move to Key Vault / env var

Framework dep gate:
  grep -r "using System.Web" src-core/ --include="*.cs"
  Must return empty.

Security headers (add to Program.cs if not present):
  app.Use(async (ctx, next) => {
    ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
    ctx.Response.Headers["X-Frame-Options"] = "DENY";
    ctx.Response.Headers["X-XSS-Protection"] = "1; mode=block";
    ctx.Response.Headers["Referrer-Policy"] = "strict-origin-when-cross-origin";
    await next();
  });

HTTPS + HSTS (add to Program.cs):
  app.UseHttpsRedirection();
  app.UseHsts();

Auth check:
  Every controller/page that is NOT explicitly [AllowAnonymous] must have [Authorize].

Anti-forgery (all POST forms):
  Razor tag helpers add this automatically.
  API controllers with [ApiController] are exempt (use JWT).

MachineKey removal:
  grep machineKey src-framework/Web.config
  Add Data Protection API in Program.cs:
    builder.Services.AddDataProtection()
      .PersistKeysToFileSystem(new DirectoryInfo("/keys"))
      .SetApplicationName("YourApp");

── ROSLYN SAST (from Artifactory NuGet — added to .csproj) ──────────────

Ensure these are in each src-core .csproj:
  <PackageReference Include="SecurityCodeScan.VS2019" Version="5.6.7">
    <PrivateAssets>all</PrivateAssets><IncludeAssets>analyzers</IncludeAssets>
  </PackageReference>
  <PackageReference Include="YourOrg.Analyzers" Version="x.x">
    <PrivateAssets>all</PrivateAssets><IncludeAssets>analyzers</IncludeAssets>
  </PackageReference>

Run: dotnet build src-core/ 2>&1 | grep "SCS\|ORG-"
Fix all SCS (SQL injection, XSS, hardcoded password) violations.

── TESTS ────────────────────────────────────────────────────────────────

Run:
  dotnet test src-core/ --filter "Category!=Integration" \
    --collect:"XPlat Code Coverage" --logger "console;verbosity=minimal"

For any failure:
  Show test name + error + stack trace.
  Classify: REGRESSION (was passing before) or NEW (new test failing).
  Fix regression before marking project complete.

── FINAL REPORT ─────────────────────────────────────────────────────────

Write .github/memory/migration-summary.md:
  ## Migration Summary
  - Files done: [count ✅ in MAP.md]
  - Files blocked: [count 🚧 — list with reason]
  - TODO-MIGRATION markers: [count — run grep to find]
  - Build: PASS / FAIL
  - Tests: X passing / Y failing
  - CVE: [count HIGH/CRITICAL]
  - System.Web refs in src-core/: [count — must be 0]
```
