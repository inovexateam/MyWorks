# CODEBASE-MAP.md
# Read first every session. One line per file. Hash check before any work.
# Hash: git log -1 --format="%H" -- <filepath>
# Match + ✅ = skip (20 tokens). Differ = work (1,500 tokens).
#
# STATUS:
#   ✅ DONE     — migrated · tested · security-cleared
#   🔄 WIP      — in progress this session
#   🔍 AST-DONE — AST extracted, migration pending (.aspx only)
#   ⏳ QUEUE    — ready, dependencies met
#   🚧 BLOCK    — needs human decision (skip and continue)
#   ⏭ SKIP     — excluded (generated, third-party)
#
# FORMAT: STATUS | PROJECT | FILE | HASH | AGENT | COV% | NOTE
#
# ORDER: [computed from .csproj graph on first run — agent-discovery writes here]
# SIGNALS: [copied from signals.json on first run]
#
# SA CACHE (org Roslyn rules — skip if hash matches):
# SA | ORG-SA-001 | <file> | <hash> | PASS | <date>
#
# APPROVED PACKAGES (from Artifactory — no re-check needed):
# PKG | Microsoft.EntityFrameworkCore 8.0.x
# PKG | Oracle.ManagedDataAccess.Core 23.x
# PKG | IBM.Data.Db2.Core 3.x
# PKG | Novell.Directory.Ldap.NETStandard 3.6.0
# PKG | Dapper 2.1.x
# PKG | Serilog.AspNetCore 8.x
# PKG | StackExchange.Redis 2.7.x
# PKG | Hangfire.AspNetCore 1.8.x
# PKG | CoreWCF.Http 1.5.x
# PKG | Swashbuckle.AspNetCore 6.x
# PKG | Microsoft.Reporting.NETCore 3.0.0
# PKG | FastReport.OpenSource 2024.x
# PKG | FluentValidation.AspNetCore 11.x
# PKG | AutoMapper 13.x
#
# FILES — populated by agent-discovery on first run:
