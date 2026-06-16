# Flow Diagram Builder — VS Code Extension

A fully self-contained visual flow diagram builder running inside VS Code.
Drag-and-drop nodes, paste DSL/Mermaid/JSON, animate, and export to SVG, PNG, GIF, or WebM.

---

## Installation (3 ways)

### Option A — Build from source (recommended)

**Prerequisites:** Node.js 16+ installed

```bash
# 1. Install vsce (VS Code Extension packager)
npm install -g @vscode/vsce

# 2. Go into the extension folder
cd flowbuilder-vscode

# 3. Package into a .vsix file
vsce package --no-dependencies

# 4. Install into VS Code
code --install-extension flowbuilder-1.0.0.vsix
```

### Option B — Install .vsix manually via VS Code UI

1. Open VS Code
2. Press `Ctrl+Shift+X` (Extensions panel)
3. Click the `···` menu (top-right of Extensions panel)
4. Click **"Install from VSIX…"**
5. Select `flowbuilder-1.0.0.vsix`
6. Reload VS Code when prompted

### Option C — Development mode (no packaging)

```bash
# 1. Open the extension folder in VS Code
code flowbuilder-vscode/

# 2. Press F5
# VS Code opens a new Extension Development Host window
# with the extension already active
```

---

## Usage

### Open the diagram builder

| Method | Action |
|---|---|
| Command Palette | `Ctrl+Shift+P` → type **"Flow Builder: Open Diagram"** |
| Keyboard shortcut | `Ctrl+Shift+F` (Mac: `Cmd+Shift+F`) |
| Side panel | Command Palette → **"Flow Builder: Open in Side Panel"** |
| Open a `.flow` file | Double-click any `.flow` file in Explorer |

---

## Features inside VS Code

### Everything from the standalone tool
- Drag & drop 25+ shapes (flowchart, UML, infra, data)
- Connect nodes, curved/step/straight edges
- Paste DSL: Arrow flow, Sequence, Mermaid, JSON, YAML, Markdown list
- Animate flow with dash-offset animation
- Per-node: font size, bold, italic, color, shape

### Extra VS Code capabilities

#### Save diagram to workspace
The Export menu has an additional **"Save to Workspace"** option that writes
a `.flow` file (JSON) directly into your project folder via VS Code's save dialog.

#### Load a saved diagram
Double-click any `.flow` file in the VS Code Explorer — it opens in the
Flow Builder with your diagram restored.

#### Insert SVG at cursor
Click **"Insert SVG into Editor"** — the diagram SVG is pasted at the cursor
position in your currently active editor. Useful for embedding diagrams into
Markdown, HTML, or documentation files.

---

## File format (.flow)

`.flow` files are plain JSON — version-controllable, diffable, human-readable:

```json
{
  "nodes": [
    { "id": "abc123", "x": 220, "y": 80, "w": 120, "h": 44,
      "label": "Start", "shape": "oval", "color": "teal",
      "fontSize": 12, "fontBold": false, "fontItalic": false }
  ],
  "edges": [
    { "id": "def456", "src": "abc123", "tgt": "xyz789",
      "label": "yes", "arrow": "arrow", "style": "" }
  ]
}
```

Commit `.flow` files to Git — teammates can open and edit them.

---

## Export formats

| Format | Use case |
|---|---|
| PNG 2× / 3× | PowerPoint, Word, Notion, Slack |
| SVG static | Confluence, Figma, GitHub README |
| SVG animated | Browser embeds, HTML docs |
| GIF animated | Confluence pages, email, PPT |
| WebM | Video embeds, Notion, modern PPT |
| Copy PNG | Paste directly into any app |
| Copy SVG | Paste into Figma, Illustrator |

---

## Keyboard shortcuts (inside the diagram)

| Key | Action |
|---|---|
| `V` | Select tool |
| `C` | Connect tool |
| `P` | Pan tool |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+C` | Copy diagram as PNG |
| `Ctrl+A` | Select all |
| `Delete` | Delete selected node/edge |
| Double-click canvas | Add new node |
| Double-click node | Rename node |
| Right-click | Context menu |
| Scroll | Zoom in/out |
| `+` / `-` | Zoom in/out |

---

## Folder structure

```
flowbuilder-vscode/
├── package.json          ← Extension manifest, commands, keybindings
├── extension.js          ← Entry point: opens WebView, handles messages
├── media/
│   └── flowbuilder.html  ← The complete diagram builder (self-contained)
└── .vscodeignore         ← Files excluded from the .vsix package
```

---

## Updating the diagram builder

To update the tool with a new version of `flowbuilder.html`:

```bash
# Replace the file
cp /path/to/new/flowbuilder.html flowbuilder-vscode/media/flowbuilder.html

# Re-package
vsce package --no-dependencies

# Re-install
code --install-extension flowbuilder-1.0.0.vsix
```

---

## Troubleshooting

**"vsce: command not found"**
```bash
npm install -g @vscode/vsce
```

**"Extension host terminated unexpectedly"**
- Open Output panel → select "Extension Host" from dropdown
- Check for missing `media/flowbuilder.html`

**WebView shows blank page**
- Ensure `media/flowbuilder.html` exists
- Check that `localResourceRoots` in `extension.js` points to the correct folder

**Diagram not saving**
- Must have a workspace folder open (`File → Open Folder`)

**Keybinding `Ctrl+Shift+F` conflicts**
- Change in `package.json` under `contributes.keybindings`

---

## Requirements

- VS Code 1.80.0 or later
- Node.js 16+ (only needed for packaging, not for running)
- No internet required after install — fully offline capable
