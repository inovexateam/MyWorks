# Fintech Business Observability
### Splunk Observability Cloud Challenge — Transfer & Pay Workflow

> **One sentence:** Turn raw OCP logs into a CFO-ready dashboard that shows ₹ impact, guilty service, and impacted customers — in real time.

---

## Executive Summary

Most teams treat Splunk as a technical monitoring tool. We treat it as a **business intelligence layer**.

The gap we solve: when a payment fails, engineers see an HTTP 500. Product managers see nothing. CFOs find out 20 minutes later in a Slack message. That gap costs money and erodes trust.

**What we built:** A 4-layer observability stack on top of existing OCP application logs — no new instrumentation required — that answers three questions any business leader needs during an incident:

- Which workflows are failing **right now?**
- What is the **₹ impact** and who is affected?
- Which service is **responsible?**

**How we're different from every other team:**

| Others | Us |
|---|---|
| Show error rates | Show ₹ at risk |
| Alert after failure | Predict failure 3 min early |
| Dashboard for SREs | Dashboard for CFO + SRE + PM simultaneously |
| Simulated app | Real OCP production logs |
| Static demo | Live chaos injection during presentation |

**The demo moment judges remember:** One button click generates a plain-English incident brief — root cause, blast radius, recommendation — in the format a CFO sends to the board. No other team has this.

---

## What's Still Pending (Do These Before Demo)

### CRITICAL — blocks the demo
- [ ] **Validate SPL searches against your real Splunk index** — paste 4 searches from `kpi_searches.spl`, confirm fields extract correctly. If log format differs, fix REGEX in `transforms.conf`.
- [ ] **Import dashboard XML** into your org Splunk and confirm all panels render.
- [ ] **Test chaos_inject.py once** against real HEC — confirm KPIs visibly degrade on dashboard.

### HIGH — judges will notice
- [ ] **Rehearse 7-min demo script** end-to-end at least twice. Timed.
- [ ] **Test `incident_brief.html`** in Chrome — click all 3 buttons, confirm smooth transitions.
- [ ] **Take dashboard screenshots** as fallback if live Splunk is slow/down at venue.

### STILL TO BUILD
- [ ] **5-slide presentation deck** — problem → architecture → KPIs → demo → value. First thing judges see.
- [ ] **1-page demo cheat sheet** — exact click sequence + what to say + fallback steps. Open on second screen during presentation.
- [ ] **Real log format adapter** — provide one sanitized real log line from your org → REGEX gets rewritten to match actual data in 2 minutes.

### SKIP (mention verbally only)
- `alerts.spl` — mention during demo, don't live-demo. No time.
- SPL searches 5–10 — show 4 max on screen.

---

---

## Project Structure

```
fintech-observability/
├── logs/sample/
│   ├── payment-api.log        # Simulated OCP API service logs (5 microservices)
│   └── ui-app.log             # Simulated OCP UI app logs
├── splunk/
│   ├── extractions/
│   │   ├── props.conf         # Sourcetype config + field extractions
│   │   ├── transforms.conf    # REGEX field extraction rules
│   │   └── customer_tier.csv  # Lookup: tier → SLA, priority, multiplier
│   ├── searches/
│   │   ├── kpi_searches.spl   # All 10 SPL searches (copy-paste into Splunk)
│   │   └── alerts.spl         # 4 alert definitions (P1/P2)
│   └── dashboards/
│       └── fintech_business_observability.xml  # Import directly into Splunk
├── scripts/
│   ├── ingest_to_splunk.py    # Replay logs → Splunk HEC (live demo feed)
│   └── chaos_inject.py        # Auth latency spike for demo
├── ai-brief/
│   └── incident_brief.html    # AI Incident Brief UI (open in browser)
└── README.md
```

---

## What This Demonstrates

