"""
Gemini AI Assistant for Naukri Application Questionnaires
==========================================================
Uses Google Gemini to answer recruiter chatbot questions (radio options & free text).
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Candidate profile details from .env or defaults (Derived directly from aman_dubey_cv.docx)
FIRSTNAME = os.getenv('FIRSTNAME', 'Aman')
LASTNAME = os.getenv('LASTNAME', 'Dubey')
TOTAL_EXPERIENCE = os.getenv('TOTAL_EXPERIENCE', '4 years')
RELEVANT_EXPERIENCE = os.getenv('RELEVANT_EXPERIENCE', '4 years')
CURRENT_CTC = os.getenv('CURRENT_CTC', '4.5 LPA')
EXPECTED_CTC = os.getenv('EXPECTED_CTC', '7 LPA')
NOTICE_PERIOD = os.getenv('NOTICE_PERIOD', '15-30 days')
CURRENT_LOCATION = os.getenv('CURRENT_LOCATION', 'Indore, M.P.')
KEY_SKILLS = os.getenv('KEY_SKILLS', 'PHP, Laravel, MySQL, MongoDB, JavaScript, jQuery, Alpine.js, CodeIgniter, Pest PHP, Git, REST API, Linux')

# Load full CV text if file exists
CV_FILE_PATH = os.path.join(os.path.dirname(__file__), "aman_dubey_cv.txt")
FULL_CV_TEXT = ""
if os.path.exists(CV_FILE_PATH):
    try:
        with open(CV_FILE_PATH, "r", encoding="utf-8") as f:
            FULL_CV_TEXT = f.read().strip()
    except Exception as e:
        logger.warning(f"Could not read CV file: {e}")

# Initialize Gemini Model if key is present
_model = None


def get_gemini_model():
    """Returns initialized Gemini model or None if key is missing."""
    global _model
    if _model is not None:
        return _model

    key = os.getenv('GEMINI_API_KEY', '').strip()
    if not key or key == 'your_gemini_api_key_here':
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        # Using gemini-1.5-flash (fast, reliable, free tier)
        _model = genai.GenerativeModel('gemini-1.5-flash')
        logger.info("🤖 Gemini AI initialized with Aman Dubey's CV!")
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
Candidate Full Resume & Profile (Aman Dubey):
==================================================
{FULL_CV_TEXT}
==================================================
Additional Application Details:
- Current CTC: {CURRENT_CTC}
- Expected CTC: {EXPECTED_CTC}
- Notice Period: {NOTICE_PERIOD}
- Comfortable working remotely: Yes, 100%
- Open to relocate: Yes / Remote / Hybrid
"""
    return f"""
Candidate Profile:
- Full Name: {FIRSTNAME} {LASTNAME}
- Target Role: Senior PHP Laravel Developer
- Total Experience: {TOTAL_EXPERIENCE}
- Relevant Laravel/PHP Experience: {RELEVANT_EXPERIENCE}
- Current CTC: {CURRENT_CTC}
- Expected CTC: {EXPECTED_CTC}
- Notice Period: {NOTICE_PERIOD}
- Current Company: Webwiders Software Solutions Pvt Ltd, Indore
- Location: {CURRENT_LOCATION}
- Willing to relocate: Yes / Open to Remote and Hybrid
- Key Skills: {KEY_SKILLS}
- Education: Bachelor of Engineering (B.E.) in Information Technology (2020)
- Comfortable working remotely: Yes
"""


def answer_question(question_text, options=None):
    """
    Given a question and optional list of choices, returns the best answer.
    If options are provided, returns the exact string matching one of the options.
    If free text, returns a short, crisp answer (e.g. '3 years', 'Yes', '15 days').
    """
    model = get_gemini_model()
    if not model:
        return None

    candidate_context = get_candidate_context()

    try:
        if options and len(options) > 0:
            prompt = f"""{candidate_context}

The recruiter asked the following multiple-choice question on a job application:
Question: "{question_text}"

Available Options:
{chr(10).join([f"- {opt}" for opt in options])}

Instructions:
Pick the BEST single option from the Available Options list that best represents the candidate.
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
            return options[0]

        else:
            prompt = f"""{candidate_context}

The recruiter asked the following question on a job application:
Question: "{question_text}"

Instructions:
Provide a very short, direct answer suitable for a job application text input field (e.g., "3", "3 years", "15 days", "Yes", "7 LPA", etc.).
Do NOT explain. Do NOT add extra sentences. Output ONLY the answer value.
"""
            response = model.generate_content(prompt)
            return response.text.strip().strip('"').strip("'")

    except Exception as e:
        logger.warning(f"Gemini API error while answering '{question_text}': {e}")
        return None


def pick_best_button(button_labels, intent="open_apply"):
    """
    Given a list of button/link texts on a webpage, use Gemini AI to decide
    which button matches the desired intent:
      - 'open_apply': Button to open the application form
      - 'submit': Button to submit the application form
    """
    model = get_gemini_model()
    if not model or not button_labels:
        return None

    intent_desc = "opens or starts the job application form (e.g., 'Apply Now', 'I'm interested', 'Apply for this position')" if intent == "open_apply" else "submits or sends the completed job application (e.g., 'Submit Application', 'Send', 'Submit')"

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

