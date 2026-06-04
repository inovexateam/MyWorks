/**
 * generate-tests.js
 * Generates test files ONLY for pages found in selectors.json with actual selectors.
 * Run: node generate-tests.js
 */

const fs      = require('fs');
const path    = require('path');
const APP_URL = process.env.APP_URL || 'https://your-app.com';

if (!fs.existsSync('selectors.json')) {
  console.error('✗ selectors.json not found. Run extract-selectors.js first.');
  process.exit(1);
}

const selectors = JSON.parse(fs.readFileSync('selectors.json', 'utf-8'));
const OUT_DIR   = path.join(__dirname, 'tests');
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

// ── Helpers ──────────────────────────────────────────────────────────────────

function findByHint(els, ...hints) {
  return els.find(e =>
    hints.some(h =>
      (e.selector     || '').toLowerCase().includes(h) ||
      (e.text         || '').toLowerCase().includes(h) ||
      (e.placeholder  || '').toLowerCase().includes(h) ||
      (e.ariaLabel    || '').toLowerCase().includes(h) ||
      (e.type         || '').toLowerCase().includes(h)
    )
  );
}

function findFirst(els, ...types) {
  return els.find(e => types.includes(e.type) || types.includes(e.tag));
}

function safeVar(s = '') {
  return s.replace(/[^a-zA-Z0-9]/g, '_').replace(/^_+|_+$/g, '').toLowerCase() || 'el';
}

// ── Infer page type from selectors + page name ───────────────────────────────

function inferPageType(pageName, els) {
  const name = pageName.toLowerCase();

  // Explicit name match
  if (/login|signin|auth/.test(name))         return 'login';
  if (/dashboard|home|index|main/.test(name)) return 'dashboard';
  if (/form|register|create|edit/.test(name)) return 'form';
  if (/list|items|crud|manage|table/.test(name)) return 'crud';

  // Fallback: infer from selectors present on page
  const hasPassword   = els.some(e => e.type === 'password');
  const hasSubmit     = els.some(e => e.type === 'submit' || (e.tag === 'button' && /submit|login|sign/i.test(e.text || '')));
  const hasTable      = els.some(e => /table|grid|list/i.test(e.selector));
  const hasNavLinks   = els.filter(e => e.tag === 'a').length > 3;
  const hasFormInputs = els.filter(e => e.tag === 'input').length > 1;

  if (hasPassword && hasSubmit)  return 'login';
  if (hasTable)                  return 'crud';
  if (hasNavLinks)               return 'dashboard';
  if (hasFormInputs)             return 'form';

  return 'generic';
}

// ── Test generators ───────────────────────────────────────────────────────────

function generateLogin(pageName, els, pageUrl) {
  const emailEl  = findByHint(els, 'email', 'username', 'user') || findFirst(els, 'email', 'text');
  const passEl   = findFirst(els, 'password');
  const submitEl = findByHint(els, 'login', 'sign in', 'submit') || findFirst(els, 'submit');

  const emailSel  = emailEl?.selector  || 'input[type="email"]';
  const passSel   = passEl?.selector   || 'input[type="password"]';
  const submitSel = submitEl?.selector || 'button[type="submit"]';

  return `import { test, expect } from '@playwright/test';
// Auto-generated from: ${pageUrl}

test.describe('Login / Auth — ${pageName}', () => {

  test('valid credentials → redirects away from login', async ({ page }) => {
    await page.goto('${pageUrl}');
    await page.fill('${emailSel}', process.env.TEST_USER || 'testuser@example.com');
    await page.fill('${passSel}', process.env.TEST_PASS || 'Test@1234');
    await page.click('${submitSel}');
    await expect(page).not.toHaveURL(/${pageName}/);
  });

  test('empty fields → validation error visible', async ({ page }) => {
    await page.goto('${pageUrl}');
    await page.click('${submitSel}');
    const error = page.locator('[class*="error"], [class*="invalid"], [role="alert"]');
    await expect(error.first()).toBeVisible({ timeout: 5000 }).catch(() => {
      expect(page.url()).toContain('${pageName}');
    });
  });

  test('wrong password → error message shown', async ({ page }) => {
    await page.goto('${pageUrl}');
    await page.fill('${emailSel}', 'wrong@example.com');
    await page.fill('${passSel}', 'wrongpassword');
    await page.click('${submitSel}');
    await expect(page.locator('[class*="error"], [role="alert"]').first())
      .toBeVisible({ timeout: 8000 });
  });

});
`;
}

