"""
AI External Job Application Agent (auto_apply_external.py) - Enhanced Edition
=============================================================================
Reads jobs from 'manual_apply_jobs.csv' (where 'Apply on company site' redirects externally),
opens the company career portal, fills the form using candidate details and Gemini AI,
attaches Aman Dubey's CV (PDF/DOCX), and tracks outcomes into:
  - external_applied_passed.csv  (Successfully submitted or filled)
  - external_applied_failed.csv  (Failed / Needs manual apply, e.g. login/captcha)

Enhanced with:
  1. Top ATS Auto-Triggers (Workable, SmartRecruiters, Zoho Recruit, Keka, Freshteam, Ashby)
  2. Embedded Iframe Form Detection (Zoho Recruit, Google Forms, WordPress career forms)
  3. Ultra-wide Submit Button Recognition (captures custom buttons, Freshteam widgets, div/a tags)
  4. Smart Retry (re-evaluates previously failed jobs while preserving already passed ones)
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

CV_PDF = os.path.join(BASE_DIR, "aman_dubey_cv.pdf")
CV_DOCX = os.path.join(BASE_DIR, "aman_dubey_cv.docx")
RESUME_PATH = CV_PDF if os.path.exists(CV_PDF) else CV_DOCX

# --- Candidate Details ---
CANDIDATE = {
    "first_name": os.getenv("FIRSTNAME", "Aman"),
    "last_name": os.getenv("LASTNAME", "Dubey"),
    "full_name": f"{os.getenv('FIRSTNAME', 'Aman')} {os.getenv('LASTNAME', 'Dubey')}",
    "email": os.getenv("NAUKRI_EMAIL", "amandubeysagarit@gmail.com"),
    "phone": "8269390982",
    "linkedin": "https://www.linkedin.com/in/aman-dubey-667904199",
    "location": os.getenv("CURRENT_LOCATION", "Indore, M.P."),
    "experience": "4",
    "experience_full": "4 years",
    "notice_period": os.getenv("NOTICE_PERIOD", "15-30 days"),
    "current_company": "Webwiders Software Solutions",
    "current_ctc": os.getenv("CURRENT_CTC", "4.5 LPA"),
    "expected_ctc": os.getenv("EXPECTED_CTC", "7 LPA")
}

AUTO_SUBMIT = os.getenv("AUTO_SUBMIT", "True").lower() in ["true", "1", "yes"]


def create_edge_driver():
    """Create and return an Edge WebDriver instance."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")

    if WEBDRIVER_MANAGER_AVAILABLE:
        service = EdgeService(EdgeChromiumDriverManager().install())
    else:
        service = EdgeService()

    driver = webdriver.Edge(service=service, options=options)
    return driver


def load_already_passed():
    """Load URLs already recorded in external_applied_passed.csv to avoid duplicate applications."""
    passed = set()
    if os.path.exists(PASSED_CSV):
        try:
            df = pd.read_csv(PASSED_CSV)
            for col in ['Naukri URL', 'Company Portal URL']:
                if col in df.columns:
                    passed.update(df[col].dropna().astype(str).tolist())
        except Exception:
            pass
    return passed


def record_passed(record):
    """Append passed application record to external_applied_passed.csv."""
    df_new = pd.DataFrame([record])
    if os.path.exists(PASSED_CSV):
        try:
            df_existing = pd.read_csv(PASSED_CSV)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.drop_duplicates(subset=['Naukri URL'], keep='last', inplace=True)
            df_combined.to_csv(PASSED_CSV, index=False)
        except Exception:
            df_new.to_csv(PASSED_CSV, index=False)
    else:
        df_new.to_csv(PASSED_CSV, index=False)
    logger.info(f"  ✅ Saved to external_applied_passed.csv")


def record_failed(record):
    """Append failed application record to external_applied_failed.csv."""
    df_new = pd.DataFrame([record])
    if os.path.exists(FAILED_CSV):
        try:
            df_existing = pd.read_csv(FAILED_CSV)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.drop_duplicates(subset=['Naukri URL'], keep='last', inplace=True)
            df_combined.to_csv(FAILED_CSV, index=False)
        except Exception:
            df_new.to_csv(FAILED_CSV, index=False)
    else:
        df_new.to_csv(FAILED_CSV, index=False)
    logger.info(f"  ❌ Saved to external_applied_failed.csv (Reason: {record['Failure Reason']})")


