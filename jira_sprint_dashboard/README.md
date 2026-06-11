# JIRA Sprint Dashboard

A desktop tool for Scrum Masters / Product Owners to visualize sprint health,
burndown progress, and per-teammate daily completion ("churn") — with optional
automated email reports.

---

## Features

- **Sprint Burndown Chart**: Ideal vs actual remaining story points, with
  shaded "ahead/behind schedule" regions.
- **Daily Completed Points by Teammate**: Stacked bar chart showing how many
  story points each team member completed each day of the sprint.
- **Workload Breakdown**: Per-assignee Done / In Progress / To Do points,
  with % completion.
- **Sprint Health Indicator**: On Track / Slightly Behind / At Risk, computed
  by comparing actual vs ideal burndown as of today.
- **Scope Change Detection**: Flags issues whose first activity occurred after
  the sprint started (possible mid-sprint scope additions).
- **Dark "terminal" GUI** (Tkinter) for live use, plus a **light theme** for
  emailed reports.
- **Automated Email Reports**: Schedule daily/weekly emails with embedded
  charts and a summary table, via SMTP.
- **Flexible Auth**: Supply your JIRA Personal Access Token (PAT) either via
  the GUI (one-time, per session) or via environment variables / `.env` file
  for fully automated/scheduled runs.

### Ideas for future extensions
- Velocity trend chart across last N sprints (requires storing historical data).
- Cycle time / lead time per issue type.
- Slack/Teams webhook notifications instead of (or in addition to) email.
- "At risk" issue list (in-progress issues with no recent activity).
- Per-sprint PDF export (combine charts into a single PDF via the existing
  matplotlib figures + `matplotlib.backends.backend_pdf.PdfPages`).
- Multi-board / multi-team comparison view.

---

## Project Structure

```
jira_sprint_dashboard/
├── core/
│   ├── jira_client.py     # JIRA REST API client (Cloud + Server/DC PAT auth)
│   ├── analytics.py        # Burndown, churn, scope-change, summary calculations
│   ├── charts.py            # Matplotlib chart generation (dark + light themes)
│   ├── report.py            # Orchestrates fetch -> analyze -> chart -> summary
│   └── emailer.py           # SMTP email sending with embedded chart images
├── gui/
│   └── dashboard.py         # Tkinter desktop application
├── scheduler/
│   ├── scheduled_report.py  # CLI scheduler for automated email reports
│   └── jira-sprint-scheduler.service.example  # systemd unit example
├── reports/
│   ├── _cache/               # GUI-generated chart images (gitignored)
│   └── _scheduled/           # Scheduler-generated chart images (gitignored)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```ini
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your.email@company.com     # required for JIRA Cloud; leave blank for Server/DC
JIRA_PAT=your_personal_access_token
JIRA_BOARD_ID=123
JIRA_PROJECT_KEY=PROJ
JIRA_STORY_POINTS_FIELD=customfield_10016   # see "Finding your Story Points field" below

# Optional, for email reports
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.email@gmail.com
SMTP_PASS=your_app_password
EMAIL_FROM=your.email@gmail.com
EMAIL_TO=team@company.com,manager@company.com
```

> **Security note**: `.env` is for local/scheduled use only. Never commit it.
> Alternatively, set these as real OS environment variables and skip `.env`.

#### Authentication notes
- **JIRA Cloud**: Use your email + an API token (Account Settings → Security →
  API tokens) as `JIRA_PAT`.
- **JIRA Server / Data Center**: Leave `JIRA_EMAIL` blank; `JIRA_PAT` is sent
  as a Bearer token (Personal Access Token from your profile).

#### Finding your Board ID
Open your Scrum board in JIRA — the URL contains `rapidView=<ID>` or
`board/<ID>`.

#### Finding your Story Points field
Story Points is usually a custom field (`customfield_10016` is the common
Jira Cloud default, but it varies). To find yours:
```bash
curl -u youremail:YOUR_TOKEN https://yourcompany.atlassian.net/rest/api/2/field | grep -i "story point"
```

---

## Running the Dashboard (GUI)

```bash
python gui/dashboard.py
```

- If `.env` is populated, fields auto-fill and you can click **Connect & Load**.
- Otherwise, manually enter Base URL, Email, PAT, and Board ID at the top.
- Tabs: **Overview** (health + per-person table), **Burndown**, **Daily Churn**,
  **Workload**.
- Click **Send Email Now** to immediately send the current charts/summary to
  the configured recipients.

---

## Automated Email Reports (Scheduler)

### Run once immediately (test)
```bash
python scheduler/scheduled_report.py --now
```

### Run as a continuous scheduler (foreground)
```bash
python scheduler/scheduled_report.py --time 09:00 --days mon,tue,wed,thu,fri
```

### Run as a background service (Linux, systemd)
1. Copy `scheduler/jira-sprint-scheduler.service.example` to
   `/etc/systemd/system/jira-sprint-scheduler.service` and edit the paths.
2. ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now jira-sprint-scheduler
   ```

### Run on Windows
Use Task Scheduler to run:
```
python C:\path\to\scheduler\scheduled_report.py --now
```
on your desired daily trigger time.

---

## Notes & Limitations

- Burndown is computed from issue **resolution dates** — works well if your
  team transitions issues to "Done" status promptly.
- Scope-change detection is a heuristic based on changelog activity timing;
  for precise scope tracking, JIRA's sprint-field changelog could be added.
- Story Points field ID varies per JIRA instance — confirm yours as described
  above, or charts will show 0 points.
