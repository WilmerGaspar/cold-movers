"""Take screenshots of the public app in a real browser (runs on GitHub Actions).

AI-assisted code (Claude, Anthropic), directed and reviewed by team Cold Movers.
Saves docs/screens/*.png so the team can see what a judge sees, on desktop and phone.
"""

import os
import re
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://cold-movers.streamlit.app/")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screens")
os.makedirs(OUT, exist_ok=True)


def app_frame(page):
    """Streamlit Community Cloud shows the app inside an iframe; use it if present."""
    for fr in page.frames:
        if "/~/+/" in fr.url:
            return fr
    return page.main_frame


def open_app(page, query):
    page.goto(URL + query, timeout=180_000, wait_until="domcontentloaded")
    page.wait_for_timeout(8_000)
    wake = page.get_by_role("button", name=re.compile(r"get this app back up", re.I))
    if wake.count():
        print("App was asleep: waking it")
        wake.first.click()
        page.wait_for_timeout(90_000)
    fr = app_frame(page)
    fr.get_by_text("At a glance", exact=False).first.wait_for(timeout=180_000)
    page.wait_for_timeout(6_000)
    return fr


with sync_playwright() as p:
    browser = p.chromium.launch()

    # Desktop
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    fr = open_app(page, "?object=wise0855")
    page.screenshot(path=os.path.join(OUT, "desktop_top.png"))
    # Click test: switch objects several times in a row; each click must load the new object.
    for name in ("R Draconis", "TRAPPIST-1", "Epsilon Indi B", "RW Aurigae", "Barnard's Star"):
        try:
            fr.get_by_text(f"{name} ·", exact=False).first.click()
            ok = False
            for _ in range(24):
                page.wait_for_timeout(2_500)
                if fr.locator("h3", has_text=name).count():
                    ok = True
                    break
            print(f"click test {name}: {'OK' if ok else 'DID NOT LOAD'}")
        except Exception as exc:
            print(f"click test {name}: error {exc}")
    fr = open_app(page, "?object=wise0855")
    try:
        toggle = fr.get_by_text("Overlay Gaia DR3 stars").first
        toggle.scroll_into_view_if_needed()
        toggle.click()
        outcome = "nothing appeared"
        for _ in range(30):  # up to ~2.5 minutes
            page.wait_for_timeout(5_000)
            if fr.get_by_text("What you see.").count():
                outcome = "atlas image shown"
                break
            if fr.get_by_text("did not answer").count():
                outcome = "service did not answer (message shown)"
                break
        print("atlas:", outcome)
        toggle.scroll_into_view_if_needed()
        page.mouse.wheel(0, 250)
        page.wait_for_timeout(3_000)
        page.screenshot(path=os.path.join(OUT, "atlas.png"))
        print("atlas screenshot saved")
    except Exception as exc:
        print("atlas screenshot failed:", exc)
    for label, name in (("1 · The sky, visit by visit", "movie"), ("2 · Its light", "spectrum"),
                        ("4 · Is it real", "is_it_real")):
        try:
            el = fr.get_by_text(label, exact=False).first
            el.scroll_into_view_if_needed()
            page.wait_for_timeout(3_000)
            page.screenshot(path=os.path.join(OUT, f"desktop_{name}.png"))
        except Exception as exc:
            print(f"{name} screenshot failed:", exc)
    page.close()

    # Phone
    phone = p.devices["iPhone 13"]
    ctx = browser.new_context(**phone)
    page = ctx.new_page()
    open_app(page, "?object=barnard")
    page.screenshot(path=os.path.join(OUT, "phone_top.png"))
    ctx.close()
    browser.close()
print("done")
sys.exit(0)
