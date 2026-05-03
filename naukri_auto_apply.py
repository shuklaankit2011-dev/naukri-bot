"""
╔══════════════════════════════════════════════════════════╗
║         NAUKRI AUTO-APPLY BOT — Ankit's Job Hunt        ║
║  Roles: Conversational AI | Marketing DS | Entry AI     ║
║  Locations: Bangalore | Remote                          ║
║  Experience: 7+ Years (Senior)                          ║
║  Applies to: Easy Apply + Regular Apply jobs           ║
╚══════════════════════════════════════════════════════════╝

SETUP INSTRUCTIONS:
  1. pip install playwright python-dotenv
  2. playwright install chromium
  3. Create a .env file in the same folder with:
       NAUKRI_EMAIL=your_naukri_email@example.com
       NAUKRI_PASSWORD=your_naukri_password
  4. Run: python naukri_auto_apply.py

OUTPUT:
  - applications_log.csv  →  every job applied to
  - skipped_log.csv       →  jobs skipped (already applied / no easy apply)
  - error_log.txt         →  any errors encountered
"""

import asyncio
import csv
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

load_dotenv()

EMAIL         = os.getenv("NAUKRI_EMAIL")
PASSWORD      = os.getenv("NAUKRI_PASSWORD")
GOOGLE_EMAIL  = os.getenv("GOOGLE_EMAIL")
GOOGLE_PASSWORD = os.getenv("GOOGLE_PASSWORD")

# ── Job keywords to search (sourced from public job boards & Naukri listings) ──
JOB_KEYWORDS = [
    # Entry-level AI roles (broad net)
    "AI Engineer",
    "Machine Learning Engineer",
    "NLP Engineer",
    "Prompt Engineer",
    "AI Trainer",
    "Chatbot Developer",
    "Conversational AI Developer",
    "Junior Data Scientist",
    "AI Analyst",
    "LLM Engineer",
    "Generative AI Engineer",
    "AI Research Associate",
    "Agentic AI Engineer",
]

LOCATIONS = ["Bangalore", "Work from home", "Remote"]   # Naukri uses "Work from home" for remote

EXPERIENCE_MIN = 0    # years (entry-level net)
EXPERIENCE_MAX = 10   # years

MAX_APPLICATIONS_PER_SESSION = 200  # safety cap per run
DELAY_BETWEEN_APPS  = (4, 9)        # seconds (randomised — avoids bot detection)
DELAY_BETWEEN_PAGES = (3, 6)        # seconds between pagination
BROWSER_CHANNEL     = os.getenv("BROWSER_CHANNEL", "chrome")

# ─────────────────────────────────────────────
#  LOGGING SETUP
# ─────────────────────────────────────────────

LOG_DIR = Path(".")
APPLIED_LOG  = LOG_DIR / "applications_log.csv"
SKIPPED_LOG  = LOG_DIR / "skipped_log.csv"
ERROR_LOG    = LOG_DIR / "error_log.txt"

def _init_csv(path, headers):
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(headers)

_init_csv(APPLIED_LOG,  ["Timestamp", "Job Title", "Company", "Location", "URL", "Search Keyword"])
_init_csv(SKIPPED_LOG,  ["Timestamp", "Job Title", "Company", "Reason", "URL"])

