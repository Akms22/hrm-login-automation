import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

USERNAME = os.getenv("HRM_USERNAME")
PASSWORD = os.getenv("HRM_PASSWORD")

print("Starting browser...")

chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(options=chrome_options)

try:
    print("Opening website...")
    driver.get("https://hrm.org.in/login")

    wait = WebDriverWait(driver, 20)

    print("Waiting for email field...")
    email_input = wait.until(
        EC.presence_of_element_located((By.ID, "email"))
    )
    email_input.clear()
    email_input.send_keys(USERNAME)

    print("Entering password...")
    password_input = wait.until(
        EC.presence_of_element_located((By.ID, "password"))
    )
    password_input.clear()
    password_input.send_keys(PASSWORD)

    print("Clicking login button...")
    login_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login')]"))
    )
    login_button.click()

    print("Waiting for dashboard...")
    wait.until(EC.url_contains("dashboard"))

    print("SUCCESS: Logged in!")

except Exception as e:
    print("ERROR during login:", str(e))

finally:
    print("Closing browser...")
    driver.quit()
