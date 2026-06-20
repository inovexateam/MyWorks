# OCP / APIGEE Service Console

Single-file HTML prototype. Open `ocp-apigee-tool.html` directly in any browser — no build, no server.

## What's real vs. simulated

| Area | Status |
|---|---|
| UI/UX, layout, navigation | Real — fully functional |
| Catalog (apps/services) | **Simulated** — generated client-side in JS, not from APIGEE |
| Token acquisition | **Simulated** — fake token after ~1s delay |
| Execute Request | **Real fetch()** — actually hits the URL shown, will fail/CORS-block against real APIGEE until backend wiring is done |
| Admin "Discover" proxy import | **Simulated** — hardcoded response, no real APIGEE Management API call |

This is a UX/architecture prototype. Treat it as the spec for what to build, not the finished product.

## Layout

- **Tester mode**: rail (pinned apps) → sidebar (services for selected app) → split pane: Request (left) / Response (right), Postman-style.
- **Admin mode**: Import Proxy → Service Catalog → Token Config, as tabs.
- **⌘K** anywhere opens global search across all apps/services — always visible as a search bar in the topbar too, not hidden behind a shortcut.

## To make this production-real

1. **Catalog source** — replace `buildCatalog()` / `CATALOG` array with a `fetch('/api/catalog')` call to your own backend, which in turn reads from a persisted store (Postgres/Git-backed JSON) populated by the Admin import flow.
2. **Token acquisition** (`openApp()`, `renderForm()`) — replace the `setTimeout` fake token with a real `fetch(tokenUrl, {method:'POST', body: client_credentials grant})` against your OAuth2/APIGEE token endpoint. Cache per app + environment, respect expiry.
3. **Admin "Discover"** (`parseProxy()`) — wire to APIGEE Management API: `GET /v1/organizations/{org}/apis/{api}/revisions/{rev}/resources` or fetch the proxy's attached OpenAPI spec. Parse `paths` to extract method/path/params instead of the current `FAKE_OPS` stub.
4. **CORS** — APIGEE proxies must allow the origin this tool is served from, or route Execute through your own backend as a relay to avoid browser CORS blocks.
5. **Secrets** — client secrets must never live in browser JS in production. Move token issuance server-side; the browser should only ever see a short-lived access token, not the client secret.

## File map

- `ocp-apigee-tool.html` — everything (HTML/CSS/JS), single file, no dependencies except Google Fonts CDN.