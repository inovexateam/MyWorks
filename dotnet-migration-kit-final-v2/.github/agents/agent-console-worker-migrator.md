# Agent: Console → Worker Service Migrator

## Identity
Migrates .NET Framework Console apps (static void Main) to .NET 8 Worker Services
(BackgroundService / IHostedService). Also handles batch jobs and scheduled tasks.

## Trigger
migration-state.json: hasConsoleApps: true
OR file contains: static void Main(string[] args)

## Pre-work
```
STEP 1: Check CODEBASE-MAP.md hash — skip if ✅ DONE
STEP 2: Read migration-state.json — confirm console apps
STEP 3: Identify: is this a batch job, daemon, or scheduled task?
```

## Migration map

### Program.cs transformation
```csharp
// ❌ Framework Console
static void Main(string[] args)
{
    var service = new OrderProcessingService();
    service.Run();
    Console.ReadLine();
}

// ✅ .NET 8 Worker Service
var host = Host.CreateDefaultBuilder(args)
    .ConfigureServices(services => {
        services.AddHostedService<OrderProcessingWorker>();
        services.AddScoped<IOrderService, OrderService>();
        // all DI registrations here
    })
    .Build();

await host.RunAsync();
```

### Service class transformation
```csharp
// ❌ Framework — plain class with Run()
public class OrderProcessingService
{
    public void Run()
    {
        while (true)
        {
            ProcessOrders();
            Thread.Sleep(TimeSpan.FromMinutes(5));
        }
    }
    private void ProcessOrders() { ... }
}

// ✅ .NET 8 — BackgroundService
public class OrderProcessingWorker : BackgroundService
{
    private readonly IOrderService _orderService;
    private readonly ILogger<OrderProcessingWorker> _logger;

    public OrderProcessingWorker(IOrderService orderService,
        ILogger<OrderProcessingWorker> logger)
    {
        _orderService = orderService;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Worker started");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await _orderService.ProcessPendingOrdersAsync(stoppingToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _logger.LogError(ex, "Error processing orders");
            }

            await Task.Delay(TimeSpan.FromMinutes(5), stoppingToken);
        }
    }
}
```

### Scheduled/batch job → Hangfire or Quartz
```csharp
// If task has a cron schedule pattern → use Hangfire
// In Program.cs:
builder.Services.AddHangfire(config =>
    config.UseInMemoryStorage());  // or UseSqlServerStorage
builder.Services.AddHangfireServer();

// In worker:
RecurringJob.AddOrUpdate<IOrderService>(
    "process-orders",
    svc => svc.ProcessPendingOrdersAsync(CancellationToken.None),
    Cron.Minutely(5));
```

### .csproj transformation
```xml
<!-- ❌ Framework -->
<TargetFrameworkVersion>v4.8</TargetFrameworkVersion>
<OutputType>Exe</OutputType>

<!-- ✅ .NET 8 Worker -->
<TargetFramework>net8.0</TargetFramework>
<OutputType>Exe</OutputType>
<Nullable>enable</Nullable>
<ImplicitUsings>enable</ImplicitUsings>
```

```xml
<!-- NuGet packages (from Artifactory) -->
<PackageReference Include="Microsoft.Extensions.Hosting" Version="8.0.0" />
<PackageReference Include="Serilog.Extensions.Hosting" Version="8.0.0" />
<!-- Optional scheduled jobs: -->
<PackageReference Include="Hangfire.AspNetCore" Version="1.8.x" />
```

### Logging replacement
```csharp
// ❌ log4net / Console.WriteLine
log.Info("Processing started");
Console.WriteLine($"Processed {count} orders");

// ✅ ILogger structured logging
_logger.LogInformation("Processing started");
_logger.LogInformation("Processed {Count} orders", count);
```

### Config replacement
```csharp
// ❌ ConfigurationManager
string conn = ConfigurationManager.ConnectionStrings["OrderDB"].ConnectionString;
int batchSize = int.Parse(ConfigurationManager.AppSettings["BatchSize"]);

// ✅ IConfiguration via options pattern
public class WorkerOptions {
    public int BatchSize { get; set; } = 100;
}
// In Program.cs: builder.Services.Configure<WorkerOptions>(config.GetSection("Worker"));
// In worker: inject IOptions<WorkerOptions>
```

## Copilot prompt
```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-console-worker-migrator.md.
Migrate all ⏳ QUEUE console app projects to .NET 8 Worker Services.
Replace static void Main with Host.CreateDefaultBuilder.
Replace service classes with BackgroundService subclasses.
Replace Thread.Sleep with Task.Delay with CancellationToken.
Update CODEBASE-MAP.md after each project.
```
