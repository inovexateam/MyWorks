# Rules: Migration Rules

## Scope
These are the non-negotiable guardrails for the entire Framework → Core migration. All agents must follow these. Violations block PRs.

---

## Rule M1: Migration Order is Sacred

```
ALWAYS migrate in this dependency order:
1. Utilities (no internal deps)
2. DAC — invoke agent-data-migrator first
3. BC (depends on DAC)
4. SAC (depends on BC)
5. BPC (depends on BC, SAC)
6. WebApp (depends on all above)

NEVER:
- Skip a layer
- Migrate a dependent before its dependency
- Partially migrate a layer (all or nothing per layer)
```

## Rule M2: No Big Bang

```
Migrate incrementally, one project at a time.
At every step, the application must be in a DEPLOYABLE state.

Allowed: Feature flags, adapter patterns, side-by-side projects
Not Allowed: "We'll fix it all and deploy at once"
```

## Rule M3: Business Logic is Frozen During Migration

```
During migration:
- No new features
- No bug fixes beyond critical security patches
- All business logic changes go to a freeze queue
- Exceptions require written approval

Reason: Concurrent changes + migration = untraceable regressions
```

## Rule M4: Every File Gets a Branch

```
Branch naming: migration/[project]/[classname]
Example: migration/DAC/UserRepository
         migration/BC/OrderService
         migration/WebApp/ProductListPage

One branch per logical unit of work.
PRs stay small (< 400 LOC diff where possible).
```

## Rule M5: Test Before, Test After

```
Before migrating a class:
- Document what tests exist (even if zero)
- Note the test coverage percentage

After migrating:
- All existing tests must pass
- Coverage must not decrease
- At least one new integration test added
```

## Rule M6: Document Every Breaking Change

```
If a public API changes:
- Document in BREAKING-CHANGES.md
- List all callers that need updating
- Never leave a caller broken silently
```

## Rule M7: No System.Web in Migrated Code

```
Absolute ban. Zero tolerance.
Pre-commit hook enforces this automatically.
Any PR containing System.Web in a migrated project is rejected.
```

## Rule M8: Agent Escalation is Mandatory

```
If an agent encounters something outside its expertise:
STOP — Do not guess or hack a solution
ESCALATE — To the appropriate specialist agent
WAIT — For explicit resolution before proceeding

Guessing causes cascading failures that are expensive to debug.
```

---

# Rules: Performance Constraints

## Scope
These performance guardrails prevent the migration from introducing regressions. Applied by agent-test-runner and the CI pipeline.

---

## Response Time Budgets

| Page/Endpoint Type | P50 Target | P95 Target | P99 Max |
|---|---|---|---|
| Static pages (no DB) | < 20ms | < 50ms | < 100ms |
| Simple data pages (1-2 queries) | < 100ms | < 200ms | < 500ms |
| Complex reports (multi-query) | < 500ms | < 1000ms | < 2000ms |
| File downloads | < 200ms to first byte | — | — |
| API endpoints (simple) | < 50ms | < 100ms | < 200ms |
| Search endpoints | < 200ms | < 500ms | < 1000ms |

## Memory Rules

```
- No unbounded in-memory collections (always paginate)
- DbContext lifetime: Scoped (never Singleton)
- Avoid loading entire tables: always use .Take(n) or pagination
- Large file processing: use streams, not byte[]
- IDisposable objects: always in using statements
- HttpClient: use IHttpClientFactory, never new HttpClient()
```

## Database Rules

```sql
-- Every LINQ query must be inspectable:
-- Enable query logging in Development:
optionsBuilder.LogTo(Console.WriteLine, LogLevel.Information)
             .EnableSensitiveDataLogging(); // Development only

-- No N+1 queries:
-- ❌ N+1
foreach (var order in orders) {
    var items = await _context.OrderItems.Where(i => i.OrderId == order.Id).ToListAsync();
}

-- ✅ Single query with Include
var orders = await _context.Orders
    .Include(o => o.OrderItems)
    .ToListAsync();

-- Pagination required for any list endpoint:
var page = await _context.Products
    .Where(p => p.IsActive)
    .OrderBy(p => p.Name)
    .Skip((pageNumber - 1) * pageSize)
    .Take(pageSize)
    .ToListAsync();

-- Indexes: Every FK must have an index
-- EF Core: builder.HasIndex(p => p.CategoryId);
```

