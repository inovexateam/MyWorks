"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         PROFESSIONAL RESUME SCREENER  v2.0  –  Offline, No API Keys        ║
║                                                                              ║
║  SCORING ENGINE  (15 signals, 100-point scale)                              ║
║  ─────────────────────────────────────────────                              ║
║  1.  Must-Have Skill Coverage          (20 pts)                             ║
║  2.  Nice-to-Have / Bonus Skills       (10 pts)                             ║
║  3.  Skill Depth  (years per skill)    (8  pts)                             ║
║  4.  Total Relevant Experience         (10 pts)                             ║
║  5.  Recency  (last 3 years activity)  (5  pts)                             ║
║  6.  Career Progression / Seniority    (7  pts)                             ║
║  7.  Education & Certifications        (7  pts)                             ║
║  8.  Domain / Industry Relevance       (5  pts)                             ║
║  9.  Job Title Match                   (5  pts)                             ║
║  10. Achievements & Impact             (5  pts)                             ║
║  11. Leadership & Team Signals         (5  pts)                             ║
║  12. Red Flags  (gaps, job-hop)       (-penalty)                            ║
║  13. Keyword Density & Context         (4  pts)                             ║
║  14. Resume Quality & Completeness     (4  pts)                             ║
║  15. Bonus: Open-source / Portfolio    (5  pts)                             ║
║                                                                              ║
║  INSTALL:   pip install pypdf python-docx                                   ║
║  RUN:       python resume_screener_v2.py                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os, re, json, math, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ─── optional imports ────────────────────────────────────────────────────────
try:
    from pypdf import PdfReader;  HAS_PYPDF = True
except ImportError:
    try:    from PyPDF2 import PdfReader;  HAS_PYPDF = True
    except: HAS_PYPDF = False

try:
    from docx import Document as DocxDocument;  HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

NOW_YEAR = datetime.now().year


