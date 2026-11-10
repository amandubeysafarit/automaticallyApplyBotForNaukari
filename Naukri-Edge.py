"""
Naukri Auto-Apply Bot - Microsoft Edge Version (Updated for Naukri.com 2026)
================================================================================
Automates job applications on Naukri.com using Selenium with Edge browser.
Opens each job keyword search in a separate tab for faster collection.

Usage:
    1. Copy .env.example to .env and fill in your details
    2. pip install -r requirements.txt
    3. python Naukri-Edge.py

Requirements:
    - Edge browser installed
    - Dependencies from requirements.txt
"""

import os
import time
import logging
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from bs4 import BeautifulSoup
from datetime import datetime

# Try to use webdriver-manager for automatic driver management
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
load_dotenv()

# --- Naukri Credentials ---
NAUKRI_EMAIL = os.getenv('NAUKRI_EMAIL', '')
NAUKRI_PASSWORD = os.getenv('NAUKRI_PASSWORD', '')

# --- Personal Details ---
FIRSTNAME = os.getenv('FIRSTNAME', '')
LASTNAME = os.getenv('LASTNAME', '')

# --- Job Search ---
KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', '').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', '').strip()

# --- Limits ---
MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '50'))
PAGES_PER_KEYWORD = int(os.getenv('PAGES_PER_KEYWORD', '2'))

# --- Edge Driver Path (optional, only if NOT using webdriver-manager) ---
EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '')

# ------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def validate_config():
    """Check that required configuration values are set."""
    errors = []
    if not NAUKRI_EMAIL:
        errors.append("NAUKRI_EMAIL is not set in .env")
    if not NAUKRI_PASSWORD:
        errors.append("NAUKRI_PASSWORD is not set in .env")
    if not KEYWORDS:
        errors.append("KEYWORDS is not set in .env (comma-separated job roles)")
    if not FIRSTNAME:
        errors.append("FIRSTNAME is not set in .env")
    if not LASTNAME:
        errors.append("LASTNAME is not set in .env")
    if errors:
        for e in errors:
            logger.error(e)
        logger.error("Please copy .env.example to .env and fill in your details.")
        return False
    return True


