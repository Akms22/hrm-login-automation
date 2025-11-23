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
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")

# Auto-deny location popup
prefs = {
    "profile.default_content_setting_values.geolocation": 2   # 2 = Block
}
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

try:
    # 1. Login
    driver.get("https://hrm.pionova.in/admin/users/login")
    time.sleep(3)

    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    time.sleep(5)

    # 2. Click Dashboard Punch In button
    punch_in_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Punch In')]")
    punch_in_btn.click()
    time.sleep(4)

    # 3. Modal opens → click Punch In inside popup
    modal_punch_in = driver.find_element(
        By.XPATH, "(//button[contains(text(),'Punch In')])[last()]"
    )
    modal_punch_in.click()

    time.sleep(5)

    # 4. Save screenshot for proof
    screenshot_path = "punch_in_screenshot.png"
    driver.save_screenshot(screenshot_path)
    print(f"Punch In completed. Screenshot saved as: {screenshot_path}")

finally:
    driver.quit()
