# Prompt: Phase 3 — Enterprise Integrations

## Purpose
Targeted prompts for Oracle, DB2, Redis, Venafi, LDAP, Apigee, Ping, WCF.
Each only activates when migration-state.json confirms the technology present.

---

## Oracle / DB2 Prompt

```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-oracle-db2-migrator.md.
Read .github/memory/migration-state.json.

If hasOracle is false AND hasDB2 is false → stop, nothing to do.

For each ⏳ QUEUE file with Oracle or DB2 data access:
  1. Check hash — skip ✅ DONE
  2. Oracle: replace Oracle.DataAccess with Oracle.ManagedDataAccess.Core
     Replace OracleConnection pattern with managed equivalent
     Replace parameter prefix from : to @ (Dapper style)
  3. DB2: replace IBM.Data.DB2 with IBM.Data.Db2.Core
  4. Replace all DataAdapter.Fill(DataTable) with Dapper QueryAsync<T>
  5. Inject connection via IDbConnectionFactory or IConfiguration
  6. Move all connection strings to appsettings.json — no passwords
  7. Update CODEBASE-MAP.md after each file
```

---

## Redis Prompt

```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-redis-venafi-migrator.md.
Read .github/memory/migration-state.json.

If hasRedis is false → stop.

For each ⏳ QUEUE file with Redis usage:
  1. Check hash — skip ✅ DONE
  2. Replace ServiceStack.Redis or direct StackExchange patterns
     with IDistributedCache abstraction
  3. Register in Program.cs:
     builder.Services.AddStackExchangeRedisCache(o =>
       o.Configuration = config.GetConnectionString("Redis"));
  4. For pub/sub or Lua scripts: use IConnectionMultiplexer directly
  5. All cache operations async with CancellationToken
  6. Update map after each file
```

---

## Venafi Prompt

```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-redis-venafi-migrator.md.

For Venafi: first determine deployment target.

If deploying to OpenShift / Kubernetes:
  Remove all direct Venafi SDK calls from application code.
  Add comment: // TODO-MIGRATION: Certificate rotation handled by cert-manager
  App reads cert from mounted K8s secret or certificate store.

If NOT Kubernetes (on-prem IIS):
  Migrate Venafi SDK calls to typed HttpClient against Venafi TPP REST API.
  API key from Key Vault / environment variable only.

Update CODEBASE-MAP.md after each file.
```

---

## LDAP Prompt

```
Read .github/memory/CODEBASE-MAP.md.

For each ⏳ QUEUE file with System.DirectoryServices:
  1. Check hash
  2. Replace DirectoryEntry / DirectorySearcher with
     Novell.Directory.Ldap.NETStandard (from Artifactory)
  3. Create LdapOptions class with Host, Port, BaseDn, BindDn
  4. Register: builder.Services.Configure<LdapOptions>(config.GetSection("Ldap"))
  5. LDAP credentials: environment variables / Key Vault only
  6. All LDAP operations async
  7. Update map after each file
```

---

## Apigee / External HTTP Prompt

```
Read .github/memory/CODEBASE-MAP.md.

For each ⏳ QUEUE file with RestSharp / WebClient / HttpWebRequest:
  1. Check hash
  2. Create typed HttpClient class implementing interface
  3. Register: builder.Services.AddHttpClient<IClient, Client>(c => {
       c.BaseAddress = new Uri(config["ServiceName:BaseUrl"]!);
     });
  4. BaseUrl and ApiKey from IConfiguration (Key Vault in prod)
  5. Replace all sync calls with async + CancellationToken
  6. Use GetFromJsonAsync / PostAsJsonAsync where possible
  7. Update map after each file
```

---

## Ping / OIDC Prompt

```
PREREQUISITE: Get from identity team before running this prompt:
  - Ping Discovery URL → Key Vault: Ping:Authority
  - Client ID          → Key Vault: Ping:ClientId
  - Client Secret      → Key Vault: Ping:ClientSecret

Read .github/memory/CODEBASE-MAP.md.

Add Microsoft.AspNetCore.Authentication.OpenIdConnect package.
In Program.cs configure:
  AddAuthentication Cookie + OpenIdConnect
  Authority / ClientId / ClientSecret from IConfiguration
  HttpOnly + Secure + SameSite=Strict cookies

Replace all FormsAuthentication.SetAuthCookie → Challenge()
Replace all FormsAuthentication.SignOut → SignOutAsync (both schemes)
Replace [System.Web.Security.Authorize] → [Authorize]

Update CODEBASE-MAP.md.
```

---

## WCF Client Prompt

```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-soap-wcf-migrator.md.

For each ⏳ QUEUE file with ServiceReference / ClientBase / BasicHttpBinding:
  1. Check hash — skip ✅ DONE
  2. Determine: does external party require WSDL contract?
     YES → migrate to CoreWCF (preserves WSDL)
     NO  → migrate to typed HttpClient + JSON
  3. For CoreWCF: add CoreWCF.Http package, keep service contract interfaces
  4. For HttpClient: replace proxy calls with typed HttpClient methods
  5. Move endpoint URLs to IConfiguration
  6. Update map after each file
```
