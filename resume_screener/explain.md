# resume_screener_v2.py

## Overview
`resume_screener_v2.py` is an **offline resume scoring application** that:
- Reads resumes from `.pdf`, `.docx`, `.doc`, and `.txt`
- Scores them against predefined job profiles
- Uses a **15-signal scoring engine**
- Displays results in an interactive **tkinter GUI**

---

## Main Structure

### 1. Imports and Setup
- **Standard libraries:** `os`, `re`, `json`, `math`, `threading`, `tkinter`, `pathlib`, `datetime`, `collections`
- **Optional imports:**
  - `pypdf` or fallback `PyPDF2` for PDF text extraction
  - `python-docx` for Word documents
- **Constant:** `NOW_YEAR = datetime.now().year`

---

### 2. Job Profiles: `DEFAULT_PROFILES`
Profiles define role templates with:
- Description
- Experience requirements (`min_exp_years`, `ideal_exp_years`)
- Regex patterns for:
  - Must-have skills
  - Nice-to-have skills
  - Skill depth markers
  - Seniority titles
  - Education
  - Certifications
  - Domain keywords
  - Target titles
  - Achievement patterns
  - Leadership patterns
  - Portfolio patterns
- Red-flag rules (`red_flags`)
- Quality markers (`quality_markers`)
- Weights for each scoring signal
- `red_flag_penalty`

**Example profile:** *Sr. .NET + SQL Engineer*

---

### 3. Text Extraction: `extract_text(path)`
- Reads resume text from:
  - **PDF** → `PdfReader`
  - **DOCX** → `DocxDocument`
  - **TXT** → plain text read
- Returns error placeholder if dependencies are missing or file type unsupported.

---

### 4. Score Signals (15 total)
Each signal analyzes resume text and contributes to the score.

- **sig_must_have(text, p)** → Required skills (missing skills heavily penalized)
- **sig_nice_to_have(text, p)** → Bonus skills (up to 120% ratio)
- **sig_skill_depth(text, p)** → Years of experience per skill
- **sig_experience(text, p)** → Explicit years or inferred from date ranges
- **sig_recency(text, p)** → Recent activity or "current" mentions
- **sig_seniority(text, p)** → Seniority-related titles
- **sig_education(text, p)** → Detects Bachelor, Master, PhD
- **sig_certifications(text, p)** → Matches certifications
- **sig_domain(text, p)** → Industry/domain keywords
- **sig_title_match(text, p)** → Checks resume titles
- **sig_achievements(text, p)** → Quantified achievements
- **sig_leadership(text, p)** → Leadership/mentorship phrases
- **sig_red_flags(text, p)** → Penalizes short tenures, gaps, too many roles
- **sig_keyword_density(text, p)** → Optimal keyword density (~2–4%)
- **sig_resume_quality(text, p)** → Contact info, LinkedIn, GitHub, metrics, word count
- **sig_portfolio(text, p)** → Portfolio/GitHub presence

---

### 5. Contact Extraction: `extract_contact(text)`
Identifies:
- Email
- Phone
- LinkedIn URL
- GitHub URL
- Candidate name (from top lines)

---

### 6. Master Scoring: `score_resume(text, profile)`
- Calls all `sig_*` functions
- Sums weighted scores
- Applies red-flag penalties
- Computes percentage based on profile weights
- Verdicts:
  - **Excellent Match** ≥ 80
  - **Strong Match** ≥ 65
  - **Moderate Match** ≥ 50
  - **Partial Match** ≥ 35
  - **Missing Core Skills** if must-have missing
  - Otherwise **Poor Match**

**Returns:**  
- Total score  
- Verdict & tag  
- Matched/missing skills  
- Experience years  
- Red flags  
- Quality details  
- Signal breakdown  

---

### 7. GUI
- Built with **tkinter**
- Features:
  - Profile selector
  - File list + drag/drop
  - Analysis button
  - Result table
  - Detail panel
  - Status bar
- Styled with custom colors, fonts, and cards.

---

### 8. Running the App
Run directly:
```bash
python resume_screener_v2.py
