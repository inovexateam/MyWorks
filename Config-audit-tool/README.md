# Config Audit Tool

A desktop app that finds dead config, classifies keys as infra vs
app-level, and flags environment drift across your OCP/Helm repo setup
(code repo, component-cd repo, app-cd repo) — single component or
whole app at once.

## Setup

```
pip install -r requirements.txt --break-system-packages   # if needed on your machine
python3 main.py
```

Or double-click `run.bat` (Windows) / run `./run.sh` (Mac/Linux). A
Tkinter window opens — no browser, no server, no port.

Requires: Python 3.10+, `tkinter` (bundled with most Python installs;
on Linux you may need `sudo apt install python3-tk`).

## How it works — 3 tabs

### ① Connect
Paste your GitHub PAT into the masked field and click **Connect**.
- The token is held **only in memory** for the life of the app — never
  written to disk. Close the app, it's gone.
- Your **org** and **username** are remembered in a local `.config.json`
  next to `main.py` (gitignore this) so you don't retype them daily —
  only the token itself is never saved.
- Connect validates the token against GitHub immediately, so you know
  it's good before you waste time filling in repo URLs.
- Required scope: `repo` (read-only is enough — the tool never writes
  to GitHub).

### ② Single Component
Paste 3 URLs — code repo, component-cd repo, app-cd repo — and click
**Run Audit**. Use this when you're checking one service.

### ③ App-Wide
Use this when you want every component under one app checked
together, and to see which app-cd keys are shared/dead **across the
whole app**, not just one service.

1. Enter your **app name** and click **Discover**. The tool searches
   your GitHub org for repos matching `{appname}-*-cd` (or
   `app-{appname}-*-cd`) and lists them with checkboxes — uncheck any
   you don't want included.
2. For repos the naming search doesn't catch, use **Manual
   Additions**: paste the code URL + component-cd URL pair and click
   **Add**.
3. Fill in the **App-CD repo URL** (shared base config) and your
   **primary component's** code + component-cd URLs.
4. Click **Run App-Wide Audit**. Every discovered + manually-added
   component is scanned against the same app-cd base, and results are
   tagged by component so you can see overlap and per-component
   differences in one place.

## What happens during a scan

1. Fetches file trees for all repos involved.
2. Detects environment-specific `values.yaml` files — folder
   convention (`env/dev/values.yaml`, `dev/values.yaml`) or filename
   convention (`values-dev.yaml`, `values.dev.yaml`). Recognized env
   names: dev, qa, stage, staging, uat, prod, production, perf, sit.
   To add more, edit `ENV_FOLDER_PATTERNS` near the top of
   `engine/analyzer.py`.
3. Deep-merges app-cd values (base) with component-cd values
   (override) per environment — same semantics as Helm's own
   values-merge, whether or not your repos use a formal subchart
   dependency.
4. Scans Helm chart templates for `{{ .Values.x.y }}` references, and
   scans Java (`@Value`, `getenv`, `getProperty`) + C#
   (`IConfiguration` indexer, `GetEnvironmentVariable`, `GetValue<T>`,
   `GetSection`) source for config reads — checked against every file
   regardless of extension assumptions, so mixed-language repos are
   handled correctly.
5. Classifies every key and detects environment drift.

A progress message cycles through these steps while it runs, since
larger repos can take a little while (this is the GitHub API, not
something to bypass).

## Reading the results

Results open automatically in a separate window when a scan finishes.
You can also click **Open Results** any time after.

Every key carries two independent tags:

- **Classification** — `LIVE` (used in both Helm templates and code),
  `DEAD_CODE` (templated but never read by app code), `DEAD_HELM`
  (code references it but no template wires it through), `FULLY_DEAD`
  (neither).
- **Role** — `INFRA` (deployment-only: image tags, resource limits,
  probes — correctly *never* expected to be read by app code) vs
  `APP_CONFIG` (connection strings, feature flags, anything app logic
  should actually be reading). A `DEAD_CODE` **infra** key is normal
  and expected. A `DEAD_CODE` **app-config** key is the one worth
  investigating.

Use the filter tabs at the top of the results window to narrow by
classification, role, or jump to the **Env Drift** tab — a separate
view for keys that are live but inconsistently defined across
environments (different bug class from dead config, so it gets its
own tab).

Click any row to populate the **evidence panel** on the right: a
trace chain showing exactly where the key is **defined → templated →
read in code**, plus the full list of every matching reference, each
with file path and line number — so you can jump straight to source.

## Exporting

From the results window status bar, or the main window's **File**
menu / per-tab export buttons:

- **HTML** — single self-contained file, opens in any browser, fully
  interactive (filter, sort, click-to-expand evidence) with no server
  needed. Good for sharing with a teammate or attaching to a ticket.
- **Excel (.xlsx)** — 3 sheets: Findings (color-coded by
  classification), Env Drift, Summary.
- **CSV** — flat findings export for further processing elsewhere.

## Honest limitations (read before trusting blindly)

- **Name matching is heuristic.** The tool generates reasonable env
  var / config-key name variants from each YAML key (camelCase →
  ENV_VAR, dotted → colon, etc.) and matches code against those. It
  favors **false-"alive" over false-"dead"** — if unsure, it won't
  flag a key as dead. Treat `FULLY_DEAD` results as a triage list to
  review, not an auto-delete list.
- **App-wide discovery guesses the code repo URL** from the
  component-cd repo's name (stripping `-cd`). If your org doesn't
  follow that convention for the code repo specifically, add that
  component manually instead — discovery only needs to find the
  *component-cd* repo correctly; you confirm/correct the rest.
- **Large repos**: GitHub's tree API can truncate very large repos
  (10k+ files). Rare for typical service repos, but worth knowing if
  a scan looks incomplete.
- **Role classification (`INFRA` vs `APP_CONFIG`)** is naming-convention
  based, not actual chart semantics — a strong heuristic, not a
  guarantee. A few unusually-named keys may land in the "wrong"
  bucket. It's there to help you scan faster, not replace judgment.

## Project layout

```
main.py                    Tkinter app entry point — 3 tabs, scan orchestration
.config.json                Saved org/username (created on first connect; never the token)
engine/github_client.py    GitHub API session, in-memory token only
engine/yaml_merge.py       Line-number-aware YAML parsing + Helm-style deep merge
engine/usage_scanner.py    Helm/Java/C# reference matchers
engine/diff_engine.py      Env-to-env key drift detection
engine/discovery.py        App-wide component repo discovery by naming convention
engine/analyzer.py         Orchestrator: fetch -> merge -> classify -> trace
ui/styles.py                Tkinter design tokens (dark, code-forward palette)
ui/results_window.py        Findings tree + evidence panel (Toplevel window)
ui/export.py                HTML / Excel / CSV export functions
```