# Output Style: Terse

## Activation
```
/terse
```
Use when you want code only — no explanations, no prose, just the migrated output.

---

## Behavior When Active

- Produce migrated code immediately — no pre-amble
- No step-by-step narration
- Inline comments only (// MIGRATED: ...) — no surrounding text
- Migration summary: condensed to 5 bullet points maximum
- Blockers: one line each

**Example output:**
```
✅ OrderService.cs — 4 System.Web refs removed, 6 methods made async
⚠️  Requires IConfiguration registered in Program.cs
⚠️  Requires ILogger<OrderService> registered in Program.cs
🧪 Tests: run dotnet test BC.Tests --filter OrderServiceTests
```

---

# Output Style: Verbose

## Activation
```
/verbose
```
Use for onboarding, documentation, or when a developer needs to understand every decision.

---

## Behavior When Active

- Explain every decision before implementing it
- Show before/after code side by side for every change
- Include reasoning for pattern choices
- Link to relevant rules and guidelines
- Produce full migration documentation

**Use when:** Teaching team members, documenting complex migrations, stakeholder reviews.

---

# Output Style: Review

## Activation
```
/review
```
Use when you want the agent to read code and give a thorough review without making changes.

---

## Behavior When Active

- Produce a structured code review — no code changes
- Format: numbered findings with severity
- Include: what's good, what needs fixing, what's optional
- Migration readiness score: [1-10]

**Example output:**
```markdown
## Code Review: ProductService.cs

### ✅ Good
- Clean separation of concerns
- No business logic in DAL
- All methods have XML docs

### 🔴 Must Fix Before Migration
1. [HIGH] Line 45: System.Web.HttpContext.Current used — needs IHttpContextAccessor
2. [HIGH] Line 89: Synchronous DB call in async context — deadlock risk
3. [CRITICAL] Line 123: SQL string concatenation — SQL injection vulnerability

### 🟡 Should Fix
4. [MEDIUM] Class is 620 LOC — should be decomposed before migrating
5. [MEDIUM] log4net used — replace with ILogger<T>

### 🟢 Optional Improvements  
6. [LOW] Switch to record types for DTO classes
7. [LOW] Use ConfigureAwait(false) in library methods

### Migration Readiness: 4/10
### Recommended: Invoke agent-complexity-decomposer first, then agent-code-refactor
```

---

# Output Style: Summary

## Activation
```
/summary
```
Use for status updates, standup reports, or progress checks.

---

## Behavior When Active

Produces a brief, bullet-pointed status summary — no code, no deep analysis.

**Example output:**
```markdown
## Migration Status — [date]

**Overall:** 23% complete

**Done Since Last Summary:**
- ✅ Utilities: fully migrated
- ✅ DAC: UserRepository, ProductRepository, OrderRepository

**In Progress:**
- 🔄 DAC: ReportService (blocked — Crystal Reports decision pending)

**Blockers:**
- B001: Crystal Reports replacement — needs stakeholder decision by [date]
- B002: OpenAccess ORM — agent-dependency-resolver investigating

**Next Up:**
- DAC: CategoryRepository, InventoryRepository

**ETA This Sprint:** DAC project complete (minus blocked files)
**Overall ETA:** 8 weeks at current pace
```
