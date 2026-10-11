"""End-to-end UI test in a real (headless) Chromium.

Requires:  pip install playwright && python -m playwright install chromium
Run:       python tests/e2e_ui.py            (starts its own server on port 8765)

A real microphone is not available in a headless browser, so the Web Speech
API is replaced with a fake recogniser that "hears" a fixed sentence. This
checks the full voice path: mic button -> recogniser -> input box -> Ask.
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"
SHOTS = ROOT / "artifacts" / "screenshots"

FAKE_SR = """
window.__heard = 'Kal Gulberg mein hawa kaisi hogi? Kya bachon ko school bhejna chahiye?';
class FakeRecognition {
  start() {
    window.__srLang = this.lang;
    setTimeout(() => {
      this.onstart && this.onstart();
      const res = [[{ transcript: window.__heard }]]; res[0].isFinal = true;
      this.onresult && this.onresult({ results: res });
      this.onend && this.onend();
    }, 50);
  }
  stop() { this.onend && this.onend(); }
}
window.SpeechRecognition = FakeRecognition;
window.webkitSpeechRecognition = FakeRecognition;
"""
NO_SR = "window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined;"


def wait_for_server():
    for _ in range(60):
        try:
            urllib.request.urlopen(URL + "api/health", timeout=1)
            return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("server did not start")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ok -", msg)


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(PORT)],
                              cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            errors = []

            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            page.add_init_script(FAKE_SR)
            page.goto(URL)
            page.wait_for_selector("#haze tbody tr")

            print("Dashboard")
            check(page.locator("#haze tbody tr").count() == 15, "haze grid shows 15 areas")
            check(page.locator("#haze tbody tr").first.locator("td").count() == 11, "1 observed + 10 forecast columns")
            check("early-warning watch" in page.inner_text("#hero-line"), "hero sentence rendered")
            check(page.locator(".metric").count() == 4, "4 metric cards")
            check(page.locator("#map circle").count() == 15, "15 hotspots on the map")
            check(page.locator("#dq li").count() == 6, "6 data-quality checks")
            dq = page.inner_text("#dq")
            check("S07" in dq and "71.8" in dq and "27" in dq and "29" in dq, "S07 flatline and -999 counts shown")
            docs = page.inner_text("#docs")
            check("Superseded by DOC-03" in docs and "Hidden instruction removed" in docs, "document trust flags shown")
            check("Ridge (ours)" in page.inner_text("#model") and "watch" in page.inner_text("#model"), "model card rendered")

            page.click("#haze thead button[data-date='2026-11-03']")
            check(page.get_attribute("#haze thead button[data-date='2026-11-03']", "aria-pressed") == "true", "date selection works")
            check("3 Nov" in page.inner_text("#map-date"), "map follows the selected date")
            page.locator("#map circle").nth(3).click()
            check(page.locator("#area-detail h3").count() == 1, "area detail opens from the map")
            page.screenshot(path=str(SHOTS / "dashboard_desktop.png"), full_page=True)

            print("Voice input")
            page.select_option("#voice-lang", "en-IN")
            page.click("#mic")
            page.wait_for_function("document.getElementById('q').value.length > 10")
            check(page.input_value("#q").startswith("Kal Gulberg mein hawa"), "speech transcript lands in the input box")
            check(page.evaluate("window.__srLang") == "en-IN", "selected voice language passed to the recogniser")

            print("Assistant")
            page.click("#send")
            page.wait_for_selector(".msg.bot .badges")
            bot = page.locator(".msg.bot").last
            check("Forecast tool called" in bot.inner_text(), "forecast badge shown for covered area")
            check(bot.get_attribute("data-language") == "ru", "Roman Urdu detected")
            check(bot.locator(".chip-doc").count() >= 2, "citation chips rendered")
            bot.locator(".json-toggle").click()
            check('"forecast_called": true' in bot.locator("pre.json").inner_text(), "exact ask() JSON viewable")

            page.fill("#q", "What is the forecast for Karachi tomorrow?")
            page.keyboard.press("Enter")
            page.wait_for_function("document.querySelectorAll('.msg.bot .badges').length === 2")
            last = page.locator(".msg.bot").last.inner_text()
            check("No forecast call" in last and "Karachi" in last and "DOC-13" in last, "unsupported city refused")

            page.fill("#q", "<img src=x onerror=alert(1)>")
            page.click("#send")
            page.wait_for_function("document.querySelectorAll('.msg.bot .badges').length === 3")
            check(page.locator(".msg img").count() == 0, "user text is escaped (no HTML injection)")
            page.screenshot(path=str(SHOTS / "dashboard_chat.png"), full_page=False)

            print("Fallbacks and layout")
            nosr = browser.new_page(viewport={"width": 390, "height": 900})
            nosr.on("pageerror", lambda e: errors.append(str(e)))
            nosr.add_init_script(NO_SR)
            nosr.goto(URL)
            nosr.wait_for_selector("#haze tbody tr")
            check(nosr.is_disabled("#mic"), "mic disabled when the browser has no speech API")
            check("not supported" in nosr.inner_text("#mic-status"), "clear message instead of a broken button")
            overflow = nosr.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            check(not overflow, "no horizontal page scroll on a 390px phone")
            nosr.screenshot(path=str(SHOTS / "dashboard_mobile.png"), full_page=True)

            check(not errors, f"no JavaScript errors ({errors})")
            browser.close()
        print("E2E UI: ALL CHECKS PASSED")
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
