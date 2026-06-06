/**
 * generate-tests.js
 * Reads selectors.json. For each page, generates tests for EXACTLY what was found.
 * No CRUD. No Login. No Form assumptions. Tests reflect actual elements on page.
 *
 * Run: node generate-tests.js
 */

const fs   = require('fs');
const path = require('path');

if (!fs.existsSync('selectors.json')) {
  console.error('✗ selectors.json missing. Run extract-selectors.js first.');
  process.exit(1);
}

const allPages = JSON.parse(fs.readFileSync('selectors.json', 'utf-8'));
const OUT_DIR  = path.join(__dirname, 'tests');
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

// ── Generate one spec file per page based on its actual elements ──────────────
function generateSpec(pageName, elements) {
  const pageUrl = elements[0]?.pageUrl || '';

  // Group elements by what they actually are
  const tabs      = elements.filter(e => e.role === 'tab'      || (e.rawId || '').toLowerCase().includes('tab'));
  const buttons   = elements.filter(e => e.tag === 'button'    && e.text);
  const inputs    = elements.filter(e => e.tag === 'input'     && e.type !== 'hidden');
  const selects   = elements.filter(e => e.tag === 'select');
  const checkboxes= elements.filter(e => e.type === 'checkbox' || e.role === 'checkbox');
  const sliders   = elements.filter(e => e.type === 'range'    || e.role === 'slider');
  const links     = elements.filter(e => e.tag === 'a'         && e.text && e.href && !e.href.startsWith('javascript'));
  const textareas = elements.filter(e => e.tag === 'textarea');

  // ── Always-present: smoke tests ────────────────────────────────────────────
  let spec = `import { test, expect } from '@playwright/test';
// Auto-generated from: ${pageUrl}
// Elements found: ${elements.length}

test.describe('${pageName}', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('${pageUrl}');
    await page.waitForLoadState('networkidle');
  });

  // ── Smoke ─────────────────────────────────────────────────────────────────

  test('page loads', async ({ page }) => {
    await expect(page).toHaveTitle(/.+/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('no console errors on load', async ({ page }) => {
    const errors = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto('${pageUrl}');
    await page.waitForLoadState('networkidle');
    expect(errors.filter(e => !e.includes('favicon') && !e.includes('404'))).toHaveLength(0);
  });
`;

  // ── Tabs ───────────────────────────────────────────────────────────────────
  if (tabs.length > 0) {
    spec += `
  // ── Tabs (${tabs.length} found) ──────────────────────────────────────────

  test('all tabs are visible', async ({ page }) => {
${tabs.map(t => `    await expect(page.locator('${t.selector}')).toBeVisible();`).join('\n')}
  });

  test('each tab is clickable', async ({ page }) => {
${tabs.map(t => `    await page.click('${t.selector}');\n    await expect(page.locator('body')).toBeVisible(); // no crash`).join('\n')}
  });
`;
  }

  // ── Buttons ────────────────────────────────────────────────────────────────
  if (buttons.length > 0) {
    spec += `
  // ── Buttons (${buttons.length} found) ────────────────────────────────────

  test('all buttons are visible', async ({ page }) => {
${buttons.map(b => `    await expect(page.locator('${b.selector}').first()).toBeVisible();`).join('\n')}
  });
`;
  }

  // ── Inputs ─────────────────────────────────────────────────────────────────
  if (inputs.length > 0) {
    const fillLines = inputs.map(inp => {
      if (inp.type === 'range')    return `    await page.fill('${inp.selector}', '50');\n    await expect(page.locator('${inp.selector}')).toHaveValue('50');`;
      if (inp.type === 'number')   return `    await page.fill('${inp.selector}', '10');`;
      if (inp.type === 'date')     return `    await page.fill('${inp.selector}', '2024-01-01');`;
      if (inp.type === 'email')    return `    await page.fill('${inp.selector}', 'test@example.com');`;
      if (inp.type === 'password') return `    await page.fill('${inp.selector}', 'Test@1234');`;
      if (inp.type === 'checkbox') return `    await page.check('${inp.selector}');\n    await expect(page.locator('${inp.selector}')).toBeChecked();`;
      return `    await page.fill('${inp.selector}', 'test input');`;
    }).join('\n');

    spec += `
  // ── Inputs (${inputs.length} found) ──────────────────────────────────────

  test('all inputs are interactable', async ({ page }) => {
${fillLines}
  });