def click_apply_on_naukri(driver, naukri_url):
    """
    Open Naukri job page and click 'Apply on company site'.
    Returns the external portal URL and switches driver to the external tab.
    """
    driver.get(naukri_url)
    time.sleep(3)

    original_handles = set(driver.window_handles)

    apply_selectors = [
        "//button[contains(text(),'Apply on company site')]",
        "//button[@id='company-site-button']",
        "//button[contains(@class,'company-site-button')]",
        "//button[contains(text(),'Apply')]",
    ]

    clicked = False
    for xpath in apply_selectors:
        try:
            btns = driver.find_elements(By.XPATH, xpath)
            for b in btns:
                if b.is_displayed():
                    driver.execute_script("arguments[0].click();", b)
                    clicked = True
                    break
            if clicked:
                break
        except Exception:
            continue

    if not clicked:
        return None, "Apply button not clickable on Naukri"

    time.sleep(4)
    new_handles = set(driver.window_handles) - original_handles

    if new_handles:
        driver.switch_to.window(list(new_handles)[0])

    time.sleep(3)
    portal_url = driver.current_url

    if "naukri.com" in portal_url.lower():
        return None, "Did not redirect to external company portal"

    return portal_url, None


def check_for_blockers(driver):
    """Check if external page requires login or has a captcha block."""
    page_source = driver.page_source.lower()
    url = driver.current_url.lower()

    if any(e in page_source for e in ["404 not found", "job not found", "job has expired", "position has been closed", "no longer accepting applications"]):
        return "Job Expired / Closed on Company Portal"

    captcha_elements = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='challenges.cloudflare.com'], .g-recaptcha, .cf-turnstile")
    if captcha_elements and any(c.is_displayed() for c in captcha_elements):
        return "CAPTCHA / Cloudflare Verification Required"

    if any(k in url for k in ["myworkdayjobs.com", "taleo.net", "brassring.com"]):
        login_prompts = driver.find_elements(By.XPATH, "//*[contains(text(),'Create Account') or contains(text(),'Sign In to Apply') or contains(text(),'Candidate Sign In')]")
        if login_prompts and any(lp.is_displayed() for lp in login_prompts):
            return "Company Account Registration / Sign-In Required (Workday/Taleo)"

    return None


def trigger_ats_application_form(driver):
    """
    Handle initial Job Description landing pages on top ATS systems
    (Workable, SmartRecruiters, Zoho Recruit, Keka, Freshteam, Ashby, etc.)
    by clicking the initial 'Apply' / 'I'm interested' button.
    """
    ats_selectors = [
        # Workable
        "[data-ui='overview-apply-btn']",
        "[data-ui='application-form-tab']",
        "a[href*='#apply']",
        # SmartRecruiters
        "//a[contains(text(),\"I'm interested\") or contains(text(),'Apply')]",
        "//button[contains(text(),\"I'm interested\") or contains(text(),'Apply')]",
        "[data-qa='apply-button']",
        # Zoho Recruit
        "//a[contains(text(),'I’m interested') or contains(text(),'Apply Now') or contains(text(),'Apply for this job')]",
        "//button[contains(text(),'I’m interested') or contains(text(),'Apply Now')]",
        "[id*='apply']",
        # Freshteam & Keka
        "[data-action='apply']",
        "a[href*='apply']",
        "button[data-testid='apply-button']",
        # Generic
        "//button[contains(translate(text(),'APPLY','apply'),'apply for this')]",
        "//a[contains(translate(text(),'APPLY','apply'),'apply for this')]",
        "//button[contains(translate(text(),'APPLY','apply'),'apply now')]",
        "//a[contains(translate(text(),'APPLY','apply'),'apply now')]",
        "//button[translate(text(),'APPLY','apply')='apply']",
        "//a[translate(text(),'APPLY','apply')='apply']",
        ".apply-btn",
        ".apply-button",
        "#apply-button",
    ]

    for sel in ats_selectors:
        try:
            if sel.startswith("//"):
                btns = driver.find_elements(By.XPATH, sel)
            else:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)

            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    href = b.get_attribute("href") or ""
                    if any(x in href for x in ["mailto:", "linkedin.com", "twitter.com", "facebook.com"]):
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", b)
                    logger.info(f"  👉 Clicked portal 'Apply' trigger button")
                    time.sleep(3)
                    return True
        except Exception:
            continue

    return False


