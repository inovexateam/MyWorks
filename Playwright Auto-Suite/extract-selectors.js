/**
 * extract-selectors.js
 * Auto-discovers ALL pages from app — no hardcoded URLs.
 * Crawls sitemap / nav links / href links recursively.
 * Run: APP_URL=https://your-app.com node extract-selectors.js
 */

const { chromium } = require('@playwright/test');
const fs  = require('fs');
const url = require('url');

const APP_URL   = process.env.APP_URL   || 'https://your-app.com';
const AUTH_USER = process.env.AUTH_USER || '';
const AUTH_PASS = process.env.AUTH_PASS || '';
const MAX_PAGES = parseInt(process.env.MAX_PAGES || '20'); // safety cap

const BASE_HOST = new URL(APP_URL).hostname;

// ── Framework detection ──────────────────────────────────────────────────────
async function detectFramework(page) {
  return await page.evaluate(() => {
    if (document.querySelector('[ng-version],[_nghost],app-root'))            return 'angular';
    if (document.querySelector('#__NEXT_DATA__,[data-reactroot]'))            return 'react';
    if (document.querySelector('#__nuxt,[data-v-]'))                          return 'vue';
    if (document.querySelector('script[src*="blazor"]') || window.__blazorSignalR) return 'blazor';
    if (document.querySelector('input[name*="__VIEWSTATE"],[id*="ctl00"]'))   return 'aspx';
    return 'html';
  });
}

// ── Smart wait per framework ─────────────────────────────────────────────────
async function waitForFramework(page, fw) {
  try {
    switch (fw) {
      case 'angular':
        await page.waitForFunction(() =>
          window.getAllAngularTestabilities?.()?.every(t => t.isStable()) ?? true
        , { timeout: 15000 });
        break;
      case 'blazor':
        await page.waitForFunction(() =>
          !document.querySelector('blazor-error-ui') && document.readyState === 'complete'
        , { timeout: 20000 });
        await page.waitForTimeout(1500);
        break;
      case 'react':
      case 'vue':
        await page.waitForSelector('#root,#app,#__nuxt,[data-reactroot]', { timeout: 10000 });
        await page.waitForLoadState('networkidle');
        break;
      default:
        await page.waitForLoadState('networkidle');
    }
  } catch (_) {
    await page.waitForLoadState('networkidle').catch(() => {});
  }
}

