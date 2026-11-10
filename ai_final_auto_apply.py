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
   - Auto-fill all standard candidate fields from Aman Dubey's CV
   - Answer recruiter custom questions and textareas using full CV context
   - Attach aman_dubey_cv.pdf
   - Locate and click the 'Submit' button
4. DYNAMIC SHEET MANAGEMENT (as requested):
   - When a job PASSES:
     -> Appended to 'external_applied_passed.csv'
     -> REMOVED from 'manual_apply_jobs.csv' and 'external_applied_failed.csv'
   - When a job FAILS:
     -> Retained in 'external_applied_failed.csv' with exact reason for manual review.
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

CV_PDF = os.path.join(BASE_DIR, "aman_dubey_cv.pdf")
CV_DOCX = os.path.join(BASE_DIR, "aman_dubey_cv.docx")
RESUME_PATH = CV_PDF if os.path.exists(CV_PDF) else CV_DOCX

# --- Candidate Profile Details ---
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


def load_all_passed_urls():
    """Load all URLs that have already passed (from passed and applied CSVs)."""
    passed = set()
    for fpath in [PASSED_CSV, APPLIED_CSV]:
        if os.path.exists(fpath):
            try:
                df = pd.read_csv(fpath)
                for col in ['Naukri URL', 'Company Portal URL', 'Job URL']:
                    if col in df.columns:
                        passed.update(df[col].dropna().astype(str).tolist())
            except Exception:
                pass
    return passed


def collect_pending_jobs():
    """
    Consolidate all pending jobs from manual_apply_jobs.csv and external_applied_failed.csv,
    filtering out any job that has already passed.
    Returns a deduplicated list of dicts: [{'title': ..., 'company': ..., 'naukri_url': ...}]
    """
    passed_urls = load_all_passed_urls()
    jobs_dict = {}

    # 1. From manual_apply_jobs.csv
    if os.path.exists(MANUAL_CSV):
        try:
            df_m = pd.read_csv(MANUAL_CSV)
            for _, row in df_m.iterrows():
                url = str(row.get('Job URL', '')).strip()
                if url and url not in passed_urls and url != 'nan':
                    jobs_dict[url] = {
                        "title": str(row.get('Job Title', 'Unknown Role')),
                        "company": str(row.get('Company Name', 'Unknown Company')),
                        "naukri_url": url
                    }
        except Exception as e:
            logger.warning(f"Could not read {MANUAL_CSV}: {e}")

    # 2. From external_applied_failed.csv
    if os.path.exists(FAILED_CSV):
        try:
            df_f = pd.read_csv(FAILED_CSV)
            for _, row in df_f.iterrows():
                url = str(row.get('Naukri URL', '')).strip()
                if url and url not in passed_urls and url != 'nan':
                    if url not in jobs_dict:
                        jobs_dict[url] = {
                            "title": str(row.get('Job Title', 'Unknown Role')),
                            "company": str(row.get('Company Name', 'Unknown Company')),
                            "naukri_url": url
                        }
        except Exception as e:
            logger.warning(f"Could not read {FAILED_CSV}: {e}")

    return list(jobs_dict.values())


def record_passed_and_clean_failed(record):
    """
    1. Append to external_applied_passed.csv.
    2. REMOVE from manual_apply_jobs.csv and external_applied_failed.csv.
    """
    naukri_url = record.get("Naukri URL", "")

    # 1. Append to passed CSV
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
    logger.info(f"  🎉 Saved to external_applied_passed.csv")

    # 2. Remove from manual_apply_jobs.csv
    if os.path.exists(MANUAL_CSV):
        try:
            df_m = pd.read_csv(MANUAL_CSV)
            if 'Job URL' in df_m.columns:
                before_len = len(df_m)
                df_m = df_m[df_m['Job URL'] != naukri_url]
                if len(df_m) < before_len:
                    df_m.to_csv(MANUAL_CSV, index=False)
                    logger.info(f"  🗑️ Removed from manual_apply_jobs.csv")
        except Exception as e:
            logger.warning(f"Could not update {MANUAL_CSV}: {e}")

    # 3. Remove from external_applied_failed.csv
    if os.path.exists(FAILED_CSV):
        try:
            df_f = pd.read_csv(FAILED_CSV)
            if 'Naukri URL' in df_f.columns:
                before_len = len(df_f)
                df_f = df_f[df_f['Naukri URL'] != naukri_url]
                if len(df_f) < before_len:
                    df_f.to_csv(FAILED_CSV, index=False)
                    logger.info(f"  🗑️ Removed from external_applied_failed.csv")
        except Exception as e:
            logger.warning(f"Could not update {FAILED_CSV}: {e}")


