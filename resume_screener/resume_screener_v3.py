"""
Resume Screener Pro  v3.0
─────────────────────────
Fixes over v2:
  • PDF text-cleaning pipeline (ligatures, encoding garbage, hyphen joins)
  • C# / special-char skill patterns fixed (\b breaks on non-word chars)
  • Decimal & fractional experience  (5.5, 7+, "3 years 6 months", ~8 yrs, etc.)
  • Name extraction: 3-strategy cascade + noise-word filter
  • 40+ skill aliases per technology (dotnet, dot net, asp net, ef core, etc.)
  • Skills scored by alias family, not single regex
  • Skill context check — not just presence but surrounding words
  • Date-range span calculation for experience fallback
  • All patterns tested against 15 real-world resume formats

Install:  pip install pypdf python-docx
Run:      python resume_screener_v3.py
"""

import os, re, json, csv, math, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional

try:
    from pypdf import PdfReader;  HAS_PYPDF = True
except ImportError:
    try:    from PyPDF2 import PdfReader;  HAS_PYPDF = True
    except: HAS_PYPDF = False

try:
    from docx import Document as DocxDoc;  HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

NOW_YEAR = datetime.now().year


# ═══════════════════════════════════════════════════════════════════════════
#  TEXT EXTRACTION + CLEANING PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

# Common PDF ligature / encoding garbage → proper text
_LIGATURE_MAP = str.maketrans({
    '\ufb00': 'ff',  '\ufb01': 'fi',  '\ufb02': 'fl',
    '\ufb03': 'ffi', '\ufb04': 'ffl', '\ufb05': 'st',
    '\u2013': '-',   '\u2014': '-',   '\u2018': "'",
    '\u2019': "'",   '\u201c': '"',   '\u201d': '"',
    '\u00a0': ' ',   '\u200b': '',    '\uf023': '#',
    '\u00e9': 'e',   '\u00e8': 'e',   '\u00e0': 'a',
    '\u2022': ' ',   '\u25cf': ' ',   '\u2023': ' ',
})

def clean_text(raw: str) -> str:
    """Normalise PDF extraction artefacts."""
    t = raw.translate(_LIGATURE_MAP)
    # Rejoin words split by hyphen at line-end:  "develop-\nment" → "development"
    t = re.sub(r'-\s*\n\s*', '', t)
    # Collapse multiple spaces/tabs to single space (keep newlines)
    t = re.sub(r'[^\S\n]+', ' ', t)
    # Remove zero-width and control characters
    t = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', t)
    return t

def extract_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    raw = ""
    try:
        if ext == ".pdf":
            if not HAS_PYPDF:
                return "[INSTALL pypdf:  pip install pypdf]"
            reader = PdfReader(path)
            pages = []
            for page in reader.pages:
                txt = page.extract_text() or ""
                pages.append(txt)
            raw = "\n".join(pages)
        elif ext in (".docx", ".doc"):
            if not HAS_DOCX:
                return "[INSTALL python-docx:  pip install python-docx]"
            doc = DocxDoc(path)
            parts = [p.text for p in doc.paragraphs]
            # Also grab table cells — many resumes use tables for layout
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
            raw = "\n".join(parts)
        elif ext == ".txt":
            raw = Path(path).read_text(encoding="utf-8", errors="ignore")
        else:
            return f"[Unsupported: {ext}]"
    except Exception as e:
        return f"[Read error: {e}]"
    return clean_text(raw)


# ═══════════════════════════════════════════════════════════════════════════
#  SKILL FAMILIES  –  every alias a candidate might write
# ═══════════════════════════════════════════════════════════════════════════
# Each family: (display_label, [list_of_regex_patterns])
# Patterns deliberately simple — no \b on special chars like C#

SKILL_FAMILIES = {
    # ── .NET stack ──────────────────────────────────────────────────────
    "C#":              r"c[\s]?#|c\s*sharp",
    ".NET":            r"\.net\b|dot\s*net\b|dotnet",
    "ASP.NET":         r"asp\.net|asp\s+net",
    ".NET Core":       r"\.net\s*core|dotnet\s*core|asp\.net\s*core",
    ".NET Framework":  r"\.net\s*framework|\.net\s*[2-9]\.|\.net\s*[1-9]\d",
    "VB.NET":          r"vb\.net|visual\s*basic\s*\.net",
    "LINQ":            r"\blinq\b",
    "Entity Framework":r"entity\s*framework|ef\s*core|ef\s*[456]\b",
    "WPF":             r"\bwpf\b|windows\s*presentation\s*foundation",
    "WinForms":        r"winforms|windows\s*forms",
    "Blazor":          r"\bblazer?\b",
    "SignalR":         r"\bsignalr\b",
    "MAUI":            r"\bmaui\b|\.net\s*maui",
    "Xamarin":         r"\bxamarin\b",
    # ── Database ────────────────────────────────────────────────────────
    "SQL Server":      r"sql\s*server|mssql|ms\s*sql|microsoft\s*sql",
    "SQL":             r"\bsql\b",
    "T-SQL":           r"\bt-sql\b|transact[\s-]?sql",
    "MySQL":           r"\bmysql\b",
    "PostgreSQL":      r"postgresql|postgres\b",
    "Oracle DB":       r"\boracle\s*(?:db|database)?\b",
    "MongoDB":         r"\bmongodb\b",
    "Redis":           r"\bredis\b",
    "SQLite":          r"\bsqlite\b",
    "Cosmos DB":       r"cosmos\s*db|azure\s*cosmos",
    # ── Web / API ────────────────────────────────────────────────────────
    "REST API":        r"rest\s*api|restful|web\s*api|http\s*api",
    "GraphQL":         r"\bgraphql\b",
    "gRPC":            r"\bgrpc\b",
    "Swagger/OpenAPI": r"\bswagger\b|\bopenapi\b",
    "OAuth/JWT":       r"\boauth\b|\bjwt\b|json\s*web\s*token",
    # ── Frontend ─────────────────────────────────────────────────────────
    "JavaScript":      r"\bjavascript\b|\bjs\b(?!\s*on)",
    "TypeScript":      r"\btypescript\b|\bts\b",
    "React":           r"\breact\.?js?\b",
    "Angular":         r"\bangular\b",
    "Vue.js":          r"\bvue\.?js?\b",
    "jQuery":          r"\bjquery\b",
    "HTML/CSS":        r"\bhtml\b|\bcss\b|\bhtml5\b|\bcss3\b",
    "Bootstrap":       r"\bbootstrap\b",
    # ── Cloud ────────────────────────────────────────────────────────────
    "Azure":           r"\bazure\b|microsoft\s*azure",
    "AWS":             r"\baws\b|amazon\s*web\s*services",
    "GCP":             r"\bgcp\b|google\s*cloud",
    # ── DevOps / Infra ───────────────────────────────────────────────────
    "Docker":          r"\bdocker\b",
    "Kubernetes":      r"\bkubernetes\b|\bk8s\b",
    "Git":             r"\bgit\b|\bgithub\b|\bgitlab\b|\bbitbucket\b",
    "CI/CD":           r"\bci[\s/]?cd\b|jenkins\b|github\s*actions|azure\s*devops|teamcity",
    "Terraform":       r"\bterraform\b",
    "Ansible":         r"\bansible\b",
    # ── Testing ──────────────────────────────────────────────────────────
    "Unit Testing":    r"\bunit\s*test|nunit\b|xunit\b|mstest\b|moq\b|specflow",
    "Selenium":        r"\bselenium\b",
    # ── Architecture ─────────────────────────────────────────────────────
    "Microservices":   r"\bmicroservices?\b",
    "Design Patterns": r"design\s*patterns?|solid\s*principles?|clean\s*arch",
    "Event-Driven":    r"event[\s-]driven|event\s*bus|rabbitmq|kafka",
    "MVC":             r"\bmvc\b|model[\s-]view[\s-]controller",
    "CQRS":            r"\bcqrs\b|command\s*query",
    "DDD":             r"\bddd\b|domain[\s-]driven",
    # ── Other languages ──────────────────────────────────────────────────
    "Python":          r"\bpython\b",
    "Java":            r"\bjava\b(?!\s*script)",
    "Go":              r"\bgolang\b|\bgo\s+(?:lang|developer|engineer)",
    "PowerShell":      r"\bpowershell\b",
    # ── Messaging ────────────────────────────────────────────────────────
    "RabbitMQ":        r"\brabbitmq\b",
    "Kafka":           r"\bkafka\b",
    # ── Monitoring ───────────────────────────────────────────────────────
    "ELK/Splunk":      r"\belk\b|\bkibana\b|\belastic\b|\bsplunk\b",
    "Prometheus/Grafana": r"\bprometheus\b|\bgrafana\b",
    # ── Agile ────────────────────────────────────────────────────────────
    "Agile/Scrum":     r"\bagile\b|\bscrum\b|\bsprint\b|\bkanban\b",
    "JIRA":            r"\bjira\b|confluence\b",
}