def log_applied(title, company, location, url, keyword):
    with open(APPLIED_LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([datetime.now().isoformat(), title, company, location, url, keyword])
    print(f"  ✅  APPLIED → {title} @ {company} ({location})")

def log_skipped(title, company, reason, url):
    with open(SKIPPED_LOG, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([datetime.now().isoformat(), title, company, reason, url])
    print(f"  ⏭  SKIPPED → {title} @ {company} [{reason}]")

def log_error(msg):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    print(f"  ❌  ERROR → {msg}")

# ─────────────────────────────────────────────
#  ALREADY-APPLIED TRACKER  (across sessions)
# ─────────────────────────────────────────────

def load_applied_urls():
    urls = set()
    if APPLIED_LOG.exists():
        with open(APPLIED_LOG, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("URL"):
                    urls.add(row["URL"])
    return urls

# ─────────────────────────────────────────────
#  CORE BOT
# ─────────────────────────────────────────────

async def human_delay(low=1.5, high=3.5):
    await asyncio.sleep(random.uniform(low, high))

COOKIES_FILE = LOG_DIR / "naukri_session.json"

async def is_logged_in(page):
    url = page.url.lower()
    # Not logged in if still on login page
    if "nlogin/login" in url:
        return False
    # Definitely logged in if on a known post-login URL
    logged_in_urls = ["myapplications", "myjobs", "mdr/", "dashboard", "myhome", "naukri.com/"]
    if any(part in url for part in logged_in_urls):
        return True
    # Check DOM for logged-in indicators
    for sel in [
        "a[href*='logout']", "a[href*='myjobs']", "a[href*='myapplications']",
        "div.nI-gNb-drawer__icon", "div.user-info", "span.nI-gNb-user__name",
        "div[class*='userInfo']", "span[class*='userName']",
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                return True
        except Exception:
            pass
    return False

async def login(page):
    import json

    # ── Try saved session cookies first ──
    if COOKIES_FILE.exists():
        print("\n🔐  Loading saved Naukri session...")
        with open(COOKIES_FILE, "r") as f:
            cookies = json.load(f)
        await page.context.add_cookies(cookies)
        await page.goto("https://www.naukri.com", wait_until="domcontentloaded")
        await human_delay(2, 3)
        if await is_logged_in(page):
            print("✅  Session restored — already logged in!")
            return
        print("  ⚠️  Saved session expired, starting fresh login...")

    # ── Manual login: open browser and wait for user to complete Google login ──
    print("\n🔐  Opening Naukri login page...")
    print("    ➡  Please log in manually via Google in the browser window.")
    print("    ➡  The script will continue automatically once you're logged in.")
    print("    ⏳  Waiting up to 3 minutes...\n")

    await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")

    # Wait until user completes login (poll every 3 seconds, up to 5 minutes)
    for i in range(100):
        await asyncio.sleep(3)
        try:
            if await is_logged_in(page):
                break
            if i % 10 == 9:
                remaining = (100 - i - 1) * 3
                print(f"    ⏳  Still waiting... ({remaining}s remaining)")
        except Exception:
            pass
    else:
        raise Exception("Login timed out after 5 minutes — please try again")

    print("✅  Login successful!")

    # Save cookies for future runs
    cookies = await page.context.cookies()
    with open(COOKIES_FILE, "w") as f:
        import json
        json.dump(cookies, f)
    print(f"  💾  Session saved to {COOKIES_FILE.resolve()}")

async def get_recommended_jobs(page):
    """Navigate to recommended jobs page and get job cards."""
    print("\n🔍  Fetching recommended jobs based on profile...")
    await page.goto("https://www.naukri.com/mnjuser/recommendedjobs", wait_until="domcontentloaded")
    await human_delay(*DELAY_BETWEEN_PAGES)
    cards = await _find_job_cards(page, timeout=10000)
    if not cards:
        print("  ⚠️  No recommended jobs found")
    return cards

CARD_SELECTORS = [
    "div.srp-jobtuple-wrapper",
    "article.jobTuple",
    "div[class*='jobTuple']",
    "div.list > div[class*='job']",
    "div[data-job-id]",
]

async def search_jobs(page, keyword, location):
    """Navigate to search results page using Naukri's current URL format."""
    kw = keyword.strip().lower().replace(" ", "-")
    loc = location.strip().lower().replace(" ", "-")
    # Naukri's slug-based URL (e.g. /ai-engineer-jobs-in-bangalore)
    slug_url = f"https://www.naukri.com/{kw}-jobs-in-{loc}"
    # Fallback query-param URL
    kw_q = keyword.replace(" ", "+")
    loc_q = location.replace(" ", "+")
    query_url = f"https://www.naukri.com/jobs?q={kw_q}&l={loc_q}&experience={EXPERIENCE_MIN}"

    print(f"\n🔍  Searching: '{keyword}' in '{location}'")
    try:
        await page.goto(slug_url, wait_until="domcontentloaded")
        await human_delay(*DELAY_BETWEEN_PAGES)
        # If slug URL lands on a no-results / error page, fallback
        cards = await _find_job_cards(page, timeout=5000)
        if not cards:
            raise Exception("No cards on slug URL")
    except Exception:
        await page.goto(query_url, wait_until="domcontentloaded")
        await human_delay(*DELAY_BETWEEN_PAGES)

async def _find_job_cards(page, timeout=10000):
    """Try multiple selectors to find job cards on current page."""
    for sel in CARD_SELECTORS:
        try:
            await page.wait_for_selector(sel, timeout=timeout)
            cards = await page.query_selector_all(sel)
            if cards:
                return cards
        except Exception:
            continue
    return []

async def get_job_cards(page):
    """Return list of job card elements on current page."""
    cards = await _find_job_cards(page)
    if not cards:
        raise Exception("No job cards found")
    return cards

async def extract_job_info(card):
    """Pull title, company, location, URL from a job card."""
    try:
        # Try multiple selector patterns for title/link
        title_el = None
        for sel in ["a.title", "a[class*='title']", "a[href*='naukri.com/job']", "h2 a", "h3 a"]:
            title_el = await card.query_selector(sel)
            if title_el:
                break

        company_el = None
        for sel in ["a.subTitle", "a[class*='comp']", "span[class*='comp']", "div[class*='comp'] a"]:
            company_el = await card.query_selector(sel)
            if company_el:
                break

        loc_el = None
        for sel in ["li.fleft.grey-text", "span[class*='loc']", "li[class*='loc']", "div[class*='location']"]:
            loc_el = await card.query_selector(sel)
            if loc_el:
                break

        title    = (await title_el.inner_text()).strip()   if title_el   else "Unknown Title"
        company  = (await company_el.inner_text()).strip() if company_el else "Unknown Company"
        location = (await loc_el.inner_text()).strip()     if loc_el     else "Unknown Location"
        url      = await title_el.get_attribute("href")   if title_el   else ""

        return title, company, location, url
    except Exception:
        return "Parse Error", "Parse Error", "Parse Error", ""

async def try_apply(page, url):
    """
    Open job page, attempt to apply (Easy Apply or regular Apply).
    Returns: 'applied' | 'already_applied' | 'no_apply' | 'error'
    """
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await human_delay(2, 4)

        # Check if already applied
        already = await page.query_selector("button.already-applied, span.applied-label, div.already-applied")
        if already:
            return "already_applied"

        # Look for Apply button (Easy Apply or regular)
        apply_btn = await page.query_selector("button.apply-button.apply, div.apply-button button, button:has-text('Apply'), button:has-text('Easy Apply')")
        if not apply_btn:
            return "no_apply"

        btn_text = (await apply_btn.inner_text()).strip().lower()
        if "apply" not in btn_text:
            return "no_apply"

        await apply_btn.click()
        await human_delay(2, 4)

        # Handle multi-step modal if it appears (for Easy Apply)
        modal = await page.query_selector("div.apply-modal, div[class*='applyModal']")
        if modal:
            # Try clicking submit/confirm inside modal
            submit = await modal.query_selector("button[type='submit'], button:has-text('Submit'), button:has-text('Apply')")
            if submit:
                await submit.click()
                await human_delay(2, 3)

        # For regular apply, it might redirect or show a message
        # Check for success messages
        success = await page.query_selector(
            "div.success-message, span.success, p:has-text('successfully applied'), "
            "div:has-text('Application submitted'), div[class*='success'], "
            "div:has-text('Applied successfully')"
        )
        if success:
            return "applied"

        # If no explicit success, check if URL changed or page indicates application
        if "apply" in page.url.lower() or "application" in page.url.lower():
            # Assume applied if on application page
            return "applied"

        # If no error, assume applied (optimistic)
        error_el = await page.query_selector("div.error-message, span.error")
        if error_el:
            return "error"

        return "applied"   # Optimistic for both Easy and regular apply

    except PlaywrightTimeout:
        log_error(f"Timeout on {url}")
        return "error"
    except Exception as e:
        log_error(f"Exception on {url}: {str(e)}")
        return "error"

async def go_to_next_page(page):
    """Click next page arrow. Returns False if no next page."""
    try:
        next_btn = None
        for sel in [
            "a[class*='pagination'][class*='next']",
            "a.fright.fs14.btn-secondary",
            "button:has-text('Next')",
            "a:has-text('Next')",
            "[aria-label='Next']",
        ]:
            next_btn = await page.query_selector(sel)
            if next_btn:
                break
        if not next_btn:
            return False
        await next_btn.click()
        await page.wait_for_load_state("networkidle")
        await human_delay(*DELAY_BETWEEN_PAGES)
        return True
    except Exception:
        return False

async def run_bot():
    if not GOOGLE_EMAIL or not GOOGLE_PASSWORD:
        print("❌  Missing credentials! Add GOOGLE_EMAIL and GOOGLE_PASSWORD to your .env file.")
        return

    applied_urls = load_applied_urls()
    total_applied = 0
    session_start = datetime.now()

    print("=" * 60)
    print("  NAUKRI AUTO-APPLY BOT  —  Starting Session")
    print(f"  Time   : {session_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode   : Profile recommendations + Keyword search")
    print(f"  Roles  : {len(JOB_KEYWORDS)} keywords")
    print(f"  Locs   : {', '.join(LOCATIONS)}")
    print(f"  Cap    : {MAX_APPLICATIONS_PER_SESSION} applications/session")
    print("=" * 60)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            channel=BROWSER_CHANNEL,
            headless=False,
            slow_mo=50,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        # Hide webdriver flag so Google doesn't detect automation
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        try:
            await login(page)
        except Exception as e:
            log_error(f"Login failed: {e}")
            await browser.close()
            return

        # Get recommended jobs based on profile
        cards = await get_recommended_jobs(page)
        if cards:
            # Collect all job info first (avoid stale element refs after navigation)
            jobs_on_page = []
            for card in cards:
                info = await extract_job_info(card)
                jobs_on_page.append(info)

            for (title, company, location_text, url) in jobs_on_page:
                if total_applied >= MAX_APPLICATIONS_PER_SESSION:
                    break
                if not url:
                    continue
                if url in applied_urls:
                    log_skipped(title, company, "Already applied (prev session)", url)
                    continue

                result = await try_apply(page, url)

                if result == "applied":
                    log_applied(title, company, location_text, url, "Recommended")
                    applied_urls.add(url)
                    total_applied += 1
                    await asyncio.sleep(random.uniform(*DELAY_BETWEEN_APPS))

                elif result == "already_applied":
                    log_skipped(title, company, "Already applied (Naukri)", url)

                elif result == "no_apply":
                    log_skipped(title, company, "No Apply button", url)

                else:
                    log_skipped(title, company, "Error during apply", url)

                # Go back to recommended jobs page
                await page.go_back(wait_until="domcontentloaded")
                await human_delay(1.5, 3)

        # Now search for jobs based on keywords
        for keyword in JOB_KEYWORDS:
            if total_applied >= MAX_APPLICATIONS_PER_SESSION:
                print(f"\n🏁  Reached session cap of {MAX_APPLICATIONS_PER_SESSION} applications. Stopping.")
                break

            for location in LOCATIONS:
                if total_applied >= MAX_APPLICATIONS_PER_SESSION:
                    break

                await search_jobs(page, keyword, location)
                page_num = 1

                while True:
                    print(f"\n  📄  Page {page_num} — {keyword} | {location}")

                    try:
                        cards = await get_job_cards(page)
                    except PlaywrightTimeout:
                        print(f"  ⚠️  No results found for '{keyword}' in '{location}'")
                        break
                    except Exception as e:
                        log_error(f"get_job_cards failed: {e}")
                        break

                    # Collect all job info first (avoid stale element refs after navigation)
                    jobs_on_page = []
                    for card in cards:
                        info = await extract_job_info(card)
                        jobs_on_page.append(info)

                    for (title, company, location_text, url) in jobs_on_page:
                        if total_applied >= MAX_APPLICATIONS_PER_SESSION:
                            break
                        if not url:
                            continue
                        if url in applied_urls:
                            log_skipped(title, company, "Already applied (prev session)", url)
                            continue

                        result = await try_apply(page, url)

                        if result == "applied":
                            log_applied(title, company, location_text, url, keyword)
                            applied_urls.add(url)
                            total_applied += 1
                            await asyncio.sleep(random.uniform(*DELAY_BETWEEN_APPS))

                        elif result == "already_applied":
                            log_skipped(title, company, "Already applied (Naukri)", url)

                        elif result == "no_apply":
                            log_skipped(title, company, "No Apply button", url)

                        else:
                            log_skipped(title, company, "Error during apply", url)

                        # Go back to search results
                        await page.go_back(wait_until="domcontentloaded")
                        await human_delay(1.5, 3)

                    # Paginate
                    has_next = await go_to_next_page(page)
                    if not has_next:
                        break
                    page_num += 1

        await browser.close()

    # ── Session Summary ──
    duration = datetime.now() - session_start
    print("\n" + "=" * 60)
    print("  SESSION COMPLETE")
    print(f"  Applied  : {total_applied} jobs")
    print(f"  Duration : {str(duration).split('.')[0]}")
    print(f"  Log file : {APPLIED_LOG.resolve()}")
    print("=" * 60)

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(run_bot())
