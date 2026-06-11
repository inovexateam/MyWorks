# CODEBASE-MAP
# Read first every session. One line per file.
# Hash check: git log -1 --format="%H" -- <filepath>
# Match + ✅ = skip (20 tokens). Differ = work (1,500 tokens).
#
# FORMAT: STATUS | PROJECT | FILE | HASH | PROMPT-USED | COV% | NOTE
# STATUS: ✅ DONE | 🔄 WIP | ⏳ QUEUE | 🚧 BLOCK | 🔍 AST-DONE | ⏭ SKIP
#
# ORDER: [computed from .csproj graph on first run — Copilot writes here]
# SIGNALS: [copied from signals.json on first run]
#
# APPROVED PACKAGES (Artifactory — no re-check):
# Microsoft.EntityFrameworkCore 8.0.x | Oracle.ManagedDataAccess.Core 23.x
# IBM.Data.Db2.Core 3.x | Novell.Directory.Ldap.NETStandard 3.6.0
# Dapper 2.1.x | Serilog.AspNetCore 8.x | StackExchange.Redis 2.7.x
# Hangfire.AspNetCore 1.8.x | CoreWCF.Http 1.5.x | Swashbuckle.AspNetCore 6.x
# Microsoft.Reporting.NETCore 3.0.0 | FastReport.OpenSource 2024.x
#
# SA CACHE (org Roslyn rules — skip if hash matches):
# SA | ORG-SA-001 | <file> | <hash> | PASS | <date>
#
# FILES (Copilot populates after discovery prompt):
