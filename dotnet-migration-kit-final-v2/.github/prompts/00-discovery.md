# Prompt: Discovery

## When to use
First session only. Run before anything else.

## Paste this in Copilot Agent mode

```
Read .github/copilot-instructions.md.

Scan every .cs, .vb, .aspx, .ascx, .asmx, .csproj, .vbproj file in this solution.

DETECT and set true/false in .github/memory/signals.json:
- hasOracle: grep OracleConnection
- hasDB2: grep DB2Connection
- hasSqlServer: grep SqlConnection
- hasEF6: grep "EntityFramework" in packages.config or .csproj
- hasEDMX: find *.edmx
- hasADONet: grep SqlCommand
- hasWebAPI2: grep ApiController
- hasWebForms: find *.aspx
- hasSOAP: find *.asmx
- hasWCF: grep ServiceModel
- hasVBNet: find *.vb
- hasConsoleApps: grep "static void Main"
- hasPingFederate: grep -i "pingfederate\|FormsAuthentication"
- hasLDAP: grep DirectoryEntry
- hasApigee: grep -i "apigee\|RestClient\|WebClient"
- hasVenafi: grep -i venafi
- hasRedis: grep -i "StackExchange.Redis\|IDistributedCache"
- hasCrystalReports: find *.rpt
- hasLog4Net: grep log4net

COUNT: totalAspxPages, totalAscxControls, totalVbFiles, totalConsoleProjects

COMPUTE dependency order:
- Read ProjectReference tags in every .csproj
- Build directed graph: A→B means A depends on B
- Topological sort: leaves first
- Write to signals.json dependencyOrder array
- Write same order to MAP.md: # ORDER: Utilities → DAC → BC → ...

POPULATE MAP.md — one line per file:
⏳ QUEUE | [PROJECT] | [filepath] | — | — | — | [brief note if special]
Mark 🚧 BLOCK for: *.rpt, OpenAccess ORM, COM Interop, GAC-only assemblies

Write signals.json with scannedAt timestamp and solutionHash.

Show summary table when done:
| Signal | Value | Files affected |
```

## After discovery
1. Open MAP.md — review all 🚧 BLOCK entries
2. Decide Crystal Reports replacement (see prompts/07-crystal-reports.md)
3. Edit nuget.config — replace Artifactory URL placeholder
4. Run structure prompt next
