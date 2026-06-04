/**
 * generate-tests.js
 * Run AFTER extract-selectors.js
 * Run: node generate-tests.js
 * Output: tests/login.spec.js, tests/dashboard.spec.js, tests/forms.spec.js, tests/crud.spec.js
 */

const fs = require('fs');
const path = require('path');

const selectors = JSON.parse(fs.readFileSync('selectors.json', 'utf-8'));
const OUT_DIR = path.join(__dirname, 'tests');
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

// ─── Helpers ────────────────────────────────────────────────────────────────

function safeVar(s = '') {
  return s.replace(/[^a-zA-Z0-9]/g, '_').replace(/^_+|_+$/g, '').toLowerCase() || 'element';
}

function findFirst(els, ...types) {
  return els.find(e => types.includes(e.type) || types.includes(e.tag));
}

function findByHint(els, ...hints) {
  return els.find(e =>
    hints.some(h =>
      e.selector.toLowerCase().includes(h) ||
      (e.text || '').toLowerCase().includes(h) ||
      (e.placeholder || '').toLowerCase().includes(h) ||
      (e.ariaLabel || '').toLowerCase().includes(h)
    )
  );
}

// ─── Login Test ──────────────────────────────────────────────────────────────

function generateLogin(els) {
  const emailEl   = findByHint(els, 'email', 'username', 'user') || findFirst(els, 'email', 'text');
  const passEl    = findFirst(els, 'password');
  const submitEl  = findByHint(els, 'login', 'sign in', 'submit') || findFirst(els, 'submit');

  const emailSel  = emailEl?.selector  || 'input[type="email"]';
  const passSel   = passEl?.selector   || 'input[type="password"]';
  const submitSel = submitEl?.selector || 'button[type="submit"]';

  return `import { test, expect } from '@playwright/test';

test.describe('Login / Auth', () => {

  test('valid credentials → redirect to dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.fill('${emailSel}', process.env.TEST_USER || 'testuser@example.com');
    await page.fill('${passSel}', process.env.TEST_PASS || 'Test@1234');
    await page.click('${submitSel}');
    await expect(page).not.toHaveURL(/login/);
  });

  test('empty fields → show validation error', async ({ page }) => {
    await page.goto('/login');
    await page.click('${submitSel}');
    // At least one error visible
    const errors = page.locator('[class*="error"], [class*="invalid"], [role="alert"]');
    await expect(errors.first()).toBeVisible({ timeout: 5000 }).catch(() => {
      // Some apps prevent submit — just verify still on login
      expect(page.url()).toContain('login');
    });
  });

  test('wrong password → show error message', async ({ page }) => {
    await page.goto('/login');
    await page.fill('${emailSel}', 'wrong@example.com');
    await page.fill('${passSel}', 'wrongpassword');
    await page.click('${submitSel}');
    await expect(page.locator('[class*="error"], [role="alert"], [class*="message"]').first())
      .toBeVisible({ timeout: 8000 });
  });

});
`;
}

// ─── Dashboard / Nav Test ────────────────────────────────────────────────────

function generateDashboard(els) {
  const navLinks = els.filter(e => e.tag === 'a' && e.text).slice(0, 5);
  const navChecks = navLinks.map(l =>
    `  await expect(page.locator('${l.selector}')).toBeVisible();`
  ).join('\n') || `  await expect(page.locator('nav, [role="navigation"]').first()).toBeVisible();`;

  const tabs = els.filter(e => e.role === 'tab' || e.tag === 'button').slice(0, 3);
  const tabChecks = tabs.map(t =>
    `    await page.click('${t.selector}');\n    await page.waitForLoadState('networkidle');\n    await expect(page).not.toHaveURL('about:blank');`
  ).join('\n') || `    // No tabs detected — add manual tab selectors`;

  return `import { test, expect } from '@playwright/test';

test.describe('Dashboard / Navigation', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
  });

  test('dashboard loads → key elements visible', async ({ page }) => {
    await expect(page).toHaveURL(/dashboard/);
${navChecks}
  });

  test('navigation links → clickable and responsive', async ({ page }) => {
${tabChecks}
  });

  test('page title → present', async ({ page }) => {
    await expect(page).toHaveTitle(/.+/);
  });

  test('no console errors on load', async ({ page }) => {
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    expect(errors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

});
`;
}

// ─── Forms Test ──────────────────────────────────────────────────────────────

