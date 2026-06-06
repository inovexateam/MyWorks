# Prompt: Refactor UI

## Purpose
Provides agents and Copilot users with precise instructions for converting WebForms `.aspx` pages and `.ascx` user controls to ASP.NET Core Razor Pages, MVC Views, or Blazor components.

---

## The UI Refactor Prompt

```
You are an expert ASP.NET Core UI migration engineer. Convert the following 
WebForms page/control to modern ASP.NET Core. The conversion must be 100% 
functionally equivalent — every button, every grid, every validation, 
every postback behavior must work identically in the new implementation.

[PASTE .aspx / .aspx.cs / .ascx CONTENT HERE]

Follow these steps exactly:
```

---

## STEP 1 — UI Inventory

```
Before writing any code, produce this inventory:

1. PAGE TYPE: [Data entry form | Data display | Mixed | Navigation | Report]
2. MASTER PAGE: [Name of master page used, if any]
3. SERVER CONTROLS FOUND:
   - List every <asp:*> control with its ID and purpose
4. EVENT HANDLERS FOUND:
   - List every Button_Click, GridView_RowCommand, etc.
5. DATA SOURCES:
   - What data does this page load? (DB queries, service calls, etc.)
6. AJAX/DYNAMIC BEHAVIOUR:
   - Any UpdatePanel? Timer? ScriptManager?
7. VALIDATION:
   - List every validator and what it validates
8. NAVIGATION:
   - List every Response.Redirect and Server.Transfer
9. SESSION/STATE:
   - Any Session, ViewState, or Application state reads/writes?
10. COMPLEXITY SCORE: [1-Simple | 2-Medium | 3-Complex | 4-Very Complex]
```

---

## STEP 2 — Migration Target Decision

```
Based on the inventory, choose:

IF page is primarily form-based (user fills fields, clicks submit):
  → Razor Page (.cshtml + PageModel)

IF page is purely a display/read-only view driven by a controller:
  → MVC Controller + View (.cshtml)

IF page has complex real-time updates, or replaces heavy UpdatePanel:
  → Blazor Server Component (.razor)

IF page is a reusable sub-component (.ascx):
  → Partial View (simple) OR View Component (with logic) OR Razor Component

State your choice and reason before proceeding.
```

---

## STEP 3 — Page Structure Migration

### For Razor Pages:

```
CREATE: Pages/[Section]/[PageName].cshtml
CREATE: Pages/[Section]/[PageName].cshtml.cs (PageModel)

PageModel template:
────────────────────────────────────────────────────────
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using [YourApp].Services.Interfaces;
using [YourApp].Models;

namespace [YourApp].Pages.[Section];

[Authorize] // Add appropriate auth
public class [PageName]Model : PageModel {
    private readonly I[Service] _service;
    private readonly ILogger<[PageName]Model> _logger;
    
    // Properties for the view (bound from form: [BindProperty])
    [BindProperty]
    public [InputModel] Input { get; set; } = new();
    
    // Read-only display properties (not bound)
    public IReadOnlyList<[Item]> Items { get; private set; } = [];
    
    public [PageName]Model(I[Service] service, ILogger<[PageName]Model> logger) {
        _service = service;
        _logger = logger;
    }
    
    // GET handler (replaces Page_Load when !IsPostBack)
    public async Task OnGetAsync([optional route parameters]) {
        Items = await _service.GetItemsAsync();
    }
    
    // POST handler (replaces Button_Click or GridView events)
    public async Task<IActionResult> OnPostAsync() {
        if (!ModelState.IsValid) {
            // Re-load any display data needed for the form
            Items = await _service.GetItemsAsync();
            return Page(); // Redisplay with validation errors
        }
        
        await _service.SaveAsync(Input);
        TempData["SuccessMessage"] = "Saved successfully";
        return RedirectToPage(); // PRG pattern
    }
}

Input model (if form has multiple fields):
────────────────────────────────────────────────────────
public class [PageName]InputModel {
    [Required]
    [MaxLength(200)]
    [Display(Name = "Product Name")]
    public string Name { get; set; } = string.Empty;
    
    [Range(0.01, 999999.99)]
    [Display(Name = "Price")]
    public decimal Price { get; set; }
    
    // Mirror every form field with appropriate annotations
}
```

### For the .cshtml view:

