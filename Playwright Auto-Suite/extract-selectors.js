/**
 * extract-selectors.js
 * Give it a URL. It extracts every interactive element from every reachable page.
 * No hardcoded page types. No assumptions. Just what's on the page.
 *
 * Run: APP_URL=https://your-app.com node extract-selectors.js
 */

const { chromium } = require('@playwright/test');
const fs = require('fs');

const APP_URL  = process.env.APP_URL  || 'https://your-app.com';
const AUTH_USER = process.env.AUTH_USER || '';
const AUTH_PASS = process.env.AUTH_PASS || '';
const MAX_PAGES = parseInt(process.env.MAX_PAGES || '20');
const BASE_HOST = new URL(APP_URL).hostname;

// ── Wait for page to settle (auto-detects framework) ─────────────────────────
async function waitForPage(page) {
  await page.waitForLoadState('networkidle').catch(() => {});

  const fw = await page.evaluate(() => {
    if (document.querySelector('[ng-version],[_nghost],app-root'))                return 'angular';
    if (document.querySelector('#__NEXT_DATA__,[data-reactroot]'))                return 'react';
    if (document.querySelector('#__nuxt,[data-v-]'))                              return 'vue';
    if (document.querySelector('script[src*="blazor"]') || window.__blazorSignalR) return 'blazor';
    if (document.querySelector('input[name*="__VIEWSTATE"],[id*="ctl00"]'))       return 'aspx';
    return 'html';
  });

  try {
    switch (fw) {
      case 'angular':
        await page.waitForFunction(() =>
          window.getAllAngularTestabilities?.()?.every(t => t.isStable()) ?? true
        , { timeout: 10000 }); break;
      case 'blazor':
        await page.waitForTimeout(1500); break;
      case 'react':
      case 'vue':
        await page.waitForLoadState('networkidle'); break;
    }
  } catch(_) {}

  return fw;
}

// ── Extract every element exactly as it exists — no category mapping ──────────
async function extractFromPage(page, pageName, pageUrl, fw) {
  return await page.evaluate(({ pageName, pageUrl, fw }) => {

    function bestSelector(el) {
      if (el.getAttribute('data-testid'))       return `[data-testid="${el.getAttribute('data-testid')}"]`;
      if (el.getAttribute('data-cy'))           return `[data-cy="${el.getAttribute('data-cy')}"]`;
      if (el.getAttribute('formcontrolname'))   return `[formcontrolname="${el.getAttribute('formcontrolname')}"]`;
      const id = el.id;
      if (id && !/ctl\d+_|ContentPlaceHolder|MasterPage|\$/.test(id)) return `#${id}`;
      const nm = el.getAttribute('name');
      if (nm && !/\$/.test(nm))                 return `[name="${nm}"]`;
      if (el.getAttribute('aria-label'))        return `[aria-label="${el.getAttribute('aria-label')}"]`;
      if (el.placeholder)                       return `[placeholder="${el.placeholder}"]`;
      const txt = el.innerText?.trim().replace(/\s+/g, ' ').slice(0, 40);
      if (txt && !['INPUT','SELECT','TEXTAREA'].includes(el.tagName)) return `text=${txt}`;
      if (el.tagName === 'INPUT' && el.type)    return `input[type="${el.type}"]`;
      const cls = [...el.classList].find(c => !c.match(/active|focus|hover|selected|ng-|js-|is-|has-|v-/));
      return cls ? `${el.tagName.toLowerCase()}.${cls}` : el.tagName.toLowerCase();
    }

    function isVisible(el) {
      const r = el.getBoundingClientRect();
      const s = window.getComputedStyle(el);
      return r.width > 0 && r.height > 0 &&
        s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
    }

    const QUERY = [
      'input:not([type="hidden"])',
      'button',
      'a[href]',
      'select',
      'textarea',
      '[role="button"]',
      '[role="tab"]',
      '[role="checkbox"]',
      '[role="slider"]',
      '[role="menuitem"]',
      '[role="link"]',
      '[onclick]',
      '[data-toggle]',
      '[data-bs-toggle]',
      '[formcontrolname]',
    ].join(',');

    return [...document.querySelectorAll(QUERY)]
      .filter(isVisible)
      .map(el => ({
        pageName,
        pageUrl,
        framework: fw,
        tag:       el.tagName.toLowerCase(),
        type:      el.type   || null,
        role:      el.getAttribute('role') || null,
        text:      el.innerText?.trim().replace(/\s+/g, ' ').slice(0, 100) || null,
        placeholder: el.placeholder || null,
        ariaLabel: el.getAttribute('aria-label') || null,
        href:      el.href   || null,
        selector:  bestSelector(el),
        rawId:     el.id     || null,
      }));
  }, { pageName, pageUrl, fw });
}

