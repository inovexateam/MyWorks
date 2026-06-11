# Skill: Security Review (Token-Efficient + Artifactory-Only)

## Token Protocol — Read First
```
Before running ANY check:
1. Read memory/CODEBASE-MAP.md (already loaded — ~0 extra tokens)
2. Get the file's stored hash: grep the map for the file path
3. Get current hash: git rev-parse HEAD:<filepath>
4. IF stored hash == current hash AND status contains SECURED → OUTPUT "cache HIT" → STOP
5. ONLY run checks if file is new or hash changed
6. After passing: update map row with SECURED + new hash

Cache hit cost:  ~20 tokens
Full review cost: ~2,000 tokens
A 90% hit rate on 200 files = saves ~178,000 tokens per migration run.
```

---

## Tools — Artifactory-Only

```bash
# 1. CVE scan — .NET SDK built-in, zero external fetch
dotnet list package --vulnerable --include-transitive

# 2. SAST — Roslyn analyzers (SecurityCodeScan + org package from Artifactory NuGet)
#    Runs automatically as part of: dotnet build
#    Key rules: SCS0002(SQLi) SCS0006(weak hash) SCS0015(hardcoded pwd) SCS0029(XSS)

# 3. Secrets — grep-based fallback (no pip, no npm)
grep -rn \
  -E '(password\s*=\s*[^$<{"'"'"'][^;\n]{3,}|api[_-]?key\s*[:=]\s*[a-zA-Z0-9]{16,})' \
  --include="*.cs" --include="*.json" --include="*.config" \
  | grep -iv '(//|#|todo|example|placeholder|<\w+>)'
# If org has an Artifactory-hosted scanner, call that instead

# 4. Org-specific rules — sourced as Roslyn analyzer package from Artifactory NuGet feed
#    Add to .csproj: <PackageReference Include="YourOrg.Analyzers" Version="x.x" />
#    Then: dotnet build — violations appear as errors with ORG-prefixed rule IDs
#    Cache result per file by git hash in CODEBASE-MAP.md SA-RESULT section
```

---

## OWASP Checks (code-review — zero tools needed)

### A01 Broken Access Control
- [ ] Every controller/page has `[Authorize]` or documented `[AllowAnonymous]`
- [ ] No IDOR — user can only access own data
- [ ] Admin roles explicitly required on admin endpoints

### A02 Cryptographic Failures
```csharp
// ❌ MD5/SHA1 passwords
FormsAuthentication.HashPasswordForStoringInConfigFile(pwd, "MD5");
// ✅ ASP.NET Core Identity (bcrypt/PBKDF2 by default)
await _userManager.CreateAsync(user, password);
```
- [ ] No MD5/SHA1 for security use
- [ ] Secrets in env vars / Key Vault — never in appsettings.json

### A03 Injection
```csharp
// ❌ String concat SQL
"SELECT * FROM Users WHERE Name='" + username + "'";
// ✅ EF Core / parameterized
_context.Users.Where(u => u.Name == username).ToListAsync();
```
- [ ] Zero string concat in SQL — EF Core or `@param` only

### A05 Security Misconfiguration
```csharp
// ✅ Required in Program.cs
app.UseHttpsRedirection(); app.UseHsts();
// Security headers middleware — see agent-security-audit.md for template
```
- [ ] All 5 security headers present
- [ ] `<customErrors mode="Off">` removed

### A07 Authentication
```csharp
// ✅ Cookie config
options.Cookie.HttpOnly = true;
options.Cookie.SecurePolicy = CookieSecurePolicy.Always;
options.Cookie.SameSite = SameSiteMode.Strict;
```
- [ ] HttpOnly + Secure + SameSite=Strict on all auth cookies
- [ ] Account lockout after ≤10 failures

### Migration-Specific Gaps
| Gap | Check | Fix |
|-----|-------|-----|
| `MachineKey` in web.config | grep machineKey | Replace with Data Protection API |
| `ValidateRequest="false"` | grep in .aspx directives | Remove + add explicit validation |
| `@Html.Raw(userInput)` | grep .cshtml files | Only use for sanitized CMS content |
| Antiforgery missing | grep for `[ValidateAntiForgeryToken]` | Add to all POST actions |

