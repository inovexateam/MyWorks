# CODEBASE MAP
# READ THIS FIRST — every session, every agent, every project.
# Do NOT load any skill or agent file until you check this map.
# Format: STATUS | PROJECT | FILE | HASH | AGENT | COVERAGE | NOTE

# ═══ HOW TO USE ═══════════════════════════════════════════════════════════════
# Before touching any file:
#   hash=$(git rev-parse HEAD:path/to/file.cs)
#   Find the file row below.
#   If status=✅ AND stored hash matches → SKIP. Output: "cache HIT [file]" and move on.
#   If status=✅ AND hash differs → file changed. Re-run, update row.
#   If status=🚧 → do not attempt. Note the blocker.
#   If not in map → new file. Add row after completing work.
#
# Skill/agent files to load — ONLY when map says you need them:
#   Analysing .cs files     → skills/code-analysis.md
#   Package changes         → skills/dependency-mapping.md
#   Security check          → skills/security-review.md
#   EF/data layer           → agents/agent-data-migrator.md
#   .aspx pages             → agents/agent-ui-adapter.md
#   File >500 LOC           → agents/agent-complexity-decomposer.md
#   Unknown blocker         → plugins/diagnostic-bundle.md
#   Never load all files. Load only what this map says you need.

# ═══ STATUS KEY ═══════════════════════════════════════════════════════════════
# ✅ DONE  — migrated · tested · security-cleared · PR merged
# 🔄 WIP   — in progress this session
# 🔍 MAP   — analysis cached, migration not started
# 🚧 BLOCK — cannot proceed (see NOTE)
# ⏭ SKIP  — excluded (legacy compat, third-party, generated)
# ⏳ QUEUE — ready to start, not yet assigned

# ═══ STATIC ANALYSIS CACHE ════════════════════════════════════════════════════
# ORG rules cached here — never re-run on unchanged files (check hash first)
# Format: SA-RESULT | ORG-RULE-ID | FILE | HASH | PASS/FAIL | DATE
# SA-RESULT | ORG-SA-001 | src/DAC/UserRepo.cs | a3f2c1 | PASS | 2025-01-12
# SA-RESULT | ORG-SA-003 | src/DAC/UserRepo.cs | a3f2c1 | PASS | 2025-01-12


# ═══ WebApp (ASP.NET → .NET 8) ════════════════════════════════════════════════
# STATUS  | PROJECT | FILE                                | HASH   | AGENT              | COV  | NOTE
✅ DONE   | Utilities | src/Utilities/StringHelper.cs     | a3f2c1 | code-refactor      | 82%  | pure logic
✅ DONE   | Utilities | src/Utilities/DateExtensions.cs   | b7e4d2 | code-refactor      | 79%  | pure logic
✅ DONE   | Utilities | src/Utilities/ValidationHelper.cs | c9a1f3 | code-refactor      | 81%  | nullable added
⏳ QUEUE  | DAC       | src/DAC/UserRepository.cs         | —      | data-migrator      | —    | EF6→Core, 287 LOC
⏳ QUEUE  | DAC       | src/DAC/OrderRepository.cs        | —      | data-migrator      | —    | EF6→Core, 312 LOC
🚧 BLOCK  | DAC       | src/DAC/ReportService.cs          | f1c4b9 | dep-resolver       | —    | Crystal Reports — awaiting stakeholder
🚧 BLOCK  | DAC       | src/DAC/LegacyOrmContext.cs       | e2d1a0 | dep-resolver       | —    | OpenAccess ORM — no Core equivalent
⏳ QUEUE  | BC        | src/BC/OrderService.cs            | —      | code-refactor      | —    | wait for DAC
⏳ QUEUE  | WebApp    | src/WebApp/Pages/ProductList.aspx | —      | ui-adapter         | —    | GridView, UpdatePanel

# ═══ SOAP Services Project ════════════════════════════════════════════════════
⏳ QUEUE  | SoapSvc   | src/SoapSvc/CustomerSvc.asmx      | —      | code-refactor      | —    | →gRPC or minimal API
⏳ QUEUE  | SoapSvc   | src/SoapSvc/OrderSvc.asmx         | —      | code-refactor      | —    | →gRPC or minimal API
🔍 MAP    | SoapSvc   | src/SoapSvc/LegacyProxy.cs        | d4e5f6 | code-refactor      | —    | 640 LOC — needs decompose first

# ═══ [ADD YOUR OTHER PROJECTS HERE] ═══════════════════════════════════════════
# Copy the format above for each .NET Web App, WCF service, class library, etc.
# One line per file. This file is your single source of truth across ALL projects.


# ═══ CROSS-PROJECT BLOCKERS ═══════════════════════════════════════════════════
# B001 | Crystal Reports | DAC/ReportSvc, WebApp/Reports/* | Stakeholder decision pending
# B002 | OpenAccess ORM  | DAC/LegacyOrmCtx               | agent-dep-resolver investigating
# B003 | SOAP→REST       | SoapSvc/*                       | API contract decision needed


# ═══ ARTIFACTORY PACKAGE REGISTRY (approved — no re-check needed) ══════════════
# PKG | Microsoft.EntityFrameworkCore  | 8.0.x  | APPROVED | replaces EF6
# PKG | Serilog.AspNetCore             | 8.x    | APPROVED | replaces log4net
# PKG | AutoMapper                     | 13.x   | APPROVED | compatible
# PKG | FluentValidation.AspNetCore    | 11.x   | APPROVED | new
# PKG | StackExchange.Redis            | 2.7.x  | APPROVED | no change needed
# PKG | Hangfire.AspNetCore            | 1.8.x  | APPROVED | replaces custom scheduler
# All packages sourced from: https://artifactory.yourorg.com/artifactory/api/nuget/nuget-virtual
