# Prompt: Console App → Worker Service

## When to use
signals.json: hasConsoleApps = true.

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md and .github/memory/signals.json.
For each ⏳ QUEUE project containing "static void Main" — hash check first.

── PROGRAM.CS ────────────────────────────────────────────────────────────

OLD: static void Main(string[] args) { var svc = new OrderService(); svc.Run(); }

NEW: var host = Host.CreateDefaultBuilder(args)
       .ConfigureServices((ctx, services) => {
         services.AddHostedService<OrderWorker>();
         services.AddScoped<IOrderService, OrderService>();
         services.Configure<WorkerOptions>(ctx.Configuration.GetSection("Worker"));
         // add all DI registrations here
       })
       .UseSerilog()
       .Build();
     await host.RunAsync();

── SERVICE CLASS → BACKGROUNDSERVICE ────────────────────────────────────

OLD: public class OrderService {
       public void Run() { while(true) { Process(); Thread.Sleep(60000); } }
       private void Process() { ... }
     }

NEW: public class OrderWorker(IOrderService svc, ILogger<OrderWorker> logger,
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

── CONFIGURATION ─────────────────────────────────────────────────────────

OLD: ConfigurationManager.AppSettings["BatchSize"]
NEW: public class WorkerOptions { public int BatchSize { get; set; } = 100;
                                   public int IntervalSeconds { get; set; } = 60; }
     Inject: IOptions<WorkerOptions> options

── LOGGING ───────────────────────────────────────────────────────────────

OLD: Console.WriteLine($"Processed {count}"); log.Info("Done");
NEW: logger.LogInformation("Processed {Count} records", count);

── .CSPROJ ───────────────────────────────────────────────────────────────

OLD: <TargetFrameworkVersion>v4.8</TargetFrameworkVersion> <OutputType>Exe</OutputType>
NEW: <TargetFramework>net8.0</TargetFramework> <OutputType>Exe</OutputType>
     <Nullable>enable</Nullable> <ImplicitUsings>enable</ImplicitUsings>
Add: <PackageReference Include="Microsoft.Extensions.Hosting" Version="8.0.0" />
     <PackageReference Include="Serilog.Extensions.Hosting" Version="8.0.0" />

── SCHEDULED JOBS ────────────────────────────────────────────────────────

If the original used a timer/scheduler pattern → Hangfire:
  Add: <PackageReference Include="Hangfire.AspNetCore" Version="1.8.x" />
  In Program.cs: services.AddHangfire(c => c.UseInMemoryStorage());
                 services.AddHangfireServer();
  In worker: RecurringJob.AddOrUpdate<IOrderService>("process",
               s => s.ProcessAsync(CancellationToken.None), Cron.Minutely(5));

Update MAP.md after each project:
  ✅ DONE | [PROJECT] | Program.cs | [hash] | console-worker | — |
Run: dotnet build src-core/[Project].Core/ — 0 errors.
```
