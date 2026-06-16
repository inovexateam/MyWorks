const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

let panel = null;

function activate(context) {

  // ── Command: Open Flow Builder ──
  const openCmd = vscode.commands.registerCommand('flowbuilder.open', (uri) => {
    openPanel(context, uri);
  });

  const openSideCmd = vscode.commands.registerCommand('flowbuilder.openInSide', (uri) => {
    openPanel(context, uri, vscode.ViewColumn.Beside);
  });

  context.subscriptions.push(openCmd, openSideCmd);
}

function openPanel(context, fileUri, column) {
  column = column || vscode.ViewColumn.One;

  // Reuse existing panel if open
  if (panel) {
    panel.reveal(column);
    if (fileUri) loadFileIntoPanel(fileUri);
    return;
  }

  // Create WebView panel
  panel = vscode.window.createWebviewPanel(
    'flowbuilder',
    'Flow Builder',
    column,
    {
      enableScripts: true,
      retainContextWhenHidden: true, // keep diagram alive when switching tabs
      localResourceRoots: [
        vscode.Uri.joinPath(context.extensionUri, 'media')
      ]
    }
  );

  // Load the HTML
  const htmlPath = path.join(context.extensionPath, 'media', 'flowbuilder.html');
  let html = fs.readFileSync(htmlPath, 'utf8');

  // Inject VS Code API bridge before closing </body>
  const bridge = `
<script>
// ── VS Code Bridge ──
const vscodeApi = acquireVsCodeApi();

// Override export buttons to also offer "Save to workspace"
window.__vscode = {
  saveToWorkspace: function(data, filename) {
    vscodeApi.postMessage({ command: 'saveFile', data, filename });
  },
  insertSVG: function(svg) {
    vscodeApi.postMessage({ command: 'insertSVG', svg });
  },
  showInfo: function(msg) {
    vscodeApi.postMessage({ command: 'info', text: msg });
  }
};

// Receive messages from extension host
window.addEventListener('message', event => {
  const msg = event.data;
  if (msg.command === 'loadDiagram' && msg.json) {
    // Restore saved diagram state
    try {
      const state = JSON.parse(msg.json);
      if (state.nodes) nodes = state.nodes;
      if (state.edges) edges = state.edges;
      fitView();
      draw();
      toast('Diagram loaded from ' + msg.filename);
    } catch(e) { console.error('Load error', e); }
  }
});
</script>`;

  html = html.replace('</body>', bridge + '\n</body>');
  panel.webview.html = html;

  // ── Handle messages from WebView ──
  panel.webview.onDidReceiveMessage(async msg => {

    if (msg.command === 'saveFile') {
      // Save diagram JSON to workspace
      const workspaceFolders = vscode.workspace.workspaceFolders;
      if (!workspaceFolders) {
        vscode.window.showErrorMessage('Open a workspace folder first.');
        return;
      }
      const defaultUri = vscode.Uri.joinPath(
        workspaceFolders[0].uri,
        msg.filename || 'diagram.flow'
      );
      const uri = await vscode.window.showSaveDialog({
        defaultUri,
        filters: {
          'Flow Diagram': ['flow'],
          'SVG': ['svg'],
          'PNG': ['png']
        }
      });
      if (uri) {
        const content = Buffer.from(msg.data, 'base64');
        await vscode.workspace.fs.writeFile(uri, content);
        vscode.window.showInformationMessage(`Saved: ${path.basename(uri.fsPath)}`);
      }
    }

    if (msg.command === 'insertSVG') {
      // Insert SVG at cursor in active editor
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage('No active editor to insert SVG into.');
        return;
      }
      editor.edit(editBuilder => {
        editBuilder.insert(editor.selection.active, msg.svg);
      });
      vscode.window.showInformationMessage('SVG inserted at cursor.');
    }

    if (msg.command === 'info') {
      vscode.window.showInformationMessage(msg.text);
    }

  }, undefined, context.subscriptions);

  // Load file if opened via .flow file
  if (fileUri) loadFileIntoPanel(fileUri);

  // Cleanup on close
  panel.onDidDispose(() => { panel = null; }, null, context.subscriptions);
}

async function loadFileIntoPanel(uri) {
  if (!panel) return;
  try {
    const bytes = await vscode.workspace.fs.readFile(uri);
    const json = Buffer.from(bytes).toString('utf8');
    const filename = path.basename(uri.fsPath);
    panel.webview.postMessage({ command: 'loadDiagram', json, filename });
  } catch (e) {
    vscode.window.showErrorMessage('Could not load diagram: ' + e.message);
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
