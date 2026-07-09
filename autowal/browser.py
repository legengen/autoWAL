import os
import tempfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMEDRIVER = os.path.join(PROJECT_ROOT, "drivers", "chromedriver-win64", "chromedriver.exe")


def init_driver(headless=False):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--user-data-dir=" + tempfile.mkdtemp(prefix="auto-fill-chrome-"))
    opts.add_argument("--incognito")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-features=TranslateUI")

    service = Service(CHROMEDRIVER) if os.path.exists(CHROMEDRIVER) else None
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
    return driver
