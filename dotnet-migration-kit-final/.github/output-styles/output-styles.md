# Output Styles — Copilot Prompts

## Terse (default — code + 5 bullets)
Add to any prompt: "Respond in terse mode: migrated code only, 5-bullet summary, no prose."

## Verbose (onboarding / complex decisions)
Add to any prompt: "Respond in verbose mode: explain every change with before/after, reasoning, and impact."

## Review only (no changes)
Add to any prompt: "Review mode: read the file, produce numbered findings with severity. No code changes."

## Summary (status check)
```
Read .github/memory/CODEBASE-MAP.md. Show migration status:
count ✅ DONE, ⏳ QUEUE, 🚧 BLOCK. Estimate remaining hours.
One paragraph, no code.
```
