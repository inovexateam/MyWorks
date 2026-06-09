# Prompt: Web API 2 → ASP.NET Core 8

## When to use
signals.json: hasWebAPI2 = true.

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md.
For each ⏳ QUEUE file containing ApiController or System.Web.Http — hash check first.

── CONTROLLER ───────────────────────────────────────────────────────────

Remove: using System.Web.Http
Add:    using Microsoft.AspNetCore.Mvc

Class declaration:
  OLD: [RoutePrefix("api/products")] public class ProductsController : ApiController
  NEW: [ApiController] [Route("api/[controller]")] public class ProductsController : ControllerBase

Return types:
  IHttpActionResult → ActionResult<T>
  Ok(value)         → Ok(value)           (same)
  NotFound()        → NotFound()          (same)
  BadRequest(ModelState) → ValidationProblem()
  Created(uri,val)  → CreatedAtAction(nameof(GetById), new { id = created.Id }, created)
  InternalServerError(ex) → Problem(ex.Message)

Action methods:
  Add async, Task<ActionResult<T>>, CancellationToken ct to all actions.
  [Authorize] attribute stays — no namespace change needed.

── WEBAPI CONFIG → PROGRAM.CS ───────────────────────────────────────────

Remove: WebApiConfig.cs, Global.asax WebApiConfig.Register(config)

Add to Program.cs:
  builder.Services.AddControllers().AddJsonOptions(o =>
    o.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase);
  builder.Services.AddEndpointsApiExplorer();
  builder.Services.AddSwaggerGen();

  app.UseSwagger(); app.UseSwaggerUI();
  app.UseHttpsRedirection();
  app.UseAuthorization();
  app.MapControllers();

── DELEGATINGHANDLER → MIDDLEWARE ────────────────────────────────────────

OLD: public class LoggingHandler : DelegatingHandler { protected override async Task<HttpResponseMessage> SendAsync(...) }

NEW: public class LoggingMiddleware(RequestDelegate next, ILogger<LoggingMiddleware> logger) {
       public async Task InvokeAsync(HttpContext ctx) {
         logger.LogInformation("{Method} {Path}", ctx.Request.Method, ctx.Request.Path);
         await next(ctx);
         logger.LogInformation("Response {Status}", ctx.Response.StatusCode);
       }
     }
     Register: app.UseMiddleware<LoggingMiddleware>();

── EXCEPTION FILTER → EXCEPTION HANDLER ─────────────────────────────────

Remove ExceptionFilterAttribute subclasses.
Add to Program.cs:
  app.UseExceptionHandler(e => e.Run(async ctx => {
    var ex = ctx.Features.Get<IExceptionHandlerFeature>()?.Error;
    ctx.Response.StatusCode = ex switch {
      KeyNotFoundException => 404, UnauthorizedAccessException => 403, _ => 500 };
    await ctx.Response.WriteAsJsonAsync(new { error = ex?.Message });
  }));

Update MAP.md after each file.
Run: dotnet build src-core/[Project].Core/ — 0 errors required.
```
