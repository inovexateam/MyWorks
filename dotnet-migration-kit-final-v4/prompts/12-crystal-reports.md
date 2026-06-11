# Prompt: Crystal Reports Decision

## When to use
MAP.md has 🚧 BLOCK entries for Crystal Reports / .rpt files.
Human must choose an option. Then run the migration prompt.

## Options

| Option | Package (Artifactory) | Best for | Cost |
|---|---|---|---|
| Microsoft.Reporting.NETCore | Microsoft.Reporting.NETCore 3.0.0 | Existing .rdlc files, simple tables | Free |
| FastReport | FastReport.OpenSource 2024.x | Complex reports, charts, subreports | Free (OSS) |
| SSRS | No package — REST API calls | Org already has SQL Server | $0 extra |
| Telerik / DevExpress | Org license required | Closest to Crystal feature set | Paid |

## After choosing — paste this in Copilot Agent mode

```
Read .github/memory/MAP.md.
Crystal Reports replacement decision: [OPTION CHOSEN]

For each 🚧 BLOCK .rpt / report file in MAP.md:

IF option = Microsoft.Reporting.NETCore:
  Add to .csproj: <PackageReference Include="Microsoft.Reporting.NETCore" Version="3.0.0" />
  Convert .rpt → .rdlc (manual redesign required — Copilot cannot auto-convert .rpt binary)
  Create report service:
    public class ReportService(IWebHostEnvironment env) {
      public byte[] GeneratePdf(string reportName, IDictionary<string,object> params) {
        var path = Path.Combine(env.ContentRootPath, "Reports", $"{reportName}.rdlc");
        using var rs = new LocalReport();
        rs.ReportPath = path;
        foreach (var p in params) rs.SetParameters(new ReportParameter(p.Key, p.Value?.ToString()));
        return rs.Render("PDF");
      }
    }

IF option = FastReport:
  Add: <PackageReference Include="FastReport.OpenSource" Version="2024.1.0" />
  Reports must be redesigned in FastReport format (.frx).
  Insert: // TODO-MIGRATION: Redesign [ReportName] in FastReport designer

IF option = SSRS:
  No package. Call SSRS REST API:
    var url = $"{config["Ssrs:BaseUrl"]}/api/v2.0/reports/{reportPath}/Export?format=PDF";
    var response = await _http.GetAsync(url, ct);

IF option = none-yet:
  Leave as 🚧 BLOCK. Insert comment in calling code:
    // TODO-MIGRATION: Crystal Reports has no .NET 8 equivalent — decision pending

Update MAP.md: change 🚧 BLOCK → ✅ DONE (if replaced) or keep 🚧 BLOCK (if pending).
```
