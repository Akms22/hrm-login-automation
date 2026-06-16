"""
punch.py — HRM Punch Automation
Automates punch-in/punch-out on https://hrm.org.in/attendance
"""
import argparse
import os
import sys
# Fix 1: removed unused 'import re'
from datetime import datetime
# Fix 2: use typing module for Python 3.9 compatibility (no X | None syntax)
from typing import Optional, List
# Fix 3: zoneinfo for IST-aware time (GitHub runners use UTC)
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
# Fix 6: use webdriver-manager to auto-match ChromeDriver version
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# -- Constants -----------------------------------------------------------------

LOGIN_URL      = "https://hrm.org.in/login"
ATTENDANCE_URL = "https://hrm.org.in/attendance"

LOGIN_TIMEOUT      = 20
ATTENDANCE_TIMEOUT = 15
PUNCH_TIMEOUT      = 10
STATE_TIMEOUT      = 10

VALID_MODES = {"in", "out", "auto"}

PUNCH_IN  = "punch-in"
PUNCH_OUT = "punch-out"

STATE_PUNCHED_IN  = "punched-in"
STATE_PUNCHED_OUT = "punched-out"

# Fix 3: IST timezone for correct auto-mode punch decision on CI runners
IST = ZoneInfo("Asia/Kolkata")

# -- Logging -------------------------------------------------------------------

def log_step(step_name: str, event: str, dt: Optional[datetime] = None) -> None:
    """
    Prints: [<ISO-8601 timestamp>] STEP <event>: <step_name>
    dt defaults to datetime.now() when None.
    """
    ts = (dt or datetime.now()).isoformat(timespec="seconds")
    print(f"[{ts}] STEP {event}: {step_name}")

# -- Screenshot helpers --------------------------------------------------------

def save_screenshot(driver, filename: str) -> None:
    """
    Saves driver.get_screenshot_as_file(filename).
    Silently logs to stderr if screenshot fails (never re-raises).
    """
    try:
        if driver:
            driver.get_screenshot_as_file(filename)
    except Exception as ex:
        print(f"WARNING: Could not save screenshot '{filename}': {ex}", file=sys.stderr)


def get_screenshot_filename(punch_action: str) -> str:
    """
    'punch-in'  -> 'punch_in_screenshot.png'
    'punch-out' -> 'punch_out_screenshot.png'
    """
    if punch_action == PUNCH_IN:
        return "punch_in_screenshot.png"
    return "punch_out_screenshot.png"

# -- Credential validation -----------------------------------------------------

def validate_credentials(username: Optional[str], password: Optional[str]) -> None:
    """
    Raises SystemExit(1) if credentials are missing or blank.
    """
    if not (username and username.strip()) or not (password and password.strip()):
        print("ERROR: HRM_USERNAME and HRM_PASSWORD must be set", file=sys.stderr)
        sys.exit(1)

# -- Mode resolution -----------------------------------------------------------

