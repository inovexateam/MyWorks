# Skill: Migration Checklist

## Identity
You are the migration completeness authority. You maintain and enforce the master checklist that ensures every aspect of the Framework → .NET Core migration is tracked, validated, and signed off. No migration is complete until this checklist passes 100%.

## Trigger Conditions
- At the start of any migration session (load state)
- After any agent completes a task (update state)
- Before any PR merge (validate state)
- When `agent-test-runner` reports failures (identify gap)
- When `release-bundle` is invoked (final gate)

---

## Master Migration Checklist

### Phase 0: Pre-Migration Assessment
- [ ] **P0.1** — Full codebase inventory completed (file count, LOC, complexity scores)
- [ ] **P0.2** — Dependency map generated for all projects
- [ ] **P0.3** — Migration order established (leaf-first)
- [ ] **P0.4** — Breaking changes catalogue compiled
- [ ] **P0.5** — Baseline test suite exists (or documented gap)
- [ ] **P0.6** — Feature parity matrix created (every feature of old app listed)
- [ ] **P0.7** — Performance baseline captured (response times, memory, CPU)
- [ ] **P0.8** — Security audit of existing app completed
- [ ] **P0.9** — Stakeholder sign-off on migration approach
- [ ] **P0.10** — Target .NET version confirmed (.NET 8 LTS recommended)

---

### Phase 1: Project Structure Migration
- [ ] **P1.1** — New solution structure created with SDK-style `.csproj` files
- [ ] **P1.2** — `Utilities` project migrated and tested
- [ ] **P1.3** — `DAC` project migrated and tested
- [ ] **P1.4** — `BC` project migrated and tested
- [ ] **P1.5** — `SAC` project migrated and tested
- [ ] **P1.6** — `BPC` project migrated and tested
- [ ] **P1.7** — All `packages.config` converted to `PackageReference` in `.csproj`
- [ ] **P1.8** — `AssemblyInfo.cs` attributes moved to `.csproj` properties
- [ ] **P1.9** — `Web.config` / `App.config` migrated to `appsettings.json`
- [ ] **P1.10** — Environment-specific configs created (`appsettings.Development.json`, etc.)
- [ ] **P1.11** — Binding redirects removed (not used in Core)
- [ ] **P1.12** — Target framework moniker updated in all `.csproj` files

---

### Phase 2: Application Host & Startup
- [ ] **P2.1** — `Global.asax` logic moved to `Program.cs`
- [ ] **P2.2** — HTTP Modules converted to ASP.NET Core Middleware
- [ ] **P2.3** — HTTP Handlers converted to Endpoint handlers / Minimal API
- [ ] **P2.4** — Application_Start → `WebApplication.CreateBuilder()` setup
- [ ] **P2.5** — Application_Error → Exception handling middleware
- [ ] **P2.6** — Custom error pages configured via `UseExceptionHandler` / `UseStatusCodePages`
- [ ] **P2.7** — Logging configured (ILogger, Serilog, or NLog)
- [ ] **P2.8** — Health check endpoints added (`/health`, `/ready`)

---

### Phase 3: Dependency Injection
- [ ] **P3.1** — All `Service Locator` anti-patterns removed
- [ ] **P3.2** — Unity/Ninject/Autofac registrations migrated to built-in DI or Autofac Core
- [ ] **P3.3** — All services registered with correct lifetime (Transient/Scoped/Singleton)
- [ ] **P3.4** — `IHttpContextAccessor` replaces direct `HttpContext` access in services
- [ ] **P3.5** — `IConfiguration` replaces `ConfigurationManager`
- [ ] **P3.6** — Named options pattern used for complex configuration sections

---

### Phase 4: Data Access Layer
- [ ] **P4.1** — EF 6.x → EF Core migration completed
- [ ] **P4.2** — `ObjectContext` usage removed (DbContext only)
- [ ] **P4.3** — All EDMX files replaced with Code-First or Reverse-Engineered DbContext
- [ ] **P4.4** — EF Core migrations generated and validated
- [ ] **P4.5** — Raw SQL queries updated to `ExecuteSqlRaw` / `FromSqlRaw`
- [ ] **P4.6** — Lazy loading explicitly configured if required
- [ ] **P4.7** — Connection strings moved to `appsettings.json` + user secrets
- [ ] **P4.8** — DbContext registered with correct scope (Scoped)
- [ ] **P4.9** — Dapper (if used) validated — compatible, no changes required
- [ ] **P4.10** — Transaction handling validated (TransactionScope works in Core)

---