def create_edge_driver():
    """Create and return an Edge WebDriver instance."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # Uncomment the line below to run in headless mode (no visible browser)
    # options.add_argument("--headless=new")

    if WEBDRIVER_MANAGER_AVAILABLE:
        logger.info("Using webdriver-manager to auto-download EdgeDriver...")
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH:
        logger.info(f"Using EdgeDriver at: {EDGE_DRIVER_PATH}")
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        logger.info("No driver path specified; assuming EdgeDriver is in PATH...")
        service = EdgeService()

    driver = webdriver.Edge(service=service, options=options)
    return driver


def login_naukri(driver):
    """Log in to Naukri.com."""
    logger.info("Logging in to Naukri.com...")
    driver.get('https://login.naukri.com/')
    time.sleep(3)

    # Wait for username field
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'usernameField'))
    )

    uname = driver.find_element(By.ID, 'usernameField')
    uname.send_keys(NAUKRI_EMAIL)

    passwd = driver.find_element(By.ID, 'passwordField')
    passwd.send_keys(NAUKRI_PASSWORD)
    passwd.send_keys(Keys.ENTER)

    # Wait for login to complete
    time.sleep(8)
    logger.info("Login completed.")


def build_search_urls():
    """
    Build all search URLs for every keyword and page combination.
    Naukri.com URL formats:
      - Normal: /{keyword}-jobs-in-{location}
      - Remote: /{keyword}-jobs?wfhType=2
    Returns a list of (keyword, url) tuples.
    """
    urls = []
    is_remote = LOCATION.lower().strip() in ['remote', 'wfh', 'work from home', 'work-from-home']

    for keyword in KEYWORDS:
        keyword_slug = keyword.lower().replace(' ', '-')
        for page_num in range(1, PAGES_PER_KEYWORD + 1):
            if is_remote:
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs?wfhType=2"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-{page_num}?wfhType=2"
            elif not LOCATION:
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-{page_num}"
            else:
                location_slug = LOCATION.lower().replace(' ', '-')
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{location_slug}"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{location_slug}-{page_num}"
            urls.append((keyword, url))
    return urls


def open_tabs_parallel(driver, search_urls):
    """
    Open all search URLs in parallel browser tabs.
    The first URL opens in the current tab; the rest open in new tabs.
    Returns the original window handle.
    """
    original_window = driver.current_window_handle

    if not search_urls:
        return original_window

    # Open first URL in current tab
    keyword, first_url = search_urls[0]
    logger.info(f"[Tab: Main] Opening: {first_url}")
    driver.get(first_url)
    time.sleep(3)

    # Open remaining URLs in new tabs
    for keyword, url in search_urls[1:]:
        logger.info(f"[Tab: New] Opening: {url}")
        driver.switch_to.new_window('tab')
        driver.get(url)
        time.sleep(2)

    # Switch back to the original tab
    driver.switch_to.window(original_window)
    return original_window


def collect_job_links_from_tab(driver, window_handle):
    """
    Switch to a specific tab, scrape job links from the page.
    Uses updated Naukri.com selectors (as of 2026 redesign).

    Current HTML structure for job cards:
        <div class="srp-jobtuple-wrapper" data-job-id="...">
          <div class="cust-job-tuple layout-wrapper lay-2 sjw__tuple">
            <div class="row1">
              <h2><a class="title " href="https://...">Job Title</a></h2>
            </div>
          </div>
        </div>
    """
    links = []
    try:
        driver.switch_to.window(window_handle)
        time.sleep(3)  # Wait for page to fully render

        soup = BeautifulSoup(driver.page_source, 'html5lib')

        # New selector: find all job tuple wrappers
        job_wrappers = soup.find_all('div', class_='srp-jobtuple-wrapper')
        logger.info(f"[Tab: {driver.title[:50]}] Found {len(job_wrappers)} job cards (srp-jobtuple-wrapper)")

        if not job_wrappers:
            # Fallback: try the older cust-job-tuple class
            job_wrappers = soup.find_all('div', class_='cust-job-tuple')
            logger.info(f"[Tab: {driver.title[:50]}] Found {len(job_wrappers)} job cards (cust-job-tuple fallback)")

        for job_wrapper in job_wrappers:
            # Find the title link - new selector is a.title (class="title ")
            title_link = job_wrapper.find('a', class_='title')
            if title_link and title_link.get('href'):
                href = title_link.get('href')
                # Ensure full URL
                if href.startswith('/'):
                    href = 'https://www.naukri.com' + href
                links.append(href)

    except WebDriverException as e:
        logger.warning(f"[Tab] Error reading tab: {e}")

    return links


def collect_all_jobs_parallel(driver, search_urls):
    """
    Open all keyword search pages in parallel tabs and collect job links from each.
    Returns a deduplicated list of job URLs.
    """
    logger.info("=" * 50)
    logger.info(f"Opening {len(search_urls)} search pages in parallel tabs...")
    logger.info("=" * 50)

    # Open all search URLs in parallel tabs
    original_window = open_tabs_parallel(driver, search_urls)

    # Collect job links from each tab
    all_links = []
    window_handles = driver.window_handles
    logger.info(f"Collecting job links from {len(window_handles)} tabs...")

    for handle in window_handles:
        tab_links = collect_job_links_from_tab(driver, handle)
        all_links.extend(tab_links)

    # Close all extra tabs and return to main
    logger.info("Closing search tabs...")
    for handle in window_handles:
        if handle != original_window:
            try:
                driver.switch_to.window(handle)
                driver.close()
            except WebDriverException:
                pass
    driver.switch_to.window(original_window)

    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for link in all_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    logger.info(f"Total unique job links collected: {len(unique_links)}")
    return unique_links


def extract_job_details(driver):
    """Extract job title and company name from current job page."""
    title = "Unknown Role"
    company = "Unknown Company"
    try:
        title_selectors = [
            "h1.styles_jd-header-title__rZwM1",
            "h1[class*='jd-header-title']",
            "h1.title",
            ".jd-header-title",
            "h1",
        ]
        for sel in title_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els and els[0].text.strip():
                title = els[0].text.strip()
                break

        company_selectors = [
            ".styles_jd-header-comp-name__MvqAI a",
            "[class*='jd-header-comp-name'] a",
            ".comp-name",
            "[class*='comp-name']",
            ".styles_jd-header-comp-name__MvqAI",
        ]
        for sel in company_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els and els[0].text.strip():
                company = els[0].text.strip()
                break
    except Exception:
        pass
    return title, company


def handle_chatbot_with_gemini(driver):
    """
    Handle the chatbot drawer using Gemini AI to answer recruiter questions.
    Returns True if application completes and drawer closes, False if timed out.
    """
    import gemini_helper
    logger.info("  🤖 Handling recruiter questionnaire with Gemini AI...")

    for iteration in range(25):  # 25 * 2s = up to 50 seconds
        time.sleep(2)

        # Check if drawer has closed (means application finished)
        containers = driver.find_elements(By.CSS_SELECTOR, "[id*='ChatbotContainer'], .chatbot_Drawer")
        if not containers or not any(c.is_displayed() for c in containers):
            logger.info("  ✓ Questionnaire completed and drawer closed!")
            return True

        # Check for success message or "Application submitted" inside drawer
        try:
            success_indicators = driver.find_elements(
                By.XPATH,
                "//*[contains(text(),'applied successfully') or contains(text(),'Application sent') or contains(text(),'already applied')]"
            )
            if success_indicators and any(s.is_displayed() for s in success_indicators):
                logger.info("  ✓ Application confirmation detected inside chatbot!")
                return True
        except Exception:
            pass

        # 1. Check for Radio Buttons
        try:
            radio_containers = driver.find_elements(By.CSS_SELECTOR, ".singleselect-radiobutton-container, [class*='radiobutton-container']")
            visible_rc = [rc for rc in radio_containers if rc.is_displayed()]
            if visible_rc:
                rc = visible_rc[0]
                bot_msgs = driver.find_elements(By.CSS_SELECTOR, ".chatbot_ListItem.botItem .msg, .chatbot_ListItem .botMsg .msg, .botItem .msg, [class*='botMsg']")
                q_text = bot_msgs[-1].text.strip() if bot_msgs else "Candidate question"

                labels = rc.find_elements(By.CSS_SELECTOR, ".ssrc__label, label")
                options = [lbl.text.strip() for lbl in labels if lbl.text.strip()]

                if options:
                    logger.info(f"  🤖 Question: '{q_text}' | Options: {options}")
                    answer = gemini_helper.answer_question(q_text, options)
                    logger.info(f"  💡 Gemini Chose: '{answer}'")

                    clicked = False
                    for lbl in labels:
                        if lbl.text.strip().lower() == (answer or '').lower():
                            driver.execute_script("arguments[0].click();", lbl)
                            clicked = True
                            break
                    if not clicked and labels:
                        driver.execute_script("arguments[0].click();", labels[0])

                    time.sleep(1)
                    # Click save / send button
                    save_btns = driver.find_elements(By.CSS_SELECTOR, ".sendMsg, [class*='sendMsg'], button[type='submit']")
                    for sb in save_btns:
                        if sb.is_displayed():
                            driver.execute_script("arguments[0].click();", sb)
                            break
                    time.sleep(2)
                    continue
        except Exception as e:
            logger.debug(f"Radio handle error: {e}")

        # 2. Check for Text input (contenteditable div or input)
        try:
            text_inputs = driver.find_elements(By.CSS_SELECTOR, ".textArea[contenteditable='true'], div[contenteditable='true'], input[type='text']")
            active_input = None
            for ti in text_inputs:
                if ti.is_displayed() and ti.is_enabled():
                    active_input = ti
                    break

            if active_input:
                bot_msgs = driver.find_elements(By.CSS_SELECTOR, ".chatbot_ListItem.botItem .msg, .chatbot_ListItem .botMsg .msg, .botItem .msg, [class*='botMsg']")
                q_text = bot_msgs[-1].text.strip() if bot_msgs else "Candidate question"
                logger.info(f"  🤖 Text Question: '{q_text}'")

                answer = gemini_helper.answer_question(q_text)
                logger.info(f"  💡 Gemini Answer: '{answer}'")

                if answer:
                    driver.execute_script("""
                        arguments[0].focus();
                        arguments[0].innerText = arguments[1];
                        if (arguments[0].value !== undefined) { arguments[0].value = arguments[1]; }
                        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                    """, active_input, answer)
                    time.sleep(0.5)

                    save_btns = driver.find_elements(By.CSS_SELECTOR, ".sendMsg, [class*='sendMsg'], button[type='submit']")
                    for sb in save_btns:
                        if sb.is_displayed():
                            driver.execute_script("arguments[0].click();", sb)
                            break
                    time.sleep(2)
                    continue
        except Exception as e:
            logger.debug(f"Text handle error: {e}")

        # 3. Check for Save/Next/Submit button in drawer
        try:
            action_btns = driver.find_elements(By.XPATH, "//div[contains(@class,'chatbot')]//button[contains(text(),'Save') or contains(text(),'Submit') or contains(text(),'Next')]")
            for ab in action_btns:
                if ab.is_displayed() and ab.is_enabled():
                    driver.execute_script("arguments[0].click();", ab)
                    time.sleep(2)
                    break
        except Exception:
            pass

    return False


def apply_to_jobs(driver, job_links):
    """
    Visit each job link and attempt to apply.
    - If direct 1-click apply works on Naukri -> marks as Applied.
    - If it's 'Apply on company site' (external link), or requires questionnaire,
      or button is missing -> marks as Manual Apply and saves with title, company,
      URL, and reason so you can apply manually.
    """
    applied = 0
    manual_count = 0
    applied_records = []
    manual_apply_records = []

    logger.info("=" * 50)
    logger.info(f"Starting job applications (max: {MAX_APPLICATIONS})...")
    logger.info("=" * 50)

    for i, link in enumerate(job_links, 1):
        if applied >= MAX_APPLICATIONS:
            logger.info(f"Reached max application limit ({MAX_APPLICATIONS}). Stopping.")
            break

        logger.info(f"[{i}/{len(job_links)}] Visiting: {link}")
        try:
            driver.get(link)
            time.sleep(4)
        except WebDriverException as e:
            logger.warning(f"  ✗ Failed to load page: {e}")
            manual_count += 1
            manual_apply_records.append({
                'Job Title': 'Unknown Role',
                'Company Name': 'Unknown Company',
                'Job URL': link,
                'Reason': f'Failed to load page: {e}',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        title, company = extract_job_details(driver)
        logger.info(f"  Job: {title} | Company: {company}")

        # Check if already applied
        try:
            already_applied_els = driver.find_elements(
                By.XPATH,
                "//*[contains(text(),'Already applied') or contains(text(),'Already Applied') or contains(text(),'Applied on')]"
            )
            if already_applied_els and any(el.is_displayed() for el in already_applied_els):
                logger.info("  ℹ Already applied to this job previously. Skipping.")
                continue
        except Exception:
            pass

        # Check if button is "Apply on company site"
        # Since this button redirects to company's external career portal (Workday/Greenhouse/etc.),
        # bot cannot fill external ATS portals. So user must apply manually.
        company_site_btns = driver.find_elements(
            By.XPATH,
            "//button[contains(text(),'Apply on company site')] | //button[@id='company-site-button'] | //button[contains(@class,'company-site-button')]"
        )
        if company_site_btns and any(btn.is_displayed() for btn in company_site_btns):
            logger.info("  ⚠ 'Apply on company site' detected (Redirects to external company career page).")
            logger.info("  -> Added to manual_apply_jobs.csv for manual application.")
            manual_count += 1
            manual_apply_records.append({
                'Job Title': title,
                'Company Name': company,
                'Job URL': link,
                'Reason': 'External Company Portal (Apply on company site)',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        # Look for direct "Apply" button (Naukri 1-click apply)
        direct_apply_btns = driver.find_elements(
            By.XPATH,
            "//button[text()='Apply' or contains(text(),'Apply on Naukri') or (contains(text(),'Apply') and not(contains(text(),'company')))]"
        )
        clickable_btn = None
        for btn in direct_apply_btns:
            if btn.is_displayed():
                clickable_btn = btn
                break

        if not clickable_btn:
            logger.warning("  ✗ No direct Apply button found.")
            manual_count += 1
            manual_apply_records.append({
                'Job Title': title,
                'Company Name': company,
                'Job URL': link,
                'Reason': 'No Apply Button Found / Expired',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        # Attempt to click direct Apply
        try:
            driver.execute_script("arguments[0].click();", clickable_btn)
            time.sleep(3)
        except Exception as e:
            logger.warning(f"  ✗ Error clicking Apply button: {e}")
            manual_count += 1
            manual_apply_records.append({
                'Job Title': title,
                'Company Name': company,
                'Job URL': link,
                'Reason': f'Error clicking Apply: {e}',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        # Check for daily quota expired
        try:
            quota_el = driver.find_elements(By.XPATH, "//*[contains(text(),'daily quota has been expired')]")
            if quota_el and any(q.is_displayed() for q in quota_el):
                logger.info("Daily quota expired. Stopping.")
                manual_apply_records.append({
                    'Job Title': title,
                    'Company Name': company,
                    'Job URL': link,
                    'Reason': 'Daily Quota Expired',
                    'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                break
        except Exception:
            pass

        # Handle custom first/last name fields if present
        try:
            fn_fields = driver.find_elements(By.XPATH, "//input[@id='CUSTOM-FIRSTNAME']")
            if fn_fields and fn_fields[0].is_displayed():
                fn_fields[0].clear()
                fn_fields[0].send_keys(FIRSTNAME)
                logger.info("  Filled custom first name field")
        except Exception:
            pass

        try:
            ln_fields = driver.find_elements(By.XPATH, "//input[@id='CUSTOM-LASTNAME']")
            if ln_fields and ln_fields[0].is_displayed():
                ln_fields[0].clear()
                ln_fields[0].send_keys(LASTNAME)
                logger.info("  Filled custom last name field")
        except Exception:
            pass

        # Handle "Submit and Apply" if present
        try:
            submit_btn = driver.find_elements(By.XPATH, "//*[text()='Submit and Apply' or contains(text(),'Submit & Apply')]")
            if submit_btn and submit_btn[0].is_displayed():
                driver.execute_script("arguments[0].click();", submit_btn[0])
                logger.info("  Clicked 'Submit and Apply'")
                time.sleep(2)
        except Exception:
            pass

        # Check if chatbot questionnaire or complex form is blocking
        try:
            chatbot_open = driver.find_elements(By.CSS_SELECTOR, "[id*='ChatbotContainer'], .chatbot_Drawer, .drawer-wrapper")
            if chatbot_open and any(c.is_displayed() for c in chatbot_open):
                import gemini_helper
                if gemini_helper.is_gemini_available():
                    logger.info("  🤖 Recruiter questionnaire detected! Auto-answering with Gemini AI...")
                    if handle_chatbot_with_gemini(driver):
                        applied += 1
                        applied_records.append({
                            'Job Title': title,
                            'Company Name': company,
                            'Job URL': link,
                            'Applied At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                        logger.info(f"  ✓ Applied successfully with Gemini AI! (Total Applied: {applied})")
                        time.sleep(2)
                        continue
                    else:
                        logger.warning("  ✗ Gemini timed out or could not complete questionnaire.")
                        manual_count += 1
                        manual_apply_records.append({
                            'Job Title': title,
                            'Company Name': company,
                            'Job URL': link,
                            'Reason': 'Chatbot Questionnaire (Gemini timeout/incomplete)',
                            'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                        continue
                else:
                    logger.info("  ℹ Chatbot / Questionnaire required (Add GEMINI_API_KEY in .env to auto-answer).")
                    logger.info("  -> Saved to manual_apply_jobs.csv for manual completion.")
                    manual_count += 1
                    manual_apply_records.append({
                        'Job Title': title,
                        'Company Name': company,
                        'Job URL': link,
                        'Reason': 'Recruiter Questionnaire / Chatbot Form Required (No Gemini Key)',
                        'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    continue
        except Exception as e:
            logger.debug(f"Chatbot handler error: {e}")

        # If we got here, application was successful!
        applied += 1
        applied_records.append({
            'Job Title': title,
            'Company Name': company,
            'Job URL': link,
            'Applied At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        logger.info(f"  ✓ Applied directly! (Total Applied: {applied})")
        time.sleep(2)

    return applied, manual_count, applied_records, manual_apply_records


def save_results(applied_records, manual_apply_records):
    """
    Save applied jobs and manual apply jobs to separate CSVs.
    Appends to existing CSVs if they already exist, avoiding duplicates.
    """
    manual_csv = "manual_apply_jobs.csv"
    applied_csv = "applied_jobs.csv"

    # Save manual apply jobs
    if manual_apply_records:
        df_new_manual = pd.DataFrame(manual_apply_records)
        if os.path.exists(manual_csv):
            try:
                df_existing = pd.read_csv(manual_csv)
                df_combined = pd.concat([df_existing, df_new_manual], ignore_index=True)
                df_combined.drop_duplicates(subset=['Job URL'], keep='last', inplace=True)
                df_combined.to_csv(manual_csv, index=False)
            except Exception:
                df_new_manual.to_csv(manual_csv, index=False)
        else:
            df_new_manual.to_csv(manual_csv, index=False)
        logger.info(f"📋 Manual apply jobs saved to {manual_csv} ({len(manual_apply_records)} jobs)")

    # Save successfully applied jobs
    if applied_records:
        df_new_applied = pd.DataFrame(applied_records)
        if os.path.exists(applied_csv):
            try:
                df_existing = pd.read_csv(applied_csv)
                df_combined = pd.concat([df_existing, df_new_applied], ignore_index=True)
                df_combined.drop_duplicates(subset=['Job URL'], keep='last', inplace=True)
                df_combined.to_csv(applied_csv, index=False)
            except Exception:
                df_new_applied.to_csv(applied_csv, index=False)
        else:
            df_new_applied.to_csv(applied_csv, index=False)
        logger.info(f"✅ Successfully applied jobs saved to {applied_csv} ({len(applied_records)} jobs)")

    # Also maintain legacy naukriapplied.csv for backward compatibility
    try:
        legacy_csv = "naukriapplied.csv"
        applied_urls = [r['Job URL'] for r in applied_records]
        failed_urls = [r['Job URL'] for r in manual_apply_records]
        df_legacy = pd.DataFrame({
            'passed': pd.Series(applied_urls),
            'failed': pd.Series(failed_urls)
        })
        df_legacy.to_csv(legacy_csv, index=False)
    except Exception:
        pass


def load_already_processed_urls():
    """Load all URLs already saved in applied_jobs.csv and manual_apply_jobs.csv to skip re-processing."""
    urls = set()
    for filename in ["applied_jobs.csv", "manual_apply_jobs.csv", "naukriapplied.csv"]:
        if os.path.exists(filename):
            try:
                df = pd.read_csv(filename)
                for col in ['Job URL', 'passed', 'failed']:
                    if col in df.columns:
                        urls.update(df[col].dropna().astype(str).tolist())
            except Exception:
                pass
    return urls


def main():
    """Main entry point for the bot."""
    logger.info("=" * 50)
    logger.info("Naukri Auto-Apply Bot (Edge Edition - 2026 Update)")
    logger.info("=" * 50)

    if not validate_config():
        return

    logger.info(f"Keywords: {KEYWORDS}")
    logger.info(f"Location: {LOCATION or 'Anywhere'}")
    logger.info(f"Max applications: {MAX_APPLICATIONS}")
    logger.info(f"Pages per keyword: {PAGES_PER_KEYWORD}")

    driver = None
    try:
        # Initialize browser
        driver = create_edge_driver()

        # Login
        login_naukri(driver)

        # Build all search URLs
        search_urls = build_search_urls()
        logger.info(f"Total search pages to open: {len(search_urls)}")

        # Collect all job links in parallel (multi-tab)
        job_links = collect_all_jobs_parallel(driver, search_urls)

        if not job_links:
            logger.warning("No job links found. Check your keywords and location.")
            return

        # Smart Filter: Skip already processed jobs
        processed_urls = load_already_processed_urls()
        fresh_job_links = [l for l in job_links if l not in processed_urls]
        logger.info(f"Total collected: {len(job_links)} | Already processed previously: {len(job_links) - len(fresh_job_links)} | Fresh new jobs to process: {len(fresh_job_links)}")

        if not fresh_job_links:
            logger.info("✨ All collected jobs have already been processed in previous runs!")
            logger.info("💡 Tip: Increase PAGES_PER_KEYWORD (e.g. 4 or 5) or add new KEYWORDS in .env to discover more jobs.")
            return

        # Apply to jobs
        applied, manual_count, applied_records, manual_apply_records = apply_to_jobs(driver, fresh_job_links)

        # Save results
        save_results(applied_records, manual_apply_records)

        # Summary
        logger.info("=" * 50)
        logger.info("APPLICATION SUMMARY")
        logger.info(f"  Successfully applied: {applied}")
        logger.info(f"  Needs Manual Apply:  {manual_count}")
        logger.info(f"  Total processed:     {applied + manual_count}")
        logger.info(f"  Applied jobs saved:  applied_jobs.csv")
        logger.info(f"  Manual jobs saved:   manual_apply_jobs.csv")
        logger.info("=" * 50)

    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception:
                pass


if __name__ == "__main__":
    main()