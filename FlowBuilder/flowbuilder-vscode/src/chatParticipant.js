const vscode = require('vscode');

// One system prompt per diagram type — forces exact Mermaid syntax for that
// type only, eliminating the ambiguity of one generic prompt guessing intent.
const TYPE_PROMPTS = {
  flowchart: `You are a flowchart generator. Respond with ONLY valid Mermaid flowchart syntax —
no explanation, no markdown fences, no extra text.

graph TD
  A[Label] --> B{Decision?}
  B -- Yes --> C[Result]
  B -- No --> D[Other result]

Rules:
- Use {Label} for decision/condition nodes, [Label] for process nodes
- Keep node labels short (2-5 words)
- Output raw Mermaid syntax only`,

  sequence: `You are a sequence diagram generator. Respond with ONLY valid Mermaid sequence syntax —
no explanation, no markdown fences, no extra text.

sequenceDiagram
  participant User
  participant Server
  User->>Server: Request
  Server-->>User: Response

Rules:
- Use ->> for requests/calls, -->> for responses/replies
- List participants explicitly if more than 2
- Keep message labels short (2-6 words)
- Output raw Mermaid syntax only`,

  state: `You are a state diagram generator. Respond with ONLY valid Mermaid state diagram syntax —
no explanation, no markdown fences, no extra text.

stateDiagram-v2
  [*] --> Pending
  Pending --> Approved : approve
  Pending --> Rejected : reject
  Approved --> [*]
  Rejected --> [*]

Rules:
- Use [*] for the initial and final states
- Label every transition with the triggering event/action after a colon
- Keep state names short (1-3 words)
- Output raw Mermaid syntax only`,

  er: `You are an entity-relationship diagram generator. Respond with ONLY valid Mermaid erDiagram syntax —
no explanation, no markdown fences, no extra text.

erDiagram
  CUSTOMER {
    int id PK
    string name
    string email
  }
  ORDER {
    int id PK
    int customer_id FK
    decimal total
  }
  CUSTOMER ||--o{ ORDER : places

Rules:
- Include a {} attribute block for every entity with at least id (PK) and 2-3 key fields
- Mark primary keys PK, foreign keys FK
- Use standard cardinality: ||--o{ (one to many), ||--|| (one to one), }o--o{ (many to many)
- Output raw Mermaid syntax only`,

  class: `You are a class diagram generator for a tool that does not yet render class diagrams.
Respond with ONLY: "Class diagrams are not yet supported by Flow Builder. Try /diagram state or /diagram er instead, or describe the classes as a flowchart."
No other text.`
};

const MODIFY_PROMPT = `You are modifying an existing flow diagram for a VS Code extension.
The current diagram is provided as Mermaid syntax below. Apply the user's requested change
and respond with the COMPLETE updated diagram in the SAME Mermaid diagram type and format —
no explanation, no fences.

Rules:
- Preserve existing nodes/edges/states/entities unless the user asks to remove or change them
- Keep the same diagram type (flowchart stays flowchart, sequence stays sequence, etc.)
- Keep labels short
- Output raw Mermaid syntax only`;

// Tracks the last diagram sent to the board, for iterative "modify" prompts.
// NOTE: this only knows what Copilot last generated — it does NOT know about
// manual edits the user made on the canvas afterward. A /modify call will
// overwrite manual changes. This is a known limitation, not a bug.
let lastDiagramText = '';
let lastDiagramType = 'flowchart';

function setLastDiagram(text, type) {
  lastDiagramText = text;
  if (type) lastDiagramType = type;
}

