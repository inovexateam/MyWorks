// Static structural check — confirms the __flowAPI bridge used by the VS Code
// extension (extension.js postMessage -> loadMermaid) exists in the shipped
// file AND that it correctly skips autoLayout() for sequence diagrams.
// This complements run.js's behavioral tests with a source-level guarantee.

const fs = require('fs');
const path = require('path');

const HTML_PATH = path.join(__dirname, '..', 'media', 'flowbuilder.html');
const html = fs.readFileSync(HTML_PATH, 'utf8');

let pass = 0, fail = 0;

function check(name, fn) {
  try {
    fn();
    pass++;
    console.log(`  \x1b[32m✓\x1b[0m ${name}`);
  } catch (err) {
    fail++;
    console.log(`  \x1b[31m✗\x1b[0m ${name}`);
    console.log(`    ${err.message}`);
  }
}

console.log('\n── Static Bridge Checks ─────────────────────────');

check('window.__flowAPI is defined in the shipped HTML', () => {
  if (!/window\.__flowAPI\s*=/.test(html)) {
    throw new Error('__flowAPI assignment not found — VS Code extension bridge will fail');
  }
});

check('__flowAPI.loadMermaid exists', () => {
  if (!/loadMermaid\s*:/.test(html)) {
    throw new Error('loadMermaid method missing from __flowAPI');
  }
});

check('loadMermaid checks for sequenceDiagram before calling autoLayout (regression guard)', () => {
  const m = html.match(/loadMermaid\s*:\s*\([^)]*\)\s*=>\s*\{([\s\S]*?)\n\s*\},/);
  if (!m) throw new Error('Could not locate loadMermaid function body to inspect');
  const body = m[1];
  if (!/isSeq/.test(body)) {
    throw new Error('loadMermaid no longer tracks isSeq flag — autoLayout may run unconditionally again');
  }
  if (!/if\(!isSeq\)autoLayout\(\)/.test(body.replace(/\s/g, ''))) {
    throw new Error('loadMermaid does not gate autoLayout() behind !isSeq — REGRESSION: sequence diagrams will be scrambled again');
  }
});

check('parseDSL also gates autoLayout behind isSeq flag', () => {
  const m = html.match(/function parseDSL\(\)\{([\s\S]*?)\n\}/);
  if (!m) throw new Error('Could not locate parseDSL function body');
  const body = m[1].replace(/\s/g, '');
  if (!/if\(!isSeq\)autoLayout\(\)/.test(body)) {
    throw new Error('parseDSL does not gate autoLayout() behind !isSeq — REGRESSION risk for DSL-tab sequence paste');
  }
});

check('epts() handles isSequence edges via seqFromX/seqToX/seqY (not nearPort)', () => {
  const m = html.match(/function epts\(e\)\{([\s\S]*?)\n\}/);
  if (!m) throw new Error('Could not locate epts function body');
  const body = m[1];
  if (!/e\.isSequence/.test(body)) {
    throw new Error('epts() no longer special-cases isSequence edges — sequence rendering will use nearPort and collapse rows again');
  }
});

check('sequence-detection regex requires space after colon to avoid misrouting bracket DSL syntax', () => {
  const matches = html.match(/->\.\*:\\?s/g) || [];
  if (matches.length < 2) {
    throw new Error('Expected sequence-detection regex /->.*:\\s/ in both parseDSL and __flowAPI bridge — found ' + matches.length + ' occurrences. REGRESSION: bracket DSL with shape:color tags will be misrouted to parseSequence again.');
  }
});

console.log('\n──────────────────────────────────────────────────');
console.log(`${pass} passed, ${fail} failed (static checks)`);
if (fail > 0) process.exit(1);
