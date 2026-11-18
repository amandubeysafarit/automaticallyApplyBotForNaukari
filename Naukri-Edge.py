"""
Naukri Auto-Apply Bot - Unified Master Edition (Shraddha Dwivedi)
================================================================
Single-command, intelligent job application bot for Naukri.com.
- Filters strictly by candidate's preferences (OFSAA, SQL, PL/SQL, Oracle Developer).
- Automatically rejects non-matching jobs (PHP, Laravel, Frontend/Mobile-only, Non-IT, etc.).
- Auto-applies to direct Naukri 1-click jobs.
- Auto-answers recruiter chatbot questionnaires using Gemini AI & Shraddha Dwivedi's CV.
- For 'Apply on company site' jobs, extracts and records the real external company career portal URL.
- Maintains exactly TWO clean, structured CSV files:
    1. applied_jobs.csv       (All successfully applied jobs)
    2. manual_apply_jobs.csv  (Jobs requiring manual action, external company portals, or failed attempts)

Usage:
    python Naukri-Edge.py
"""

import os
import re
import time
import logging
import warnings
from datetime import datetime
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

import gemini_helper

# Suppress deprecation warnings
warnings.filterwarnings('ignore', category=FutureWarning)

# ------------------------------------------------------------
# Configuration & Credentials
# ------------------------------------------------------------
load_dotenv()

NAUKRI_EMAIL = os.getenv('NAUKRI_EMAIL', '').strip()
NAUKRI_PASSWORD = os.getenv('NAUKRI_PASSWORD', '').strip()

FIRSTNAME = os.getenv('FIRSTNAME', 'Shraddha').strip()
LASTNAME = os.getenv('LASTNAME', 'Dwivedi').strip()

# Target Job Search Preferences
default_keywords = 'OFSAA developer, sql developer, plsql developer, oracle plsql developer'
KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', default_keywords).split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', '').strip().lower()

# Parse candidate experience (e.g. '4 years' -> 4)
total_exp_str = os.getenv('TOTAL_EXPERIENCE', '4 years')
exp_match = re.search(r'\d+', total_exp_str)
CANDIDATE_EXP = int(exp_match.group(0)) if exp_match else 4

MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '100'))
PAGES_PER_KEYWORD = int(os.getenv('PAGES_PER_KEYWORD', '2'))

EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '').strip()

# CSV Output Files (ONLY TWO CSV FILES AS REQUIRED)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPLIED_CSV = os.path.join(BASE_DIR, "applied_jobs.csv")
MANUAL_CSV = os.path.join(BASE_DIR, "manual_apply_jobs.csv")

# Try to use webdriver-manager
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# ------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Relevance & Eligibility Filtering Rules (Shraddha Dwivedi)
# ------------------------------------------------------------
EXCLUDED_ROLES_AND_TECHS = [
    # Non-relevant tech stacks & mobile/frontend
    'php', 'laravel', 'wordpress', 'codeigniter', 'magento', 'shopify', 'drupal',
    'react native', 'flutter', 'ios developer', 'android developer', 'swift developer', 'kotlin developer',
    'frontend developer', 'front end developer', 'ui developer', 'ui/ux designer', 'graphic designer',
    # Non-IT / Sales / BPO
    'telecaller', 'inside sales', 'field sales', 'business development executive', 'bde',
    'hr recruiter', 'recruitment executive', 'bpo', 'voice process', 'customer care',
    'content writer', 'copywriter', 'seo executive', 'digital marketer',
    # Hardware / Embedded
    'vlsi', 'embedded c', 'pcb', 'hardware engineer',
    # Senior Leadership / Architect roles far above candidate experience (> 6-7 yrs)
    'director', 'vp', 'vice president', 'general manager', 'chief architect', 'head of engineering'
]

# Core domain target keywords for Shraddha Dwivedi (OFSAA, SQL, PL/SQL, Oracle, Database)
DEFAULT_CORE_KEYWORDS = [
    'ofsaa', 'ofsdf', 'ofsaai', 'fsdf', 'lrm', 'alm',
    'sql', 'plsql', 'pl/sql', 'oracle', 'database developer', 'database engineer',
    'rdbms', 'etl', 'data warehouse', 'data warehousing', 'dwh',
    'performance tuning', 'jasper reports', 'query optimization', 'data migration'
]