def update_failed_record(record):
    """Update or append failure record in external_applied_failed.csv."""
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
    logger.info(f"  ⚠️ Recorded failure in external_applied_failed.csv ({record['Failure Reason']})")


def click_apply_on_naukri(driver, naukri_url):
    """Navigate to Naukri and click 'Apply on company site' to open external tab."""
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
    """Detect hard blockers: 404, Captcha, Workday mandatory sign-in."""
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


def ai_read_and_trigger_form(driver):
    """
    Use heuristic patterns + Gemini AI to read page buttons and click the one
    that opens the application form (Workable, SmartRecruiters, Keka, Zoho, etc.).
    """
    ats_quick_selectors = [
        "[data-ui='overview-apply-btn']",
        "[data-ui='application-form-tab']",
        "a[href*='#apply']",
        "[data-qa='apply-button']",
        "[data-action='apply']",
        "button[data-testid='apply-button']",
        "//a[contains(text(),\"I'm interested\") or contains(text(),'Apply')]",
        "//button[contains(text(),\"I'm interested\") or contains(text(),'Apply')]",
        ".apply-btn",
        ".apply-button",
        "#apply-button",
    ]

    for sel in ats_quick_selectors:
        try:
            btns = driver.find_elements(By.XPATH, sel) if sel.startswith("//") else driver.find_elements(By.CSS_SELECTOR, sel)
            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    href = b.get_attribute("href") or ""
                    if any(x in href for x in ["mailto:", "linkedin.com", "twitter.com"]):
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", b)
                    logger.info(f"  👉 Clicked apply button: '{b.text.strip()[:30]}'")
                    time.sleep(3)
                    return True
        except Exception:
            continue

    # If quick selectors did not match, collect visible buttons & ask Gemini AI!
    try:
        visible_btns = driver.find_elements(By.CSS_SELECTOR, "button, a.btn, a.button, div[role='button']")
        btn_labels = []
        btn_elements = []
        for b in visible_btns:
            if b.is_displayed():
                txt = b.text.strip()
                if txt and len(txt) < 40 and not any(x in txt.lower() for x in ["search", "menu", "login", "cookie"]):
                    btn_labels.append(txt)
                    btn_elements.append(b)

        if btn_labels:
            ai_chosen = gemini_helper.pick_best_button(btn_labels[:15], intent="open_apply")
            if ai_chosen:
                for b in btn_elements:
                    if b.text.strip().lower() == ai_chosen.lower():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", b)
                        logger.info(f"  🤖 Gemini AI identified apply trigger: '{ai_chosen}'")
                        time.sleep(3)
                        return True
    except Exception:
        pass

    return False


def fill_form_fields(driver):
    """Fill standard form inputs (Name, Email, Phone, LinkedIn, Location, Experience)."""
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

    # Handle dropdowns
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
    """Locate file upload element and attach Aman Dubey's CV."""
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
    """Answer all visible textareas using Gemini AI loaded with Aman Dubey's CV."""
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
                    logger.info(f"  🤖 Asking Gemini AI: '{q_text[:60]}...'")
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


