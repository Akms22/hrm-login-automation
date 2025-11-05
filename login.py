from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import os
import time

# Get credentials from environment variables
USERNAME = os.getenv("HRM_USERNAME")
PASSWORD = os.getenv("HRM_PASSWORD")

# Setup headless browser
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

try:
    # Open the login page
    driver.get("https://hrm.pionova.in/admin/users/login")

    # Wait for elements
    time.sleep(3)

    # Find input fields and fill them
    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)

    # Click the login button
    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    time.sleep(5)

    # Optional: Check if login succeeded
    print("Page title after login:", driver.title)

finally:
    driver.quit()
