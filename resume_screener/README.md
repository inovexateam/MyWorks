# ⚡ Resume Screener Pro

**Offline • No API Keys • No Internet Required • Works on Any Machine**

A professional-grade resume screening tool with a **15-signal scoring engine** — built entirely with Python standard libraries + 2 pip packages. Reads PDF and Word files, ranks candidates, and exports results.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation — Step by Step](#installation)
4. [How to Run](#how-to-run)
5. [The 15 Scoring Signals](#the-15-scoring-signals)
6. [Using the App](#using-the-app)
7. [Job Profiles](#job-profiles)
8. [Adding a Custom Job Profile](#adding-a-custom-job-profile)
9. [Exporting Results](#exporting-results)
10. [Troubleshooting](#troubleshooting)
11. [Run on Any Machine — Cheat Sheet](#run-on-any-machine)

---

## What It Does

- Reads **PDF**, **DOCX**, **DOC**, and **TXT** resume files (batch — up to any number)
- Scores each resume across **15 professional signals** on a 0–100 scale
- Ranks candidates best-to-worst automatically
- Shows per-candidate breakdown: matched skills, missing skills, red flags, achievements, and more
- Lets you filter by minimum score, minimum experience, verdict, and red flags
- Exports ranked results to **JSON** or **CSV**
- Pre-loaded with 5 job profiles; create unlimited custom profiles in the UI

---

## Requirements

| What | Version | Notes |
|------|---------|-------|
| Python | 3.8 or higher | Pre-installed on most machines |
| tkinter | (built-in) | Comes with Python — no install needed |
| pypdf | any recent | For reading PDF files |
| python-docx | any recent | For reading DOCX/DOC files |

> **No internet needed after install. No API keys. No cloud services.**

---

## Installation

### Step 1 — Check your Python version

Open a terminal / command prompt and run:

```
python --version
```

or on some systems:

```
python3 --version
```

You need **Python 3.8+**. If not installed, download from your company's software portal or https://www.python.org/downloads/

---

### Step 2 — Install the two required libraries

#### Option A — Install from the internet (home / personal laptop)

```
pip install pypdf python-docx
```

#### Option B — Install from your company Artifactory (office laptop, no internet)

Ask your IT/DevOps team for the internal pip index URL, then run:

```
pip install pypdf python-docx --index-url https://YOUR-ARTIFACTORY-URL/pypi/simple/
```

Or if your company uses a trusted-host:

```
pip install pypdf python-docx --trusted-host YOUR-ARTIFACTORY-HOST --index-url https://YOUR-ARTIFACTORY-URL/pypi/simple/
```

#### Option C — Install from downloaded wheel files (fully air-gapped)

If your office has zero internet, ask IT to download these wheel files from PyPI and copy them to your machine:

```
pypdf-*.whl
python_docx-*.whl
```

Then install locally:

```
pip install pypdf-*.whl python_docx-*.whl
```

---

### Step 3 — Copy the script to your machine

Put `resume_screener_v2.py` anywhere you like — your Desktop, Documents, or a project folder. That's the only file you need.

---

## How to Run

### Windows

**Option 1 — Double-click**
Right-click `resume_screener_v2.py` → Open With → Python

**Option 2 — Command Prompt**
```
cd C:\Users\YourName\Desktop
python resume_screener_v2.py
```

### macOS

**Terminal:**
```bash
cd ~/Desktop
python3 resume_screener_v2.py
```

### Linux

**Terminal:**
```bash
cd ~/Desktop
python3 resume_screener_v2.py
```

> If you get a `tkinter not found` error on Linux, run:
> `sudo apt-get install python3-tk`  (Ubuntu/Debian)
> `sudo dnf install python3-tkinter`  (Fedora/RHEL)

---

## The 15 Scoring Signals

The engine scores each resume on a **100-point scale** across 15 signals, modelled after enterprise ATS systems (Workday, Greenhouse, LinkedIn Recruiter).

| # | Signal | Max Points | What It Checks |
|---|--------|-----------|----------------|
| 1 | **Must-Have Skill Coverage** | 20 | Core required skills (C#, .NET, SQL, etc.). Non-linear penalty — missing even 1 drops score significantly |
| 2 | **Nice-to-Have / Bonus Skills** | 10 | Supporting skills like Azure, Docker, REST API, Redis |
| 3 | **Skill Depth** | 8 | "5 years of C#" — explicit per-skill experience mentions |
| 4 | **Total Relevant Experience** | 10 | Parses "X years" text + date ranges (2018–2024); rewards ideal range |
| 5 | **Recency** | 5 | Active in last 3 years? Stale resumes are penalised |
| 6 | **Career Progression / Seniority** | 7 | Senior/Lead/Architect = high; Junior on senior role = penalty |
| 7a | **Education Level** | 4 | B.Tech / M.Tech / MCA / PhD |
| 7b | **Certifications** | 3 | Microsoft, Azure, AWS, CKAD, Databricks, Scrum, PMP |
| 8 | **Domain / Industry Relevance** | 5 | Fintech, healthcare, SaaS, e-commerce industry match |
| 9 | **Job Title Match** | 5 | Checks top lines of resume for matching role titles |
| 10 | **Quantified Achievements** | 5 | "Improved performance by 30%", "led team of 8", "reduced cost by 40%" |
| 11 | **Leadership & Mentorship** | 5 | Code reviews, mentoring, stakeholder engagement, cross-functional work |
| 12 | **Red Flags** (penalty) | −10 max | Job-hopping, employment gaps >8 months, multiple short tenures (<12 months) |
| 13 | **Keyword Density & Context** | 4 | Detects natural keyword usage vs. keyword stuffing |
| 14 | **Resume Completeness** | 4 | Email, phone, LinkedIn, GitHub, word count, quantified results |
| 15 | **Portfolio / Open Source** | 5 | GitHub links, Kaggle, OSS contributions, personal projects |

### Verdict Thresholds

| Score | Verdict |
|-------|---------|
| 80–100% | 🏆 Excellent Match |
| 65–79% | ✅ Strong Match |
| 50–64% | 🟡 Moderate Match |
| 35–49% | ⚠️ Partial Match |
| 0–34% | ❌ Poor Match / Missing Core Skills |

---

## Using the App

### Step 1 — Choose a Job Profile
Select from the dropdown on the left. The profile preview shows must-have skills, nice-to-have skills, and min/ideal experience.

### Step 2 — Add Resumes
- Click **📂 Add Files** to pick individual PDF/DOCX/TXT files
- Click **📁 Folder** to load all resumes from a folder at once
- Click 🗑 to clear the list and start fresh

### Step 3 — Click ▶ Analyse Resumes
The tool processes all files and populates the ranked table. The status bar at the bottom shows progress.

### Step 4 — Review Results
- The table shows all 13 columns: rank, name, file, score, verdict, experience, must-have matched, nice-to-have, red flags, achievements count, leadership count, quality indicators, and certifications
- **Click any column header** to sort by that column
- **Click any row** to see the full detail panel below — shows the complete 15-signal breakdown with a visual bar for each signal, matched/missing skills, red flags, resume quality, and a text preview

### Step 5 — Filter
Use the left panel sliders and dropdowns:
- **Min Score** — hide anyone below a threshold (e.g. 50%)
- **Min Experience** — filter out under-experienced candidates
- **Verdict** — show only Excellent, Strong, Moderate, etc.
- **Hide Red-Flagged** — checkbox to exclude job-hoppers and gap candidates

---

## Job Profiles

Five profiles are pre-loaded:

| Profile | Min/Ideal Exp | Focus |
|---------|-------------|-------|
| **Sr. .NET + SQL Engineer** | 5 / 8 yrs | C#, ASP.NET, SQL Server, Azure |
| **Jr. .NET Developer** | 0 / 2 yrs | C#, .NET, SQL, HTML/CSS |
| **Full Stack .NET + React** | 3 / 6 yrs | C#, .NET, React, JavaScript, SQL |
| **Data Engineer (SQL + Python)** | 3 / 6 yrs | Python, SQL, ETL, Spark, Airflow |
| **DevOps / Cloud Engineer** | 3 / 6 yrs | Docker, Kubernetes, CI/CD, Terraform |

---

## Adding a Custom Job Profile

Click **+ New** next to the profile dropdown. Fill in:

| Field | Example |
|-------|---------|
| Profile Name | Java Microservices Lead |
| Description | Senior Java backend with Spring Boot |
| Must-have skills | java, spring boot, kafka, postgresql |
| Nice-to-have skills | docker, kubernetes, aws, redis, git |
| Min / Ideal experience | 5, 8 |
| Target job titles | java developer, backend engineer, software engineer |

Click **Save Profile** — it appears in the dropdown immediately.

To make a profile permanent across sessions, add it to the `DEFAULT_PROFILES` dictionary in the Python script (see the existing profiles as a template).

---

## Exporting Results

| Button | Output | What's Included |
|--------|--------|----------------|
| **💾 Export JSON** | `.json` file | All fields including full score breakdown per signal |
| **📋 Export CSV** | `.csv` file | Flat table — rank, name, email, phone, score, verdict, skills, red flags, certs |

CSV can be opened directly in Excel. JSON is useful for sharing with other tools or your manager.

---

## Troubleshooting

### "pypdf not installed" warning
Run: `pip install pypdf`
PDFs will show `[pypdf not installed]` as text until this is done.

### "python-docx not installed" warning
Run: `pip install python-docx`
DOCX files will not be readable until this is done.

### `tkinter` not found (Linux only)
```bash
# Ubuntu / Debian
sudo apt-get install python3-tk

# Fedora / RHEL / CentOS
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

### The window is too small / cut off
Drag the window edges to resize. The minimum size is 1100×680 pixels.

### Score seems low even though candidate has the skills
- The resume may be scanned (image PDF) — text extraction won't work on image-only PDFs. Ask the candidate for a text-based PDF or DOCX.
- The skill may be written differently — e.g. "dot net" instead of ".NET". The engine uses regex patterns; you can add aliases in the profile's `must_have` dictionary.

### Python says "command not found"
Try `python3` instead of `python`, or locate your Python install path and run it directly:
- Windows: `C:\Python311\python.exe resume_screener_v2.py`
- macOS/Linux: `/usr/bin/python3 resume_screener_v2.py`

---

## Run on Any Machine — Cheat Sheet

```
┌─────────────────────────────────────────────────────────┐
│  QUICK START  (save this card)                          │
│                                                         │
│  1. Check Python:   python --version    (need 3.8+)     │
│                                                         │
│  2. Install:        pip install pypdf python-docx       │
│     (company pip):  pip install pypdf python-docx       │
│                     --index-url https://YOUR-ARTIFACTORY │
│                                                         │
│  3. Run:            python resume_screener_v2.py        │
│     (macOS/Linux):  python3 resume_screener_v2.py       │
│                                                         │
│  Files needed:      resume_screener_v2.py  (only this)  │
│                                                         │
│  Supported:  Windows 10/11  •  macOS 12+  •  Ubuntu     │
└─────────────────────────────────────────────────────────┘
```

---

## File Structure

```
your-folder/
├── resume_screener_v2.py    ← the only file you need
├── README.md                ← this file
└── resumes/                 ← put your candidate files here (optional)
    ├── candidate1.pdf
    ├── candidate2.docx
    └── ...
```

---

*Built for offline use. No telemetry. No cloud. All processing happens locally on your machine.*