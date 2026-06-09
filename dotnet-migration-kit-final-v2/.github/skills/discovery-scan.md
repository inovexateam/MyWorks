# Skill: Discovery Scan (P0)

## What it does
Scans legacy solution. Writes migration-state.json + screen-inventory.csv.
Drives every downstream agent decision. Run once before anything else.

## Token rule
Run once. Output cached in migration-state.json. Never re-run if file exists
with matching solution hash. Cache check: read first 3 lines of file — done.

## Invoke
```
Load: skills/discovery-scan.md
TARGET: solution root
OUTPUT: .github/memory/migration-state.json
        .github/memory/screen-inventory.csv
```

## Detection checklist

### Databases
```
grep -r "OracleConnection\|Oracle.DataAccess\|Oracle.ManagedDataAccess" --include="*.cs" -l
grep -r "DB2Connection\|IBM.Data.DB2" --include="*.cs" -l
grep -r "SqlConnection" --include="*.cs" -l
grep -r "StackExchange.Redis\|IDistributedCache" --include="*.cs" -l
```

### Auth
```
grep -r "FormsAuthentication\|WindowsIdentity\|PingFederate\|Saml2\|OpenIdConnect" --include="*.cs" -l
grep -r "System.IdentityModel\|WIF" --include="*.cs" -l
```

### Integrations
```
grep -r "ServiceReference\|ClientBase\|System.ServiceModel" --include="*.cs" -l  → WCF
grep -r "OracleConnection" --include="*.cs" -l                                   → Oracle
grep -r "DB2Connection" --include="*.cs" -l                                      → DB2
grep -r "VenafiClient\|TPP\|TLS Protect" --include="*.cs" -l                    → Venafi
grep -r "log4net\|EntLib\|Logger.Write" --include="*.cs" -l                     → Legacy logging
grep -r "RestClient\|HttpClient\|WebClient" --include="*.cs" -l                 → External HTTP
```

### UI
```
find . -name "*.aspx" | wc -l        → WebForms count
find . -name "*.ascx" | wc -l        → UserControl count
find . -name "*.master" | wc -l      → MasterPage count
find . -name "*.vb" | wc -l          → VB.NET count
find . -name "*.asmx" | wc -l        → SOAP count
grep -r "ApiController" --include="*.cs" -l | wc -l  → Web API 2
grep -r "static void Main" --include="*.cs" -l        → Console apps
```

### Framework version
```
grep -r "TargetFrameworkVersion\|TargetFramework" --include="*.csproj" --include="*.vbproj"
```

## Output: migration-state.json
```json
{
  "scannedAt": "ISO-timestamp",
  "solutionHash": "git-rev-parse HEAD",
  "hasOracle": false,
  "hasDB2": false,
  "hasSqlServer": true,
  "hasRedis": false,
  "hasPingFederate": false,
  "hasWCF": false,
  "hasVenafi": false,
  "hasEntityFramework": true,
  "hasEF6": true,
  "hasADONet": true,
  "hasLog4Net": true,
  "hasWebAPI2": true,
  "hasConsoleApps": false,
  "hasVBNet": false,
  "hasSOAP": false,
  "hasLDAP": false,
  "hasApigee": false,
  "totalAspxPages": 0,
  "totalAscxControls": 0,
  "totalMasterPages": 0,
  "totalVbFiles": 0,
  "totalSoapServices": 0,
  "totalCodeBehindFiles": 0,
  "totalConsoleProjects": 0,
  "targetFrameworks": [],
  "projects": []
}
```

## Output: screen-inventory.csv
```csv
Screen,File,LOC,Controls,HasCodeBehind,UpdatePanel,GridView,MasterPage,EstimatedHours,MigrationPath
CustomerList,src/WebApp/Customer/List.aspx,245,8,true,true,true,Site.Master,4,ReactSPA
OrderDetail,src/WebApp/Order/Detail.aspx,180,12,true,false,false,Site.Master,3,RazorPage
```

## Migration path rules (auto-assign)
```
Page has UpdatePanel AND GridView → ReactSPA (complex interaction)
Page is read-only display          → RazorPage
Page is simple CRUD form           → RazorPage
Page has chart/reporting controls  → ReactSPA
Organization standardizes Angular  → AngularSPA (override flag)
```

## Copilot prompt to trigger this skill
```
Read .github/skills/discovery-scan.md. Scan this entire solution.
Write results to .github/memory/migration-state.json and
.github/memory/screen-inventory.csv. Show summary when done.
```

---

## Dependency graph computation (run after file scan)

After detecting all files, compute migration order from .csproj references:

```bash
# For each .csproj in src-framework/, extract ProjectReference elements
grep -r "ProjectReference" src-framework/ --include="*.csproj" -h \
  | grep -oP 'Include="[^"]*"' \
  | sed 's/Include=//; s/"//g'
```

Build adjacency list:
```
ProjectA depends on → [ProjectB, ProjectC]
ProjectB depends on → [ProjectC]
ProjectC depends on → []   ← leaf, migrate first
```

Topological sort output → write to CODEBASE-MAP.md:
```
# ORDER: ProjectC → ProjectB → ProjectA → WebApp
```

This order replaces any fixed P0→P6 sequence.
If circular dependency found → flag in CODEBASE-MAP.md as 🚧 BLOCK with note.

## migration-state.json — add dep graph section

```json
{
  ...existing flags...,
  "dependencyOrder": ["Utilities", "DAC", "BC", "SAC", "BPC", "WebApp"],
  "circularDependencies": [],
  "projectCount": 6
}
```