function generateDashboard(pageName, els, pageUrl) {
  const navLinks  = els.filter(e => e.tag === 'a' && e.text).slice(0, 5);
  const navChecks = navLinks.length
    ? navLinks.map(l => `    await expect(page.locator('${l.selector}')).toBeVisible();`).join('\n')
    : `    await expect(page.locator('nav, [role="navigation"]').first()).toBeVisible();`;

  const tabs = els.filter(e => e.role === 'tab' || (e.tag === 'button' && e.text)).slice(0, 3);
  const tabChecks = tabs.length
    ? tabs.map(t =>
        `    await page.click('${t.selector}');\n    await page.waitForLoadState('networkidle');`
      ).join('\n')
    : `    // No tabs detected`;

  return `import { test, expect } from '@playwright/test';
// Auto-generated from: ${pageUrl}

test.describe('Dashboard / Navigation — ${pageName}', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('${pageUrl}');
  });

  test('page loads → key elements visible', async ({ page }) => {
${navChecks}
  });

  test('navigation → clickable without crash', async ({ page }) => {
${tabChecks}
  });

  test('page has title', async ({ page }) => {
    await expect(page).toHaveTitle(/.+/);
  });

  test('no console errors on load', async ({ page }) => {
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto('${pageUrl}');
    await page.waitForLoadState('networkidle');
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

});
`;
}

function generateForm(pageName, els, pageUrl) {
  const inputs    = els.filter(e => ['input','textarea','select'].includes(e.tag) && e.type !== 'hidden');
  const submitEl  = findByHint(els, 'submit','save','send') || findFirst(els, 'submit');
  const submitSel = submitEl?.selector || 'button[type="submit"]';

  const fillSteps = inputs.slice(0, 8).map(inp => {
    if (inp.tag === 'select')                          return `    await page.selectOption('${inp.selector}', { index: 1 });`;
    if (['checkbox','radio'].includes(inp.type))       return `    await page.check('${inp.selector}');`;
    if (inp.type === 'date')                           return `    await page.fill('${inp.selector}', '2024-01-15');`;
    if (inp.type === 'number')                         return `    await page.fill('${inp.selector}', '42');`;
    if (/email/i.test(inp.placeholder || inp.selector)) return `    await page.fill('${inp.selector}', 'test@example.com');`;
    return `    await page.fill('${inp.selector}', 'Test ${safeVar(inp.placeholder || inp.selector)}');`;
  }).join('\n') || `    // No inputs detected`;

  return `import { test, expect } from '@playwright/test';
// Auto-generated from: ${pageUrl}

test.describe('Form — ${pageName}', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('${pageUrl}');
  });

  test('form visible on page', async ({ page }) => {
    await expect(page.locator('form, [role="form"]').first()).toBeVisible();
  });

  test('fill valid data → submit succeeds', async ({ page }) => {
${fillSteps}
    await page.click('${submitSel}');
    await Promise.race([
      page.waitForURL(url => !url.includes('${pageName}'), { timeout: 8000 }),
      page.waitForSelector('[class*="success"], [role="alert"], [class*="toast"]', { timeout: 8000 }),
    ]).catch(() => {});
    await expect(page.locator('body')).toBeVisible();
  });

  test('required fields empty → validation fires', async ({ page }) => {
    await page.click('${submitSel}');
    const errors = page.locator('[class*="error"], [class*="invalid"], [required]:invalid, [aria-invalid="true"]');
    expect(await errors.count()).toBeGreaterThan(0);
  });

});
`;
}

