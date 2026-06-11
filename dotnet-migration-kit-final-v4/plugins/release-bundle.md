# Plugin: Release Bundle

## Identity
The release bundle is the final gate before any build reaches production. It is the most comprehensive plugin — it runs everything and signs off on the complete migration or a phase of it. Nothing deploys without this plugin completing successfully.

**Invoke with:** `/release-bundle [version] [environment]`
**Environments:** `staging` | `production`

---

## Pre-Conditions (Must ALL be true before this plugin starts)

```
☐ All phase checklist items for this release scope: 100% complete
☐ migration-bundle completed for all included projects
☐ security-bundle completed (pre-release mode): CLEARED
☐ All PRs for this release merged to release branch
☐ Release branch created: release/v[version]
☐ CHANGELOG.md updated with all migration changes
☐ Stakeholder sign-off documented
```

---

## Orchestration Script

```
PLUGIN: release-bundle
INPUT: version     = [semver, e.g. 1.0.0]
INPUT: environment = [staging | production]

─── STAGE 1: FINAL BUILD VERIFICATION ───────────────────────

STEP 1.1: Clean build
  dotnet clean
  dotnet restore --locked-mode
  dotnet build --configuration Release --no-restore
  GATE: 0 errors, 0 warnings (or all warnings in approved-warnings.txt)

STEP 1.2: Version stamping
  Verify AssemblyVersion, FileVersion, InformationalVersion in .csproj
  Verify appsettings.json has correct version references
  Tag git commit: v[version]

STEP 1.3: Framework dependency final check
  Scan ALL .cs files for System.Web references
  Scan ALL .csproj for net471 / net48 target frameworks
  GATE: Zero Framework references in any migrated project

─── STAGE 2: COMPLETE TEST SUITE ─────────────────────────────

STEP 2.1: Unit tests
  Read: agent-test-runner
  SCOPE: All unit test projects
  GATE: 100% pass, coverage ≥ minimums

STEP 2.2: Integration tests (against staging DB)
  Read: agent-test-runner
  SCOPE: All integration test projects
  DATABASE: staging replica (read-only snapshot for tests)
  GATE: 100% pass

STEP 2.3: Feature parity tests
  Read: agent-test-runner
  FILTER: Category=FeatureParity
  GATE: 100% pass — every feature of old app verified in new app

STEP 2.4: Performance tests
  Read: agent-test-runner
  FILTER: Category=Performance
  COMPARE: vs baseline captured in Phase 0
  GATE: No regression > 10% on any tracked metric
  REPORT: Performance comparison table

STEP 2.5: E2E tests (Playwright)
  RUN: dotnet test tests/E2ETests/
  AGAINST: Staging environment
  SCOPE: Critical user journeys (login, core workflows, checkout/submit)
  GATE: 100% pass on happy paths

─── STAGE 3: SECURITY FINAL GATE ─────────────────────────────

STEP 3.1: Full security bundle
  Read: security-bundle
  MODE: pre-release
  GATE: CLEARED status required
  NOTE: If security-bundle was run within 24 hours with no code changes,
        cached result is accepted

STEP 3.2: Penetration test checklist
  FOR environment=production:
    VERIFY: External pen test has been conducted (or waiver approved)
    VERIFY: All pen test findings resolved or accepted with risk sign-off

─── STAGE 4: DATABASE MIGRATION VALIDATION ───────────────────

STEP 4.1: Migration dry-run
  dotnet ef migrations script --idempotent \
    --output release-migration-v[version].sql
  REVIEW: Generated SQL — no DROP TABLE, no data loss operations
  GATE: Human DBA reviews and approves SQL script

STEP 4.2: Staging DB migration
  Apply migration to staging DB
  Run smoke tests against migrated staging DB
  GATE: All smoke tests pass on staging

STEP 4.3: Rollback plan
  VERIFY: Down migration script exists and tested
  VERIFY: DB backup taken immediately before production deploy
  DOCUMENT: Step-by-step rollback procedure

─── STAGE 5: DEPLOYMENT ARTIFACTS ────────────────────────────

STEP 5.1: Docker image build
  docker build -t yourapp:v[version] .
  docker run --rm yourapp:v[version] dotnet --info
  docker scout cves yourapp:v[version]  # Scan image for CVEs
  GATE: Image builds, runs, zero CRITICAL CVEs in base image

STEP 5.2: Health check validation
  Start container
  curl -f http://localhost/health → 200 OK
  curl -f http://localhost/health/ready → 200 OK
  GATE: Both health endpoints respond healthy

STEP 5.3: Configuration validation
  Run: dotnet run --environment Production --dry-run (if supported)
  OR: Start app, check startup logs for configuration errors
  GATE: No configuration exceptions on startup

STEP 5.4: Artifact publishing
  Push Docker image to registry: yourapp:v[version], yourapp:latest-staging
  Publish release notes to GitHub releases
  Archive test results and security reports

─── STAGE 6: STAGING SMOKE TEST ──────────────────────────────

STEP 6.1: Deploy to staging
  kubectl apply -f k8s/staging/ 
  OR: Deploy via CI/CD pipeline to staging

STEP 6.2: Staging validation
  Run smoke test suite against live staging:
    ✅ Application loads
    ✅ Login works
    ✅ Core business operation #1 works (define per app)
    ✅ Core business operation #2 works
    ✅ API health endpoint responds
    ✅ No 500 errors in logs for 5 minutes post-deploy
  GATE: All smoke tests pass

─── STAGE 7: PRODUCTION DEPLOYMENT (production only) ─────────

IF environment == staging: STOP HERE — release to staging complete

STEP 7.1: Pre-production checklist (human sign-off required)
  ☐ Staging smoke test: PASSED
  ☐ Security bundle: CLEARED
  ☐ DBA DB migration approval: SIGNED
  ☐ Rollback plan: DOCUMENTED AND TESTED
  ☐ Support team notified of deployment window
  ☐ Monitoring dashboards open
  ☐ On-call engineer confirmed available

STEP 7.2: Blue-green or canary deployment
  RECOMMENDED: Deploy to 10% of traffic first
  MONITOR: Error rate, response times for 15 minutes
  IF error rate increases > 2%: AUTO-ROLLBACK
  ELSE: Gradually increase to 100%

STEP 7.3: Post-deployment validation
  Monitor for 30 minutes:
    - Error rate < 0.1%
    - P95 response time within budget
    - No memory leak (heap steady)
    - DB connection pool healthy
  GATE: All metrics healthy for 30 continuous minutes

STEP 7.4: Production sign-off
  Tag: v[version]-production-[timestamp]
  Update CODEBASE-MAP.md — mark all release files ✅ DONE
  Update migration progress dashboard
  Send deployment notification to stakeholders
```

