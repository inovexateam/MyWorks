# SKILL: [Module Name]
# Version: 1.0.0
# Last updated: YYYY-MM-DD
# Owner: @your-github-handle
# Scope: [e.g. src/auth/, src/payments/]

---

## 1. Module overview

**What this module does:**
> One paragraph. What is the job of this module? What does it own? What does it NOT own?

**Entry points:**
- `src/auth/auth.controller.ts` — HTTP layer, receives requests
- `src/auth/auth.service.ts` — Core business logic
- `src/auth/auth.middleware.ts` — Request guard / JWT validation

**External dependencies:**
- `jsonwebtoken` — Token sign/verify
- `bcrypt` — Password hashing
- `UserRepository` (from `src/users/`) — DB access

**Boundary rule:**
> This module never directly queries the DB. It always goes through `UserRepository`.

---

## 2. Key files and responsibilities

| File | Responsibility | Churn risk |
|------|---------------|------------|
| `auth.service.ts` | Login, register, token refresh | HIGH |
| `auth.middleware.ts` | JWT decode + attach user to req | MEDIUM |
| `auth.controller.ts` | Route handlers only, no logic | LOW |
| `token.util.ts` | Sign/verify/expire helpers | MEDIUM |
| `auth.types.ts` | Interfaces: `AuthUser`, `JwtPayload` | LOW |

> **Churn risk** = how often this file is edited. High churn = higher bug probability.
> Update this column after each sprint.

---

## 3. Known error patterns

### Pattern A — Null user object
**Trigger:** `NullPointerException` or `Cannot read property of undefined` on `req.user`
**Root cause:** Middleware did not attach user (token missing, expired, or malformed)
**Location:** `auth.middleware.ts` → `validateToken()` function
**Confidence:** HIGH (this is the #1 recurring issue in this module)
**Fix hint:** Check `Authorization` header exists before calling `jwt.verify()`

```
TypeError: Cannot read properties of undefined (reading 'id')
    at AuthMiddleware.validateToken (auth.middleware.ts:42)
```

---

### Pattern B — Token expiry race condition
**Trigger:** `TokenExpiredError: jwt expired`
**Root cause:** Token checked at request start but expires mid-request in long operations
**Location:** `token.util.ts` → `verifyToken()`
**Confidence:** MEDIUM
**Fix hint:** Add a buffer window (e.g. 30s leeway) or implement token refresh logic

```
JsonWebTokenError: TokenExpiredError: jwt expired
    at /node_modules/jsonwebtoken/verify.js:89
    at token.util.ts:28
```

---

### Pattern C — Refresh token not invalidated
**Trigger:** User logs out but old refresh token still works
**Root cause:** Refresh token not added to blocklist on logout
**Location:** `auth.service.ts` → `logout()` method
**Confidence:** MEDIUM
**Fix hint:** Check `TokenBlocklistService.add()` is called in logout flow

---

### Pattern D — [Add your pattern]
**Trigger:**
**Root cause:**
**Location:**
**Confidence:** HIGH / MEDIUM / LOW
**Fix hint:**

---

## 4. Confidence scoring guide

When diagnosing an issue in this module, use these signals to rate your confidence:

| Signal | Weight | Notes |
|--------|--------|-------|
| Stack trace mentions a file in this module | +30 | Strong locator |
| Error message matches a known pattern above | +30 | Pattern match |
| File has HIGH churn risk (see section 2) | +20 | Historical risk |
| Error occurred after a recent commit to this file | +15 | Temporal signal |
| Error reproducible in isolation | +5 | Confirms scope |

**Score interpretation:**
- 80–100 → High confidence. File and function identified. Suggest a fix.
- 50–79 → Medium confidence. Likely area identified. Request more context.
- Below 50 → Low confidence. Cannot narrow to this module. Escalate or expand scope.

---

## 5. Common gotchas (things that confuse even experienced devs)

- `req.user` is typed as `AuthUser | undefined` — always null-check before use
- `jwt.verify()` throws, not returns null — must be wrapped in try/catch
- The `exp` field in JWT payload is in **seconds**, not milliseconds
- `bcrypt.compare()` is async — missing `await` causes silent auth bypass

---

## 6. Copilot / AI prompt hint

When sending an error from this module to AI, include:
1. The full stack trace
2. The contents of `auth.middleware.ts` lines ±20 around the error line
3. This SKILL.md file
4. The last git commit message touching the affected file

**Do NOT include:** entire `node_modules`, unrelated service files, test fixtures

Suggested prompt prefix:
```
You are diagnosing a bug in the auth module of a Node.js/TypeScript project.
Read the SKILL.md context below first. Then analyse the error and return:
- Suspected file and function
- Root cause hypothesis
- Confidence score (0-100) with justification
- Suggested fix
```

---

## 7. Recent issues log

> Keep a short running log. Helps train future pattern matching.

| Date | Error | Root cause confirmed | Fixed by |
|------|-------|---------------------|----------|
| 2024-01-15 | Null req.user in /profile | Missing auth middleware on route | @dev1 |
| 2024-02-03 | TokenExpiredError in checkout | Token not refreshed on long cart session | @dev2 |
| — | — | — | — |

---

## 8. Linked resources

- ADR: [link to architecture decision record if any]
- Runbook: [link to incident runbook]
- Tests: `src/auth/__tests__/`
- Related skills: `src/users/SKILL.md`, `src/sessions/SKILL.md`