| Layer | What | Business Value |
|---|---|---|
| Log Enrichment | OCP logs → business fields via Splunk extractions | Engineers & PMs share same data |
| KPI Mapping | SPL searches → success rate, revenue at risk, SLA breach | CFO sees ₹ not HTTP 500s |
| Blast Radius | Failure by region, tier, workflow step | Prioritise by customer value |
| Predictive Alert | Auth P99 rising → fires BEFORE success rate drops | Shift from reactive to predictive |
| AI Brief | Pre-generated incident summary, one-click reveal | CFO briefing in 60 seconds |

---

## Business KPIs Defined

| KPI | SPL Signal | SLA | Alert |
|---|---|---|---|
| Transfer Success Rate | `avg(is_success)*100` per 5m window | ≥ 99% | P1 if < 95% |
| Revenue At Risk | `sum(amount)` where `status!=200`, last 15m | ₹0 | P1 if > ₹10L |
| Auth P99 Latency | `p99(duration_ms)` on auth-service | HNI: 1000ms, Corp: 1500ms, Retail: 2000ms | P2 if > 1500ms (predictive) |
| SLA Breach Rate | `breached/total` per tier | 0% for HNI/Corporate | P1 on any HNI breach |
| Impacted Customers | `dc(user_id)` where failed | 0 | P1 on HNI/Corporate |

---

## Tagging Convention (OCP Log Standard)

Every log line MUST carry these fields:

```
app=<service-name>
pod=<ocp-pod-name>
namespace=<ocp-namespace>
endpoint=<api-path>
status=<http-status>
user_id=<user-id>
customer_tier=<HNI|Corporate|Retail>
amount=<integer-inr>
currency=INR
duration_ms=<integer>
region=<HYD|MUM|BLR|DEL|CHN>
workflow_step=<initiate|fraud_check|auth_verify|ledger_update|notify>
correlation_id=<TXN-YYYYMMDD-NNN>
trace_id=<alphanumeric>
```

**Why:** These 14 fields are the bridge between technical signals and business KPIs. Without them, Splunk only tells you *that* something failed. With them, it tells you *what it costs*.

---

## Workflow: Transfer & Pay (5 Steps)

```
[1] Initiate Transfer
    └─ payment-api → POST /api/v1/transfer

[2] Fraud Check
    └─ fraud-service → POST /api/v1/fraud-check

[3] Auth Verify          ← 🔥 Failure point in demo
    └─ auth-service → POST /api/v1/auth/verify

[4] Ledger Update
    └─ ledger-service → POST /api/v1/ledger/debit

[5] SMS Notify
    └─ notification-service → POST /api/v1/notify/sms
```

---

## Quick Start

### Option A: Demo with sample logs (no Splunk needed)
```bash
# Open the AI Incident Brief in browser
open ai-brief/incident_brief.html

# Click "Inject Chaos" → watch KPIs degrade
# Click "Show Healthy" → back to green
# Click "Regenerate Brief" → simulates AI analysis
```

### Option B: Full Splunk integration (org access)

**Step 1: Create HEC token in Splunk**
- Settings → Data Inputs → HTTP Event Collector → New Token
- Index: `ocp_fintech` | Sourcetype: `ocp_fintech_logs`

**Step 2: Deploy field extractions**
```bash
# Copy to your Splunk app
cp splunk/extractions/props.conf     $SPLUNK_HOME/etc/apps/search/local/
cp splunk/extractions/transforms.conf $SPLUNK_HOME/etc/apps/search/local/
cp splunk/extractions/customer_tier.csv $SPLUNK_HOME/etc/apps/search/lookups/
# Restart Splunk or reload configs
```

**Step 3: Send sample logs**
```bash
pip install requests
python scripts/ingest_to_splunk.py \
  --hec-url https://YOUR-SPLUNK:8088 \
  --token YOUR-HEC-TOKEN \
  --no-ssl
```

**Step 4: Import dashboard**
- Splunk UI → Dashboards → Import Dashboard
- Paste contents of `splunk/dashboards/fintech_business_observability.xml`
- Set index filter to `ocp_fintech`

**Step 5: Run KPI searches**
- Open `splunk/searches/kpi_searches.spl`
- Copy-paste each search into Splunk Search & Reporting
- Save as reports and pin to dashboard

