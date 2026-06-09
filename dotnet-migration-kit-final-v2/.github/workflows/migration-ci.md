# Workflow: Migration CI Pipeline (Artifactory-Only)
# File: .github/workflows/migration-ci.yml
# All tools: .NET SDK built-ins + packages from Artifactory NuGet feed only.
# No truffleHog, no SonarCloud, no Trivy, no external actions.

---

```yaml
name: .NET Migration CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: [main, develop, "release/**"]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  DOTNET_VERSION: "8.0.x"
  DOTNET_SKIP_FIRST_TIME_EXPERIENCE: true
  DOTNET_CLI_TELEMETRY_OPTOUT: true
  DOTNET_NOLOGO: true
  # Artifactory credentials — stored as GitHub secrets
  ARTIFACTORY_URL: ${{ secrets.ARTIFACTORY_URL }}
  ARTIFACTORY_USER: ${{ secrets.ARTIFACTORY_USER }}
  ARTIFACTORY_TOKEN: ${{ secrets.ARTIFACTORY_TOKEN }}

jobs:
  # ── JOB 1: Smart change detection — skip jobs if files unchanged ───────────
  changes:
    name: Detect Changes
    runs-on: [self-hosted]   # use org self-hosted runner with Artifactory access
    outputs:
      src: ${{ steps.filter.outputs.src }}
      csproj: ${{ steps.filter.outputs.csproj }}
    steps:
      - uses: actions/checkout@v4
      - id: filter
        run: |
          SRC=$(git diff --name-only origin/${{ github.base_ref || 'main' }}...HEAD \
            | grep -E '\.(cs|csproj)$' | wc -l)
          echo "src=$([ $SRC -gt 0 ] && echo 'true' || echo 'false')" >> $GITHUB_OUTPUT
          CSPROJ=$(git diff --name-only origin/${{ github.base_ref || 'main' }}...HEAD \
            | grep '\.csproj$' | wc -l)
          echo "csproj=$([ $CSPROJ -gt 0 ] && echo 'true' || echo 'false')" >> $GITHUB_OUTPUT

  # ── JOB 2: Build + Roslyn/Org Analyzers ────────────────────────────────────
  build:
    name: Build & Org Static Analysis
    runs-on: [self-hosted]
    needs: changes
    if: needs.changes.outputs.src == 'true'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}

      # Point NuGet at Artifactory — no nuget.org
      - name: Configure Artifactory NuGet source
        run: |
          dotnet nuget remove source nuget.org 2>/dev/null || true
          dotnet nuget add source "${{ env.ARTIFACTORY_URL }}/api/nuget/nuget-virtual" \
            --name Artifactory \
            --username "${{ env.ARTIFACTORY_USER }}" \
            --password "${{ env.ARTIFACTORY_TOKEN }}" \
            --store-password-in-clear-text

      - name: Restore (locked mode)
        run: dotnet restore --locked-mode

      # Build runs ALL Roslyn analyzers including:
      # - Microsoft.CodeAnalysis.NetAnalyzers (ships with SDK)
      # - SecurityCodeScan (from Artifactory NuGet feed, referenced in .csproj)
      # - Your org's custom Roslyn analyzer (from Artifactory NuGet feed)
      - name: Build + Org Static Analysis
        run: |
          dotnet build --no-restore --configuration Release 2>&1 | tee build-output.txt
          
          # Parse org rule violations (ORG-prefixed)
          ORG_VIOLATIONS=$(grep -E "^.*\.(cs)\([0-9].*: (error|warning) ORG[0-9]" build-output.txt || true)
          if [ -n "$ORG_VIOLATIONS" ]; then
            echo "::error::Org static analysis violations found:"
            echo "$ORG_VIOLATIONS"
            exit 1
          fi
          
          # Check build result
          grep -q "Build succeeded" build-output.txt || exit 1

      # CVE check — built into .NET SDK, no external tool
      - name: CVE Scan (dotnet built-in)
        if: needs.changes.outputs.csproj == 'true'
        run: |
          OUTPUT=$(dotnet list package --vulnerable --include-transitive 2>&1)
          echo "$OUTPUT"
          if echo "$OUTPUT" | grep -qiE "\b(High|Critical)\b"; then
            echo "::error::HIGH/CRITICAL CVE found — update packages immediately"
            exit 1
          fi

      # Secret detection — pure grep, zero external tool
      - name: Secret Detection (grep-based)
        run: |
          HITS=$(git diff origin/${{ github.base_ref || 'main' }}...HEAD -- '*.cs' '*.json' '*.config' \
            | grep "^+" \
            | grep -iv "^+++" \
            | grep -iE '(password\s*=\s*[^$<{"'"'"'][^;\n]{3,}|api[_-]?key\s*[:=]\s*[a-zA-Z0-9]{16,})' \
            | grep -iv '(//|#|todo|example|placeholder|your[_-]|changeme|<\w+>)' || true)
          if [ -n "$HITS" ]; then
            echo "::error::Potential secrets in diff:"
            echo "$HITS"
            exit 1
          fi
          echo "✅ No secrets detected"

      # Framework dep check
      - name: Framework Dependency Check
        run: |
          VIOLATIONS=$(find src/ -name "*.cs" -not -path "*/obj/*" -not -path "*/Legacy/*" \
            | xargs grep -l "using System\.Web" 2>/dev/null || true)
          if [ -n "$VIOLATIONS" ]; then
            echo "::error::System.Web in Core projects:"
            echo "$VIOLATIONS"
            exit 1
          fi

      # Migration progress metrics (goes to job summary — zero tokens)
      - name: Migration Progress
        if: always()
        run: |
          ASPX=$(find . -name "*.aspx" -not -path "*/obj/*" 2>/dev/null | wc -l)
          SYSWEB=$(grep -r "using System\.Web" src/ --include="*.cs" 2>/dev/null | wc -l)
          ASMX=$(find . -name "*.asmx" -not -path "*/obj/*" 2>/dev/null | wc -l)
          EDMX=$(find . -name "*.edmx" -not -path "*/obj/*" 2>/dev/null | wc -l)
          
          echo "| Metric | Count |" >> $GITHUB_STEP_SUMMARY
          echo "|--------|-------|" >> $GITHUB_STEP_SUMMARY
          echo "| .aspx pages remaining | $ASPX |" >> $GITHUB_STEP_SUMMARY
          echo "| System.Web references | $SYSWEB |" >> $GITHUB_STEP_SUMMARY
          echo "| ASMX services remaining | $ASMX |" >> $GITHUB_STEP_SUMMARY
          echo "| EDMX models remaining | $EDMX |" >> $GITHUB_STEP_SUMMARY

  # ── JOB 3: Unit Tests ───────────────────────────────────────────────────────
  unit-tests:
    name: Unit Tests
    runs-on: [self-hosted]
    needs: build
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with: { dotnet-version: "${{ env.DOTNET_VERSION }}" }

      - name: Configure Artifactory NuGet
        run: |
          dotnet nuget remove source nuget.org 2>/dev/null || true
          dotnet nuget add source "${{ env.ARTIFACTORY_URL }}/api/nuget/nuget-virtual" \
            --name Artifactory --username "${{ env.ARTIFACTORY_USER }}" \
            --password "${{ env.ARTIFACTORY_TOKEN }}" --store-password-in-clear-text

      - name: Restore
        run: dotnet restore --locked-mode

      - name: Unit Tests + Coverage
        run: |
          dotnet test \
            --no-restore --configuration Release \
            --filter "Category!=Integration&Category!=E2E&Category!=Performance" \
            --collect:"XPlat Code Coverage" \
            --results-directory ./TestResults \
            --logger "trx;LogFileName=unit-results.trx"

      - name: Enforce Coverage Minimum (75%)
        run: |
          XML=$(find TestResults -name "*.cobertura.xml" | head -1)
          if [ -z "$XML" ]; then echo "No coverage file found" && exit 1; fi
          RATE=$(grep -oP 'line-rate="\K[0-9.]+' "$XML" | head -1)
          PCT=$(echo "$RATE * 100" | bc)
          echo "Coverage: ${PCT}%"
          PASS=$(echo "$PCT >= 75" | bc)
          [ "$PASS" -ne 1 ] && echo "::error::Coverage ${PCT}% below 75%" && exit 1

  # ── JOB 4: Integration Tests (PRs to main only) ─────────────────────────────
  integration-tests:
    name: Integration Tests
    runs-on: [self-hosted]
    needs: unit-tests
    if: github.event_name == 'pull_request' && (github.base_ref == 'main' || startsWith(github.base_ref, 'release/'))
    services:
      sqlserver:
        image: mcr.microsoft.com/mssql/server:2022-latest
        env: { ACCEPT_EULA: "Y", MSSQL_SA_PASSWORD: "Test@123!" }
        ports: ["1433:1433"]
    env:
      ConnectionStrings__DefaultConnection: "Server=localhost,1433;Database=TestDb;User Id=sa;Password=Test@123!;TrustServerCertificate=True"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with: { dotnet-version: "${{ env.DOTNET_VERSION }}" }

      - name: Configure Artifactory NuGet
        run: |
          dotnet nuget remove source nuget.org 2>/dev/null || true
          dotnet nuget add source "${{ env.ARTIFACTORY_URL }}/api/nuget/nuget-virtual" \
            --name Artifactory --username "${{ env.ARTIFACTORY_USER }}" \
            --password "${{ env.ARTIFACTORY_TOKEN }}" --store-password-in-clear-text

      - name: Restore & Migrate DB
        run: |
          dotnet restore --locked-mode
          dotnet ef database update \
            --project src/DAC/DAC.csproj \
            --startup-project src/WebApp/WebApp.csproj

      - name: Integration Tests
        run: dotnet test tests/IntegrationTests/ --configuration Release

  # ── JOB 5: Final Gate ───────────────────────────────────────────────────────
  gate:
    name: Quality Gate
    runs-on: [self-hosted]
    needs: [build, unit-tests]
    if: always() && github.event_name == 'pull_request'
    steps:
      - name: Evaluate
        run: |
          B="${{ needs.build.result }}"
          T="${{ needs.unit-tests.result }}"
          [ "$B" = "failure" ] && echo "::error::Build failed" && exit 1
          [ "$T" = "failure" ] && echo "::error::Tests failed" && exit 1
          echo "✅ Quality gate passed"
```
