# Skill: Roslyn AST Analysis

## Purpose
Called by agent-roslyn-ast before UI migration.
Extracts screen metadata so agent-ui-adapter works from JSON (~120 tokens)
instead of re-reading the full .aspx file (~2,000 tokens) each session.

## Token saving
First extraction: ~2,000 tokens (reads .aspx + .aspx.cs).
All subsequent sessions: ~120 tokens (reads .json cache).
20 screens × 5 sessions = 190,000 tokens saved.

## Cache rule
Check CODEBASE-MAP.md for 🔍 AST-DONE + matching hash.
If match → skip, JSON already valid. Re-extract only if file changed.

## What to extract from .aspx markup
- Every `<asp:*>` tag → type, ID, key attributes (OnClick, DataSourceID, etc.)
- MasterPageFile attribute
- Page Title

## What to extract from .aspx.cs code-behind
- All event handlers (Page_Load, Button_Click, RowCommand, etc.)
- IsPostBack guards
- Session reads / writes
- Response.Redirect targets
- Service / repository calls
- ViewState usage

## suggestedPath decision
| Condition | Path |
|---|---|
| Has UpdatePanel AND GridView | ReactSPA |
| Has chart / reporting controls | ReactSPA |
| Simple CRUD form | RazorPage |
| Read-only display | RazorPage |
| Override flag set | AngularSPA |

## Output location
.github/memory/ast/[PageName].json
