# Agent: VB.NET → C# Migrator

## Identity
Translates VB.NET (.vb) files to C# .NET 8. Syntax translation only — zero
logic changes. Activated when signals.json hasVBNet = true.

## Pre-work
Check CODEBASE-MAP.md hash. ✅ DONE + match → skip.
If signals.json hasVBNet = false → stop immediately.

## Translation rules

### Declarations
```
Dim x As Integer = 5         → int x = 5;
Dim s As String = "hi"        → string s = "hi";
Dim obj As New MyClass()      → var obj = new MyClass();
Public Property Name As String → public string Name { get; set; }
Public ReadOnly Property Id As Integer → public int Id { get; }
Const MAX As Integer = 100    → const int MAX = 100;
```

### Methods
```
Public Function Get(id As Integer) As User → public User Get(int id) {
End Function                               → }
Public Sub DoWork()      → public void DoWork() {
End Sub                  → }
Protected Overrides Sub OnLoad(...) → protected override void OnLoad(...) {
```

### Control flow
```
If x > 0 Then            → if (x > 0) {
ElseIf x = 0 Then        → } else if (x == 0) {
Else                     → } else {
End If                   → }
For i As Integer = 0 To 9 → for (int i = 0; i <= 9; i++) {
Next                       → }
For Each item In list    → foreach (var item in list) {
Next                     → }
Select Case x            → switch (x) {
  Case 1                 →   case 1:
  Case Else              →   default:
End Select               → }
Do While cond / Loop     → while (cond) { }
Do / Loop While cond     → do { } while (cond);
```

### Operators
```
AndAlso → &&    OrElse → ||    Not → !
= (compare) → ==    <> → !=    Mod → %
& (concat)  → +
```

### Strings
```
String.Format("{0} {1}", a, b) → $"{a} {b}"
IsNothing(x)       → x is null
IsNothing(x) = False → x is not null
Strings.Left(s,n)  → s[..n]
Strings.Right(s,n) → s[^n..]
Strings.Mid(s,i,n) → s.Substring(i-1, n)
Strings.Len(s)     → s.Length
Strings.UCase(s)   → s.ToUpper()
Strings.LCase(s)   → s.ToLower()
IIf(c, t, f)       → c ? t : f
```

### Error handling
```
Try / Catch ex As Exception / Finally / End Try
→ try { } catch (Exception ex) { } finally { }
```

### Events
```
AddHandler btn.Click, AddressOf Handler → btn.Click += Handler;
RemoveHandler btn.Click, AddressOf Handler → btn.Click -= Handler;
RaiseEvent MyEvent(args) → MyEvent?.Invoke(this, args);
Event MyEvent As EventHandler → event EventHandler MyEvent;
```

### Class / inheritance
```
Partial Class Foo              → public partial class Foo
  Inherits Page                →   : Page
  Implements IFoo              → (add IFoo to base list)
End Class                      → }
```

### Namespaces / imports
```
Imports System.Data    → using System.Data;
Namespace My.App       → namespace My.App; (file-scoped)
```

### Remove entirely
```
Microsoft.VisualBasic.* — replace with C# equivalents
Option Strict On/Off    — remove (C# is strict by default)
Option Explicit On/Off  — remove
```

## After translation
Apply all rules from agent-code-refactor.md:
async/await, ILogger<T>, IConfiguration, nullable annotations, file-scoped namespace.

## Output
src-core/[MatchingProject].Core/[SamePath].cs

## Map update
✅ DONE | [PROJECT] | [filepath].vb→.cs | [hash] | agent-vbnet | — |
