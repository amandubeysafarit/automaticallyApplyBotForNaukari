"""
Gemini AI Assistant for Naukri Application Questionnaires
==========================================================
Uses Google Gemini to answer recruiter chatbot questions (radio options & free text)
with candidate context (Shreyash Gupta) and automatic fallback.
"""

import os
import re
import logging
import warnings
import zipfile
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

# Suppress deprecation warnings from legacy package
warnings.filterwarnings('ignore', category=FutureWarning)

load_dotenv()
logger = logging.getLogger(__name__)

# Candidate profile details from .env or defaults (Derived directly from Shreyash Gupta's CV)
FIRSTNAME = os.getenv('FIRSTNAME', 'Shreyash')
LASTNAME = os.getenv('LASTNAME', 'Gupta')
TOTAL_EXPERIENCE = os.getenv('TOTAL_EXPERIENCE', '1 year')
RELEVANT_EXPERIENCE = os.getenv('RELEVANT_EXPERIENCE', '1 year')
CURRENT_CTC = os.getenv('CURRENT_CTC', '3 LPA')
EXPECTED_CTC = os.getenv('EXPECTED_CTC', '5 LPA')
NOTICE_PERIOD = os.getenv('NOTICE_PERIOD', 'Immediate')
CURRENT_LOCATION = os.getenv('CURRENT_LOCATION', 'Bhopal, M.P.')
CURRENT_COMPANY = os.getenv('CURRENT_COMPANY', 'Fresher / MBA Candidate (LNCT Bhopal)')
PHONE = os.getenv('PHONE', '+91-7879946573')
EMAIL = os.getenv('NAUKRI_EMAIL', 'shreyash2025gupta@gmail.com')
KEY_SKILLS = os.getenv('KEY_SKILLS', 'SQL, Python, Power BI, Excel, Tableau, Pandas, NumPy, Data Analytics, ETL, Business Intelligence, Data Visualization')

# Auto-locate and load CV text
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSSIBLE_CV_FILES = [
    os.path.join(BASE_DIR, "shreyash_gupta_cv.txt"),
    os.path.join(BASE_DIR, "SHREYASH GUPTA.docx"),
    os.path.join(BASE_DIR, "SHREYASH GUPTA.pdf")
]

FULL_CV_TEXT = ""

def _extract_text_from_docx(file_path):
    try:
        with zipfile.ZipFile(file_path) as z:
            xml_content = z.read('word/document.xml')
        tree = ET.fromstring(xml_content)
        texts = []
        for elem in tree.iter():
            if elem.tag.endswith('}t'):
                if elem.text:
                    texts.append(elem.text)
            elif elem.tag.endswith('}p'):
                texts.append('\n')
        return ''.join(texts).strip()
    except Exception as e:
        logger.warning(f"Could not extract docx text: {e}")
        return ""

for cv_path in POSSIBLE_CV_FILES:
    if os.path.exists(cv_path):
        try:
            if cv_path.endswith('.txt'):
                with open(cv_path, "r", encoding="utf-8") as f:
                    FULL_CV_TEXT = f.read().strip()
            elif cv_path.endswith('.docx') and not FULL_CV_TEXT:
                FULL_CV_TEXT = _extract_text_from_docx(cv_path)
            if FULL_CV_TEXT:
                break
        except Exception as e:
            logger.warning(f"Could not read CV file {cv_path}: {e}")

# Initialize Gemini Model if key is present
_model = None
_model_name_cached = None

MODELS_TO_TRY = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-flash-latest']


def get_gemini_model():
    """Returns initialized Gemini model or None if key is missing."""
    global _model, _model_name_cached
    if _model is not None:
        return _model

    key = os.getenv('GEMINI_API_KEY', '').strip()
    if not key or key == 'your_gemini_api_key_here':
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=key)

        for model_name in MODELS_TO_TRY:
            try:
                candidate_model = genai.GenerativeModel(model_name)
                _model = candidate_model
                _model_name_cached = model_name
                logger.info(f"🤖 Gemini AI initialized with model '{model_name}' and Shreyash Gupta's CV!")
                return _model
            except Exception:
                continue

        _model = genai.GenerativeModel('gemini-2.5-flash')
        return _model
    except Exception as e:
        logger.warning(f"Could not initialize Gemini: {e}")
        return None


