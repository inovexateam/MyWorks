const vscode = require('vscode');
const path = require('path');

// Sort nodes/edges by id for stable, diff-friendly JSON output
function stabilizeDiagramJSON(diagramObj) {
  const obj = { ...diagramObj };
  if (Array.isArray(obj.nodes)) {
    obj.nodes = [...obj.nodes].sort((a, b) => (a.id > b.id ? 1 : -1));
  }
  if (Array.isArray(obj.edges)) {
    obj.edges = [...obj.edges].sort((a, b) => {
      const ka = `${a.src}-${a.tgt}`, kb = `${b.src}-${b.tgt}`;
      return ka > kb ? 1 : -1;
    });
  }
  return obj;
}

const ADR_TEMPLATE = (title, num) => `# ${num}. ${title}

**Status:** Proposed
**Date:** ${new Date().toISOString().split('T')[0]}

## Context

<!-- What is the issue we're seeing that motivates this decision? -->

## Decision

<!-- What change are we proposing/making? -->

## Diagram

\`\`\`flowbuilder
{
  "nodes": [],
  "edges": []
}
\`\`\`

> Open this diagram in VS Code: place cursor inside the block above, then
> run **"Flow Builder: Open Embedded Diagram"** from the Command Palette.

## Consequences

<!-- What becomes easier or harder as a result of this change? -->
`;

async function newADR() {
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders) {
    vscode.window.showErrorMessage('Open a workspace folder first.');
    return;
  }

  const title = await vscode.window.showInputBox({
    prompt: 'ADR title (e.g. "Use event-driven architecture for order processing")',
    placeHolder: 'Decision title'
  });
  if (!title) return;

  const adrDir = vscode.Uri.joinPath(workspaceFolders[0].uri, 'docs', 'adr');
  try {
    await vscode.workspace.fs.createDirectory(adrDir);
  } catch (e) { /* already exists */ }

  // Find next ADR number by listing existing files
  let nextNum = 1;
  try {
    const entries = await vscode.workspace.fs.readDirectory(adrDir);
    const nums = entries
      .map(([name]) => name.match(/^(\d{4})-/))
      .filter(Boolean)
      .map(m => parseInt(m[1], 10));
    if (nums.length) nextNum = Math.max(...nums) + 1;
  } catch (e) { /* dir empty or new */ }

  const numStr = String(nextNum).padStart(4, '0');
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  if (!slug) {
    vscode.window.showErrorMessage('Title produced an empty filename — use at least one letter or number.');
    return;
  }
  const fileName = `${numStr}-${slug}.md`;
  const fileUri = vscode.Uri.joinPath(adrDir, fileName);

  const content = ADR_TEMPLATE(title, nextNum);
  try {
    await vscode.workspace.fs.writeFile(fileUri, Buffer.from(content, 'utf8'));
    const doc = await vscode.workspace.openTextDocument(fileUri);
    await vscode.window.showTextDocument(doc);
    vscode.window.showInformationMessage(`Created ${fileName}`);
  } catch (err) {
    vscode.window.showErrorMessage(`Could not create ADR: ${err.message}`);
  }
}

function registerADR(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand('flowbuilder.newADR', newADR)
  );
}

module.exports = { registerADR, stabilizeDiagramJSON };