# ═══════════════════════════════════════════════════════════════════════════════
#  JOB PROFILES  –  fully extensible dictionary
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_PROFILES = {

  "Sr. .NET + SQL Engineer": {
    "description": "Senior backend engineer with .NET & SQL Server expertise",
    "min_exp_years": 5,
    "ideal_exp_years": 8,

    # ── Signal 1: Must-Have (deal-breakers) ──────────────────────────────
    "must_have": {
      r"\bc#\b":             "C#",
      r"\b\.net\b":          ".NET",
      r"\basp\.net\b":       "ASP.NET",
      r"\bsql\s*server\b|\bms\s*sql\b": "SQL Server",
      r"\bsql\b":            "SQL",
    },

    # ── Signal 2: Nice-to-Have / Bonus skills ────────────────────────────
    "nice_to_have": {
      r"\bmicroservices?\b":            "Microservices",
      r"\brest\s*api\b|\brestful\b":    "REST API",
      r"\bazure\b":                      "Azure",
      r"\baws\b":                        "AWS",
      r"\bdocker\b":                     "Docker",
      r"\bkubernetes\b|\bk8s\b":        "Kubernetes",
      r"\bentity\s*framework\b|\bef\s*core\b": "EF Core",
      r"\blinq\b":                       "LINQ",
      r"\bredis\b":                      "Redis",
      r"\brabbitmq\b":                   "RabbitMQ",
      r"\bkafka\b":                      "Kafka",
      r"\bgit\b|\bgithub\b|\bgitlab\b":  "Git",
      r"\bci[/\s]cd\b|\bdevops\b":       "CI/CD",
      r"\bnunit\b|\bxunit\b|\bmstest\b|\bunit\s*test": "Unit Testing",
      r"\bsignalr\b":                    "SignalR",
      r"\bwpf\b|\bwinforms\b|\blazor\b": "Desktop/Blazor",
      r"\bgraphql\b":                    "GraphQL",
      r"\bnginx\b|\biis\b":              "Web Server",
    },

    # ── Signal 3: Skill-depth clues (years associated with skill) ────────
    "skill_depth_markers": [
      r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience\s+(?:in|with))?\s*\.?net\b",
      r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience\s+(?:in|with))?\s*c#",
      r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience\s+(?:in|with))?\s*sql",
    ],

    # ── Signal 6: Seniority / Career Progression ─────────────────────────
    "seniority_titles": {
      r"\bsenior\b|\bsr\.?\b":           3,
      r"\blead\b|\btech\s*lead\b":       4,
      r"\barchitect\b":                  5,
      r"\bprincipal\b|\bstaff\b":        5,
      r"\bmanager\b|\bhead\b":           4,
      r"\bjunior\b|\bjr\.?\b|\bfresher\b": -2,
    },

    # ── Signal 7: Education & Certs ──────────────────────────────────────
    "education": {
      r"\bb\.?tech\b|\bb\.?e\b|\bbachelor": 3,
      r"\bm\.?tech\b|\bm\.?e\b|\bmaster":   4,
      r"\bphd\b|\bdoctorate\b":              5,
      r"\bmca\b|\bbca\b|\bbsc\s*(?:cs|it)": 2,
    },
    "certifications": {
      r"\bmicrosoft\s*certified\b|\bmcp\b|\bmcsa\b|\bmcsd\b": 4,
      r"\bazure\s*(?:developer|architect|administrator)":       4,
      r"\baws\s*(?:developer|architect|sysops)":                4,
      r"\bscrum\b|\bpsm\b|\bcsm\b":                             2,
      r"\bpmp\b":                                                2,
    },

    # ── Signal 8: Domain Relevance ────────────────────────────────────────
    "domain_keywords": {
      r"\bfintech\b|\bbanking\b|\bfinance\b|\bpayment":          3,
      r"\bhealthcare\b|\bhealth\s*it\b|\behr\b":                  2,
      r"\be[\-\s]?commerce\b|\bretail\b|\bsupply\s*chain\b":      2,
      r"\binsurance\b|\binsuretech\b":                             2,
      r"\benterprise\b|\bsaas\b|\bproduct\b":                     2,
    },

    # ── Signal 9: Job Title Match ─────────────────────────────────────────
    "target_titles": [
      r"\.net\s*developer", r"c#\s*developer", r"software\s*engineer",
      r"backend\s*developer", r"full\s*stack", r"application\s*developer",
      r"senior\s*developer", r"lead\s*developer",
    ],

    # ── Signal 10: Achievements & Impact ──────────────────────────────────
    "achievement_patterns": [
      r"improved\s+(?:performance|speed|throughput)\s+by\s+\d+",
      r"reduced\s+(?:latency|time|cost|bug|error)\s+by\s+\d+",
      r"led\s+(?:a\s+)?team\s+of\s+\d+",
      r"delivered\s+\d+\s+(?:projects?|features?|sprints?)",
      r"increased\s+(?:revenue|sales|users?)\s+by\s+\d+",
      r"migrated\s+(?:to\s+)?\w+",
      r"architected\s+|designed\s+(?:and\s+)?(?:built|developed|implemented)",
      r"mentored\s+|coached\s+",
      r"\d+[km+]?\s*(?:users?|customers?|transactions?)",
    ],

    # ── Signal 11: Leadership ──────────────────────────────────────────────
    "leadership_patterns": [
      r"\bmentored?\b", r"\bcoached?\b", r"\bmanaged?\s+(?:a\s+)?team\b",
      r"\bteam\s+lead\b", r"\btechnical\s+lead\b", r"\bonboard(?:ing|ed)?\b",
      r"\bcross[- ]functional\b", r"\bstakeholder\b", r"\bpresented?\s+to\b",
      r"\barchitectur(?:e|al|ed)\b", r"\breviewed?\s+code\b|\bcode\s+review\b",
      r"\bproject\s+(?:manager|owner|lead)\b",
    ],

    # ── Signal 12: Red Flags ───────────────────────────────────────────────
    "red_flags": {
      "short_tenures": True,       # jobs < 12 months = flag
      "long_gap_months": 8,        # gap > 8 months = flag
      "max_jobs_5yr": 4,           # > 4 jobs in 5 years = job-hopper flag
    },

    # ── Signal 14: Resume Quality Markers ────────────────────────────────
    "quality_markers": {
      "has_email": 1, "has_phone": 1, "has_linkedin": 1,
      "has_github": 1, "has_quantified_results": 2,
      "min_word_count": 300,
    },

    # ── Signal 15: Portfolio / Open Source ───────────────────────────────
    "portfolio_patterns": [
      r"\bgithub\.com/\w+", r"\bbitbucket\b", r"\bgitlab\b",
      r"\bstackoverflow\b|\bstack\s*overflow\b",
      r"\bnuget\b|\bopen[\s-]source\b|\bcontributed?\b",
      r"\bportfolio\b", r"\bpersonal\s*project\b",
    ],

    # ── Score weights (must sum to 100 + penalty budget) ─────────────────
    "weights": {
      "must_have":        20,
      "nice_to_have":     10,
      "skill_depth":       8,
      "experience":       10,
      "recency":           5,
      "seniority":         7,
      "education":         4,
      "certifications":    3,
      "domain":            5,
      "title_match":       5,
      "achievements":      5,
      "leadership":        5,
      "keyword_density":   4,
      "resume_quality":    4,
      "portfolio":         5,
    },
    "red_flag_penalty": 10,   # max points deducted
  },

  # ─────────────────────────────────────────────────────────────────────────
  "Jr. .NET Developer": {
    "description": "Entry/mid-level .NET developer, 0–3 years",
    "min_exp_years": 0,
    "ideal_exp_years": 2,
    "must_have": {
      r"\bc#\b": "C#", r"\b\.net\b": ".NET", r"\bsql\b": "SQL",
    },
    "nice_to_have": {
      r"\basp\.net\b":"ASP.NET", r"\brest\s*api\b":"REST API",
      r"\bgit\b":"Git", r"\bjquery\b":"jQuery",
      r"\bhtml\b":"HTML", r"\bcss\b":"CSS", r"\bjavascript\b":"JS",
      r"\blinq\b":"LINQ", r"\bentity\s*framework\b":"EF",
    },
    "skill_depth_markers": [
      r"(\d+)\+?\s*years?\s+(?:of\s+)?\w*\.?net\b",
    ],
    "seniority_titles": {
      r"\bjunior\b|\bjr\.?\b|\bfresher\b|\bgraduate\b": 3,
      r"\bsenior\b|\bsr\.?\b": -1,
    },
    "education": {
      r"\bb\.?tech\b|\bb\.?e\b|\bbachelor": 4,
      r"\bmca\b|\bbca\b|\bbsc": 3,
    },
    "certifications": {
      r"\bmicrosoft\s*certified\b|\bmcsd\b": 3,
      r"\bazure\s*fundamentals\b": 2,
    },
    "domain_keywords": {
      r"\bweb\s*(?:application|development)\b": 2,
      r"\benterprise\b|\bsaas\b": 1,
    },
    "target_titles": [
      r"\.net\s*developer", r"c#\s*developer", r"software\s*developer",
      r"junior\s*developer", r"associate\s*developer",
    ],
    "achievement_patterns": [
      r"completed\s+(?:project|internship|training)",
      r"developed\s+(?:a\s+)?\w+\s+(?:application|module|feature)",
    ],
    "leadership_patterns": [r"\bteam\s*player\b", r"\bcollaborated?\b"],
    "red_flags": {"short_tenures": False, "long_gap_months": 18, "max_jobs_5yr": 6},
    "quality_markers": {"has_email":1,"has_phone":1,"min_word_count":200},
    "portfolio_patterns": [r"\bgithub\.com/\w+", r"\bpersonal\s*project\b", r"\binternship\b"],
    "weights": {
      "must_have":30,"nice_to_have":15,"skill_depth":5,"experience":10,
      "recency":5,"seniority":5,"education":10,"certifications":5,
      "domain":2,"title_match":4,"achievements":3,"leadership":2,
      "keyword_density":2,"resume_quality":2,"portfolio":4,
    },
    "red_flag_penalty": 5,
  },

  # ─────────────────────────────────────────────────────────────────────────
  "Full Stack .NET + React": {
    "description": "Full-stack with .NET backend and React frontend",
    "min_exp_years": 3,
    "ideal_exp_years": 6,
    "must_have": {
      r"\bc#\b":"C#", r"\b\.net\b":".NET", r"\breact\.?js?\b|\breact\b":"React",
      r"\bjavascript\b|\bjs\b":"JavaScript", r"\bsql\b":"SQL",
    },
    "nice_to_have": {
      r"\btypescript\b":"TypeScript", r"\basp\.net\b":"ASP.NET",
      r"\brest\s*api\b":"REST API", r"\bnode\.?js\b":"Node.js",
      r"\bhtml\b|\bcss\b":"HTML/CSS", r"\bazure\b":"Azure",
      r"\bdocker\b":"Docker", r"\bgit\b":"Git",
      r"\bredux\b|\bzustand\b":"State Mgmt",
      r"\bwebpack\b|\bvite\b":"Bundler",
      r"\bjest\b|\bcypress\b":"Testing",
    },
    "skill_depth_markers": [
      r"(\d+)\+?\s*years?\s+\w*\.?net\b",
      r"(\d+)\+?\s*years?\s+\w*react\b",
    ],
    "seniority_titles": {
      r"\bsenior\b|\bsr\.?\b":3, r"\blead\b":4, r"\barchitect\b":5, r"\bjunior\b":-1,
    },
    "education": {
      r"\bb\.?tech\b|\bbachelor":3, r"\bm\.?tech\b|\bmaster":4,
    },
    "certifications": {
      r"\bazure\b":3, r"\baws\b":3, r"\breact\s*certified\b":3,
    },
    "domain_keywords": {
      r"\bsaas\b|\bproduct\b":2, r"\be[\-\s]?commerce\b":2, r"\bstartup\b":1,
    },
    "target_titles": [
      r"full\s*stack", r"\.net\s*developer", r"react\s*developer",
      r"frontend\s*developer", r"software\s*engineer",
    ],
    "achievement_patterns": [
      r"improved\s+\w+\s+by\s+\d+", r"reduced\s+\w+\s+by\s+\d+",
      r"built\s+(?:a\s+)?\w+\s+(?:application|platform|dashboard)",
    ],
    "leadership_patterns": [
      r"\bmentored?\b", r"\bcode\s+review\b", r"\bcross[- ]functional\b",
    ],
    "red_flags": {"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
    "quality_markers": {"has_email":1,"has_phone":1,"has_github":1,"min_word_count":300},
    "portfolio_patterns": [
      r"\bgithub\.com/\w+", r"\bportfolio\b", r"\bopen[\s-]source\b",
    ],
    "weights": {
      "must_have":22,"nice_to_have":10,"skill_depth":7,"experience":10,
      "recency":5,"seniority":6,"education":4,"certifications":3,
      "domain":4,"title_match":5,"achievements":5,"leadership":4,
      "keyword_density":3,"resume_quality":3,"portfolio":5,
    },
    "red_flag_penalty": 8,
  },

  # ─────────────────────────────────────────────────────────────────────────
  "Data Engineer (SQL + Python)": {
    "description": "Data pipeline / ETL engineer with Python and SQL",
    "min_exp_years": 3,
    "ideal_exp_years": 6,
    "must_have": {
      r"\bpython\b":"Python", r"\bsql\b":"SQL",
      r"\betl\b|\bdata\s*pipeline\b|\bingestion\b":"ETL/Pipeline",
    },
    "nice_to_have": {
      r"\bspark\b|\bpyspark\b":"Spark", r"\bairflow\b":"Airflow",
      r"\bsnowflake\b":"Snowflake", r"\bdatabricks\b":"Databricks",
      r"\bpowerbi\b|\bpower\s*bi\b|\btableau\b":"BI Tool",
      r"\bhadoop\b|\bhive\b":"Hadoop/Hive",
      r"\bazure\s*data\b|\badf\b":"Azure Data",
      r"\baws\s*glue\b|\bs3\b|\bredshift\b":"AWS Data",
      r"\bkafka\b|\bkinesis\b":"Streaming",
      r"\bdbt\b":"dbt", r"\bpandas\b|\bnumpy\b":"Pandas/NumPy",
    },
    "skill_depth_markers": [
      r"(\d+)\+?\s*years?\s+\w*python\b",
      r"(\d+)\+?\s*years?\s+\w*sql\b",
    ],
    "seniority_titles": {
      r"\bsenior\b|\bsr\.?\b":3, r"\blead\b":4,
      r"\barchitect\b|\bprincipal\b":5, r"\bjunior\b":-1,
    },
    "education": {
      r"\bb\.?tech\b|\bbachelor":3, r"\bm\.?tech\b|\bmaster":4,
      r"\bstatistics\b|\bmathematics\b|\bdata\s*science\b":4,
    },
    "certifications": {
      r"\bazure\s*data\b|\bdp[- ]?\d+":4,
      r"\baws\s*(?:data|analytics)":4,
      r"\bgoogle\s*(?:cloud|data)":3,
      r"\bdatabricks\s*certified":4,
    },
    "domain_keywords": {
      r"\bdata\s*warehouse\b|\bdwh\b":3,
      r"\bdata\s*lake\b|\bdelta\s*lake\b":3,
      r"\breal[\s-]time\b|\bstreaming\b":2,
      r"\bml\b|\bmachine\s*learning\b|\bai\b":2,
    },
    "target_titles": [
      r"data\s*engineer", r"etl\s*developer", r"data\s*developer",
      r"analytics\s*engineer", r"platform\s*engineer",
    ],
    "achievement_patterns": [
      r"processed\s+\d+[tbmk]?\+?\s*(?:records?|rows?|events?)",
      r"reduced\s+\w+\s+by\s+\d+", r"built\s+(?:a\s+)?\w+\s+pipeline",
      r"migrated\s+to\s+\w+", r"improved\s+\w+\s+by\s+\d+",
    ],
    "leadership_patterns": [
      r"\bmentored?\b", r"\bcode\s+review\b", r"\barchitected\b",
    ],
    "red_flags": {"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
    "quality_markers": {"has_email":1,"has_phone":1,"min_word_count":300},
    "portfolio_patterns": [
      r"\bgithub\.com/\w+", r"\bkaggle\b", r"\bopen[\s-]source\b",
    ],
    "weights": {
      "must_have":25,"nice_to_have":12,"skill_depth":7,"experience":10,
      "recency":5,"seniority":6,"education":5,"certifications":4,
      "domain":5,"title_match":5,"achievements":4,"leadership":3,
      "keyword_density":2,"resume_quality":3,"portfolio":4,
    },
    "red_flag_penalty": 8,
  },

  # ─────────────────────────────────────────────────────────────────────────
  "DevOps / Cloud Engineer": {
    "description": "Cloud infrastructure, CI/CD, and DevOps engineer",
    "min_exp_years": 3,
    "ideal_exp_years": 6,
    "must_have": {
      r"\bdocker\b":"Docker", r"\bkubernetes\b|\bk8s\b":"Kubernetes",
      r"\bci[/\s]?cd\b":"CI/CD", r"\blinux\b|\bbash\b|\bshell\s*script":"Linux/Bash",
    },
    "nice_to_have": {
      r"\bterraform\b":"Terraform", r"\bansible\b":"Ansible",
      r"\bazure\s*devops\b|\bazure\b":"Azure", r"\baws\b":"AWS",
      r"\bgcp\b|\bgoogle\s*cloud\b":"GCP",
      r"\bjenkins\b|\bgithub\s*actions\b|\bgitlab\s*ci\b":"CI Tool",
      r"\bhelm\b":"Helm", r"\bargoCd\b|\bargocd\b":"ArgoCD",
      r"\bprometheus\b|\bgrafana\b":"Monitoring",
      r"\belastic\b|\bkibana\b|\belk\b":"Observability",
      r"\bpython\b|\bgo\b|\bpowershell\b":"Scripting",
    },
    "skill_depth_markers": [
      r"(\d+)\+?\s*years?\s+\w*(?:docker|kubernetes|devops|cloud)\b",
    ],
    "seniority_titles": {
      r"\bsenior\b|\bsr\.?\b":3, r"\blead\b":4, r"\barchitect\b|\bprincipal\b":5,
      r"\bjunior\b|\bjr\.?\b":-1,
    },
    "education": {
      r"\bb\.?tech\b|\bbachelor":3, r"\bm\.?tech\b|\bmaster":4,
    },
    "certifications": {
      r"\bckad\b|\bcka\b|\bckss\b":5,
      r"\bazure\s*(?:administrator|architect|devops)":4,
      r"\baws\s*(?:devops|sysops|architect)":4,
      r"\bgcp\s*(?:professional|associate)":3,
      r"\bterraform\s*(?:associate|professional)":3,
    },
    "domain_keywords": {
      r"\bcloud\s*native\b|\bcontaineriz":3,
      r"\bmicroservices?\b":2, r"\bsre\b|\bsite\s*reliability":3,
      r"\bhigh\s*availability\b|\bdisaster\s*recovery\b":2,
    },
    "target_titles": [
      r"devops\s*engineer", r"cloud\s*engineer", r"platform\s*engineer",
      r"infrastructure\s*engineer", r"sre\b", r"site\s*reliability",
    ],
    "achievement_patterns": [
      r"reduced\s+deploy\w*\s+time\s+by\s+\d+",
      r"uptime\s+of\s+\d+\.\d+\s*%",
      r"automated\s+\w+", r"migrated\s+to\s+\w+",
      r"managed\s+\d+\+?\s*(?:servers?|nodes?|clusters?)",
    ],
    "leadership_patterns": [
      r"\bmentored?\b", r"\bcode\s+review\b", r"\barchitected\b",
      r"\bcross[- ]functional\b",
    ],
    "red_flags": {"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
    "quality_markers": {"has_email":1,"has_phone":1,"has_github":1,"min_word_count":300},
    "portfolio_patterns": [
      r"\bgithub\.com/\w+", r"\bopen[\s-]source\b", r"\bportfolio\b",
    ],
    "weights": {
      "must_have":25,"nice_to_have":12,"skill_depth":7,"experience":8,
      "recency":6,"seniority":6,"education":3,"certifications":7,
      "domain":5,"title_match":4,"achievements":5,"leadership":3,
      "keyword_density":2,"resume_quality":3,"portfolio":4,
    },
    "red_flag_penalty": 8,
  },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  TEXT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════
def extract_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            if not HAS_PYPDF:
                return "[pypdf not installed]"
            r = PdfReader(path)
            return "\n".join(p.extract_text() or "" for p in r.pages)
        elif ext in (".docx", ".doc"):
            if not HAS_DOCX:
                return "[python-docx not installed]"
            doc = DocxDocument(path)
            return "\n".join(p.text for p in doc.paragraphs)
        elif ext == ".txt":
            return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"[Error reading file: {e}]"
    return f"[Unsupported: {ext}]"


# ═══════════════════════════════════════════════════════════════════════════════
#  SIGNAL EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════════

def sig_must_have(text, p):
    """Signal 1 – Must-Have Skill Coverage (hard requirements)"""
    matched, missing = [], []
    tl = text.lower()
    for pat, label in p["must_have"].items():
        (matched if re.search(pat, tl) else missing).append(label)
    ratio = len(matched) / max(len(p["must_have"]), 1)
    # Non-linear: missing even one must-have hurts a lot
    if len(missing) == 0:
        score = 1.0
    elif len(missing) == 1:
        score = 0.65
    elif len(missing) == 2:
        score = 0.25
    else:
        score = 0.0
    return score * p["weights"]["must_have"], matched, missing


def sig_nice_to_have(text, p):
    """Signal 2 – Nice-to-Have / Bonus Skills"""
    matched = []
    tl = text.lower()
    for pat, label in p["nice_to_have"].items():
        if re.search(pat, tl):
            matched.append(label)
    ratio = len(matched) / max(len(p["nice_to_have"]), 1)
    return min(ratio * 1.2, 1.0) * p["weights"]["nice_to_have"], matched


def sig_skill_depth(text, p):
    """Signal 3 – Skill Depth: years explicitly mentioned per skill"""
    tl = text.lower()
    total_depth = 0
    for pat in p.get("skill_depth_markers", []):
        for m in re.finditer(pat, tl):
            try:
                yrs = float(m.group(1))
                total_depth += min(yrs, 15)
            except: pass
    # 3+ years per skill marker = full credit
    ideal = len(p.get("skill_depth_markers", [])) * 4
    ratio = min(total_depth / max(ideal, 1), 1.0)
    return ratio * p["weights"]["skill_depth"], round(total_depth, 1)


def sig_experience(text, p):
    """Signal 4 – Total Relevant Experience"""
    tl = text.lower()
    years_found = []
    # Explicit "X years of experience"
    for pat in [
        r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:total\s+)?(?:professional\s+)?(?:experience|exp)",
        r"(\d+)\+?\s*yrs?\s+(?:of\s+)?experience",
        r"experience\s*[:\-–]?\s*(\d+)\+?\s*years?",
    ]:
        for m in re.finditer(pat, tl):
            try: years_found.append(float(m.group(1)))
            except: pass
    # Date-range spans
    date_spans = []
    for m in re.finditer(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|"
        r"july|august|september|october|november|december)?\s*(\d{4})\s*[-–to]+\s*"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|"
        r"july|august|september|october|november|december|\bpresent\b|\bcurrent\b|\btill\s*date\b)?",
        tl
    ):
        try:
            start = int(m.group(2))
            end_grp = m.group(0).lower()
            if re.search(r"present|current|till", end_grp):
                end = NOW_YEAR
            else:
                end_m = re.search(r"(\d{4})\s*$", m.group(0))
                end = int(end_m.group(1)) if end_m else NOW_YEAR
            span = end - start
            if 0 < span < 45:
                date_spans.append(span)
        except: pass
    # Use heuristic: max explicit OR max distinct date span
    candidates = years_found + date_spans
    years = max(candidates) if candidates else 0.0
    min_exp   = p["min_exp_years"]
    ideal_exp = p["ideal_exp_years"]
    if years <= 0:
        ratio = 0.0
    elif years < min_exp:
        ratio = 0.4 * (years / max(min_exp, 1))
    elif years <= ideal_exp:
        ratio = 0.4 + 0.6 * ((years - min_exp) / max(ideal_exp - min_exp, 1))
    else:
        ratio = min(1.0 + 0.05 * (years - ideal_exp), 1.15)  # slight bonus for over-qualified
    return min(ratio, 1.0) * p["weights"]["experience"], round(years, 1)


def sig_recency(text, p):
    """Signal 5 – Recency: has candidate been active in the last 3 years?"""
    tl = text.lower()
    recent_years = {str(y) for y in range(NOW_YEAR - 3, NOW_YEAR + 1)}
    # Check for recent year mentions near activity words
    activity_ctx = re.findall(
        r"(20\d{2})\s*[-–]?\s*(?:present|current|till|"
        r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})",
        tl
    )
    recent_activity = any(y in recent_years for y in activity_ctx)
    # Also check certifications, education, or project dates
    all_years = re.findall(r"\b(20\d{2})\b", tl)
    has_recent_year = any(y in recent_years for y in all_years)
    score = 1.0 if recent_activity else (0.6 if has_recent_year else 0.2)
    return score * p["weights"]["recency"], recent_activity


