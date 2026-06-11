# DevTools Suite

8 engineering intelligence tools for C#, Java & Angular codebases — as a single project.

## Install

```bash
git clone <this-repo>
cd devtools-suite
pip install -r requirements.txt      # installs pyyaml
```

## Run any tool

```bash
python devtools.py <tool> [options]
```

| Tool | Command | What it does |
|------|---------|-------------|
| blast-radius | `python devtools.py blast-radius --pr main` | Trace blast radius of changes |
| assumption | `python devtools.py assumption scan .` | Surface implicit code assumptions |
| arch-drift | `python devtools.py arch-drift --init` | Detect architectural drift |
| cross-pr | `python devtools.py cross-pr` | Find cross-PR conflicts |
| dead-code | `python devtools.py dead-code --confidence high` | Find unreachable code |
| flag-graveyard | `python devtools.py flag-graveyard --plans` | Hunt dead feature flags |
| knowledge | `python devtools.py knowledge --wiki` | Map knowledge & bus factor |
| docfill | `python devtools.py docfill --apply` | Auto-fill missing docstrings |

## Run all tools at once

```bash
python devtools.py all
```

## Tool-specific quick starts

### Blast Radius
```bash
python devtools.py blast-radius                  # scan uncommitted changes
python devtools.py blast-radius --pr main        # compare vs base branch
python devtools.py blast-radius --report         # open blast-radius.html
```

### Assumption Miner
```bash
python devtools.py assumption scan .             # full repo scan
python devtools.py assumption scan . --pr main   # PR contradiction check
python devtools.py assumption show --risk high   # high risk only
git add .assumptions.json && git commit -m "chore: assumption registry"
```

### Arch Drift
```bash
pip install pyyaml
python devtools.py arch-drift --init             # creates arch-rules.yml
# edit arch-rules.yml to define your layers, then:
python devtools.py arch-drift                    # scan
python devtools.py arch-drift --pr main          # PR check
python devtools.py arch-drift --timeline         # git history timeline
```

### Cross-PR Intelligence
```bash
export GITHUB_TOKEN=ghp_...
export GITHUB_REPO=owner/repo
python devtools.py cross-pr                      # scan all open PRs
python devtools.py cross-pr --pr 42             # focus on one PR
python devtools.py cross-pr --comment 42        # print PR comment
```

### Dead Code
```bash
python devtools.py dead-code                     # full scan
python devtools.py dead-code --confidence high   # safe-to-delete only
python devtools.py dead-code --no-graph          # skip BFS (faster)
python devtools.py dead-code --pr               # generate cleanup PR description
```

### Flag Graveyard
```bash
python devtools.py flag-graveyard               # scan
python devtools.py flag-graveyard --plans       # generate cleanup plans → flag-cleanup-plans/
python devtools.py flag-graveyard --show simple # easy cleanups first
```

### Knowledge Extractor
```bash
python devtools.py knowledge                    # full analysis
python devtools.py knowledge --wiki            # generate knowledge-wiki/ markdown pages
python devtools.py knowledge --gaps            # show critical bus-factor gaps
python devtools.py knowledge --pairings        # show pairing recommendations
python devtools.py knowledge --no-blame        # faster (skip git blame)
```

### Docstring Filler
```bash
python devtools.py docfill                         # dry run preview
python devtools.py docfill --apply                 # write to files (rule-based)
export OPENAI_API_KEY=sk-...
python devtools.py docfill --apply --min-confidence 0.7   # AI-powered
python devtools.py docfill --report                # HTML coverage report
```

## GitHub Actions — install all

```bash
mkdir -p .github/workflows
cp .github/workflows/*.yml  your-repo/.github/workflows/
```

Secrets needed:
- `GITHUB_TOKEN` — auto-available in Actions (cross-pr)
- `OPENAI_API_KEY` — optional, for AI docstring generation

## Project structure

```
devtools-suite/
├── devtools.py                    ← unified CLI entry point
├── requirements.txt
├── pyproject.toml
│
├── tools/
│   ├── blast_radius/              blast_radius.py + core/ + reporters/
│   ├── assumption_miner/          assume_miner.py + patterns/ + registry/
│   ├── arch_drift/                arch_drift.py + rules/ + scanner/
│   ├── cross_pr/                  cross_pr.py + engine/ + fetcher/
│   ├── dead_code/                 dead_code.py + graph/ + scanner/
│   ├── flag_graveyard/            flag_graveyard.py + cleanup/ + resolver/
│   ├── knowledge_extractor/       knowledge_extractor.py + miner/ + graph/ + wiki/
│   └── docstring_filler/          docfill.py + generator/ + scanner/
│
└── .github/
    └── workflows/                 one .yml per tool
```

## Supported languages

| | C# | Java | TypeScript/Angular |
|--|:--:|:--:|:--:|
| Blast Radius | ✓ | ✓ | ✓ |
| Assumption Miner | ✓ | ✓ | ✓ |
| Arch Drift | ✓ | ✓ | ✓ |
| Cross-PR Intel | ✓ | ✓ | ✓ |
| Dead Code | ✓ | ✓ | ✓ |
| Flag Graveyard | ✓ | ✓ | ✓ |
| Knowledge Extractor | any | any | any |
| Docstring Filler | ✓ (XML doc) | ✓ (Javadoc) | ✓ (JSDoc) |

## Python version

Python 3.12+ required. All tools use only stdlib (subprocess, re, pathlib, json)
except `pyyaml` for arch-drift and flag-graveyard.
