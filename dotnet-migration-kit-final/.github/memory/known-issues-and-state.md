# Memory: Known Issues

## Purpose
A living document maintained by the diagnostic-bundle and all agents. Every issue encountered during migration is recorded here so future agents can learn from it and avoid repeating the same debugging cycle.

**Agents: Read this at the start of every session. Update it every time you discover a new issue or resolve a known one.**

---

## Issue Registry

### Issue #001 — EF Core LINQ Client Evaluation
```
STATUS: RESOLVED
DISCOVERED BY: agent-data-migrator
SYMPTOM: InvalidOperationException — "The LINQ expression could not be translated"
ROOT CAUSE: EF Core 3+ removed client-side evaluation. Custom methods in Where() 
            clauses that EF6 evaluated in memory now fail.
AFFECTED FILES: [list as discovered]
FIX: Replace custom method calls with inline expressions EF can translate to SQL.
     If complex logic is unavoidable: .AsEnumerable() to switch to LINQ-to-Objects,
     but only after initial filtering to keep result set small.
PREVENTION: Test all LINQ queries against real DB, not just in-memory test DB.
```

### Issue #002 — Session Middleware Order
```
STATUS: RESOLVED  
DISCOVERED BY: agent-code-refactor
SYMPTOM: ISession always returns null values
ROOT CAUSE: app.UseSession() called AFTER app.MapControllers() in Program.cs
FIX: Move app.UseSession() before app.UseRouting() or at minimum before app.MapControllers()
CORRECT ORDER:
  app.UseRouting();
  app.UseAuthentication();
  app.UseSession();        // ← here
  app.UseAuthorization();
  app.MapControllers();
PREVENTION: Follow middleware order template in rules/coding-standards.md
```

### Issue #003 — Antiforgery Token on AJAX Posts
```
STATUS: RESOLVED
DISCOVERED BY: agent-security-audit
SYMPTOM: AJAX POST requests return 400 Bad Request with "Invalid antiforgery token"
ROOT CAUSE: AJAX requests don't automatically include the antiforgery token
FIX: 
  // In _Layout.cshtml — make token available to JS
  <meta name="csrf-token" content="@Antiforgery.GetAndStoreTokens(HttpContext).RequestToken">
  
  // In JS — include in all AJAX requests
  const token = document.querySelector('meta[name="csrf-token"]').content;
  fetch('/api/endpoint', {
      method: 'POST',
      headers: { 
          'Content-Type': 'application/json',
          'RequestVerificationToken': token
      },
      body: JSON.stringify(data)
  });
PREVENTION: Add to security test suite — verify all POST endpoints require token
```

### Issue #004 — ConfigureAwait in ASP.NET Core
```
STATUS: DOCUMENTED (behavior change from Framework)
DISCOVERED BY: agent-code-refactor
NOTE: In ASP.NET Core, there is no SynchronizationContext, so ConfigureAwait(false)
      has no practical effect in web request handlers (controllers/pages).
      However, it is still recommended in library code (BC, DAC, SAC, BPC) for:
      - Portability (library may be used in non-Core contexts)
      - Clarity of intent
      - Future-proofing
RULE: Add ConfigureAwait(false) in all library projects. Omit in WebApp project.
```

### Issue #005 — EF Core Soft Delete Query Filter
```
STATUS: DOCUMENTED
DISCOVERED BY: agent-data-migrator
SYMPTOM: Queries return deleted records after migration (EF6 had manual where clauses)
ROOT CAUSE: EF6 code had manual .Where(x => !x.IsDeleted) in every query.
            These were sometimes missed during migration.
FIX: Add global query filter to DbContext (applies to ALL queries automatically):
  modelBuilder.Entity<Product>().HasQueryFilter(p => !p.IsDeleted);
WARNING: Global filters are IGNORED by: .Find(), .FindAsync()
         Use .FirstOrDefaultAsync(p => p.Id == id) instead of FindAsync when soft delete matters
PREVENTION: All entities with IsDeleted column should have HasQueryFilter in their config
```

---

## Adding New Issues

When you discover a new issue, add an entry:

```markdown
### Issue #[next number] — [Short descriptive title]
STATUS: [OPEN | IN PROGRESS | RESOLVED | DOCUMENTED]
DISCOVERED BY: [agent name or human]
SYMPTOM: [What goes wrong — error message, wrong behavior]
ROOT CAUSE: [Why it happens]
AFFECTED FILES: [which files, if specific]
FIX: [Exact fix — code if applicable]
PREVENTION: [How future agents can avoid this]
```

---

# Memory: Migration State

## Purpose
Tracks the exact current state of the migration across all projects. Agents read this at session start to understand what's done and what's next.

**Last Updated:** [timestamp — update every session]

---

## Project Status

```
Utilities       [████████████████████] 100% ✅ COMPLETE
DAC             [████████████░░░░░░░░]  62% 🔄 IN PROGRESS
BC              [░░░░░░░░░░░░░░░░░░░░]   0% ⏳ NOT STARTED
SAC             [░░░░░░░░░░░░░░░░░░░░]   0% ⏳ NOT STARTED
BPC             [░░░░░░░░░░░░░░░░░░░░]   0% ⏳ NOT STARTED
WebApp          [░░░░░░░░░░░░░░░░░░░░]   0% ⏳ NOT STARTED

OVERALL         [████░░░░░░░░░░░░░░░░]  18%
```

## Active Blockers

| ID | Project | File | Blocker | Owner | Since |
|----|---------|------|---------|-------|-------|
| B001 | DAC | ReportService.cs | Crystal Reports — no Core equivalent | Stakeholder decision needed | 2025-01-10 |
| B002 | DAC | LegacyOrmContext.cs | OpenAccess ORM — no Core equivalent | agent-dependency-resolver | 2025-01-12 |

## Last Session Summary

```
Date: [timestamp]
Mode: [migration-mode]
Agent: [which agent was active]
Files completed: [list]
Checklist items: [list]
Next up: [file/task]
Open questions: [list]
```

---

# Memory: Agent Log

## Purpose
Running log of all significant agent actions, decisions, and handoffs. Used for debugging, auditing, and understanding what happened when something goes wrong.

---

## Log Format

```
[timestamp] [AGENT] [ACTION] [TARGET] [RESULT]
```

## Sample Entries

```
2025-01-15 09:30 | agent-code-refactor    | STARTED MIGRATION  | DAC/UserRepository.cs     | -
2025-01-15 09:31 | agent-code-refactor    | READ SKILL         | code-analysis             | HIGH complexity, 3 EF6 deps
2025-01-15 09:35 | agent-code-refactor    | ESCALATED          | agent-data-migrator       | EF6 ObjectContext usage found
2025-01-15 09:36 | agent-data-migrator    | RECEIVED ESCALATION| UserRepository.cs         | Converting EF6 → EF Core
2025-01-15 10:15 | agent-data-migrator    | MIGRATION COMPLETE | DAC/UserRepository.cs     | EF Core, async, 0 EF6 refs
2025-01-15 10:16 | agent-test-runner      | TESTS RUN          | DAC.Tests                 | 12/12 pass, coverage 74%
2025-01-15 10:17 | agent-security-audit   | SECURITY REVIEW    | DAC/UserRepository.cs     | PASS — no issues
2025-01-15 10:18 | agent-code-refactor    | MAP UPDATED        | DAC/UserRepository.cs   | ✅ DONE + hash
2025-01-15 10:18 | agent-code-refactor    | PR CREATED         | migration/DAC/UserRepository | PR #147
```
