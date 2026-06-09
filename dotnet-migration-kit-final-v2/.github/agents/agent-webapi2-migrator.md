# Agent: Web API 2 → ASP.NET Core 8 Migrator

## Identity
Migrates ASP.NET Web API 2 (ApiController, System.Web.Http) to ASP.NET Core 8
controllers (ControllerBase, Microsoft.AspNetCore.Mvc). Token-first: check
CODEBASE-MAP.md hash before loading any file.

## Trigger
Files containing: ApiController, System.Web.Http, WebApiConfig, RoutePrefix
OR migration-state.json shows hasWebAPI2: true

## Pre-work
```
STEP 1: Check CODEBASE-MAP.md — skip ✅ DONE files (hash match)
STEP 2: Read migration-state.json — confirm Web API 2 presence
STEP 3: Load file only if hash differs or not in map
```

---

## Migration map

### .csproj
```xml
<!-- ❌ Framework -->
<TargetFrameworkVersion>v4.8</TargetFrameworkVersion>
<Reference Include="System.Web.Http" />
<Reference Include="System.Web.Http.WebHost" />
<Reference Include="Newtonsoft.Json" Version="6.x" />

<!-- ✅ .NET 8 -->
<TargetFramework>net8.0</TargetFramework>
<Nullable>enable</Nullable>
<ImplicitUsings>enable</ImplicitUsings>
<PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="8.0.0" />
<PackageReference Include="Swashbuckle.AspNetCore" Version="6.x" />
```

### Controller class
```csharp
// ❌ Web API 2
using System.Web.Http;

[RoutePrefix("api/products")]
public class ProductsController : ApiController
{
    [HttpGet]
    [Route("")]
    public IHttpActionResult GetAll()
    {
        var products = _service.GetAll();
        return Ok(products);
    }

    [HttpGet]
    [Route("{id:int}")]
    public IHttpActionResult GetById(int id)
    {
        var p = _service.GetById(id);
        if (p == null) return NotFound();
        return Ok(p);
    }

    [HttpPost]
    [Route("")]
    public IHttpActionResult Create(ProductDto dto)
    {
        if (!ModelState.IsValid) return BadRequest(ModelState);
        var created = _service.Create(dto);
        return Created($"api/products/{created.Id}", created);
    }
}

// ✅ ASP.NET Core 8
using Microsoft.AspNetCore.Mvc;

[ApiController]
[Route("api/[controller]")]
public class ProductsController : ControllerBase
{
    private readonly IProductService _service;

    public ProductsController(IProductService service)
        => _service = service;

    [HttpGet]
    public async Task<ActionResult<IReadOnlyList<ProductDto>>> GetAll(
        CancellationToken ct)
        => Ok(await _service.GetAllAsync(ct));

    [HttpGet("{id:int}")]
    public async Task<ActionResult<ProductDto>> GetById(int id, CancellationToken ct)
    {
        var p = await _service.GetByIdAsync(id, ct);
        return p is null ? NotFound() : Ok(p);
    }

    [HttpPost]
    public async Task<ActionResult<ProductDto>> Create(
        CreateProductDto dto, CancellationToken ct)
    {
        var created = await _service.CreateAsync(dto, ct);
        return CreatedAtAction(nameof(GetById), new { id = created.Id }, created);
    }
}
```

### Startup / WebApiConfig → Program.cs
```csharp
// ❌ Framework — WebApiConfig.Register()
public static class WebApiConfig
{
    public static void Register(HttpConfiguration config)
    {
        config.MapHttpAttributeRoutes();
        config.Routes.MapHttpRoute("DefaultApi",
            "api/{controller}/{id}",
            new { id = RouteParameter.Optional });

        config.Formatters.JsonFormatter.SerializerSettings.ContractResolver
            = new CamelCasePropertyNamesContractResolver();
    }
}

// ✅ .NET 8 — Program.cs
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers()
    .AddJsonOptions(o =>
        o.JsonSerializerOptions.PropertyNamingPolicy =
            JsonNamingPolicy.CamelCase);

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// Register services (replaces Unity/Ninject from Global.asax)
builder.Services.AddScoped<IProductService, ProductService>();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();
app.UseAuthorization();
app.MapControllers();
app.Run();
```