---

## Output Format

```markdown
## Security Review: [FileName] [hash: abc123]

Status: ✅ PASS → update map: SECURED | [file] | [hash]
   OR
Status: ❌ FAIL
  CRITICAL: [description] → BLOCK PR
  HIGH: [description] → fix before merge

OWASP: A01✅ A02✅ A03✅ A05✅ A07✅
CVE: 0 HIGH/CRITICAL
Org rules: PASS (via build step)
```

After a PASS, write one line to `memory/CODEBASE-MAP.md`:
```
✅ DONE | [project] | [filepath] | [hash] | security-audit | [cov%] | SECURED [date]
```

---

## Security Design Review (OWASP Categories)

Run after all files migrated. Check every category.

### Authentication
- [ ] AddAuthentication configured in Program.cs
- [ ] Cookie: HttpOnly=true, Secure=Always, SameSite=Strict
- [ ] Account lockout: MaxFailedAccessAttempts ≤ 10
- [ ] Session tokens regenerated after login
- [ ] Logout: SignOutAsync on both Cookie and OIDC schemes
- [ ] No FormsAuthentication remaining in src-core/

### Authorization
- [ ] Every endpoint has [Authorize] or documented [AllowAnonymous]
- [ ] Admin endpoints require explicit Admin role/policy
- [ ] No IDOR: data queries filtered by authenticated user ID
- [ ] `.Where(x => x.UserId == currentUserId)` not `.Find(rawParam)`

### Data Protection
- [ ] No passwords/keys in appsettings.json values → Key Vault
- [ ] No secrets in source code: `grep -rni "password\s*=" src-core/ --include="*.cs"`
- [ ] MachineKey removed → Data Protection API configured
- [ ] HTTPS enforced: UseHttpsRedirection + UseHsts
- [ ] Sensitive fields not logged

### Input Validation
- [ ] All inputs have DataAnnotations or FluentValidation
- [ ] MaxLength on all string inputs
- [ ] No raw SQL string concatenation
- [ ] No @Html.Raw(userInput) — only for CMS-sanitized content
- [ ] File uploads: whitelist extension, size limit, stored outside webroot

### Session Management
- [ ] Session timeout ≤ 8 hours
- [ ] No sensitive data in session — IDs only
- [ ] No session ID in URL

### Logging & Monitoring
- [ ] Auth events logged (success + failure)
- [ ] No PII in logs (no SSN, passwords, card numbers)
- [ ] Structured logging — no string interpolation in log calls
- [ ] Rate limiting on auth endpoints (AddRateLimiter)

### API Security
- [ ] Response DTOs used — not raw domain entities
- [ ] No mass assignment — separate Input/Output DTOs
- [ ] CORS policy is restrictive (not AllowAnyOrigin)

### Secrets Management
- [ ] No hardcoded API keys: `grep -rni "apikey\|api_key" src-core/ --include="*.cs"`
- [ ] packages.lock.json committed (supply chain protection)
- [ ] ARTIFACTORY_USER + ARTIFACTORY_TOKEN as GitHub Secrets only

### Attack Vector Protection
- CSRF: Razor tag helpers auto-inject antiforgery. [ValidateAntiForgeryToken] on non-API POST actions.
- SSRF: All outbound HTTP uses base addresses from config — no user-supplied URLs fetched directly.
- XSS: Razor @Model.Value auto-encodes. Content-Security-Policy header set.
- SQLi: Zero raw SQL concat. All EF Core LINQ or Dapper with `new { Id = id }` params.
- XXE: XmlReaderSettings.DtdProcessing = Prohibit on all XML parsing.

### Security Headers (Program.cs)
```csharp
app.Use(async (ctx, next) => {
    ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
    ctx.Response.Headers["X-Frame-Options"] = "DENY";
    ctx.Response.Headers["X-XSS-Protection"] = "1; mode=block";
    ctx.Response.Headers["Referrer-Policy"] = "strict-origin-when-cross-origin";
    ctx.Response.Headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self';";
    await next();
});
```