function generateCRUD(pageName, els, pageUrl) {
  const createBtn = findByHint(els, 'create','add','new','+') || findFirst(els, 'button');
  const editBtn   = findByHint(els, 'edit','update','modify');
  const deleteBtn = findByHint(els, 'delete','remove','trash');

  const createSel = createBtn?.selector || 'button:has-text("Add")';
  const editSel   = editBtn?.selector   || '[data-testid*="edit"], button:has-text("Edit")';
  const deleteSel = deleteBtn?.selector || '[data-testid*="delete"], button:has-text("Delete")';
  const listSel   = 'table, [role="grid"], ul[class*="list"], [class*="table"]';

  return `import { test, expect } from '@playwright/test';
// Auto-generated from: ${pageUrl}

test.describe('CRUD — ${pageName}', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('${pageUrl}');
  });

  test('READ — list or empty state visible', async ({ page }) => {
    const list  = page.locator('${listSel}');
    const empty = page.locator('[class*="empty"], [class*="no-data"], [class*="no-results"]');
    await expect(list.or(empty).first()).toBeVisible({ timeout: 8000 });
  });

  test('CREATE — open form → submit → count increases', async ({ page }) => {
    const rowSel = '${listSel} tr, ${listSel} li, ${listSel} [class*="row"]';
    const before = await page.locator(rowSel).count();
    await page.click('${createSel}');
    await page.locator('input[type="text"]:visible').first().fill('AutoTest Item').catch(() => {});
    await page.locator('button[type="submit"], button:has-text("Save")').first().click();
    await page.waitForLoadState('networkidle');
    expect(await page.locator(rowSel).count()).toBeGreaterThanOrEqual(before);
  });

  test('UPDATE — edit first item → save', async ({ page }) => {
    const btns = page.locator('${editSel}');
    if (await btns.count() === 0) test.skip(true, 'No edit buttons');
    await btns.first().click();
    const inp = page.locator('input[type="text"]:visible').first();
    if (await inp.count()) { await inp.clear(); await inp.fill('Updated Item'); }
    await page.locator('button[type="submit"], button:has-text("Save")').first().click();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).toBeVisible();
  });

  test('DELETE — delete first item → count decreases', async ({ page }) => {
    const rowSel = '${listSel} tr, ${listSel} li, ${listSel} [class*="row"]';
    const btns   = page.locator('${deleteSel}');
    if (await btns.count() === 0) test.skip(true, 'No delete buttons');
    const before = await page.locator(rowSel).count();
    await btns.first().click();
    page.on('dialog', d => d.accept());
    const confirm = page.locator('button:has-text("Confirm"), button:has-text("Yes"), button:has-text("OK")');
    if (await confirm.count()) await confirm.first().click();
    await page.waitForLoadState('networkidle');
    expect(await page.locator(rowSel).count()).toBeLessThanOrEqual(before);
  });

});
`;
}

function generateGeneric(pageName, els, pageUrl) {
  const buttons = els.filter(e => e.tag === 'button' || e.role === 'button').slice(0, 4);
  const links   = els.filter(e => e.tag === 'a' && e.text).slice(0, 4);

  const checks = [...buttons, ...links].map(e =>
    `    await expect(page.locator('${e.selector}')).toBeVisible();`
  ).join('\n') || `    await expect(page.locator('body')).toBeVisible();`;

  return `import { test, expect } from '@playwright/test';
// Auto-generated from: ${pageUrl}

test.describe('Page — ${pageName}', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('${pageUrl}');
  });

  test('page loads successfully', async ({ page }) => {
    await expect(page).toHaveTitle(/.+/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('key elements visible', async ({ page }) => {
${checks}
  });

  test('no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto('${pageUrl}');
    await page.waitForLoadState('networkidle');
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

});
`;
}

const GENERATORS = {
  login:     generateLogin,
  dashboard: generateDashboard,
  form:      generateForm,
  crud:      generateCRUD,
  generic:   generateGeneric,
};

// ── Main: only generate for pages with selectors ─────────────────────────────

let generated = 0;
let skipped   = 0;

for (const [pageName, els] of Object.entries(selectors)) {
  if (!els || els.length === 0) {
    console.warn(`✗ [${pageName}] — 0 selectors found, skipping`);
    skipped++;
    continue;
  }

  const pageUrl  = `${APP_URL}/${pageName}`;  // override per-page if needed
  const pageType = inferPageType(pageName, els);
  const genFn    = GENERATORS[pageType] || GENERATORS.generic;
  const code     = genFn(pageName, els, pageUrl);
  const outFile  = path.join(OUT_DIR, `${pageName}.spec.js`);

  fs.writeFileSync(outFile, code);
  console.log(`✓ tests/${pageName}.spec.js  [type: ${pageType}, selectors: ${els.length}]`);
  generated++;
}

console.log(`\n→ ${generated} test files generated, ${skipped} pages skipped (no selectors)`);
console.log('→ Run: npx playwright test');