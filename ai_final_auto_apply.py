"""
Final Autonomous AI Job Application Agent (ai_final_auto_apply.py)
==================================================================
This is the ultimate AI application script to be run after initial Naukri runs.

Key Features:
1. Consolidates all pending jobs from:
   - manual_apply_jobs.csv
   - external_applied_failed.csv
2. Excludes any job that has already PASSED.
3. Uses Gemini AI to:
   - "Read" the webpage structure
   - Identify & click the right 'Apply' buttons on complex portals
   - Auto-fill all standard candidate fields from Shreyash Gupta's CV
   - Answer recruiter custom questions and textareas using full CV context
   - Attach SHREYASH GUPTA.pdf
   - Locate and click the 'Submit' button
"""

import os
import time
import logging
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    ElementClickInterceptedException
)

import gemini_helper

try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANUAL_CSV = os.path.join(BASE_DIR, "manual_apply_jobs.csv")
FAILED_CSV = os.path.join(BASE_DIR, "external_applied_failed.csv")
PASSED_CSV = os.path.join(BASE_DIR, "external_applied_passed.csv")
APPLIED_CSV = os.path.join(BASE_DIR, "applied_jobs.csv")

CV_PDF = os.path.join(BASE_DIR, "SHREYASH GUPTA.pdf")
CV_DOCX = os.path.join(BASE_DIR, "SHREYASH GUPTA.docx")
RESUME_PATH = CV_PDF if os.path.exists(CV_PDF) else CV_DOCX

# --- Candidate Profile Details ---
CANDIDATE = {
    "first_name": os.getenv("FIRSTNAME", "Shreyash"),
    "last_name": os.getenv("LASTNAME", "Gupta"),
    "full_name": f"{os.getenv('FIRSTNAME', 'Shreyash')} {os.getenv('LASTNAME', 'Gupta')}",
    "email": os.getenv("NAUKRI_EMAIL", "shreyash2025gupta@gmail.com"),
    "phone": os.getenv("PHONE", "+91-7879946573"),
    "linkedin": "https://www.linkedin.com/in/shreyash-gupta-6039b6287",
    "location": os.getenv("CURRENT_LOCATION", "Bhopal, M.P."),
    "experience": "1",
    "experience_full": "1 year",
    "notice_period": os.getenv("NOTICE_PERIOD", "Immediate"),
    "current_company": os.getenv("CURRENT_COMPANY", "Fresher / MBA Business Analytics"),
    "current_ctc": os.getenv("CURRENT_CTC", "3 LPA"),
    "expected_ctc": os.getenv("EXPECTED_CTC", "5 LPA")
}


def upload_resume_file(driver):
    """Locate file upload element and attach Shreyash Gupta's CV."""
    if not os.path.exists(RESUME_PATH):
        logger.warning(f"Resume file not found at: {RESUME_PATH}")
        return False

    try:
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        for fi in file_inputs:
            try:
                fi.send_keys(os.path.abspath(RESUME_PATH))
                logger.info(f"  📎 Resume attached: {os.path.basename(RESUME_PATH)}")
                time.sleep(2)
                return True
            except Exception:
                driver.execute_script("arguments[0].style.display = 'block'; arguments[0].style.visibility = 'visible';", fi)
                fi.send_keys(os.path.abspath(RESUME_PATH))
                logger.info(f"  📎 Resume attached (forced visible): {os.path.basename(RESUME_PATH)}")
                time.sleep(2)
                return True
    except Exception as e:
        logger.warning(f"Resume upload error: {e}")

    return False


def fill_ai_custom_questions(driver):
    """Answer all visible textareas using Gemini AI loaded with Shreyash Gupta's CV."""
    if not gemini_helper.is_gemini_available():
        return 0

    answered = 0
    try:
        textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
        for ta in textareas:
            if ta.is_displayed() and ta.is_enabled():
                q_text = ta.get_attribute("placeholder") or ta.get_attribute("name") or "Candidate question"
                ans = gemini_helper.answer_question(q_text)
                ta.clear()
                ta.send_keys(ans)
                answered += 1
    except Exception:
        pass
    return answered
