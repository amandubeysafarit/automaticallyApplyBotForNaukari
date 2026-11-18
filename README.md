# Naukri-Autoapply-Bot (Shraddha Dwivedi Edition)

> Intelligent, automated job application bot for Naukri.com using **Selenium**, **Microsoft Edge**, and **Gemini AI**.
> Custom tailored for **Shraddha Dwivedi** to apply to relevant roles (OFSAA Developer, SQL Developer, PL/SQL Developer, Oracle Database Developer), filtering out irrelevant technologies and over-qualified roles, answering recruiter questionnaires with AI, capturing external company URLs, and maintaining exactly 2 clean CSV reports.

## 📋 Key Features

- ✅ **Single Command Execution** — Run `python Naukri-Edge.py` for end-to-end processing.
- ✅ **Smart Preference & Relevance Filtering**:
  - Targets OFSAA Developer, SQL Developer, PL/SQL Developer, Oracle Developer roles matching `.env` settings.
  - Automatically rejects unrelated stacks (PHP, Laravel, Mobile/Frontend-only, Sales, BPO, etc.).
  - Experience filter ensures you only apply to roles fitting your experience level (4 years exp, skips > 6-7 yrs).
  - Location filter respects `.env` (pan-India by default, or specific cities / remote).
- ✅ **Recruiter Chatbot Auto-Answering with Gemini AI**:
  - Automatically answers recruiter questions and MCQs using Shraddha Dwivedi's CV context.
  - Includes robust profile fallbacks so questions never time out or stall.
- ✅ **Company Career Portal URL Extraction**:
  - When a job requires "Apply on company site", the bot automatically opens/extracts the real external company career URL and records it.
- ✅ **Clean 2-CSV Report Architecture**:
  1. `applied_jobs.csv` — All successfully applied jobs with timestamps and application type.
  2. `manual_apply_jobs.csv` — Jobs requiring manual attention (with real company external URLs, failed jobs, or expired quotas).

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.8+ installed
- Microsoft Edge browser installed
- Naukri.com credentials configured in `.env`

### 2. Configure `.env`
Ensure your `.env` contains:
```ini
NAUKRI_EMAIL=shraddha.it@yahoo.com
NAUKRI_PASSWORD=your_password

FIRSTNAME=Shraddha
LASTNAME=Dwivedi
PHONE=+91-7610557288

# Job Search Preferences
KEYWORDS=OFSAA developer, sql developer, plsql developer, oracle plsql developer
LOCATION=
PAGES_PER_KEYWORD=2
MAX_APPLICATIONS=100

# Candidate Profile Details
TOTAL_EXPERIENCE=4 years
RELEVANT_EXPERIENCE=4 years
CURRENT_CTC=6 LPA
EXPECTED_CTC=10 LPA
NOTICE_PERIOD=15-30 days
CURRENT_LOCATION=Bangalore
CURRENT_COMPANY=Highpoints Technologies Pvt Ltd
KEY_SKILLS=OFSAA, SQL, PL/SQL, Oracle 12c, Python, Linux/Unix, Database Development, Performance Tuning, Jasper Reports
```

### 3. Run the Bot (Single Command)

```bash
python Naukri-Edge.py
```

## 📊 CSV Output Structure

Only two CSV files are generated and updated:

1. **`applied_jobs.csv`**:
   - `Job Title`
   - `Company Name`
   - `Job URL`
   - `Location`
   - `Experience`
   - `Application Type` (Direct Apply 1-Click / Recruiter Questionnaire Gemini AI)
   - `Applied At`

2. **`manual_apply_jobs.csv`**:
   - `Job Title`
   - `Company Name`
   - `Job URL` (Naukri Link)
   - `Company External URL` (Real External Career Portal Link to apply directly)
   - `Location`
   - `Experience`
   - `Reason` (Reason for manual apply or failure)
   - `Checked At`
