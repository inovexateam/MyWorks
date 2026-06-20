const vscode = require('vscode');

// System prompt forces the LLM to output ONLY parseable DSL — no prose, no markdown fences
const SYSTEM_PROMPT = `You are a flow diagram generator for a VS Code extension.
Respond with ONLY one of these formats — no explanation, no markdown code fences, no extra text:

1. Mermaid flowchart:
graph TD
  A[Label] --> B{Decision?}
  B -- Yes --> C[Result]

2. Mermaid sequence diagram:
sequenceDiagram
  User->>Server: Request
  Server->>DB: Query

Rules:
- Use graph TD for process/architecture flows
- Use sequenceDiagram for request/response or interaction flows
- Keep node labels short (2-5 words)
- Use {Label} for decision/condition nodes
- Use [Label] for process nodes
- Output raw Mermaid syntax only — your entire response must be valid Mermaid, nothing else`;

const MODIFY_PROMPT = `You are modifying an existing flow diagram for a VS Code extension.
The current diagram is provided as Mermaid syntax below. Apply the user's requested change
and respond with the COMPLETE updated diagram in the same Mermaid format — no explanation, no fences.

Rules:
- Preserve existing nodes/edges unless the user asks to remove or change them
- Keep node labels short (2-5 words)
- Output raw Mermaid syntax only`;

// Tracks the last diagram sent to the board, per panel, for iterative "modify" prompts
let lastDiagramText = '';

function setLastDiagram(text) {
  lastDiagramText = text;
}

function registerChatParticipant(context, getPanel) {
  const handler = async (request, chatContext, stream, token) => {
    try {
      const models = await vscode.lm.selectChatModels({ vendor: 'copilot' });
      if (!models || models.length === 0) {
        stream.markdown('⚠️ No Copilot language model available. Ensure GitHub Copilot Chat is installed and you are signed in.');
        return;
      }
      const model = models[0];

      const isModify = request.command === 'modify' || /\b(add|change|remove|update|modify)\b/i.test(request.prompt);
      const isSequence = request.command === 'sequence' || /\b(sequence|request|response|api call|interaction)\b/i.test(request.prompt);

      let systemPrompt = SYSTEM_PROMPT;
      let userPrompt = request.prompt;

      if (isModify && lastDiagramText) {
        systemPrompt = MODIFY_PROMPT;
        userPrompt = `Current diagram:\n${lastDiagramText}\n\nRequested change: ${request.prompt}`;
      } else if (isSequence) {
        userPrompt = `Create a sequence diagram for: ${request.prompt}`;
      }

      const messages = [
        vscode.LanguageModelChatMessage.User(systemPrompt),
        vscode.LanguageModelChatMessage.User(userPrompt)
      ];

      stream.progress('Generating diagram…');

      const chatResponse = await model.sendRequest(messages, {}, token);

      let fullText = '';
      for await (const fragment of chatResponse.text) {
        fullText += fragment;
      }

      // Strip markdown fences if the model added them despite instructions
      fullText = fullText.replace(/^```(?:mermaid)?\n?/i, '').replace(/\n?```$/i, '').trim();

      if (!fullText) {
        stream.markdown('⚠️ Empty response from the model. Try rephrasing your prompt.');
        return;
      }

      setLastDiagram(fullText);

      // Send to the WebView board
      const panel = getPanel();
      if (panel) {
        panel.reveal(vscode.ViewColumn.Beside, true);
        panel.webview.postMessage({ command: 'loadDSL', text: fullText });
        stream.markdown(`✅ Diagram generated and sent to the Flow Builder board.\n\n\`\`\`mermaid\n${fullText}\n\`\`\``);
      } else {
        // No panel open yet — open one and queue the message
        stream.markdown(`Diagram generated. Opening Flow Builder…\n\n\`\`\`mermaid\n${fullText}\n\`\`\``);
        vscode.commands.executeCommand('flowbuilder.openInSide').then(() => {
          setTimeout(() => {
            const p = getPanel();
            if (p) p.webview.postMessage({ command: 'loadDSL', text: fullText });
          }, 600);
        });
      }

    } catch (err) {
      stream.markdown(`❌ Error generating diagram: ${err.message}`);
    }
  };

  const participant = vscode.chat.createChatParticipant('flowbuilder.chat', handler);
  participant.iconPath = new vscode.ThemeIcon('git-branch');
  context.subscriptions.push(participant);

  return participant;
}

module.exports = { registerChatParticipant, setLastDiagram };
