# Prompt: Update Dependencies

## Purpose
Used by `agent-dependency-resolver` and Copilot users to update a project's package references from Framework to Core-compatible equivalents.

---

## The Prompt

```
You are a .NET dependency migration specialist. Analyze the following 
packages.config or .csproj and produce a complete, updated .csproj 
with PackageReference entries using Core-compatible packages.

[PASTE packages.config OR .csproj CONTENT HERE]

Perform these steps:

STEP 1: INVENTORY
List every package found with:
  - Current version
  - .NET Core / .NET 8 support status (✅ Supported | ⚠️ Partial | 🔄 Replaced | ❌ Unsupported)
  - Core equivalent (if different package)
  - Latest stable version for Core

STEP 2: MAP REPLACEMENTS
For each package, specify the exact replacement:
  - Entity Framework 6.x → Microsoft.EntityFrameworkCore 8.x + SqlServer provider
  - log4net → Serilog.AspNetCore (or keep via adapter: log4net.AspNetCore)
  - Unity → Remove (use built-in DI)
  - Autofac → Autofac.Extensions.DependencyInjection
  - RestSharp < 107 → RestSharp 110+ or HttpClient (built-in)
  [Apply full mapping table from skill/dependency-mapping.md]

STEP 3: IDENTIFY BLOCKERS
List any packages with NO Core equivalent.
For each: explain the impact and provide 2-3 resolution options.

STEP 4: PRODUCE UPDATED .csproj
Write the complete updated .csproj in SDK style:

<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <LangVersion>latest</LangVersion>
  </PropertyGroup>
  
  <ItemGroup>
    <!-- All PackageReference entries here -->
  </ItemGroup>
  
  <ItemGroup>
    <!-- Project references here -->
  </ItemGroup>
</Project>

STEP 5: PRODUCE Directory.Packages.props ENTRY
For each new package, provide the line to add to central package management:
<PackageVersion Include="[PackageId]" Version="[Version]" />

STEP 6: PROGRAM.CS REGISTRATION
For any packages that need DI registration (e.g., Autofac, Serilog), 
provide the exact Program.cs code needed:
builder.Services.AddXxx(...)
builder.Host.UseSerilog(...)
etc.
```

---

# Prompt: Run Tests

## Purpose
Instructions for `agent-test-runner` and developers to execute the test suite and interpret results.

---

## The Prompt

```
You are a .NET test automation expert. Execute and analyze the test suite 
for the following migrated component.

CONTEXT:
  Component: [name]
  Recent changes: [describe what was just migrated]
  Known test gaps: [any areas without tests]

STEP 1: DETERMINE TEST SCOPE
Based on what was changed, determine which test projects to run:
  - Always: unit tests for the changed project
  - If data access changed: integration tests
  - If endpoint/page changed: API/page integration tests
  - If auth changed: security tests
  - If critical path: feature parity tests

STEP 2: EXECUTE TESTS
Run the following commands (provide exact output):

dotnet test [TestProject] \
  --configuration Release \
  --logger "console;verbosity=normal" \
  --collect:"XPlat Code Coverage"

STEP 3: ANALYZE RESULTS
For each failure:
  a) Show the full test name
  b) Show the failure message and stack trace
  c) Classify the failure:
     - REGRESSION: Was passing before migration → code-refactor bug
     - NEW FAILURE: Test written for Core that doesn't work yet → implementation gap
     - FLAKY: Sometimes passes → isolation issue
     - ENVIRONMENT: Setup/teardown issue → not a code bug
  d) Recommend fix and which agent to escalate to

STEP 4: COVERAGE ANALYSIS
Report coverage for changed namespaces:
  - Which classes have < 60% coverage?
  - Which critical methods have no tests at all?
  - Propose 3-5 highest-value new tests to write

STEP 5: VERDICT
  ✅ PASS: All tests pass, coverage meets minimum
  ⚠️ WARN: Tests pass but coverage low — flag for improvement
  ❌ FAIL: Test failures found — provide escalation message for responsible agent
```

---

# Prompt: Analyze Page

## Purpose
Quick-analysis prompt for any .aspx page before migration begins.

---

## The Prompt

```
Analyze this ASP.NET WebForms page and produce a complete migration brief.

[PASTE .aspx + .aspx.cs CONTENT]

Produce:
1. MIGRATION COMPLEXITY: [1-Simple | 2-Medium | 3-Complex | 4-Very Complex]
   Justify the score.

2. CONTROLS INVENTORY (table):
   | Control Type | ID | Purpose | Core Equivalent | Effort |

3. CODE-BEHIND ANALYSIS:
   | Method | Lines | Purpose | Core Equivalent | Async Required? |

4. DEPENDENCIES:
   | Service/Repo Called | Framework API Used | Migrated Yet? |

5. STATE MANAGEMENT:
   | Mechanism | Data Stored | Core Equivalent |

6. ESTIMATED EFFORT: [hours]
   Breakdown:
   - .cshtml markup: [X]h
   - PageModel: [X]h
   - Service method changes: [X]h
   - Tests: [X]h

7. RECOMMENDED AGENT:
   Primary: [agent name]
   Support: [agent names]
   
8. PREREQUISITES:
   List everything that must be done BEFORE this page can be migrated
   (e.g., services must be migrated, packages resolved, etc.)

9. RISKS:
   List anything unusual or complex about this page that could cause problems
```

---

# Prompt: Decompose Class

## Purpose
Used by `agent-complexity-decomposer` when a class is too large to migrate safely.

---

## The Prompt

```
This class has too many responsibilities to migrate safely as a single unit.
Analyze it and produce a decomposition plan.

[PASTE LARGE CLASS CONTENT]

STEP 1: RESPONSIBILITY MAPPING
Read every method. Group methods by their SINGLE core responsibility.
For each group:
  - Name the group (this becomes the new class name)
  - List the methods in the group  
  - State the single responsibility in one sentence
  - List what this class would depend on

STEP 2: DEPENDENCY GRAPH
Draw the dependency relationships between the proposed classes.
Are there any circular dependencies? How to resolve?

STEP 3: INTERFACE DESIGN
For each proposed class, write its interface:
  - Interface name: I[ClassName]
  - Only public methods (no internal helpers)
  - All methods async where they do I/O
  - CancellationToken on all async methods

STEP 4: EXTRACTION ORDER
In what order should classes be extracted?
Rule: Extract leaves first (no dependencies on other extracted classes)

STEP 5: BACKWARD COMPATIBILITY FACADE
Write a facade class that:
  - Has the EXACT same public interface as the original class
  - Delegates every call to the new extracted services
  - Is marked [Obsolete("Use I[X], I[Y] directly")]
  - Allows existing callers to keep working during transition

STEP 6: DI REGISTRATIONS
Provide the Program.cs service registrations for all new classes:
  builder.Services.AddScoped<I[X], [X]>();
  builder.Services.AddScoped<I[Y], [Y]>();

STEP 7: EFFORT ESTIMATE
| New Class | LOC | Hours | Tests Needed |
```