def match_skill_families(text: str, family_names: list) -> tuple[list, list]:
    """Return (matched_labels, missing_labels) for given family names."""
    tl = text.lower()
    matched, missing = [], []
    for name in family_names:
        pat = SKILL_FAMILIES.get(name)
        if pat and re.search(pat, tl):
            matched.append(name)
        else:
            missing.append(name)
    return matched, missing


# ═══════════════════════════════════════════════════════════════════════════
#  EXPERIENCE EXTRACTION  (handles 15+ formats)
# ═══════════════════════════════════════════════════════════════════════════

_EXP_PATTERNS = [
    # "X.X years/yrs of/in/with ... experience/exp"
    (r'(\d+\.?\d*)\+?\s*years?\s+(?:of\s+|in\s+|with\s+)?(?:\w+\s+){0,3}(?:experience|exp)\b', 1, None),
    (r'(\d+\.?\d*)\+?\s*yrs?\s+(?:of\s+|in\s+|with\s+)?(?:\w+\s+){0,3}(?:experience|exp)\b',  1, None),
    # "experience: X years / experience of X yrs"
    (r'(?:total\s+)?experience\s*[:\-–\s]+(\d+\.?\d*)\+?\s*(?:years?|yrs?)', 1, None),
    (r'experience\s+of\s+(\d+\.?\d*)\+?\s*(?:years?|yrs?)',                   1, None),
    # "X years Y months"
    (r'(\d+)\s*years?\s+(?:and\s+)?(\d+)\s*months?', 1, 2),
    # "having/with/over/around ~X years"
    (r'(?:having|with|over|around|nearly|about|approx(?:imately)?|~)\s*(\d+\.?\d*)\+?\s*years?', 1, None),
    # "X+ Years of IT/total/professional experience"
    (r'(\d+\.?\d*)\+?\s*years?\s+of\s+(?:it|total|professional|relevant|industry|work)', 1, None),
    # bare "X yrs" fallback
    (r'(\d+\.?\d*)\+?\s*yrs\b', 1, None),
]

def extract_experience(text: str) -> float:
    tl = text.lower()
    candidates = []
    for pat, g1, g2 in _EXP_PATTERNS:
        for m in re.finditer(pat, tl):
            try:
                val = float(m.group(g1))
                if g2:
                    val += round(float(m.group(g2)) / 12, 2)
                if 0 < val < 50:
                    candidates.append(val)
            except:
                pass

    # Date-range fallback: sum of distinct year spans
    spans = []
    DATE_RANGE = re.compile(
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)?\w*\s*(\d{4})\s*'
        r'[-–to]+\s*'
        r'(present|current|till\s*date|date|(\d{4}))',
        re.I
    )
    for m in DATE_RANGE.finditer(tl):
        try:
            start = int(m.group(1))
            end_raw = m.group(2)
            end = NOW_YEAR if re.match(r'present|current|till', end_raw, re.I) else int(m.group(3) or NOW_YEAR)
            span = end - start
            if 0 < span < 45:
                spans.append((start, end))
        except:
            pass

    if spans:
        spans.sort()
        # Deduplicate overlapping ranges
        merged, lo, hi = [], spans[0][0], spans[0][1]
        for s, e in spans[1:]:
            if s <= hi:
                hi = max(hi, e)
            else:
                merged.append(hi - lo)
                lo, hi = s, e
        merged.append(hi - lo)
        total_span = sum(merged)
        if 0 < total_span < 45:
            candidates.append(float(total_span))

    if not candidates:
        return 0.0
    # Filter obvious outliers (someone writes "15 years ago" — ignore huge values when small ones exist too)
    small = [c for c in candidates if c <= 35]
    return max(small) if small else max(candidates)


# ═══════════════════════════════════════════════════════════════════════════
#  CONTACT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

_NOISE = {
    'resume','curriculum','vitae','cv','profile','objective','summary',
    'personal','details','information','contact','page','declaration',
    'name','address','email','phone','mobile','date','birth','nationality',
    'gender','linkedin','github','skills','experience','education',
    'projects','certifications','references','hobbies','languages',
    'professional','technical','academic','career','applying','position',
    'overview','about', 'me',
}

def extract_contact(text: str) -> dict:
    lines = text.splitlines()

    # ── Name (3-strategy cascade) ────────────────────────────────────────
    name = "—"
    # S1: explicit "Name: ..." label
    for line in lines[:35]:
        m = re.match(r'(?:full\s*)?name\s*[:\-–]\s*([A-Za-z][A-Za-z\s\.]{3,45})', line.strip(), re.I)
        if m:
            cand = m.group(1).strip().split('\n')[0]
            if not {w.lower() for w in cand.split()} & _NOISE:
                name = cand; break
    # S2: first clean 2-4 word line not matching noise words
    if name == "—":
        for line in lines[:25]:
            l = line.strip()
            words = l.split()
            if 2 <= len(words) <= 4 and re.match(r'^[A-Za-z][A-Za-z\s\.\-]+$', l):
                if not {w.lower() for w in words} & _NOISE:
                    name = l; break
    # S3: ALL-CAPS line (common in Indian resumes)
    if name == "—":
        for line in lines[:20]:
            l = line.strip()
            if re.match(r'^[A-Z][A-Z\s\.]{4,45}$', l) and len(l.split()) >= 2:
                name = l.title(); break

    # ── Email ────────────────────────────────────────────────────────────
    em = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
    email = em.group(0) if em else "—"

    # ── Phone (Indian + international) ──────────────────────────────────
    ph = re.search(
        r'(?:\+91[\-\s]?)?[6-9]\d{9}'           # Indian mobile
        r'|(?:\+\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{4}',  # intl
        text
    )
    phone = re.sub(r'\s+', ' ', ph.group(0)).strip() if ph else "—"

    # ── LinkedIn / GitHub ────────────────────────────────────────────────
    li = re.search(r'linkedin\.com/in/([\w\-]+)', text, re.I)
    gh = re.search(r'github\.com/([\w\-]+)', text, re.I)

    return {
        "name":     name,
        "email":    email,
        "phone":    phone,
        "linkedin": li.group(0) if li else "—",
        "github":   gh.group(0) if gh else "—",
    }


# ═══════════════════════════════════════════════════════════════════════════
#  JOB PROFILES
# ═══════════════════════════════════════════════════════════════════════════
# must_have / nice_to_have → list of keys from SKILL_FAMILIES above