def get_all_target_keywords():
    """Combines DEFAULT_CORE_KEYWORDS with user keywords from .env."""
    tokens = set(DEFAULT_CORE_KEYWORDS)
    for kw in KEYWORDS:
        kw_clean = kw.lower().strip()
        if kw_clean:
            tokens.add(kw_clean)
            for part in re.split(r'[\s,\-_/]+', kw_clean):
                if len(part) > 2 and part not in ['developer', 'engineer', 'lead', 'jobs', 'senior']:
                    tokens.add(part)
    return list(tokens)


def parse_experience_range(text):
    """Extract min and max experience in years from strings like '17-25 Yrs', '3-6 years', '4+ yrs'."""
    if not text:
        return 0, 99
    m = re.search(r'(\d+)\s*(?:-|to)\s*(\d+)', str(text))
    if m:
        return int(m.group(1)), int(m.group(2))
    m_single = re.search(r'(\d+)\+?\s*(?:years|yrs)', str(text), re.I)
    if m_single:
        return int(m_single.group(1)), 99
    return 0, 99


def is_job_relevant(title, url, exp_str="", loc_str="", skills_str="", jd_snippet=""):
    """
    Evaluates whether a job matches candidate preferences (Shraddha Dwivedi):
    - Target: OFSAA, SQL, PL/SQL, Oracle Developer, Database Engineer, Application Developer.
    - Reject: PHP, Laravel, Mobile/Frontend-only, Sales, BPO, Hardware, or over-experienced leadership roles.
    - Experience: Candidate has 4 yrs -> reject min_exp > 6 yrs.
    - Location: If LOCATION specified in .env, filter accordingly; if empty, permit all.
    Returns (is_match: bool, reason: str)
    """
    title_lower = (title or "").lower().strip()
    url_lower = (url or "").lower().strip()
    combined_text = f"{title_lower} {url_lower} {(skills_str or '').lower()} {(jd_snippet or '').lower()}"

    target_keywords = get_all_target_keywords()

    # 1. Negative Tech / Role Check
    for exc in EXCLUDED_ROLES_AND_TECHS:
        pattern = r'\b' + re.escape(exc) + r'\b'
        if re.search(pattern, title_lower) or exc in url_lower:
            # If excluded term is in title, only permit if a core database/OFSAA/SQL keyword is explicitly in title
            if not any(k in title_lower for k in ['ofsaa', 'sql', 'plsql', 'pl/sql', 'oracle']):
                return False, f"Excluded role/tech: '{exc}'"

    # 2. Positive Core Skill Check
    has_target_skill = any(k in title_lower or k in url_lower or k in combined_text for k in target_keywords)
    if not has_target_skill:
        # Check if generic application/software developer role
        generic_roles = [
            'application developer', 'software developer', 'software engineer',
            'backend developer', 'database developer', 'database engineer',
            'data engineer', 'consultant', 'associate consultant',
            'technical consultant', 'analyst', 'programmer', 'technical specialist'
        ]
        is_generic = any(r in title_lower for r in generic_roles)
        if not is_generic:
            return False, "Does not match OFSAA/SQL/PLSQL/Oracle target profile"
        # If generic role, skills or description MUST have SQL, PL/SQL, Oracle, Database or OFSAA
        core_db_terms = ['sql', 'plsql', 'pl/sql', 'oracle', 'database', 'ofsaa', 'rdbms', 'etl', 'query']
        if not any(k in combined_text for k in core_db_terms):
            return False, "Generic developer role without SQL/Oracle/OFSAA in skills or JD"

    # 3. Experience Filter
    exp_source = exp_str or url_lower
    min_exp, max_exp = parse_experience_range(exp_source)
    # Candidate has 4 years experience; cannot qualify for 7+, 10+, 17+ yrs roles
    if min_exp > (CANDIDATE_EXP + 2):
        return False, f"Experience required too high ({min_exp}-{max_exp} yrs vs candidate {CANDIDATE_EXP} yrs)"

    # 4. Location Filter (if user specified LOCATION in .env)
    if LOCATION:
        loc_source = f"{loc_str} {url_lower} {combined_text}".lower()
        is_remote_pref = LOCATION in ['remote', 'wfh', 'work from home', 'work-from-home']
        if is_remote_pref:
            remote_indicators = ['remote', 'wfh', 'work from home', 'hybrid', 'india', 'anywhere']
            if not any(ind in loc_source for ind in remote_indicators):
                return False, f"Not remote/WFH (Location: '{loc_str}')"
        else:
            # City specific location check
            loc_target = LOCATION.lower()
            allowed_locs = [loc_target, 'remote', 'wfh', 'hybrid', 'india', 'anywhere']
            if not any(al in loc_source for al in allowed_locs):
                return False, f"Location '{loc_str}' does not match '{LOCATION}'"

    return True, "Matches candidate profile"


