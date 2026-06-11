# Agent: Clean Architecture Scaffolder

## Identity
Creates Clean Architecture folder structure in src-core/ before any migration.
Run once. Never needs to re-run.

## Pre-work
Check: does src-core/[Project]/Domain/ exist? If yes → skip entirely.

## Structure to create per project
```
src-core/[Project].Core/
├── Domain/
│   ├── Entities/        ← BaseEntity.cs
│   ├── Interfaces/      ← IRepository<T>.cs
│   ├── ValueObjects/
│   └── Exceptions/      ← NotFoundException.cs, ValidationException.cs
├── Application/
│   ├── Services/        ← business logic implementations
│   ├── Interfaces/      ← IService contracts
│   ├── DTOs/            ← request/response models
│   ├── Validators/      ← FluentValidation rules
│   └── Mappings/        ← AutoMapper profiles
├── Infrastructure/
│   ├── Persistence/
│   │   ├── AppDbContext.cs
│   │   ├── Repositories/
│   │   └── Migrations/
│   └── ExternalServices/ ← typed HttpClients, LDAP, Redis
└── Presentation/
    ├── Controllers/       ← API controllers
    ├── Pages/             ← Razor Pages
    └── Middleware/
```

## Base files to generate

### Domain/Entities/BaseEntity.cs
```csharp
namespace [Project].Domain.Entities;
public abstract class BaseEntity {
    public int Id { get; protected set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? UpdatedAt { get; set; }
}
```

### Domain/Interfaces/IRepository.cs
```csharp
namespace [Project].Domain.Interfaces;
public interface IRepository<T> where T : BaseEntity {
    Task<T?> GetByIdAsync(int id, CancellationToken ct = default);
    Task<IReadOnlyList<T>> GetAllAsync(CancellationToken ct = default);
    Task<T> AddAsync(T entity, CancellationToken ct = default);
    Task UpdateAsync(T entity, CancellationToken ct = default);
    Task DeleteAsync(int id, CancellationToken ct = default);
}
```

### Domain/Exceptions/
```csharp
// NotFoundException.cs
namespace [Project].Domain.Exceptions;
public sealed class NotFoundException(string message) : Exception(message);

// ValidationException.cs
public sealed class ValidationException(string message) : Exception(message);
```

## Dependency rule (enforced by project references)
```
Presentation → Application → Domain
Infrastructure implements Application interfaces
Nothing references Infrastructure directly except Presentation/Program.cs
```

## Mapping: where existing classes go
| Old class type | New location |
|---|---|
| Business logic service | Application/Services/ |
| Service interface | Application/Interfaces/ |
| Repository | Infrastructure/Persistence/Repositories/ |
| DbContext / EF models | Infrastructure/Persistence/ |
| Domain entity / model | Domain/Entities/ |
| DTO / request model | Application/DTOs/ |
| Controller | Presentation/Controllers/ |
| Razor Page | Presentation/Pages/ |
| HTTP client (Apigee etc.) | Infrastructure/ExternalServices/ |
| Middleware | Presentation/Middleware/ |
