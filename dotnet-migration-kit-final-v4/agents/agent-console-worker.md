# Agent: Console App → Worker Service Migrator

## Identity
Migrates .NET Framework console apps (static void Main) to .NET 8
BackgroundService / Worker Services. Activated when signals.json hasConsoleApps = true.

## Pre-work
Hash check. ✅ match → skip.
signals.json hasConsoleApps = false → stop.

## Program.cs transformation
```csharp
// Old
static void Main(string[] args) {
    var svc = new OrderProcessingService();
    svc.Run();
}

// New
var host = Host.CreateDefaultBuilder(args)
    .ConfigureServices((ctx, services) => {
        services.AddHostedService<OrderProcessingWorker>();
        services.AddScoped<IOrderService, OrderService>();
        services.Configure<WorkerOptions>(ctx.Configuration.GetSection("Worker"));
    })
    .UseSerilog()
    .Build();
await host.RunAsync();
```

## Service class → BackgroundService
```csharp
// Old
public class OrderProcessingService {
    public void Run() {
        while (true) { Process(); Thread.Sleep(60000); }
    }
    private void Process() { ... }
}

// New
public class OrderProcessingWorker(
    IOrderService svc,
    ILogger<OrderProcessingWorker> logger,
    IOptions<WorkerOptions> opts) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct) {
        logger.LogInformation("Worker started");
        while (!ct.IsCancellationRequested) {
            try { await svc.ProcessAsync(ct); }
            catch (Exception ex) when (ex is not OperationCanceledException)
            { logger.LogError(ex, "Processing failed"); }
            await Task.Delay(TimeSpan.FromSeconds(opts.Value.IntervalSeconds), ct);
        }
    }
}
```

## Configuration
```csharp
// Old: ConfigurationManager.AppSettings["BatchSize"]
// New: strongly-typed options
public class WorkerOptions {
    public int BatchSize { get; set; } = 100;
    public int IntervalSeconds { get; set; } = 60;
}
// Program.cs: services.Configure<WorkerOptions>(ctx.Configuration.GetSection("Worker"));
// appsettings.json: "Worker": { "BatchSize": 100, "IntervalSeconds": 60 }
```

## Scheduled/cron jobs → Hangfire
```csharp
// If original had timer-based scheduling:
// Program.cs
services.AddHangfire(c => c.UseSqlServerStorage(config.GetConnectionString("Hangfire")));
services.AddHangfireServer();
// In worker or startup:
RecurringJob.AddOrUpdate<IOrderService>(
    "process-orders",
    s => s.ProcessAsync(CancellationToken.None),
    Cron.Minutely(5));
```

## .csproj changes
```xml
<TargetFramework>net8.0</TargetFramework>
<OutputType>Exe</OutputType>
<Nullable>enable</Nullable>
<ImplicitUsings>enable</ImplicitUsings>
<!-- Add packages from Artifactory: -->
<PackageReference Include="Microsoft.Extensions.Hosting" Version="8.0.0" />
<PackageReference Include="Serilog.Extensions.Hosting" Version="8.0.0" />
<!-- If scheduled: -->
<PackageReference Include="Hangfire.AspNetCore" Version="1.8.x" />
```

## Map update
✅ DONE | [PROJECT] | Program.cs | [hash] | agent-console-worker | — |
