"""
AI External Job Application Agent (auto_apply_external.py) - Enhanced Edition
=============================================================================
Reads jobs from 'manual_apply_jobs.csv' (where 'Apply on company site' redirects externally),
opens the company career portal, fills the form using candidate details and Gemini AI,
attaches Shreyash Gupta's CV (PDF/DOCX), and tracks outcomes into:
  - external_applied_passed.csv  (Successfully submitted or filled)
  - external_applied_failed.csv  (Failed / Needs manual apply, e.g. login/captcha)
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

# --- Files & Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANUAL_CSV = os.path.join(BASE_DIR, "manual_apply_jobs.csv")
PASSED_CSV = os.path.join(BASE_DIR, "external_applied_passed.csv")
FAILED_CSV = os.path.join(BASE_DIR, "external_applied_failed.csv")

CV_PDF = os.path.join(BASE_DIR, "SHREYASH GUPTA.pdf")
CV_DOCX = os.path.join(BASE_DIR, "SHREYASH GUPTA.docx")
RESUME_PATH = CV_PDF if os.path.exists(CV_PDF) else CV_DOCX

# --- Candidate Details ---
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

AUTO_SUBMIT = os.getenv("AUTO_SUBMIT", "True").lower() in ["true", "1", "yes"]


def create_edge_driver():
    """Create and return an Edge WebDriver instance."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")

    if WEBDRIVER_MANAGER_AVAILABLE:
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif os.getenv('EDGE_DRIVER_PATH'):
        service = EdgeService(executable_path=os.getenv('EDGE_DRIVER_PATH'))
    else:
        service = EdgeService()

    return webdriver.Edge(service=service, options=options)


def upload_resume_file(driver):
    """Find input[type='file'] on the page and upload Shreyash Gupta's CV."""
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