def is_gemini_available():
    """Check if Gemini API key is configured."""
    key = os.getenv('GEMINI_API_KEY', '').strip()
    return bool(key and key != 'your_gemini_api_key_here')


def get_candidate_context():
    """Build candidate context for Gemini using full CV details."""
    if FULL_CV_TEXT:
        return f"""
Candidate Full Resume & Profile (Shreyash Gupta):
==================================================
{FULL_CV_TEXT}
==================================================
Additional Application Details:
- Candidate Name: {FIRSTNAME} {LASTNAME}
- Target Roles: Data Analyst, Business Analyst, Power BI Analyst, Python Data Analyst, SQL Analyst, Junior Data Analyst
- Current Status: {CURRENT_COMPANY}
- Total Experience: {TOTAL_EXPERIENCE}
- Relevant Analytics Experience: {RELEVANT_EXPERIENCE}
- Current CTC: {CURRENT_CTC}
- Expected CTC: {EXPECTED_CTC}
- Notice Period: {NOTICE_PERIOD} (Immediate Joiner)
- Location: {CURRENT_LOCATION}
- Comfortable working remotely: Yes, 100%
- Open to relocate: Yes / Bhopal / Bangalore / Pune / Hyderabad / Gurgaon / Remote / Hybrid
- Key Skills: {KEY_SKILLS}
- Education: MBA in Business Analytics (LNCT Bhopal, 2024-2026), BBA (Barkatullah University, Bhopal)
- Phone: {PHONE}
- Email: {EMAIL}
"""
    return f"""
Candidate Profile:
- Full Name: {FIRSTNAME} {LASTNAME}
- Target Role: Data Analyst, Business Analyst, Power BI Analyst
- Total Experience: {TOTAL_EXPERIENCE}
- Relevant Experience: {RELEVANT_EXPERIENCE}
- Current CTC: {CURRENT_CTC}
- Expected CTC: {EXPECTED_CTC}
- Notice Period: {NOTICE_PERIOD}
- Current Status: {CURRENT_COMPANY}
- Location: {CURRENT_LOCATION}
- Willing to relocate: Yes / Open to Remote and Hybrid
- Key Skills: {KEY_SKILLS}
- Education: MBA in Business Analytics (2024-2026), BBA
- Comfortable working remotely: Yes, 100%
- Phone: {PHONE}
- Email: {EMAIL}
"""


def get_fallback_answer(question_text, options=None):
    """
    Deterministic rule-based fallback answering if Gemini is unavailable or errors out.
    Ensures questionnaire NEVER gets stuck or returns empty/None.
    """
    q = (question_text or '').lower().strip()

    if options and len(options) > 0:
        # Multiple Choice Fallback
        # Notice Period / Joining
        if any(w in q for w in ['notice', 'soon', 'join', 'start']):
            for target in ['immediately', 'immediate', '0-15 days', '15 days', 'within 15', 'less than 15', '1 month']:
                for opt in options:
                    if target in opt.lower():
                        return opt

        # Experience
        if any(w in q for w in ['experience', 'exp', 'years']):
            # Shreyash has 0-1 year experience / Fresher
            for target in ['0-1', '0 to 1', '1 year', '1', 'fresher', '0-2', '0 to 2', 'less than 1']:
                for opt in options:
                    if target in opt.lower():
                        return opt

        # Location / Relocation / Remote / Shift
        if any(w in q for w in ['relocate', 'remote', 'wfh', 'shift', 'flexible', 'travel', 'comfortable', 'willing']):
            for target in ['flexible', 'comfortable', 'both', 'yes', 'open', 'agree']:
                for opt in options:
                    if target in opt.lower():
                        return opt

        # CTC
        if any(w in q for w in ['ctc', 'salary']):
            for target in ['3-5', '3 to 5', '4-6', '3', '4', '5', 'negotiable']:
                for opt in options:
                    if target in opt.lower():
                        return opt

        # Binary Yes / No
        for opt in options:
            if opt.lower().strip() in ['yes', 'agree', 'y']:
                return opt

        # If options has "Skip this question", avoid it unless no other choice
        valid_opts = [o for o in options if 'skip' not in o.lower()]
        return valid_opts[0] if valid_opts else options[0]

    else:
        # Free Text Fallback
        if any(w in q for w in ['experience', 'how many years', 'years of experience', 'total software']):
            return '1'
        if any(w in q for w in ['current ctc', 'present ctc', 'current fixed', 'current salary', 'fixed ctc']):
            return CURRENT_CTC
        if any(w in q for w in ['expected ctc', 'expected salary', 'salary expectation']):
            return EXPECTED_CTC
        if any(w in q for w in ['notice period', 'how soon', 'when can you join', 'serving notice']):
            return NOTICE_PERIOD
        if any(w in q for w in ['currently based', 'current location', 'city', 'where do you live', 'where are you']):
            return CURRENT_LOCATION
        if any(w in q for w in ['relocate', 'remote', 'comfortable', 'willing', 'have you', 'are you', 'do you']):
            return 'Yes'
        if any(w in q for w in ['degree', 'qualification', 'education']):
            return 'MBA in Business Analytics'
        if any(w in q for w in ['company', 'current employer', 'organization']):
            return CURRENT_COMPANY
        if any(w in q for w in ['tools', 'technologies', 'skills']):
            return KEY_SKILLS
        return 'Yes'


