# Agent: Oracle / DB2 Migrator

## Identity
Migrates Oracle ODP.NET and IBM DB2 data access code to .NET 8 compatible
drivers. Does NOT change SQL logic — only the connection/command plumbing.

## Trigger
migration-state.json: hasOracle: true OR hasDB2: true

## Token rule
Check CODEBASE-MAP.md hash. If ✅ DONE + hash match → skip entirely.

## Oracle migration

### Package swap (Artifactory NuGet)
```xml
<!-- ❌ Remove -->
<Reference Include="Oracle.DataAccess" />  <!-- ODP.NET unmanaged — no Core support -->

<!-- ✅ Add (from Artifactory) -->
<PackageReference Include="Oracle.ManagedDataAccess.Core" Version="23.x" />
```

### Connection pattern
```csharp
// ❌ Framework ODP.NET (unmanaged)
using Oracle.DataAccess.Client;
var conn = new OracleConnection(ConfigurationManager.ConnectionStrings["OracleDB"].ConnectionString);

// ✅ Core managed driver
using Oracle.ManagedDataAccess.Client;
public class OracleRepository(IConfiguration config)
{
    private readonly string _conn = config.GetConnectionString("OracleDB")!;

    public async Task<List<T>> QueryAsync<T>(string sql, object? param = null)
    {
        await using var conn = new OracleConnection(_conn);
        return (await conn.QueryAsync<T>(sql, param)).ToList();
    }
}
```

### Oracle-specific → standard SQL
```csharp
// ❌ Oracle-specific syntax in code
":param"  → "@param"  (Dapper parameterization)
// Keep ROWNUM, CONNECT BY etc. in SQL strings — they're DB-side, not .NET

// ❌ OracleDataAdapter (no Core equivalent)
var adapter = new OracleDataAdapter(cmd);
adapter.Fill(dataTable);

// ✅ Dapper replacement
var results = await conn.QueryAsync<MyModel>(sql, parameters);
```

### appsettings.json
```json
{
  "ConnectionStrings": {
    "OracleDB": "Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=orahost)(PORT=1521))(CONNECT_DATA=(SID=ORCL)));User Id=appuser;Password=${ORACLE_PASSWORD};"
  }
}
```
Password from Key Vault / environment variable — never hardcoded.

## DB2 migration

### Package swap (Artifactory NuGet)
```xml
<!-- ❌ Remove -->
<Reference Include="IBM.Data.DB2" />  <!-- Framework-only GAC assembly -->

<!-- ✅ Add (from Artifactory) -->
<PackageReference Include="IBM.Data.Db2.Core" Version="3.x" />
<!-- OR if org uses community package: -->
<PackageReference Include="Net.IBM.Data.Db2" Version="8.x" />
```

### Connection pattern
```csharp
// ❌ Framework
using IBM.Data.DB2;
var conn = new DB2Connection(connStr);

// ✅ Core
using IBM.Data.Db2;
await using var conn = new DB2Connection(_connStr);
var results = await conn.QueryAsync<OrderModel>(sql, param);
```

### DB2-specific parameter syntax
```csharp
// ❌ Positional parameters
cmd.Parameters.Add("@0", DB2Type.Integer).Value = id;

// ✅ Named parameters with Dapper
var result = await conn.QueryAsync<Order>(
    "SELECT * FROM ORDERS WHERE ID = @Id",
    new { Id = id });
```

## EF Core with Oracle/DB2 (if requested)
```csharp
// Oracle EF Core provider
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseOracle(config.GetConnectionString("OracleDB")));

// DB2 — use community provider
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseDb2(config.GetConnectionString("DB2")));
```

## Copilot prompt
```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-oracle-db2-migrator.md.
Check migration-state.json for hasOracle and hasDB2.
Migrate all ⏳ QUEUE Oracle/DB2 data access files. Replace unmanaged drivers
with Oracle.ManagedDataAccess.Core or IBM.Data.Db2.Core. Use Dapper for query
execution. Move connection strings to appsettings.json (no passwords).
Update CODEBASE-MAP.md after each file.
```
