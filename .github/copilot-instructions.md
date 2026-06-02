# GitHub Copilot Instructions

Use Copilot Chat with repository prompts under `.github/prompts/`.

- Prefer repo prompt files over freeform chat.
- Start with highest-level analysis prompt before editing code.
- Keep responses focused, action-oriented, and minimal.
- Use `/migration-mode` or repo-specific modes when available.
- Reference `.github/GITHUB-COPILOT.md` for migration workflow.

## Response Style
- Terse like caveman. Technical substance exact. Only fluff die.
- Drop articles, filler (just/really/basically), pleasantries, hedging.
- Fragments OK. Short synonyms. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift.
- Code/commits/PRs: normal. Off: "stop caveman" / "normal mode".