def fill_standard_inputs(driver):
    """Find and auto-fill candidate fields (Name, Email, Phone, LinkedIn, etc.)."""
    filled_count = 0

    field_mappings = [
        (["first_name", "firstname", "first-name", "fname", "first"], CANDIDATE["first_name"]),
        (["last_name", "lastname", "last-name", "lname", "last"], CANDIDATE["last_name"]),
        (["full_name", "fullname", "candidate_name", "applicant_name", "name"], CANDIDATE["full_name"]),
        (["email", "e-mail", "user_email"], CANDIDATE["email"]),
        (["phone", "mobile", "contact", "telephone", "phone_number"], CANDIDATE["phone"]),
        (["linkedin", "linked_in", "linkedin_profile", "social_media"], CANDIDATE["linkedin"]),
        (["city", "location", "address", "current_location"], CANDIDATE["location"]),
        (["current_company", "company", "employer", "organization"], CANDIDATE["current_company"]),
        (["experience", "total_experience", "years_of_experience", "exp"], CANDIDATE["experience"]),
        (["notice", "notice_period", "availability"], CANDIDATE["notice_period"]),
        (["current_ctc", "current_salary", "present_ctc"], CANDIDATE["current_ctc"]),
        (["expected_ctc", "expected_salary"], CANDIDATE["expected_ctc"]),
    ]

    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email'], input[type='tel'], input:not([type])")

    for inp in inputs:
        try:
            if not inp.is_displayed() or not inp.is_enabled():
                continue

            current_val = inp.get_attribute("value") or ""
            if current_val.strip():
                continue

            inp_id = (inp.get_attribute("id") or "").lower()
            inp_name = (inp.get_attribute("name") or "").lower()
            inp_placeholder = (inp.get_attribute("placeholder") or "").lower()
            inp_aria = (inp.get_attribute("aria-label") or "").lower()

            combined_attr = f"{inp_id} {inp_name} {inp_placeholder} {inp_aria}"

            for keys, value in field_mappings:
                if any(k in combined_attr for k in keys):
                    if keys == ["full_name", "fullname", "candidate_name", "applicant_name", "name"]:
                        if any(x in combined_attr for x in ["first", "last"]):
                            continue

                    driver.execute_script("""
                        arguments[0].focus();
                        arguments[0].value = arguments[1];
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    """, inp, value)
                    filled_count += 1
                    break
        except Exception:
            continue

    # Also handle <select> dropdowns for experience or notice period
    try:
        selects = driver.find_elements(By.CSS_SELECTOR, "select")
        for sel in selects:
            if not sel.is_displayed() or not sel.is_enabled():
                continue
            sel_name = (sel.get_attribute("name") or "").lower() + " " + (sel.get_attribute("id") or "").lower()
            if any(k in sel_name for k in ["experience", "exp", "year"]):
                options = sel.find_elements(By.TAG_NAME, "option")
                for opt in options:
                    txt = opt.text.lower()
                    if "4" in txt or "3-5" in txt or "3 to 5" in txt:
                        driver.execute_script("arguments[0].selected = true; arguments[1].dispatchEvent(new Event('change', {bubbles: true}));", opt, sel)
                        filled_count += 1
                        break
    except Exception:
        pass

    return filled_count


def upload_resume_file(driver):
    """Find input[type='file'] on the page and upload Aman Dubey's CV."""
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


def fill_custom_questions_with_gemini(driver):
    """Find textareas or custom questions on external portal and answer them using Gemini AI."""
    if not gemini_helper.is_gemini_available():
        return 0

    answered = 0
    try:
        textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
        for ta in textareas:
            try:
                if not ta.is_displayed() or not ta.is_enabled():
                    continue
                if (ta.get_attribute("value") or "").strip():
                    continue

                q_text = ""
                ta_id = ta.get_attribute("id")
                if ta_id:
                    labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{ta_id}']")
                    if labels and labels[0].text.strip():
                        q_text = labels[0].text.strip()

                if not q_text:
                    q_text = ta.get_attribute("placeholder") or ta.get_attribute("name") or ta.get_attribute("aria-label") or ""

                if q_text and len(q_text) > 3:
                    logger.info(f"  🤖 Answering portal question with Gemini: '{q_text[:60]}...'")
                    ai_answer = gemini_helper.answer_question(q_text)
                    if ai_answer:
                        driver.execute_script("""
                            arguments[0].focus();
                            arguments[0].value = arguments[1];
                            arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                        """, ta, ai_answer)
                        answered += 1
                        time.sleep(1)
            except Exception:
                continue
    except Exception:
        pass

    return answered


