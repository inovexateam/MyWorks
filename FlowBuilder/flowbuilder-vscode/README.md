# Flow Diagram Builder — VS Code Extension

A fully self-contained visual flow diagram builder running inside VS Code.
Drag-and-drop nodes, paste DSL/Mermaid/JSON, animate, and export to SVG, PNG, GIF, or WebM.

---

## Requirements

- **Windows 10 / 11** (also works on macOS and Linux)
- **VS Code 1.80.0 or later** — [Download VS Code](https://code.visualstudio.com/)
- **Node.js 16 or later** — [Download Node.js](https://nodejs.org/en/download) *(only needed for packaging, not for running)*

To check if Node.js is already installed, open **Command Prompt** and run:
```cmd
node --version
```
If you see a version number like `v18.x.x` you are good to go.

---

## Installation

### Option A — Build and install from source (recommended for Windows)

Open **Command Prompt** (`Win + R` → type `cmd` → Enter) or **PowerShell**:

```cmd
:: Step 1 — Install the VS Code extension packager globally
npm install -g @vscode/vsce

:: Step 2 — Navigate into the extension folder
:: (adjust the path to where you extracted the zip)
cd C:\Users\YourName\Downloads\flowbuilder-vscode

:: Step 3 — Package into a .vsix installer file
vsce package --no-dependencies

:: Step 4 — Install into VS Code
code --install-extension flowbuilder-1.0.0.vsix
```

> **Tip:** After Step 4, restart VS Code if prompted.

---

### Option B — Install .vsix manually via VS Code UI (no terminal needed)

Use this if you already have the `.vsix` file from someone else.

1. Open **VS Code**
2. Press `Ctrl + Shift + X` to open the Extensions panel
3. Click the `···` menu button at the top-right of the Extensions panel
4. Click **"Install from VSIX…"**
5. Browse to and select `flowbuilder-1.0.0.vsix`
6. Click **Install**
7. Click **Reload Window** when prompted

---

### Option C — Run in development mode (no packaging needed)

Use this to test without installing.

1. Open **VS Code**
2. Go to **File → Open Folder** and select the `flowbuilder-vscode` folder
3. Press **F5**
4. A new VS Code window opens with the extension active — test it there

---

## Opening the Diagram Builder

Once installed, open it any of these ways:

| Method | Steps |
|---|---|
| **Command Palette** | Press `Ctrl + Shift + P` → type `Flow Builder` → select **"Flow Builder: Open Diagram"** |
| **Keyboard shortcut** | Press `Ctrl + Shift + F` |
| **Side panel** | `Ctrl + Shift + P` → **"Flow Builder: Open in Side Panel"** |
| **Open a .flow file** | Double-click any `.flow` file in the VS Code Explorer sidebar |

---

## How to Use

### Drawing
- **Drag** any shape from the left panel onto the canvas
- **Double-click** empty canvas → add a new node
- **Double-click** a node → rename it
- Switch to **Connect** mode (or press `C`) then drag from one node to another to connect them
- **Right-click** anywhere on the canvas for a context menu

### Generate from text (DSL tab)
1. Click the **DSL / Text** tab in the left panel
2. Paste any of these formats and click **Generate**:

```
Arrow flow:      A -> B -> C
Labels:          A --yes--> B
Sequence:        User -> Server: login
Mermaid:         graph TD ...
JSON:            {"nodes":[...], "edges":[...]}
Markdown list:   # Title / - item
```

Click any **example link** in the DSL tab to pre-fill a sample.

### Saving your diagram
1. Click **Export** in the toolbar
2. Select **"Save to Workspace"** — a save dialog opens inside VS Code
3. Choose your project folder and save as `diagram.flow`
4. The `.flow` file is plain JSON — commit it to Git like any other file

### Loading a saved diagram
Double-click any `.flow` file in the VS Code Explorer sidebar — it opens in Flow Builder automatically.

### Inserting a diagram into your code/docs
1. Open the file you want to embed the diagram into (Markdown, HTML, etc.)
2. Place your cursor where you want the diagram
3. In Flow Builder, click **Export → Insert SVG into Editor**
4. The SVG is pasted at your cursor position

---

## Export Formats

| Format | How to get it | Best for |
|---|---|---|
| PNG 2× | Export → PNG standard 2× | PowerPoint, Word, Teams, Slack |
| PNG 3× | Export → PNG hi-res 3× | Large displays, print |
| SVG static | Export → SVG static (white bg) | Confluence, Figma, GitHub README |
| SVG animated | Export → SVG animated | Browser HTML pages |
| GIF animated | Export → GIF animated | Confluence, Outlook email, PPT |
| WebM video | Export → WebM animated | Modern PPT, Notion, video embeds |
| Copy PNG | Export → Copy PNG to clipboard | Paste into any Windows app (`Ctrl+V`) |
| Copy SVG | Export → Copy SVG to clipboard | Paste into Figma or Illustrator |

> **Copying to clipboard:** After clicking "Copy PNG", press `Ctrl + V` in PowerPoint,
> Word, Teams, Outlook, or any other app to paste it directly — no file needed.

---

## Keyboard Shortcuts (inside the diagram)

| Key | Action |
|---|---|
| `V` | Switch to Select tool |
| `C` | Switch to Connect tool |
| `P` | Switch to Pan tool |
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |
| `Ctrl + C` | Copy entire diagram as PNG to clipboard |
| `Ctrl + A` | Select all (then Ctrl+C to copy) |
| `Delete` or `Backspace` | Delete selected node or edge |
| Double-click canvas | Add new node |
| Double-click node | Rename node |
| Right-click | Context menu (copy, download, delete) |
| Mouse scroll | Zoom in / out |
| `+` or `=` | Zoom in |
| `-` | Zoom out |
| Middle mouse drag | Pan canvas |

---

## Diagram File Format (.flow)

`.flow` files are plain JSON you can open in any text editor:

```json
{
  "nodes": [
    {
      "id": "abc123",
      "x": 220, "y": 80, "w": 120, "h": 44,
      "label": "Start",
      "shape": "oval",
      "color": "teal",
      "fontSize": 12,
      "fontBold": false,
      "fontItalic": false
    }
  ],
  "edges": [
    {
      "id": "def456",
      "src": "abc123",
      "tgt": "xyz789",
      "label": "yes",
      "arrow": "arrow",
      "style": ""
    }
  ]
}
```

Commit `.flow` files to Git so teammates can open and edit them.

---

## Folder Structure

```
flowbuilder-vscode\
├── package.json          ← Extension manifest, commands, keybindings
├── extension.js          ← Opens WebView panel, handles save/load/SVG insert
├── media\
│   └── flowbuilder.html  ← The complete diagram builder (self-contained HTML)
├── README.md             ← This file
└── .vscodeignore         ← Files excluded from the .vsix package
```

---

## Updating the Diagram Builder

When a new version of `flowbuilder.html` is available:

**Windows Command Prompt:**
```cmd
:: Replace the HTML file
copy /Y C:\path\to\new\flowbuilder.html flowbuilder-vscode\media\flowbuilder.html

:: Re-package
cd flowbuilder-vscode
vsce package --no-dependencies

:: Re-install
code --install-extension flowbuilder-1.0.0.vsix
```

---

## Troubleshooting

**`'vsce' is not recognized as an internal or external command`**
```cmd
npm install -g @vscode/vsce
```
If npm itself is not found, install Node.js from https://nodejs.org first, then reopen Command Prompt.

---

**`'code' is not recognized as an internal or external command`**

VS Code's CLI isn't on your PATH. Fix:
1. Open VS Code
2. Press `Ctrl + Shift + P`
3. Type **"Shell Command: Install 'code' command in PATH"**
4. Click it, then reopen Command Prompt

---

**Extension installs but nothing happens when I press `Ctrl+Shift+F`**
- Press `Ctrl + Shift + P` and type **"Flow Builder"** to find the command manually
- Check if another extension is using the same shortcut: `File → Preferences → Keyboard Shortcuts` → search `flowbuilder`

---

**WebView shows a blank white page**
- Make sure `media\flowbuilder.html` exists inside the extension folder
- Try uninstalling and reinstalling the `.vsix`
- Check **Output** panel (`Ctrl + Shift + U`) → select **"Extension Host"** from the dropdown

---

**Diagram won't save to workspace**
- You must have a folder open in VS Code (`File → Open Folder`) before saving
- The save dialog will not appear if no workspace is open

---

**GIF export gets stuck**
- Use **WebM export** instead — it's instant and works in PowerPoint and Notion
- For GIF, try reducing the number of nodes or zooming in on a smaller section first

---

## Support

If the extension doesn't load or commands are missing:

1. Press `Ctrl + Shift + P` → **"Developer: Reload Window"**
2. Check `Help → Toggle Developer Tools` → Console tab for error messages
3. Reinstall the `.vsix` using Option B above

---

## Future Roadmap / TODO

### 🤖 GitHub Copilot Chat Integration

**Goal:** User types a prompt in Copilot Chat and the diagram renders live on the Flow Builder board.

**How it will work:**

```
User types in Copilot Chat
        ↓
Extension registers @flowbuilder as a Chat Participant
        ↓
Copilot LLM generates Mermaid / JSON / DSL text
        ↓
extension.js sends it to WebView via postMessage
        ↓
flowbuilder.html parseDSL() renders it on the board instantly
```

**Example usage (once implemented):**
```
@flowbuilder draw an auth flow with JWT and refresh tokens
@flowbuilder create a CI/CD pipeline with staging and rollback
@flowbuilder sequence diagram for a payment checkout flow
```

**What needs to be built:**
- VS Code 1.90+ required (Chat Participant API)
- GitHub Copilot subscription required (provides the LLM)
- Add `"extensionDependencies": ["github.copilot-chat"]` to `package.json`
- Register `@flowbuilder` participant in `contributes.chatParticipants`
- ~50 lines added to `extension.js` to call `vscode.lm.selectChatModels()`
- System prompt instructs Copilot to respond in Mermaid / JSON / DSL only
- `postMessage({ command: 'loadDSL', text: mermaidOutput })` sends result to board
- **Zero changes to `flowbuilder.html`** — existing `parseDSL()` handles rendering

**Supported output formats from Copilot:**

| Prompt type | Format generated | Reason |
|---|---|---|
| Simple flows | Mermaid `graph TD` | Most reliable from LLMs |
| Sequence diagrams | Mermaid `sequenceDiagram` | Native support |
| Complex with colors | JSON `{"nodes":[],"edges":[]}` | Full node control |
| Architecture | Arrow DSL `A -> B -> C` | Lightweight |

**Known limitation:** Copilot Chat API is currently read-only from the extension side — the board can receive generated diagrams but cannot send current board state back to Copilot for iteration prompts like *"add an error state to the existing diagram"*. Workaround: track diagram JSON in `extension.js` state and include it as LLM context on each message.

---

### 📋 Other Planned Features
- **Multi-select** — drag rectangle to select multiple nodes at once
- **Swim lanes** — group nodes into labelled lanes (essential for process docs)
- **Auto-route edges** — edges avoid overlapping nodes
- **Edge waypoints** — drag the middle of an edge to bend it
- **Save/restore via localStorage** — diagram persists on browser refresh
- **Shareable URL** — diagram state encoded in URL hash for easy sharing
- **Presentation mode** — step-through animation highlighting one path at a time
- **Draw.io XML import** — open existing `.drawio` files directly