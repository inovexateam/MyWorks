# Design Flaw Reviewer Agent — v3 (Final)

A multi-language, multi-pass design review agent for GitHub Copilot.
Produces real entity/dependency graphs, detects behavioral anti-patterns,
prioritizes findings by severity × blast-radius, verifies proposed fixes
build/lint cleanly, runs incrementally on PRs, and tracks accept/reject
feedback over time.

## What's in v3 vs v2

| Item | Status |
|---|---|
| #1 Graph format unification (C# vs cross-language) | **Not done** (by request) |
| #2 Incremental scanning | ✅ `run_review.py --since <ref>` |
| #3 Real-code testing | ✅ tested against C#, Java, Angular samples |
| #4 Call-graph / behavioral patterns (N+1, blocking async, leaks, etc.) | ✅ `pattern_detect.py` |
| #5 Fix verification (build/lint the proposed diff) | ✅ `verify_fix.py` |
| #6 Automatic CI triggering on PRs | ✅ `automated-design-review.yml` |
| #7 Java/Angular entity-level parity with C# | ✅ `gen_graph_java_ts.py` |
| #8 Prioritization by blast radius | ✅ scoring in `run_review.py` |

## Structure

```
.github/
  copilot-instructions.md
  chatmodes/
    design-review.chatmode.md           # quick single-file v1 mode
    design-review-agentic.chatmode.md    # v3 — use this for real reviews
  workflows/
    automated-design-review.yml          # runs on every PR, posts summary comment
tools/
  run_review.py                          # ORCHESTRATOR — run this
  dependency-graph/
    gen_graph.py                         # C# entity graph (controllers/services/DI/EF)
    gen_graph_java_ts.py                 # Java/Spring + Angular entity graph
    dep-graph.py                         # cross-language layering/cycle/coupling graph
    pattern_detect.py                    # N+1, blocking async, leaks, god methods
  verify-fix/
    verify_fix.py                        # applies a diff to a temp copy, runs build/lint
  feedback-tracker/
    feedback.py                          # log accept/reject decisions, see stats
analyzers/
  dotnet-setup.md / java-setup.md / angular-setup.md
```

## Setup

```bash
# 1. Copy .github/, tools/, analyzers/ into your repo root

# 2. Run a full scan once
python3 tools/run_review.py . --out review-summary.json

# 3. Open in VS Code (1.99+, Copilot Chat extension)
#    Select chat mode: "Design Flaw Reviewer — Agentic v3"
#    Ask: Review #file:review-summary.json — focus on the top 10 findings
```

## Usage patterns

**Full repo audit**
```bash
python3 tools/run_review.py . --out review-summary.json
```
Then in Copilot Chat (Agentic v3 mode): `#file:review-summary.json review top findings`

**PR / incremental review**
```bash
python3 tools/run_review.py . --out review-summary.json --since origin/main
```
This only re-scans changed files (faster) and is what `automated-design-review.yml`
runs automatically on every PR, posting a scored table as a PR comment.

**Verify a proposed fix builds**
```bash
python3 tools/verify-fix/verify_fix.py . --diff fix.patch --stack dotnet
# exit 0 = builds clean, 1 = diff didn't apply, 2 = build failed, 3 = toolchain unavailable
```

**Track feedback / tune false-positive rate**
```bash
python3 tools/feedback-tracker/feedback.py add --title "..." --location "src/Foo.cs:42" \
  --category "DIP violation" --decision rejected --reason "Intentional, see ADR-007"

python3 tools/feedback-tracker/feedback.py stats
```

## How scoring works

`run_review.py` combines four sources into `review-summary.json`:

- **Behavioral patterns** (`pattern_detect.py`): N+1 queries, `.Result`/`.Wait()`
  blocking, `async void`, empty catch blocks, undisposed `HttpClient`/`StreamReader`,
  RxJS subscriptions without cleanup, god methods (>60 lines, configurable)
- **Cross-layer violations / cycles / high-coupling modules** (`dep-graph.py`)
- **Entity graphs** (`gen_graph.py` for C#, `gen_graph_java_ts.py` for Java/Angular)
  — used to compute **fan-in** (how many other files depend on the flagged file)

Score = `severity_weight × (1 + min(fan_in, 50) / 10)`. A Critical issue in a
file with 50 dependents scores ~600; the same issue in an isolated file scores 100.
This is what makes the "Top findings" list reflect actual blast radius, not
just raw severity.

## What's still NOT solved (honest limits)

- **#1 remains open**: `codebase-graph.json` (C#) and `java-ts-graph.json` /
  `dep-graph.json` use different node-id schemes. `run_review.py` handles this
  by computing fan-in separately per graph rather than merging them into one
  graph — works for scoring, but there's no single unified cross-language graph.
- Regex-based parsing will still miss edge cases: partial classes split across
  files, deeply nested generics, minified/generated code, non-standard formatting.
- `verify_fix.py` requires the actual toolchain (`dotnet`/`mvn`/`npx tsc`) to be
  present in the environment running it — it reports `SKIPPED` (exit 3) if not,
  rather than a false pass.
- Fan-in for Java/Angular only counts `injects`/`inherits`/`implements`/`has_entity`
  edges within that single graph — cross-stack fan-in (e.g., an Angular service
  calling a Java endpoint) isn't tracked.
- CI workflow posts a table; it does not call any AI model itself (no Copilot
  API call wired in) — the explain/fix step is still a manual Copilot Chat step.

## Tested

All four graph/detection tools were run against synthetic C#, Java, and Angular
samples covering: layering violations, circular dependencies, high coupling,
N+1 queries, blocking async, async void, empty catch, undisposed resources,
RxJS leaks, DI injection edges, EF entities, Spring controllers/services/repos,
and Angular components/services/modules/routes — all produced correct output.
The orchestrator (`run_review.py`) was run in both full and incremental
(`--since`) modes successfully.
