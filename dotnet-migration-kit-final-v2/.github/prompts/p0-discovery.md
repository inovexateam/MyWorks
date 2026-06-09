# Prompt: P0 Discovery Scan

## Purpose
Triggers the full P0 discovery scan. Produces migration-state.json,
screen-inventory.csv, and populates CODEBASE-MAP.md. Run once per project.
Never re-run if migration-state.json exists with matching solution hash.

---

## The Prompt

```
Read .github/skills/discovery-scan.md.

Scan this entire solution. For every .cs, .vb, .aspx, .ascx, .asmx,
.csproj, .vbproj file found:

1. Detect all patterns listed in discovery-scan.md (Oracle, DB2, Redis,
   Venafi, WCF, LDAP, Apigee, PingFederate, FormsAuthentication,
   Crystal Reports, log4net, ADO.NET, EF6, EDMX, VB.NET, console apps,
   Web API 2, SOAP services, UpdatePanel, GridView, MasterPage).

2. Write .github/memory/migration-state.json with all boolean flags
   and counts per the skill specification.

3. Write .github/memory/screen-inventory.csv with one row per .aspx page:
   Screen, File, LOC, Controls, HasCodeBehind, UpdatePanel, GridView,
   MasterPage, EstimatedHours, MigrationPath

4. Populate .github/memory/CODEBASE-MAP.md — one line per file:
   STATUS | PROJECT | FILE | HASH | AGENT | COV | NOTE
   All new files start as ⏳ QUEUE.
   Files with Crystal Reports, COM, OpenAccess ORM → 🚧 BLOCK.

5. Show a summary table when done:
   | Category | Count | Flag |
   For each detected technology, count files affected.

Do not migrate anything yet. Discovery only.
```

---

## After scan — review BLOCK entries

Open `.github/memory/CODEBASE-MAP.md` and filter for `🚧 BLOCK`.
Each blocked file needs a human decision before migration can continue.
Common blocks and their decisions:

| Block reason | Decision needed |
|---|---|
| Crystal Reports | Choose: NETCore.Reporting / FastReport / SSRS |
| OpenAccess ORM | Rewrite with EF Core (no equivalent) |
| COM Interop | Assess: remove / wrap / platform invoke |
| GAC-only assembly | Find NuGet equivalent or containerize on Windows |
| Venafi SDK | Decide: K8s cert-manager or typed HttpClient |

Once decisions made, update map entries from `🚧 BLOCK` to `⏳ QUEUE` with
a note on the chosen approach. Then run Phase 1.
