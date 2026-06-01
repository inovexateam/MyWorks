# Hook: Post-Merge

## Identity
Fires after every `git merge` completes. Runs heavier validation that's too slow for pre-commit, ensuring the merged codebase is stable and migration progress is up to date.

---

## Trigger
```bash
# .git/hooks/post-merge
```

## Execution Sequence

### Step 1: Full Test Suite
```bash
echo "🧪 Running full test suite post-merge..."
dotnet test --configuration Release --logger "trx;LogFileName=post-merge-results.trx"
```

### Step 2: Migration Progress Sync
```bash
# Recalculate migration checklist completion percentage
echo "📊 Updating migration progress metrics..."
dotnet run --project tools/MigrationTracker -- --update-metrics
```

### Step 3: Dependency Drift Check
```bash
# Verify packages.lock.json matches after merge
echo "📦 Verifying package lock integrity..."
dotnet restore --locked-mode
if [ $? -ne 0 ]; then
  echo "⚠️  Package lock mismatch detected after merge"
  echo "   Run: dotnet restore --use-lock-file"
  echo "   Then commit the updated packages.lock.json"
fi
```

### Step 4: Agent Notification
```bash
# Notify agents of merge completion so they can pick up new work
echo "📢 Notifying agents of merge completion..."
# This triggers agent orchestration to re-evaluate pending tasks
```

---

# Hook: CI Build

## Identity
The CI pipeline definition. Runs on every push to any branch, and must pass before any PR can be merged to `main`.

---

## GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: Migration CI Pipeline

on:
  push:
    branches: [ "**" ]
  pull_request:
    branches: [ main, develop ]

env:
  DOTNET_VERSION: '8.0.x'
  DOTNET_SKIP_FIRST_TIME_EXPERIENCE: true
  DOTNET_CLI_TELEMETRY_OPTOUT: true

jobs:
  # ─────────────────────────────────────────────
  # Job 1: Build & Unit Tests
  # ─────────────────────────────────────────────
  build-and-unit-test:
    name: Build & Unit Tests
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for migration tracking
      
      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}
      
      - name: Restore (locked mode)
        run: dotnet restore --locked-mode
      
      - name: Build
        run: dotnet build --no-restore --configuration Release
      
      - name: Unit Tests
        run: |
          dotnet test --no-build --configuration Release \
            --filter "Category!=Integration&Category!=E2E&Category!=Performance" \
            --collect:"XPlat Code Coverage" \
            --results-directory ./TestResults \
            --logger "trx;LogFileName=unit-tests.trx"
      
      - name: Publish Test Results
        uses: dorny/test-reporter@v1
        if: always()
        with:
          name: Unit Test Results
          path: TestResults/*.trx
          reporter: dotnet-trx
      
      - name: Upload Coverage
        uses: codecov/codecov-action@v4
        with:
          files: TestResults/**/coverage.cobertura.xml

  # ─────────────────────────────────────────────
  # Job 2: Security Scanning
  # ─────────────────────────────────────────────
  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - name: Secret Detection (TruffleHog)
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD
          extra_args: --only-verified
      
      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}
      
      - name: Vulnerable Package Check
        run: |
          dotnet list package --vulnerable --include-transitive 2>&1 | tee vuln-report.txt
          if grep -q "has the following vulnerable packages" vuln-report.txt; then
            echo "::error::Vulnerable packages found. See vuln-report.txt"
            exit 1
          fi
      
      - name: OWASP Dependency Check
        uses: dependency-check/Dependency-Check_Action@main
        with:
          project: 'YourApp'
          path: '.'
          format: 'HTML'
          out: 'dependency-check-report'
          args: >
            --failOnCVSS 7
            --enableRetired
      
      - name: Upload Security Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: security-reports
          path: |
            vuln-report.txt
            dependency-check-report/

  # ─────────────────────────────────────────────
  # Job 3: Code Quality
  # ─────────────────────────────────────────────
  code-quality:
    name: Code Quality
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}
      
      - name: Check Code Format
        run: dotnet format --verify-no-changes --no-restore
      
      - name: Framework Dependency Check
        run: |
          echo "Checking for System.Web references in Core projects..."
          VIOLATIONS=$(find . -name "*.cs" \
            -not -path "*/Legacy/*" \
            -not -path "*/obj/*" \
            -not -path "*/.git/*" \
            | xargs grep -l "using System\.Web" 2>/dev/null || true)
          
          if [ -n "$VIOLATIONS" ]; then
            echo "::error::System.Web references found in Core projects:"
            echo "$VIOLATIONS"
            exit 1
          fi
          echo "✅ No Framework dependencies found in Core projects"
      
      - name: SonarCloud Analysis
        uses: SonarSource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}

  # ─────────────────────────────────────────────
  # Job 4: Integration Tests (PR to main only)
  # ─────────────────────────────────────────────
  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request' && github.base_ref == 'main'
    
    services:
      sqlserver:
        image: mcr.microsoft.com/mssql/server:2022-latest
        env:
          ACCEPT_EULA: Y
          SA_PASSWORD: TestPassword123!
        ports:
          - 1433:1433
        options: >-
          --health-cmd "/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P TestPassword123! -Q 'SELECT 1'"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: ${{ env.DOTNET_VERSION }}
      
      - name: Run EF Core Migrations
        run: |
          dotnet ef database update \
            --project src/DAC/DAC.csproj \
            --startup-project src/WebApp/WebApp.csproj \
            --connection "Server=localhost;Database=TestDb;User Id=sa;Password=TestPassword123!;TrustServerCertificate=True"
      
      - name: Integration Tests
        run: |
          dotnet test tests/IntegrationTests/ \
            --configuration Release \
            --logger "trx;LogFileName=integration-tests.trx" \
            --results-directory ./TestResults
        env:
          ConnectionStrings__DefaultConnection: "Server=localhost;Database=TestDb;User Id=sa;Password=TestPassword123!;TrustServerCertificate=True"
  
  # ─────────────────────────────────────────────
  # Job 5: Migration Progress Report
  # ─────────────────────────────────────────────
  migration-progress:
    name: Migration Progress
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Calculate Migration Metrics
        run: |
          # Count remaining .aspx files
          ASPX_COUNT=$(find . -name "*.aspx" | wc -l)
          # Count System.Web references
          SYSWEB_COUNT=$(grep -r "using System\.Web" --include="*.cs" | wc -l)
          # Count TODO migration comments
          TODO_COUNT=$(grep -r "TODO.*[Mm]igrat" --include="*.cs" | wc -l)
          
          echo "## Migration Progress Report" >> $GITHUB_STEP_SUMMARY
          echo "| Metric | Count |" >> $GITHUB_STEP_SUMMARY
          echo "|--------|-------|" >> $GITHUB_STEP_SUMMARY
          echo "| Remaining .aspx files | $ASPX_COUNT |" >> $GITHUB_STEP_SUMMARY
          echo "| System.Web references | $SYSWEB_COUNT |" >> $GITHUB_STEP_SUMMARY
          echo "| Migration TODOs | $TODO_COUNT |" >> $GITHUB_STEP_SUMMARY
```
