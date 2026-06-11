"""
Cleanup generator — Layer 3.
The most valuable part of the tool: not just finding dead flags,
but generating the actual cleanup plan and PR scaffold.

For each graveyard flag it produces:
  1. A diff showing what code would be removed
  2. A PR description with context (ticket ref, age, affected files)
  3. A cleanup checklist for the developer
"""

import re
from pathlib import Path
from core.models import FlagDefinition, FlagState, FlagUsage, CleanupAction


# ── Code simplifier ───────────────────────────────────────────────────────────

def simplify_always_true_flag(content: str, flag_name: str) -> tuple[str, int]:
    """
    For an ALWAYS_ON flag:
      if (IsEnabled("flag")) { TRUE_BRANCH } else { FALSE_BRANCH }
      → TRUE_BRANCH (else removed)

    Returns (simplified_content, num_changes).
    Changes are shown as what gets removed from the file.
    """
    changes = 0
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        # Detect flag check lines
        if re.search(re.escape(flag_name), line, re.IGNORECASE) and re.search(r'\bif\b', line):
            # Simple single-line if: if (IsEnabled("flag")) {
            brace_depth = line.count('{') - line.count('}')
            result.append(f"// [CLEANUP] Flag '{flag_name}' always ON — removed check")
            i += 1
            # Skip until we find the else or end of if block, keeping the true branch
            in_true = True
            while i < len(lines) and brace_depth > 0:
                next_line = lines[i]
                brace_depth += next_line.count('{') - next_line.count('}')
                if brace_depth == 0 and re.search(r'\}\s*else\s*\{', next_line):
                    # Found else — skip false branch
                    in_true = False
                    i += 1
                    brace_depth = 1
                    while i < len(lines) and brace_depth > 0:
                        el = lines[i]
                        brace_depth += el.count('{') - el.count('}')
                        i += 1
                    changes += 1
                    break
                elif in_true and brace_depth > 0:
                    result.append(next_line)
                i += 1
            changes += 1
        else:
            result.append(line)
            i += 1

    return '\n'.join(result), changes


def simplify_always_false_flag(content: str, flag_name: str) -> tuple[str, int]:
    """
    For an ALWAYS_OFF flag:
      if (IsEnabled("flag")) { TRUE_BRANCH } else { FALSE_BRANCH }
      → FALSE_BRANCH (if branch removed) — or delete entire block if no else
    """
    changes = 0
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if re.search(re.escape(flag_name), line, re.IGNORECASE) and re.search(r'\bif\b', line):
            result.append(f"// [CLEANUP] Flag '{flag_name}' always OFF — removed true branch")
            brace_depth = line.count('{') - line.count('}')
            i += 1
            # Skip true branch entirely
            while i < len(lines) and brace_depth > 0:
                next_line = lines[i]
                brace_depth += next_line.count('{') - next_line.count('}')
                if brace_depth == 0 and re.search(r'\}\s*else\s*\{', next_line):
                    # Keep false branch
                    i += 1
                    brace_depth = 1
                    while i < len(lines) and brace_depth > 0:
                        el = lines[i]
                        brace_depth += el.count('{') - el.count('}')
                        if brace_depth > 0:
                            result.append(el)
                        i += 1
                    changes += 1
                    break
                i += 1
            changes += 1
            if not any('CLEANUP' in l for l in result[-3:]):
                # No else found — entire block was removed
                result.append(f"// [CLEANUP] Entire flag block removed (no else)")
        else:
            result.append(line)
            i += 1

    return '\n'.join(result), changes


# ── Diff generator ────────────────────────────────────────────────────────────

