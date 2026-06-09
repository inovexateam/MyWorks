# Prompt: WebForms UI Migration

## When to use
signals.json: hasWebForms = true. Run AFTER all class library projects are done.

## Step 1 — AST extraction (paste first)

```
Read .github/memory/MAP.md.
For each ⏳ QUEUE .aspx page — hash check first, skip ✅ DONE.

For each .aspx file:
  Read the .aspx markup and .aspx.cs code-behind together.
  Extract and write .github/memory/ast/[PageName].json:
  {
    "page": "[PageName]",
    "masterPage": "[filename or null]",
    "controls": [{ "type": "GridView", "id": "gvOrders", "hasRowCommand": true, "hasPaging": true }],
    "events": [{ "name": "btnSave_Click", "action": "save-and-redirect", "target": "List.aspx" }],
    "sessionReads": ["UserId","UserRole"],
    "dataBindings": [{ "source": "_service.GetOrders()", "target": "gvOrders" }],
    "hasUpdatePanel": true,
    "suggestedPath": "RazorPage or ReactSPA",
    "apiEndpoints": ["GET /api/orders", "POST /api/orders/{id}/save"]
  }
  Suggest ReactSPA if: UpdatePanel + GridView + complex events.
  Suggest RazorPage otherwise.

Update MAP.md: 🔍 AST-DONE | [file] | [hash] | ast-extracted | — | ast:[PageName].json
```

## Step 2 — Migrate using AST (paste after Step 1)

```
Read .github/memory/MAP.md.
For each 🔍 AST-DONE .aspx page:

  Read .github/memory/ast/[PageName].json — do NOT re-read the .aspx file.

  IF suggestedPath = RazorPage:
    Create src-core/WebApp.Core/Pages/[Section]/[PageName].cshtml.cs:
      public class [PageName]Model : PageModel {
        // Inject services found in dataBindings[]
        // OnGetAsync() — maps from Page_Load(!IsPostBack) logic
        // OnPostAsync() — maps from primary button click event
        // OnPost[Action]Async(int id) — one per RowCommand or named handler
      }
    Create src-core/WebApp.Core/Pages/[Section]/[PageName].cshtml:
      @page @model [PageName]Model
      // Map every control[] entry:
      GridView → <table>@foreach(var item in Model.Items)
      TextBox  → <input asp-for="Input.Field">
      Button   → <button type="submit">
      DropDown → <select asp-for="Input.Field" asp-items="Model.Options">
      UpdatePanel → AJAX fetch to partial: <div id="target"> + JS fetch()
      MasterPage → Layout = "_Layout"
      @section Scripts { <partial name="_ValidationScriptsPartial" /> }

  IF suggestedPath = ReactSPA:
    Create API endpoints in Program.cs for each apiEndpoints[] entry.
    Create src-core/WebApp.Core/ClientApp/src/pages/[PageName].tsx:
      React functional component with useState, useEffect.
      Map controls[] to JSX elements.
      Map events[] to onClick/onChange handlers calling the API endpoints.
      Type all data with TypeScript interfaces.

  MasterPage → _Layout.cshtml:
    ContentPlaceHolder → @RenderBody() or @await RenderSectionAsync("name", false)

  .ascx UserControl:
    Simple → Partial view _[ControlName].cshtml
    Has logic → ViewComponent: [Name]ViewComponent.cs + Views/Shared/Components/[Name]/Default.cshtml

Update MAP.md: ✅ DONE | [file] | [hash] | webforms-ui | — |
Run: grep -r "runat=\"server\"" src-core/ — must return empty.
```

## Control → .NET 8 quick reference

| WebForms | .NET 8 |
|---|---|
| `<asp:GridView>` | `<table> @foreach` |
| `<asp:Repeater>` | `@foreach` + partial |
| `<asp:UpdatePanel>` | AJAX fetch + partial or React component |
| `<asp:TextBox>` | `<input asp-for="...">` |
| `<asp:DropDownList>` | `<select asp-for="..." asp-items="...">` |
| `<asp:Button>` | `<button type="submit">` |
| `<asp:RequiredFieldValidator>` | `[Required]` + `<span asp-validation-for>` |
| `Page_Load(!IsPostBack)` | `OnGetAsync()` |
| `Button_Click` | `OnPostAsync()` |
| `GridView_RowCommand` | `OnPost[Command]Async(int id)` |
| `Response.Redirect("x.aspx")` | `return RedirectToPage("./X")` |
| `Session["key"]` | `HttpContext.Session.GetString("key")` |
| ViewState | Remove — re-query or use TempData |
