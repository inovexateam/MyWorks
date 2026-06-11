# Skill: Discovery Scan

## Purpose
Called by agent-discovery. Defines detection commands and output format.
Result cached in signals.json — never re-run if solutionHash matches.

## Detection commands
```bash
# Databases
grep -rl "OracleConnection\|Oracle\.DataAccess" src/ --include="*.cs" | wc -l   # hasOracle
grep -rl "DB2Connection\|IBM\.Data\.DB2" src/ --include="*.cs" | wc -l          # hasDB2
grep -rl "SqlConnection\b" src/ --include="*.cs" | wc -l                         # hasSqlServer
# ORM
grep -rl "ObjectContext\|DbSet\|DbContext" src/ --include="*.cs" | wc -l         # hasEF6
find src/ -name "*.edmx" 2>/dev/null | wc -l                                      # hasEDMX
grep -rl "SqlCommand\|SqlDataReader" src/ --include="*.cs" | wc -l               # hasADONet
# UI
find src/ -name "*.aspx" 2>/dev/null | wc -l                                      # hasWebForms
find src/ -name "*.asmx" 2>/dev/null | wc -l                                      # hasSOAP
grep -rl "ApiController\|System\.Web\.Http" src/ --include="*.cs" | wc -l        # hasWebAPI2
# Services
grep -rl "ServiceModel\|ClientBase" src/ --include="*.cs" | wc -l               # hasWCF
# Language
find src/ -name "*.vb" 2>/dev/null | wc -l                                        # hasVBNet
grep -rl "static void Main" src/ --include="*.cs" | wc -l                        # hasConsoleApps
# Auth
grep -ril "FormsAuthentication\|pingfederate" src/ --include="*.cs" | wc -l     # hasPingFederate
grep -rl "DirectoryEntry\|DirectorySearcher" src/ --include="*.cs" | wc -l      # hasLDAP
# External
grep -ril "RestClient\|WebClient\|apigee" src/ --include="*.cs" | wc -l         # hasApigee
grep -ril "venafi" src/ --include="*.cs" | wc -l                                  # hasVenafi
grep -rl "StackExchange\.Redis\|IDistributedCache" src/ --include="*.cs" | wc -l # hasRedis
# Misc
find src/ -name "*.rpt" 2>/dev/null | wc -l                                       # hasCrystalReports
grep -rl "log4net\|LogManager\.GetLogger" src/ --include="*.cs" | wc -l         # hasLog4Net
```

## Dependency graph algorithm
```
1. Find all *.csproj files
2. For each: extract <ProjectReference Include="..." /> paths
3. Build map: projectName → [dependencies]
4. Topological sort (Kahn's algorithm):
   - Find nodes with no incoming edges (leaves)
   - Add to order, remove their edges
   - Repeat until all nodes placed
5. Output: ["Utilities","DAC","BC","SAC","BPC","WebApp"]
```

## BLOCK conditions
Flag as 🚧 BLOCK in CODEBASE-MAP.md when file contains:
- Crystal Reports .rpt binary or CrystalDecisions namespace
- OpenAccess ORM (Telerik.OpenAccess)
- COM Interop [ComImport] attributes
- GAC-only references not available as NuGet packages