def sig_seniority(text, p):
    """Signal 6 – Career Progression / Seniority Level"""
    tl = text.lower()
    best_pts = 0
    matched_title = ""
    for pat, pts in p["seniority_titles"].items():
        if re.search(pat, tl):
            if pts > best_pts:
                best_pts = pts
                matched_title = pat
    max_pts = max((v for v in p["seniority_titles"].values() if v > 0), default=5)
    ratio = max(best_pts / max_pts, 0.0)
    return ratio * p["weights"]["seniority"], matched_title


def sig_education(text, p):
    """Signal 7a – Education Level"""
    tl = text.lower()
    best = 0
    matched = ""
    for pat, pts in p["education"].items():
        if re.search(pat, tl) and pts > best:
            best = pts
            matched = pat
    max_pts = max(p["education"].values(), default=5)
    return (best / max_pts) * p["weights"]["education"], matched


def sig_certifications(text, p):
    """Signal 7b – Certifications"""
    tl = text.lower()
    found = []
    total = 0
    for pat, pts in p["certifications"].items():
        if re.search(pat, tl):
            found.append(pat)
            total += pts
    max_pts = sum(p["certifications"].values()) if p["certifications"] else 1
    ratio = min(total / max(max_pts * 0.4, 1), 1.0)  # hitting 40% of certs = full
    return ratio * p["weights"]["certifications"], found


