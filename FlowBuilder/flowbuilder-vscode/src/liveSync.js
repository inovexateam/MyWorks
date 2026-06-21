const vscode = require('vscode');

// Matches ```flowbuilder ... ``` fenced blocks in markdown
const EMBED_REGEX = /```flowbuilder\n([\s\S]*?)```/g;

class FlowEmbedCodeLensProvider {
  provideCodeLenses(document, token) {
    const lenses = [];
    const text = document.getText();
    let match;
    EMBED_REGEX.lastIndex = 0;
    while ((match = EMBED_REGEX.exec(text)) !== null) {
      const startPos = document.positionAt(match.index);
      const range = new vscode.Range(startPos, startPos);

      lenses.push(new vscode.CodeLens(range, {
        title: '▶ Open in Flow Builder',
        command: 'flowbuilder.openEmbedded',
        arguments: [document.uri, match.index, match[1]]
      }));

      // Only show refresh action if the block has source metadata
      if (/"sourceMeta"/.test(match[1])) {
        lenses.push(new vscode.CodeLens(range, {
          title: '↻ Refresh from source',
          command: 'flowbuilder.refreshFromSource',
          arguments: [document.uri, match.index, match[1]]
        }));
      }
    }
    return lenses;
  }
}

function registerLiveSync(context, getPanel, openEmbeddedJson) {
  // CodeLens for .md files
  const provider = new FlowEmbedCodeLensProvider();
  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider({ language: 'markdown' }, provider)
  );

  // Command: open the embedded diagram block in the WebView
  context.subscriptions.push(
    vscode.commands.registerCommand('flowbuilder.openEmbedded', async (uri, matchIndex, jsonOrMermaid) => {
      try {
        let panel = getPanel();
        if (!panel) {
          await vscode.commands.executeCommand('flowbuilder.openInSide');
          await new Promise(r => setTimeout(r, 500));
          panel = getPanel();
        } else {
          panel.reveal(vscode.ViewColumn.Beside, true);
        }
        if (!panel) {
          vscode.window.showWarningMessage('Could not open Flow Builder panel.');
          return;
        }

        const trimmed = jsonOrMermaid.trim();
        if (trimmed.startsWith('{')) {
          panel.webview.postMessage({ command: 'loadDiagram', json: trimmed, filename: uri ? uri.fsPath.split(/[\\/]/).pop() : 'embedded' });
        } else {
          panel.webview.postMessage({ command: 'loadDSL', text: trimmed });
        }
      } catch (err) {
        vscode.window.showErrorMessage(`Could not open embedded diagram: ${err.message}`);
      }
    })
  );

  // Command: refresh an embedded diagram by re-running code extraction on its sourceMeta
  context.subscriptions.push(
    vscode.commands.registerCommand('flowbuilder.refreshFromSource', async (uri, matchIndex, jsonText) => {
      try {
        const data = JSON.parse(jsonText);
        const meta = data.sourceMeta;
        if (!meta || !meta.file) {
          vscode.window.showWarningMessage('This diagram has no linked source to refresh from.');
          return;
        }

        const srcUri = vscode.Uri.file(meta.file);
        const srcDoc = await vscode.workspace.openTextDocument(srcUri);
        const range = new vscode.Range(meta.startLine, 0, meta.endLine, srcDoc.lineAt(meta.endLine).text.length);
        const code = srcDoc.getText(range);

        // Re-run extraction (reuses codeToDiagram logic inline to avoid circular import)
        const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
        if (!models || models.length === 0) {
          vscode.window.showErrorMessage('No Copilot model available to refresh.');
          return;
        }
        const model = models[0];
        const messages = [
          vscode.LanguageModelChatMessage.User('Extract control flow as Mermaid graph TD or sequenceDiagram. Output ONLY raw Mermaid, no fences, no explanation.'),
          vscode.LanguageModelChatMessage.User(`Code:\n${code}`)
        ];
        const response = await model.sendRequest(messages, {}, new vscode.CancellationTokenSource().token);
        let fullText = '';
        for await (const fragment of response.text) fullText += fragment;
        fullText = fullText.replace(/^```(?:mermaid)?\n?/i, '').replace(/\n?```$/i, '').trim();

        let panel = getPanel();
        if (!panel) {
          await vscode.commands.executeCommand('flowbuilder.openInSide');
          await new Promise(r => setTimeout(r, 500));
          panel = getPanel();
        } else {
          panel.reveal(vscode.ViewColumn.Beside, true);
        }
        if (panel) {
          panel.webview.postMessage({ command: 'loadDSL', text: fullText, sourceMeta: meta });
          vscode.window.showInformationMessage('Diagram refreshed from source.');
        }
      } catch (err) {
        vscode.window.showErrorMessage(`Refresh failed: ${err.message}`);
      }
    })
  );

  // Watch for saves to files that diagrams were generated from — prompt to refresh
  const trackedSources = new Map(); // file path -> last known mtime

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (doc) => {
      const filePath = doc.uri.fsPath;
      if (!trackedSources.has(filePath)) return;

      const choice = await vscode.window.showInformationMessage(
        `"${filePath.split(/[\\/]/).pop()}" changed — its linked diagram may be outdated.`,
        'Refresh Diagram', 'Dismiss'
      );
      if (choice === 'Refresh Diagram') {
        vscode.window.showInformationMessage('Open the diagram\'s markdown file and click "↻ Refresh from source" above the block.');
      }
    })
  );

  // Expose a way for codeToDiagram.js to register a tracked source
  return {
    trackSource: (filePath) => trackedSources.set(filePath, Date.now())
  };
}

module.exports = { registerLiveSync, FlowEmbedCodeLensProvider };