# ------------------------------------------------------------
# Driver & Login Setup
# ------------------------------------------------------------
def validate_config():
    """Verify that credentials and essential .env settings are present."""
    if not NAUKRI_EMAIL or not NAUKRI_PASSWORD:
        logger.error("❌ NAUKRI_EMAIL or NAUKRI_PASSWORD is not set in .env")
        return False
    return True


def create_edge_driver():
    """Create and return an Edge WebDriver instance."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # To run silently without browser GUI: options.add_argument("--headless=new")

    if WEBDRIVER_MANAGER_AVAILABLE:
        logger.info("Using webdriver-manager to initialize EdgeDriver...")
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH:
        logger.info(f"Using EdgeDriver at: {EDGE_DRIVER_PATH}")
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        logger.info("Assuming EdgeDriver is in system PATH...")
        service = EdgeService()

    return webdriver.Edge(service=service, options=options)


def login_naukri(driver):
    """Log in to Naukri.com with user credentials."""
    logger.info("Logging in to Naukri.com...")
    driver.get('https://login.naukri.com/')
    time.sleep(3)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'usernameField'))
        )
        uname = driver.find_element(By.ID, 'usernameField')
        uname.clear()
        uname.send_keys(NAUKRI_EMAIL)

        passwd = driver.find_element(By.ID, 'passwordField')
        passwd.clear()
        passwd.send_keys(NAUKRI_PASSWORD)
        passwd.send_keys(Keys.ENTER)

        time.sleep(7)
        logger.info("✓ Login completed.")
    except Exception as e:
        logger.warning(f"Login notice: {e}. Checking if already logged in...")


# ------------------------------------------------------------
# Search & Job Collection
# ------------------------------------------------------------
def build_search_urls():
    """Build search URLs using user's KEYWORDS and LOCATION."""
    urls = []
    is_remote = LOCATION in ['remote', 'wfh', 'work from home', 'work-from-home']

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
                loc_slug = LOCATION.replace(' ', '-')
                if page_num == 1:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{loc_slug}"
                else:
                    url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{loc_slug}-{page_num}"
            urls.append((keyword, url))
    return urls


def collect_job_links_from_tab(driver, window_handle):
    """
    Scrapes job cards from a tab and applies card-level relevance filtering.
    Only returns URLs that strictly match candidate profile.
    """
    valid_links = []
    try:
        driver.switch_to.window(window_handle)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, 'html5lib')
        job_wrappers = soup.find_all('div', class_='srp-jobtuple-wrapper')
        if not job_wrappers:
            job_wrappers = soup.find_all('div', class_='cust-job-tuple')

        logger.info(f"[Tab: {driver.title[:45]}] Found {len(job_wrappers)} job cards")

        for wrapper in job_wrappers:
            title_link = wrapper.find('a', class_='title')
            if not title_link or not title_link.get('href'):
                continue

            href = title_link.get('href')
            if href.startswith('/'):
                href = 'https://www.naukri.com' + href

            card_title = title_link.text.strip() if title_link.text else ""

            # Extract card metadata
            exp_el = wrapper.find(class_=re.compile(r'exp|expwdth', re.I))
            card_exp = exp_el.text.strip() if exp_el else ""

            loc_el = wrapper.find(class_=re.compile(r'loc|locWdth', re.I))
            card_loc = loc_el.text.strip() if loc_el else ""

            tag_els = wrapper.find_all(class_=re.compile(r'tag|chip', re.I))
            card_skills = " ".join([t.text.strip() for t in tag_els if t.text])

            # Pre-filter at Card Level
            relevant, reason = is_job_relevant(
                title=card_title,
                url=href,
                exp_str=card_exp,
                loc_str=card_loc,
                skills_str=card_skills
            )

            if relevant:
                valid_links.append(href)
            else:
                logger.debug(f"  ⏭ Filtered out: '{card_title}' -> {reason}")

    except Exception as e:
        logger.warning(f"[Tab] Error reading tab: {e}")

    return valid_links


