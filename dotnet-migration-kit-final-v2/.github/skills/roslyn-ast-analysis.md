# Skill: Roslyn AST Analysis

## Identity
Extracts structured metadata from C#/VB.NET source using AST pattern matching.
Produces per-screen JSON used by UI agents to generate React/Angular components.
No Roslyn SDK required — Copilot reads source as text and extracts AST-equivalent data.

## Token rule
Check CODEBASE-MAP.md for existing ast.json entries. If hash matches → skip.
AST extraction is expensive (~2,000 tokens/file). Cache aggressively.

## Invoke
```
Load: skills/roslyn-ast-analysis.md
TARGET: [file.aspx + file.aspx.cs]
OUTPUT: .github/memory/ast/[ScreenName].ast.json
```

## What gets extracted

### From .aspx markup
```
Controls: every <asp:*> tag → type, ID, visible properties
Events: every asp event attribute (OnClick, OnRowCommand, etc.)
MasterPage: MasterPageFile attribute
Title: Page title
ContentPlaceHolders used
```

### From .aspx.cs code-behind
```
Class name, base class
Page lifecycle methods (Page_Load, Page_PreRender, etc.)
Event handlers (Button_Click, GridView_RowCommand, etc.)
Properties and fields (especially those bound to controls)
Service/repo calls made
Session reads/writes
Response.Redirect targets
ViewState usage
```

## Output: [ScreenName].ast.json
```json
{
  "screen": "CustomerList",
  "file": "src/WebApp/Customer/List.aspx",
  "masterPage": "Site.Master",
  "title": "Customer List",
  "controls": [
    { "type": "GridView", "id": "gvCustomers", "hasRowCommand": true, "hasPaging": true },
    { "type": "TextBox", "id": "txtSearch", "maxLength": 100 },
    { "type": "Button", "id": "btnSearch", "onClick": "btnSearch_Click" },
    { "type": "Button", "id": "btnAdd", "onClick": "btnAdd_Click" },
    { "type": "UpdatePanel", "id": "upGrid", "wrapsControls": ["gvCustomers"] }
  ],
  "events": [
    { "name": "Page_Load", "isPostBackGuarded": true, "callsBindGrid": true },
    { "name": "btnSearch_Click", "action": "filter-and-rebind" },
    { "name": "btnAdd_Click", "action": "redirect", "target": "Add.aspx" },
    { "name": "gvCustomers_RowCommand", "commands": ["Edit", "Delete", "View"] }
  ],
  "dataBindings": [
    { "source": "_customerService.GetAll(searchTerm)", "target": "gvCustomers" }
  ],
  "sessionReads": ["CurrentUserId", "UserRole"],
  "redirects": ["Add.aspx", "Edit.aspx?id={id}"],
  "viewStateUsed": false,
  "hasUpdatePanel": true,
  "estimatedComplexity": "Medium",
  "suggestedMigrationPath": "ReactSPA",
  "suggestedComponentName": "CustomerListPage",
  "suggestedApiEndpoints": [
    "GET /api/customers?search={term}",
    "DELETE /api/customers/{id}"
  ]
}
```

## How UI agents use this output
```
agent-ui-adapter reads [ScreenName].ast.json FIRST.
Uses controls[] to know exactly what HTML elements to generate.
Uses events[] to know what handlers to create.
Uses suggestedApiEndpoints[] to know what API routes needed.
Saves re-reading the .aspx file entirely → token saving.
```

## Copilot prompt to run AST extraction
```
Read .github/skills/roslyn-ast-analysis.md.
For each ⏳ QUEUE .aspx page in CODEBASE-MAP.md:
  1. Read the .aspx and .aspx.cs files
  2. Extract the AST metadata per the skill specification
  3. Write to .github/memory/ast/[ScreenName].ast.json
  4. Add ast.json path to CODEBASE-MAP.md entry
Do NOT migrate yet — extraction only. Update map after each screen.
```
