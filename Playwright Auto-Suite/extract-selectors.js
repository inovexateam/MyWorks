/**
 * extract-selectors.js
 * Run: node extract-selectors.js
 * Output: selectors.json — feed to test generator
 */

const { chromium } = require('@playwright/test');
const fs = require('fs');

const APP_URL = process.env.APP_URL || 'https://your-app.com';
const AUTH_USER = process.env.AUTH_USER || '';
const AUTH_PASS = process.env.AUTH_PASS || '';

// Pages to crawl — add yours
const PAGES_TO_CRAWL = [
  { name: 'login',     url: `${APP_URL}/login` },
  { name: 'dashboard', url: `${APP_URL}/dashboard` },
  { name: 'forms',     url: `${APP_URL}/form` },
  { name: 'crud',      url: `${APP_URL}/items` },
];

async function extractSelectors(page, pageName) {
  return await page.evaluate((name) => {
    const INTERACTIVE = 'input, button, a[href], select, textarea, [role="button"], [role="link"], [role="menuitem"], [role="tab"], [onclick]';

    function bestSelector(el) {
      if (el.getAttribute('data-testid')) return `[data-testid="${el.getAttribute('data-testid')}"]`;
      if (el.id) return `#${el.id}`;
      if (el.getAttribute('name')) return `[name="${el.getAttribute('name')}"]`;
      if (el.getAttribute('aria-label')) return `[aria-label="${el.getAttribute('aria-label')}"]`;
      if (el.getAttribute('placeholder')) return `[placeholder="${el.getAttribute('placeholder')}"]`;
      const text = el.innerText?.trim().slice(0, 40);
      if (text && el.tagName !== 'INPUT') return `text=${text}`;
      return `${el.tagName.toLowerCase()}${el.className ? '.' + [...el.classList].join('.') : ''}`;
    }

    return [...document.querySelectorAll(INTERACTIVE)].map(el => ({
      page: name,
      tag: el.tagName.toLowerCase(),
      type: el.type || null,
      text: el.innerText?.trim().slice(0, 60) || null,
      placeholder: el.placeholder || null,
      ariaLabel: el.getAttribute('aria-label') || null,
      role: el.getAttribute('role') || null,
      selector: bestSelector(el),
      isVisible: el.offsetParent !== null,
    })).filter(e => e.isVisible);
  }, pageName);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // --- Login if credentials provided ---
  if (AUTH_USER && AUTH_PASS) {
    await page.goto(`${APP_URL}/login`);
    const userField = await page.$('input[type="email"], input[name="username"], input[name="email"], #username, #email');
    const passField = await page.$('input[type="password"]');
    const submitBtn = await page.$('button[type="submit"], input[type="submit"]');
    if (userField) await userField.fill(AUTH_USER);
    if (passField) await passField.fill(AUTH_PASS);
    if (submitBtn) await submitBtn.click();
    await page.waitForNavigation({ waitUntil: 'networkidle' }).catch(() => {});
    await context.storageState({ path: 'auth-state.json' });
    console.log('✓ Auth complete, state saved → auth-state.json');
  }

  const allSelectors = {};

  for (const { name, url } of PAGES_TO_CRAWL) {
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
      allSelectors[name] = await extractSelectors(page, name);
      console.log(`✓ ${name}: ${allSelectors[name].length} selectors extracted`);
    } catch (e) {
      console.warn(`✗ ${name}: ${e.message}`);
      allSelectors[name] = [];
    }
  }

  fs.writeFileSync('selectors.json', JSON.stringify(allSelectors, null, 2));
  console.log('\n→ selectors.json written. Run: node generate-tests.js');
  await browser.close();
})();