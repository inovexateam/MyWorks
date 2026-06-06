# Agent: VB.NET Migrator

## Identity
Migrates VB.NET (.vb) files to C# .NET 8. Token-first: check CODEBASE-MAP.md
hash before loading any file. VB.NET and C# are semantically equivalent —
this is syntax translation, not logic change.

## Trigger
migration-state.json shows hasVBNet: true
OR file extension is .vb

## Pre-work
```
STEP 1: Read CODEBASE-MAP.md — skip ✅ files
STEP 2: Read migration-state.json — confirm VB.NET present
STEP 3: Only then load file contents
```

## VB.NET → C# translation rules

### Syntax
```vb
' VB → C# pattern map

' Declarations
Dim x As Integer = 5         → int x = 5;
Dim s As String = "hi"       → string s = "hi";
Public Property Name As String → public string Name { get; set; }
Dim obj As New MyClass()     → var obj = new MyClass();

' Methods
Public Function GetUser(id As Integer) As User  → public User GetUser(int id) {
End Function                                     → }

Public Sub DoWork()          → public void DoWork() {
End Sub                      → }

' Control flow
If x > 0 Then                → if (x > 0) {
ElseIf x = 0 Then            → } else if (x == 0) {
Else                         → } else {
End If                       → }

For i As Integer = 0 To 9   → for (int i = 0; i <= 9; i++) {
Next                         → }

For Each item In collection  → foreach (var item in collection) {
Next                         → }

Select Case x                → switch (x) {
  Case 1                     →   case 1:
  Case Else                  →   default:
End Select                   → }

' Operators
AndAlso   → &&
OrElse    → ||
Not       → !
=  (compare) → ==
<>        → !=
Mod       → %

' String
& (concat) → +
String.Format("{0}", x) → $"{x}"
IsNothing(x) → x is null
IsNothing(x) = False → x is not null

' Error handling
Try                          → try {
Catch ex As Exception        → } catch (Exception ex) {
Finally                      → } finally {
End Try                      → }

' Events
AddHandler btn.Click, AddressOf Handler → btn.Click += Handler;
RaiseEvent MyEvent(args)     → MyEvent?.Invoke(args);

' Inheritance
Class Foo : Inherits Bar     → class Foo : Bar {
Implements IFoo              → — add to class declaration: class Foo : Bar, IFoo
```

### .NET API differences
```
Microsoft.VisualBasic.*     → Remove — use C# equivalents
Strings.Left(s, n)         → s[..n]
Strings.Right(s, n)        → s[^n..]
Strings.Mid(s, start, len) → s.Substring(start-1, len)
Strings.Len(s)             → s.Length
Strings.UCase(s)           → s.ToUpper()
Strings.LCase(s)           → s.ToLower()
Strings.Trim(s)            → s.Trim()
IIf(condition, t, f)       → condition ? t : f
```

### WebForms VB code-behind
```vb
' .aspx.vb → .cshtml.cs (Razor PageModel)
Partial Class ProductList_aspx
  Inherits System.Web.UI.Page
  Protected Sub Page_Load(sender As Object, e As EventArgs)
    If Not IsPostBack Then
      GridView1.DataSource = GetProducts()
      GridView1.DataBind()
    End If
  End Sub
End Class

' → C# Razor PageModel
public class ProductListModel : PageModel {
    public IReadOnlyList<Product> Products { get; private set; } = [];
    public async Task OnGetAsync() {
        Products = await _service.GetProductsAsync();
    }
}
```

## File output
- Input: `src/BC/CustomerService.vb`
- Output: `src-core/BC.Core/CustomerService.cs`
- Map entry: `✅ DONE | BC | src-core/BC.Core/CustomerService.cs | [hash] | vbnet-migrator | — | converted from VB`

## Copilot prompt
```
Read .github/memory/CODEBASE-MAP.md and .github/agents/agent-vbnet-migrator.md.
Migrate all ⏳ QUEUE .vb files to C# .NET 8. Place output in matching
src-core/ project. Update CODEBASE-MAP.md after each file.
```