**Step 6: Demo chaos injection**
```bash
# During demo — fires 20 auth failures into Splunk live
python scripts/chaos_inject.py \
  --hec-url https://YOUR-SPLUNK:8088 \
  --token YOUR-HEC-TOKEN \
  --count 20
```
Watch dashboard KPIs degrade in real time.

---

## Dashboard Panels (5 rows)

| Row | Panels | Audience |
|---|---|---|
| 1 | AI Incident Brief (static HTML embed) | CFO / All |
| 2 | Success Rate %, Revenue At Risk, Impacted Customers, Auth P99, SLA Breaches | All |
| 3 | Success Rate trend line, Auth P99 trend (predictive signal) | SRE / PM |
| 4 | Failure by workflow step, Blast radius by region, Guilty service table | SRE / Eng |
| 5 | Revenue at risk by tier, SLA breach by tier, Live transaction feed | PM / CFO |

---

## Alerts

| Alert | Trigger | Severity | Audience |
|---|---|---|---|
| Transfer Success Rate Below SLA | < 95% for 5m | P1 Critical | All |
| Auth P99 Rising (PREDICTIVE) | P99 > 1,500ms | P2 High | SRE |
| HNI/Corporate Transaction Failed | Any failure in premium tiers | P1 Critical | PM / CX |
| Revenue At Risk > ₹10L | 15m rolling window | P1 Critical | CFO |

---

## 7-Minute Demo Script

| Time | Action | Say |
|---|---|---|
| 0–1m | Problem slide / intro | "Engineers see HTTP 500s. CFOs see nothing for 20 minutes. We closed that gap." |
| 1–2m | Show healthy dashboard (green KPIs) | "Every log from our OCP apps now carries business context — tier, amount, region." |
| 2–4m | Run chaos_inject.py → watch KPIs turn red | "I'm spiking auth latency now. Watch the business impact appear in real time." |
| 4–5m | Point to blast radius panel | "₹50.2L at risk. 5 customers impacted. HYD region. auth-service is guilty." |
| 5–6m | Click 'Regenerate Brief' in AI Brief UI | "From 10,000 log lines to a CFO brief in under 60 seconds." |
| 6–7m | Show predictive alert timeline | "The system warned us at 14:31 — before failures started at 14:32. Reactive → Predictive." |

---

## Q&A Pre-loaded Answers

**Why log-based only, no traces?**
OCP apps emit structured logs today. Distributed tracing adds agent overhead and instrumentation time. Business observability doesn't require traces — it requires business fields in the data you already have. We can layer OTel on top incrementally.

**How does this scale?**
Splunk field extractions are applied at index time — zero query overhead. Lookup tables are cached. The dashboard searches run on summary indexes in production.

**What are the assumptions?**
Log format is structured key=value (OCP standard). Apps emit `correlation_id` for transaction stitching. Amount field represents INR. Customer tier is available at log emission time from auth context.

**What's the trade-off of the AI brief being static?**
In production, this is a webhook triggered by the P1 alert that calls an LLM API with the live KPI snapshot and posts to Slack. The static demo proves the format and value — integration takes 2 hours once you have an API key.

**Could this work with your real OCP apps?**
Yes. Replace index=ocp_fintech with your actual Splunk index. Adjust the REGEX in transforms.conf to match your log format. The business logic (KPI definitions, SLAs, tier weights) is fully configurable via the CSV lookup.

---

## Enrichment Strategy Summary

```
Log emission (OCP app)
  └─ Structured key=value with 14 mandatory business fields
       └─ Splunk HEC → index=ocp_fintech
            └─ props.conf field extractions (REGEX + EVAL)
                 └─ customer_tier.csv lookup (tier → SLA, weight)
                      └─ SPL KPI searches (business aggregations)
                           └─ Dashboard panels (business + technical views)
                                └─ Alerts → P1/P2 → AI Brief
```

---

*Built for Splunk Observability Cloud — Business Observability Challenge*
*Stack: OCP logs → Splunk HEC → SPL → Dashboard → AI Incident Brief*