// ── Discover all pages reachable from APP_URL ─────────────────────────────────
async function discoverPages(page) {
  const visited = new Set();
  const queue   = [APP_URL];
  const pages   = [];

  // Try sitemap first
  try {
    const r = await page.goto(`${new URL(APP_URL).origin}/sitemap.xml`, { timeout: 6000 });
    if (r?.ok()) {
      const xml = await page.content();
      [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].forEach(m => {
        try { if (new URL(m[1]).hostname === BASE_HOST) queue.push(m[1].trim()); } catch(_) {}
      });
    }
  } catch(_) {}

  while (queue.length && pages.length < MAX_PAGES) {
    const url = queue.shift();
    if (visited.has(url)) continue;
    visited.add(url);

    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
      const fw = await waitForPage(page);

      // Page name from URL path/filename
      const pathname = new URL(url).pathname;
      const name = pathname
        .replace(/^\/|\/$/g, '')
        .replace(/\.[^.]+$/, '')          // remove extension
        .replace(/\//g, '__')             // slashes → __
        || 'home';

      pages.push({ name, url, fw });
      console.log(`  ✓ [${name}] (${fw}) → ${url}`);

      // Collect internal nav/menu links only (avoids crawling every href)
      const links = await page.evaluate((host) => {
        const scope = 'nav a, header a, aside a, [role="navigation"] a, [class*="nav"] a, [class*="menu"] a, [class*="sidebar"] a';
        return [...document.querySelectorAll(scope)]
          .map(a => a.href)
          .filter(h => {
            try {
              const u = new URL(h);
              return u.hostname === host && !h.includes('#') && !/\.(jpg|png|pdf|svg|css|js|xml|zip)$/i.test(h);
            } catch { return false; }
          });
      }, BASE_HOST);

      links.forEach(l => { if (!visited.has(l)) queue.push(l); });

    } catch(e) {
      console.warn(`  ✗ ${url} — ${e.message}`);
    }
  }

  // Single page / no nav links found → use entry URL directly
  if (pages.length === 0) {
    const pathname = new URL(APP_URL).pathname;
    const name = pathname.replace(/^\/|\/$/g, '').replace(/\.[^.]+$/, '').replace(/\//g, '__') || 'home';
    pages.push({ name, url: APP_URL, fw: 'html' });
  }

  return pages;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
async function login(page) {
  await page.goto(APP_URL, { waitUntil: 'networkidle' });
  for (const s of ['input[type="email"]','input[name="username"]','input[name="UserName"]','#username','#email','[formcontrolname="username"]'])
    { const e = await page.$(s); if (e) { await e.fill(AUTH_USER); break; } }
  for (const s of ['input[type="password"]','#password','[formcontrolname="password"]'])
    { const e = await page.$(s); if (e) { await e.fill(AUTH_PASS); break; } }
  for (const s of ['button[type="submit"]','input[type="submit"]','button:has-text("Login")','button:has-text("Sign in")'])
    { const e = await page.$(s); if (e) { await e.click(); break; } }
  await page.waitForLoadState('networkidle').catch(() => {});
}

// ── Main ──────────────────────────────────────────────────────────────────────
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
  });
  const page = await context.newPage();

  if (AUTH_USER && AUTH_PASS) {
    console.log('→ Authenticating...');
    await login(page);
    await context.storageState({ path: 'auth-state.json' });
    console.log('✓ Session saved → auth-state.json');
  }

  console.log(`\n→ Discovering pages from ${APP_URL}...\n`);
  const pages = await discoverPages(page);
  console.log(`\n→ ${pages.length} page(s) found. Extracting elements...\n`);

  const result = {};
  let total = 0;

  for (const { name, url, fw } of pages) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await waitForPage(page);
    const elements = await extractFromPage(page, name, url, fw);
    result[name] = elements;
    total += elements.length;
    console.log(`✓ [${name}] → ${elements.length} elements`);
  }

  fs.writeFileSync('selectors.json', JSON.stringify(result, null, 2));
  console.log(`\n✓ selectors.json written — ${pages.length} page(s), ${total} elements total`);
  console.log('→ Next: node generate-tests.js');
  await browser.close();
})();