// ── Discover all internal page URLs ─────────────────────────────────────────
async function discoverPages(page) {
  const visited = new Set();
  const toVisit = [APP_URL];
  const found   = [];

  // 1. Try sitemap.xml first
  try {
    const sitemapRes = await page.goto(`${APP_URL}/sitemap.xml`, { timeout: 8000 });
    if (sitemapRes?.ok()) {
      const content = await page.content();
      const matches = [...content.matchAll(/<loc>(.*?)<\/loc>/g)];
      matches.forEach(m => {
        const u = m[1].trim();
        if (new URL(u).hostname === BASE_HOST) toVisit.push(u);
      });
      console.log(`✓ sitemap.xml → ${matches.length} URLs found`);
    }
  } catch (_) {
    console.log('  sitemap.xml not found, crawling nav links...');
  }

  // 2. Crawl app recursively via nav/sidebar links
  while (toVisit.length && found.length < MAX_PAGES) {
    const current = toVisit.shift();
    if (visited.has(current)) continue;
    visited.add(current);

    try {
      await page.goto(current, { waitUntil: 'domcontentloaded', timeout: 15000 });
      const fw = await detectFramework(page);
      await waitForFramework(page, fw);

      // Derive page name from pathname
      const pathname = new URL(current).pathname.replace(/^\/|\/$/g, '') || 'home';
      const name     = pathname.replace(/\//g, '_') || 'home';

      found.push({ name, url: current, framework: fw });
      console.log(`  found: [${name}] (${fw}) → ${current}`);

      // Collect internal links from nav, sidebar, menu — not all hrefs (avoids noise)
      const newLinks = await page.evaluate((baseHost) => {
        const NAV_SCOPE = 'nav a, [role="navigation"] a, aside a, header a, [class*="sidebar"] a, [class*="menu"] a, [class*="nav"] a';
        return [...document.querySelectorAll(NAV_SCOPE)]
          .map(a => a.href)
          .filter(h => {
            try {
              const u = new URL(h);
              return u.hostname === baseHost &&
                !h.includes('#') &&
                !h.match(/\.(pdf|jpg|png|gif|svg|css|js|xml|zip)$/i);
            } catch { return false; }
          });
      }, BASE_HOST);

      newLinks.forEach(l => { if (!visited.has(l)) toVisit.push(l); });
    } catch (e) {
      console.warn(`  ✗ skipped ${current}: ${e.message}`);
    }
  }

  return found;
}

// ── Extract selectors ────────────────────────────────────────────────────────
async function extractSelectors(page, pageName, fw) {
  return await page.evaluate(({ name, fw }) => {
    function best(el) {
      if (el.getAttribute('data-testid'))    return `[data-testid="${el.getAttribute('data-testid')}"]`;
      if (fw === 'angular') {
        if (el.getAttribute('data-cy'))      return `[data-cy="${el.getAttribute('data-cy')}"]`;
        if (el.getAttribute('formcontrolname')) return `[formcontrolname="${el.getAttribute('formcontrolname')}"]`;
      }
      const id = el.id;
      if (id && !/ctl\d+_|ContentPlaceHolder|MasterPage|\$/.test(id)) return `#${id}`;
      const nm = el.getAttribute('name');
      if (nm && !/\$/.test(nm))             return `[name="${nm}"]`;
      if (el.getAttribute('aria-label'))    return `[aria-label="${el.getAttribute('aria-label')}"]`;
      if (el.placeholder)                   return `[placeholder="${el.placeholder}"]`;
      if (fw === 'blazor' && el.getAttribute('_bl_')) return `[_bl_="${el.getAttribute('_bl_')}"]`;
      const text = el.innerText?.trim().replace(/\s+/g,' ').slice(0,40);
      if (text && !['INPUT','SELECT','TEXTAREA'].includes(el.tagName)) return `text=${text}`;
      if (el.tagName === 'INPUT' && el.type) return `input[type="${el.type}"]`;
      const sc = [...el.classList].find(c => !c.match(/active|focus|hover|selected|ng-|js-|is-|has-|v-/));
      return sc ? `${el.tagName.toLowerCase()}.${sc}` : el.tagName.toLowerCase();
    }

    function isVisible(el) {
      const r = el.getBoundingClientRect();
      const s = window.getComputedStyle(el);
      return r.width > 0 && r.height > 0 &&
        s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
    }

    const INTERACTIVE = [
      'input:not([type="hidden"])','button','a[href]','select','textarea',
      '[role="button"]','[role="link"]','[role="menuitem"]','[role="tab"]',
      '[onclick]','label[for]','[data-toggle]','[data-bs-toggle]',
      '[formcontrolname]','[mat-button]','[mat-raised-button]',
    ].join(',');

    return [...document.querySelectorAll(INTERACTIVE)]
      .filter(isVisible)
      .map(el => ({
        page:        name,
        framework:   fw,
        tag:         el.tagName.toLowerCase(),
        type:        el.type || null,
        text:        el.innerText?.trim().replace(/\s+/g,' ').slice(0,80) || null,
        placeholder: el.placeholder || null,
        ariaLabel:   el.getAttribute('aria-label') || null,
        role:        el.getAttribute('role') || el.tagName.toLowerCase(),
        selector:    best(el),
        rawId:       el.id || null,
      }));
  }, { name: pageName, fw });
}

// ── Auth ─────────────────────────────────────────────────────────────────────
async function login(page) {
  console.log('→ Logging in...');
  await page.goto(`${APP_URL}/login`, { waitUntil: 'networkidle' }).catch(() =>
    page.goto(APP_URL, { waitUntil: 'networkidle' })
  );
  const fw = await detectFramework(page);
  await waitForFramework(page, fw);

  const userTry   = ['input[type="email"]','input[name="username"]','input[name="email"]',
                     'input[name="UserName"]','#UserName','#username','#email',
                     '[formcontrolname="username"]','[formcontrolname="email"]',
                     'input[placeholder*="user" i]','input[placeholder*="email" i]'];
  const passTry   = ['input[type="password"]','input[name="password"]','input[name="Password"]',
                     '#password','#Password','[formcontrolname="password"]'];
  const submitTry = ['button[type="submit"]','input[type="submit"]',
                     'button:has-text("Login")','button:has-text("Sign in")','button:has-text("Log in")'];

  for (const s of userTry)   { const e = await page.$(s); if (e) { await e.fill(AUTH_USER); break; } }
  for (const s of passTry)   { const e = await page.$(s); if (e) { await e.fill(AUTH_PASS); break; } }
  for (const s of submitTry) { const e = await page.$(s); if (e) { await e.click();         break; } }

  await page.waitForLoadState('networkidle').catch(() => {});
  console.log('✓ Auth done');
}

// ── Main ─────────────────────────────────────────────────────────────────────
(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
  });
  const page = await context.newPage();

  if (AUTH_USER && AUTH_PASS) {
    await login(page);
    await context.storageState({ path: 'auth-state.json' });
    console.log('✓ Session saved → auth-state.json\n');
  }

  // Auto-discover all pages
  console.log(`\n→ Crawling ${APP_URL} (max ${MAX_PAGES} pages)...\n`);
  const pages = await discoverPages(page);
  console.log(`\n→ ${pages.length} pages discovered. Extracting selectors...\n`);

  const allSelectors = {};
  let total = 0;

  for (const { name, url: pageUrl, framework } of pages) {
    try {
      await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
      await waitForFramework(page, framework);
      const found = await extractSelectors(page, name, framework);
      allSelectors[name] = found;
      total += found.length;
      console.log(`✓ [${name}] ${found.length} selectors (${framework})`);
    } catch (e) {
      console.warn(`✗ [${name}] ${e.message}`);
      allSelectors[name] = [];
    }
  }

  fs.writeFileSync('selectors.json', JSON.stringify(allSelectors, null, 2));
  console.log(`\n✓ selectors.json — ${pages.length} pages, ${total} selectors`);
  console.log('→ Next: node generate-tests.js');
  await browser.close();
})();