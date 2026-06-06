# Rules: Coding Standards

## Scope
These rules apply to ALL code produced during the migration. Every agent enforces these. They load automatically when any `.cs` file is being modified.

---

## .NET 8 Code Standards

### Naming Conventions
```csharp
// Classes, interfaces, methods, properties: PascalCase
public class OrderService : IOrderService { }
public interface IOrderService { }
public Task<Order> GetOrderAsync(int orderId) { }
public string OrderNumber { get; set; }

// Local variables, parameters: camelCase
var orderNumber = "ORD-001";
public Task ProcessAsync(Order order, CancellationToken cancellationToken)

// Private fields: _camelCase (underscore prefix)
private readonly IOrderRepository _orderRepository;
private readonly ILogger<OrderService> _logger;

// Constants: PascalCase
public const int MaxRetryCount = 3;
private const string DefaultCurrency = "USD";

// Async methods MUST end in Async
public async Task<Order> GetOrderAsync() { }  // ✅
public async Task<Order> GetOrder() { }       // ❌ VIOLATION
```

### File Organization
```csharp
// Standard file structure (in this order):
namespace MyApp.Services;  // File-scoped namespace (C# 10+)

// 1. Using directives (sorted: System, then alphabetical)
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using MyApp.Core.Interfaces;
using MyApp.Core.Models;

// 2. Class declaration
public sealed class OrderService : IOrderService {
    // 3. Constants
    private const int MaxRetries = 3;
    
    // 4. Private fields
    private readonly IOrderRepository _orderRepository;
    private readonly ILogger<OrderService> _logger;
    
    // 5. Constructor(s)
    public OrderService(IOrderRepository orderRepository, ILogger<OrderService> logger) {
        _orderRepository = orderRepository ?? throw new ArgumentNullException(nameof(orderRepository));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
    
    // 6. Public interface implementation (alphabetical)
    // 7. Private methods (alphabetical)
}
```

### Modern C# Features (Required for Migration)
```csharp
// ✅ File-scoped namespaces (eliminates indentation level)
namespace MyApp.Services;

// ✅ Record types for DTOs and value objects
public record CreateOrderRequest(string CustomerId, IReadOnlyList<OrderItem> Items);
public record OrderSummary(int Id, string Status, decimal Total);

// ✅ Primary constructors (C# 12)
public class OrderService(IOrderRepository repo, ILogger<OrderService> logger) 
    : IOrderService {
    // repo and logger available as fields automatically
}

// ✅ Null coalescing and null safety
var name = customer?.Name ?? "Unknown";
ArgumentNullException.ThrowIfNull(order);

// ✅ Pattern matching
string GetDiscount(Customer customer) => customer switch {
    { IsPremium: true, YearsActive: > 5 } => "20%",
    { IsPremium: true } => "10%",
    { YearsActive: > 3 } => "5%",
    _ => "0%"
};

// ✅ Collection expressions (C# 12)
int[] numbers = [1, 2, 3, 4, 5];
List<string> names = [.. existingNames, "Alice", "Bob"];

// ✅ Nullable reference types (ENABLED project-wide)
// In .csproj: <Nullable>enable</Nullable>
// All types are non-nullable by default
// Use ? for intentionally nullable: string? middleName
```

### Async Rules (Non-Negotiable)
```csharp
// ✅ ALWAYS use CancellationToken in public async methods
public async Task<Order> GetOrderAsync(int id, CancellationToken ct = default)

// ✅ ALWAYS use ConfigureAwait(false) in library code (BC, BPC, DAC, SAC)
var order = await _repo.GetByIdAsync(id, ct).ConfigureAwait(false);

// ✅ NEVER use .Result or .Wait() 
var order = await GetOrderAsync(id);  // ✅
var order = GetOrderAsync(id).Result; // ❌ DEADLOCK RISK

// ✅ Use Task.WhenAll for parallel operations
var (orders, customers) = await Task.WhenAll(
    GetOrdersAsync(ct),
    GetCustomersAsync(ct));

// ✅ Return Task, not void (except event handlers)
public async Task ProcessAsync() { }    // ✅
public async void ProcessAsync() { }    // ❌ (exceptions swallowed)
```

### Dependency Injection Rules
```csharp
// ✅ Inject interfaces, not concrete types
public class OrderService(IOrderRepository repo) { } // ✅
public class OrderService(OrderRepository repo) { }  // ❌

// ✅ Lifetime rules:
// Singleton: stateless services, caches, configuration wrappers
// Scoped: database contexts, request-scoped services  
// Transient: lightweight, stateless, frequently created

// ✅ Register all services in Program.cs (not constructors)
builder.Services.AddScoped<IOrderService, OrderService>();
builder.Services.AddScoped<IOrderRepository, OrderRepository>();

// ❌ Never new() a service that has dependencies
var service = new OrderService(new OrderRepository()); // ❌
```

### Exception Handling
```csharp
// ✅ Throw specific exceptions
throw new ArgumentNullException(nameof(order));
throw new InvalidOperationException($"Order {id} is already completed");
throw new NotFoundException($"Order {id} not found"); // Custom exception

// ✅ Log + rethrow (don't swallow)
try {
    await _repo.SaveAsync(order, ct);
} catch (DbUpdateException ex) {
    _logger.LogError(ex, "Failed to save order {OrderId}", order.Id);
    throw; // rethrow — don't swallow
}

// ❌ Never catch Exception without purpose
catch (Exception ex) { } // ❌ swallowed — never do this

// ✅ Custom domain exceptions
public sealed class NotFoundException : Exception {
    public NotFoundException(string message) : base(message) { }
}
```

---

## EditorConfig (`.editorconfig` — commit this file)
```ini
root = true

[*.cs]
indent_style = space
indent_size = 4
end_of_line = crlf
charset = utf-8-bom
trim_trailing_whitespace = true
insert_final_newline = true

# Naming rules
dotnet_naming_rule.private_fields.symbols = private_field_symbols
dotnet_naming_rule.private_fields.style = underscore_camel_case
dotnet_naming_symbols.private_field_symbols.applicable_kinds = field
dotnet_naming_symbols.private_field_symbols.applicable_accessibilities = private
dotnet_naming_style.underscore_camel_case.capitalization = camel_case
dotnet_naming_style.underscore_camel_case.required_prefix = _

# Modern C#
csharp_style_namespace_declarations = file_scoped:error
csharp_prefer_simple_using_statement = true:suggestion
csharp_style_expression_bodied_methods = when_on_single_line:suggestion

[*.{csproj,props,targets}]
indent_size = 2
```
