const vscode = require('vscode');

const CODE_EXTRACTION_PROMPT = `You are a code-flow analyzer for a VS Code extension.
Given a code snippet, extract its control flow and respond with ONLY a Mermaid diagram —
no explanation, no markdown fences, no extra text.

Rules:
- If the code is a single function with branching logic, use: graph TD
  - Represent if/else and switch branches as {Decision?} diamond nodes
  - Represent function calls and operations as [Action] process nodes
  - Show the return/exit paths clearly
- If the code shows interaction between multiple objects/services/API calls, use: sequenceDiagram
  - Each class/service/module becomes a participant
  - Each method call becomes an arrow with the method name as the label
- Keep node labels short (3-6 words), based on what the code actually does
- Output raw Mermaid syntax only — your entire response must be valid Mermaid`;

async function generateFromSelection(context, getPanel) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.selection.isEmpty) {
    vscode.window.showWarningMessage('Select a function or code block first.');
    return;
  }

  const code = editor.document.getText(editor.selection);
  const languageId = editor.document.languageId;
  const fileName = editor.document.fileName;

  if (code.trim().length < 10) {
    vscode.window.showWarningMessage('Selection too short to analyze.');
    return;
  }

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: 'Flow Builder: analyzing code…', cancellable: true },
    async (progress, token) => {
      try {
        const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
        if (!models || models.length === 0) {
          vscode.window.showErrorMessage('No Copilot language model available. Install/sign in to GitHub Copilot Chat.');
          return;
        }
        const model = models[0];

        const messages = [
          vscode.LanguageModelChatMessage.User(CODE_EXTRACTION_PROMPT),
          vscode.LanguageModelChatMessage.User(`Language: ${languageId}\n\nCode:\n\`\`\`${languageId}\n${code}\n\`\`\``)
        ];

        progress.report({ message: 'Calling Copilot…' });
        const response = await model.sendRequest(messages, {}, token);

        let fullText = '';
        for await (const fragment of response.text) {
          fullText += fragment;
        }
        fullText = fullText.replace(/^```(?:mermaid)?\n?/i, '').replace(/\n?```$/i, '').trim();

        if (!fullText) {
          vscode.window.showWarningMessage('Could not extract a flow from this selection.');
          return;
        }

        // Open/reveal panel and send diagram, tagged with source info for Phase 5 sync
        let panel = getPanel();
        if (!panel) {
          await vscode.commands.executeCommand('flowbuilder.openInSide');
          await new Promise(r => setTimeout(r, 500));
          panel = getPanel();
        } else {
          panel.reveal(vscode.ViewColumn.Beside, true);
        }

        if (panel) {
          panel.webview.postMessage({
            command: 'loadDSL',
            text: fullText,
            sourceMeta: {
              file: fileName,
              startLine: editor.selection.start.line,
              endLine: editor.selection.end.line,
              generatedAt: new Date().toISOString()
            }
          });
          vscode.window.showInformationMessage('Diagram generated from selected code.');
        }

      } catch (err) {
        vscode.window.showErrorMessage(`Code-to-diagram failed: ${err.message}`);
      }
    }
  );
}

function registerCodeToDigram(context, getPanel) {
  const cmd = vscode.commands.registerCommand('flowbuilder.generateFromSelection', () => {
    generateFromSelection(context, getPanel);
  });
  context.subscriptions.push(cmd);
}

module.exports = { registerCodeToDigram, generateFromSelection };
