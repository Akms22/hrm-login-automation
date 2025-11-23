from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import os
import time

USERNAME = os.getenv("HRM_USERNAME")
PASSWORD = os.getenv("HRM_PASSWORD")

# Chrome options
options = Options()
options.add_argument("--headless=new")   # more stable headless mode
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")

# Auto-deny location popup
prefs = {
    "profile.default_content_setting_values.geolocation": 2  # deny
}
options.add_experimental_option("prefs", prefs)

# Real browser user agent to avoid bot-block
options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36"
)

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

try:
    # 1. Load Login Page
    driver.get("https://hrm.pionova.in/admin/users/login")
    time.sleep(6)

    # Debug screenshot BEFORE login fields
    driver.save_screenshot("page_loaded.png")
    print("Saved debug screenshot: page_loaded.png")

    # 2. Login
    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    time.sleep(5)

    # 3. Click Dashboard Punch In button
    punch_in_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Punch In')]")
    punch_in_btn.click()
    time.sleep(4)

    # 4. Modal → Click final Punch In
    modal_btn = driver.find_element(By.XPATH, "(//button[contains(text(),'Punch In')])[last()]")
    modal_btn.click()

    time.sleep(5)

    # 5. Punch-in screenshot
    driver.save_screenshot("punch_in_screenshot.png")
    print("Saved punch-in screenshot: punch_in_screenshot.png")

finally:
    driver.quit()
