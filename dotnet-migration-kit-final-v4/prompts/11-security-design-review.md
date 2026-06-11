# Prompt: Security Design Review

## When to use
Before final release. Validates migrated architecture against OWASP SAMM
and secure design principles — not just code scanning.

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md and .github/memory/signals.json.
Read src-core/ Program.cs and all controller/page files.

Perform a security design review across these categories.
Report each finding as: CATEGORY | SEVERITY | LOCATION | ISSUE | FIX

── AUTHENTICATION ────────────────────────────────────────────────────────
Check Program.cs for:
  [ ] Authentication middleware configured (AddAuthentication)
  [ ] Cookie: HttpOnly=true, Secure=Always, SameSite=Strict
  [ ] Account lockout configured (MaxFailedAccessAttempts ≤ 10)
  [ ] Password policy: MinLength ≥ 12 (if using Identity)
  [ ] Session tokens regenerated after login
  [ ] Logout invalidates server-side session (SignOutAsync both schemes)
  [ ] MFA available for admin accounts
  [ ] No FormsAuthentication remaining anywhere in src-core/

── AUTHORIZATION ─────────────────────────────────────────────────────────
Check every controller/page:
  [ ] Every endpoint has [Authorize] or explicit documented [AllowAnonymous]
  [ ] Admin endpoints require explicit Admin role or policy
  [ ] No IDOR: data queries filtered by authenticated user ID, not raw param
      Example check: .Where(x => x.UserId == currentUserId) not .Find(id)
  [ ] Role checks present where privilege separation required

── DATA PROTECTION ───────────────────────────────────────────────────────
  [ ] No passwords in plain text anywhere (grep -r "password" --include="*.json" src-core/)
  [ ] No secrets in appsettings.json values (only key names, values in Key Vault)
  [ ] Connection strings use env vars / Key Vault — not inline passwords
  [ ] MachineKey removed, Data Protection API configured
  [ ] Sensitive fields not logged (grep for LogInformation.*password|ssn|dob)
  [ ] HTTPS enforced: UseHttpsRedirection + UseHsts in Program.cs

── INPUT VALIDATION ──────────────────────────────────────────────────────
  [ ] All model inputs have DataAnnotations or FluentValidation rules
  [ ] MaxLength on every string input (no unbounded strings)
  [ ] No raw string SQL concatenation (grep "SELECT.*\+" src-core/ --include="*.cs")
  [ ] File uploads: whitelist of allowed extensions, size limit, stored outside webroot
  [ ] No @Html.Raw(userInput) — only @Html.Raw for CMS-sanitized content
  [ ] XML input: XmlReaderSettings.DtdProcessing = Prohibit (prevent XXE)
  [ ] No Process.Start with user-controlled input

── SESSION MANAGEMENT ────────────────────────────────────────────────────
  [ ] Session timeout configured (≤ 8 hours for sensitive apps)
  [ ] Distributed session (Redis) if multi-node deployment
  [ ] No sensitive data in session (only IDs, not full objects with PII)
  [ ] No session ID in URL query string

── LOGGING & MONITORING ──────────────────────────────────────────────────
  [ ] Authentication events logged (success + failure)
  [ ] Authorization failures logged
  [ ] No PII in logs (no SSN, DOB, full card numbers, passwords)
  [ ] Structured logging used (not string interpolation in log calls)
  [ ] Centralized log shipping configured (App Insights / ELK / Seq)
  [ ] Rate limiting on login endpoint (AddRateLimiter in Program.cs)

── API SECURITY ──────────────────────────────────────────────────────────
  [ ] APIs return only required fields — no full entity serialization
      Check: DTOs used in responses, not domain entities directly
  [ ] No mass assignment: [BindNever] or separate Input DTOs from domain models
  [ ] CORS policy is restrictive (not AllowAnyOrigin)
  [ ] API versioning in place if breaking changes possible

── SECRETS MANAGEMENT ────────────────────────────────────────────────────
  [ ] No hardcoded API keys or credentials in src-core/
      Run: grep -rn "apikey\|api_key\|password\|secret\|connectionstring" \
             src-core/ --include="*.cs" -i | grep -v "(//|IOptions|GetValue|config\[)"
  [ ] User Secrets for development (dotnet user-secrets)
  [ ] Azure Key Vault / env vars for production
  [ ] packages.lock.json committed (prevents supply chain drift)

── CSRF / SSRF / XSS / SQLI ─────────────────────────────────────────────
  CSRF:
    [ ] Razor forms use tag helpers (auto antiforgery)
    [ ] [ValidateAntiForgeryToken] on all non-API POST actions
    [ ] AJAX POSTs include RequestVerificationToken header

  SSRF:
    [ ] Outbound HTTP calls use allowlisted base addresses only
    [ ] No user-supplied URLs fetched directly

  XSS:
    [ ] Razor @Model.Value auto-encodes (default, verify not disabled)
    [ ] Content-Security-Policy header set
    [ ] No eval() or innerHTML with user data in JavaScript

  SQLi:
    [ ] Zero raw string SQL: grep "ExecuteSqlRaw\|FromSqlRaw" src-core/
        Each must use @param not string format
    [ ] EF Core LINQ used for all ORM queries
    [ ] Dapper uses parameterized: new { Id = id } not string concat

── ARCHITECTURE ──────────────────────────────────────────────────────────
  [ ] Least privilege: DB user has only SELECT/INSERT/UPDATE (not sa/dbo)
  [ ] Secrets not in Docker images (use secrets mounts or env vars)
  [ ] Health endpoints (/health, /ready) do not expose internal config
  [ ] Error responses: generic message in production (no stack traces)
      app.UseExceptionHandler — not app.UseDeveloperExceptionPage in prod
  [ ] Components independently deployable (no circular project references)

── OUTPUT ────────────────────────────────────────────────────────────────
Write findings to .github/memory/security-design-review.md:

## Security Design Review

| Category | Severity | Location | Issue | Fix |
|---|---|---|---|---|
| Authentication | HIGH | Program.cs | No account lockout | Add MaxFailedAccessAttempts=5 |

SEVERITY: CRITICAL (block deploy) | HIGH (fix before merge) | MEDIUM (this sprint) | LOW (backlog)

Count: CRITICAL: X | HIGH: X | MEDIUM: X | LOW: X
Overall: PASS (0 CRITICAL + 0 HIGH) or BLOCKED
```