def collect_all_jobs_parallel(driver, search_urls):
    """Open search URLs in parallel tabs and collect pre-filtered relevant job URLs."""
    logger.info("=" * 50)
    logger.info(f"Opening {len(search_urls)} search pages in parallel tabs...")
    logger.info("=" * 50)

    original_window = driver.current_window_handle
    if not search_urls:
        return []

    # Open first URL in current tab
    _, first_url = search_urls[0]
    logger.info(f"[Tab: Main] Opening: {first_url}")
    driver.get(first_url)
    time.sleep(2)

    # Open remaining URLs in new tabs
    for _, url in search_urls[1:]:
        logger.info(f"[Tab: New] Opening: {url}")
        driver.switch_to.new_window('tab')
        driver.get(url)
        time.sleep(1.5)

    driver.switch_to.window(original_window)

    all_links = []
    window_handles = driver.window_handles
    logger.info(f"Collecting and filtering relevant jobs from {len(window_handles)} tabs...")

    for handle in window_handles:
        tab_links = collect_job_links_from_tab(driver, handle)
        all_links.extend(tab_links)

    # Close extra tabs
    logger.info("Closing search tabs...")
    for handle in window_handles:
        if handle != original_window:
            try:
                driver.switch_to.window(handle)
                driver.close()
            except Exception:
                pass
    driver.switch_to.window(original_window)

    # Deduplicate while preserving order
    seen = set()
    unique_links = []
    for link in all_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    logger.info(f"Total relevant job links collected: {len(unique_links)}")
    return unique_links