def sig_domain(text, p):
    """Signal 8 – Domain / Industry Relevance"""
    tl = text.lower()
    total = 0
    domains = []
    for pat, pts in p["domain_keywords"].items():
        if re.search(pat, tl):
            total += pts
            domains.append(pat)
    max_pts = sum(p["domain_keywords"].values()) if p["domain_keywords"] else 1
    ratio = min(total / max(max_pts * 0.5, 1), 1.0)
    return ratio * p["weights"]["domain"], domains


def sig_title_match(text, p):
    """Signal 9 – Job Title / Role Match"""
    tl = text.lower()
    lines = tl.splitlines()[:10]   # look in top of resume
    header = "\n".join(lines) + "\n" + tl[:600]
    matched = []
    for pat in p["target_titles"]:
        if re.search(pat, header):
            matched.append(pat)
    score = 1.0 if len(matched) >= 2 else (0.7 if len(matched) == 1 else 0.1)
    return score * p["weights"]["title_match"], matched


def sig_achievements(text, p):
    """Signal 10 – Quantified Achievements & Impact"""
    tl = text.lower()
    hits = []
    for pat in p["achievement_patterns"]:
        if re.search(pat, tl):
            hits.append(pat)
    ratio = min(len(hits) / max(len(p["achievement_patterns"]) * 0.4, 1), 1.0)
    return ratio * p["weights"]["achievements"], hits


def sig_leadership(text, p):
    """Signal 11 – Leadership, Mentorship, Cross-team Signals"""
    tl = text.lower()
    hits = []
    for pat in p["leadership_patterns"]:
        if re.search(pat, tl):
            hits.append(pat)
    ratio = min(len(hits) / max(len(p["leadership_patterns"]) * 0.35, 1), 1.0)
    return ratio * p["weights"]["leadership"], hits


def sig_red_flags(text, p):
    """Signal 12 – Red Flags: employment gaps, job-hopping"""
    rf = p.get("red_flags", {})
    penalty = 0
    flags = []
    tl = text.lower()
    # Extract date spans
    spans = []
    for m in re.finditer(
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+)?(\d{4})\s*[-–to]+\s*"
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+)?(present|\d{4})",
        tl
    ):
        try:
            start_yr = int(m.group(2))
            end_raw  = m.group(4)
            end_yr   = NOW_YEAR if "present" in end_raw else int(end_raw)
            dur = (end_yr - start_yr) * 12
            spans.append((start_yr, end_yr, dur))
        except: pass
    spans.sort()
    # Short tenures
    if rf.get("short_tenures") and spans:
        short = [s for s in spans if 0 < s[2] < 12]
        if len(short) >= 2:
            penalty += 4
            flags.append(f"⚠ {len(short)} short tenures (<12 mo)")
    # Job hopping: many jobs in last 5 years
    max_jobs = rf.get("max_jobs_5yr", 4)
    recent_jobs = [s for s in spans if s[1] >= NOW_YEAR - 5]
    if len(recent_jobs) > max_jobs:
        penalty += 3
        flags.append(f"⚠ {len(recent_jobs)} roles in last 5 years")
    # Employment gaps
    if len(spans) >= 2:
        max_gap = rf.get("long_gap_months", 10)
        for i in range(len(spans) - 1):
            gap = (spans[i+1][0] - spans[i][1]) * 12
            if gap > max_gap:
                penalty += 3
                flags.append(f"⚠ ~{gap//12}yr gap around {spans[i][1]}")
    max_penalty = p.get("red_flag_penalty", 10)
    return -min(penalty, max_penalty), flags


