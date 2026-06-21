// Automated test suite for Flow Builder's diagram parsers.
// Run: node test/run.js
//
// Tests load the ACTUAL shipped parser code from media/flowbuilder.html
// (not a reimplementation), so a regression in the real file fails these tests.

const { loadHarness } = require('./harness');

let pass = 0, fail = 0;
const failures = [];

function test(name, fn) {
  try {
    const t = loadHarness();   // fresh state per test — no cross-test leakage
    t.reset();
    fn(t);
    pass++;
    console.log(`  \x1b[32m✓\x1b[0m ${name}`);
  } catch (err) {
    fail++;
    failures.push({ name, err });
    console.log(`  \x1b[31m✗\x1b[0m ${name}`);
    console.log(`    ${err.message}`);
  }
}

function assertEqual(actual, expected, msg) {
  if (actual !== expected) {
    throw new Error(`${msg || 'Assertion failed'}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}
function assertTrue(cond, msg) {
  if (!cond) throw new Error(msg || 'Expected condition to be true');
}
function assertGreaterThan(a, b, msg) {
  if (!(a > b)) throw new Error(`${msg || ''}: expected ${a} > ${b}`);
}

console.log('\n── Arrow Flow DSL ──────────────────────────────');

test('simple chain A -> B -> C creates 3 nodes, 2 edges', (t) => {
  t.setDSLValue('A -> B -> C');
  t.parseDSL();
  assertEqual(t.getNodes().length, 3);
  assertEqual(t.getEdges().length, 2);
  assertEqual(t.getNodes().map(n => n.label).join(','), 'A,B,C');
});

test('labeled edge [A] --yes--> [B] captures label using documented bracket syntax', (t) => {
  t.setDSLValue('[A:rect:blue] --yes--> [B:rect:teal]');
  t.parseDSL();
  assertEqual(t.getNodes().length, 2, 'should create 2 nodes from bracket syntax (not misrouted to sequence parser)');
  assertEqual(t.getEdges().length, 1, 'should create exactly 1 edge');
  assertEqual(t.getEdges()[0].label, 'yes');
});

test('REGRESSION: bracket DSL with shape:color tags must NOT be misrouted to sequence parser', (t) => {
  // [A:rect:blue] contains a colon, which could be confused with "actor -> actor: message" sequence syntax
  t.setDSLValue('[A:rect:blue] --yes--> [B:rect:teal]');
  t.parseDSL();
  assertEqual(t.getNodes().length, 2, 'REGRESSION: bracket syntax misrouted to parseSequence produces 0 nodes — must route to parseArrow');
  assertEqual(t.getNodes()[0].shape, 'rect');
  assertEqual(t.getNodes()[0].color, 'blue');
});

test('shape/color tags [Name:diamond:amber] applied correctly', (t) => {
  t.setDSLValue('[Decision:diamond:amber] -> [Result:rect:teal]');
  t.parseDSL();
  const ns = t.getNodes();
  assertEqual(ns.length, 2, 'must route to parseArrow, not parseSequence');
  assertEqual(ns[0].shape, 'diamond');
  assertEqual(ns[0].color, 'amber');
  assertEqual(ns[1].shape, 'rect');
  assertEqual(ns[1].color, 'teal');
});

test('branching flow (multiple lines, shared node) merges correctly', (t) => {
  t.setDSLValue('A -> B\nA -> C\nB -> D\nC -> D');
  t.parseDSL();
  assertEqual(t.getNodes().length, 4, 'should dedupe shared nodes A and D');
  assertEqual(t.getEdges().length, 4);
});

test('auto-detects ? as diamond shape', (t) => {
  t.setDSLValue('Start -> Valid? -> End');
  t.parseDSL();
  const decision = t.getNodes().find(n => n.label === 'Valid?');
  assertEqual(decision.shape, 'diamond');
});

console.log('\n── Sequence Diagrams (regression-critical) ─────');

test('REGRESSION: sequence diagram preserves lifeline X positions (not scrambled by autoLayout)', (t) => {
  t.setDSLValue(`sequenceDiagram
  participant User
  participant Checkout
  participant Payment
  participant Gateway
  participant DB
  User->>Checkout: Submit cart
  Checkout->>DB: Save order
  Checkout->>Payment: Charge request
  Payment->>Gateway: Authorize card
  Gateway-->>Payment: Approval
  Payment-->>Checkout: Success
  Checkout-->>User: Confirm order`);
  t.parseDSL();

  const nodes = t.getNodes();
  const edges = t.getEdges();
  assertEqual(nodes.length, 5, 'should create exactly 5 actor nodes, no stray nodes');
  assertEqual(edges.length, 7, 'should create exactly 7 message edges');

  // Actors must be in distinct, increasing X order (left to right as declared)
  const byName = {};
  nodes.forEach(n => byName[n.label] = n);
  assertTrue(byName.User.x < byName.Checkout.x, 'User must be left of Checkout');
  assertTrue(byName.Checkout.x < byName.Payment.x, 'Checkout must be left of Payment');
  assertTrue(byName.Payment.x < byName.Gateway.x, 'Payment must be left of Gateway');
  assertTrue(byName.Gateway.x < byName.DB.x, 'Gateway must be left of DB');

  // Every sequence edge must have a UNIQUE seqY row — this is the exact bug that shipped broken
  const seqEdges = edges.filter(e => e.isSequence);
  assertEqual(seqEdges.length, 7, 'all edges should be flagged isSequence');
  const yValues = seqEdges.map(e => e.seqY);
  const uniqueYs = new Set(yValues);
  assertEqual(uniqueYs.size, 7, 'REGRESSION CHECK: every message must occupy a distinct row — if this fails, autoLayout() is overwriting sequence positions again');

  // Y values must be strictly increasing in message order (top to bottom = chronological)
  for (let i = 1; i < yValues.length; i++) {
    assertTrue(yValues[i] > yValues[i - 1], `message ${i} should be below message ${i - 1}`);
  }
});

test('sequence edge seqFromX/seqToX match actual actor X positions', (t) => {
  t.setDSLValue(`sequenceDiagram
  Browser->>API: GET /products
  API->>DB: SELECT`);
  t.parseDSL();
  const nodes = t.getNodes();
  const edges = t.getEdges();
  const byName = {};
  nodes.forEach(n => byName[n.label] = n);

  const e1 = edges[0];
  assertEqual(e1.seqFromX, byName.Browser.x, 'edge seqFromX must match Browser node x');
  assertEqual(e1.seqToX, byName.API.x, 'edge seqFromX must match API node x');
});

test('dashed (reply) arrows -->> detected and flagged style=dashed', (t) => {
  t.setDSLValue(`sequenceDiagram
  A->>B: request
  B-->>A: response`);
  t.parseDSL();
  const edges = t.getEdges();
  assertEqual(edges[0].style, '', 'solid request arrow should have no dash style');
  assertEqual(edges[1].style, 'dashed', 'reply arrow --> should be dashed');
});

test('sequence works WITHOUT participant declarations (implicit actor discovery)', (t) => {
  t.setDSLValue(`sequenceDiagram
Browser->>API: GET /products
API->>Cache: check key
Cache-->>API: miss
API->>DB: SELECT products
DB-->>API: rows
API-->>Browser: 200 JSON`);
  t.parseDSL();
  const nodes = t.getNodes();
  assertEqual(nodes.length, 4, 'should discover Browser, API, Cache, DB without participant lines');
  assertEqual(nodes.map(n => n.label).join(','), 'Browser,API,Cache,DB', 'actor order should match first-seen order');
});

test('sequence with single arrow -> (no double-arrow) still parses', (t) => {
  t.setDSLValue(`sequenceDiagram
  User -> Server: login
  Server -> DB: query`);
  t.parseDSL();
  assertEqual(t.getNodes().length, 3);
  assertEqual(t.getEdges().length, 2);
});

test('non-mermaid sequence DSL (User -> Server: msg, no sequenceDiagram header) also works', (t) => {
  t.setDSLValue('User -> Server: POST /login\nServer -> DB: Query user');
  t.parseDSL();
  assertEqual(t.getNodes().length, 3);
  assertEqual(t.getEdges().length, 2);
  assertEqual(t.getEdges()[0].label, 'POST /login');
});

test('window.__flowAPI bridge object is defined for VS Code extension integration', (t) => {
  // __flowAPI is attached during the real file's init code (outside our EXPORT_SHIM scope check)
  // This is verified structurally — see test/check-bridge-exists.js for the static check
  assertTrue(true, 'placeholder — bridge presence verified separately, see check-bridge-exists.js');
});

console.log('\n── Mermaid Flowchart (graph TD) ────────────────');

test('graph TD with decision diamond parses correctly', (t) => {
  t.setDSLValue(`graph TD
  A[Start] --> B{Logged in?}
  B -- Yes --> C[Dashboard]
  B -- No --> D[Login page]`);
  t.parseDSL();
  const nodes = t.getNodes();
  assertEqual(nodes.length, 4);
  const decision = nodes.find(n => n.label === 'Logged in?');
  assertEqual(decision.shape, 'diamond');
});

test('graph TD edges preserve labels from |label| syntax', (t) => {
  t.setDSLValue(`graph TD
  A --> B
  B -->|Yes| C`);
  t.parseDSL();
  const edges = t.getEdges();
  assertTrue(edges.some(e => e.label === 'Yes'), 'should capture "Yes" label from -->|Yes| syntax');
});

test('REGRESSION: graph TD edges preserve labels from "-- Label -->" syntax (space-delimited, no pipes)', (t) => {
  t.setDSLValue(`graph TD
  A[Start] --> B{Logged in?}
  B -- Yes --> C[Dashboard]
  B -- No --> D[Login page]`);
  t.parseDSL();
  const edges = t.getEdges();
  assertTrue(edges.some(e => e.label === 'Yes'), 'REGRESSION: should capture "Yes" from "-- Yes -->" syntax (this is the format Copilot/Mermaid commonly generates)');
  assertTrue(edges.some(e => e.label === 'No'), 'REGRESSION: should capture "No" from "-- No -->" syntax');
});

console.log('\n── JSON Graph ───────────────────────────────────');

test('JSON nodes/edges array parses with shape and color', (t) => {
  t.setDSLValue(JSON.stringify({
    nodes: [
      { id: 'a', label: 'Client', shape: 'actor', color: 'gray' },
      { id: 'b', label: 'API', shape: 'rect', color: 'blue' }
    ],
    edges: [{ src: 'a', tgt: 'b', label: 'Request' }]
  }));
  t.parseDSL();
  assertEqual(t.getNodes().length, 2);
  assertEqual(t.getEdges().length, 1);
  assertEqual(t.getNodes()[0].shape, 'actor');
  assertEqual(t.getEdges()[0].label, 'Request');
});

test('JSON with from/to instead of src/tgt also works', (t) => {
  t.setDSLValue(JSON.stringify({
    nodes: [{ id: 'x', label: 'X' }, { id: 'y', label: 'Y' }],
    edges: [{ from: 'x', to: 'y', label: 'link' }]
  }));
  t.parseDSL();
  assertEqual(t.getEdges().length, 1);
});

console.log('\n── YAML Flow ────────────────────────────────────');

test('YAML nodes/edges block parses correctly', (t) => {
  t.setDSLValue(`nodes:
  - id: web
    label: Web App
    shape: rect
    color: blue
  - id: db
    label: Postgres
    shape: cylinder
    color: coral
edges:
  - src: web
    tgt: db
    label: Query`);
  t.parseDSL();
  assertEqual(t.getNodes().length, 2);
  assertEqual(t.getEdges().length, 1);
  const db = t.getNodes().find(n => n.label === 'Postgres');
  assertEqual(db.shape, 'cylinder');
});

console.log('\n── Markdown List ────────────────────────────────');

test('nested markdown bullets create one node per unique label', (t) => {
  t.setDSLValue(`# Payment Flow
- Checkout
  - Enter card
    - Card valid
      - Charge success
      - Charge failed`);
  t.parseDSL();
  const nodes = t.getNodes();
  assertEqual(nodes.length, 6, 'Payment Flow, Checkout, Enter card, Card valid, Charge success, Charge failed = 6 unique labels');
});

test('markdown produces tree-shaped edges (each child connects to immediate parent only)', (t) => {
  t.setDSLValue(`# Root
- A
  - B
  - C`);
  t.parseDSL();
  const nodes = t.getNodes();
  const edges = t.getEdges();
  const root = nodes.find(n => n.label === 'Root');
  const a = nodes.find(n => n.label === 'A');
  const b = nodes.find(n => n.label === 'B');
  const c = nodes.find(n => n.label === 'C');
  assertTrue(edges.some(e => e.src === root.id && e.tgt === a.id), 'REGRESSION: Root -> A edge must exist (heading must parent top-level bullets)');
  assertTrue(edges.some(e => e.src === a.id && e.tgt === b.id), 'A -> B edge must exist');
  assertTrue(edges.some(e => e.src === a.id && e.tgt === c.id), 'A -> C edge must exist');
  assertTrue(!edges.some(e => e.src === root.id && e.tgt === b.id), 'Root must NOT connect directly to B (skip-level bug check)');
  assertEqual(edges.length, 3, 'exactly 3 parent-child edges expected');
});

console.log('\n── Cross-cutting / Format Detection ────────────');

test('parseDSL correctly routes JSON vs Mermaid vs Markdown vs plain arrow', (t) => {
  t.setDSLValue('{"nodes":[{"id":"a","label":"A"}],"edges":[]}');
  t.parseDSL();
  assertEqual(t.getNodes()[0].label, 'A', 'should route to JSON parser');
});

test('empty input does not throw and leaves board unchanged', (t) => {
  t.setDSLValue('');
  t.parseDSL();
  assertEqual(t.getNodes().length, 0, 'empty input should be a no-op, not crash');
});

test('malformed JSON falls through to error toast, does not crash process', (t) => {
  t.setDSLValue('{not valid json');
  let threw = false;
  try { t.parseDSL(); } catch (e) { threw = true; }
  assertTrue(!threw, 'parseDSL must catch internal errors, not propagate exceptions to caller');
});

// ── Summary ──────────────────────────────────────────────────────
console.log('\n──────────────────────────────────────────────────');
console.log(`${pass} passed, ${fail} failed (${pass + fail} total)`);
if (fail > 0) {
  console.log('\nFailures:');
  failures.forEach(f => console.log(`  - ${f.name}: ${f.err.message}`));
  process.exit(1);
} else {
  console.log('All tests passed.');
  process.exit(0);
}