def answer_question(question_text, options=None):
    """
    Given a question and optional list of choices, returns the best answer.
    Uses Gemini AI first, and automatically falls back to get_fallback_answer if needed.
    """
    if not question_text or not question_text.strip():
        return get_fallback_answer(question_text, options)

    model = get_gemini_model()
    if not model:
        return get_fallback_answer(question_text, options)

    candidate_context = get_candidate_context()

    try:
        if options and len(options) > 0:
            prompt = f"""{candidate_context}

The recruiter asked the following multiple-choice question on a job application:
Question: "{question_text}"

Available Options:
{chr(10).join([f"- {opt}" for opt in options])}

Instructions:
Pick the BEST single option from the Available Options list that best represents candidate Shreyash Gupta.
Output ONLY the exact option text without any extra words, quotes, or markdown.
"""
            response = model.generate_content(prompt)
            chosen = response.text.strip().strip('"').strip("'")

            # Match with one of the available options
            for opt in options:
                if opt.lower().strip() == chosen.lower().strip():
                    return opt
            for opt in options:
                if opt.lower().strip() in chosen.lower() or chosen.lower() in opt.lower().strip():
                    return opt
            return get_fallback_answer(question_text, options)

        else:
            prompt = f"""{candidate_context}

The recruiter asked the following question on a job application:
Question: "{question_text}"

Instructions:
Provide a very short, direct answer suitable for a job application text input field (e.g., "1", "1 year", "Immediate", "Yes", "3 LPA", "5 LPA", "Bhopal", etc.) representing candidate Shreyash Gupta.
Do NOT explain. Do NOT add extra sentences. Output ONLY the concise answer value.
"""
            response = model.generate_content(prompt)
            ans = response.text.strip().strip('"').strip("'")
            if not ans or ans.lower() == 'none':
                return get_fallback_answer(question_text, options)
            return ans

    except Exception as e:
        logger.warning(f"Gemini API error while answering '{question_text}': {e}. Using smart fallback.")
        return get_fallback_answer(question_text, options)


def pick_best_button(button_labels, intent="open_apply"):
    """
    Given a list of button/link texts on a webpage, use Gemini AI to decide
    which button matches the desired intent.
    """
    model = get_gemini_model()
    if not model or not button_labels:
        return None

    intent_desc = "opens or starts the job application form (e.g., 'Apply Now', 'I\\'m interested', 'Apply for this position')" if intent == "open_apply" else "submits or sends the completed job application (e.g., 'Submit Application', 'Send', 'Submit', 'Save')"

    prompt = f"""
We are automating a job application. The following buttons/links are visible on the company's webpage:
{chr(10).join([f"{i+1}. {txt}" for i, txt in enumerate(button_labels)])}

Task:
Identify which button {intent_desc}.
If none of them matches, reply with "NONE".
Output ONLY the exact button text as shown in the list, nothing else.
"""
    try:
        response = model.generate_content(prompt)
        chosen = response.text.strip().strip('"').strip("'")
        if chosen == "NONE" or not chosen:
            return None
        for b in button_labels:
            if b.lower().strip() == chosen.lower().strip():
                return b
        for b in button_labels:
            if b.lower().strip() in chosen.lower() or chosen.lower() in b.lower().strip():
                return b
    except Exception as e:
        logger.warning(f"Gemini button pick error: {e}")

    return None