def generate_cleanup_diff(flag: FlagDefinition, repo_path: str) -> str:
    """
    Generate a simplified unified diff showing what would be removed.
    Not a real git diff — a human-readable preview of changes.
    """
    if not flag.usages:
        return f"# No code usages found — delete config entry in {flag.source_file}\n"

    diff_parts = [f"# Cleanup diff for flag: {flag.name}\n# State: {flag.state.value}\n\n"]

    # Group usages by file
    by_file: dict[str, list[FlagUsage]] = {}
    for u in flag.usages[:5]:  # limit to 5 files for readability
        by_file.setdefault(u.file, []).append(u)

    for filepath, usages in by_file.items():
        try:
            content = (Path(repo_path) / filepath).read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue

        diff_parts.append(f"--- a/{filepath}\n+++ b/{filepath}\n")

        for usage in usages:
            lines = content.split('\n')
            start = max(0, usage.line - 2)
            end   = min(len(lines), usage.line + 8)
            diff_parts.append(f"@@ -{start+1},{end-start} +{start+1},{end-start} @@\n")

            for lineno, line in enumerate(lines[start:end], start + 1):
                if lineno == usage.line:
                    diff_parts.append(f"-{line}\n")
                    if flag.state == FlagState.ALWAYS_ON:
                        diff_parts.append(f"  // flag '{flag.name}' removed (always enabled)\n")
                    else:
                        diff_parts.append(f"  // flag '{flag.name}' removed (always disabled)\n")
                else:
                    diff_parts.append(f" {line}\n")
        diff_parts.append("\n")

    return ''.join(diff_parts)


# ── PR description generator ──────────────────────────────────────────────────

def generate_pr_description(flag: FlagDefinition) -> str:
    """Generate a complete GitHub PR description for cleaning up one flag."""
    state_str = "permanently enabled" if flag.state == FlagState.ALWAYS_ON else "permanently disabled"
    action_str = (
        "inline the enabled code path and remove the flag check"
        if flag.state == FlagState.ALWAYS_ON
        else "remove the disabled code path and the flag check"
    )
    age_str = f"{flag.git_age_days} days" if flag.git_age_days else "unknown"
    files_list = '\n'.join(f"- `{f}`" for f in sorted(flag.affected_files())[:10])
    checklist = _build_checklist(flag)

    ticket_line = f"\nRelated ticket: {flag.ticket_ref}" if flag.ticket_ref else ""
    author_line = f"\nOriginally introduced by: @{flag.introduced_by}" if flag.introduced_by else ""

    return f"""## Cleanup: remove dead feature flag `{flag.name}`

This flag has been {state_str} for ~{age_str} and is safe to remove.
Action: {action_str}.{ticket_line}{author_line}

### Summary
| Field | Value |
|-------|-------|
| Flag name | `{flag.name}` |
| State | {flag.state.value} |
| Age | ~{age_str} |
| Usages | {flag.total_usages()} locations |
| Files affected | {len(flag.affected_files())} |
| Recoverable LOC | ~{flag.dead_lines()} |
| Complexity | {flag.cleanup_complexity} |

### Affected files
{files_list or "- Config file only"}

### Cleanup checklist
{checklist}

---
*Generated by Feature Flag Graveyard Hunter*
"""


def _build_checklist(flag: FlagDefinition) -> str:
    items = [
        f"- [ ] Remove flag definition from `{flag.source_file}`",
    ]
    for f in sorted(flag.affected_files())[:8]:
        if flag.state == FlagState.ALWAYS_ON:
            items.append(f"- [ ] In `{f}`: inline the enabled branch, remove the flag check and else block")
        else:
            items.append(f"- [ ] In `{f}`: remove the disabled branch and the flag check")
    items += [
        "- [ ] Remove flag from any feature flag management system (LaunchDarkly / Unleash / config)",
        "- [ ] Run full test suite",
        "- [ ] Search codebase for any remaining references: " + f"`{flag.name}`",
    ]
    return '\n'.join(items)


# ── Batch PR scaffolder ───────────────────────────────────────────────────────

def scaffold_all_prs(flags: list[FlagDefinition], repo_path: str, output_dir: str = "."):
    """
    For each simple/medium flag, write a cleanup plan file.
    Complex flags get a review template instead.
    """
    from pathlib import Path
    out = Path(output_dir) / "flag-cleanup-plans"
    out.mkdir(exist_ok=True)

    for flag in flags:
        safe_name = re.sub(r'[^\w\-]', '_', flag.name)
        plan_path = out / f"{safe_name}.md"
        pr_desc = generate_pr_description(flag)
        diff = generate_cleanup_diff(flag, repo_path)
        content = pr_desc + "\n\n### Diff preview\n\n```diff\n" + diff + "```\n"
        plan_path.write_text(content)

    print(f"Cleanup plans written to: {out}/")
    return str(out)
