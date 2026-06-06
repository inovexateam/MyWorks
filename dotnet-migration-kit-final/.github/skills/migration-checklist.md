# Skill: Migration Checklist

## Purpose
Tracks per-file and per-project migration completion. Read by Copilot to
determine what's left. Updated by agents after each file completes.
Lives entirely in CODEBASE-MAP.md — this file is the reading guide.

## Token rule
Read CODEBASE-MAP.md (single file, ~200 tokens) instead of this checklist
for session state. This file is reference only — not loaded every session.

---

## Per-file completion gates

Before marking any file ✅ DONE in CODEBASE-MAP.md, verify:

### Code quality
- [ ] Zero `System.Web.*` references remain
- [ ] Zero `ConfigurationManager` references remain
- [ ] Zero `static HttpContext.Current` references
- [ ] All I/O methods are async with CancellationToken
- [ ] Nullable reference types annotated
- [ ] File-scoped namespace used
- [ ] `dotnet build` — 0 errors on this file's project

### Security (run agent-security-audit on each file)
- [ ] No hardcoded passwords, keys, or connection strings
- [ ] CVE scan: `dotnet list package --vulnerable` — 0 HIGH/CRITICAL
- [ ] `[Authorize]` on all protected endpoints
- [ ] Anti-forgery on all POST forms

### Map update
- [ ] CODEBASE-MAP.md updated: ✅ DONE | hash | agent | coverage

---

## Per-project completion gates (run before moving to next project)

```bash
dotnet build src-core/[Project]/ --configuration Release
# Must be: Build succeeded. 0 Error(s)
```

```bash
dotnet test src-core/ --filter "Category!=Integration"
# Must be: X passed, 0 failed
```

```bash
grep -r "using System.Web" src-core/[Project]/ --include="*.cs"
# Must be: no output
```

---

## Dependency gate (from CODEBASE-MAP.md ORDER line)

Never start a project until all its dependencies are ✅ DONE:
```
# Check: is DAC fully done before starting BC?
grep "⏳ QUEUE\|🔄 WIP" .github/memory/CODEBASE-MAP.md | grep "DAC"
# If output is empty → DAC is clear, BC can start
```

---

## Signal completion gates

After all files done, verify each active signal is resolved:

| Signal | Resolved when |
|--------|--------------|
| hasEF6 | Zero EF6 ObjectContext / DbModelBuilder in src-core/ |
| hasADONet | Zero SqlCommand / SqlDataReader in src-core/ |
| hasVBNet | Zero .vb files remain in src-framework/ queue |
| hasConsoleApps | Zero static void Main in src-core/ |
| hasWebAPI2 | Zero ApiController / System.Web.Http in src-core/ |
| hasPingFederate | FormsAuthentication removed, OIDC configured |
| hasLDAP | Zero DirectoryEntry in src-core/ |
| hasWebForms | Zero .aspx files in QUEUE (BLOCK files documented) |
| hasCrystalReports | All .rpt files either replaced or BLOCK with decision |

---

## Final release gates

```bash
# 1. Build
dotnet build src-core/ --configuration Release

# 2. Tests
dotnet test src-core/ --filter "Category!=Integration" --collect:"XPlat Code Coverage"

# 3. CVE
dotnet list package --vulnerable --include-transitive

# 4. Framework refs
grep -r "using System.Web" src-core/ --include="*.cs"

# 5. TODO markers to review
grep -r "TODO-MIGRATION" src-core/ --include="*.cs" | wc -l
```

All must pass before running p6-migration-summary.md.