### Return type changes
```
IHttpActionResult        → ActionResult<T> or IActionResult
Ok(value)                → Ok(value)         ✅ same
NotFound()               → NotFound()        ✅ same
BadRequest(ModelState)   → ValidationProblem() or BadRequest(ModelState)
Created(uri, value)      → CreatedAtAction(nameof(Get), new { id }, value)
InternalServerError(ex)  → Problem() or StatusCode(500)
ResponseMessage(...)     → new ObjectResult(...) { StatusCode = ... }
```

### HttpRequestMessage → HttpContext
```csharp
// ❌ Web API 2
public IHttpActionResult Get()
{
    var host = Request.RequestUri.Host;
    var header = Request.Headers.Authorization;
}

// ✅ Core — HttpContext available directly in ControllerBase
public IActionResult Get()
{
    var host = Request.Host.Value;
    var header = Request.Headers.Authorization;
}
```

### DelegatingHandler → Middleware
```csharp
// ❌ Web API 2 — DelegatingHandler
public class LoggingHandler : DelegatingHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken ct)
    {
        _logger.LogInformation("Request: {Method} {Uri}", request.Method, request.RequestUri);
        var response = await base.SendAsync(request, ct);
        _logger.LogInformation("Response: {Status}", response.StatusCode);
        return response;
    }
}

// ✅ Core — Middleware
public class LoggingMiddleware(RequestDelegate next, ILogger<LoggingMiddleware> logger)
{
    public async Task InvokeAsync(HttpContext context)
    {
        logger.LogInformation("Request: {Method} {Path}",
            context.Request.Method, context.Request.Path);
        await next(context);
        logger.LogInformation("Response: {Status}", context.Response.StatusCode);
    }
}
// Register: app.UseMiddleware<LoggingMiddleware>();
```

### Authorization
```csharp
// ❌ Web API 2
[System.Web.Http.Authorize]
[System.Web.Http.Authorize(Roles = "Admin")]

// ✅ Core
[Microsoft.AspNetCore.Authorization.Authorize]
[Authorize(Roles = "Admin")]
[Authorize(Policy = "RequireAdmin")]
```

### Exception filters
```csharp
// ❌ Web API 2 ExceptionFilterAttribute
public class ApiExceptionFilter : ExceptionFilterAttribute
{
    public override void OnException(HttpActionExecutedContext ctx)
    {
        ctx.Response = ctx.Request.CreateErrorResponse(
            HttpStatusCode.InternalServerError, ctx.Exception.Message);
    }
}

// ✅ Core — UseExceptionHandler in Program.cs
app.UseExceptionHandler(appError => {
    appError.Run(async context => {
        var feature = context.Features.Get<IExceptionHandlerFeature>();
        context.Response.StatusCode = feature?.Error switch {
            NotFoundException => 404,
            ValidationException => 400,
            _ => 500
        };
        await context.Response.WriteAsJsonAsync(
            new { error = feature?.Error?.Message });
    });
});
```

---

## Map update after completion
```
✅ DONE | WebApp | src/WebApp/Controllers/ProductsController.cs | [hash] | webapi2-migrator | [cov%] |
```

## Copilot prompt
```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-webapi2-migrator.md.
Migrate all ⏳ QUEUE Web API 2 controller files. Replace ApiController with
ControllerBase, IHttpActionResult with ActionResult<T>, WebApiConfig with
Program.cs registration, DelegatingHandlers with middleware.
Add async + CancellationToken to all action methods.
Update CODEBASE-MAP.md after each file.
```
