# Memory: Session Cache — Token Conservation System

## Purpose
This is the **single most important file for saving tokens**. Every agent reads
this FIRST at session start. If a file is listed as DONE here, agents do NOT
re-analyse it — they trust the cached result and move on.

**Rule: Never re-check what the ledger says is clean. Trust the ledger.**

---

## How Token Saving Works

```
WITHOUT this file (wasteful):
  Session 1: Analyse OrderService.cs → 800 tokens
  Session 2: Analyse OrderService.cs again → 800 tokens wasted
  Session 3: Analyse OrderService.cs again → 800 tokens wasted

WITH this file (efficient):
  Session 1: Analyse OrderService.cs → write result here → 800 tokens
  Session 2: Read 3-line ledger entry → 15 tokens ✅
  Session 3: Read 3-line ledger entry → 15 tokens ✅
```

Token savings scale with project size. On a 200-file project,
this file alone saves ~150,000 tokens across the migration.

---

## Ledger Format (one line per file)

```
[STATUS] | [FILE PATH] | [HASH] | [AGENT] | [DATE] | [NOTES]
```

Status values:
- `ANALYSED`  — code-analysis run, result cached below
- `MIGRATED`  — fully migrated and verified
- `TESTED`    — tests passing, coverage recorded
- `SECURED`   — security-audit passed
- `BLOCKED`   — cannot proceed, reason in notes
- `SKIP`      — deliberately excluded (legacy/compat file)
- `DECOMPOSE` — needs decomposition before migration (>500 LOC)

---

## Active Ledger

### Utilities Project
```
MIGRATED | src/Utilities/StringHelper.cs       | a3f2c1 | agent-code-refactor | 2025-01-10 | Pure logic, no deps
MIGRATED | src/Utilities/DateExtensions.cs      | b7e4d2 | agent-code-refactor | 2025-01-10 | Pure logic, no deps
MIGRATED | src/Utilities/ValidationHelper.cs    | c9a1f3 | agent-code-refactor | 2025-01-11 | Added nullable annotations
SECURED  | src/Utilities/CryptoHelper.cs        | d2b5e7 | agent-security-audit| 2025-01-11 | SHA256 confirmed, no MD5
```

### DAC Project
```
ANALYSED | src/DAC/UserRepository.cs           | e8f3a2 | agent-code-refactor | 2025-01-12 | EF6, 3 ObjectContext uses → agent-data-migrator
BLOCKED  | src/DAC/ReportService.cs            | f1c4b9 | agent-dependency-resolver | 2025-01-12 | Crystal Reports — awaiting stakeholder decision
```

### BC, SAC, BPC, WebApp
```
(not started)
```

---

## Cached Analysis Results

### Format: paste brief code-analysis output here so future sessions skip re-analysis

```markdown
FILE: src/DAC/UserRepository.cs
ANALYSED: 2025-01-12
LOC: 287
COMPLEXITY: Medium
FRAMEWORK_DEPS: ObjectContext (line 14), EF6 Include (lines 45, 89, 134)
ASYNC_NEEDED: GetUser, GetAllUsers, SaveUser, DeleteUser
PACKAGES: EntityFramework 6.4.4 → EF Core 8
ASSIGNED_TO: agent-data-migrator (EF6 specialist)
ESTIMATED_HOURS: 3
SECURITY_NOTES: Parameterized queries confirmed — no injection risk
```

---

## What Agents Do With This File

```
SESSION START — Every agent does this FIRST:
  1. Read this file (cheap — ~200 tokens)
  2. For any file you're about to analyse/migrate:
     - If status is MIGRATED/SECURED/TESTED → SKIP, use cached notes
     - If status is ANALYSED → use cached analysis, skip re-analysis
     - If status is BLOCKED → skip, do not attempt
     - If not in ledger → add after completing work

SESSION END — Every agent does this LAST:
  Update this file with every file touched this session
  Write the 1-line ledger entry + brief cached result
```

---

## Token Budget Awareness

When you notice you're running low on context:
```
/terse              → switch to code-only output (saves ~60% tokens per response)
/summary            → get status without deep analysis
"skip analysis"     → trust ledger, go straight to migration
"ledger only"       → show me the ledger, nothing else
```

---

## Bulk Status Updates

After running CI, paste results here instead of re-running per-file:

```
CI RUN: 2025-01-15 | Branch: migration/DAC/bundle
BUILD: PASS
TESTS: 47/47 pass | Coverage: 74%
SECURITY: PASS (0 HIGH, 0 CRITICAL)
FILES VERIFIED THIS RUN:
  src/DAC/UserRepository.cs → TESTED ✅
  src/DAC/ProductRepository.cs → TESTED ✅
  src/DAC/OrderRepository.cs → TESTED ✅
```

Paste this block → agents mark all listed files as TESTED without re-running individually.