```cshtml
─── .cshtml template ──────────────────────────────────────
@page
@model [PageName]Model
@{
    ViewData["Title"] = "[Page Title]";
    Layout = "_Layout"; // Replaces MasterPageFile
}

@* Success/error messages (replaces code-behind label updates) *@
@if (TempData["SuccessMessage"] != null) {
    <div class="alert alert-success">@TempData["SuccessMessage"]</div>
}

@* Form (replaces <asp:Button> + postback) *@
<form method="post">
    <div asp-validation-summary="ModelOnly" class="text-danger"></div>
    
    <div class="mb-3">
        <label asp-for="Input.Name" class="form-label"></label>
        <input asp-for="Input.Name" class="form-control" />
        <span asp-validation-for="Input.Name" class="text-danger"></span>
    </div>
    
    <button type="submit" class="btn btn-primary">Save</button>
    <a asp-page="./Index" class="btn btn-secondary">Cancel</a>
</form>

@* Data grid (replaces GridView) *@
@if (Model.Items.Any()) {
    <table class="table table-striped">
        <thead>
            <tr>
                <th>Name</th>
                <th>Price</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            @foreach (var item in Model.Items) {
                <tr>
                    <td>@item.Name</td>
                    <td>@item.Price.ToString("C")</td>
                    <td>
                        <a asp-page="./Edit" asp-route-id="@item.Id" 
                           class="btn btn-sm btn-outline-primary">Edit</a>
                        <form method="post" asp-page-handler="Delete" 
                              asp-route-id="@item.Id" class="d-inline"
                              onsubmit="return confirm('Delete this item?')">
                            <button type="submit" class="btn btn-sm btn-outline-danger">Delete</button>
                        </form>
                    </td>
                </tr>
            }
        </tbody>
    </table>
}

@section Scripts {
    @{await Html.RenderPartialAsync("_ValidationScriptsPartial");}
    @* Add page-specific JS here *@
}
───────────────────────────────────────────────────────────
```

---

## STEP 4 — Control-by-Control Conversion

For each server control in the inventory, provide the exact Razor equivalent.

Follow the complete control migration map in `agent-ui-adapter.md`.

Key rules:
```
✅ Every <asp:TextBox>         → <input asp-for="...">
✅ Every <asp:DropDownList>    → <select asp-for="..." asp-items="...">
✅ Every <asp:GridView>        → HTML table + @foreach
✅ Every <asp:RequiredField>   → [Required] attribute + <span asp-validation-for>
✅ Every <asp:Button>          → <button type="submit"> or AJAX fetch
✅ Every <asp:Label> (display) → <span>@Model.Value</span>
✅ Every UpdatePanel           → AJAX partial refresh (fetch + partial view)
✅ Every Response.Redirect     → return RedirectToPage() or return Redirect()
```

---

## STEP 5 — Code-Behind Logic Migration

For every event handler in the code-behind:

```
Button1_Click(sender, e) { Save(); }
→ OnPostAsync() { await _service.SaveAsync(Input); return RedirectToPage(); }

GridView1_RowCommand with CommandName="Delete"
→ OnPostDeleteAsync(int id) { await _service.DeleteAsync(id); return RedirectToPage(); }

GridView1_RowCommand with CommandName="Edit"  
→ OnGetEditAsync(int id) { return RedirectToPage("./Edit", new { id }); }

ddlCategory_SelectedIndexChanged
→ AJAX call to partial endpoint OR form submit + re-render with selected value preserved
```

---

## STEP 6 — Output All Files

Produce all new files in this order:
1. `[PageName].cshtml.cs` — PageModel (complete, compilable)
2. `[PageName].cshtml` — Razor markup (complete)
3. Any partial views created (`_[Name].cshtml`)
4. Any View Components created (`[Name]ViewComponent.cs` + `Default.cshtml`)
5. Any new service method signatures needed (as interfaces)

---

## STEP 7 — Post-Migration Checklist

```
After producing all files, verify:
☐ Zero <asp: tags in any .cshtml file
☐ Zero runat="server" attributes
☐ All forms have method="post" (not missing)
☐ Anti-forgery handled by tag helpers (automatic)
☐ All validation attributes on InputModel
☐ _ValidationScriptsPartial included in @section Scripts
☐ No inline JavaScript (extract to .js file)
☐ Mobile responsive classes used (Bootstrap or equivalent)
☐ All user-facing strings in <label> tags (not hardcoded in inputs)
☐ Images have alt attributes
☐ Form inputs have associated <label> (accessibility)
☐ All redirects use PRG pattern (Post-Redirect-Get)
```
