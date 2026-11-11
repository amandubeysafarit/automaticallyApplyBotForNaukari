# Naukri-Autoapply-Bot (Unified Master Edition)

> Intelligent, automated job application bot for Naukri.com using **Selenium**, **Microsoft Edge**, and **Gemini AI**.
> Custom tailored to apply only to relevant roles (PHP / Laravel / Web Development), filtering out irrelevant technologies and over-qualified roles, answering recruiter questionnaires with AI, capturing external company URLs, and maintaining exactly 2 clean CSV reports.

## 📋 Key Features

- ✅ **Single Command Execution** — Run `python Naukri-Edge.py` for end-to-end processing.
- ✅ **Smart Preference & Relevance Filtering**:
  - Targets PHP, Laravel, and Web Development roles strictly matching `.env` settings.
  - Automatically rejects unrelated stacks (Java, Spring Boot, ERP, SAP, .NET, C#, Python/Django, AI Lead, etc.).
  - Experience filter ensures you only apply to roles fitting your experience level (e.g. 4 years).
  - Location/Remote filter respects `LOCATION=remote`.
- ✅ **Recruiter Chatbot Auto-Answering with Gemini AI**:
  - Automatically answers recruiter questions and MCQs using candidate CV context.
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
- Naukri.com account & free Gemini API key

### 2. Configure `.env`
Ensure your `.env` contains:
```ini
NAUKRI_EMAIL=your_email@example.com
NAUKRI_PASSWORD=your_password

FIRSTNAME=Aman
LASTNAME=Dubey

# Job Search Preferences
KEYWORDS=php laravel, laravel developer, php, laravel
LOCATION=remote
PAGES_PER_KEYWORD=2
MAX_APPLICATIONS=50

# Gemini AI Key
GEMINI_API_KEY=your_gemini_api_key

# Candidate Profile Details
TOTAL_EXPERIENCE=4 years
RELEVANT_EXPERIENCE=4 years
CURRENT_CTC=4.5 LPA
EXPECTED_CTC=7 LPA
NOTICE_PERIOD=15-30 days
CURRENT_LOCATION=Indore, M.P.
KEY_SKILLS=PHP, Laravel, MySQL, MongoDB, JavaScript, jQuery, Alpine.js, CodeIgniter, Pest PHP, Git, REST API
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