## Caching Rules

```csharp
// Cache readonly/slow-changing data
// Never cache user-specific data in a shared cache without isolation

// ✅ Cache with appropriate expiry
_cache.Set("categories", categories, new MemoryCacheEntryOptions {
    AbsoluteExpirationRelativeToNow = TimeSpan.FromHours(1),
    SlidingExpiration = TimeSpan.FromMinutes(30),
    Priority = CacheItemPriority.Normal,
    Size = 1 // For size-limited caches
});

// ✅ Pattern: Cache-aside
if (!_cache.TryGetValue("categories", out List<Category>? categories)) {
    categories = await _repo.GetAllCategoriesAsync();
    _cache.Set("categories", categories, TimeSpan.FromHours(1));
}
```

---

# Rules: Security Policies

## Scope
Non-negotiable security rules. Applied by agent-security-audit. Violation = PR blocked.

---

## Policy: Secrets

```
❌ NEVER in source code:
  - Passwords
  - Connection strings with credentials
  - API keys
  - JWT secrets
  - Encryption keys
  - Service account credentials

✅ ALWAYS use:
  - Azure Key Vault (production)
  - User Secrets (development): dotnet user-secrets set "Key" "Value"
  - Environment variables (CI/CD)
  - GitHub Actions Secrets

Detection: truffleHog runs on every commit.
Consequence: If found in git history, history must be purged (git filter-repo).
```

## Policy: Authentication

```
Password requirements:
  - Minimum 12 characters
  - Complexity: upper + lower + digit + special
  - No common passwords (use HaveIBeenPwned API check)
  - Bcrypt/PBKDF2 hashing (ASP.NET Core Identity default)
  - Not stored in plain text ANYWHERE — not even logs

Session requirements:
  - HttpOnly cookies
  - Secure cookies (HTTPS only)
  - SameSite=Strict
  - Max age: 8 hours (or less for sensitive apps)
  - Server-side invalidation on logout
  - Regenerate session ID on privilege escalation
```

## Policy: Authorization

```
Default deny: All resources require explicit authorization
No security through obscurity: Hidden URLs are not protected
Every API endpoint: Has [Authorize] or explicit [AllowAnonymous] (documented reason)
Admin endpoints: Require Admin role + additional policy
Data access: Always filter by authenticated user's scope
```

## Policy: Input Validation

```
All user input:
  - Validated with DataAnnotations or FluentValidation
  - Length constrained (no unbounded strings)
  - Type validated before use
  - HTML encoded on output (Razor default)
  
File uploads:
  - Type checked (whitelist: .pdf, .docx, .xlsx, .jpg, .png)
  - Size limited (configurable, default 10MB)
  - Filename sanitized (no path traversal)
  - Stored outside webroot
  - Virus scan (if configured)
```

## Policy: Logging

```
✅ Log:
  - Authentication events (login, logout, failure)
  - Authorization failures
  - Data modification events
  - Errors and exceptions
  - Performance anomalies

❌ Never log:
  - Passwords
  - Full credit card numbers
  - SSN / National ID
  - Full session tokens
  - Health/medical information
  - Any PII beyond minimum necessary
```

## Policy: Dependencies

```
All packages must:
  - Have no CRITICAL or HIGH CVEs (verified: dotnet list package --vulnerable)
  - Be from trusted publishers (NuGet verified publishers preferred)
  - Be actively maintained (last commit < 1 year)
  - Be approved in agent-dependency-resolver's registry

Third-party code review:
  - Any new package: reviewed by agent-security-audit before use
  - No forked/custom packages without security review
```
