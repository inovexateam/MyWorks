# Workflow: Migration CI Pipeline

## File Location
`.github/workflows/migration-ci.yml`

---

```yaml
name: .NET Migration CI Pipeline

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

jobs:
  # ─────────────────────────────────────────────────────
  # JOB 1: Detect what changed (smart CI — skip if unchanged)
  # ─────────────────────────────────────────────────────
  changes:
    name: Detect Changes
    runs-on: ubuntu-latest
    outputs:
      src: ${{ steps.filter.outputs.src }}
      tests: ${{ steps.filter.outputs.tests }}
      csproj: ${{ steps.filter.outputs.csproj }}
      docker: ${{ steps.filter.outputs.docker }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            src:
              - 'src/**/*.cs'
              - 'src/**/*.csproj'
            tests:
              - 'tests/**'
            csproj:
              - '**/*.csproj'
              - 'Directory.Packages.props'
            docker:
              - 'Dockerfile'
              - '.dockerignore'

  # ─────────────────────────────────────────────────────
  # JOB 2: Build & Code Quality
  # ─────────────────────────────────────────────────────
  build:
    name: Build & Code Quality
    runs-on: ubuntu-latest
    needs: changes
    if: needs.changes.outputs.src == 'true' || needs.changes.outputs.csproj == 'true'

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup .NET ${{ env.DOTNET_VERSION }}
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}

      - name: Cache NuGet packages
        uses: actions/cache@v4
        with:
          path: ~/.nuget/packages
          key: nuget-${{ hashFiles('**/packages.lock.json') }}
          restore-keys: nuget-

      - name: Restore (locked mode — enforces package integrity)
        run: dotnet restore --locked-mode

      - name: Build (Release)
        run: |
          dotnet build \
            --no-restore \
            --configuration Release \
            -warnaserror \
            /p:TreatWarningsAsErrors=false

      - name: Verify no System.Web in migrated projects
        run: |
          echo "Scanning for Framework dependencies in Core projects..."
          
          VIOLATIONS=$(find src/ -name "*.cs" \
            -not -path "*/obj/*" \
            -not -path "*/Legacy/*" \
            | xargs grep -l "using System\.Web" 2>/dev/null || true)
          
          if [ -n "$VIOLATIONS" ]; then
            echo "::error title=Framework Dependencies Found::System.Web references found:"
            echo "$VIOLATIONS" | while read f; do
              echo "::error file=$f::Remove System.Web reference - use Core equivalents"
            done
            exit 1
          fi
          echo "✅ No Framework dependencies found"

      - name: Check code format
        run: dotnet format --verify-no-changes --no-restore

      - name: Count migration progress
        run: |
          ASPX=$(find . -name "*.aspx" -not -path "*/obj/*" | wc -l)
          SYSWEB=$(grep -r "using System\.Web" src/ --include="*.cs" 2>/dev/null | wc -l)
          EDMX=$(find . -name "*.edmx" -not -path "*/obj/*" | wc -l)
          
          echo "## 📊 Migration Metrics" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "| Metric | Count | Goal |" >> $GITHUB_STEP_SUMMARY
          echo "|--------|-------|------|" >> $GITHUB_STEP_SUMMARY
          echo "| Remaining .aspx pages | $ASPX | 0 |" >> $GITHUB_STEP_SUMMARY
          echo "| System.Web references | $SYSWEB | 0 |" >> $GITHUB_STEP_SUMMARY
          echo "| Remaining EDMX files | $EDMX | 0 |" >> $GITHUB_STEP_SUMMARY

  # ─────────────────────────────────────────────────────
  # JOB 3: Unit Tests
  # ─────────────────────────────────────────────────────
  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest
    needs: build

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}

      - name: Restore
        run: dotnet restore --locked-mode

      - name: Unit Tests with Coverage
        run: |
          dotnet test \
            --no-restore \
            --configuration Release \
            --filter "Category!=Integration&Category!=E2E&Category!=Performance&Category!=Security" \
            --collect:"XPlat Code Coverage" \
            --results-directory ./TestResults/Unit \
            --logger "trx;LogFileName=unit-results.trx" \
            -- DataCollectionRunSettings.DataCollectors.DataCollector.Configuration.Format=cobertura

      - name: Coverage Report
        uses: danielpalme/ReportGenerator-GitHub-Action@5
        with:
          reports: "TestResults/**/*.cobertura.xml"
          targetdir: "TestResults/CoverageReport"
          reporttypes: "HtmlInline;Cobertura;MarkdownSummaryGithub"

      - name: Coverage Summary
        run: cat TestResults/CoverageReport/SummaryGithub.md >> $GITHUB_STEP_SUMMARY

      - name: Publish Test Results
        uses: dorny/test-reporter@v1
        if: always()
        with:
          name: Unit Test Results
          path: TestResults/**/*.trx
          reporter: dotnet-trx

      - name: Enforce Coverage Minimums
        run: |
          # Parse coverage and fail if below 75%
          COVERAGE=$(grep -oP 'line-rate="\K[0-9.]+' TestResults/**/*.cobertura.xml | \
            awk '{sum+=$1; count++} END {print sum/count*100}')
          echo "Overall coverage: ${COVERAGE}%"
          
          MINIMUM=75
          if (( $(echo "$COVERAGE < $MINIMUM" | bc -l) )); then
            echo "::error::Coverage ${COVERAGE}% is below minimum ${MINIMUM}%"
            exit 1
          fi

  # ─────────────────────────────────────────────────────
  # JOB 4: Security Scanning
  # ─────────────────────────────────────────────────────
  security:
    name: Security Scan
    runs-on: ubuntu-latest
    needs: changes
    if: needs.changes.outputs.src == 'true' || needs.changes.outputs.csproj == 'true'

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for secret scanning

      - name: TruffleHog Secret Detection
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.pull_request.base.sha || github.event.before }}
          head: ${{ github.event.pull_request.head.sha || github.sha }}
          extra_args: --only-verified --fail

      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}

      - name: Restore
        run: dotnet restore --locked-mode

      - name: Check for Vulnerable Packages
        run: |
          OUTPUT=$(dotnet list package --vulnerable --include-transitive 2>&1)
          echo "$OUTPUT"
          
          if echo "$OUTPUT" | grep -q "has the following vulnerable packages"; then
            # Check for HIGH or CRITICAL
            if echo "$OUTPUT" | grep -qiE "(High|Critical)"; then
              echo "::error::HIGH or CRITICAL vulnerable packages found. Update immediately."
              echo "$OUTPUT" >> $GITHUB_STEP_SUMMARY
              exit 1
            else
              echo "::warning::Vulnerable packages found (MEDIUM/LOW severity). Review soon."
            fi
          fi

      - name: Upload Security Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: security-reports-${{ github.run_id }}
          path: |
            **/vuln-report.txt
          retention-days: 30

  # ─────────────────────────────────────────────────────
  # JOB 5: Integration Tests (PRs to main/develop only)
  # ─────────────────────────────────────────────────────
  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: [build, unit-tests]
    if: |
      github.event_name == 'pull_request' && 
      (github.base_ref == 'main' || github.base_ref == 'develop' || startsWith(github.base_ref, 'release/'))

    services:
      sqlserver:
        image: mcr.microsoft.com/mssql/server:2022-latest
        env:
          ACCEPT_EULA: "Y"
          MSSQL_SA_PASSWORD: "Test@Password123!"
          MSSQL_PID: "Developer"
        ports:
          - 1433:1433
        options: >-
          --health-cmd "/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P 'Test@Password123!' -Q 'SELECT 1' -b"
          --health-interval 15s
          --health-timeout 10s
          --health-retries 10
          --health-start-period 30s

    env:
      ConnectionStrings__DefaultConnection: "Server=localhost,1433;Database=TestDb_CI;User Id=sa;Password=Test@Password123!;TrustServerCertificate=True;MultipleActiveResultSets=True"

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}

      - name: Restore
        run: dotnet restore --locked-mode

      - name: Apply EF Core Migrations to Test DB
        run: |
          dotnet ef database update \
            --project src/DAC/DAC.csproj \
            --startup-project src/WebApp/WebApp.csproj \
            --no-build 2>/dev/null || \
          dotnet build --configuration Release && \
          dotnet ef database update \
            --project src/DAC/DAC.csproj \
            --startup-project src/WebApp/WebApp.csproj

      - name: Integration Tests
        run: |
          dotnet test tests/IntegrationTests/ \
            --configuration Release \
            --logger "trx;LogFileName=integration-results.trx" \
            --results-directory ./TestResults/Integration

      - name: Publish Integration Test Results
        uses: dorny/test-reporter@v1
        if: always()
        with:
          name: Integration Test Results
          path: TestResults/Integration/*.trx
          reporter: dotnet-trx

  # ─────────────────────────────────────────────────────
  # JOB 6: Docker Build Validation
  # ─────────────────────────────────────────────────────
  docker:
    name: Docker Build
    runs-on: ubuntu-latest
    needs: build
    if: needs.changes.outputs.docker == 'true' || github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker Image
        run: |
          docker build \
            --tag yourapp:ci-${{ github.sha }} \
            --file Dockerfile \
            --target final \
            .

      - name: Test Container Health
        run: |
          docker run -d \
            --name test-container \
            -p 8080:8080 \
            -e ASPNETCORE_ENVIRONMENT=Testing \
            yourapp:ci-${{ github.sha }}
          
          sleep 10
          
          # Health check
          curl --fail --retry 5 --retry-delay 2 \
            http://localhost:8080/health || \
          (docker logs test-container && exit 1)
          
          docker stop test-container

      - name: Scan Image for CVEs
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "yourapp:ci-${{ github.sha }}"
          format: "sarif"
          output: "trivy-results.sarif"
          severity: "CRITICAL,HIGH"
          exit-code: "1"

  # ─────────────────────────────────────────────────────
  # JOB 7: Migration Gate (PR to main — final check)
  # ─────────────────────────────────────────────────────
  migration-gate:
    name: Migration Quality Gate
    runs-on: ubuntu-latest
    needs: [build, unit-tests, security, integration-tests]
    if: |
      always() && 
      github.event_name == 'pull_request' && 
      github.base_ref == 'main'

    steps:
      - uses: actions/checkout@v4

      - name: Evaluate Gate
        run: |
          BUILD_STATUS="${{ needs.build.result }}"
          UNIT_STATUS="${{ needs.unit-tests.result }}"
          SECURITY_STATUS="${{ needs.security.result }}"
          INTEGRATION_STATUS="${{ needs.integration-tests.result }}"
          
          echo "## 🚦 Migration Quality Gate" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "| Check | Status |" >> $GITHUB_STEP_SUMMARY
          echo "|-------|--------|" >> $GITHUB_STEP_SUMMARY
          echo "| Build | $BUILD_STATUS |" >> $GITHUB_STEP_SUMMARY
          echo "| Unit Tests | $UNIT_STATUS |" >> $GITHUB_STEP_SUMMARY
          echo "| Security | $SECURITY_STATUS |" >> $GITHUB_STEP_SUMMARY
          echo "| Integration Tests | $INTEGRATION_STATUS |" >> $GITHUB_STEP_SUMMARY
          
          # Fail gate if any critical job failed
          if [[ "$BUILD_STATUS" == "failure" || 
                "$UNIT_STATUS" == "failure" || 
                "$SECURITY_STATUS" == "failure" || 
                "$INTEGRATION_STATUS" == "failure" ]]; then
            echo "" >> $GITHUB_STEP_SUMMARY
            echo "### ❌ GATE FAILED — PR cannot merge" >> $GITHUB_STEP_SUMMARY
            exit 1
          else
            echo "" >> $GITHUB_STEP_SUMMARY
            echo "### ✅ GATE PASSED — PR approved for merge" >> $GITHUB_STEP_SUMMARY
          fi
```
