"""Open the public app in a real browser so Streamlit Community Cloud keeps it awake.

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.
If the app has gone to sleep, press the "wake up" button and wait for it to load.
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://cold-movers.streamlit.app/")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL, timeout=120_000, wait_until="domcontentloaded")
    page.wait_for_timeout(10_000)
    wake = page.get_by_role("button", name=re.compile(r"get this app back up", re.I))
    if wake.count():
        print("App was asleep: pressing the wake-up button")
        wake.first.click()
        page.wait_for_timeout(90_000)
    else:
        print("App is awake")
    page.wait_for_timeout(5_000)
    print("Page title:", page.title())
    browser.close()
sys.exit(0)
