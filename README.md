# Naukri-Autoapply-Bot (Shreyash Gupta Edition)

> Intelligent, automated job application bot for Naukri.com using **Selenium**, **Microsoft Edge**, and **Gemini AI**.
> Custom tailored for **Shreyash Gupta** to apply to relevant roles (Data Analyst, Business Analyst, Power BI Analyst, Python/SQL Analyst), filtering out irrelevant technologies and over-qualified roles, answering recruiter questionnaires with AI, capturing external company URLs, and maintaining exactly 2 clean CSV reports.

## 📋 Key Features

- ✅ **Single Command Execution** — Run `python Naukri-Edge.py` for end-to-end processing.
- ✅ **Smart Preference & Relevance Filtering**:
  - Targets Data Analyst, Business Analyst, Power BI Analyst, Python/SQL Data Analyst roles matching `.env` settings.
  - Automatically rejects unrelated stacks (PHP, Laravel, Mobile Dev, Sales, BPO, etc.).
  - Experience filter ensures you apply to roles fitting your profile (Entry-level / Fresher to 3 yrs, skipping 4+ yrs senior roles).
  - Location filter respects `.env` (pan-India by default, or specific cities / remote).
- ✅ **Recruiter Chatbot Auto-Answering with Gemini AI**:
  - Automatically answers recruiter questions and MCQs using Shreyash Gupta's CV context.
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
NAUKRI_EMAIL=shreyash2025gupta@gmail.com
NAUKRI_PASSWORD=your_password

FIRSTNAME=Shreyash
LASTNAME=Gupta
PHONE=+91-7879946573

# Job Search Preferences
KEYWORDS=data analyst, business analyst, power bi analyst, python data analyst, sql data analyst, junior data analyst
LOCATION=
PAGES_PER_KEYWORD=2
MAX_APPLICATIONS=100

# Candidate Profile Details
TOTAL_EXPERIENCE=1 year
RELEVANT_EXPERIENCE=1 year
CURRENT_CTC=3 LPA
EXPECTED_CTC=5 LPA
NOTICE_PERIOD=Immediate
CURRENT_LOCATION=Bhopal, M.P.
CURRENT_COMPANY=Fresher / MBA Business Analytics
KEY_SKILLS=SQL, Python, Power BI, Excel, Tableau, Pandas, NumPy, Data Analytics, ETL, Business Intelligence, Data Visualization
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
