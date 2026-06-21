const fs = require('fs');
const path = require('path');
const vm = require('vm');

const HTML_PATH = path.join(__dirname, '..', 'media', 'flowbuilder.html');

const EXPORT_SHIM = `
;globalThis.__t = {
  getNodes: () => nodes,
  getEdges: () => edges,
  getLanes: () => (typeof lanes !== 'undefined' ? lanes : []),
  reset: () => { nodes = []; edges = []; if (typeof lanes !== 'undefined') lanes = []; },
  parseDSL,
  parseArrow,
  parseSequence,
  parseMermaid,
  parseJSON,
  parseYAML,
  parseMarkdown,
  parseStateDiagram,
  parseERDiagram,
  autoLayout,
  setDSLValue: (v) => { document.getElementById('dsl-input').value = v; }
};
`;

function extractScripts(html) {
  const re = /<script[^>]*>([\s\S]*?)<\/script>/g;
  let m, out = [];
  while ((m = re.exec(html)) !== null) out.push(m[1]);
  return out.join('\n');
}

function makeCtxStub() {
  const noop = () => {};
  return {
    save: noop, restore: noop, beginPath: noop, closePath: noop,
    moveTo: noop, lineTo: noop, bezierCurveTo: noop, quadraticCurveTo: noop,
    arc: noop, arcTo: noop, ellipse: noop, rect: noop, roundRect: noop,
    fill: noop, stroke: noop, clearRect: noop, fillRect: noop,
    translate: noop, scale: noop, rotate: noop, setLineDash: noop,
    measureText: (t) => ({ width: (t || '').length * 6 }),
    fillText: noop, strokeText: noop,
    createLinearGradient: () => ({ addColorStop: noop }),
    getImageData: () => ({ data: new Uint8ClampedArray(4) }),
    putImageData: noop,
    set fillStyle(v) {}, get fillStyle() { return '#000'; },
    set strokeStyle(v) {}, get strokeStyle() { return '#000'; },
    set lineWidth(v) {}, set font(v) {}, set textAlign(v) {}, set textBaseline(v) {},
    set globalAlpha(v) {}, set shadowColor(v) {}, set shadowBlur(v) {}, set shadowOffsetY(v) {},
    set lineDashOffset(v) {}
  };
}

function makeElementStub(tag) {
  const children = [];
  const el = {
    tagName: (tag || 'div').toUpperCase(),
    style: {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    children, childNodes: children, dataset: {},
    addEventListener: () => {}, removeEventListener: () => {},
    appendChild: (c) => { children.push(c); return c; },
    setAttribute: () => {}, getAttribute: () => null,
    querySelector: () => makeElementStub('div'), querySelectorAll: () => [],
    getContext: (type) => (type === '2d' ? makeCtxStub() : null),
    getBoundingClientRect: () => ({ width: 1000, height: 700, left: 0, top: 0 }),
    get clientWidth() { return 1000; }, get clientHeight() { return 700; },
    get value() { return this._value || ''; }, set value(v) { this._value = v; },
    focus: () => {}, click: () => {}, remove: () => {}, innerHTML: '', textContent: ''
  };
  return el;
}

function buildSandbox() {
  const elements = {};
  const documentStub = {
    getElementById: (id) => elements[id] || (elements[id] = makeElementStub('div')),
    createElement: (tag) => makeElementStub(tag),
    querySelectorAll: () => [],
    addEventListener: () => {},
    documentElement: { classList: { toggle: () => {} } },
    body: makeElementStub('body')
  };

  const sandbox = {
    console,
    document: documentStub,
    matchMedia: () => ({ matches: false, addEventListener: () => {} }),
    requestAnimationFrame: () => 0,
    cancelAnimationFrame: () => {},
    location: { href: 'file:///test.html', hash: '', pathname: '/test.html' },
    history: { replaceState: () => {} },
    btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    navigator: { clipboard: { writeText: async () => {}, write: async () => {} } },
    localStorage: {
      _store: {},
      getItem(k) { return this._store[k] || null; },
      setItem(k, v) { this._store[k] = v; },
      removeItem(k) { delete this._store[k]; }
    },
    ResizeObserver: class { observe() {} disconnect() {} },
    ClipboardItem: class {},
    prompt: () => null,
    confirm: () => true,
    addEventListener: () => {}, removeEventListener: () => {},
    setTimeout, clearTimeout,
    Buffer, Uint8Array, Uint8ClampedArray,
    Math, JSON, Array, Object, String, Number, Set, Map, Promise, RegExp,
    parseInt, parseFloat, isNaN
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  return sandbox;
}

// Loads a FRESH, fully isolated copy of the real parser code from
// media/flowbuilder.html into its own vm.Context. No state, no const/let
// redeclaration issues, no cross-test leakage — exactly like opening the
// file fresh in a new browser tab each time.
function loadHarness() {
  const html = fs.readFileSync(HTML_PATH, 'utf8');
  const js = extractScripts(html) + EXPORT_SHIM;
  const sandbox = buildSandbox();
  const context = vm.createContext(sandbox);
  vm.runInContext(js, context, { filename: 'flowbuilder.html', timeout: 5000 });
  return sandbox.__t;
}

module.exports = { loadHarness };
