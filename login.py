import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

USERNAME = os.getenv("HRM_USERNAME")
PASSWORD = os.getenv("HRM_PASSWORD")

# Setup Chrome options
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    print("Opening website...")
    driver.get("https://hrmapps.in/login")

    time.sleep(3)

    print("Entering credentials...")
    driver.find_element(By.NAME, "email").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)

    print("Clicking login...")
    driver.find_element(By.XPATH, "//button[contains(text(),'Login')]").click()

    time.sleep(5)

    print("Taking screenshot...")
    driver.save_screenshot("punch_in_screenshot.png")

finally:
    driver.quit()

print("Automation completed successfully.")