def attempt_submit_with_ai(driver):
    """Find and click the Submit button using selectors + Gemini AI."""
    submit_selectors = [
        "button[data-ui='application-submit-btn']",
        "button.freshteam-apply-button",
        "//input[@type='submit']",
        "//input[contains(@value,'Submit') or contains(@value,'Apply') or contains(@value,'Send')]",
        "//button[contains(translate(.,'SUBMIT','submit'),'submit application')]",
        "//button[contains(translate(.,'SUBMIT','submit'),'submit')]",
        "//button[contains(translate(.,'SEND','send'),'send application') or contains(translate(.,'SEND','send'),'send')]",
        "//button[contains(translate(.,'APPLY','apply'),'apply now') or contains(translate(.,'APPLY','apply'),'submit')]",
        "button[type='submit']",
        "//a[contains(translate(.,'SUBMIT','submit'),'submit')]",
        "//div[@role='button' and (contains(translate(.,'SUBMIT','submit'),'submit') or contains(translate(.,'APPLY','apply'),'apply'))]",
        "[class*='submit-btn'], [id*='submit-btn'], [class*='submit_btn'], [id*='submit_btn'], [class*='btn-submit']"
    ]

    for sel in submit_selectors:
        try:
            btns = driver.find_elements(By.XPATH, sel) if sel.startswith("//") else driver.find_elements(By.CSS_SELECTOR, sel)
            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    txt = b.text.strip().lower()
                    if any(x in txt for x in ["search", "filter", "login", "sign in"]):
                        continue
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", b)
                    logger.info(f"  🚀 Clicked Submit button ({b.text.strip()[:30]})")
                    time.sleep(4)
                    return True
        except Exception:
            continue

    # AI Button Pick as fallback
    try:
        visible_btns = driver.find_elements(By.CSS_SELECTOR, "button, a.btn, input[type='button'], div[role='button']")
        btn_labels = []
        btn_elements = []
        for b in visible_btns:
            if b.is_displayed():
                txt = b.text.strip() or b.get_attribute("value") or ""
                if txt and len(txt) < 35:
                    btn_labels.append(txt)
                    btn_elements.append(b)

        if btn_labels:
            ai_submit = gemini_helper.pick_best_button(btn_labels[:15], intent="submit")
            if ai_submit:
                for b in btn_elements:
                    txt = b.text.strip() or b.get_attribute("value") or ""
                    if txt.lower() == ai_submit.lower():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", b)
                        logger.info(f"  🤖 Gemini AI submitted via button: '{ai_submit}'")
                        time.sleep(4)
                        return True
    except Exception:
        pass

    return False


