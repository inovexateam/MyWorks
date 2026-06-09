# CODEBASE-MAP.md
# Read this first every session. One pass = ~200 tokens.
# Hash check before loading any file: match = skip (20 tokens), differ = work (1,500 tokens)
#
# STATUS:
#   ✅ DONE    — migrated · tested · security-cleared
#   🔄 WIP     — in progress this session
#   🔍 ANALYSED — AST cached, not yet migrated (.aspx only)
#   ⏳ QUEUE   — ready, dependencies met
#   🚧 BLOCK   — needs human decision (skip + continue)
#   ⏭ SKIP    — excluded (generated, third-party)
#   🔧 NEEDS-FIX — migrated, auto-fixer not yet run
#
# FORMAT: STATUS | PROJECT | FILE | HASH | AGENT | COV | NOTE

# ═══ DEPENDENCY ORDER (computed by copilot from .csproj graph) ═══════════════
# ORDER: [populated on first run — Copilot writes here after reading .csproj files]
# Example: Utilities → DAC → BC → SAC → BPC → WebApp

# ═══ ACTIVE SIGNALS (from migration-state.json) ══════════════════════════════
# Agents activated: [populated on first run from migration-state.json]
# Example: data-migrator, oracle-db2, vbnet, webapi2

# ═══ STATIC ANALYSIS CACHE (org Roslyn rules — skip if hash matches) ═════════
# SA | ORG-SA-001 | <filepath> | <hash> | PASS | <date>

# ═══ APPROVED PACKAGES (Artifactory — no re-check needed) ════════════════════
# PKG | Microsoft.EntityFrameworkCore         | 8.0.x | APPROVED
# PKG | Oracle.ManagedDataAccess.Core         | 23.x  | APPROVED
# PKG | IBM.Data.Db2.Core                     | 3.x   | APPROVED
# PKG | Novell.Directory.Ldap.NETStandard     | 3.6.0 | APPROVED
# PKG | StackExchange.Redis                   | 2.7.x | APPROVED
# PKG | Serilog.AspNetCore                    | 8.x   | APPROVED
# PKG | Hangfire.AspNetCore                   | 1.8.x | APPROVED
# PKG | Dapper                                | 2.1.x | APPROVED
# PKG | CoreWCF.Http                          | 1.5.x | APPROVED
# PKG | Swashbuckle.AspNetCore                | 6.x   | APPROVED
# PKG | Microsoft.Reporting.NETCore           | 3.0.0 | APPROVED
# PKG | FastReport.OpenSource                 | 2024.x| APPROVED
# PKG | Microsoft.AspNetCore.OpenApi          | 8.0.x | APPROVED
# PKG | Novell.Directory.Ldap.NETStandard     | 3.6.0 | APPROVED

# ═══ FILES (populated by discovery scan) ═════════════════════════════════════
# Copilot writes one line per file after the first scan.
# Example entries:
#
# ✅ DONE  | Utilities | src/Utilities/StringHelper.cs   | a3f2c1 | code-refactor  | 82% |
# ⏳ QUEUE | DAC       | src/DAC/UserRepository.cs        | —      | data-migrator  | —   | EF6
# 🚧 BLOCK | DAC       | src/DAC/ReportService.cs         | f1c4b9 | —              | —   | Crystal Reports — awaiting decision
# 🔍 ANALYSED | WebApp | src/WebApp/Customer/List.aspx   | d4e2a1 | ui-adapter     | —   | ast: memory/ast/CustomerList.ast.json
