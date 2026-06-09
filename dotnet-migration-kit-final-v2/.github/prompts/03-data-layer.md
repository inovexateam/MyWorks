# Prompt: Data Layer Migration

## When to use
signals.json: hasEF6, hasEDMX, or hasADONet = true.
Covers: EF6→EF Core, EDMX→Code-First, ADO.NET→Dapper, Oracle, DB2.

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md and .github/memory/signals.json.
For each ⏳ QUEUE data access file in [PROJECT]:

Hash check first. Skip ✅ DONE (hash match).

── IF hasEF6 or hasEDMX ─────────────────────────────────────────────────

EF6 → EF Core:
  DbContext constructor:
    OLD: public MyCtx() : base("name=MyDB") {}
    NEW: public AppDbContext(DbContextOptions<AppDbContext> o) : base(o) {}

  Include:
    OLD: .Include("OrderItems.Product")
    NEW: .Include(o => o.OrderItems).ThenInclude(i => i.Product)

  Find:
    OLD: context.Users.Find(id)
    NEW: await context.Users.FindAsync(id, ct)

  Raw SQL:
    OLD: context.Database.ExecuteSqlCommand("UPDATE...")
    NEW: context.Database.ExecuteSqlInterpolated($"UPDATE...")

  Remove lazy loading unless explicitly re-enabled with .UseLazyLoadingProxies()

EDMX files → Code-First:
  Run in terminal:
    dotnet ef dbcontext scaffold "<connection>" Microsoft.EntityFrameworkCore.SqlServer \
      --output-dir Infrastructure/Persistence/Models \
      --context AppDbContext --no-onconfiguring --force
  Then mark *.edmx as ⏭ SKIP in MAP.md

Register in Program.cs:
  builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseSqlServer(config.GetConnectionString("DefaultConnection")));

── IF hasADONet ─────────────────────────────────────────────────────────

ADO.NET → Dapper:
  OLD: var cmd = new SqlCommand("SELECT...", conn); var reader = cmd.ExecuteReader();
  NEW: var result = await conn.QueryAsync<T>("SELECT...", new { Id = id });

  Inject IDbConnectionFactory or IConfiguration for connection string.
  Connection string in appsettings.json — no passwords in code.

── IF hasOracle ─────────────────────────────────────────────────────────

  Remove: Oracle.DataAccess (unmanaged, no Core support)
  Add from Artifactory: Oracle.ManagedDataAccess.Core 23.x
  using Oracle.DataAccess.Client → using Oracle.ManagedDataAccess.Client
  Parameter prefix : (Oracle) → @ (Dapper style)

── IF hasDB2 ────────────────────────────────────────────────────────────

  Remove: IBM.Data.DB2 (GAC-only)
  Add from Artifactory: IBM.Data.Db2.Core 3.x
  using IBM.Data.DB2 → using IBM.Data.Db2

── ALL DATA FILES ────────────────────────────────────────────────────────

  All repository methods → async with CancellationToken
  Connection strings → appsettings.json only, never hardcoded
  DbContext lifetime → Scoped (never Singleton)
  HasQueryFilter for soft-delete entities

Update MAP.md after each file. Run dotnet build after all data files done.
```