def attempt_submit_application(driver):
    """
    Attempt to click the final submit button across standard HTML,
    Freshteam, Workable, SmartRecruiters, custom buttons, and div/a tags.
    """
    submit_selectors = [
        # Freshteam & Workable
        "button[data-ui='application-submit-btn']",
        "button.freshteam-apply-button",
        # Standard input submit
        "//input[@type='submit']",
        "//input[contains(@value,'Submit') or contains(@value,'Apply') or contains(@value,'Send')]",
        # Button tags
        "//button[contains(translate(.,'SUBMIT','submit'),'submit application')]",
        "//button[contains(translate(.,'SUBMIT','submit'),'submit')]",
        "//button[contains(translate(.,'SEND','send'),'send application') or contains(translate(.,'SEND','send'),'send message') or contains(translate(.,'SEND','send'),'send')]",
        "//button[contains(translate(.,'APPLY','apply'),'apply now') or contains(translate(.,'APPLY','apply'),'submit')]",
        "//button[contains(@class,'submit') or contains(@id,'submit')]",
        "button[type='submit']",
        # Anchor / Div role=button tags
        "//a[contains(translate(.,'SUBMIT','submit'),'submit')]",
        "//div[@role='button' and (contains(translate(.,'SUBMIT','submit'),'submit') or contains(translate(.,'APPLY','apply'),'apply'))]",
        "[class*='submit-btn'], [id*='submit-btn'], [class*='submit_btn'], [id*='submit_btn'], [class*='btn-submit']"
    ]

    for sel in submit_selectors:
        try:
            if sel.startswith("//"):
                btns = driver.find_elements(By.XPATH, sel)
            else:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)

            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    txt = b.text.strip().lower()
                    # Skip search or nav buttons
                    if any(x in txt for x in ["search", "filter", "login", "sign in"]):
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", b)
                    logger.info(f"  🚀 Clicked 'Submit Application' button! ({b.text.strip()[:30]})")
                    time.sleep(4)
                    return True
        except Exception:
            continue

    return False