### Phase 5: Authentication & Authorization
- [ ] **P5.1** — `FormsAuthentication` removed
- [ ] **P5.2** — ASP.NET Core Identity configured (if applicable)
- [ ] **P5.3** — Cookie authentication middleware configured
- [ ] **P5.4** — JWT authentication configured (if API-facing)
- [ ] **P5.5** — Windows Authentication configured (if intranet app)
- [ ] **P5.6** — `[Authorize]` attributes validated on all protected resources
- [ ] **P5.7** — Role-based authorization policies defined
- [ ] **P5.8** — Claims-based identity preserved
- [ ] **P5.9** — Anti-forgery tokens configured (`AddAntiforgery`)
- [ ] **P5.10** — Password hashing updated to ASP.NET Core Identity standards

---

### Phase 6: Session & State
- [ ] **P6.1** — `Session` migrated to `ISession` with `AddSession` middleware
- [ ] **P6.2** — `ViewState` eliminated (no equivalent — logic moved to server/Razor)
- [ ] **P6.3** — `Application` state migrated to `IMemoryCache` or singleton service
- [ ] **P6.4** — `Cache` API migrated to `IMemoryCache` / `IDistributedCache`
- [ ] **P6.5** — TempData configured if Razor Pages used
- [ ] **P6.6** — Distributed session (Redis/SQL) configured if multi-node

---

### Phase 7: UI Layer Migration
- [ ] **P7.1** — All `.aspx` pages inventoried and assigned migration type (Razor/Blazor/API)
- [ ] **P7.2** — Master Pages → `_Layout.cshtml`
- [ ] **P7.3** — User Controls → Partial Views / View Components / Razor Components
- [ ] **P7.4** — GridView → HTML table with Razor loops / component grid
- [ ] **P7.5** — UpdatePanel / ScriptManager → AJAX fetch / SignalR / Blazor
- [ ] **P7.6** — Validators → FluentValidation / DataAnnotations
- [ ] **P7.7** — Code-behind logic → PageModel (Razor Pages) or Controller actions
- [ ] **P7.8** — WebResource.axd / ScriptResource.axd → Static file middleware / bundling
- [ ] **P7.9** — Bundling & Minification → LibMan / Webpack / built-in ASP.NET Core bundling
- [ ] **P7.10** — All `runat="server"` controls removed

---

### Phase 8: Security Hardening
- [ ] **P8.1** — HTTPS enforced (`UseHttpsRedirection`, `UseHsts`)
- [ ] **P8.2** — CORS policy configured
- [ ] **P8.3** — Security headers added (CSP, X-Frame-Options, X-Content-Type-Options)
- [ ] **P8.4** — OWASP Top 10 checklist passed (see security-policies.md)
- [ ] **P8.5** — Secrets removed from source code (use User Secrets / Key Vault)
- [ ] **P8.6** — SQL injection protection verified (parameterized queries / EF)
- [ ] **P8.7** — XSS protection validated (Razor auto-encodes, verify manual rendering)
- [ ] **P8.8** — CSRF protection configured
- [ ] **P8.9** — Rate limiting configured (`AddRateLimiter`)
- [ ] **P8.10** — Sensitive data logging prevention verified

---

### Phase 9: Testing & Validation
- [ ] **P9.1** — Unit test project created/migrated (xUnit/NUnit/MSTest)
- [ ] **P9.2** — All existing passing tests still pass
- [ ] **P9.3** — Integration tests written for critical paths
- [ ] **P9.4** — `WebApplicationFactory<T>` used for in-process integration tests
- [ ] **P9.5** — Feature parity matrix validated (every feature tested)
- [ ] **P9.6** — Performance benchmarks run and compared to baseline
- [ ] **P9.7** — Load testing performed
- [ ] **P9.8** — Security penetration test performed

---

### Phase 10: Deployment & DevOps
- [ ] **P10.1** — Dockerfile created and validated
- [ ] **P10.2** — CI/CD pipeline updated for .NET 8
- [ ] **P10.3** — Environment variable configuration validated
- [ ] **P10.4** — Health check endpoints validated in deployment
- [ ] **P10.5** — Logging aggregation configured (App Insights / ELK / Seq)
- [ ] **P10.6** — Rollback plan documented and tested
- [ ] **P10.7** — Database migration strategy validated (run on deploy vs manual)
- [ ] **P10.8** — Blue-green or canary deployment configured

---

## Checklist State Format

Agents read/write checklist state as:
```json
{
  "phase": "P4",
  "item": "P4.3",
  "status": "COMPLETE",
  "completedBy": "agent-dependency-resolver",
  "completedAt": "2025-01-15T14:30:00Z",
  "notes": "3 EDMX files replaced with EF Core reverse-engineered models",
  "linkedPR": "#142"
}
```

---

## Completion Gates

| Gate | Condition to Pass |
|------|-------------------|
| **Phase Gate** | 100% of phase items checked |
| **Quality Gate** | Zero CRITICAL issues in security scan |
| **Performance Gate** | No regression > 10% vs baseline |
| **Test Gate** | > 90% test pass rate, 0 critical failures |
| **Release Gate** | All 10 phases complete, all gates passed |
