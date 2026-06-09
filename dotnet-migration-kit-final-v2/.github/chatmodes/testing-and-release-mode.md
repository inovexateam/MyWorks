# Copilot: Testing Mode

## Activate with this prompt
```
Read .github/agents/agent-test-runner.md.
Run the test suite for [component or "all"].
Show pass/fail counts, coverage, and diagnose any failures.
```

## Full validation suite
```
Read .github/agents/agent-test-runner.md.
Run dotnet build src-core/ — 0 errors required.
Run dotnet test filtering Category!=Integration.
Run dotnet list package --vulnerable — 0 HIGH/CRITICAL.
Check grep -r "using System.Web" src-core/ — must be empty.
Report results. Block on failures.
```

---

# Copilot: Release Mode

## Activate with this prompt
```
Read .github/plugins/release-bundle.md.
Run release validation for v[version] targeting [staging|production].
Follow all stages. Show status after each stage.
```

## Staging release
```
Read .github/plugins/release-bundle.md.
Run stages 1-6 for staging deployment of v[version].
Gate on: build, tests, security scan, DB migration dry-run.
Show go/no-go decision with evidence.
```
