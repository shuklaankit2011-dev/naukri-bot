# Naukri Auto-Apply Bot

A Python automation bot that logs into [Naukri.com](https://www.naukri.com) and automatically applies to jobs based on configurable keywords and locations. Built with [Playwright](https://playwright.dev/python/) for browser automation.

## Features

- **Google Login support** — logs in via Google OAuth with a one-time manual sign-in; saves the session cookie for all future runs (no repeated login needed)
- **Keyword-based search** — searches across multiple job titles (e.g. AI Engineer, LLM Engineer, Chatbot Developer)
- **Multi-location search** — covers Bangalore, Work from home, and Remote
- **Recommended jobs** — also fetches jobs from your Naukri profile's recommended feed
- **Duplicate prevention** — tracks all applied URLs across sessions; never applies to the same job twice
- **Pagination** — automatically moves through multiple pages of results per keyword
- **Human-like behaviour** — randomised delays between actions to avoid bot detection
- **Anti-detection** — disables Playwright's `webdriver` flag and automation signals
- **CSV logging** — every application and skip is logged with timestamp, company, location, and URL

## Output Files

| File | Description |
|---|---|
| `applications_log.csv` | Every job successfully applied to |
| `skipped_log.csv` | Jobs skipped (already applied / no Apply button) |
| `error_log.txt` | Errors encountered during the run |
| `naukri_session.json` | Saved login session (auto-generated, never commit this) |

## Setup

### 1. Install dependencies

```bash
pip install playwright python-dotenv
playwright install chromium
```

### 2. Create a `.env` file

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
GOOGLE_EMAIL=your_gmail@gmail.com
GOOGLE_PASSWORD=your_gmail_password
BROWSER_CHANNEL=chrome
```

### 3. Run the bot

```bash
python naukri_auto_apply.py
```

On the **first run**, a browser window will open and prompt you to log in manually via Google (Google blocks automated OAuth). Once logged in, the session is saved and all future runs start instantly without any manual step.

## Configuration

Edit the top of `naukri_auto_apply.py` to customise:

```python
JOB_KEYWORDS = [
    "AI Engineer",
    "LLM Engineer",
    "Generative AI Engineer",
    # add or remove keywords here
]

LOCATIONS = ["Bangalore", "Work from home", "Remote"]

MAX_APPLICATIONS_PER_SESSION = 200   # cap per run
DELAY_BETWEEN_APPS  = (4, 9)         # seconds between applications
```

## Security

- **Never commit `.env`** — it contains your login credentials
- **Never commit `naukri_session.json`** — it contains your active login session cookies
- Both files are blocked by `.gitignore`
- Use `.env.example` as a safe template to share the required variables

## Requirements

- Python 3.8+
- Google Chrome installed (used via `channel="chrome"`)
- A Naukri account linked to Google login
