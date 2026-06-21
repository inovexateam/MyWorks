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
Labels:          [A] --yes--> [B]
Sequence:        User -> Server: login
Mermaid flow:    graph TD ...
State diagram:   stateDiagram-v2 ...
ER diagram:      erDiagram ...
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

### 🤖 GitHub Copilot Chat Integration — ✅ Shipped

Generate diagrams by typing in Copilot Chat — no need to open the DSL tab manually.

**How it works:**
```
You type in Copilot Chat
        ↓
@flowbuilder participant receives your message
        ↓
Copilot's language model generates Mermaid syntax for your chosen diagram type
        ↓
Diagram is sent to the open Flow Builder panel and rendered instantly
```

**Usage — explicit type selection (no guessing):**
```
@flowbuilder /diagram flowchart: auth flow with JWT and refresh tokens
@flowbuilder /diagram sequence: payment checkout flow
@flowbuilder /diagram state: order approval workflow
@flowbuilder /diagram er: e-commerce schema with customers, orders, products
```

Or use the slash commands directly:
```
@flowbuilder /flowchart auth flow with JWT and refresh tokens
@flowbuilder /sequence payment checkout flow
@flowbuilder /state order approval workflow
@flowbuilder /er e-commerce schema with customers, orders, products
```

If you don't specify a type, Flow Builder asks which one you want instead of guessing — this avoids generating the wrong diagram type from an ambiguous prompt.

**Modifying an existing diagram:**
```
@flowbuilder /modify add a retry node after the API call
```
Applies your change to the last diagram generated *in this chat session*. Note: this only knows what Copilot last generated — manual edits you made on the canvas afterward are not visible to `/modify` and will be overwritten if you run it.

**Requirements:**
- VS Code 1.90+ (Chat Participant API)
- Active GitHub Copilot subscription
- Flow Builder panel open (or it opens automatically on first generation)

**Supported diagram types:**

| Type | Command | Status |
|---|---|---|
| Flowchart | `/diagram flowchart:` or `/flowchart` | ✅ Full support |
| Sequence diagram | `/diagram sequence:` or `/sequence` | ✅ Full support |
| State diagram | `/diagram state:` or `/state` | ✅ Full support |
| Entity-relationship | `/diagram er:` or `/er` | ✅ Full support |
| Class diagram | `/diagram class:` | ❌ Not rendered yet — Copilot will tell you to use state/ER instead |

**Known limitation:** the extension only tracks the last diagram *it* generated, not your manual canvas edits. `/modify` will overwrite manual changes made after generation. There's no live read of current board state back into Copilot.

---

### 📋 Other Planned Features
- **Code-to-diagram for state/ER types** — currently "Visualize Selected Code" only generates flowchart/sequence; extending it to detect state machines and data models in code
- **Class diagram rendering** — requires structural (AST-level) extraction for accuracy; LLM-only extraction was judged too unreliable to ship for this type
- **Presentation mode** — step-through animation highlighting one path at a time
- **Draw.io XML import** — open existing `.drawio` files directly
- **Token-walk animation** — animated marker traveling sequence-diagram lifelines in execution order (decorative pulse animation exists today; true ordered walk does not)

> ✅ Shipped: Multi-select, edge waypoints, localStorage auto-save, shareable URL, Copilot Chat generation (flowchart/sequence/state/ER), swim lanes, auto-route — see Usage section above.

---

## 🗺️ Value-Add Roadmap

Ranked by leverage. Each phase reuses infrastructure from the previous one where noted.

### Phase 1 — AI-native generation via Copilot Chat
**Effort: Medium | Impact: Highest**

| Step | Task |
|---|---|
| 1.1 | Add `"extensionDependencies": ["github.copilot-chat"]` to `package.json` |
| 1.2 | Register `@flowbuilder` chat participant in `contributes.chatParticipants` |
| 1.3 | Implement `vscode.chat.createChatParticipant()` handler in `extension.js` |
| 1.4 | Call `vscode.lm.selectChatModels()`, system prompt forces Mermaid/JSON output |
| 1.5 | Parse LLM response, `postMessage({command:'loadDSL', text})` to WebView |
| 1.6 | Wire `loadDSL` message handler — reuses existing `parseDSL()` in `flowbuilder.html` |
| 1.7 | Track last diagram JSON in extension state for iterative prompts |

**Files touched:** `package.json`, `extension.js` only.

---

### Phase 2 — Git-diffable ADRs (quick win, no dependencies)
**Effort: Low | Impact: Medium**

| Step | Task |
|---|---|
| 2.1 | Sort node/edge arrays by `id` on save for stable, diffable JSON |
| 2.2 | Add command `flowbuilder.newADR` — scaffolds `docs/adr/NNNN-title.md` with embedded diagram |
| 2.3 | `.flow` syntax highlighting via `contributes.languages` |
| 2.4 | *(Stretch)* Visual diff provider for two `.flow` JSONs side-by-side |

---

### Phase 3 — Code-to-diagram generation
**Effort: High | Impact: High (unique differentiator)**

| Step | Task |
|---|---|
| 3.1 | Add command `flowbuilder.generateFromSelection` |
| 3.2 | Start with LLM-based extraction: send selected code to Copilot, prompt "extract control flow as Mermaid sequenceDiagram" |
| 3.3 | Map function calls → sequence nodes; if/else/switch → decision diamonds |
| 3.4 | Add context menu: right-click code → "Flow Builder: Visualize this function" |
| 3.5 | Render via same `loadDSL` pipeline as Phase 1 |
| 3.6 | *(Later)* Replace LLM extraction with real AST parsing (TS Compiler API) for accuracy |

**Dependency:** Reuses Phase 1 plumbing.

---

### Phase 4 — Swim lanes + auto-route edges
**Effort: High | Impact: Table-stakes for credibility**

| Step | Task |
|---|---|
| 4.1 | Add `lane` container object: `{id,label,x,y,w,h,color}` rendered behind nodes |
| 4.2 | Nodes get optional `laneId`; drag-into-lane bounds auto-assigns |
| 4.3 | Update `autoLayout()` to group/order nodes by lane |
| 4.4 | Auto-route: detect edge-node collisions, insert 90° detour via existing `waypoints[]` array |
| 4.5 | Toolbar toggle: "Auto-route" on/off |

**Reuses:** waypoints system already shipped.

---

### Phase 5 — Live sync with code
**Effort: High | Impact: Medium-high (long-term differentiator)**

| Step | Task |
|---|---|
| 5.1 | Define embed syntax: ` ```flowbuilder\n{json}\n``` ` in `.md` files |
| 5.2 | `CodeLensProvider` for `.md` — "▶ Open in Flow Builder" above the block |
| 5.3 | "Refresh from source" command — reruns Phase 3 extraction, diffs against saved diagram |
| 5.4 | On code save, check linked diagrams, prompt "Diagram may be outdated — regenerate?" |
| 5.5 | Store source file path + symbol name in `.flow` metadata for re-sync |

**Dependency:** Requires Phase 3.

---

### Suggested Timeline

```
Phase 1 (1-2 wks)  AI Copilot generation      → highest leverage, ships first
Phase 2 (1 wk)     ADR / diff support         → quick win, parallel-safe
Phase 3 (2-3 wks)  Code-to-diagram            → reuses Phase 1
Phase 4 (1-2 wks)  Swim lanes + auto-route    → table stakes, independent
Phase 5 (2 wks)    Live sync                  → depends on Phase 3
```

**Total: ~8–10 weeks** for all five. Phases 1+2 alone (~3 weeks) deliver the highest-leverage majority of the value.
