# Agent: Web API 2 → ASP.NET Core 8 Migrator

## Identity
Migrates ASP.NET Web API 2 controllers and config to ASP.NET Core 8.
Activated when signals.json hasWebAPI2 = true.

## Pre-work
Hash check. ✅ match → skip.

## Controller migration
```csharp
// Old
using System.Web.Http;
[RoutePrefix("api/products")]
public class ProductsController : ApiController {
    [HttpGet, Route("")]
    public IHttpActionResult GetAll() => Ok(_service.GetAll());

    [HttpGet, Route("{id:int}")]
    public IHttpActionResult GetById(int id) {
        var p = _service.GetById(id);
        return p == null ? (IHttpActionResult)NotFound() : Ok(p);
    }

    [HttpPost, Route("")]
    public IHttpActionResult Create(ProductDto dto) {
        if (!ModelState.IsValid) return BadRequest(ModelState);
        var created = _service.Create(dto);
        return Created($"api/products/{created.Id}", created);
    }
}

// New
using Microsoft.AspNetCore.Mvc;
[ApiController]
[Route("api/[controller]")]
public class ProductsController(IProductService service) : ControllerBase {
    [HttpGet]
    public async Task<ActionResult<IReadOnlyList<ProductDto>>> GetAll(CancellationToken ct)
        => Ok(await service.GetAllAsync(ct));

    [HttpGet("{id:int}")]
    public async Task<ActionResult<ProductDto>> GetById(int id, CancellationToken ct)
        => await service.GetByIdAsync(id, ct) is { } p ? Ok(p) : NotFound();

    [HttpPost]
    public async Task<ActionResult<ProductDto>> Create(CreateProductDto dto, CancellationToken ct) {
        var created = await service.CreateAsync(dto, ct);
        return CreatedAtAction(nameof(GetById), new { id = created.Id }, created);
    }
}
```

## Return type map
```
IHttpActionResult           → ActionResult<T>
Ok(value)                   → Ok(value)
NotFound()                  → NotFound()
BadRequest(ModelState)      → ValidationProblem()
Created(uri, value)         → CreatedAtAction(nameof(Get), new { id }, value)
InternalServerError(ex)     → Problem(ex.Message)
ResponseMessage(response)   → new ObjectResult(value) { StatusCode = n }
```

## WebApiConfig → Program.cs
```csharp
// Remove: WebApiConfig.cs and Global.asax WebApiConfig.Register(config)
// Add to Program.cs:
builder.Services.AddControllers()
    .AddJsonOptions(o => o.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase);
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

app.UseSwagger();
app.UseSwaggerUI();
app.UseHttpsRedirection();
app.UseAuthorization();
app.MapControllers();
```

## DelegatingHandler → Middleware
```csharp
// Old
public class LoggingHandler : DelegatingHandler {
    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage req, CancellationToken ct) {
        _logger.LogInformation("Request: {Method} {Uri}", req.Method, req.RequestUri);
        var response = await base.SendAsync(req, ct);
        return response;
    }
}

// New
public class LoggingMiddleware(RequestDelegate next, ILogger<LoggingMiddleware> logger) {
    public async Task InvokeAsync(HttpContext ctx) {
        logger.LogInformation("{Method} {Path}", ctx.Request.Method, ctx.Request.Path);
        await next(ctx);
        logger.LogInformation("Response {Status}", ctx.Response.StatusCode);
    }
}
// Register: app.UseMiddleware<LoggingMiddleware>();
```

## ExceptionFilterAttribute → UseExceptionHandler
```csharp
// Remove ExceptionFilterAttribute subclasses
// Add to Program.cs:
app.UseExceptionHandler(e => e.Run(async ctx => {
    var ex = ctx.Features.Get<IExceptionHandlerFeature>()?.Error;
    ctx.Response.StatusCode = ex switch {
        KeyNotFoundException => 404,
        UnauthorizedAccessException => 403,
        _ => 500
    };
    await ctx.Response.WriteAsJsonAsync(new { error = ex?.Message });
}));
```

## Map update
✅ DONE | [PROJECT] | [filepath] | [hash] | agent-webapi2 | — |
