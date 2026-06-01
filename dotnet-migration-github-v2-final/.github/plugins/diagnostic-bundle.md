# Plugin: Diagnostic Bundle

## Identity
The diagnostic bundle is an on-demand troubleshooting orchestrator. It is invoked whenever an error, test failure, build break, or runtime anomaly cannot be quickly resolved by the responsible agent.

**Invoke with:** `/diagnostic-bundle [symptom] [context]`

**Examples:**
```
/diagnostic-bundle "build-error" "DAC project after EF Core migration"
/diagnostic-bundle "test-failure" "UserRepository.GetByIdAsync returns null"
/diagnostic-bundle "runtime-error" "NullReferenceException in ProductService line 87"
/diagnostic-bundle "performance" "ProductList page taking 4500ms since migration"
```

---

## Diagnostic Orchestration

```
PLUGIN: diagnostic-bundle
INPUT: symptom = [build-error | test-failure | runtime-error | performance | security-anomaly]
INPUT: context = [description of what's happening]
INPUT: evidence = [stack trace, error message, log output — paste directly]

STEP 1: Triage
  Classify symptom into diagnostic category:
    BUILD_ERROR     → Route to Build Diagnostic Agent
    TEST_FAILURE    → Route to agent-test-runner (diagnosis mode)
    RUNTIME_ERROR   → Route to agent-code-refactor (runtime analysis mode)
    PERFORMANCE     → Route to Performance Diagnostic Agent
    SECURITY        → Route to agent-security-audit (incident mode)
    DATA_CORRUPTION → Route to agent-data-migrator (emergency mode)

STEP 2: Context Collection
  GATHER automatically:
    - Last 50 git commits on current branch
    - dotnet build output (full, no truncation)
    - Last 100 log lines from application
    - Current migration checklist state
    - Which agents were active in last 2 hours
    - Any recent dependency changes (git diff *.csproj)

STEP 3: Root Cause Analysis
  INVOKE: Appropriate specialist agent (from Step 1)
  PROVIDE: All context from Step 2 + evidence from input
  REQUEST: Root cause hypothesis + fix recommendation

STEP 4: Fix Execution
  If fix is clear:
    INVOKE: Appropriate agent with explicit fix instruction
    MONITOR: Fix attempt
  If fix is ambiguous:
    Present 2-3 hypotheses with investigation steps
    Ask human to select investigation path

STEP 5: Verification
  After fix applied:
  INVOKE: agent-test-runner (scope: affected component)
  GATE: Issue no longer reproduces
  GATE: No new issues introduced by fix

STEP 6: Knowledge Capture
  Record in memory/known-issues.md:
    - Symptom
    - Root cause
    - Fix applied
    - Prevention recommendation
```

---

## Common Diagnostic Patterns

### Pattern 1: EF Core LINQ Query Failure
```
Symptom: "The LINQ expression could not be translated"
Root Cause: Client-side evaluation removed in EF Core
Fix:
  ❌ context.Products.Where(p => MyHelperMethod(p.Name)).ToList()
  ✅ context.Products.Where(p => p.Name.StartsWith(prefix)).ToList()
  Rule: All filtering must be DB-translatable
  If complex logic needed: Load data first, then filter in memory (if small dataset)
```

### Pattern 2: DI Scope Mismatch
```
Symptom: "Cannot consume scoped service from singleton"
Root Cause: Singleton service depends on Scoped service
Fix:
  Option A: Change singleton to scoped (if appropriate)
  Option B: Inject IServiceScopeFactory, create scope manually
  
  services.AddSingleton<IMyBackgroundService>(provider => {
      var scopeFactory = provider.GetRequiredService<IServiceScopeFactory>();
      return new MyBackgroundService(scopeFactory);
  });
```

### Pattern 3: Null Reference After Migration
```
Symptom: NullReferenceException where Framework code never threw
Root Cause: Nullable reference types enabled — previously hidden null
Fix:
  1. Enable nullable warnings as errors: <Nullable>enable</Nullable>
  2. Trace the null source
  3. Add null guard: ArgumentNullException.ThrowIfNull(param)
  4. Or use null-conditional: value?.Property ?? defaultValue
```

### Pattern 4: Session State Lost
```
Symptom: Session values null after migration
Root Cause: Session middleware not configured, or using wrong session key
Fix:
  // In Program.cs — ORDER MATTERS:
  builder.Services.AddDistributedMemoryCache();
  builder.Services.AddSession(options => {
      options.IdleTimeout = TimeSpan.FromMinutes(20);
      options.Cookie.HttpOnly = true;
      options.Cookie.IsEssential = true;
  });
  // In middleware pipeline — BEFORE UseRouting:
  app.UseSession(); // Must be before app.MapControllers()
```

### Pattern 5: Authentication Redirect Loop
```
Symptom: Login page keeps redirecting to itself
Root Cause: Auth middleware order incorrect, or cookie path mismatch
Fix:
  // Correct middleware order in Program.cs:
  app.UseRouting();
  app.UseAuthentication(); // BEFORE UseAuthorization
  app.UseAuthorization();  // AFTER UseAuthentication
  app.MapControllers();    // LAST
  
  // Check cookie path matches login path:
  options.LoginPath = "/Account/Login"; // Must match actual route
```

### Pattern 6: 404 After Migrating Route
```
Symptom: Previously working URL returns 404 after migration
Root Cause: Route pattern changed (WebForms URL ≠ Razor Page URL)
Fix:
  // Add legacy route redirect in Program.cs:
  app.MapGet("/OldPage.aspx", context => {
      context.Response.Redirect("/new-page", permanent: true);
      return Task.CompletedTask;
  });
  
  // Or use route constraints:
  [Route("products/{id:int}")]
  // Was: Products/Details.aspx?id=5
  // Now: /products/5
```

### Pattern 7: Performance Regression — N+1 Query
```
Symptom: Page that was fast now takes 3000ms
Diagnosis:
  1. Enable EF Core query logging
  2. Look for same query running many times with different IDs
  3. This is N+1: loading collection, then each item's related data separately
Fix:
  // Add .Include() to load related data in one query
  var orders = await _context.Orders
      .Include(o => o.Customer)    // Was: lazy loaded per order
      .Include(o => o.OrderItems)  // Was: lazy loaded per order
      .ToListAsync();
```

---

## Escalation to Human

Escalate to human when:
- Data corruption detected or suspected
- Production is down
- Security incident confirmed
- Root cause requires business context to resolve
- Diagnostic bundle has attempted > 3 fix iterations without resolution

```
ESCALATION MESSAGE FORMAT:
🚨 HUMAN REQUIRED — Diagnostic Bundle Cannot Resolve

Issue: [clear description]
Attempts Made:
  1. [what was tried] → [result]
  2. [what was tried] → [result]
  3. [what was tried] → [result]

Current State: [is system running? is data safe?]
Evidence: [stack trace / logs / screenshots]
Recommended Next Step: [best hypothesis for human to investigate]
Urgency: [P0 Production Down | P1 Major Feature Broken | P2 Minor Issue]
```
