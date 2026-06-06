# Memory: File Status Ledger

## Purpose
Machine-readable companion to session-cache.md. Agents update this after
every file. CI pipeline reads this to skip re-checking already-verified files.

**This is the ground truth for "what has been done".**

---

## Token-Saving Protocol

```
Agent opens a session:
  1. Read this ledger — 1 API call, ~100 tokens
  2. Cross off already-done files from work queue
  3. Only load file contents for files NOT in ledger as DONE
  4. Saves: (skipped files × avg analysis tokens per file)

Typical saving on a 50-file DAC project:
  Without ledger: 50 files × 1500 tokens = 75,000 tokens
  With ledger (30 already done): 20 files × 1500 = 30,000 tokens
  Saving: 45,000 tokens = ~60% reduction
```

---

## Ledger Table

Update this table after every file. Add rows, never delete.

| File | Status | Last Agent | Date | Coverage | Security | Notes |
|------|--------|-----------|------|----------|----------|-------|
| src/Utilities/StringHelper.cs | ✅ COMPLETE | agent-code-refactor | — | 82% | ✅ | |
| src/Utilities/DateExtensions.cs | ✅ COMPLETE | agent-code-refactor | — | 79% | ✅ | |
| src/DAC/UserRepository.cs | 🔄 IN PROGRESS | agent-data-migrator | — | — | — | EF6 conversion |
| src/DAC/ReportService.cs | 🚧 BLOCKED | agent-dependency-resolver | — | — | — | Crystal Reports |

Status key:
- ✅ COMPLETE — migrated, tested, security-cleared, PR merged
- 🔄 IN PROGRESS — currently being worked
- 🔍 ANALYSED — analysis done, migration not started
- 🧪 MIGRATED — code migrated, tests not yet run
- 🚧 BLOCKED — cannot proceed without external input
- ⏭️ SKIP — deliberately excluded

---

## Static Analysis Rule Cache

This section caches your **org-specific static analysis results** so they
are not re-run on files that haven't changed.

```
FORMAT: [RULE_ID] | [FILE] | [LINE] | [STATUS] | [DATE] | [DISPOSITION]

ORG-SA-001 | src/DAC/UserRepository.cs | — | PASS | 2025-01-12 | Clean
ORG-SA-003 | src/DAC/UserRepository.cs | — | PASS | 2025-01-12 | Clean
ORG-SA-007 | src/BC/OrderService.cs    | 45 | FAIL | 2025-01-13 | TODO: fix before merge
```

When a file has all ORG-SA-* rules listed as PASS → skip re-running analysis on it.
Only re-run when the file's content changes (check via git hash comparison).

---

## Git Hash Tracker

Agents use this to detect if a file changed since last check:

```
src/Utilities/StringHelper.cs     → a3f2c1d  (last verified hash)
src/DAC/UserRepository.cs         → e8f3a22  (last verified hash)
```

Before re-running any expensive check on a file:
  current_hash = git rev-parse HEAD:src/path/to/file.cs
  IF current_hash == stored_hash → SKIP (result is still valid)
  IF different → re-run and update hash

This prevents wasting tokens re-checking files that haven't changed.