def process_single_job_full_ai(driver, job_title, company_name, naukri_url):
    """Execute complete end-to-end AI application flow."""
    logger.info("=" * 60)
    logger.info(f"AI Processing: {job_title} | Company: {company_name}")
    logger.info(f"Naukri URL: {naukri_url}")

    portal_url, nav_error = click_apply_on_naukri(driver, naukri_url)

    if nav_error:
        return "failed", {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url or "N/A",
            "Failure Reason": nav_error,
            "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    logger.info(f"  🌐 Landed on external portal: {portal_url}")

    # Check for hard blockers
    blocker = check_for_blockers(driver)
    if blocker:
        return "failed", {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url,
            "Failure Reason": blocker,
            "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    # Trigger form via AI or ATS pattern
    ai_read_and_trigger_form(driver)

    # Fill form fields
    fields_filled = fill_form_fields(driver)
    resume_uploaded = upload_resume_file(driver)

    # Iframe fallback
    if fields_filled == 0 and not resume_uploaded:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                f_count = fill_form_fields(driver)
                r_up = upload_resume_file(driver)
                if f_count > 0 or r_up:
                    fields_filled = f_count
                    resume_uploaded = r_up
                    logger.info(f"  🔀 Switched inside form iframe (Fields: {fields_filled}, Resume: {resume_uploaded})")
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

    logger.info(f"  📝 Fields filled: {fields_filled} | Resume Attached: {resume_uploaded}")

    # Custom Questions via Gemini AI
    questions_answered = fill_ai_custom_questions(driver)
    if questions_answered > 0:
        logger.info(f"  💡 Gemini answered {questions_answered} custom questions")

    # If nothing could be filled or uploaded, report layout issue
    if fields_filled == 0 and not resume_uploaded:
        driver.switch_to.default_content()
        return "failed", {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url,
            "Failure Reason": "No standard application form detected / Custom layout",
            "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    # Submit Application
    if AUTO_SUBMIT:
        submitted = attempt_submit_with_ai(driver)
        if not submitted:
            driver.switch_to.default_content()
            submitted = attempt_submit_with_ai(driver)

        driver.switch_to.default_content()

        if submitted:
            time.sleep(3)
            return "passed", {
                "Job Title": job_title,
                "Company Name": company_name,
                "Naukri URL": naukri_url,
                "Company Portal URL": portal_url,
                "Applied At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Notes": f"Full AI Submitted (Fields: {fields_filled}, Resume: {resume_uploaded}, AI Questions: {questions_answered})"
            }
        else:
            return "failed", {
                "Job Title": job_title,
                "Company Name": company_name,
                "Naukri URL": naukri_url,
                "Company Portal URL": portal_url,
                "Failure Reason": "Form filled & resume uploaded, but submit button could not be clicked automatically",
                "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    else:
        logger.info("  👀 Review Mode: Waiting 15s for manual review...")
        time.sleep(15)
        driver.switch_to.default_content()
        return "passed", {
            "Job Title": job_title,
            "Company Name": company_name,
            "Naukri URL": naukri_url,
            "Company Portal URL": portal_url,
            "Applied At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Notes": "Form pre-filled in Review Mode"
        }


def main():
    """Main runner for the Final Autonomous AI Job Application Agent."""
    logger.info("=" * 60)
    logger.info("FINAL AUTONOMOUS AI JOB APPLICATION AGENT (ai_final_auto_apply.py)")
    logger.info("=" * 60)
    logger.info(f"Resume: {RESUME_PATH}")
    logger.info(f"Candidate: {CANDIDATE['full_name']} | {CANDIDATE['email']} | {CANDIDATE['phone']}")
    logger.info(f"Gemini AI Active: {gemini_helper.is_gemini_available()}")

    pending_jobs = collect_pending_jobs()
    logger.info(f"📊 Total pending jobs to process: {len(pending_jobs)}")

    if not pending_jobs:
        logger.info("✨ Congratulations! No pending jobs left to apply. All jobs are already passed!")
        return

    driver = None
    passed_count = 0
    failed_count = 0

    try:
        driver = create_edge_driver()

        # Login to Naukri
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

        for idx, job in enumerate(pending_jobs, 1):
            job_title = job["title"]
            company_name = job["company"]
            naukri_url = job["naukri_url"]

            logger.info(f"\n[{idx}/{len(pending_jobs)}] Processing: {job_title} ({company_name})")

            try:
                status, record = process_single_job_full_ai(driver, job_title, company_name, naukri_url)

                if status == "passed":
                    passed_count += 1
                    # Save to passed AND REMOVE from manual_apply_jobs.csv and external_applied_failed.csv!
                    record_passed_and_clean_failed(record)
                else:
                    failed_count += 1
                    update_failed_record(record)

            except Exception as e:
                logger.error(f"Error processing job: {e}")
                failed_count += 1
                update_failed_record({
                    "Job Title": job_title,
                    "Company Name": company_name,
                    "Naukri URL": naukri_url,
                    "Company Portal URL": "N/A",
                    "Failure Reason": f"Unexpected Exception: {e}",
                    "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

            # Clean extra tabs
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
        logger.info("FINAL AI AGENT RUN SUMMARY")
        logger.info(f"  Successfully Passed & Applied: {passed_count}")
        logger.info(f"  Remaining Failed (Manual):     {failed_count}")
        logger.info(f"  Clean Passed Sheet:            external_applied_passed.csv")
        logger.info(f"  Remaining Failed Sheet:        external_applied_failed.csv")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"Fatal error in Final AI Agent: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
