"""
Gemini AI Assistant for Naukri Application Questionnaires
==========================================================
Uses Google Gemini to answer recruiter chatbot questions (radio options & free text)
with candidate context (Shraddha Dwivedi) and automatic fallback.
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

# Candidate profile details from .env or defaults (Derived directly from Shraddha Dwivedi's CV)
FIRSTNAME = os.getenv('FIRSTNAME', 'Shraddha')
LASTNAME = os.getenv('LASTNAME', 'Dwivedi')
TOTAL_EXPERIENCE = os.getenv('TOTAL_EXPERIENCE', '4 years')
RELEVANT_EXPERIENCE = os.getenv('RELEVANT_EXPERIENCE', '4 years')
CURRENT_CTC = os.getenv('CURRENT_CTC', '6 LPA')
EXPECTED_CTC = os.getenv('EXPECTED_CTC', '10 LPA')
NOTICE_PERIOD = os.getenv('NOTICE_PERIOD', '15-30 days')
CURRENT_LOCATION = os.getenv('CURRENT_LOCATION', 'Bangalore')
CURRENT_COMPANY = os.getenv('CURRENT_COMPANY', 'Highpoints Technologies Pvt Ltd')
PHONE = os.getenv('PHONE', '+91-7610557288')
EMAIL = os.getenv('NAUKRI_EMAIL', 'shraddha.it@yahoo.com')
KEY_SKILLS = os.getenv('KEY_SKILLS', 'OFSAA, SQL, PL/SQL, Oracle 12c, Python, Linux/Unix, Database Development, Performance Tuning, Jasper Reports')

# Auto-locate and load CV text
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSSIBLE_CV_FILES = [
    os.path.join(BASE_DIR, "shraddha_dwivedi_cv.txt"),
    os.path.join(BASE_DIR, "Shraddha_Dwivedi_cv.txt"),
    os.path.join(BASE_DIR, "Shraddha_Dwivedi_cv.docx"),
    os.path.join(BASE_DIR, "shraddha_dwivedi_cv.docx")
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
                logger.info(f"🤖 Gemini AI initialized with model '{model_name}' and Shraddha Dwivedi's CV!")
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
Candidate Full Resume & Profile (Shraddha Dwivedi):
==================================================
{FULL_CV_TEXT}
==================================================
Additional Application Details:
- Candidate Name: {FIRSTNAME} {LASTNAME}
- Target Roles: SQL/PLSQL Developer, OFSAA Developer, Oracle Database Developer, Application Developer
- Current Company: {CURRENT_COMPANY}
- Current CTC: {CURRENT_CTC}
- Expected CTC: {EXPECTED_CTC}
- Notice Period: {NOTICE_PERIOD}
- Location: {CURRENT_LOCATION}
- Comfortable working remotely: Yes, 100%
- Open to relocate: Yes / Bangalore / Hyderabad / Pune / Remote / Hybrid
- Key Skills: {KEY_SKILLS}
- Education: Bachelor of Engineering (B.E.) in Information Technology (Govt. Indira Gandhi Engineering College, Sagar, 2020)
- Phone: {PHONE}
- Email: {EMAIL}
"""
    return f"""
Candidate Profile:
- Full Name: {FIRSTNAME} {LASTNAME}
- Target Role: SQL/PLSQL Developer, OFSAA Developer, Oracle Database Developer
- Total Experience: {TOTAL_EXPERIENCE}
- Relevant Experience: {RELEVANT_EXPERIENCE}
- Current CTC: {CURRENT_CTC}
- Expected CTC: {EXPECTED_CTC}
- Notice Period: {NOTICE_PERIOD}
- Current Company: {CURRENT_COMPANY}
- Location: {CURRENT_LOCATION}
- Willing to relocate: Yes / Open to Remote and Hybrid
- Key Skills: {KEY_SKILLS}
- Education: Bachelor of Engineering (B.E.) in Information Technology (2020)
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
            for target in ['immediately', '15 days', 'within 15', 'within 30', '15-30', 'less than 15', '1 month']:
                for opt in options:
                    if target in opt.lower():
                        return opt

        # Experience
        if any(w in q for w in ['experience', 'exp', 'years']):
            # Shraddha has 4 years experience
            for target in ['4', '3 to 5', '3-5', 'more than 2', 'more than 3', '2 to 4', '4 to 6']:
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
            for target in ['6-8', '5-7', '6-10', '6 to 10', '8-10', '6', '10']:
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
            return '4'
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
            return 'B.E. Information Technology'
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
Pick the BEST single option from the Available Options list that best represents candidate Shraddha Dwivedi.
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
Provide a very short, direct answer suitable for a job application text input field (e.g., "4", "4 years", "15-30 days", "Yes", "6 LPA", "Bangalore", etc.) representing candidate Shraddha Dwivedi.
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