# ------------------------------------------------------------
# Job Details Extraction & Company External URL
# ------------------------------------------------------------
def extract_job_details(driver):
    """Extract job title, company, experience, location, and skills from current page."""
    title = "Unknown Role"
    company = "Unknown Company"
    exp_req = ""
    location = ""
    skills = ""
    jd_text = ""

    # 1. Title
    for sel in ["h1.styles_jd-header-title__rZwM1", "h1[class*='jd-header-title']", "h1.title", ".jd-header-title", "h1"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            title = els[0].text.strip()
            break

    # 2. Company Name
    for sel in [".styles_jd-header-comp-name__MvqAI a", "[class*='jd-header-comp-name'] a", ".comp-name", "[class*='comp-name']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els and els[0].text.strip():
            company = els[0].text.strip()
            break

    # 3. Experience & Location badges
    try:
        exp_els = driver.find_elements(By.CSS_SELECTOR, "[class*='exp'], .styles_jhc__exp__n2GWp, [class*='jhc__exp']")
        if exp_els:
            exp_req = exp_els[0].text.strip()
    except Exception:
        pass

    try:
        loc_els = driver.find_elements(By.CSS_SELECTOR, "[class*='loc'], .styles_jhc__loc___Oq4e, [class*='jhc__loc'], [class*='wfh']")
        if loc_els:
            location = loc_els[0].text.strip()
    except Exception:
        pass

    # 4. Key Skills
    try:
        skill_els = driver.find_elements(By.CSS_SELECTOR, "[class*='styles_key-skill'] a, [class*='key-skills'] a, a.chip")
        if skill_els:
            skills = ", ".join([s.text.strip() for s in skill_els if s.text.strip()])
    except Exception:
        pass

    # 5. JD Snippet
    try:
        jd_els = driver.find_elements(By.CSS_SELECTOR, "section[class*='job-desc'], .styles_job-desc-container__txpYf")
        if jd_els:
            jd_text = jd_els[0].text[:500].strip()
    except Exception:
        pass

    return title, company, exp_req, location, skills, jd_text


def extract_company_external_url(driver, company_btn, job_url):
    """
    Extracts the real external company career portal URL when 'Apply on company site' is present.
    Clicks the button, catches the new tab or redirect, captures the URL, closes the tab, and returns.
    """
    external_url = "N/A"
    original_window = driver.current_window_handle
    existing_handles = set(driver.window_handles)

    # 1. Direct href check on button or anchor
    try:
        href = company_btn.get_attribute("href") or company_btn.get_attribute("data-href") or company_btn.get_attribute("data-url")
        if href and href.startswith("http") and "naukri.com" not in href and "javascript" not in href:
            return href
    except Exception:
        pass

    # 2. Click to trigger redirect / new window
    try:
        driver.execute_script("arguments[0].click();", company_btn)
        time.sleep(3)

        new_handles = set(driver.window_handles) - existing_handles
        if new_handles:
            new_tab = list(new_handles)[0]
            driver.switch_to.window(new_tab)
            time.sleep(3)  # Wait for tracking redirection
            dest_url = driver.current_url
            if dest_url and dest_url.startswith("http") and not dest_url.startswith("about:"):
                external_url = dest_url
            driver.close()
            driver.switch_to.window(original_window)
        else:
            # Check if navigated in current tab
            if driver.current_url != job_url and "naukri.com" not in driver.current_url:
                external_url = driver.current_url
                driver.get(job_url)
                time.sleep(2)
    except Exception as e:
        logger.debug(f"Could not extract external URL by clicking: {e}")
        try:
            driver.switch_to.window(original_window)
        except Exception:
            pass

    return external_url


# ------------------------------------------------------------
# Recruiter Chatbot Questionnaire Handler (Gemini AI)
# ------------------------------------------------------------
def find_and_click_chatbot_save_btn(driver):
    """Locate and click the Save / Submit / Send button inside the chatbot drawer."""
    save_xpaths = [
        "//div[contains(@class,'chatbot') or contains(@id,'Chatbot')]//button[contains(translate(normalize-space(.),'SAVE','save'),'save')]",
        "//div[contains(@class,'chatbot') or contains(@id,'Chatbot')]//button[contains(translate(normalize-space(.),'SUBMIT','submit'),'submit')]",
        "//div[contains(@class,'chatbot') or contains(@id,'Chatbot')]//button[contains(translate(normalize-space(.),'SEND','send'),'send')]",
        "//div[contains(@class,'chatbot') or contains(@id,'Chatbot')]//button[contains(translate(normalize-space(.),'NEXT','next'),'next')]",
        "//button[normalize-space(text())='Save' or text()='Save']",
        "//button[contains(text(),'Save')]"
    ]
    for xpath in save_xpaths:
        try:
            btns = driver.find_elements(By.XPATH, xpath)
            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    driver.execute_script("arguments[0].click();", b)
                    return True
        except Exception:
            pass

    # Try CSS
    for sel in [".sendMsg", "[class*='sendMsg']", "button.saveBtn", "button[class*='save']", "button[type='submit']"]:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    driver.execute_script("arguments[0].click();", b)
                    return True
        except Exception:
            pass

    return False


def handle_chatbot_with_gemini(driver):
    """
    Auto-answers recruiter questionnaire using Gemini AI and Shraddha Dwivedi's CV.
    Returns True on completion, False on timeout.
    """
    logger.info("  🤖 Handling recruiter questionnaire with Gemini AI...")

    for iteration in range(25):  # Up to ~50 seconds
        time.sleep(2)

        # Check if drawer has closed (means application finished)
        containers = driver.find_elements(By.CSS_SELECTOR, "[id*='ChatbotContainer'], .chatbot_Drawer, .drawer-wrapper")
        if not containers or not any(c.is_displayed() for c in containers):
            logger.info("  ✓ Questionnaire completed and drawer closed!")
            return True

        # Check for success indicators
        try:
            success = driver.find_elements(
                By.XPATH,
                "//*[contains(text(),'applied successfully') or contains(text(),'Application sent') or contains(text(),'already applied')]"
            )
            if success and any(s.is_displayed() for s in success):
                logger.info("  ✓ Application confirmation detected inside chatbot!")
                return True
        except Exception:
            pass

        # 1. Radio Options Check
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
                        # Fallback click first valid option
                        driver.execute_script("arguments[0].click();", labels[0])

                    time.sleep(1)
                    find_and_click_chatbot_save_btn(driver)
                    time.sleep(2)
                    continue
        except Exception as e:
            logger.debug(f"Radio handle error: {e}")

        # 2. Text Input Check
        try:
            text_inputs = driver.find_elements(By.CSS_SELECTOR, ".textArea[contenteditable='true'], div[contenteditable='true'], input[type='text'], textarea")
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

                # Insert answer and trigger DOM events
                driver.execute_script("""
                    arguments[0].focus();
                    arguments[0].innerText = arguments[1];
                    if (arguments[0].value !== undefined) { arguments[0].value = arguments[1]; }
                    arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                    arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                """, active_input, answer)
                time.sleep(0.5)

                try:
                    active_input.send_keys(Keys.SPACE)
                    active_input.send_keys(Keys.BACK_SPACE)
                except Exception:
                    pass

                time.sleep(0.5)
                clicked = find_and_click_chatbot_save_btn(driver)
                if not clicked:
                    try:
                        active_input.send_keys(Keys.ENTER)
                    except Exception:
                        pass
                time.sleep(2)
                continue
        except Exception as e:
            logger.debug(f"Text handle error: {e}")

        # 3. Action Buttons check (Save/Next/Submit)
        find_and_click_chatbot_save_btn(driver)

    return False


# ------------------------------------------------------------
# CSV Persistence - ONLY TWO CSV FILES
# ------------------------------------------------------------
def load_already_processed_urls():
    """Load all URLs already present in applied_jobs.csv or manual_apply_jobs.csv."""
    urls = set()
    for path in [APPLIED_CSV, MANUAL_CSV]:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                for col in ['Job URL', 'Job Link', 'Naukri URL']:
                    if col in df.columns:
                        urls.update(df[col].dropna().astype(str).tolist())
            except Exception:
                pass
    return urls


def save_applied_record(record):
    """Save successfully applied job into applied_jobs.csv."""
    df_new = pd.DataFrame([record])
    if os.path.exists(APPLIED_CSV):
        try:
            df_existing = pd.read_csv(APPLIED_CSV)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.drop_duplicates(subset=['Job URL'], keep='last', inplace=True)
            df_combined.to_csv(APPLIED_CSV, index=False)
        except Exception:
            df_new.to_csv(APPLIED_CSV, index=False)
    else:
        df_new.to_csv(APPLIED_CSV, index=False)


def save_manual_record(record):
    """Save manual / external / failed job into manual_apply_jobs.csv."""
    df_new = pd.DataFrame([record])
    if os.path.exists(MANUAL_CSV):
        try:
            df_existing = pd.read_csv(MANUAL_CSV)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.drop_duplicates(subset=['Job URL'], keep='last', inplace=True)
            df_combined.to_csv(MANUAL_CSV, index=False)
        except Exception:
            df_new.to_csv(MANUAL_CSV, index=False)
    else:
        df_new.to_csv(MANUAL_CSV, index=False)


# ------------------------------------------------------------
# Core Application Engine
# ------------------------------------------------------------
def apply_to_jobs(driver, job_links):
    """
    Visits each job link, checks relevance, and executes application:
    - Direct Apply -> applies and saves to applied_jobs.csv
    - Chatbot Questionnaire -> answers via Gemini and saves to applied_jobs.csv
    - Apply on company site -> extracts external URL and saves to manual_apply_jobs.csv
    - Fails/Quota -> saves to manual_apply_jobs.csv with clear reason
    """
    applied = 0
    manual_count = 0
    skipped_count = 0

    logger.info("=" * 50)
    logger.info(f"Starting job evaluation & applications (Max limit: {MAX_APPLICATIONS})...")
    logger.info("=" * 50)

    for i, link in enumerate(job_links, 1):
        if applied >= MAX_APPLICATIONS:
            logger.info(f"Reached maximum application limit ({MAX_APPLICATIONS}). Stopping.")
            break

        logger.info(f"[{i}/{len(job_links)}] Visiting: {link}")
        try:
            driver.get(link)
            time.sleep(4)
        except WebDriverException as e:
            logger.warning(f"  ✗ Failed to load page: {e}")
            manual_count += 1
            save_manual_record({
                'Job Title': 'Unknown Role',
                'Company Name': 'Unknown Company',
                'Job URL': link,
                'Company External URL': 'N/A',
                'Location': 'N/A',
                'Experience': 'N/A',
                'Reason': f'Page Load Error: {str(e)[:100]}',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        title, company, exp_req, location, skills, jd_text = extract_job_details(driver)
        logger.info(f"  Job: {title} | Company: {company} | Exp: {exp_req or 'N/A'} | Loc: {location or 'N/A'}")

        # Page-Level Relevance Verification
        is_rel, reason = is_job_relevant(
            title=title,
            url=link,
            exp_str=exp_req,
            loc_str=location,
            skills_str=skills,
            jd_snippet=jd_text
        )

        if not is_rel:
            logger.info(f"  ⏭ Skipping job: '{title}' - {reason}")
            skipped_count += 1
            continue

        # Check if already applied previously
        try:
            already_applied = driver.find_elements(
                By.XPATH,
                "//*[contains(text(),'Already applied') or contains(text(),'Already Applied') or contains(text(),'Applied on')]"
            )
            if already_applied and any(el.is_displayed() for el in already_applied):
                logger.info("  ℹ Already applied to this job previously. Skipping.")
                continue
        except Exception:
            pass

        # Case 1: 'Apply on company site' detected
        company_site_btns = driver.find_elements(
            By.XPATH,
            "//button[contains(text(),'Apply on company site')] | //button[@id='company-site-button'] | //button[contains(@class,'company-site-button')] | //a[contains(text(),'Apply on company site')]"
        )
        if company_site_btns and any(btn.is_displayed() for btn in company_site_btns):
            logger.info("  ⚠ 'Apply on company site' detected (Redirects to external company career page).")
            ext_url = extract_company_external_url(driver, company_site_btns[0], link)
            logger.info(f"  🔗 Captured Company Website URL: {ext_url}")
            logger.info("  -> Added to manual_apply_jobs.csv for quick manual application.")

            manual_count += 1
            save_manual_record({
                'Job Title': title,
                'Company Name': company,
                'Job URL': link,
                'Company External URL': ext_url,
                'Location': location or LOCATION,
                'Experience': exp_req,
                'Reason': 'External Company Portal (Apply on company site)',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        # Case 2: Direct Naukri Apply Button
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
            logger.warning("  ✗ No direct Apply button found on page.")
            manual_count += 1
            save_manual_record({
                'Job Title': title,
                'Company Name': company,
                'Job URL': link,
                'Company External URL': 'N/A',
                'Location': location or LOCATION,
                'Experience': exp_req,
                'Reason': 'No Apply Button Found / Expired',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        # Click Direct Apply
        try:
            driver.execute_script("arguments[0].click();", clickable_btn)
            time.sleep(3)
        except Exception as e:
            logger.warning(f"  ✗ Error clicking Apply button: {e}")
            manual_count += 1
            save_manual_record({
                'Job Title': title,
                'Company Name': company,
                'Job URL': link,
                'Company External URL': 'N/A',
                'Location': location or LOCATION,
                'Experience': exp_req,
                'Reason': f'Click Apply Error: {str(e)[:100]}',
                'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            continue

        # Check for Daily Quota Expired
        try:
            quota_els = driver.find_elements(By.XPATH, "//*[contains(text(),'daily quota has been expired')]")
            if quota_els and any(q.is_displayed() for q in quota_els):
                logger.warning("❌ Naukri daily application quota expired! Stopping execution.")
                save_manual_record({
                    'Job Title': title,
                    'Company Name': company,
                    'Job URL': link,
                    'Company External URL': 'N/A',
                    'Location': location or LOCATION,
                    'Experience': exp_req,
                    'Reason': 'Naukri Daily Quota Expired',
                    'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                break
        except Exception:
            pass

        # Handle custom first/last name fields if prompted
        try:
            fn_fields = driver.find_elements(By.XPATH, "//input[@id='CUSTOM-FIRSTNAME']")
            if fn_fields and fn_fields[0].is_displayed():
                fn_fields[0].clear()
                fn_fields[0].send_keys(FIRSTNAME)

            ln_fields = driver.find_elements(By.XPATH, "//input[@id='CUSTOM-LASTNAME']")
            if ln_fields and ln_fields[0].is_displayed():
                ln_fields[0].clear()
                ln_fields[0].send_keys(LASTNAME)
        except Exception:
            pass

        # Handle "Submit and Apply" button if prompted
        try:
            submit_btn = driver.find_elements(By.XPATH, "//*[text()='Submit and Apply' or contains(text(),'Submit & Apply')]")
            if submit_btn and submit_btn[0].is_displayed():
                driver.execute_script("arguments[0].click();", submit_btn[0])
                time.sleep(2)
        except Exception:
            pass

        # Check for Recruiter Questionnaire Drawer
        try:
            chatbot_open = driver.find_elements(By.CSS_SELECTOR, "[id*='ChatbotContainer'], .chatbot_Drawer, .drawer-wrapper")
            if chatbot_open and any(c.is_displayed() for c in chatbot_open):
                logger.info("  🤖 Recruiter questionnaire detected! Auto-answering with Gemini AI...")
                if handle_chatbot_with_gemini(driver):
                    applied += 1
                    save_applied_record({
                        'Job Title': title,
                        'Company Name': company,
                        'Job URL': link,
                        'Location': location or LOCATION,
                        'Experience': exp_req,
                        'Application Type': 'Recruiter Questionnaire (Gemini AI)',
                        'Applied At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    logger.info(f"  ✓ Applied successfully with Gemini AI! (Total Applied: {applied})")
                    time.sleep(2)
                    continue
                else:
                    logger.warning("  ✗ Questionnaire timed out or could not complete.")
                    manual_count += 1
                    save_manual_record({
                        'Job Title': title,
                        'Company Name': company,
                        'Job URL': link,
                        'Company External URL': 'N/A',
                        'Location': location or LOCATION,
                        'Experience': exp_req,
                        'Reason': 'Chatbot Questionnaire incomplete',
                        'Checked At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    continue
        except Exception as e:
            logger.debug(f"Chatbot handler error: {e}")

        # Direct application succeeded!
        applied += 1
        save_applied_record({
            'Job Title': title,
            'Company Name': company,
            'Job URL': link,
            'Location': location or LOCATION,
            'Experience': exp_req,
            'Application Type': 'Direct Apply (1-Click)',
            'Applied At': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        logger.info(f"  ✓ Applied directly! (Total Applied: {applied})")
        time.sleep(2)

    return applied, manual_count, skipped_count


# ------------------------------------------------------------
# Main Function
# ------------------------------------------------------------
def main():
    logger.info("=" * 60)
    logger.info("Naukri Auto-Apply Bot - Unified Master Edition (2026)")
    logger.info("=" * 60)

    if not validate_config():
        return

    logger.info(f"Target Keywords:       {KEYWORDS}")
    logger.info(f"Target Location:       {LOCATION or 'Anywhere'}")
    logger.info(f"Candidate Experience:  {CANDIDATE_EXP} years")
    logger.info(f"Max Applications:      {MAX_APPLICATIONS}")
    logger.info(f"Pages per Keyword:     {PAGES_PER_KEYWORD}")

    driver = None
    try:
        driver = create_edge_driver()
        login_naukri(driver)

        search_urls = build_search_urls()
        logger.info(f"Total search pages to process: {len(search_urls)}")

        # Scrape and filter relevant job links
        job_links = collect_all_jobs_parallel(driver, search_urls)

        if not job_links:
            logger.warning("No relevant job links found matching your preferences.")
            return

        # Skip already processed jobs from both CSVs
        processed_urls = load_already_processed_urls()
        fresh_job_links = [l for l in job_links if l not in processed_urls]
        logger.info(f"Total collected: {len(job_links)} | Already processed previously: {len(job_links) - len(fresh_job_links)} | Fresh jobs to evaluate: {len(fresh_job_links)}")

        if not fresh_job_links:
            logger.info("✨ All matching jobs have already been processed in previous runs!")
            logger.info("💡 Tip: Increase PAGES_PER_KEYWORD (e.g. 3 or 4) to discover more jobs.")
            return

        applied, manual_count, skipped_count = apply_to_jobs(driver, fresh_job_links)

        logger.info("=" * 60)
        logger.info("EXECUTION SUMMARY")
        logger.info(f"  Successfully Applied:        {applied}")
        logger.info(f"  Manual / External Portals:   {manual_count}")
        logger.info(f"  Skipped (Non-matching):      {skipped_count}")
        logger.info(f"  Applied CSV File:            {APPLIED_CSV}")
        logger.info(f"  Manual Apply CSV File:       {MANUAL_CSV}")
        logger.info("=" * 60)

    except Exception as e:
        logger.exception(f"An unexpected error occurred during execution: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed safely.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