def process_single_job(driver, job_title, company_name, naukri_url):
    """
    Process a single external job:
    Naukri -> External Portal -> Form Trigger -> Fill Form (inc. iframes) -> Attach Resume -> Submit.
    Returns (status: 'passed' | 'failed', record: dict).
    """
    logger.info("=" * 60)
    logger.info(f"Processing: {job_title} | Company: {company_name}")
    logger.info(f"Naukri URL: {naukri_url}")

    portal_url, nav_error = click_apply_on_naukri(driver, naukri_url)

    if nav_error:
        record = {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url or "N/A",
            "Failure Reason": nav_error,
            "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return "failed", record

    logger.info(f"  🌐 Landed on external portal: {portal_url}")

    # Check for blockers
    blocker_reason = check_for_blockers(driver)
    if blocker_reason:
        record = {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url,
            "Failure Reason": blocker_reason,
            "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return "failed", record

    # Trigger initial ATS apply button if on JD overview page
    trigger_ats_application_form(driver)

    # Fill form fields
    fields_filled = fill_standard_inputs(driver)
    resume_uploaded = upload_resume_file(driver)

    # Iframe fallback: If 0 fields filled, search inside iframes (Zoho Recruit, Google Forms, etc.)
    if fields_filled == 0 and not resume_uploaded:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                f_count = fill_standard_inputs(driver)
                r_uploaded = upload_resume_file(driver)
                if f_count > 0 or r_uploaded:
                    fields_filled = f_count
                    resume_uploaded = r_uploaded
                    logger.info(f"  🔀 Switched inside form iframe (Filled {fields_filled} fields, Resume: {resume_uploaded})")
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

    logger.info(f"  📝 Auto-filled {fields_filled} standard fields (Name, Email, Phone, LinkedIn, etc.)")

    # Custom Questions via Gemini AI
    questions_answered = fill_custom_questions_with_gemini(driver)
    if questions_answered > 0:
        logger.info(f"  💡 Gemini answered {questions_answered} custom questions")

    # If no fields and no resume, form was not detected
    if fields_filled == 0 and not resume_uploaded:
        driver.switch_to.default_content()
        record = {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url,
            "Failure Reason": "No standard application form detected / Custom portal layout",
            "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return "failed", record

    # Submit Application
    if AUTO_SUBMIT:
        submitted = attempt_submit_application(driver)
        # If not submitted in iframe, try switching to default content and submit
        if not submitted:
            driver.switch_to.default_content()
            submitted = attempt_submit_application(driver)

        driver.switch_to.default_content()

        if submitted:
            time.sleep(3)
            record = {
                "Job Title": job_title,
                "Company Name": company_name,
                "Naukri URL": naukri_url,
                "Company Portal URL": portal_url,
                "Applied At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Notes": f"Auto-submitted (Fields: {fields_filled}, Resume: {resume_uploaded}, AI Questions: {questions_answered})"
            }
            return "passed", record
        else:
            record = {
                "Job Title": job_title,
                "Company Name": company_name,
                "Naukri URL": naukri_url,
                "Company Portal URL": portal_url,
                "Failure Reason": "Form filled but could not locate Submit button automatically",
                "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return "failed", record
    else:
        logger.info("  👀 Review Mode: Form is filled! Review in browser and click Submit (waiting 15s)...")
        time.sleep(15)
        driver.switch_to.default_content()
        record = {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url,
            "Applied At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Notes": "Form pre-filled in Review Mode"
        }
        return "passed", record


def main():
    """Main runner for auto-applying to external company jobs."""
    logger.info("=" * 60)
    logger.info("AI External Job Application Agent (Enhanced Edition)")
    logger.info("=" * 60)
    logger.info(f"Resume: {RESUME_PATH}")
    logger.info(f"Candidate: {CANDIDATE['full_name']} | {CANDIDATE['email']} | {CANDIDATE['phone']}")
    logger.info(f"Auto-Submit Mode: {AUTO_SUBMIT}")

    if not os.path.exists(MANUAL_CSV):
        logger.error(f"File not found: {MANUAL_CSV}. Please run Naukri-Edge.py first.")
        return

    df_manual = pd.read_csv(MANUAL_CSV)
    if "Job URL" not in df_manual.columns:
        logger.error("Job URL column not found in manual_apply_jobs.csv")
        return

    external_jobs = df_manual[
        df_manual['Reason'].astype(str).str.contains("External Company Portal", case=False, na=False)
    ]
    logger.info(f"Total external jobs in CSV: {len(external_jobs)}")

    # Smart Skip: ONLY skip jobs that have already PASSED, so failed jobs get retried with enhanced logic!
    already_passed = load_already_passed()
    pending_jobs = external_jobs[~external_jobs['Job URL'].isin(already_passed)]
    logger.info(f"Already passed previously: {len(already_passed)} | Pending to process/retry: {len(pending_jobs)}")

    if len(pending_jobs) == 0:
        logger.info("✨ All external jobs have already been successfully applied and passed!")
        return

    driver = None
    passed_count = 0
    failed_count = 0

    try:
        driver = create_edge_driver()

        # Login to Naukri first so we can click 'Apply on company site'
        logger.info("Logging into Naukri.com...")
        driver.get("https://login.naukri.com/")
        time.sleep(3)

        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "usernameField"))
        )
        email_input.send_keys(CANDIDATE["email"])
        pwd_input = driver.find_element(By.ID, "passwordField")
        pwd_input.send_keys(os.getenv("NAUKRI_PASSWORD", ""))
        pwd_input.send_keys(Keys.ENTER)
        time.sleep(7)

        main_window = driver.current_window_handle

        for idx, (_, row) in enumerate(pending_jobs.iterrows(), 1):
            job_title = str(row.get("Job Title", "Unknown Role"))
            company_name = str(row.get("Company Name", "Unknown Company"))
            naukri_url = str(row.get("Job URL", ""))

            logger.info(f"\n[{idx}/{len(pending_jobs)}] Starting: {job_title}")

            try:
                status, record = process_single_job(driver, job_title, company_name, naukri_url)

                if status == "passed":
                    passed_count += 1
                    record_passed(record)
                else:
                    failed_count += 1
                    record_failed(record)

            except Exception as e:
                logger.error(f"Error processing job: {e}")
                failed_count += 1
                record_failed({
                    "Job Title": job_title,
                    "Company Name": company_name,
                    "Naukri URL": naukri_url,
                    "Company Portal URL": "N/A",
                    "Failure Reason": f"Unexpected Exception: {e}",
                    "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

            # Clean up extra tabs: close all tabs except the main Naukri window
            try:
                driver.switch_to.default_content()
                for handle in driver.window_handles:
                    if handle != main_window:
                        driver.switch_to.window(handle)
                        driver.close()
                driver.switch_to.window(main_window)
            except Exception:
                pass

            time.sleep(2)

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("EXTERNAL APPLICATION SUMMARY")
        logger.info(f"  Successfully Passed/Applied: {passed_count}")
        logger.info(f"  Failed (Needs Manual Check):  {failed_count}")
        logger.info(f"  Passed Sheet:                external_applied_passed.csv")
        logger.info(f"  Failed Sheet:                external_applied_failed.csv")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"Fatal error in external agent: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
