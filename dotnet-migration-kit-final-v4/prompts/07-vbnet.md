# Prompt: VB.NET → C#

## When to use
signals.json: hasVBNet = true.

## Paste this in Copilot Agent mode

```
Read .github/memory/MAP.md.
For each ⏳ QUEUE .vb file — hash check first, skip ✅ DONE.

Translate VB.NET syntax to C# .NET 8. Logic unchanged — syntax only.

DECLARATIONS:
  Dim x As Integer = 5      → int x = 5;
  Dim s As String = "hi"    → string s = "hi";
  Dim obj As New MyClass()  → var obj = new MyClass();
  Public Property Name As String → public string Name { get; set; }

METHODS:
  Public Function Get(id As Integer) As User → public User Get(int id) {
  End Function                               → }
  Public Sub DoWork()  → public void DoWork() {
  End Sub              → }

CONTROL FLOW:
  If x > 0 Then / ElseIf / Else / End If → if { } else if { } else { }
  For i As Integer = 0 To 9 / Next       → for (int i = 0; i <= 9; i++) { }
  For Each item In list / Next            → foreach (var item in list) { }
  Select Case x / Case 1 / Case Else / End Select → switch (x) { case 1: default: }
  Do While / Loop                         → while { }

OPERATORS:
  AndAlso → &&   OrElse → ||   Not → !
  = (compare) → ==   <> → !=   Mod → %
  & (string concat) → +

STRING:
  String.Format("{0} {1}", a, b) → $"{a} {b}"
  IsNothing(x) → x is null
  Strings.Left(s,n) → s[..n]
  Strings.Right(s,n) → s[^n..]
  Strings.Mid(s,start,len) → s.Substring(start-1, len)
  Strings.Len(s) → s.Length

ERROR HANDLING:
  Try/Catch ex As Exception/Finally/End Try → try { } catch (Exception ex) { } finally { }

EVENTS:
  AddHandler btn.Click, AddressOf Handler → btn.Click += Handler;
  RaiseEvent MyEvent(args) → MyEvent?.Invoke(this, args);

MISC:
  Microsoft.VisualBasic.* → remove entirely, use C# equivalents
  IIf(cond, t, f) → cond ? t : f
  Partial Class Foo Inherits Page → public partial class Foo : Page
  Implements IFoo → add to class: public class Foo : BaseFoo, IFoo

OUTPUT: src-core/[MatchingProject].Core/[SameRelativePath].cs

Apply all rules from migrate-cs.md (async, DI, logging, nullable) to the translated C# output.

Update MAP.md after each file:
  ✅ DONE | [PROJECT] | [original .vb path → .cs path] | [hash] | vbnet | — |
```
