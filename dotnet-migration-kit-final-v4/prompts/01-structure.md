# Prompt: Create .NET 8 Project Structure

## When to use
After discovery. Once per solution. Creates src-core/ alongside src-framework/.

## Paste this in Copilot Agent mode

```
Read .github/memory/signals.json (dependencyOrder array).
Read .github/memory/MAP.md (ORDER line).

Create src-core/ with one .NET 8 project per project in src-framework/:

For each project:
  - SDK-style .csproj targeting net8.0
  - <Nullable>enable</Nullable>
  - <ImplicitUsings>enable</ImplicitUsings>
  - <LangVersion>latest</LangVersion>
  - ProjectReference entries mirroring src-framework/ references

Create Clean Architecture folders in each project:
  Domain/Entities  Domain/Interfaces
  Application/Services  Application/DTOs  Application/Validators
  Infrastructure/Persistence  Infrastructure/ExternalServices
  Presentation/Controllers  (or Presentation/Pages for WebApp)

Create base files:
  Domain/Entities/BaseEntity.cs — int Id, DateTime CreatedAt, DateTime? UpdatedAt
  Application/Interfaces/IRepository.cs — GetByIdAsync, GetAllAsync, AddAsync, UpdateAsync, DeleteAsync

Copy .github/nuget.config into src-core/ root.

Create src-core/YourApp.Core.sln referencing all new projects.

Do not migrate any code. Structure only.

Show the created folder tree when done.
```