---

## Release Bundle Report

```markdown
# Release Bundle Report v[version]

**Date:** [timestamp]
**Environment:** [staging | production]
**Release Branch:** release/v[version]
**Deployed By:** [pipeline / agent / human]

## Stage Results

| Stage | Status | Duration | Notes |
|-------|--------|----------|-------|
| 1. Build Verification | ✅/❌ | Xs | |
| 2. Full Test Suite | ✅/❌ | Xs | X/Y passing |
| 3. Security Gate | ✅/❌ | Xs | Score: X/100 |
| 4. DB Migration | ✅/❌ | Xs | |
| 5. Artifacts | ✅/❌ | Xs | Image: yourapp:v[version] |
| 6. Staging Smoke | ✅/❌ | Xs | |
| 7. Production Deploy | ✅/❌ | Xs | |

## Test Summary
- Unit Tests: [X passed, 0 failed]
- Integration Tests: [X passed, 0 failed]
- Feature Parity Tests: [X/X features verified]
- Performance: [No regression | Improved X%]
- E2E Tests: [X passed, 0 failed]

## Security Summary
- Secret Scan: ✅ Clean
- CVE Scan: ✅ Zero HIGH/CRITICAL
- OWASP: ✅ 10/10
- Security Tests: ✅ All passing

## Migration Progress
- Checklist Completion: [X%]
- Remaining .aspx files: [count]
- System.Web references: [count]

## Deployment Status
🟢 DEPLOYED TO [ENVIRONMENT] SUCCESSFULLY
OR
🔴 DEPLOYMENT BLOCKED — see blocking issues below

## Blocking Issues
[List with owner and ETA]

## Rollback Instructions
[If needed, exact commands to revert]
```

---

## Rollback Procedure

```bash
# Immediate rollback (production emergency)
# 1. Revert deployment
kubectl rollout undo deployment/yourapp

# 2. Verify old version is running
kubectl rollout status deployment/yourapp

# 3. If DB migration needs rollback
dotnet ef database update [PreviousMigrationName] \
  --connection "[production-connection-string]"

# 4. Notify: all stakeholders, support, on-call
# 5. Create post-mortem issue immediately
# 6. Do NOT re-deploy until root cause identified
```
