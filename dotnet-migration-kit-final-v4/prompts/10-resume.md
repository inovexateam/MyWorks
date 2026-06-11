# Prompt: Resume Migration

## Context limit hit or starting a new session?

```
Read .github/memory/MAP.md and .github/memory/signals.json.
Show me:
  - Count of ✅ DONE, ⏳ QUEUE, 🚧 BLOCK files
  - Last 🔄 WIP or most recent ✅ DONE file
  - Next ⏳ QUEUE file to work on
  - Any active signals from signals.json not yet fully resolved

Then continue: migrate the next ⏳ QUEUE file using the correct prompt
from .github/prompts/ based on its file type.
```

## Team handoff (another dev picking up)

```
Read .github/memory/MAP.md and .github/memory/signals.json.
I am picking up this migration. Show me the current state:
  - Which projects are complete
  - Which project is in progress and which file is next
  - All 🚧 BLOCK items with reasons
  - ORDER line from MAP.md (dependency sequence)
Do not start migrating yet — summary only.
```

## Check if a specific file needs migration

```
Read .github/memory/MAP.md.
Check if #file:src/[Project]/[FileName].cs needs migration.
Hash check: git log -1 --format="%H" -- src/[Project]/[FileName].cs
If ✅ DONE + hash matches → tell me it's already done.
If ⏳ QUEUE or not in map → migrate it now using the correct prompt.
```

## Status report (no migration — summary only)

```
Read .github/memory/MAP.md.
Count: ✅ DONE, ⏳ QUEUE, 🚧 BLOCK, 🔄 WIP.
Run these and show results:
  dotnet build src-core/ --configuration Release --no-incremental 2>&1 | tail -3
  grep -c "TODO-MIGRATION" $(find src-core/ -name "*.cs") 2>/dev/null
  dotnet list src-core/ package --vulnerable 2>&1 | grep -c "vulnerable" || echo "0 CVEs"
Show as a 5-line summary.
```
