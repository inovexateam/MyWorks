# Hook: Pre-Commit (Artifactory-Only)

## All tools either ship with the .NET SDK or are sourced from Artifactory.
## Zero pip install. Zero npm install. Zero external registries.

---

## Execution Sequence

### Check 1: Secret Detection — org scanner or git grep fallback
```bash
# Option A: If your org hosts a scanner in Artifactory, call it here
# [your-org-secret-scanner] --path . --staged-only

# Option B: Zero-dependency fallback — pure git + grep
# Scans only staged files, catches the most common patterns
STAGED=$(git diff --cached --name-only)
if [ -z "$STAGED" ]; then exit 0; fi

HITS=$(echo "$STAGED" | xargs grep -iEn \
  '(password\s*=\s*[^$<{"\x27][^;\n]{3,}|connectionstring.*password\s*=|api[_-]?key\s*[:=]\s*[a-zA-Z0-9]{16,}|secret\s*[:=]\s*[^$<{"\x27][^;\n]{3,})' \
  2>/dev/null \
  | grep -iv '(//.*|#.*|todo|example|placeholder|your[_-]|change[_-]me|<\w+>)')

if [ -n "$HITS" ]; then
  echo "🚨 BLOCKED: Possible secrets in staged files:"
  echo "$HITS"
  echo "Move to environment variables or Azure Key Vault"
  exit 1
fi
echo "✅ Secret scan passed"
```

### Check 2: Build — .NET SDK only
```bash
dotnet build --no-incremental --configuration Debug 2>&1
[ $? -ne 0 ] && echo "🚫 BLOCKED: Build failed" && exit 1
echo "✅ Build passed"
```

### Check 3: Unit Tests — .NET SDK only
```bash
dotnet test \
  --filter "Category!=Integration&Category!=E2E&Category!=Performance" \
  --no-build --logger "console;verbosity=minimal"
[ $? -ne 0 ] && echo "🚫 BLOCKED: Unit tests failed" && exit 1
echo "✅ Unit tests passed"
```

### Check 4: CVE Scan — built into .NET SDK (no external tool)
```bash
# Only runs if a .csproj changed — skip otherwise
CSPROJ_CHANGED=$(git diff --cached --name-only | grep "\.csproj$")
if [ -n "$CSPROJ_CHANGED" ]; then
  OUTPUT=$(dotnet list package --vulnerable --include-transitive 2>&1)
  if echo "$OUTPUT" | grep -qiE "\b(High|Critical)\b"; then
    echo "🚨 BLOCKED: HIGH/CRITICAL vulnerable packages found"
    echo "$OUTPUT"
    exit 1
  fi
  echo "✅ CVE scan passed"
fi
```

### Check 5: Framework dependency check — pure grep
```bash
STAGED_CS=$(git diff --cached --name-only | grep "\.cs$")
if [ -n "$STAGED_CS" ]; then
  VIOLATIONS=$(echo "$STAGED_CS" | \
    xargs grep -l "using System\.Web" 2>/dev/null | \
    grep -v "Legacy\|Framework\|Compat")
  if [ -n "$VIOLATIONS" ]; then
    echo "🚫 BLOCKED: System.Web in migrated files:"
    echo "$VIOLATIONS"
    exit 1
  fi
fi
echo "✅ Framework dependency check passed"
```

### Check 6: Org static analysis — Roslyn analyzers from Artifactory
```bash
# Roslyn analyzers run automatically as part of dotnet build (Check 2 above).
# If org analyzer package is referenced in .csproj (sourced from Artifactory feed),
# violations appear as build errors/warnings — already caught in Check 2.
# No separate tool invocation needed.
echo "✅ Org static analysis covered by build step"
```

### Check 7: Update CODEBASE-MAP.md status
```bash
# Any migrated .cs files in this commit → mark as 🔄 WIP in map
# Agents update to ✅ DONE after tests + security pass
STAGED_MIGRATED=$(git diff --cached --name-only | grep "src/.*\.cs$")
if [ -n "$STAGED_MIGRATED" ]; then
  echo "📝 Remember to update memory/CODEBASE-MAP.md with these files:"
  echo "$STAGED_MIGRATED"
fi
```

## Bypass (emergency only — creates automatic follow-up ticket)
```bash
git commit --no-verify -m "EMERGENCY: [ticket #] [reason]"
# Must be resolved within 48h — creates tech-debt tracking issue automatically
```
