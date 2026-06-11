# Agent: Oracle / DB2 Migrator

## Identity
Migrates Oracle ODP.NET and IBM DB2 connections to .NET 8 managed drivers.
Activated when signals.json hasOracle = true OR hasDB2 = true.

## Pre-work
Hash check. ✅ match → skip.

## Oracle migration

### Package swap (from Artifactory)
```xml
<!-- Remove -->
<Reference Include="Oracle.DataAccess" />   <!-- unmanaged — no Core support -->
<!-- Add -->
<PackageReference Include="Oracle.ManagedDataAccess.Core" Version="23.x" />
```

### Code changes
```csharp
// Namespace
using Oracle.DataAccess.Client;  →  using Oracle.ManagedDataAccess.Client;

// Connection — inject via IConfiguration
public class OracleRepo(IConfiguration config) {
    private readonly string _conn = config.GetConnectionString("OracleDB")!;
    public async Task<List<T>> QueryAsync<T>(string sql, object? param = null) {
        await using var conn = new OracleConnection(_conn);
        return (await conn.QueryAsync<T>(sql, param)).ToList();
    }
}

// Parameter prefix: :param → @param (Dapper style)
// Keep Oracle SQL syntax (ROWNUM, CONNECT BY etc.) — DB-side, untouched

// OracleDataAdapter (no Core equivalent) → Dapper
var adapter = new OracleDataAdapter(cmd);   // Remove
adapter.Fill(dataTable);                    // Remove
// Replace: var results = await conn.QueryAsync<T>(sql, param);
```

### appsettings.json
```json
"ConnectionStrings": {
  "OracleDB": "Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=orahost)(PORT=1521))(CONNECT_DATA=(SID=ORCL)));User Id=appuser;Password=${ORACLE_PASSWORD};"
}
```
Password via Key Vault / env var only. Never hardcoded.

### EF Core with Oracle (if requested)
```csharp
builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseOracle(config.GetConnectionString("OracleDB")));
```

## DB2 migration

### Package swap (from Artifactory)
```xml
<!-- Remove -->
<Reference Include="IBM.Data.DB2" />   <!-- GAC-only, no Core support -->
<!-- Add -->
<PackageReference Include="IBM.Data.Db2.Core" Version="3.x" />
```

### Code changes
```csharp
using IBM.Data.DB2;  →  using IBM.Data.Db2;

// Named parameters with Dapper
// Old: cmd.Parameters.Add("@0", DB2Type.Integer).Value = id;
// New:
var result = await conn.QueryAsync<Order>(
    "SELECT * FROM ORDERS WHERE ID = @Id", new { Id = id });
```

## Map update
✅ DONE | [PROJECT] | [filepath] | [hash] | agent-oracle-db2 | — |