// Parses "/diagram <type>: <description>" or "<type>: <description>" or just "<description>"
// Returns { type, description } — type defaults to null if not explicitly specified,
// triggering the "ask the user" flow instead of guessing.
function parseTypedPrompt(rawPrompt, slashCommand) {
  // If invoked via a VS Code slash command (e.g. /sequence, /state, /er), that's explicit
  const commandTypeMap = {
    flowchart: 'flowchart',
    sequence: 'sequence',
    state: 'state',
    er: 'er',
    class: 'class'
  };
  if (slashCommand && commandTypeMap[slashCommand]) {
    return { type: commandTypeMap[slashCommand], description: rawPrompt.trim() };
  }

  // Otherwise look for "type: description" written directly in the prompt text,
  // e.g. "/diagram state: order approval workflow"
  const m = rawPrompt.match(/^\s*(flowchart|sequence|state|er|class)\s*:\s*(.+)$/i);
  if (m) {
    return { type: m[1].toLowerCase(), description: m[2].trim() };
  }

  return { type: null, description: rawPrompt.trim() };
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

      if (isModify) {
        if (!lastDiagramText) {
          stream.markdown('⚠️ No diagram generated yet in this session to modify. Generate one first with `/diagram <type>: <description>`.');
          return;
        }
        const userPrompt = `Current diagram:\n${lastDiagramText}\n\nRequested change: ${request.prompt}`;
        await generateAndSend(model, MODIFY_PROMPT, userPrompt, lastDiagramType, stream, getPanel, token);
        return;
      }

      const { type, description } = parseTypedPrompt(request.prompt, request.command);

      if (!type) {
        // Explicit type selection requested rather than guessing — directly
        // addresses "how will I know which flow type the user wants"
        stream.markdown(
          `Which diagram type? Reply with one of:\n\n` +
          `- \`/diagram flowchart: ${description}\`\n` +
          `- \`/diagram sequence: ${description}\`\n` +
          `- \`/diagram state: ${description}\`\n` +
          `- \`/diagram er: ${description}\`\n\n` +
          `Or use the slash commands directly: \`/flowchart\`, \`/sequence\`, \`/state\`, \`/er\``
        );
        return;
      }

      if (!TYPE_PROMPTS[type]) {
        stream.markdown(`⚠️ Unknown diagram type "${type}". Supported: flowchart, sequence, state, er.`);
        return;
      }

      if (!description) {
        stream.markdown(`Describe what you want the ${type} diagram to show, e.g. \`/diagram ${type}: user login flow\`.`);
        return;
      }

      await generateAndSend(model, TYPE_PROMPTS[type], description, type, stream, getPanel, token);

    } catch (err) {
      stream.markdown(`❌ Error generating diagram: ${err.message}`);
    }
  };

  const participant = vscode.chat.createChatParticipant('flowbuilder.chat', handler);
  participant.iconPath = new vscode.ThemeIcon('git-branch');
  context.subscriptions.push(participant);

  return participant;
}

async function generateAndSend(model, systemPrompt, userPrompt, type, stream, getPanel, token) {
  const messages = [
    vscode.LanguageModelChatMessage.User(systemPrompt),
    vscode.LanguageModelChatMessage.User(userPrompt)
  ];

  stream.progress(`Generating ${type} diagram…`);

  const chatResponse = await model.sendRequest(messages, {}, token);

  let fullText = '';
  for await (const fragment of chatResponse.text) {
    fullText += fragment;
  }

  fullText = fullText.replace(/^```(?:mermaid)?\n?/i, '').replace(/\n?```$/i, '').trim();

  if (!fullText) {
    stream.markdown('⚠️ Empty response from the model. Try rephrasing your description.');
    return;
  }

  // Class diagrams aren't rendered yet — the model returns a plain message, not Mermaid.
  // Detect and show it as-is without sending to the board.
  if (type === 'class') {
    stream.markdown(fullText);
    return;
  }

  setLastDiagram(fullText, type);

  const panel = getPanel();
  if (panel) {
    panel.reveal(vscode.ViewColumn.Beside, true);
    panel.webview.postMessage({ command: 'loadDSL', text: fullText });
    stream.markdown(`✅ ${capitalize(type)} diagram generated and sent to the Flow Builder board.\n\n\`\`\`mermaid\n${fullText}\n\`\`\``);
  } else {
    stream.markdown(`${capitalize(type)} diagram generated. Opening Flow Builder…\n\n\`\`\`mermaid\n${fullText}\n\`\`\``);
    vscode.commands.executeCommand('flowbuilder.openInSide').then(() => {
      setTimeout(() => {
        const p = getPanel();
        if (p) p.webview.postMessage({ command: 'loadDSL', text: fullText });
      }, 600);
    }, (openErr) => {
      stream.markdown(`⚠️ Could not open Flow Builder panel: ${openErr.message}`);
    });
  }
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

module.exports = { registerChatParticipant, setLastDiagram };
