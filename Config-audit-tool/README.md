# Config Audit Tool

Finds dead config, classifies keys as infra vs app-level, and flags
environment drift across your three-repo OCP/Helm setup (code repo,
component-cd repo, app-cd repo).

## Setup

```
pip install -r requirements.txt --break-system-packages   # if needed on your machine
python3 app.py
```

Or just double-click `run.bat` (Windows) / run `./run.sh` (Mac/Linux).
Your browser opens automatically to `http://127.0.0.1:5057`.

## Daily token workflow

Your org's PAT expires every ~24h. This tool is built around that:

- Paste the token into the "GitHub session" box each time you open the
  tool. It is **never written to disk** — held only in the Python
  process's memory for that run. Closing the app/terminal clears it.
- Required scopes: `repo` (read access is enough — the tool never
  writes to GitHub).
- If the token expires mid-scan, the UI shows an inline "session
  expired, please re-enter" prompt instead of crashing — paste a
  fresh token and re-run the audit, no restart needed.
- A soft warning appears in the rail once the token is ~23h old, as a
  heads-up before it actually expires.

## What it expects from your repos

- **Env detection**: works with either folder convention
  (`env/dev/values.yaml`, `dev/values.yaml`) or filename convention
  (`values-dev.yaml`, `values.dev.yaml`). Recognized env names: dev,
  qa, stage, staging, uat, prod, production, perf, sit. If your repo
  uses different names, line 32 of `engine/analyzer.py`
  (`ENV_FOLDER_PATTERNS`) is the one place to extend that list.
- **app-cd / component-cd merge**: app-cd values are treated as the
  base, component-cd values override on key collision — this mirrors
  Helm's own values-merge semantics, regardless of whether your repos
  use a formal Helm subchart dependency or just follow the convention
  by hand.
- **Code matching**: scans Java (`@Value`, `getenv`, `getProperty`)
  and C# (`IConfiguration` indexer, `GetEnvironmentVariable`,
  `GetValue<T>`, `GetSection`) patterns against every source file —
  it does not trust file extensions alone, so mixed-language repos are
  handled.

## Reading the results

Every key gets two independent tags:

- **Classification**: `LIVE` (used in both Helm templates and code),
  `DEAD_CODE` (templated but never read by app code), `DEAD_HELM`
  (code references it but no template wires it through), `FULLY_DEAD`
  (neither).
- **Role**: `INFRA` (deployment-only config like image tags, resource
  limits, probes — correctly *never* expected to be read by app code)
  vs `APP_CONFIG` (connection strings, feature flags, anything your
  application logic should be reading). A `DEAD_CODE` infra key is
  normal. A `DEAD_CODE` app-config key is the one worth investigating.

Click any row to open the evidence drawer: a trace chain showing
exactly where the key is **defined → templated → read in code**, each
with file path and line number, so a reviewer can jump straight to
the source.

The **Env drift** tab is separate from dead-config — it shows keys
present in some environments but missing in others (a live, real key
that's just inconsistently defined), since that's a different bug
class from dead config and deserves its own view.

## Honest limitations (read before trusting blindly)

- **Name matching is heuristic.** The tool generates reasonable env
  var / config-key name variants from each YAML key (camelCase →
  ENV_VAR, dotted → colon, etc.) and matches code against those. It
  favors **false-"alive" over false-"dead"** — i.e. if unsure, it
  won't flag a key as dead. Always sanity-check `FULLY_DEAD` results
  before deleting anything; treat this as a triage list, not an
  auto-delete list.
- **Large repos**: GitHub's tree API can truncate very large repos
  (10k+ files). If a repo's tree is truncated, scope down by pointing
  at a more specific ref if needed — this is rare for typical service
  repos but worth knowing.
- **Role classification (`INFRA` vs `APP_CONFIG`)** is based on naming
  convention matching, not actual chart semantics. It's a strong
  heuristic, not a guarantee — a few unusually-named keys may land in
  the "wrong" bucket. The tags are there to help you scan faster, not
  to replace judgment.

## Project layout

```
app.py                   Flask routes, in-memory token handling
engine/github_client.py  GitHub API session (token never persisted)
engine/yaml_merge.py     Line-number-aware YAML parsing + Helm-style deep merge
engine/usage_scanner.py  Helm/Java/C# reference matchers
engine/diff_engine.py    Env-to-env key drift detection
engine/analyzer.py       Orchestrator: fetch -> merge -> classify -> trace
templates/index.html     Single-page UI
static/style.css         Design system (dark, code-forward palette)
static/app.js            Frontend logic, no framework
```
