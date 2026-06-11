# Prompt: Enterprise Integrations

## When to use
signals.json: hasLDAP, hasApigee, hasPingFederate, hasRedis, hasVenafi, hasWCF, hasSOAP = true.
Only run for signals that are true — skip the rest.

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md and .github/memory/signals.json.
For each ⏳ QUEUE integration file — hash check first, skip ✅ DONE.
Only apply sections where the signal is true.

── LDAP (hasLDAP) ───────────────────────────────────────────────────────

Remove: System.DirectoryServices, DirectoryEntry, DirectorySearcher
Add from Artifactory: Novell.Directory.Ldap.NETStandard 3.6.0

Create strongly-typed options class:
  public class LdapOptions { public string Host{get;set;} public int Port{get;set;}
    public string BaseDn{get;set;} public string BindDn{get;set;} public string BindPassword{get;set;} }
Register: builder.Services.Configure<LdapOptions>(config.GetSection("Ldap"))
Inject: IOptions<LdapOptions> options

Replace DirectorySearcher queries:
  await conn.ConnectAsync(options.Host, options.Port)
  await conn.BindAsync(options.BindDn, options.BindPassword)
  conn.Search(options.BaseDn, LdapConnection.ScopeSub, $"(sAMAccountName={username})", null, false)

LDAP credentials → appsettings.json keys only, values in Key Vault / env vars.

── APIGEE / EXTERNAL HTTP (hasApigee) ───────────────────────────────────

Remove: RestSharp, WebClient, HttpWebRequest
Replace with typed HttpClient:

  public class ApigeeProductClient(HttpClient http) : IApigeeProductClient {
    public async Task<List<Product>> GetProductsAsync(string search, CancellationToken ct = default)
      => await http.GetFromJsonAsync<List<Product>>($"/products?q={search}", ct) ?? [];
  }

Register in Program.cs:
  builder.Services.AddHttpClient<IApigeeProductClient, ApigeeProductClient>(c => {
    c.BaseAddress = new Uri(config["Apigee:BaseUrl"]!);
    c.DefaultRequestHeaders.Add("x-api-key", config["Apigee:ApiKey"]);
  });

Base URL and API key → Key Vault / env vars. Never in appsettings.json values.

── PING / OIDC (hasPingFederate) ────────────────────────────────────────

PREREQUISITE: Get from identity team first:
  Ping:Authority (discovery URL) → Key Vault
  Ping:ClientId                  → Key Vault
  Ping:ClientSecret              → Key Vault

Remove: FormsAuthentication.SetAuthCookie, FormsAuthentication.SignOut

Add to Program.cs:
  builder.Services
    .AddAuthentication(o => {
      o.DefaultScheme = CookieAuthenticationDefaults.AuthenticationScheme;
      o.DefaultChallengeScheme = OpenIdConnectDefaults.AuthenticationScheme;
    })
    .AddCookie(o => {
      o.Cookie.HttpOnly = true;
      o.Cookie.SecurePolicy = CookieSecurePolicy.Always;
      o.Cookie.SameSite = SameSiteMode.Strict;
      o.ExpireTimeSpan = TimeSpan.FromHours(8);
    })
    .AddOpenIdConnect(o => {
      o.Authority = config["Ping:Authority"];
      o.ClientId = config["Ping:ClientId"];
      o.ClientSecret = config["Ping:ClientSecret"];
      o.ResponseType = OpenIdConnectResponseType.Code;
      o.SaveTokens = true;
    });

SetAuthCookie → return Challenge(OpenIdConnectDefaults.AuthenticationScheme)
SignOut → await HttpContext.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme)
         await HttpContext.SignOutAsync(OpenIdConnectDefaults.AuthenticationScheme)

── REDIS (hasRedis) ──────────────────────────────────────────────────────

Replace ServiceStack.Redis / legacy StackExchange patterns:

Program.cs:
  builder.Services.AddStackExchangeRedisCache(o =>
    o.Configuration = config.GetConnectionString("Redis"));

Service injection: IDistributedCache cache
Get: var json = await cache.GetStringAsync(key, ct)
Set: await cache.SetStringAsync(key, JsonSerializer.Serialize(obj),
       new DistributedCacheEntryOptions { AbsoluteExpirationRelativeToNow = TimeSpan.FromHours(1) }, ct)

For pub/sub or Lua scripts only: inject IConnectionMultiplexer directly.

── VENAFI (hasVenafi) ────────────────────────────────────────────────────

If deploying to OpenShift / Kubernetes:
  Remove all Venafi SDK calls from application code.
  Insert: // TODO-MIGRATION: Certificate rotation handled by cert-manager (Venafi issuer)
  App reads cert from K8s mounted secret — no SDK needed.

If NOT Kubernetes (IIS on-prem):
  Replace Venafi SDK with typed HttpClient against Venafi TPP REST API.
  Venafi API key → Key Vault. Never in code.

── WCF CLIENT (hasWCF) ───────────────────────────────────────────────────

External clients need WSDL preserved?
  YES → Add CoreWCF.Http from Artifactory. Keep service contract interfaces unchanged.
  NO  → Replace proxy calls with typed HttpClient + JSON (same as Apigee pattern above).

── SOAP ASMX SERVER (hasSOAP) ────────────────────────────────────────────

For each .asmx file:
  Remove [WebService], [WebMethod], System.Web.Services
  Each WebMethod → Minimal API endpoint in Program.cs:
    app.MapGet("/customers/{id:int}", async (int id, ICustomerService svc, CancellationToken ct)
      => await svc.GetAsync(id, ct) is { } c ? Results.Ok(c) : Results.NotFound())
      .WithOpenApi();

Update MAP.md after each file. Run dotnet build when done.
```