`;
  }

  // ── Selects ────────────────────────────────────────────────────────────────
  if (selects.length > 0) {
    spec += `
  // ── Dropdowns (${selects.length} found) ──────────────────────────────────

  test('dropdowns have selectable options', async ({ page }) => {
${selects.map(s => `    await page.selectOption('${s.selector}', { index: 1 });\n    expect(await page.inputValue('${s.selector}')).toBeTruthy();`).join('\n')}
  });
`;
  }

  // ── Checkboxes ─────────────────────────────────────────────────────────────
  if (checkboxes.length > 0) {
    spec += `
  // ── Checkboxes (${checkboxes.length} found) ──────────────────────────────

  test('checkboxes toggle correctly', async ({ page }) => {
${checkboxes.map(c => `    await page.check('${c.selector}');\n    await expect(page.locator('${c.selector}')).toBeChecked();\n    await page.uncheck('${c.selector}');\n    await expect(page.locator('${c.selector}')).not.toBeChecked();`).join('\n')}
  });
`;
  }

  // ── Range sliders ──────────────────────────────────────────────────────────
  if (sliders.length > 0) {
    spec += `
  // ── Sliders (${sliders.length} found) ────────────────────────────────────

  test('sliders accept value changes', async ({ page }) => {
${sliders.map(s => `    await page.fill('${s.selector}', '50');\n    await expect(page.locator('${s.selector}')).toHaveValue('50');`).join('\n')}
  });
`;
  }

  // ── Textareas ──────────────────────────────────────────────────────────────
  if (textareas.length > 0) {
    spec += `
  // ── Textareas (${textareas.length} found) ────────────────────────────────

  test('textareas accept input', async ({ page }) => {
${textareas.map(t => `    await page.fill('${t.selector}', 'Sample text input');\n    await expect(page.locator('${t.selector}')).toHaveValue('Sample text input');`).join('\n')}
  });
`;
  }

  // ── Links ──────────────────────────────────────────────────────────────────
  if (links.length > 0) {
    spec += `
  // ── Links (${links.length} found) ────────────────────────────────────────

  test('navigation links are visible', async ({ page }) => {
${links.slice(0, 8).map(l => `    await expect(page.locator('${l.selector}').first()).toBeVisible();`).join('\n')}
  });
`;
  }

  spec += `\n});\n`;
  return spec;
}

// ── Main ──────────────────────────────────────────────────────────────────────
let generated = 0;
let skipped   = 0;

for (const [pageName, elements] of Object.entries(allPages)) {
  if (!elements || elements.length === 0) {
    console.warn(`✗ [${pageName}] 0 elements — skipped`);
    skipped++;
    continue;
  }

  const spec    = generateSpec(pageName, elements);
  const outFile = path.join(OUT_DIR, `${pageName}.spec.js`);
  fs.writeFileSync(outFile, spec);

  const types = [
    elements.some(e => e.role === 'tab')           && 'tabs',
    elements.some(e => e.tag === 'button')         && 'buttons',
    elements.some(e => e.tag === 'input')          && 'inputs',
    elements.some(e => e.tag === 'select')         && 'selects',
    elements.some(e => e.type === 'checkbox')      && 'checkboxes',
    elements.some(e => e.type === 'range')         && 'sliders',
    elements.some(e => e.tag === 'a' && e.text)    && 'links',
  ].filter(Boolean);

  console.log(`✓ tests/${pageName}.spec.js  [${elements.length} elements: ${types.join(', ')}]`);
  generated++;
}

console.log(`\n→ ${generated} test file(s) generated, ${skipped} skipped`);
console.log('→ Run: npx playwright test');