def sig_keyword_density(text, p):
    """Signal 13 – Keyword Density & Contextual Usage (not just presence)"""
    tl  = text.lower()
    words = re.findall(r'\b\w+\b', tl)
    wc  = max(len(words), 1)
    all_patterns = list(p["must_have"].keys()) + list(p["nice_to_have"].keys())
    hit_count = sum(len(re.findall(pat, tl)) for pat in all_patterns)
    density = hit_count / wc
    # Good density ~ 0.02–0.08 (2–8 relevant terms per 100 words)
    if density < 0.005:      score = 0.1
    elif density < 0.015:    score = 0.4
    elif density < 0.04:     score = 1.0
    elif density < 0.08:     score = 0.85
    else:                    score = 0.6   # keyword-stuffed
    return score * p["weights"]["keyword_density"], round(density * 100, 2)


def sig_resume_quality(text, p):
    """Signal 14 – Resume Completeness & Quality"""
    qm = p.get("quality_markers", {})
    pts = 0
    max_pts = 0
    details = []
    if "has_email" in qm:
        max_pts += qm["has_email"]
        if re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text):
            pts += qm["has_email"]; details.append("Email ✓")
        else: details.append("Email ✗")
    if "has_phone" in qm:
        max_pts += qm["has_phone"]
        if re.search(r"(?:\+?\d[\d\s\-()]{7,14}\d)", text):
            pts += qm["has_phone"]; details.append("Phone ✓")
        else: details.append("Phone ✗")
    if "has_linkedin" in qm:
        max_pts += qm["has_linkedin"]
        if re.search(r"linkedin\.com", text.lower()):
            pts += qm["has_linkedin"]; details.append("LinkedIn ✓")
        else: details.append("LinkedIn ✗")
    if "has_github" in qm:
        max_pts += qm["has_github"]
        if re.search(r"github\.com", text.lower()):
            pts += qm["has_github"]; details.append("GitHub ✓")
        else: details.append("GitHub ✗")
    if "has_quantified_results" in qm:
        max_pts += qm["has_quantified_results"]
        if re.search(r"\d+\s*%|\d+x\b|\d+\s*(?:million|thousand|k\b)", text.lower()):
            pts += qm["has_quantified_results"]; details.append("Metrics ✓")
        else: details.append("Metrics ✗")
    wc_req = qm.get("min_word_count", 200)
    wc_actual = len(re.findall(r'\b\w+\b', text))
    max_pts += 2
    if wc_actual >= wc_req:
        pts += 2; details.append(f"Length ✓ ({wc_actual}w)")
    else:
        details.append(f"Length ✗ ({wc_actual}w < {wc_req})")
    ratio = pts / max(max_pts, 1)
    return ratio * p["weights"]["resume_quality"], details, wc_actual


def sig_portfolio(text, p):
    """Signal 15 – Open-Source / Portfolio / Side Projects"""
    tl = text.lower()
    hits = []
    for pat in p.get("portfolio_patterns", []):
        if re.search(pat, tl):
            hits.append(pat)
    ratio = min(len(hits) / max(len(p.get("portfolio_patterns", [])) * 0.4, 1), 1.0)
    return ratio * p["weights"]["portfolio"], hits