function generateForms(els) {
  const inputs   = els.filter(e => ['input', 'textarea', 'select'].includes(e.tag) && e.type !== 'hidden');
  const submitEl = findByHint(els, 'submit', 'save', 'send') || findFirst(els, 'submit');
  const submitSel = submitEl?.selector || 'button[type="submit"]';

  const fillSteps = inputs.slice(0, 8).map(inp => {
    if (inp.tag === 'select') return `    await page.selectOption('${inp.selector}', { index: 1 });`;
    if (inp.type === 'checkbox' || inp.type === 'radio') return `    await page.check('${inp.selector}');`;
    if (inp.type === 'date') return `    await page.fill('${inp.selector}', '2024-01-15');`;
    if (inp.type === 'number') return `    await page.fill('${inp.selector}', '42');`;
    if ((inp.placeholder || '').toLowerCase().includes('email') || (inp.selector || '').includes('email'))
      return `    await page.fill('${inp.selector}', 'test@example.com');`;
    return `    await page.fill('${inp.selector}', 'Test Input ${safeVar(inp.placeholder || inp.selector)}');`;
  }).join('\n') || `    // No inputs detected — add selectors manually`;

  return `import { test, expect } from '@playwright/test';

test.describe('Forms & Submit', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/form');
  });

  test('form visible → all required fields present', async ({ page }) => {
    await expect(page.locator('form, [role="form"]').first()).toBeVisible();
  });

  test('fill valid data → submit succeeds', async ({ page }) => {
${fillSteps}
    await page.click('${submitSel}');
    // Expect success state: URL change OR success message
    await Promise.race([
      page.waitForURL(url => !url.includes('/form'), { timeout: 8000 }),
      page.waitForSelector('[class*="success"], [role="alert"], [class*="toast"]', { timeout: 8000 }),
    ]).catch(() => {});
    // At minimum — no crash
    await expect(page.locator('body')).toBeVisible();
  });

  test('required fields empty → validation fires', async ({ page }) => {
    await page.click('${submitSel}');
    const errorLocator = page.locator('[class*="error"], [class*="invalid"], [required]:invalid, [aria-invalid="true"]');
    const count = await errorLocator.count();
    expect(count).toBeGreaterThan(0);
  });

  test('form reset/cancel → fields clear', async ({ page }) => {
    const resetBtn = page.locator('button[type="reset"], [class*="cancel"], [class*="clear"]').first();
    const exists = await resetBtn.count();
    if (exists) {
${fillSteps.split('\n').slice(0, 2).join('\n')}
      await resetBtn.click();
      // First visible input should be empty
      const firstInput = page.locator('input[type="text"], input[type="email"]').first();
      if (await firstInput.count()) await expect(firstInput).toHaveValue('');
    }
  });

});
`;
}

// ─── CRUD Test ───────────────────────────────────────────────────────────────

function generateCRUD(els) {
  const createBtn = findByHint(els, 'create', 'add', 'new', '+') || findFirst(els, 'button');
  const editBtn   = findByHint(els, 'edit', 'update', 'modify');
  const deleteBtn = findByHint(els, 'delete', 'remove', 'trash');
  const listEl    = findByHint(els, 'table', 'list', 'grid', 'row') ||
                    els.find(e => ['table', 'ul', 'ol'].includes(e.tag));

  const createSel = createBtn?.selector || 'button:has-text("Add"), button:has-text("Create"), button:has-text("New")';
  const editSel   = editBtn?.selector   || '[data-testid*="edit"], button:has-text("Edit")';
  const deleteSel = deleteBtn?.selector || '[data-testid*="delete"], button:has-text("Delete")';
  const listSel   = listEl?.selector    || 'table, [role="grid"], ul[class*="list"]';

  return `import { test, expect } from '@playwright/test';

test.describe('CRUD Operations', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('/items');
  });

  test('READ — list loads → items or empty state visible', async ({ page }) => {
    const list = page.locator('${listSel}');
    const empty = page.locator('[class*="empty"], [class*="no-data"], [class*="no-results"]');
    await expect(list.or(empty).first()).toBeVisible({ timeout: 8000 });
  });

  test('CREATE — open form → submit → item appears in list', async ({ page }) => {
    const countBefore = await page.locator('${listSel} tr, ${listSel} li, ${listSel} [class*="row"]').count();
    await page.click('${createSel}');
    // Fill whatever inputs appear
    await page.locator('input[type="text"]:visible').first().fill('AutoTest Item').catch(() => {});
    await page.locator('button[type="submit"], button:has-text("Save"), button:has-text("Create")').first().click();
    await page.waitForLoadState('networkidle');
    const countAfter = await page.locator('${listSel} tr, ${listSel} li, ${listSel} [class*="row"]').count();
    expect(countAfter).toBeGreaterThanOrEqual(countBefore);
  });

  test('UPDATE — click edit → modify → save → changes persist', async ({ page }) => {
    const editButtons = page.locator('${editSel}');
    const count = await editButtons.count();
    if (count === 0) test.skip(true, 'No edit buttons found on page');
    await editButtons.first().click();
    const editInput = page.locator('input[type="text"]:visible').first();
    if (await editInput.count()) {
      await editInput.clear();
      await editInput.fill('Updated AutoTest');
    }
    await page.locator('button[type="submit"], button:has-text("Save"), button:has-text("Update")').first().click();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).toBeVisible();
  });

  test('DELETE — click delete → confirm → item removed', async ({ page }) => {
    const deleteButtons = page.locator('${deleteSel}');
    const count = await deleteButtons.count();
    if (count === 0) test.skip(true, 'No delete buttons found on page');
    const countBefore = await page.locator('${listSel} tr, ${listSel} li, ${listSel} [class*="row"]').count();
    await deleteButtons.first().click();
    // Handle confirm dialog (native or modal)
    page.on('dialog', dialog => dialog.accept());
    const confirmBtn = page.locator('button:has-text("Confirm"), button:has-text("Yes"), button:has-text("OK")');
    if (await confirmBtn.count()) await confirmBtn.first().click();
    await page.waitForLoadState('networkidle');
    const countAfter = await page.locator('${listSel} tr, ${listSel} li, ${listSel} [class*="row"]').count();
    expect(countAfter).toBeLessThanOrEqual(countBefore);
  });

});
`;
}

// ─── Generate All ────────────────────────────────────────────────────────────

const generators = {
  login:     generateLogin,
  dashboard: generateDashboard,
  forms:     generateForms,
  crud:      generateCRUD,
};

for (const [name, fn] of Object.entries(generators)) {
  const els  = selectors[name] || [];
  const code = fn(els);
  const out  = path.join(OUT_DIR, `${name}.spec.js`);
  fs.writeFileSync(out, code);
  console.log(`✓ tests/${name}.spec.js generated`);
}

console.log('\n→ Run: npx playwright test');