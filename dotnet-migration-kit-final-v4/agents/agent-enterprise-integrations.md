# Agent: Enterprise Integrations

## Identity
Handles LDAP, Apigee, Ping OIDC, Redis, Venafi, WCF clients.
Activated by any true signal: hasLDAP, hasApigee, hasPingFederate, hasRedis, hasVenafi, hasWCF.

## Pre-work
Hash check. ✅ match → skip. Only apply sections where signal is true.

## LDAP (hasLDAP)
```csharp
// Remove: System.DirectoryServices, DirectoryEntry, DirectorySearcher
// Add from Artifactory: Novell.Directory.Ldap.NETStandard 3.6.0

public class LdapOptions {
    public string Host { get; set; } = "";
    public int Port { get; set; } = 389;
    public string BaseDn { get; set; } = "";
    public string BindDn { get; set; } = "";
    public string BindPassword { get; set; } = ""; // from Key Vault
}
// Program.cs: builder.Services.Configure<LdapOptions>(config.GetSection("Ldap"));

// Old
var entry = new DirectoryEntry("LDAP://yourorg.com", user, pass);
var searcher = new DirectorySearcher(entry);
searcher.Filter = $"(sAMAccountName={username})";
var result = searcher.FindOne();

// New
using var conn = new LdapConnection();
await conn.ConnectAsync(_opts.Host, _opts.Port);
await conn.BindAsync(_opts.BindDn, _opts.BindPassword);
var results = conn.Search(_opts.BaseDn, LdapConnection.ScopeSub,
    $"(sAMAccountName={username})", null, false);
```

## Apigee / External HTTP (hasApigee)
```csharp
// Remove: RestSharp, WebClient, HttpWebRequest
// Replace with typed HttpClient:

public class ApigeeClient(HttpClient http) : IApigeeClient {
    public async Task<List<Product>> GetProductsAsync(CancellationToken ct = default)
        => await http.GetFromJsonAsync<List<Product>>("/products", ct) ?? [];
    public async Task<T?> PostAsync<T>(string path, object body, CancellationToken ct = default) {
        var resp = await http.PostAsJsonAsync(path, body, ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<T>(ct);
    }
}

// Program.cs
builder.Services.AddHttpClient<IApigeeClient, ApigeeClient>(c => {
    c.BaseAddress = new Uri(config["Apigee:BaseUrl"]!);
    c.DefaultRequestHeaders.Add("x-api-key", config["Apigee:ApiKey"]); // Key Vault
    c.Timeout = TimeSpan.FromSeconds(30);
});
```

## Ping / OIDC (hasPingFederate)
```csharp
// PREREQUISITE: from identity team → Key Vault:
// Ping:Authority (discovery URL), Ping:ClientId, Ping:ClientSecret

// Remove: FormsAuthentication.SetAuthCookie, FormsAuthentication.SignOut

// Program.cs
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
        o.GetClaimsFromUserInfoEndpoint = true;
    });

app.UseAuthentication();
app.UseAuthorization();

// Replace calls:
// FormsAuthentication.SetAuthCookie(user, false) → return Challenge(OpenIdConnectDefaults.AuthenticationScheme);
// FormsAuthentication.SignOut() →
//   await HttpContext.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
//   await HttpContext.SignOutAsync(OpenIdConnectDefaults.AuthenticationScheme);
```

## Redis (hasRedis)
```csharp
// Program.cs
builder.Services.AddStackExchangeRedisCache(o =>
    o.Configuration = config.GetConnectionString("Redis"));

// Service injection: IDistributedCache cache
public async Task SetAsync<T>(string key, T value, TimeSpan expiry, CancellationToken ct) {
    await _cache.SetStringAsync(key, JsonSerializer.Serialize(value),
        new DistributedCacheEntryOptions { AbsoluteExpirationRelativeToNow = expiry }, ct);
}
public async Task<T?> GetAsync<T>(string key, CancellationToken ct) {
    var json = await _cache.GetStringAsync(key, ct);
    return json is null ? default : JsonSerializer.Deserialize<T>(json);
}
// For pub/sub only: inject IConnectionMultiplexer directly
```

## Venafi (hasVenafi)
```csharp
// IF deploying to Kubernetes / OpenShift:
//   Remove all Venafi SDK calls
//   Insert: // TODO-MIGRATION: cert rotation handled by cert-manager (Venafi issuer)
//   App reads cert from K8s mounted secret — zero SDK needed

// IF on-prem IIS:
public class VenafiClient(HttpClient http) : IVenafiClient {
    public async Task<string> RequestCertAsync(string cn, CancellationToken ct = default) {
        var resp = await http.PostAsJsonAsync("/vedsdk/certificates/request",
            new { PolicyDN = _opts.PolicyDN, Subject = cn }, ct);
        resp.EnsureSuccessStatusCode();
        var result = await resp.Content.ReadFromJsonAsync<VenafiResult>(ct);
        return result!.CertificateDN;
    }
}
// Program.cs: builder.Services.AddHttpClient<IVenafiClient, VenafiClient>(c => {
//     c.BaseAddress = new Uri(config["Venafi:BaseUrl"]!);
//     c.DefaultRequestHeaders.Add("X-Venafi-Api-Key", config["Venafi:ApiKey"]); // Key Vault
// });
```

## WCF Client (hasWCF)
```csharp
// External clients need WSDL preserved?
//   YES → Add CoreWCF.Http from Artifactory. Keep service contract interfaces.
//   NO  → Replace proxy with typed HttpClient (same pattern as Apigee above)

// CoreWCF path (Program.cs):
builder.Services.AddServiceModelServices();
app.UseServiceModel(sb => {
    sb.AddService<CustomerService>();
    sb.AddServiceEndpoint<CustomerService, ICustomerService>(
        new BasicHttpBinding(), "/CustomerService.svc");
});
```

## Map update
✅ DONE | [PROJECT] | [filepath] | [hash] | agent-enterprise-integrations | — |