def extract_contact(text):
    email_m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    phone_m = re.search(r"(?:\+91[\-\s]?)?[6-9]\d{9}|(?:\+?\d[\d\s\-()]{7,14}\d)", text)
    linkedin_m = re.search(r"linkedin\.com/in/[\w\-]+", text.lower())
    github_m = re.search(r"github\.com/[\w\-]+", text.lower())
    name = "—"
    for line in text.splitlines():
        l = line.strip()
        if 2 <= len(l.split()) <= 5 and re.match(r"^[A-Za-z\s\.\-]+$", l) and len(l) > 4:
            name = l; break
    return {
        "name":     name,
        "email":    email_m.group(0) if email_m else "—",
        "phone":    phone_m.group(0).strip() if phone_m else "—",
        "linkedin": linkedin_m.group(0) if linkedin_m else "—",
        "github":   github_m.group(0) if github_m else "—",
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MASTER SCORER
# ═══════════════════════════════════════════════════════════════════════════════
def score_resume(text: str, profile: dict) -> dict:
    s1,  must_matched,   must_missing  = sig_must_have(text, profile)
    s2,  nice_matched                  = sig_nice_to_have(text, profile)
    s3,  skill_depth_yrs               = sig_skill_depth(text, profile)
    s4,  exp_years                     = sig_experience(text, profile)
    s5,  is_recent                     = sig_recency(text, profile)
    s6,  seniority_hit                 = sig_seniority(text, profile)
    s7a, edu_hit                       = sig_education(text, profile)
    s7b, cert_hits                     = sig_certifications(text, profile)
    s8,  domain_hits                   = sig_domain(text, profile)
    s9,  title_hits                    = sig_title_match(text, profile)
    s10, ach_hits                      = sig_achievements(text, profile)
    s11, lead_hits                     = sig_leadership(text, profile)
    s12, red_flag_msgs                 = sig_red_flags(text, profile)
    s13, kw_density                    = sig_keyword_density(text, profile)
    s14, quality_details, word_count   = sig_resume_quality(text, profile)
    s15, portfolio_hits                = sig_portfolio(text, profile)

    raw = s1+s2+s3+s4+s5+s6+s7a+s7b+s8+s9+s10+s11+s13+s14+s15
    total = max(raw + s12, 0)
    max_possible = sum(profile["weights"].values())
    pct = round((total / max_possible) * 100, 1)

    if pct >= 80:          verdict, tag = "🏆 Excellent Match",    "excellent"
    elif pct >= 65:        verdict, tag = "✅ Strong Match",        "strong"
    elif pct >= 50:        verdict, tag = "🟡 Moderate Match",      "moderate"
    elif pct >= 35:        verdict, tag = "⚠️  Partial Match",       "partial"
    elif must_missing:     verdict, tag = "❌ Missing Core Skills",  "weak"
    else:                  verdict, tag = "❌ Poor Match",           "weak"

    return {
        "score":           pct,
        "verdict":         verdict,
        "tag":             tag,
        "exp_years":       exp_years,
        "must_matched":    must_matched,
        "must_missing":    must_missing,
        "nice_matched":    nice_matched,
        "seniority":       seniority_hit,
        "achievements":    len(ach_hits),
        "leadership":      len(lead_hits),
        "red_flags":       red_flag_msgs,
        "is_recent":       is_recent,
        "word_count":      word_count,
        "quality":         quality_details,
        "portfolio":       bool(portfolio_hits),
        "kw_density":      kw_density,
        "certs":           cert_hits,
        "breakdown": {
            "must_have":       round(s1,  1),
            "nice_to_have":    round(s2,  1),
            "skill_depth":     round(s3,  1),
            "experience":      round(s4,  1),
            "recency":         round(s5,  1),
            "seniority":       round(s6,  1),
            "education":       round(s7a, 1),
            "certifications":  round(s7b, 1),
            "domain":          round(s8,  1),
            "title_match":     round(s9,  1),
            "achievements":    round(s10, 1),
            "leadership":      round(s11, 1),
            "red_flags":       round(s12, 1),
            "keyword_density": round(s13, 1),
            "resume_quality":  round(s14, 1),
            "portfolio":       round(s15, 1),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  COLOUR PALETTE & FONTS
# ═══════════════════════════════════════════════════════════════════════════════
BG="#0b0f1a"; CARD="#131929"; CARD2="#1a2035"; BORDER="#1e2d4a"
ACCENT="#3b82f6"; ACCENT2="#8b5cf6"; ACCENT3="#06b6d4"
SUCCESS="#10b981"; WARNING="#f59e0b"; DANGER="#ef4444"; ORANGE="#f97316"
FG="#e2e8f0"; FG2="#94a3b8"; MUTED="#475569"
GOLD="#fbbf24"; SILVER="#94a3b8"; BRONZE="#b45309"

TAG_COLORS = {
    "excellent": ("#052e16","#86efac"),
    "strong":    ("#0d2218","#4ade80"),
    "moderate":  ("#1f1a0a","#fcd34d"),
    "partial":   ("#1c1408","#fdba74"),
    "weak":      ("#1f0f0f","#fca5a5"),
}

F1=("Segoe UI",19,"bold"); F2=("Segoe UI",12,"bold"); F3=("Segoe UI",10,"bold")
FN=("Segoe UI",10); FS=("Segoe UI",9); FM=("Consolas",9)


# ═══════════════════════════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Resume Screener Pro  •  15-Signal Engine  •  Offline")
        self.configure(bg=BG); self.geometry("1440x860"); self.minsize(1100,680)
        self.profiles  = DEFAULT_PROFILES.copy()
        self.files: list[str] = []
        self.results:  list[dict] = []
        self.sort_col  = "score"
        self.sort_rev  = True
        self._build(); self._dep_check()

    # ── dep warning ─────────────────────────────────────────────────────────
    def _dep_check(self):
        miss = []
        if not HAS_PYPDF:  miss.append("pypdf          →  pip install pypdf")
        if not HAS_DOCX:   miss.append("python-docx    →  pip install python-docx")
        if miss:
            messagebox.showwarning("Missing Libraries",
                "Some file types won't work:\n\n" + "\n".join(miss))

    # ── top-level layout ────────────────────────────────────────────────────
    def _build(self):
        # header
        hdr = tk.Frame(self, bg=BG, pady=10); hdr.pack(fill="x", padx=20)
        tk.Label(hdr, text="⚡ Resume Screener Pro", font=F1, bg=BG, fg=FG).pack(side="left")
        tk.Label(hdr, text="15 Signals  •  Offline  •  No API Keys",
                 font=FS, bg=BG, fg=MUTED).pack(side="left", padx=14)
        # body
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True, padx=16, pady=0)
        body.columnconfigure(1, weight=1); body.rowconfigure(0, weight=1)
        self._left(body); self._right(body)
        # status
        sf = tk.Frame(self, bg=CARD, pady=5); sf.pack(fill="x", side="bottom")
        self.sv = tk.StringVar(value="Ready  –  add resumes, choose a profile, click Analyse")
        tk.Label(sf, textvariable=self.sv, font=FS, bg=CARD, fg=FG2, padx=12).pack(side="left")

    # ── LEFT panel ──────────────────────────────────────────────────────────
    def _left(self, parent):
        lf = tk.Frame(parent, bg=CARD, padx=14, pady=12, width=300)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0,10))
        lf.pack_propagate(False)

        # Profile
        tk.Label(lf, text="Job Profile", font=F2, bg=CARD, fg=FG).pack(anchor="w")
        self.pv = tk.StringVar(value=list(self.profiles.keys())[0])
        pr = tk.Frame(lf, bg=CARD); pr.pack(fill="x", pady=(4,0))
        self.pcb = ttk.Combobox(pr, textvariable=self.pv,
                                 values=list(self.profiles.keys()),
                                 state="readonly", font=FN)
        self.pcb.pack(side="left", fill="x", expand=True)
        _btn(pr,"+ New",self._new_profile,ACCENT2).pack(side="left",padx=(6,0))
        self.pcb.bind("<<ComboboxSelected>>", lambda _: self._prev())

        self.pdtxt = tk.Text(lf, height=6, bg="#0d1424", fg=FG2, font=FM,
                              bd=0, wrap="word", state="disabled", relief="flat")
        self.pdtxt.pack(fill="x", pady=(6,0)); self._prev()

        _sep(lf)

        # Files
        tk.Label(lf, text="Resumes", font=F2, bg=CARD, fg=FG).pack(anchor="w")
        self.fcl = tk.Label(lf, text="0 files", font=FS, bg=CARD, fg=MUTED)
        self.fcl.pack(anchor="w")
        br = tk.Frame(lf, bg=CARD); br.pack(fill="x", pady=5)
        _btn(br,"📂 Add Files", self._add_files, ACCENT).pack(side="left")
        _btn(br,"📁 Folder",    self._add_folder,ACCENT2).pack(side="left",padx=5)
        _btn(br,"🗑",           self._clr,       "#374151").pack(side="right")

        self.flb = tk.Listbox(lf, bg="#0d1424", fg=FG2, font=FS,
                               selectbackground=ACCENT, bd=0, height=9, activestyle="none")
        self.flb.pack(fill="both", expand=True)

        _sep(lf)

        # Filters
        tk.Label(lf, text="Filters", font=F2, bg=CARD, fg=FG).pack(anchor="w")
        self.ms  = tk.IntVar(value=0)
        self.me  = tk.DoubleVar(value=0)
        self.vf  = tk.StringVar(value="All")
        self.shrf= tk.BooleanVar(value=False)
        _slider(lf, "Min Score (%)",      self.ms,  0, 100)
        _slider(lf, "Min Exp (yrs)",      self.me,  0, 30)
        vrow = tk.Frame(lf, bg=CARD); vrow.pack(fill="x", pady=3)
        tk.Label(vrow, text="Verdict:", font=FS, bg=CARD, fg=FG2, width=12, anchor="w").pack(side="left")
        ttk.Combobox(vrow, textvariable=self.vf, font=FS, state="readonly", width=16,
                     values=["All","Excellent","Strong","Moderate","Partial","Weak"]).pack(side="left")
        rfrow = tk.Frame(lf, bg=CARD); rfrow.pack(fill="x", pady=2)
        tk.Checkbutton(rfrow, text="Hide flagged (red flags)", variable=self.shrf,
                       bg=CARD, fg=FG2, selectcolor=CARD, font=FS,
                       activebackground=CARD).pack(side="left")

        _sep(lf)

        self.rb = tk.Button(lf, text="▶  Analyse Resumes", font=F2,
                             bg=SUCCESS, fg="white", bd=0, pady=10,
                             cursor="hand2", command=self._run)
        self.rb.pack(fill="x")
        _btn(lf,"💾 Export JSON", self._export, "#374151").pack(fill="x", pady=(5,0))
        _btn(lf,"📋 Export CSV",  self._export_csv, "#374151").pack(fill="x", pady=(3,0))

    # ── RIGHT panel ─────────────────────────────────────────────────────────
    def _right(self, parent):
        rf = tk.Frame(parent, bg=BG)
        rf.grid(row=0, column=1, sticky="nsew")
        rf.rowconfigure(1, weight=1); rf.columnconfigure(0, weight=1)

        # stat cards
        self.scf = tk.Frame(rf, bg=BG); self.scf.grid(row=0,column=0,sticky="ew",pady=(0,8))
        self._stats()

        # paned: tree top / detail bottom
        pw = tk.PanedWindow(rf, orient="vertical", bg=BG, sashwidth=5,
                             sashrelief="flat", sashpad=2)
        pw.grid(row=1, column=0, sticky="nsew")

        tf = tk.Frame(pw, bg=CARD); self._tree(tf); pw.add(tf, minsize=200)
        df = tk.Frame(pw, bg=CARD, padx=12, pady=8); self._detail(df); pw.add(df, minsize=140)

    # ── stat cards ──────────────────────────────────────────────────────────
    def _stats(self):
        for w in self.scf.winfo_children(): w.destroy()
        R = self.results
        top3  = [r for r in R if r["tag"] == "excellent"]
        strng = [r for r in R if r["tag"] == "strong"]
        mod   = [r for r in R if r["tag"] == "moderate"]
        bad   = [r for r in R if r["tag"] in ("weak","partial")]
        avg   = sum(r["score"] for r in R)/max(len(R),1)
        flagged=[r for r in R if r["red_flags"]]
        cards  = [
            ("Total",   str(len(R)),          ACCENT),
            ("Excellent",str(len(top3)),       GOLD),
            ("Strong",  str(len(strng)),       SUCCESS),
            ("Moderate",str(len(mod)),         WARNING),
            ("Weak",    str(len(bad)),          DANGER),
            ("Avg Score",f"{avg:.1f}%",        ACCENT3),
            ("Red Flags",str(len(flagged)),    ORANGE),
        ]
        for lbl, val, clr in cards:
            c = tk.Frame(self.scf, bg=CARD, padx=12, pady=7)
            c.pack(side="left", padx=(0,7))
            tk.Label(c, text=val, font=("Segoe UI",17,"bold"), bg=CARD, fg=clr).pack()
            tk.Label(c, text=lbl, font=FS, bg=CARD, fg=MUTED).pack()

    # ── tree ────────────────────────────────────────────────────────────────
    def _tree(self, parent):
        COLS = ("rank","name","file","score","verdict","exp",
                "must","nice","red","ach","lead","qual","certs")
        HDRS = ("#","Name","File","Score","Verdict","Exp","Must-Have","Nice-to-Have",
                "Red Flags","Ach","Lead","Quality","Certs")
        WIDS = [36,155,165,65,165,58,190,180,130,42,42,110,90]

        sty = ttk.Style(); sty.theme_use("clam")
        sty.configure("Treeview", background=CARD, fieldbackground=CARD,
                       foreground=FG, rowheight=24, font=FN, borderwidth=0)
        sty.configure("Treeview.Heading", background="#0d1929", foreground=FG2,
                       font=F3, relief="flat", padding=5)
        sty.map("Treeview", background=[("selected",ACCENT)], foreground=[("selected","white")])

        self.tv = ttk.Treeview(parent, columns=COLS, show="headings", selectmode="browse")
        for col,hdr,w in zip(COLS,HDRS,WIDS):
            self.tv.heading(col, text=hdr, command=lambda c=col: self._sort(c))
            self.tv.column(col, width=w,
                            anchor="center" if col in ("rank","score","exp","ach","lead") else "w",
                            stretch=(col in ("must","nice")))

        vsb=ttk.Scrollbar(parent,orient="vertical",  command=self.tv.yview)
        hsb=ttk.Scrollbar(parent,orient="horizontal",command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x")
        self.tv.pack(fill="both",expand=True)
        self.tv.bind("<<TreeviewSelect>>", self._sel)

        for tag,(bg,fg) in TAG_COLORS.items():
            self.tv.tag_configure(tag, background=bg, foreground=fg)

    # ── detail ──────────────────────────────────────────────────────────────
    def _detail(self, parent):
        tk.Label(parent, text="Candidate Detail  (click any row)",
                  font=F2, bg=CARD, fg=FG).pack(anchor="w")
        self.dtxt = tk.Text(parent, bg="#0d1424", fg=FG, font=FM, bd=0,
                             wrap="word", state="disabled", relief="flat")
        self.dtxt.pack(fill="both", expand=True, pady=(4,0))

    # ── helpers ─────────────────────────────────────────────────────────────
    def _prev(self):
        nm = self.pv.get(); p = self.profiles.get(nm,{})
        must = p.get("must_have",{})
        nice = p.get("nice_to_have",{})
        lines=[
            f"Role     : {p.get('description',nm)}",
            f"Min/Ideal: {p.get('min_exp_years','?')} / {p.get('ideal_exp_years','?')} yrs",
            f"Must-have ({len(must)}): " + ", ".join(must.values()),
            f"Nice-have ({len(nice)}): " + ", ".join(list(nice.values())[:10])
                + ("…" if len(nice)>10 else ""),
            f"Weights  : " + "  ".join(f"{k[:4]}={v}" for k,v in p.get("weights",{}).items()),
        ]
        self.pdtxt.configure(state="normal")
        self.pdtxt.delete("1.0","end")
        self.pdtxt.insert("end","\n".join(lines))
        self.pdtxt.configure(state="disabled")

    def _add_files(self):
        ps=filedialog.askopenfilenames(
            title="Select Resumes",
            filetypes=[("Resumes","*.pdf *.docx *.doc *.txt"),("All","*.*")])
        for p in ps:
            if p not in self.files:
                self.files.append(p); self.flb.insert("end",Path(p).name)
        self.fcl.config(text=f"{len(self.files)} files")

    def _add_folder(self):
        d=filedialog.askdirectory(title="Folder with resumes")
        if not d: return
        for f in Path(d).rglob("*"):
            if f.suffix.lower() in {".pdf",".docx",".doc",".txt"} and str(f) not in self.files:
                self.files.append(str(f)); self.flb.insert("end",f.name)
        self.fcl.config(text=f"{len(self.files)} files")

    def _clr(self):
        self.files.clear(); self.flb.delete(0,"end"); self.fcl.config(text="0 files")

    def _run(self):
        if not self.files:
            messagebox.showinfo("No files","Add resume files first."); return
        self.rb.config(state="disabled",text="⏳  Analysing…")
        threading.Thread(target=self._analyse, daemon=True).start()

    def _analyse(self):
        pn = self.pv.get(); prof = self.profiles[pn]
        self.results = []
        for i,path in enumerate(self.files):
            self.sv.set(f"Processing {i+1}/{len(self.files)}: {Path(path).name}")
            text = extract_text(path)
            ct   = extract_contact(text)
            sc   = score_resume(text, prof)
            self.results.append({**ct, "file":Path(path).name, "path":path,
                                  "raw": text[:5000], **sc})
        self.results.sort(key=lambda x: x["score"], reverse=True)
        self.after(0, self._populate)

    def _populate(self):
        ms  = self.ms.get()
        me  = self.me.get()
        vfl = self.vf.get().lower()
        hrf = self.shrf.get()

        vis = [r for r in self.results
               if r["score"]   >= ms
               and r["exp_years"] >= me
               and (vfl == "all" or vfl in r["verdict"].lower())
               and not (hrf and r["red_flags"])]

        self.tv.delete(*self.tv.get_children())
        for rank,r in enumerate(vis,1):
            rf_str  = ", ".join(r["red_flags"]) if r["red_flags"] else "—"
            must_str= ", ".join(r["must_matched"]) or "—"
            nice_str= ", ".join(r["nice_matched"][:6]) or "—"
            qual_str= "  ".join(r["quality"])
            cert_str= str(len(r["certs"])) + " cert" + ("s" if len(r["certs"])!=1 else "")
            self.tv.insert("","end", iid=str(rank), tags=(r["tag"],),
                            values=(rank, r["name"], r["file"],
                                    f"{r['score']}%", r["verdict"],
                                    r["exp_years"],
                                    must_str, nice_str, rf_str,
                                    r["achievements"], r["leadership"],
                                    qual_str, cert_str))
        self._stats()
        self.sv.set(f"Done — {len(vis)} shown (of {len(self.results)} processed)")
        self.rb.config(state="normal", text="▶  Analyse Resumes")

    def _sel(self, _=None):
        sel = self.tv.selection()
        if not sel: return
        vals  = self.tv.item(sel[0],"values")
        fname = vals[2]
        r = next((x for x in self.results if x["file"]==fname), None)
        if not r: return
        bd = r["breakdown"]
        w  = self.profiles[self.pv.get()]["weights"]
        lines = [
            "━"*62,
            f"  Name     :  {r['name']}",
            f"  Email    :  {r['email']}",
            f"  Phone    :  {r['phone']}",
            f"  LinkedIn :  {r.get('linkedin','—')}",
            f"  GitHub   :  {r.get('github','—')}",
            f"  File     :  {r['file']}",
            "━"*62,
            f"  TOTAL SCORE : {r['score']}%   {r['verdict']}",
            f"  Experience  : {r['exp_years']} yrs detected",
            f"  Word Count  : {r['word_count']}  |  KW Density: {r['kw_density']}%",
            "─"*62,
            "  SIGNAL BREAKDOWN              scored / max",
        ]
        signal_rows = [
            ("1  Must-Have Skills",    bd["must_have"],      w["must_have"]),
            ("2  Nice-to-Have Skills", bd["nice_to_have"],   w["nice_to_have"]),
            ("3  Skill Depth",         bd["skill_depth"],    w["skill_depth"]),
            ("4  Total Experience",    bd["experience"],     w["experience"]),
            ("5  Recency",             bd["recency"],        w["recency"]),
            ("6  Seniority",           bd["seniority"],      w["seniority"]),
            ("7a Education",           bd["education"],      w["education"]),
            ("7b Certifications",      bd["certifications"], w["certifications"]),
            ("8  Domain Relevance",    bd["domain"],         w["domain"]),
            ("9  Job Title Match",     bd["title_match"],    w["title_match"]),
            ("10 Achievements",        bd["achievements"],   w["achievements"]),
            ("11 Leadership",          bd["leadership"],     w["leadership"]),
            ("12 Red Flags",           bd["red_flags"],      0),
            ("13 Keyword Density",     bd["keyword_density"],w["keyword_density"]),
            ("14 Resume Quality",      bd["resume_quality"], w["resume_quality"]),
            ("15 Portfolio/OSS",       bd["portfolio"],      w["portfolio"]),
        ]
        for label, got, mx in signal_rows:
            bar_len = int((got / mx * 14) if mx > 0 else 0) if mx else 0
            bar = "█"*max(bar_len,0) + "░"*(14-max(bar_len,0)) if mx else "─"*14
            lines.append(f"    {label:<28} {got:>5.1f} / {mx:>2}   [{bar}]")
        lines += [
            "─"*62,
            f"  ✅ Must-have matched   : {', '.join(r['must_matched']) or 'none'}",
            f"  ❌ Must-have MISSING   : {', '.join(r['must_missing']) or 'none'}",
            f"  ⭐ Nice-to-have matched: {', '.join(r['nice_matched']) or 'none'}",
            f"  🏅 Certifications      : {', '.join(r['certs']) or 'none'}",
            f"  🚩 Red Flags           : {', '.join(r['red_flags']) or 'none'}",
            f"  📋 Resume Quality      : {', '.join(r['quality'])}",
            f"  🔗 Portfolio/OSS       : {'Yes' if r['portfolio'] else 'No'}",
            "─"*62,
            "  RESUME PREVIEW",
            "─"*62,
            r["raw"][:2000],
        ]
        self.dtxt.configure(state="normal")
        self.dtxt.delete("1.0","end")
        self.dtxt.insert("end","\n".join(lines))
        self.dtxt.configure(state="disabled")

    def _sort(self, col):
        self.sort_rev = not self.sort_rev if self.sort_col==col else True
        self.sort_col = col
        km = {"score":lambda r:r["score"],"exp":lambda r:r["exp_years"],
              "name":lambda r:r["name"].lower(),"file":lambda r:r["file"].lower(),
              "verdict":lambda r:r["verdict"],"ach":lambda r:r["achievements"],
              "lead":lambda r:r["leadership"]}
        self.results.sort(key=km.get(col,lambda r:r.get(col,"")), reverse=self.sort_rev)
        self._populate()

    def _export(self):
        if not self.results: messagebox.showinfo("Empty","Run analysis first."); return
        p = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON","*.json")],
            initialfile=f"screening_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        if p:
            out = [{k:v for k,v in r.items() if k!="raw"} for r in self.results]
            Path(p).write_text(json.dumps(out,indent=2), encoding="utf-8")
            messagebox.showinfo("Saved",f"JSON saved:\n{p}")

    def _export_csv(self):
        if not self.results: messagebox.showinfo("Empty","Run analysis first."); return
        p = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            initialfile=f"screening_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        if not p: return
        import csv
        fields = ["rank","name","email","phone","file","score","verdict","exp_years",
                  "must_matched","must_missing","nice_matched","achievements",
                  "leadership","red_flags","word_count","portfolio","certs"]
        with open(p,"w",newline="",encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for i,r in enumerate(self.results,1):
                row = {k:v for k,v in r.items() if k in fields}
                row["rank"]         = i
                row["must_matched"] = ", ".join(r.get("must_matched",[]))
                row["must_missing"] = ", ".join(r.get("must_missing",[]))
                row["nice_matched"] = ", ".join(r.get("nice_matched",[]))
                row["red_flags"]    = " | ".join(r.get("red_flags",[]))
                row["certs"]        = str(len(r.get("certs",[])))
                w.writerow(row)
        messagebox.showinfo("Saved",f"CSV saved:\n{p}")

    # ── New Profile dialog ───────────────────────────────────────────────────
    def _new_profile(self):
        dlg = tk.Toplevel(self); dlg.title("Create Job Profile")
        dlg.configure(bg=BG); dlg.geometry("620x600"); dlg.resizable(False,False)

        def lbl(t): tk.Label(dlg,text=t,font=F3,bg=BG,fg=FG,anchor="w").pack(fill="x",padx=16,pady=(10,2))
        def entry():
            e=tk.Entry(dlg,bg=CARD,fg=FG,font=FN,bd=0,insertbackground=FG,relief="flat")
            e.pack(fill="x",padx=16,ipady=6); return e
        def txtbox(h=2):
            t=tk.Text(dlg,height=h,bg=CARD,fg=FG,font=FM,bd=0,insertbackground=FG,relief="flat")
            t.pack(fill="x",padx=16); return t

        lbl("Profile Name"); ne=entry(); ne.insert(0,"My Custom Role")
        lbl("Description");  de=entry(); de.insert(0,"e.g. Mid-level backend engineer")
        lbl("Must-have skills (comma-separated)"); mt=txtbox()
        mt.insert("end","python, django, postgresql")
        lbl("Nice-to-have skills (comma-separated)"); gt=txtbox()
        gt.insert("end","docker, redis, celery, git")
        lbl("Min / Ideal experience (years,  e.g.  3,6)"); ee=entry(); ee.insert(0,"3, 6")
        lbl("Target job titles (comma-separated)");        ti=entry()
        ti.insert(0,"python developer, backend engineer, software engineer")

        def save():
            name = ne.get().strip()
            if not name: messagebox.showerror("Error","Name required",parent=dlg); return
            def pats(raw):
                return {r"\b"+re.escape(s.strip().lower())+r"\b": s.strip().title()
                        for s in raw.split(",") if s.strip()}
            try:
                pts = [float(x) for x in ee.get().split(",")]
                mn,id_ = (pts[0],pts[1]) if len(pts)>=2 else (pts[0],pts[0]+3)
            except: mn,id_=3,6
            titles = [r"\b"+re.escape(t.strip().lower())+r"\b"
                      for t in ti.get().split(",") if t.strip()]
            self.profiles[name]={
                "description":de.get().strip(), "min_exp_years":mn, "ideal_exp_years":id_,
                "must_have":pats(mt.get("1.0","end")),
                "nice_to_have":pats(gt.get("1.0","end")),
                "skill_depth_markers":[],
                "seniority_titles":{r"\bsenior\b|\bsr\.?\b":3,r"\blead\b":4,r"\barchitect\b":5,r"\bjunior\b":-1},
                "education":{r"\bb\.?tech\b|\bbachelor":3,r"\bm\.?tech\b|\bmaster":4},
                "certifications":{},
                "domain_keywords":{},
                "target_titles":titles,
                "achievement_patterns":[r"improved\s+\w+\s+by\s+\d+",r"reduced\s+\w+\s+by\s+\d+"],
                "leadership_patterns":[r"\bmentored?\b",r"\bcode\s+review\b",r"\blead\b"],
                "red_flags":{"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
                "quality_markers":{"has_email":1,"has_phone":1,"min_word_count":300},
                "portfolio_patterns":[r"\bgithub\.com/\w+",r"\bopen[\s-]source\b"],
                "weights":{"must_have":25,"nice_to_have":12,"skill_depth":6,"experience":10,
                           "recency":5,"seniority":6,"education":4,"certifications":3,
                           "domain":4,"title_match":5,"achievements":5,"leadership":4,
                           "keyword_density":3,"resume_quality":3,"portfolio":5},
                "red_flag_penalty":8,
            }
            self.pcb["values"]=list(self.profiles.keys())
            self.pv.set(name); self._prev(); dlg.destroy()

        tk.Button(dlg, text="Save Profile", font=F2, bg=SUCCESS, fg="white",
                  bd=0, pady=10, cursor="hand2", command=save).pack(fill="x", padx=16, pady=14)


# ── widget helpers ────────────────────────────────────────────────────────────
def _btn(p, t, c, col):
    return tk.Button(p, text=t, font=FS, bg=col, fg="white", bd=0,
                     padx=8, pady=5, cursor="hand2", command=c)

def _sep(p):
    tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=8)

def _slider(p, lbl, var, lo, hi):
    row = tk.Frame(p, bg=CARD); row.pack(fill="x", pady=2)
    tk.Label(row, text=lbl, font=FS, bg=CARD, fg=FG2, width=18, anchor="w").pack(side="left")
    tk.Scale(row, variable=var, from_=lo, to=hi, orient="horizontal",
             bg=CARD, fg=FG, troughcolor=BORDER, highlightthickness=0,
             font=FS, length=110).pack(side="left")
    tk.Label(row, textvariable=var, font=FS, bg=CARD, fg=ACCENT, width=4).pack(side="left")


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    App().mainloop()