# Playwright Auto-Suite

## One-time setup
```bash
npm install @playwright/test
npx playwright install chromium
```

## Step 1 — Extract selectors from your app
```bash
# No auth
APP_URL=https://your-app.com node extract-selectors.js
$env:APP_URL="https://inovexateam.github.io/MyWorks/github_copilot_token_optimizer_demo.html"; node extract-selectors.js

# With auth (saves session → reused in all tests)
APP_URL=https://your-app.com AUTH_USER=admin@org.com AUTH_PASS=secret node extract-selectors.js
```
→ Produces `selectors.json`

## Step 2 — Generate test files from selectors
```bash
node generate-tests.js
```
→ Produces:
- `tests/login.spec.js`
- `tests/dashboard.spec.js`
- `tests/forms.spec.js`
- `tests/crud.spec.js`

## Step 3 — Run tests
```bash
# All tests
npx playwright test

# One file
npx playwright test tests/login.spec.js

# With report
npx playwright test --reporter=html && npx playwright show-report
```

## Env vars
| Var        | Purpose                        |
|------------|--------------------------------|
| APP_URL    | Base URL of your app           |
| AUTH_USER  | Login username/email           |
| AUTH_PASS  | Login password                 |
| TEST_USER  | Used inside tests (can differ) |
| TEST_PASS  | Used inside tests              |

## Re-run after UI changes
```bash
node extract-selectors.js && node generate-tests.js
```
Selectors re-extracted. Tests regenerated. No manual work.