def parse_mode(argv: Optional[List[str]] = None) -> str:
    """
    Returns resolved punch mode: 'in', 'out', or 'auto'.
    CLI --mode takes precedence over HRM_PUNCH_MODE env var.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", default=None)
    args, _ = parser.parse_known_args(argv)
    cli_mode = args.mode
    env_mode = os.getenv("HRM_PUNCH_MODE")
    raw = cli_mode if cli_mode is not None else env_mode
    if raw is None:
        print("WARNING: HRM_PUNCH_MODE not set, defaulting to auto", file=sys.stderr)
        return "auto"
    normalized = raw.strip().lower()
    if normalized not in VALID_MODES:
        print(f"ERROR: Invalid mode '{raw}'. Accepted values: in, out, auto", file=sys.stderr)
        sys.exit(1)
    return normalized

def resolve_punch_action(mode: str, current_hour: Optional[int] = None) -> str:
    """
    mode: 'in' | 'out' | 'auto'
    current_hour: 0-23 injectable for testing.
    Fix 3: defaults to IST hour (not UTC) so auto-mode is correct on CI.
    """
    if mode == "in":
        return PUNCH_IN
    if mode == "out":
        return PUNCH_OUT
    # auto mode — use IST to determine punch direction
    hour = current_hour if current_hour is not None else datetime.now(tz=IST).hour
    return PUNCH_IN if hour < 12 else PUNCH_OUT

# -- Browser setup -------------------------------------------------------------

def create_driver() -> webdriver.Chrome:
    """
    Returns a configured headless Chrome WebDriver.
    Fix 5: all required CI flags set.
    Fix 6: webdriver-manager auto-matches ChromeDriver to installed Chrome.
    """
    opts = Options()
    for flag in [
        "--headless=new",        # Fix 5: headless mode
        "--no-sandbox",          # Fix 5: required in CI
        "--disable-dev-shm-usage",  # Fix 5: prevents shared memory errors
        "--disable-gpu",         # Fix 5: no GPU in CI
        "--window-size=1920,1080",
    ]:
        opts.add_argument(flag)
    # Fix 6: auto-match ChromeDriver version via webdriver-manager
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

# -- Login ---------------------------------------------------------------------

def login(driver: webdriver.Chrome, username: str, password: str) -> None:
    """
    Authenticates against https://hrm.org.in/login.
    Waits up to 20s for dashboard URL.
    Raises RuntimeError if dashboard is not reached.
    """
    driver.get(LOGIN_URL)
    # Debug: capture page immediately after load
    driver.save_screenshot("debug_01_page_loaded.png")
    print(f"DEBUG: current URL after get = {driver.current_url}", flush=True)
    print(f"DEBUG: page title = {driver.title}", flush=True)

    wait = WebDriverWait(driver, LOGIN_TIMEOUT)

    # Try finding email field — log what we find
    try:
        email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
        print("DEBUG: found email field by ID='email'", flush=True)
    except TimeoutException:
        # Fallback: try by name or type
        print("DEBUG: email field not found by ID='email', trying alternatives", flush=True)
        driver.save_screenshot("debug_02_no_email_field.png")
        print(f"DEBUG: page source snippet = {driver.page_source[:2000]}", flush=True)
        raise RuntimeError("Login failed — email field not found")

    email_field.clear()
    email_field.send_keys(username)

    try:
        pwd_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
        print("DEBUG: found password field by ID='password'", flush=True)
    except TimeoutException:
        print("DEBUG: password field not found by ID='password'", flush=True)
        driver.save_screenshot("debug_03_no_password_field.png")
        raise RuntimeError("Login failed — password field not found")

    pwd_field.clear()
    pwd_field.send_keys(password)

    try:
        btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login')]"))
        )
        print("DEBUG: found Login button", flush=True)
        driver.save_screenshot("debug_04_before_click.png")
        btn.click()
        print("DEBUG: clicked Login button", flush=True)
    except TimeoutException:
        print("DEBUG: Login button not found", flush=True)
        driver.save_screenshot("debug_05_no_login_button.png")
        raise RuntimeError("Login failed — Login button not found")

    try:
        wait.until(EC.url_contains("dashboard"))
        print(f"DEBUG: reached dashboard, URL = {driver.current_url}", flush=True)
    except TimeoutException:
        driver.save_screenshot("debug_06_after_click.png")
        print(f"DEBUG: URL after click = {driver.current_url}", flush=True)
        print(f"DEBUG: page source after click = {driver.page_source[:3000]}", flush=True)
        raise RuntimeError("Login failed — dashboard URL not reached")

# -- Attendance navigation -----------------------------------------------------

def navigate_to_attendance(driver: webdriver.Chrome):
    """
    Navigates to the attendance page and waits for the Punch_Button.
    Returns the Punch_Button WebElement or raises TimeoutException.
    """
    driver.get(ATTENDANCE_URL)
    wait = WebDriverWait(driver, ATTENDANCE_TIMEOUT)
    try:
        btn = wait.until(EC.visibility_of_element_located(
            (By.XPATH, "//*[contains(@class,'punch') or contains(text(),'Punch')]")
        ))
        return btn
    except TimeoutException:
        raise TimeoutException("Attendance page did not load — Punch_Button not found")

# -- Punch state detection -----------------------------------------------------

def detect_punch_state(punch_button, driver: webdriver.Chrome) -> str:
    """
    Reads the Punch_Button text label to determine current state.
    Fix 4: replaced EC.element_to_be_clickable(element) with lambda
    (passing a WebElement directly to EC is fragile).
    """
    wait = WebDriverWait(driver, STATE_TIMEOUT)
    # Fix 4: wait until button is both visible and enabled
    wait.until(lambda d: punch_button.is_displayed() and punch_button.is_enabled())
    text = punch_button.text.strip().lower()
    if "punch in" in text:
        return STATE_PUNCHED_OUT
    if "punch out" in text:
        return STATE_PUNCHED_IN
    raise RuntimeError(f"Cannot determine punch state from button text: '{punch_button.text}'")


def is_duplicate_action(punch_state: str, punch_action: str) -> bool:
    """Returns True if the action would be a no-op duplicate."""
    return (
        (punch_state == STATE_PUNCHED_IN  and punch_action == PUNCH_IN) or
        (punch_state == STATE_PUNCHED_OUT and punch_action == PUNCH_OUT)
    )

# -- Punch action --------------------------------------------------------------

def _confirmation_detected(driver: webdriver.Chrome, original_button, punch_action: str) -> bool:
    """Returns True when any post-punch confirmation indicator is visible."""
    try:
        success_els = driver.find_elements(
            By.XPATH,
            "//*[contains(@class,'success') or contains(@class,'toast') or contains(@class,'alert')]"
        )
        if any(el.is_displayed() for el in success_els):
            return True
        new_text = original_button.text.strip().lower()
        if punch_action == PUNCH_IN and "punch out" in new_text:
            return True
        if punch_action == PUNCH_OUT and "punch in" in new_text:
            return True
    except Exception:
        pass
    return False


def perform_punch(driver: webdriver.Chrome, punch_button, punch_action: str) -> None:
    """Clicks the punch button and waits up to 10s for confirmation."""
    punch_button.click()
    wait = WebDriverWait(driver, PUNCH_TIMEOUT)
    try:
        wait.until(lambda d: _confirmation_detected(d, punch_button, punch_action))
    except TimeoutException:
        raise RuntimeError(
            f"Punch action '{punch_action}' not confirmed after {PUNCH_TIMEOUT} seconds"
        )


# -- Main orchestration -------------------------------------------------------

def main() -> None:
    username = os.getenv("HRM_USERNAME")
    password = os.getenv("HRM_PASSWORD")

    validate_credentials(username, password)
    mode         = parse_mode()
    punch_action = resolve_punch_action(mode)

    driver = None
    try:
        log_step("browser launch", "START")
        driver = create_driver()
        log_step("browser launch", "END")

        log_step("login", "START")
        try:
            login(driver, username, password)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            save_screenshot(driver, "login_error.png")
            sys.exit(1)
        log_step("login", "END")

        log_step("attendance page navigation", "START")
        try:
            punch_button = navigate_to_attendance(driver)
        except TimeoutException:
            print("ERROR: Attendance page did not load — Punch_Button not found", file=sys.stderr)
            save_screenshot(driver, "attendance_page_error.png")
            sys.exit(1)
        log_step("attendance page navigation", "END")

        log_step("punch state detection", "START")
        try:
            punch_state = detect_punch_state(punch_button, driver)
        except (RuntimeError, TimeoutException):
            print("ERROR: Punch_Button not found or not interactable", file=sys.stderr)
            save_screenshot(driver, "punch_button_error.png")
            sys.exit(1)
        log_step("punch state detection", "END")

        if is_duplicate_action(punch_state, punch_action):
            print(f"WARNING: Already {punch_state}, skipping action", file=sys.stderr)
            sys.exit(0)

        log_step("punch action", "START")
        try:
            perform_punch(driver, punch_button, punch_action)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            save_screenshot(driver, "punch_error.png")
            sys.exit(1)
        log_step("punch action", "END")

        ts = datetime.now(tz=IST).isoformat(timespec="seconds")
        print(f"SUCCESS: {punch_action} recorded at {ts}")
        save_screenshot(driver, get_screenshot_filename(punch_action))

    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: [{type(e).__name__}] {e}", file=sys.stderr)
        save_screenshot(driver, "unexpected_error.png")
        sys.exit(1)
    finally:
        if driver:
            log_step("browser close", "START")
            driver.quit()
            log_step("browser close", "END")


if __name__ == "__main__":
    main()
