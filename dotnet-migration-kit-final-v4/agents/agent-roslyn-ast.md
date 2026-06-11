# Agent: Roslyn AST Extractor

## Identity
Extracts structured metadata from .aspx + .aspx.cs files before UI migration.
Writes per-screen JSON to .github/memory/ast/.
Copilot reads JSON (~120 tokens) instead of re-parsing .aspx (~2,000 tokens).

## Pre-work
Check CODEBASE-MAP.md for 🔍 AST-DONE status with matching hash → skip.

## What to extract per screen

Read .aspx markup and .aspx.cs code-behind together. Write:

```json
// .github/memory/ast/[PageName].json
{
  "page": "CustomerList",
  "file": "src/WebApp/Customer/List.aspx",
  "masterPage": "Site.Master",
  "controls": [
    { "type": "GridView", "id": "gvCustomers", "hasRowCommand": true, "hasPaging": true },
    { "type": "TextBox", "id": "txtSearch", "maxLength": 100 },
    { "type": "Button", "id": "btnSearch", "onClick": "btnSearch_Click" },
    { "type": "UpdatePanel", "id": "upGrid", "wrapsControls": ["gvCustomers"] },
    { "type": "DropDownList", "id": "ddlStatus", "onSelectedIndex": "ddlStatus_Changed" }
  ],
  "events": [
    { "name": "Page_Load", "isPostBackGuarded": true, "bindsControl": "gvCustomers" },
    { "name": "btnSearch_Click", "action": "filter-rebind", "target": "gvCustomers" },
    { "name": "gvCustomers_RowCommand", "commands": ["Edit", "Delete", "View"] },
    { "name": "btnExport_Click", "action": "export-excel" }
  ],
  "dataBindings": [
    { "source": "_service.GetCustomers(searchTerm, status)", "target": "gvCustomers" }
  ],
  "sessionReads": ["CurrentUserId", "UserRole"],
  "sessionWrites": ["SelectedCustomerId"],
  "redirects": ["Edit.aspx?id={id}", "Add.aspx"],
  "hasUpdatePanel": true,
  "hasViewState": false,
  "suggestedPath": "ReactSPA",
  "apiEndpoints": [
    "GET /api/customers?search={term}&status={status}",
    "DELETE /api/customers/{id}"
  ]
}
```

## suggestedPath rules
- `ReactSPA` — has UpdatePanel + GridView + multiple events
- `RazorPage` — simple form, CRUD, read-only display
- `AngularSPA` — org standardizes Angular (set via override flag)

## Map update
🔍 AST-DONE | WebApp | src/WebApp/Customer/List.aspx | [hash] | agent-roslyn-ast | — | ast:memory/ast/CustomerList.json
