# Agent: Clean Architecture Scaffolder

## Identity
Creates Clean Architecture folder structure in src-core/ before migration
begins. Sets up layers so every migrating agent drops code into the right
place from the start. Run once after P1 project structure, before any P2 work.

## Trigger
Invoked at end of Phase 1 (project structure created).
OR manually: when org requires Clean Architecture layout.

## Token rule
Check if src-core/[Project]/Domain/ already exists → if yes, skip entirely.
This agent runs once and never needs to re-run.

---

## Clean Architecture layers

```
src-core/
└── [ProjectName].Core/
    ├── Domain/                    ← Entities, value objects, domain events
    │   ├── Entities/
    │   ├── ValueObjects/
    │   ├── Events/
    │   └── Exceptions/
    ├── Application/               ← Use cases, interfaces, DTOs
    │   ├── Interfaces/            ← IRepository, IService contracts
    │   ├── Services/              ← Business logic implementations
    │   ├── DTOs/                  ← Request/response models
    │   ├── Validators/            ← FluentValidation rules
    │   └── Mappings/              ← AutoMapper profiles
    ├── Infrastructure/            ← DB, external services, implementations
    │   ├── Persistence/
    │   │   ├── AppDbContext.cs
    │   │   ├── Repositories/
    │   │   └── Migrations/
    │   ├── ExternalServices/      ← Apigee, WCF clients, typed HttpClients
    │   └── Identity/              ← Auth implementations
    └── Presentation/              ← Controllers, Razor Pages, Endpoints
        ├── Controllers/
        ├── Pages/
        └── Middleware/
```

## Dependency rule
```
Presentation → Application → Domain
Infrastructure → Application (implements interfaces)
Domain has ZERO dependencies
Application depends only on Domain
Nothing depends on Infrastructure directly
```

## Scaffolding prompt
```
Read .github/agents/agent-clean-arch-scaffolder.md.
Create Clean Architecture folder structure in src-core/ for each project.
Add a .gitkeep in each folder so structure is committed.
Create base interfaces in Application/Interfaces/:
  IRepository<T> with GetByIdAsync, GetAllAsync, AddAsync, UpdateAsync, DeleteAsync
  IUnitOfWork with SaveChangesAsync
Create base entity in Domain/Entities/:
  BaseEntity with Id (int), CreatedAt, UpdatedAt
Do not create any business-specific classes — structure only.
```

## Mapping existing code to layers

When migrating existing classes, agents place them as:

| Existing Framework class | Clean Arch layer | Folder |
|---|---|---|
| Business logic service | Application | Application/Services/ |
| Interface / contract | Application | Application/Interfaces/ |
| Repository | Infrastructure | Infrastructure/Persistence/Repositories/ |
| DbContext / EF models | Infrastructure | Infrastructure/Persistence/ |
| Entity / domain model | Domain | Domain/Entities/ |
| DTO / request model | Application | Application/DTOs/ |
| Controller / Page | Presentation | Presentation/Controllers or Pages/ |
| HTTP client (Apigee) | Infrastructure | Infrastructure/ExternalServices/ |
| Middleware | Presentation | Presentation/Middleware/ |
| Validator | Application | Application/Validators/ |

## Base interfaces (created by scaffolder)
```csharp
// Application/Interfaces/IRepository.cs
namespace YourApp.Application.Interfaces;

public interface IRepository<T> where T : BaseEntity
{
    Task<T?> GetByIdAsync(int id, CancellationToken ct = default);
    Task<IReadOnlyList<T>> GetAllAsync(CancellationToken ct = default);
    Task<T> AddAsync(T entity, CancellationToken ct = default);
    Task UpdateAsync(T entity, CancellationToken ct = default);
    Task DeleteAsync(int id, CancellationToken ct = default);
}

// Domain/Entities/BaseEntity.cs
namespace YourApp.Domain.Entities;

public abstract class BaseEntity
{
    public int Id { get; protected set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? UpdatedAt { get; set; }
}
```
