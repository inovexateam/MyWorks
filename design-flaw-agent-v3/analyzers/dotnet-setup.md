# .NET / C# — Design-Focused Analyzer Setup

## 1. Add analyzer packages (run in each project, or add to Directory.Build.props)

```xml
<!-- Directory.Build.props at repo root -->
<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers" Version="9.0.0" PrivateAssets="all" />
    <PackageReference Include="Meziantou.Analyzer" Version="2.0.*" PrivateAssets="all" />
    <PackageReference Include="AsyncFixer" Version="1.6.0" PrivateAssets="all" />
    <PackageReference Include="Roslynator.Analyzers" Version="4.*" PrivateAssets="all" />
  </ItemGroup>
  <PropertyGroup>
    <AnalysisLevel>latest</AnalysisLevel>
    <AnalysisMode>AllEnabledByDefault</AnalysisMode>
    <EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
  </PropertyGroup>
</Project>
```

## 2. Key design-relevant rules to enforce (add to `.editorconfig`)

```ini
# .editorconfig — design-relevant rules (excerpt)

# CA2007: Do not directly await a Task without ConfigureAwait
dotnet_diagnostic.CA2007.severity = warning

# CA1063 / CA1816: Implement IDisposable correctly
dotnet_diagnostic.CA1063.severity = warning
dotnet_diagnostic.CA1816.severity = warning

# CA2000: Dispose objects before losing scope
dotnet_diagnostic.CA2000.severity = warning

# CA1031: Do not catch general exception types
dotnet_diagnostic.CA1031.severity = warning

# CA1062: Validate arguments of public methods (DIP/contract boundary)
dotnet_diagnostic.CA1062.severity = suggestion

# AsyncFixer: blocking on async code (.Result, .Wait())
dotnet_diagnostic.AsyncFixer01.severity = error
dotnet_diagnostic.AsyncFixer02.severity = error

# CA1812: Avoid uninstantiated internal classes (dead abstractions)
dotnet_diagnostic.CA1812.severity = suggestion

# CA1822: Mark members as static (hints at missing instance dependency = poor DI)
dotnet_diagnostic.CA1822.severity = suggestion
```

## 3. Architecture tests with ArchUnitNET (enforce layering + dependency direction)

```bash
dotnet add package ArchUnitNET.xUnit
```

```csharp
// Tests/ArchitectureTests.cs
using ArchUnitNET.Domain;
using ArchUnitNET.Loader;
using ArchUnitNET.xUnit;
using static ArchUnitNET.Fluent.ArchRuleDefinition;

public class ArchitectureTests
{
    private static readonly Architecture Architecture =
        new ArchLoader().LoadAssemblies(typeof(Program).Assembly).Build();

    [Fact]
    public void Domain_Should_Not_Depend_On_Infrastructure()
    {
        IArchRule rule = Types().That().ResideInNamespace("MyApp.Domain.*")
            .Should().NotDependOnAny(
                Types().That().ResideInNamespace("MyApp.Infrastructure.*"));

        rule.Check(Architecture);
    }

    [Fact]
    public void Controllers_Should_Not_Access_DbContext_Directly()
    {
        IArchRule rule = Types().That().ResideInNamespace("MyApp.Api.Controllers.*")
            .Should().NotDependOnAny(
                Types().That().HaveNameEndingWith("DbContext"));

        rule.Check(Architecture);
    }

    [Fact]
    public void Services_Should_Depend_On_Interfaces_Not_Concrete_Repositories()
    {
        IArchRule rule = Types().That().ResideInNamespace("MyApp.Application.Services.*")
            .Should().NotDependOnAny(
                Types().That().HaveNameEndingWith("Repository")
                    .And().AreNotInterfaces());

        rule.Check(Architecture);
    }
}
```

## 4. EF Core N+1 / tracking checks

Add `EFCorePerformance` analyzer or rely on `CA1827`/`CA1829` plus a runtime
check in dev: enable `Microsoft.EntityFrameworkCore.Diagnostics` logging for
`Microsoft.EntityFrameworkCore.Database.Command` at `Information` level in
`appsettings.Development.json` to spot repeated identical queries (N+1
signature).
