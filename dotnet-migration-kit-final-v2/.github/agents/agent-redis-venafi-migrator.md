# Agent: Redis / Venafi Migrator

## Identity
Migrates legacy Redis clients and Venafi certificate management to
.NET 8 patterns. Token-first: hash check before loading any file.

## Trigger
migration-state.json: hasRedis: true OR hasVenafi: true

## Redis migration

### Package
```xml
<!-- Already Core-compatible — usually no change needed -->
<PackageReference Include="StackExchange.Redis" Version="2.7.x" />
<!-- For IDistributedCache abstraction (preferred): -->
<PackageReference Include="Microsoft.Extensions.Caching.StackExchangeRedis" Version="8.0.0" />
```

### Pattern A — IDistributedCache (preferred for portability)
```csharp
// Program.cs
builder.Services.AddStackExchangeRedisCache(options => {
    options.Configuration = builder.Configuration.GetConnectionString("Redis");
    options.InstanceName = "YourApp:";
});

// Service — inject IDistributedCache
public class ProductCacheService(IDistributedCache cache)
{
    public async Task<Product?> GetAsync(int id, CancellationToken ct = default)
    {
        var key = $"product:{id}";
        var cached = await cache.GetStringAsync(key, ct);
        if (cached is not null)
            return JsonSerializer.Deserialize<Product>(cached);

        var product = await _repo.GetByIdAsync(id, ct);
        if (product is not null)
            await cache.SetStringAsync(key,
                JsonSerializer.Serialize(product),
                new DistributedCacheEntryOptions {
                    AbsoluteExpirationRelativeToNow = TimeSpan.FromHours(1)
                }, ct);
        return product;
    }
}
```

### Pattern B — Direct StackExchange.Redis (if pub/sub or Lua scripts needed)
```csharp
// Program.cs
builder.Services.AddSingleton<IConnectionMultiplexer>(
    ConnectionMultiplexer.Connect(builder.Configuration.GetConnectionString("Redis")!));

// Service
public class PubSubService(IConnectionMultiplexer redis)
{
    private readonly ISubscriber _sub = redis.GetSubscriber();
    public async Task PublishAsync(string channel, string message)
        => await _sub.PublishAsync(RedisChannel.Literal(channel), message);
}
```

### ❌ Legacy patterns to remove
```csharp
// Static ServiceStack.Redis or old StackExchange patterns
using ServiceStack.Redis;
var client = new RedisClient("localhost");  // → DI pattern above

// Synchronous .Wait() on Redis calls
cache.StringGet("key").ToString()  // → await cache.GetStringAsync("key")
```

## Venafi migration

### What Venafi does
Manages TLS certificates. In Framework apps: direct SDK or REST calls.
In .NET 8 / Kubernetes: certificates become Kubernetes secrets or
OpenShift cert-manager managed — Venafi integration moves to platform level.

### Pattern A — Kubernetes/OpenShift (recommended)
```
App no longer calls Venafi directly.
Certificate rotation handled by cert-manager + Venafi issuer.
App reads cert from mounted Kubernetes secret or certificate store.

// Remove: VenafiClient SDK calls from application code
// Add: Read cert from environment / mounted file
```

```csharp
// Program.cs — read cert from K8s mounted secret
builder.WebHost.ConfigureKestrel(options => {
    var certPath = builder.Configuration["Tls:CertPath"];    // mounted by K8s
    var keyPath  = builder.Configuration["Tls:KeyPath"];
    if (certPath is not null && keyPath is not null)
        options.ConfigureHttpsDefaults(h =>
            h.ServerCertificate = X509Certificate2.CreateFromPemFile(certPath, keyPath));
});
```

### Pattern B — Venafi REST API (if app must request certs)
```csharp
// Typed HttpClient for Venafi TPP REST API
public class VenafiClient(HttpClient http, IConfiguration config) : IVenafiClient
{
    public async Task<string> RequestCertificateAsync(
        string commonName, CancellationToken ct = default)
    {
        var payload = new { PolicyDN = config["Venafi:PolicyDN"], Subject = commonName };
        var resp = await http.PostAsJsonAsync("/vedsdk/certificates/request", payload, ct);
        resp.EnsureSuccessStatusCode();
        var result = await resp.Content.ReadFromJsonAsync<VenafiRequestResult>(ct);
        return result!.CertificateDN;
    }
}

// Program.cs
builder.Services.AddHttpClient<IVenafiClient, VenafiClient>(c => {
    c.BaseAddress = new Uri(config["Venafi:BaseUrl"]!);
    c.DefaultRequestHeaders.Add("X-Venafi-Api-Key",
        config["Venafi:ApiKey"]);  // from Key Vault
});
```

## Copilot prompt
```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-redis-venafi-migrator.md.
Check migration-state.json for hasRedis and hasVenafi flags.
For Redis: replace legacy clients with IDistributedCache + StackExchange.Redis.
For Venafi: assess if app calls Venafi directly — if deploying to OpenShift/K8s,
remove direct calls and note that cert-manager handles rotation. Otherwise
migrate to typed HttpClient. Update CODEBASE-MAP.md after each file.
```