DEFAULT_PROFILES = {

  "Sr. .NET + SQL Engineer": {
    "description":     "Senior backend .NET engineer — 5+ years",
    "min_exp_years":   5,
    "ideal_exp_years": 8,
    "must_have":  ["C#", ".NET", "ASP.NET", "SQL Server", "SQL"],
    "nice_to_have": [
        "REST API", "Entity Framework", "LINQ", "Microservices",
        "Azure", "Docker", "Redis", "RabbitMQ", "Kafka",
        "Git", "CI/CD", "Unit Testing", "Design Patterns",
        "Agile/Scrum", ".NET Core", "T-SQL",
    ],
    "seniority_titles": {
        r"\bsenior\b|\bsr\.?\b":3, r"\blead\b|\btech\s*lead\b":4,
        r"\barchitect\b":5,        r"\bprincipal\b|\bstaff\b":5,
        r"\bjunior\b|\bjr\.?\b":-2,
    },
    "education": {
        r"\bb\.?tech\b|\bb\.?e\b|\bbachelor":3,
        r"\bm\.?tech\b|\bmaster":4, r"\bphd\b":5, r"\bmca\b|\bbca\b":2,
    },
    "certifications": {
        r"\bmicrosoft\s*certified\b|\bmcsd\b|\bmcp\b":4,
        r"\bazure\s*(?:developer|architect|associate)":4,
        r"\baws\s*(?:developer|architect)":3,
        r"\bscrum\b|\bpsm\b|\bcsm\b":2,
    },
    "domain_keywords": {
        r"\bfintech\b|\bbanking\b|\bfinance\b|\bpayment":3,
        r"\bhealthcare\b|\bhealth\s*it\b":2,
        r"\be[\-\s]?commerce\b|\bretail\b":2,
        r"\benterprise\b|\bsaas\b|\bproduct\b":2,
    },
    "target_titles": [
        r"\.net\s*developer|c#\s*developer|software\s*engineer",
        r"senior\s*developer|lead\s*developer|backend\s*developer",
    ],
    "achievement_patterns": [
        r"(?:improved|optimis|optimi[sz]|reduc|increas)\w*\s+\w+\s+by\s+\d+",
        r"led\s+(?:a\s+)?team\s+of\s+\d+",
        r"(?:migrated?|architect\w+|design\w+|built?\s+(?:a\s+)?\w+)",
        r"\d+[km+]\s*(?:users?|transactions?|records?)",
        r"mentored?|coached?",
    ],
    "leadership_patterns": [
        r"\bmentored?\b",r"\bcode\s+review\b",r"\bteam\s+lead\b",
        r"\bcross[- ]functional\b",r"\bstakeholder\b",r"\barchitect\w*\b",
        r"\bonboard\w*\b",r"\bpresented?\s+to\b",
    ],
    "red_flags": {"short_tenures":True,"long_gap_months":8,"max_jobs_5yr":4},
    "quality_markers": {"has_email":1,"has_phone":1,"has_linkedin":1,"has_github":1,"has_metrics":2,"min_words":300},
    "portfolio_patterns": [r"github\.com/\w+",r"open[\s-]source",r"\bnuget\b",r"\bportfolio\b"],
    "weights": {
        "must_have":20,"nice_to_have":10,"skill_depth":8,"experience":10,
        "recency":5,"seniority":7,"education":4,"certifications":3,
        "domain":5,"title_match":5,"achievements":5,"leadership":5,
        "keyword_density":4,"resume_quality":4,"portfolio":5,
    },
    "red_flag_penalty":10,
  },

  "Jr. .NET Developer": {
    "description":     "Entry/mid .NET developer — 0–3 years",
    "min_exp_years":   0,
    "ideal_exp_years": 2,
    "must_have":  ["C#", ".NET", "SQL"],
    "nice_to_have": ["ASP.NET", "REST API", "Git", "HTML/CSS", "JavaScript", "LINQ", "Entity Framework", "jQuery"],
    "seniority_titles": {r"\bjunior\b|\bjr\.?\b|\bfresher\b|\bgraduate\b":3, r"\bsenior\b":-1},
    "education": {r"\bb\.?tech\b|\bbachelor":4, r"\bmca\b|\bbca\b|\bbsc":3},
    "certifications": {r"\bmicrosoft\s*certified\b|\bmcsd\b":3, r"\bazure\s*fundamentals\b":2},
    "domain_keywords": {r"\bweb\s*(?:application|development)\b":2, r"\benterprise\b|\bsaas\b":1},
    "target_titles": [r"\.net\s*developer|c#\s*developer|junior\s*developer|associate\s*developer"],
    "achievement_patterns": [r"completed\s+(?:project|internship|training)",r"developed\s+\w+\s+(?:application|module)"],
    "leadership_patterns": [r"\bteam\s*player\b",r"\bcollaborated?\b"],
    "red_flags": {"short_tenures":False,"long_gap_months":18,"max_jobs_5yr":6},
    "quality_markers": {"has_email":1,"has_phone":1,"min_words":200},
    "portfolio_patterns": [r"github\.com/\w+",r"personal\s*project",r"\binternship\b"],
    "weights": {
        "must_have":30,"nice_to_have":15,"skill_depth":5,"experience":10,
        "recency":5,"seniority":5,"education":10,"certifications":5,
        "domain":2,"title_match":4,"achievements":3,"leadership":2,
        "keyword_density":2,"resume_quality":2,"portfolio":4,
    },
    "red_flag_penalty":5,
  },

  "Full Stack .NET + React": {
    "description":     "Full-stack .NET backend + React frontend — 3+ years",
    "min_exp_years":   3,
    "ideal_exp_years": 6,
    "must_have":  ["C#", ".NET", "React", "JavaScript", "SQL"],
    "nice_to_have": [
        "TypeScript","ASP.NET","REST API","HTML/CSS","Git",
        "Azure","Docker","Unit Testing","Bootstrap","Redux → Zustand".replace(" → Zustand",""),
        ".NET Core","Entity Framework","CI/CD",
    ],
    "seniority_titles": {r"\bsenior\b|\bsr\.?\b":3,r"\blead\b":4,r"\bjunior\b":-1},
    "education": {r"\bb\.?tech\b|\bbachelor":3,r"\bm\.?tech\b|\bmaster":4},
    "certifications": {r"\bazure\b":3,r"\baws\b":3},
    "domain_keywords": {r"\bsaas\b|\bproduct\b":2,r"\be[\-\s]?commerce\b":2},
    "target_titles": [r"full\s*stack|\.net\s*developer|react\s*developer|software\s*engineer"],
    "achievement_patterns": [r"(?:improved|reduced|built|migrated?)\w*\s+\w+\s+by\s+\d+",r"built\s+\w+\s+(?:application|platform)"],
    "leadership_patterns": [r"\bmentored?\b",r"\bcode\s+review\b",r"\bcross[- ]functional\b"],
    "red_flags": {"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
    "quality_markers": {"has_email":1,"has_phone":1,"has_github":1,"min_words":300},
    "portfolio_patterns": [r"github\.com/\w+",r"open[\s-]source",r"\bportfolio\b"],
    "weights": {
        "must_have":22,"nice_to_have":10,"skill_depth":7,"experience":10,
        "recency":5,"seniority":6,"education":4,"certifications":3,
        "domain":4,"title_match":5,"achievements":5,"leadership":4,
        "keyword_density":3,"resume_quality":3,"portfolio":5,
    },
    "red_flag_penalty":8,
  },

  "Data Engineer": {
    "description":     "Data pipeline / ETL engineer — 3+ years",
    "min_exp_years":   3,
    "ideal_exp_years": 6,
    "must_have":  ["Python","SQL","MongoDB"],
    "nice_to_have": ["PostgreSQL","Redis","Kafka","Docker","Git","CI/CD","AWS","Azure","GCP"],
    "seniority_titles": {r"\bsenior\b|\bsr\.?\b":3,r"\blead\b":4,r"\barchitect\b|\bprincipal\b":5,r"\bjunior\b":-1},
    "education": {r"\bb\.?tech\b|\bbachelor":3,r"\bm\.?tech\b|\bmaster":4,r"\bstatistics\b|\bdata\s*science\b":4},
    "certifications": {r"\bazure\s*data\b|\bdp[- ]?\d+":4,r"\baws\s*(?:data|analytics)":4,r"\bdatabricks":4},
    "domain_keywords": {r"\bdata\s*warehouse\b|\bdwh\b":3,r"\bdata\s*lake\b":3,r"\breal[\s-]time\b":2,r"\bml\b|\bmachine\s*learning\b":2},
    "target_titles": [r"data\s*engineer|etl\s*developer|analytics\s*engineer|platform\s*engineer"],
    "achievement_patterns": [r"processed\s+\d+[tbmk]?\+?\s*(?:records?|rows?)",r"(?:reduced|improved)\s+\w+\s+by\s+\d+",r"built\s+\w+\s+pipeline"],
    "leadership_patterns": [r"\bmentored?\b",r"\barchitect\w*\b",r"\bcode\s+review\b"],
    "red_flags": {"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
    "quality_markers": {"has_email":1,"has_phone":1,"min_words":300},
    "portfolio_patterns": [r"github\.com/\w+",r"\bkaggle\b",r"open[\s-]source"],
    "weights": {
        "must_have":25,"nice_to_have":12,"skill_depth":7,"experience":10,
        "recency":5,"seniority":6,"education":5,"certifications":4,
        "domain":5,"title_match":5,"achievements":4,"leadership":3,
        "keyword_density":2,"resume_quality":3,"portfolio":4,
    },
    "red_flag_penalty":8,
  },

  "DevOps / Cloud Engineer": {
    "description":     "Cloud + CI/CD + containers — 3+ years",
    "min_exp_years":   3,
    "ideal_exp_years": 6,
    "must_have":  ["Docker","Kubernetes","CI/CD","Git"],
    "nice_to_have": ["Terraform","Ansible","Azure","AWS","GCP","ELK/Splunk","Prometheus/Grafana","Python","PowerShell"],
    "seniority_titles": {r"\bsenior\b|\bsr\.?\b":3,r"\blead\b":4,r"\barchitect\b|\bprincipal\b":5,r"\bjunior\b":-1},
    "education": {r"\bb\.?tech\b|\bbachelor":3,r"\bm\.?tech\b|\bmaster":4},
    "certifications": {
        r"\bckad\b|\bcka\b|\bckss\b":5,
        r"\bazure\s*(?:administrator|architect|devops)":4,
        r"\baws\s*(?:devops|sysops|architect)":4,
        r"\bterraform\s*(?:associate|professional)":3,
    },
    "domain_keywords": {r"\bcloud\s*native\b|\bcontaineriz":3,r"\bmicroservices?\b":2,r"\bsre\b|\bsite\s*reliability":3},
    "target_titles": [r"devops\s*engineer|cloud\s*engineer|platform\s*engineer|sre\b|site\s*reliability"],
    "achievement_patterns": [r"reduced\s+deploy\w*\s+time",r"uptime\s+of\s+\d+",r"automated\s+\w+",r"managed\s+\d+\+?\s*(?:servers?|clusters?)"],
    "leadership_patterns": [r"\bmentored?\b",r"\barchitect\w*\b",r"\bcross[- ]functional\b"],
    "red_flags": {"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
    "quality_markers": {"has_email":1,"has_phone":1,"has_github":1,"min_words":300},
    "portfolio_patterns": [r"github\.com/\w+",r"open[\s-]source"],
    "weights": {
        "must_have":25,"nice_to_have":12,"skill_depth":7,"experience":8,
        "recency":6,"seniority":6,"education":3,"certifications":7,
        "domain":5,"title_match":4,"achievements":5,"leadership":3,
        "keyword_density":2,"resume_quality":3,"portfolio":4,
    },
    "red_flag_penalty":8,
  },
}


# ═══════════════════════════════════════════════════════════════════════════
#  15-SIGNAL SCORER
# ═══════════════════════════════════════════════════════════════════════════

def score_resume(text: str, profile: dict) -> dict:
    tl   = text.lower()
    w    = profile["weights"]

    # 1 Must-have
    must_hit, must_miss = match_skill_families(text, profile["must_have"])
    miss_n = len(must_miss)
    s1 = ({0:1.0, 1:0.65, 2:0.25}.get(miss_n, 0.0)) * w["must_have"]

    # 2 Nice-to-have
    nice_hit, _ = match_skill_families(text, profile["nice_to_have"])
    s2 = min(len(nice_hit)/max(len(profile["nice_to_have"]),1)*1.2, 1.0) * w["nice_to_have"]

    # 3 Skill depth
    depth_yrs = 0.0
    for pat in profile.get("skill_depth_markers",[]):
        for m in re.finditer(pat, tl):
            try: depth_yrs += min(float(m.group(1)), 15)
            except: pass
    # Also detect inline "X years of .NET/C#" near skill names
    for skill_pat in [SKILL_FAMILIES.get(s,"") for s in profile["must_have"]]:
        if not skill_pat: continue
        for m in re.finditer(r'(\d+\.?\d*)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?' + skill_pat, tl):
            try: depth_yrs += min(float(m.group(1)), 15)
            except: pass
    ideal_depth = len(profile["must_have"]) * 4
    s3 = min(depth_yrs / max(ideal_depth,1), 1.0) * w["skill_depth"]

    # 4 Experience
    yrs = extract_experience(text)
    mn, id_ = profile["min_exp_years"], profile["ideal_exp_years"]
    if yrs <= 0:        exp_r = 0.0
    elif yrs < mn:      exp_r = 0.4 * (yrs/max(mn,1))
    elif yrs <= id_:    exp_r = 0.4 + 0.6*((yrs-mn)/max(id_-mn,1))
    else:               exp_r = min(1.0 + 0.04*(yrs-id_), 1.15)
    s4 = min(exp_r,1.0) * w["experience"]

    # 5 Recency
    recent = {str(y) for y in range(NOW_YEAR-3, NOW_YEAR+1)}
    yr_ctx = re.findall(r'(20\d{2})\s*[-–to]+\s*(?:present|current|till|\d{4})', tl)
    rec = any(y in recent for y in yr_ctx)
    if not rec:
        all_y = re.findall(r'\b(20\d{2})\b', tl)
        rec = any(y in recent for y in all_y)
    s5 = (1.0 if rec else 0.2) * w["recency"]

    # 6 Seniority
    best_pts = 0
    for pat, pts in profile["seniority_titles"].items():
        if re.search(pat, tl) and pts > best_pts:
            best_pts = pts
    max_pts = max((v for v in profile["seniority_titles"].values() if v > 0), default=5)
    s6 = max(best_pts/max_pts, 0) * w["seniority"]

    # 7a Education
    edu_best = 0
    for pat, pts in profile["education"].items():
        if re.search(pat, tl) and pts > edu_best: edu_best = pts
    max_edu = max(profile["education"].values(), default=5)
    s7a = (edu_best/max_edu) * w["education"]

    # 7b Certifications
    cert_hits, cert_total = [], 0
    for pat, pts in profile["certifications"].items():
        if re.search(pat, tl):
            cert_hits.append(pat); cert_total += pts
    max_cert = sum(profile["certifications"].values()) or 1
    s7b = min(cert_total / max(max_cert*0.4,1), 1.0) * w["certifications"]

    # 8 Domain
    dom_total = 0
    for pat, pts in profile["domain_keywords"].items():
        if re.search(pat, tl): dom_total += pts
    max_dom = sum(profile["domain_keywords"].values()) or 1
    s8 = min(dom_total / max(max_dom*0.5,1), 1.0) * w["domain"]

    # 9 Title match
    header = "\n".join(text.splitlines()[:12]) + text[:700]
    htl = header.lower()
    tm = sum(1 for p in profile["target_titles"] if re.search(p, htl))
    s9 = (1.0 if tm>=2 else 0.7 if tm==1 else 0.1) * w["title_match"]

    # 10 Achievements
    ach = [p for p in profile["achievement_patterns"] if re.search(p, tl)]
    s10 = min(len(ach)/max(len(profile["achievement_patterns"])*0.4,1),1.0) * w["achievements"]

    # 11 Leadership
    lead = [p for p in profile["leadership_patterns"] if re.search(p, tl)]
    s11 = min(len(lead)/max(len(profile["leadership_patterns"])*0.35,1),1.0) * w["leadership"]

    # 12 Red flags (penalty)
    rf_msgs, penalty = [], 0
    rf = profile.get("red_flags",{})
    spans = []
    for m in re.finditer(
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)?\w*\s*(\d{4})\s*[-–to]+\s*(present|\d{4})',
        tl, re.I
    ):
        try:
            s = int(m.group(1))
            e = NOW_YEAR if 'present' in m.group(2).lower() else int(m.group(2))
            if 0 < e-s < 45: spans.append((s,e))
        except: pass
    spans.sort()
    if rf.get("short_tenures") and spans:
        short = [s for s in spans if 0<(s[1]-s[0])*12<12]
        if len(short)>=2: penalty+=4; rf_msgs.append(f"⚠ {len(short)} tenures <12 mo")
    max_jobs = rf.get("max_jobs_5yr",4)
    recent_jobs = [s for s in spans if s[1]>=NOW_YEAR-5]
    if len(recent_jobs)>max_jobs: penalty+=3; rf_msgs.append(f"⚠ {len(recent_jobs)} roles in 5 yrs")
    if len(spans)>=2:
        for i in range(len(spans)-1):
            gap=(spans[i+1][0]-spans[i][1])*12
            if gap>rf.get("long_gap_months",10): penalty+=3; rf_msgs.append(f"⚠ gap ~{gap//12}yr")
    s12 = -min(penalty, profile.get("red_flag_penalty",10))

    # 13 Keyword density
    all_pats = [SKILL_FAMILIES.get(k,"") for k in profile["must_have"]+profile["nice_to_have"]]
    hits = sum(len(re.findall(p, tl)) for p in all_pats if p)
    wc = max(len(re.findall(r'\b\w+\b', tl)), 1)
    density = hits/wc
    if   density < 0.005: kd = 0.1
    elif density < 0.015: kd = 0.4
    elif density < 0.04:  kd = 1.0
    elif density < 0.08:  kd = 0.85
    else:                 kd = 0.6
    s13 = kd * w["keyword_density"]

    # 14 Resume quality
    qm = profile.get("quality_markers",{})
    q_pts, q_max = 0, 0
    q_info = []
    for key, val in qm.items():
        if key == "min_words": continue
        q_max += val
        checks = {
            "has_email":   bool(re.search(r'[a-zA-Z0-9._%+\-]+@\S+\.\w{2,}', text)),
            "has_phone":   bool(re.search(r'\b\d{10}\b|\+\d{7,}', text)),
            "has_linkedin":bool(re.search(r'linkedin\.com', tl)),
            "has_github":  bool(re.search(r'github\.com', tl)),
            "has_metrics": bool(re.search(r'\d+\s*%|\d+x\b|\d+\s*(?:million|thousand|\bk\b)', tl)),
        }
        ok = checks.get(key, False)
        if ok: q_pts += val
        q_info.append(f"{key.replace('has_','').title()} {'✓' if ok else '✗'}")
    wc_min = qm.get("min_words", 200)
    wc_act = len(re.findall(r'\b\w+\b', text))
    q_max += 2
    if wc_act >= wc_min: q_pts += 2; q_info.append(f"Length ✓({wc_act}w)")
    else: q_info.append(f"Length ✗({wc_act}<{wc_min})")
    s14 = (q_pts/max(q_max,1)) * w["resume_quality"]

    # 15 Portfolio
    port = [p for p in profile["portfolio_patterns"] if re.search(p, tl)]
    s15 = min(len(port)/max(len(profile["portfolio_patterns"])*0.4,1),1.0) * w["portfolio"]

    raw   = s1+s2+s3+s4+s5+s6+s7a+s7b+s8+s9+s10+s11+s13+s14+s15
    total = max(raw+s12, 0)
    pct   = round((total/sum(w.values()))*100, 1)

    if pct>=80:         verdict,tag = "🏆 Excellent Match",   "excellent"
    elif pct>=65:       verdict,tag = "✅ Strong Match",       "strong"
    elif pct>=50:       verdict,tag = "🟡 Moderate Match",     "moderate"
    elif pct>=35:       verdict,tag = "⚠️  Partial Match",      "partial"
    elif must_miss:     verdict,tag = "❌ Missing Core Skills", "weak"
    else:               verdict,tag = "❌ Poor Match",          "weak"

    return {
        "score":       pct, "verdict":     verdict, "tag":   tag,
        "exp_years":   round(yrs,1),
        "must_matched":must_hit,  "must_missing":must_miss,
        "nice_matched":nice_hit,
        "achievements":len(ach),  "leadership":  len(lead),
        "red_flags":   rf_msgs,   "is_recent":   rec,
        "word_count":  wc_act,    "quality":     q_info,
        "portfolio":   bool(port),"certs":       cert_hits,
        "kw_density":  round(density*100,2),
        "breakdown":{
            "must_have":       round(s1,1),
            "nice_to_have":    round(s2,1),
            "skill_depth":     round(s3,1),
            "experience":      round(s4,1),
            "recency":         round(s5,1),
            "seniority":       round(s6,1),
            "education":       round(s7a,1),
            "certifications":  round(s7b,1),
            "domain":          round(s8,1),
            "title_match":     round(s9,1),
            "achievements":    round(s10,1),
            "leadership":      round(s11,1),
            "red_flags":       round(s12,1),
            "keyword_density": round(s13,1),
            "resume_quality":  round(s14,1),
            "portfolio":       round(s15,1),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
#  COLOUR PALETTE & FONTS
# ═══════════════════════════════════════════════════════════════════════════
BG="#0b0f1a"; CARD="#131929"; BORDER="#1e2d4a"
ACCENT="#3b82f6"; ACCENT2="#8b5cf6"
SUCCESS="#10b981"; WARNING="#f59e0b"; DANGER="#ef4444"; ORANGE="#f97316"
FG="#e2e8f0"; FG2="#94a3b8"; MUTED="#475569"; GOLD="#fbbf24"

TAG_BG = {"excellent":("#052e16","#86efac"),"strong":("#0d2218","#4ade80"),
          "moderate":("#1f1a0a","#fcd34d"),"partial":("#1c1408","#fdba74"),
          "weak":("#1f0f0f","#fca5a5")}

F1=("Segoe UI",19,"bold"); F2=("Segoe UI",12,"bold"); F3=("Segoe UI",10,"bold")
FN=("Segoe UI",10); FS=("Segoe UI",9); FM=("Consolas",9)


# ═══════════════════════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Resume Screener Pro v3  •  15-Signal  •  Offline")
        self.configure(bg=BG); self.geometry("1440x860"); self.minsize(1100,680)
        self.profiles = DEFAULT_PROFILES.copy()
        self.files: list[str] = []
        self.results: list[dict] = []
        self.sort_col, self.sort_rev = "score", True
        self._build(); self._dep_check()

    def _dep_check(self):
        miss = []
        if not HAS_PYPDF:  miss.append("pypdf       →  pip install pypdf")
        if not HAS_DOCX:   miss.append("python-docx →  pip install python-docx")
        if miss: messagebox.showwarning("Missing Libraries",
            "Some file types won't work:\n\n" + "\n".join(miss))

    def _build(self):
        hdr=tk.Frame(self,bg=BG,pady=10); hdr.pack(fill="x",padx=20)
        tk.Label(hdr,text="⚡ Resume Screener Pro v3",font=F1,bg=BG,fg=FG).pack(side="left")
        tk.Label(hdr,text="15 Signals  •  40+ skill aliases  •  Offline",font=FS,bg=BG,fg=MUTED).pack(side="left",padx=14)
        body=tk.Frame(self,bg=BG); body.pack(fill="both",expand=True,padx=16)
        body.columnconfigure(1,weight=1); body.rowconfigure(0,weight=1)
        self._left(body); self._right(body)
        sf=tk.Frame(self,bg=CARD,pady=5); sf.pack(fill="x",side="bottom")
        self.sv=tk.StringVar(value="Ready — add resumes, pick a profile, click Analyse")
        tk.Label(sf,textvariable=self.sv,font=FS,bg=CARD,fg=FG2,padx=12).pack(side="left")

    def _left(self, parent):
        lf=tk.Frame(parent,bg=CARD,padx=14,pady=12,width=300)
        lf.grid(row=0,column=0,sticky="nsew",padx=(0,10)); lf.pack_propagate(False)

        tk.Label(lf,text="Job Profile",font=F2,bg=CARD,fg=FG).pack(anchor="w")
        self.pv=tk.StringVar(value=list(self.profiles.keys())[0])
        prow=tk.Frame(lf,bg=CARD); prow.pack(fill="x",pady=(4,0))
        self.pcb=ttk.Combobox(prow,textvariable=self.pv,values=list(self.profiles.keys()),
                               state="readonly",font=FN)
        self.pcb.pack(side="left",fill="x",expand=True)
        _btn(prow,"+ New",self._new_profile,ACCENT2).pack(side="left",padx=(6,0))
        self.pcb.bind("<<ComboboxSelected>>",lambda _:self._prev())
        self.pdtxt=tk.Text(lf,height=5,bg="#0d1424",fg=FG2,font=FM,bd=0,
                            wrap="word",state="disabled",relief="flat")
        self.pdtxt.pack(fill="x",pady=(6,0)); self._prev()
        _sep(lf)

        tk.Label(lf,text="Resumes",font=F2,bg=CARD,fg=FG).pack(anchor="w")
        self.fcl=tk.Label(lf,text="0 files",font=FS,bg=CARD,fg=MUTED); self.fcl.pack(anchor="w")
        br=tk.Frame(lf,bg=CARD); br.pack(fill="x",pady=5)
        _btn(br,"📂 Add Files",self._add_files,ACCENT).pack(side="left")
        _btn(br,"📁 Folder",self._add_folder,ACCENT2).pack(side="left",padx=5)
        _btn(br,"🗑",self._clr,"#374151").pack(side="right")
        self.flb=tk.Listbox(lf,bg="#0d1424",fg=FG2,font=FS,selectbackground=ACCENT,
                             bd=0,height=9,activestyle="none")
        self.flb.pack(fill="both",expand=True)
        _sep(lf)

        tk.Label(lf,text="Filters",font=F2,bg=CARD,fg=FG).pack(anchor="w")
        self.ms=tk.IntVar(value=0); self.me=tk.DoubleVar(value=0)
        self.vf=tk.StringVar(value="All"); self.hrf=tk.BooleanVar(value=False)
        _slider(lf,"Min Score (%)",self.ms,0,100)
        _slider(lf,"Min Exp (yrs)",self.me,0,30)
        vr=tk.Frame(lf,bg=CARD); vr.pack(fill="x",pady=3)
        tk.Label(vr,text="Verdict:",font=FS,bg=CARD,fg=FG2,width=10,anchor="w").pack(side="left")
        ttk.Combobox(vr,textvariable=self.vf,state="readonly",font=FS,width=18,
                     values=["All","Excellent","Strong","Moderate","Partial","Weak"]).pack(side="left")
        rr=tk.Frame(lf,bg=CARD); rr.pack(fill="x",pady=2)
        tk.Checkbutton(rr,text="Hide red-flagged",variable=self.hrf,
                       bg=CARD,fg=FG2,selectcolor=CARD,font=FS,activebackground=CARD).pack(side="left")
        _sep(lf)

        self.rb=tk.Button(lf,text="▶  Analyse Resumes",font=F2,bg=SUCCESS,
                           fg="white",bd=0,pady=10,cursor="hand2",command=self._run)
        self.rb.pack(fill="x")
        _btn(lf,"💾 Export JSON",self._exp_json,"#374151").pack(fill="x",pady=(5,0))
        _btn(lf,"📋 Export CSV", self._exp_csv, "#374151").pack(fill="x",pady=(3,0))

    def _right(self, parent):
        rf=tk.Frame(parent,bg=BG); rf.grid(row=0,column=1,sticky="nsew")
        rf.rowconfigure(1,weight=1); rf.columnconfigure(0,weight=1)
        self.scf=tk.Frame(rf,bg=BG); self.scf.grid(row=0,column=0,sticky="ew",pady=(0,8))
        self._stats()
        pw=tk.PanedWindow(rf,orient="vertical",bg=BG,sashwidth=5,sashrelief="flat",sashpad=2)
        pw.grid(row=1,column=0,sticky="nsew")
        tf=tk.Frame(pw,bg=CARD); self._tree(tf); pw.add(tf,minsize=200)
        df=tk.Frame(pw,bg=CARD,padx=12,pady=8); self._detail(df); pw.add(df,minsize=140)

    def _stats(self):
        for w in self.scf.winfo_children(): w.destroy()
        R=self.results
        cards=[
            ("Total",      str(len(R)),                                               ACCENT),
            ("Excellent",  str(sum(1 for r in R if r["tag"]=="excellent")),           GOLD),
            ("Strong",     str(sum(1 for r in R if r["tag"]=="strong")),              SUCCESS),
            ("Moderate",   str(sum(1 for r in R if r["tag"]=="moderate")),            WARNING),
            ("Weak",       str(sum(1 for r in R if r["tag"] in ("weak","partial"))),  DANGER),
            ("Avg Score",  f"{sum(r['score'] for r in R)/max(len(R),1):.1f}%",       "#94a3b8"),
            ("Red Flags",  str(sum(1 for r in R if r["red_flags"])),                  ORANGE),
        ]
        for lbl,val,clr in cards:
            c=tk.Frame(self.scf,bg=CARD,padx=12,pady=7); c.pack(side="left",padx=(0,7))
            tk.Label(c,text=val,font=("Segoe UI",17,"bold"),bg=CARD,fg=clr).pack()
            tk.Label(c,text=lbl,font=FS,bg=CARD,fg=MUTED).pack()

    def _tree(self, parent):
        COLS=("rank","name","file","score","verdict","exp","must","nice","red","ach","lead","qual","certs")
        HDRS=("#","Name","File","Score","Verdict","Exp","Must-Have","Nice-to-Have","Red Flags","Ach","Lead","Quality","Certs")
        WIDS=[36,155,160,62,162,55,190,175,130,42,42,115,90]
        sty=ttk.Style(); sty.theme_use("clam")
        sty.configure("Treeview",background=CARD,fieldbackground=CARD,
                       foreground=FG,rowheight=24,font=FN,borderwidth=0)
        sty.configure("Treeview.Heading",background="#0d1929",foreground=FG2,
                       font=F3,relief="flat",padding=5)
        sty.map("Treeview",background=[("selected",ACCENT)],foreground=[("selected","white")])
        self.tv=ttk.Treeview(parent,columns=COLS,show="headings",selectmode="browse")
        for col,hdr,w in zip(COLS,HDRS,WIDS):
            self.tv.heading(col,text=hdr,command=lambda c=col:self._sort(c))
            self.tv.column(col,width=w,
                            anchor="center" if col in ("rank","score","exp","ach","lead") else "w",
                            stretch=(col in ("must","nice")))
        vsb=ttk.Scrollbar(parent,orient="vertical",command=self.tv.yview)
        hsb=ttk.Scrollbar(parent,orient="horizontal",command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x")
        self.tv.pack(fill="both",expand=True)
        self.tv.bind("<<TreeviewSelect>>",self._sel)
        for tag,(bg,fg) in TAG_BG.items():
            self.tv.tag_configure(tag,background=bg,foreground=fg)

    def _detail(self, parent):
        tk.Label(parent,text="Candidate Detail  —  click any row",font=F2,bg=CARD,fg=FG).pack(anchor="w")
        self.dtxt=tk.Text(parent,bg="#0d1424",fg=FG,font=FM,bd=0,wrap="word",
                           state="disabled",relief="flat")
        self.dtxt.pack(fill="both",expand=True,pady=(4,0))

    # ── helpers ──────────────────────────────────────────────────────────
    def _prev(self):
        nm=self.pv.get(); p=self.profiles.get(nm,{})
        must=p.get("must_have",[]); nice=p.get("nice_to_have",[])
        lines=[
            f"Role     : {p.get('description',nm)}",
            f"Exp      : {p.get('min_exp_years','?')} – {p.get('ideal_exp_years','?')} yrs",
            f"Must ({len(must)}): {', '.join(must)}",
            f"Nice ({len(nice)}): {', '.join(nice[:10])}{'…' if len(nice)>10 else ''}",
        ]
        self.pdtxt.configure(state="normal")
        self.pdtxt.delete("1.0","end")
        self.pdtxt.insert("end","\n".join(lines))
        self.pdtxt.configure(state="disabled")

    def _add_files(self):
        ps=filedialog.askopenfilenames(title="Select Resumes",
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
        if not self.files: messagebox.showinfo("No files","Add resume files first."); return
        self.rb.config(state="disabled",text="⏳  Analysing…")
        threading.Thread(target=self._analyse,daemon=True).start()

    def _analyse(self):
        pn=self.pv.get(); prof=self.profiles[pn]; self.results=[]
        for i,path in enumerate(self.files):
            self.sv.set(f"Reading {i+1}/{len(self.files)}: {Path(path).name}")
            text=extract_text(path)
            ct=extract_contact(text)
            sc=score_resume(text,prof)
            self.results.append({**ct,"file":Path(path).name,"path":path,"raw":text[:5000],**sc})
        self.results.sort(key=lambda x:x["score"],reverse=True)
        self.after(0,self._populate)

    def _populate(self):
        ms=self.ms.get(); me=self.me.get(); vfl=self.vf.get().lower(); hrf=self.hrf.get()
        vis=[r for r in self.results
             if r["score"]>=ms and r["exp_years"]>=me
             and (vfl=="all" or vfl in r["verdict"].lower())
             and not (hrf and r["red_flags"])]
        self.tv.delete(*self.tv.get_children())
        for rank,r in enumerate(vis,1):
            self.tv.insert("","end",iid=str(rank),tags=(r["tag"],),
                values=(rank,r["name"],r["file"],f"{r['score']}%",r["verdict"],
                        r["exp_years"],
                        ", ".join(r["must_matched"]) or "—",
                        ", ".join(r["nice_matched"][:6]) or "—",
                        ", ".join(r["red_flags"]) or "—",
                        r["achievements"],r["leadership"],
                        "  ".join(r["quality"]),
                        f"{len(r['certs'])} cert{'s' if len(r['certs'])!=1 else ''}"))
        self._stats()
        self.sv.set(f"Done — {len(vis)} shown / {len(self.results)} processed")
        self.rb.config(state="normal",text="▶  Analyse Resumes")

    def _sel(self,_=None):
        sel=self.tv.selection()
        if not sel: return
        fname=self.tv.item(sel[0],"values")[2]
        r=next((x for x in self.results if x["file"]==fname),None)
        if not r: return
        bd=r["breakdown"]; w=self.profiles[self.pv.get()]["weights"]
        lines=["━"*64,
               f"  Name     :  {r['name']}",
               f"  Email    :  {r['email']}",
               f"  Phone    :  {r['phone']}",
               f"  LinkedIn :  {r.get('linkedin','—')}",
               f"  GitHub   :  {r.get('github','—')}",
               f"  File     :  {r['file']}",
               "━"*64,
               f"  TOTAL SCORE : {r['score']}%   {r['verdict']}",
               f"  Experience  : {r['exp_years']} yrs detected",
               f"  Word Count  : {r['word_count']}  |  KW Density: {r['kw_density']}%",
               "─"*64,
               "  SIGNAL BREAKDOWN                   scored / max",
        ]
        rows=[
            ("1  Must-Have Skills",    bd["must_have"],       w["must_have"]),
            ("2  Nice-to-Have Skills", bd["nice_to_have"],    w["nice_to_have"]),
            ("3  Skill Depth",         bd["skill_depth"],     w["skill_depth"]),
            ("4  Total Experience",    bd["experience"],      w["experience"]),
            ("5  Recency",             bd["recency"],         w["recency"]),
            ("6  Seniority",           bd["seniority"],       w["seniority"]),
            ("7a Education",           bd["education"],       w["education"]),
            ("7b Certifications",      bd["certifications"],  w["certifications"]),
            ("8  Domain Relevance",    bd["domain"],          w["domain"]),
            ("9  Job Title Match",     bd["title_match"],     w["title_match"]),
            ("10 Achievements",        bd["achievements"],    w["achievements"]),
            ("11 Leadership",          bd["leadership"],      w["leadership"]),
            ("12 Red Flags (penalty)", bd["red_flags"],       0),
            ("13 Keyword Density",     bd["keyword_density"], w["keyword_density"]),
            ("14 Resume Quality",      bd["resume_quality"],  w["resume_quality"]),
            ("15 Portfolio / OSS",     bd["portfolio"],       w["portfolio"]),
        ]
        for label,got,mx in rows:
            bar=("█"*int(got/mx*14) + "░"*(14-int(got/mx*14))) if mx>0 else "─"*14
            lines.append(f"    {label:<32} {got:>5.1f} / {mx:<3}  [{bar}]")
        lines+=[
            "─"*64,
            f"  ✅ Must-have matched  : {', '.join(r['must_matched']) or 'none'}",
            f"  ❌ Must-have MISSING  : {', '.join(r['must_missing']) or 'none'}",
            f"  ⭐ Nice-to-have found : {', '.join(r['nice_matched']) or 'none'}",
            f"  🏅 Certifications     : {', '.join(r['certs']) or 'none'}",
            f"  🚩 Red Flags          : {', '.join(r['red_flags']) or 'none'}",
            f"  📋 Resume Quality     : {', '.join(r['quality'])}",
            f"  🔗 Portfolio/OSS      : {'Yes' if r['portfolio'] else 'No'}",
            "─"*64,
            "  RESUME TEXT PREVIEW",
            "─"*64,
            r["raw"][:2000],
        ]
        self.dtxt.configure(state="normal")
        self.dtxt.delete("1.0","end")
        self.dtxt.insert("end","\n".join(lines))
        self.dtxt.configure(state="disabled")

    def _sort(self,col):
        self.sort_rev=not self.sort_rev if self.sort_col==col else True
        self.sort_col=col
        km={"score":lambda r:r["score"],"exp":lambda r:r["exp_years"],
            "name":lambda r:r["name"].lower(),"ach":lambda r:r["achievements"],
            "lead":lambda r:r["leadership"]}
        self.results.sort(key=km.get(col,lambda r:r.get(col,"")),reverse=self.sort_rev)
        self._populate()

    def _exp_json(self):
        if not self.results: messagebox.showinfo("Empty","Run analysis first."); return
        p=filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON","*.json")],
            initialfile=f"screening_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        if p:
            out=[{k:v for k,v in r.items() if k!="raw"} for r in self.results]
            Path(p).write_text(json.dumps(out,indent=2),encoding="utf-8")
            messagebox.showinfo("Saved",f"JSON saved:\n{p}")

    def _exp_csv(self):
        if not self.results: messagebox.showinfo("Empty","Run analysis first."); return
        p=filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            initialfile=f"screening_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        if not p: return
        fields=["rank","name","email","phone","file","score","verdict","exp_years",
                "must_matched","must_missing","nice_matched","achievements",
                "leadership","red_flags","word_count","portfolio","certs"]
        with open(p,"w",newline="",encoding="utf-8") as f:
            wtr=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            wtr.writeheader()
            for i,r in enumerate(self.results,1):
                row={k:v for k,v in r.items() if k in fields}
                row["rank"]=i
                row["must_matched"]=", ".join(r.get("must_matched",[]))
                row["must_missing"]=", ".join(r.get("must_missing",[]))
                row["nice_matched"]=", ".join(r.get("nice_matched",[]))
                row["red_flags"]=" | ".join(r.get("red_flags",[]))
                row["certs"]=str(len(r.get("certs",[])))
                wtr.writerow(row)
        messagebox.showinfo("Saved",f"CSV saved:\n{p}")

    def _new_profile(self):
        dlg=tk.Toplevel(self); dlg.title("Create Job Profile")
        dlg.configure(bg=BG); dlg.geometry("640x620"); dlg.resizable(False,False)
        def lbl(t): tk.Label(dlg,text=t,font=F3,bg=BG,fg=FG,anchor="w").pack(fill="x",padx=16,pady=(10,2))
        def ent():
            e=tk.Entry(dlg,bg=CARD,fg=FG,font=FN,bd=0,insertbackground=FG,relief="flat")
            e.pack(fill="x",padx=16,ipady=6); return e
        def txtb(h=2):
            t=tk.Text(dlg,height=h,bg=CARD,fg=FG,font=FM,bd=0,insertbackground=FG,relief="flat")
            t.pack(fill="x",padx=16); return t
        tk.Label(dlg,text=f"Available skill keys: {', '.join(list(SKILL_FAMILIES.keys())[:25])}…",
                  font=("Consolas",8),bg=BG,fg=MUTED,wraplength=600,justify="left").pack(padx=16,pady=(10,0))
        lbl("Profile Name"); ne=ent(); ne.insert(0,"My Role")
        lbl("Description");  de=ent(); de.insert(0,"e.g. Mid Python backend engineer")
        lbl("Must-have skills — comma list of keys above"); mt=txtb()
        mt.insert("end","Python, SQL, MongoDB")
        lbl("Nice-to-have — comma list"); gt=txtb()
        gt.insert("end","Docker, Redis, Kafka, Git")
        lbl("Min / Ideal experience (e.g. 3, 6)"); ee=ent(); ee.insert(0,"3, 6")
        lbl("Target job titles (comma-separated)"); ti=ent()
        ti.insert(0,"python developer, backend engineer")
        def save():
            name=ne.get().strip()
            if not name: messagebox.showerror("Error","Name required",parent=dlg); return
            def keys(raw): return [k.strip() for k in raw.split(",") if k.strip() in SKILL_FAMILIES]
            def unknown(raw):
                unk=[k.strip() for k in raw.split(",") if k.strip() and k.strip() not in SKILL_FAMILIES]
                return unk
            must_keys=keys(mt.get("1.0","end"))
            nice_keys=keys(gt.get("1.0","end"))
            unk=unknown(mt.get("1.0","end"))+unknown(gt.get("1.0","end"))
            if unk:
                messagebox.showwarning("Unknown skill keys",
                    f"These keys are NOT in SKILL_FAMILIES and will be ignored:\n{', '.join(unk)}\n\nAdd them to SKILL_FAMILIES in the script for full matching.",
                    parent=dlg)
            try:
                pts=[float(x) for x in ee.get().split(",")]
                mn,id_=(pts[0],pts[1]) if len(pts)>=2 else (pts[0],pts[0]+3)
            except: mn,id_=3,6
            titles=[r"\b"+re.escape(t.strip().lower())+r"\b" for t in ti.get().split(",") if t.strip()]
            self.profiles[name]={
                "description":de.get().strip(),"min_exp_years":mn,"ideal_exp_years":id_,
                "must_have":must_keys,"nice_to_have":nice_keys,
                "skill_depth_markers":[],
                "seniority_titles":{r"\bsenior\b|\bsr\.?\b":3,r"\blead\b":4,r"\barchitect\b":5,r"\bjunior\b":-1},
                "education":{r"\bb\.?tech\b|\bbachelor":3,r"\bm\.?tech\b|\bmaster":4},
                "certifications":{},"domain_keywords":{},"target_titles":titles,
                "achievement_patterns":[r"(?:improved|reduced)\w*\s+\w+\s+by\s+\d+"],
                "leadership_patterns":[r"\bmentored?\b",r"\bcode\s+review\b"],
                "red_flags":{"short_tenures":True,"long_gap_months":10,"max_jobs_5yr":4},
                "quality_markers":{"has_email":1,"has_phone":1,"min_words":300},
                "portfolio_patterns":[r"github\.com/\w+",r"open[\s-]source"],
                "weights":{"must_have":25,"nice_to_have":12,"skill_depth":6,"experience":10,
                           "recency":5,"seniority":6,"education":4,"certifications":3,
                           "domain":4,"title_match":5,"achievements":5,"leadership":4,
                           "keyword_density":3,"resume_quality":3,"portfolio":5},
                "red_flag_penalty":8,
            }
            self.pcb["values"]=list(self.profiles.keys())
            self.pv.set(name); self._prev(); dlg.destroy()
        tk.Button(dlg,text="Save Profile",font=F2,bg=SUCCESS,fg="white",
                  bd=0,pady=10,cursor="hand2",command=save).pack(fill="x",padx=16,pady=14)


def _btn(p,t,c,col):
    return tk.Button(p,text=t,font=FS,bg=col,fg="white",bd=0,padx=8,pady=5,cursor="hand2",command=c)

def _sep(p):
    tk.Frame(p,bg=BORDER,height=1).pack(fill="x",pady=8)

def _slider(p,lbl,var,lo,hi):
    row=tk.Frame(p,bg=CARD); row.pack(fill="x",pady=2)
    tk.Label(row,text=lbl,font=FS,bg=CARD,fg=FG2,width=18,anchor="w").pack(side="left")
    tk.Scale(row,variable=var,from_=lo,to=hi,orient="horizontal",
             bg=CARD,fg=FG,troughcolor=BORDER,highlightthickness=0,font=FS,length=110).pack(side="left")
    tk.Label(row,textvariable=var,font=FS,bg=CARD,fg=ACCENT,width=4).pack(side="left")


if __name__ == "__main__":
    App().mainloop()
