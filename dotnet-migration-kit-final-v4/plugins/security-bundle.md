# Plugin: Security Bundle

## Identity
This plugin runs a full, independent security sweep across the entire migrated codebase or a specific component. It is completely autonomous from the migration pipeline — it can be invoked at any time by any agent or manually.

**Invoke with:** `/security-bundle [target]`
**Auto-invoked:** Before every merge to `main` or `release/*` branches.

---

## What This Plugin Does

```
agent-security-audit (SAST + config review)
    ↓
Dependency CVE scan
    ↓
Secret detection sweep
    ↓
agent-test-runner (security test category only)
    ↓
Threat model review (for major releases)
    ↓
[SECURITY REPORT]
```

---

## Orchestration Script

```
PLUGIN: security-bundle
INPUT: target = [file | project | solution | full-app]
INPUT: mode   = [standard | pre-release | emergency]

PHASE 1: Secret Detection
  TOOL: truffleHog
  SCOPE: git history + working tree
  ON_FOUND: CRITICAL block — halt everything
  NOTIFY: agent-security-audit + human lead
  GATE: Zero secrets in codebase or history

PHASE 2: Dependency CVE Scan
  TOOL: dotnet list package --vulnerable --include-transitive
  SCOPE: All .csproj files in solution
  CLASSIFY:
    CVSS ≥ 9.0  → CRITICAL — halt deployment
    CVSS ≥ 7.0  → HIGH — block PR
    CVSS ≥ 4.0  → MEDIUM — log + track
    CVSS < 4.0  → LOW — track
  ESCALATE CRITICAL/HIGH: agent-dependency-resolver
  GATE: Zero CRITICAL or HIGH CVEs

PHASE 3: SAST (Static Application Security Testing)
  Read: agent-security-audit
  SKILL: security-review
  MODE: full
  CHECKS:
    - OWASP Top 10 (A01–A10)
    - .NET-specific security patterns
    - Migration-specific security gaps
    - Authentication flows
    - Authorization coverage
    - Input validation completeness
    - Cryptographic usage
    - Logging policy compliance
  GATE: Zero CRITICAL issues; zero HIGH issues

PHASE 4: Configuration Security Review
  REVIEW FILES:
    - appsettings.json (no secrets)
    - appsettings.Production.json (no secrets)
    - Program.cs (security middleware order correct)
    - Dockerfile (no secrets, non-root user)
    - .github/workflows/*.yml (no secrets in plain text)
  CHECKS:
    - HTTPS enforced (UseHttpsRedirection + UseHsts)
    - Security headers configured
    - Rate limiting on auth endpoints
    - CORS policy is restrictive (not *)
    - Error details hidden in production
    - Data Protection API configured
  GATE: All configuration checks pass

PHASE 5: Security-Category Tests
  Read: agent-test-runner
  FILTER: Category=Security
  TESTS INCLUDE:
    - All admin endpoints require auth
    - CSRF protection on all POST forms
    - XSS payloads are rejected/encoded
    - SQL injection payloads are rejected
    - Path traversal attempts rejected
    - Security headers present in all responses
    - Account lockout fires after N failures
    - Brute force rate limiting works
  GATE: 100% security tests passing (no exceptions)

PHASE 6: Threat Model Review (pre-release mode only)
  IF mode == pre-release:
    REVIEW: Threat model document
    VERIFY: All identified threats have mitigations
    CHECK: New features in release don't introduce new threat vectors
    SIGN-OFF: Required before release-bundle can proceed

PHASE 7: Security Regression Check
  COMPARE: Current scan vs previous scan
  FLAG: Any new findings not present in last scan
  TREND: Show security improvement over time
  REPORT: Delta report (what was fixed, what is new)
```

---

## Security Bundle Report

```markdown
## Security Bundle Report

**Date:** [ISO timestamp]
**Target:** [project/scope]
**Mode:** [standard | pre-release | emergency]
**Run By:** [agent or human]

---

### 🔑 Secret Detection
Status: ✅ PASS | 🚨 FAIL
Findings: [count] | Details: [if any]

### 📦 Dependency CVEs
Status: ✅ PASS | 🚨 FAIL
| Package | CVSS | CVE | Status |
|---------|------|-----|--------|

### 🔍 SAST Results
Status: ✅ PASS | 🚨 FAIL
| Finding | Severity | File | Line | Status |
|---------|----------|------|------|--------|

OWASP Coverage:
- A01 Broken Access Control:        ✅ / ❌
- A02 Cryptographic Failures:       ✅ / ❌
- A03 Injection:                     ✅ / ❌
- A04 Insecure Design:               ✅ / ❌
- A05 Security Misconfiguration:     ✅ / ❌
- A06 Vulnerable Components:         ✅ / ❌
- A07 Auth Failures:                 ✅ / ❌
- A08 Integrity Failures:            ✅ / ❌
- A09 Logging/Monitoring Failures:   ✅ / ❌
- A10 SSRF:                          ✅ / ❌

### ⚙️ Configuration Review
Status: ✅ PASS | 🚨 FAIL
[List of checks with pass/fail]

### 🧪 Security Tests
Status: ✅ PASS | 🚨 FAIL
Tests Passed: [X / Y]
[Any failures with details]

### 📊 Security Score
Overall: [X / 100]
Trend: [↑ Improved | → Stable | ↓ Degraded] vs last scan

### 🔒 Deployment Clearance
Status: ✅ CLEARED FOR DEPLOYMENT | 🚫 BLOCKED

Blocking Issues:
[List if any, with required actions]
```

---

## Emergency Mode

When invoked with `mode=emergency` (active security incident):

```
1. Run Phase 1 (secrets) and Phase 2 (CVEs) IMMEDIATELY — skip all others
2. Produce findings within 5 minutes
3. Page human security lead
4. All deployment pipelines paused until clearance issued
5. Post findings to #security-incidents channel
```

---

## Integration Points

```
CALLED BY:
  - release-bundle plugin (always, pre-release mode)
  - CI pipeline (standard mode, every PR to main)
  - agent-security-audit (on-demand, standard mode)
  - Human (on-demand, any mode)

CALLS:
  - agent-security-audit
  - agent-dependency-resolver (on CVE findings)
  - agent-test-runner (security category)
  - agent-code-refactor (on SAST fix requests)
```
