"""
punch.py — HRM Punch Automation
Automates punch-in/punch-out on https://hrm.org.in/attendance
"""
import argparse
import os
import sys
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

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

# -- Logging -------------------------------------------------------------------

def log_step(step_name: str, event: str, dt: datetime | None = None) -> None:
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

def validate_credentials(username: str | None, password: str | None) -> None:
    """
    Raises SystemExit(1) with an error message if credentials are missing or blank.
    Checks: None, empty string "", or whitespace-only strings like "  " or "\t\n"
    """
    if not (username and username.strip()) or not (password and password.strip()):
        print("ERROR: HRM_USERNAME and HRM_PASSWORD must be set", file=sys.stderr)
        sys.exit(1)

# -- Mode resolution -----------------------------------------------------------

def parse_mode(argv: list[str] | None = None) -> str:
    """
    Returns the resolved, lowercased punch mode: 'in', 'out', or 'auto'.
    CLI --mode takes precedence over HRM_PUNCH_MODE env var.
    Prints a WARNING to stderr if mode was absent (defaulted to auto).
    Raises SystemExit(1) if mode is invalid.
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

def resolve_punch_action(mode: str, current_hour: int | None = None) -> str:
    """
    mode: 'in' | 'out' | 'auto'
    current_hour: 0-23 (injectable for testing; defaults to datetime.now().hour)
    Returns: 'punch-in' | 'punch-out'
    """
    if mode == "in":
        return PUNCH_IN
    if mode == "out":
        return PUNCH_OUT
    # auto mode
    hour = current_hour if current_hour is not None else datetime.now().hour
    return PUNCH_IN if hour < 12 else PUNCH_OUT

# -- Browser setup -------------------------------------------------------------

def create_driver() -> webdriver.Chrome:
    """
    Returns a configured Chrome WebDriver with headless flags.
    Flags: --headless=new, --no-sandbox, --disable-dev-shm-usage,
           --disable-gpu, --window-size=1920,1080
    """
    opts = Options()
    for flag in [
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
    ]:
        opts.add_argument(flag)
    return webdriver.Chrome(options=opts)

# -- Login ---------------------------------------------------------------------

def login(driver: webdriver.Chrome, username: str, password: str) -> None:
    """
    Authenticates against https://hrm.org.in/login.
    Waits up to 20s for dashboard URL.
    Raises RuntimeError if dashboard is not reached.
    """
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, LOGIN_TIMEOUT)
    wait.until(EC.presence_of_element_located((By.ID, "email"))).send_keys(username)
    wait.until(EC.presence_of_element_located((By.ID, "password"))).send_keys(password)
    wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Login')]"))
    ).click()
    try:
        wait.until(EC.url_contains("dashboard"))
    except TimeoutException:
        raise RuntimeError("Login failed — dashboard URL not reached")

# -- Attendance navigation -----------------------------------------------------

def navigate_to_attendance(driver: webdriver.Chrome):
    """
    Navigates to https://hrm.org.in/attendance.
    Waits up to 15s for the Punch_Button to be visible.
    Returns the Punch_Button WebElement.
    Raises TimeoutException if not found.
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
    Reads the Punch_Button text label.
    'Punch In' text  -> returns 'punched-out'  (not yet punched in)
    'Punch Out' text -> returns 'punched-in'   (already punched in)
    Raises RuntimeError if neither label is found.
    """
    wait = WebDriverWait(driver, STATE_TIMEOUT)
    wait.until(EC.element_to_be_clickable(punch_button))
    text = punch_button.text.strip().lower()
    if "punch in" in text:
        return STATE_PUNCHED_OUT
    if "punch out" in text:
        return STATE_PUNCHED_IN
    raise RuntimeError(f"Cannot determine punch state from button text: '{punch_button.text}'")


def is_duplicate_action(punch_state: str, punch_action: str) -> bool:
    """
    Returns True if punch_action would be a duplicate given punch_state.
    ('punched-in', 'punch-in')   -> True
    ('punched-out', 'punch-out') -> True
    All other combos             -> False
    """
    return (
        (punch_state == STATE_PUNCHED_IN  and punch_action == PUNCH_IN) or
        (punch_state == STATE_PUNCHED_OUT and punch_action == PUNCH_OUT)
    )

# -- Punch action --------------------------------------------------------------

def _confirmation_detected(driver: webdriver.Chrome, original_button, punch_action: str) -> bool:
    """Returns True when any confirmation indicator is present after a punch action."""
    try:
        # Check 1: success/toast/alert message is visible
        success_els = driver.find_elements(
            By.XPATH,
            "//*[contains(@class,'success') or contains(@class,'toast') or contains(@class,'alert')]"
        )
        if any(el.is_displayed() for el in success_els):
            return True
        # Check 2: button text changed to reflect the new opposite state
        new_text = original_button.text.strip().lower()
        if punch_action == PUNCH_IN and "punch out" in new_text:
            return True
        if punch_action == PUNCH_OUT and "punch in" in new_text:
            return True
    except Exception:
        pass
    return False


def perform_punch(driver: webdriver.Chrome, punch_button, punch_action: str) -> None:
    """
    Clicks Punch_Button, waits up to 10s for confirmation.
    Confirmation: success message visible, OR button text changes, OR page update.
    Raises RuntimeError if not confirmed within 10s.
    """
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

        ts = datetime.now().isoformat(timespec="seconds")
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
