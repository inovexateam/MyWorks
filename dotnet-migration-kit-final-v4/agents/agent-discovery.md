# Agent: Discovery & Codebase Map Builder

## Identity
Runs once. Scans the entire legacy solution. Writes CODEBASE-MAP.md and
signals.json. Computes migration order from actual .csproj dependency graph.
Everything downstream depends on this agent running correctly first.

## Pre-work
Check: does .github/memory/signals.json exist with a real solutionHash?
If yes AND solution files unchanged → skip scan (already done).

## Copilot prompt to invoke this agent
```
Read .github/agents/agent-discovery.md.
Scan this entire solution and build the migration map.
```

## Execution

### Step 1 — Detect all technologies
```bash
# Run each detection and set signal true/false
grep -rl "OracleConnection\|Oracle\.DataAccess\|Oracle\.ManagedDataAccess" src/ --include="*.cs" | wc -l  # hasOracle
grep -rl "DB2Connection\|IBM\.Data\.DB2" src/ --include="*.cs" | wc -l                                   # hasDB2
grep -rl "SqlConnection" src/ --include="*.cs" | wc -l                                                    # hasSqlServer
grep -rl "EntityFramework\|DbContext" src/ --include="*.cs" | wc -l                                       # hasEF6
find src/ -name "*.edmx" | wc -l                                                                           # hasEDMX
grep -rl "SqlCommand\|SqlDataReader\|SqlDataAdapter" src/ --include="*.cs" | wc -l                        # hasADONet
grep -rl "ApiController\|System\.Web\.Http" src/ --include="*.cs" | wc -l                                 # hasWebAPI2
find src/ -name "*.aspx" | wc -l                                                                           # hasWebForms
find src/ -name "*.asmx" | wc -l                                                                           # hasSOAP
grep -rl "ServiceModel\|ClientBase\|ServiceReference" src/ --include="*.cs" | wc -l                       # hasWCF
find src/ -name "*.vb" | wc -l                                                                             # hasVBNet
grep -rl "static void Main" src/ --include="*.cs" | wc -l                                                  # hasConsoleApps
grep -rl "FormsAuthentication\|PingFederate\|pingfederate" src/ --include="*.cs" -i | wc -l               # hasPingFederate
grep -rl "DirectoryEntry\|DirectorySearcher" src/ --include="*.cs" | wc -l                                # hasLDAP
grep -rl "RestClient\|WebClient\|HttpWebRequest\|apigee" src/ --include="*.cs" -i | wc -l                 # hasApigee
grep -rl "VenafiClient\|TPP\|Venafi" src/ --include="*.cs" -i | wc -l                                     # hasVenafi
grep -rl "StackExchange\.Redis\|IDistributedCache\|RedisClient" src/ --include="*.cs" | wc -l             # hasRedis
grep -rl "log4net\|LogManager\.GetLogger" src/ --include="*.cs" | wc -l                                   # hasLog4Net
find src/ -name "*.rpt" | wc -l                                                                            # hasCrystalReports
```

### Step 2 — Compute dependency order from .csproj graph
```
For each .csproj: extract all <ProjectReference Include="..." /> paths
Build directed graph: A→B means A depends on B  
Topological sort: nodes with no dependencies migrate first (leaves)
Result: ordered list like [Utilities, DAC, BC, SAC, BPC, WebApp]
```

### Step 3 — Write signals.json
```json
{
  "scannedAt": "<ISO timestamp>",
  "solutionHash": "<git rev-parse HEAD>",
  "dependencyOrder": ["Utilities","DAC","BC","SAC","BPC","WebApp"],
  "hasOracle": false, "hasDB2": false, "hasSqlServer": true,
  "hasEF6": true, "hasEDMX": true, "hasADONet": true,
  "hasWebAPI2": false, "hasWebForms": true, "hasSOAP": false, "hasWCF": false,
  "hasVBNet": false, "hasConsoleApps": false, "hasPingFederate": true,
  "hasLDAP": true, "hasApigee": true, "hasVenafi": false, "hasRedis": false,
  "hasLog4Net": true, "hasCrystalReports": false,
  "totalAspxPages": 0, "totalAscxControls": 0, "totalVbFiles": 0
}
```

### Step 4 — Populate CODEBASE-MAP.md
One line per file. Format:
```
⏳ QUEUE | [PROJECT] | [filepath] | — | — | — | [note]
```
Mark 🚧 BLOCK for: *.rpt, COM Interop assemblies, OpenAccess ORM, GAC-only refs.

### Step 5 — Write ORDER line to CODEBASE-MAP.md header
```
# ORDER: Utilities → DAC → BC → SAC → BPC → WebApp
# SIGNALS: hasEF6 hasADONet hasPingFederate hasLDAP hasApigee hasWebForms
```

### Step 6 — Show summary
Table: | Signal | Value | Files affected |
List all 🚧 BLOCK entries with reason.
Confirm: "Ready to migrate. Next: run migration-bundle for [first project]."

### Step 7 — Ask for SPA framework preference
After writing signals.json, ask:

"Which SPA framework do you want for WebForms pages?
  1. React 18 + TypeScript (recommended — component-based, fast, widely used)
  2. Angular 17+ + TypeScript (if org standardises on Angular)
  3. Razor Pages (simplest — stays server-rendered, no SPA build step)

Enter 1, 2, or 3:"

Based on answer, set in signals.json:
  1 → "spaFramework": "React"
  2 → "spaFramework": "Angular"
  3 → "spaFramework": "Razor"

This setting drives every .aspx migration in the solution.
