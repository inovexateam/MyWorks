# Copilot: Migration Mode

## Activate with this prompt
```
Read .github/copilot-instructions.md and .github/memory/CODEBASE-MAP.md.
Migrate the next ⏳ QUEUE file. Hash check first — skip if ✅ DONE.
Load only the agent needed for that file's type.
```

## Project-specific migration
```
Read .github/memory/CODEBASE-MAP.md and .github/memory/migration-state.json.
Migrate all ⏳ QUEUE files in [ProjectName].
Signal-driven: load only agents triggered by migration-state.json flags.
Update map after each file. Run dotnet build when project complete.
```

## File-specific migration
```
Read .github/copilot-instructions.md.
Migrate #file:src/[Project]/[FileName].cs
Load the agent appropriate for this file type.
Update CODEBASE-MAP.md when done.
```

## Session flow
1. Read map → find next ⏳ QUEUE file
2. Hash check → skip if ✅ DONE
3. Load one agent → migrate → update map
4. Repeat until project complete or context limit hit
5. On context limit: start new chat, use resume prompt

## Resume prompt
```
Read .github/memory/CODEBASE-MAP.md and .github/memory/migration-state.json.
Continue from the last ⏳ QUEUE or 🔄 WIP file.
```
