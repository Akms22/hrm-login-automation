"""
test_punch.py — Comprehensive unit tests for punch.py

Covers all unit-testable functions per the design's unit test table:
  - validate_credentials
  - parse_mode
  - resolve_punch_action
  - is_duplicate_action
  - get_screenshot_filename
  - log_step
  - detect_punch_state
  - login
  - perform_punch

Requirements: 1.4, 2.1–2.6, 4.1–4.5, 5.1–5.5, 6.3
"""
import re
import sys
import os
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call

# Ensure punch.py is importable from the same directory
sys.path.insert(0, os.path.dirname(__file__))

from punch import (
    validate_credentials,
    parse_mode,
    resolve_punch_action,
    is_duplicate_action,
    get_screenshot_filename,
    log_step,
    detect_punch_state,
    login,
    perform_punch,
    PUNCH_IN,
    PUNCH_OUT,
    STATE_PUNCHED_IN,
    STATE_PUNCHED_OUT,
    LOGIN_TIMEOUT,
    PUNCH_TIMEOUT,
)
from selenium.common.exceptions import TimeoutException


# ── validate_credentials ───────────────────────────────────────────────────────

class TestValidateCredentials:
    """Requirement 1.4: Credentials must be non-empty, non-whitespace strings."""

    def test_none_username_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials(None, "password")
        assert exc.value.code == 1

    def test_none_password_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials("user", None)
        assert exc.value.code == 1

    def test_empty_username_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials("", "password")
        assert exc.value.code == 1

    def test_empty_password_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials("user", "")
        assert exc.value.code == 1

    def test_whitespace_only_username_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials("   ", "password")
        assert exc.value.code == 1

    def test_tab_newline_whitespace_username_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials("\t\n", "password")
        assert exc.value.code == 1

    def test_whitespace_only_password_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials("user", "  ")
        assert exc.value.code == 1

    def test_both_none_exits_1(self):
        with pytest.raises(SystemExit) as exc:
            validate_credentials(None, None)
        assert exc.value.code == 1

    def test_valid_credentials_do_not_raise(self):
        """Valid username and password should not raise any exception."""
        validate_credentials("admin", "secret123")  # must not raise

    def test_valid_credentials_with_spaces_in_middle(self):
        """Credentials with leading/trailing content but not purely whitespace are valid."""
        validate_credentials("admin user", "pass word")  # must not raise


# ── parse_mode ────────────────────────────────────────────────────────────────

class TestParseMode:
    """Requirements 2.1–2.6: Mode resolution from CLI and env var."""

    def test_cli_arg_in(self):
        assert parse_mode(argv=["--mode", "in"]) == "in"

    def test_cli_arg_out(self):
        assert parse_mode(argv=["--mode", "out"]) == "out"

    def test_cli_arg_auto(self):
        assert parse_mode(argv=["--mode", "auto"]) == "auto"

    def test_cli_arg_uppercase_normalized(self):
        assert parse_mode(argv=["--mode", "OUT"]) == "out"

    def test_cli_arg_mixed_case_normalized(self):
        assert parse_mode(argv=["--mode", "In"]) == "in"

    def test_env_var_in(self, monkeypatch):
        monkeypatch.setenv("HRM_PUNCH_MODE", "in")
        assert parse_mode(argv=[]) == "in"

    def test_env_var_out(self, monkeypatch):
        monkeypatch.setenv("HRM_PUNCH_MODE", "out")
        assert parse_mode(argv=[]) == "out"

    def test_env_var_auto(self, monkeypatch):
        monkeypatch.setenv("HRM_PUNCH_MODE", "auto")
        assert parse_mode(argv=[]) == "auto"

    def test_cli_overrides_env_var(self, monkeypatch):
        """Requirement 2.1: CLI --mode takes precedence over HRM_PUNCH_MODE."""
        monkeypatch.setenv("HRM_PUNCH_MODE", "out")
        assert parse_mode(argv=["--mode", "in"]) == "in"

    def test_cli_overrides_env_var_reverse(self, monkeypatch):
        monkeypatch.setenv("HRM_PUNCH_MODE", "in")
        assert parse_mode(argv=["--mode", "out"]) == "out"

    def test_neither_present_defaults_to_auto(self, monkeypatch):
        """Requirement 2.5: No CLI or env → default to 'auto' with a warning."""
        monkeypatch.delenv("HRM_PUNCH_MODE", raising=False)
        assert parse_mode(argv=[]) == "auto"

    def test_neither_present_prints_warning(self, monkeypatch, capsys):
        monkeypatch.delenv("HRM_PUNCH_MODE", raising=False)
        parse_mode(argv=[])
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "auto" in captured.err

    def test_invalid_value_exits_1(self, monkeypatch):
        """Requirement 2.6: Invalid mode value triggers SystemExit(1)."""
        monkeypatch.delenv("HRM_PUNCH_MODE", raising=False)
        with pytest.raises(SystemExit) as exc:
            parse_mode(argv=["--mode", "bogus"])
        assert exc.value.code == 1

    def test_invalid_value_via_env_exits_1(self, monkeypatch):
        monkeypatch.setenv("HRM_PUNCH_MODE", "bogus")
        with pytest.raises(SystemExit) as exc:
            parse_mode(argv=[])
        assert exc.value.code == 1

    def test_invalid_value_error_message_contains_value(self, monkeypatch, capsys):
        monkeypatch.delenv("HRM_PUNCH_MODE", raising=False)
        with pytest.raises(SystemExit):
            parse_mode(argv=["--mode", "invalid_xyz"])
        captured = capsys.readouterr()
        assert "invalid_xyz" in captured.err


# ── resolve_punch_action ──────────────────────────────────────────────────────

class TestResolvePunchAction:
    """Requirement 2.4: Mode maps correctly to punch actions; auto uses current hour."""

    def test_mode_in_returns_punch_in(self):
        assert resolve_punch_action("in") == PUNCH_IN

    def test_mode_out_returns_punch_out(self):
        assert resolve_punch_action("out") == PUNCH_OUT

    def test_auto_hour_0_is_punch_in(self):
        assert resolve_punch_action("auto", current_hour=0) == PUNCH_IN

    def test_auto_hour_6_is_punch_in(self):
        assert resolve_punch_action("auto", current_hour=6) == PUNCH_IN

    def test_auto_hour_11_is_punch_in(self):
        assert resolve_punch_action("auto", current_hour=11) == PUNCH_IN

    def test_auto_hour_12_is_punch_out(self):
        """Boundary: noon (12) is the first punch-out hour."""
        assert resolve_punch_action("auto", current_hour=12) == PUNCH_OUT

    def test_auto_hour_17_is_punch_out(self):
        assert resolve_punch_action("auto", current_hour=17) == PUNCH_OUT

    def test_auto_hour_23_is_punch_out(self):
        assert resolve_punch_action("auto", current_hour=23) == PUNCH_OUT


# ── is_duplicate_action ───────────────────────────────────────────────────────

class TestIsDuplicateAction:
    """Requirement 4.4: Duplicate punch actions must be detected and skipped."""

    def test_punched_in_punch_in_is_duplicate(self):
        assert is_duplicate_action(STATE_PUNCHED_IN, PUNCH_IN) is True

    def test_punched_out_punch_out_is_duplicate(self):
        assert is_duplicate_action(STATE_PUNCHED_OUT, PUNCH_OUT) is True

    def test_punched_in_punch_out_is_not_duplicate(self):
        assert is_duplicate_action(STATE_PUNCHED_IN, PUNCH_OUT) is False

    def test_punched_out_punch_in_is_not_duplicate(self):
        assert is_duplicate_action(STATE_PUNCHED_OUT, PUNCH_IN) is False


# ── get_screenshot_filename ───────────────────────────────────────────────────

class TestGetScreenshotFilename:
    """Requirements 5.1–5.5: Screenshot filenames are correct per action."""

    def test_punch_in_filename(self):
        assert get_screenshot_filename(PUNCH_IN) == "punch_in_screenshot.png"

    def test_punch_out_filename(self):
        assert get_screenshot_filename(PUNCH_OUT) == "punch_out_screenshot.png"


# ── log_step ──────────────────────────────────────────────────────────────────

class TestLogStep:
    """Requirement 6.3: Log output contains step name and ISO-8601 timestamp."""

    ISO_8601_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    def test_output_contains_step_name(self, capsys):
        fixed_dt = datetime(2024, 6, 15, 9, 30, 0)
        log_step("login", "START", dt=fixed_dt)
        captured = capsys.readouterr()
        assert "login" in captured.out

    def test_output_contains_event(self, capsys):
        fixed_dt = datetime(2024, 6, 15, 9, 30, 0)
        log_step("browser launch", "END", dt=fixed_dt)
        captured = capsys.readouterr()
        assert "END" in captured.out

    def test_output_contains_iso8601_timestamp(self, capsys):
        fixed_dt = datetime(2024, 6, 15, 9, 30, 0)
        log_step("punch action", "START", dt=fixed_dt)
        captured = capsys.readouterr()
        assert self.ISO_8601_PATTERN.search(captured.out), (
            f"No ISO-8601 timestamp found in: {captured.out!r}"
        )

    def test_timestamp_matches_injected_datetime(self, capsys):
        fixed_dt = datetime(2024, 3, 22, 14, 45, 30)
        log_step("attendance page navigation", "START", dt=fixed_dt)
        captured = capsys.readouterr()
        assert "2024-03-22T14:45:30" in captured.out

    def test_step_format_contains_step_keyword(self, capsys):
        fixed_dt = datetime(2024, 1, 1, 0, 0, 0)
        log_step("test-step", "START", dt=fixed_dt)
        captured = capsys.readouterr()
        assert "STEP" in captured.out
        assert "test-step" in captured.out


# ── detect_punch_state ────────────────────────────────────────────────────────

class TestDetectPunchState:
    """Requirements 4.1–4.3: Punch state derived from button text."""

    def _make_button(self, text: str) -> MagicMock:
        btn = MagicMock()
        btn.text = text
        return btn

    def _make_driver(self) -> MagicMock:
        driver = MagicMock()
        return driver

    def test_punch_in_text_returns_punched_out(self):
        """Button says 'Punch In' → user is punched-out (hasn't punched in yet)."""
        btn = self._make_button("Punch In")
        driver = self._make_driver()
        with patch("punch.WebDriverWait") as mock_wait:
            # element_to_be_clickable returns without raising
            mock_wait.return_value.until.return_value = None
            result = detect_punch_state(btn, driver)
        assert result == STATE_PUNCHED_OUT

    def test_punch_out_text_returns_punched_in(self):
        """Button says 'Punch Out' → user is already punched-in."""
        btn = self._make_button("Punch Out")
        driver = self._make_driver()
        with patch("punch.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = None
            result = detect_punch_state(btn, driver)
        assert result == STATE_PUNCHED_IN

    def test_punch_in_lowercase_returns_punched_out(self):
        """Text matching is case-insensitive."""
        btn = self._make_button("punch in")
        driver = self._make_driver()
        with patch("punch.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = None
            result = detect_punch_state(btn, driver)
        assert result == STATE_PUNCHED_OUT

    def test_punch_out_lowercase_returns_punched_in(self):
        btn = self._make_button("punch out")
        driver = self._make_driver()
        with patch("punch.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = None
            result = detect_punch_state(btn, driver)
        assert result == STATE_PUNCHED_IN

    def test_unknown_button_text_raises_runtime_error(self):
        """Unrecognized button text must raise RuntimeError."""
        btn = self._make_button("Click Here")
        driver = self._make_driver()
        with patch("punch.WebDriverWait") as mock_wait:
            mock_wait.return_value.until.return_value = None
            with pytest.raises(RuntimeError) as exc:
                detect_punch_state(btn, driver)
        assert "Click Here" in str(exc.value)


# ── login ─────────────────────────────────────────────────────────────────────

class TestLogin:
    """Requirements 2.2, 4.5: Login navigates to dashboard or raises RuntimeError."""

    def test_successful_login_does_not_raise(self):
        """When dashboard URL is reached, login() returns normally."""
        mock_driver = MagicMock()
        mock_driver.current_url = "https://hrm.org.in/dashboard"

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            # All wait.until() calls return a mock element (for send_keys, click, url_contains)
            mock_element = MagicMock()
            mock_wait.until.return_value = mock_element

            # Should not raise
            login(mock_driver, "user@example.com", "password123")

        mock_driver.get.assert_called_once()

    def test_timeout_raises_runtime_error(self):
        """When url_contains('dashboard') times out, RuntimeError is raised."""
        mock_driver = MagicMock()

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait

            mock_element = MagicMock()

            # First three until() calls succeed (email field, password field, login button)
            # Fourth until() call (url_contains) raises TimeoutException
            mock_wait.until.side_effect = [
                mock_element,   # presence_of_element_located email
                mock_element,   # presence_of_element_located password
                mock_element,   # element_to_be_clickable login button
                TimeoutException(),  # url_contains("dashboard")
            ]

            with pytest.raises(RuntimeError) as exc:
                login(mock_driver, "user@example.com", "password123")

        assert "dashboard" in str(exc.value).lower() or "login failed" in str(exc.value).lower()

    def test_timeout_error_message_content(self):
        """RuntimeError message must mention login failure and dashboard."""
        mock_driver = MagicMock()

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            mock_element = MagicMock()
            mock_wait.until.side_effect = [
                mock_element,
                mock_element,
                mock_element,
                TimeoutException(),
            ]

            with pytest.raises(RuntimeError) as exc:
                login(mock_driver, "user@example.com", "password123")

        error_msg = str(exc.value).lower()
        # Message should reference the failure (login failed) and the expected destination
        assert "login failed" in error_msg or "dashboard" in error_msg


# ── perform_punch ─────────────────────────────────────────────────────────────

class TestPerformPunch:
    """Requirements 5.1–5.5: Punch action clicks button and waits for confirmation."""

    def test_confirmation_detected_exits_normally(self):
        """When confirmation is detected, perform_punch() returns without raising."""
        mock_driver = MagicMock()
        mock_button = MagicMock()

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            # wait.until() returns truthy (confirmation detected immediately)
            mock_wait.until.return_value = True

            # Should not raise
            perform_punch(mock_driver, mock_button, PUNCH_IN)

        mock_button.click.assert_called_once()

    def test_confirmation_timeout_raises_runtime_error(self):
        """When confirmation never arrives, RuntimeError is raised after timeout."""
        mock_driver = MagicMock()
        mock_button = MagicMock()

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            mock_wait.until.side_effect = TimeoutException()

            with pytest.raises(RuntimeError) as exc:
                perform_punch(mock_driver, mock_button, PUNCH_IN)

        assert PUNCH_IN in str(exc.value)

    def test_timeout_error_message_contains_action(self):
        """RuntimeError message must contain the punch action name."""
        mock_driver = MagicMock()
        mock_button = MagicMock()

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            mock_wait.until.side_effect = TimeoutException()

            with pytest.raises(RuntimeError) as exc:
                perform_punch(mock_driver, mock_button, PUNCH_OUT)

        assert PUNCH_OUT in str(exc.value)

    def test_timeout_error_message_contains_timeout_seconds(self):
        """RuntimeError message should mention the timeout duration."""
        mock_driver = MagicMock()
        mock_button = MagicMock()

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            mock_wait.until.side_effect = TimeoutException()

            with pytest.raises(RuntimeError) as exc:
                perform_punch(mock_driver, mock_button, PUNCH_IN)

        assert str(PUNCH_TIMEOUT) in str(exc.value)

    def test_button_is_clicked_before_wait(self):
        """The punch button must be clicked (even on timeout path)."""
        mock_driver = MagicMock()
        mock_button = MagicMock()

        with patch("punch.WebDriverWait") as mock_wait_cls:
            mock_wait = MagicMock()
            mock_wait_cls.return_value = mock_wait
            mock_wait.until.side_effect = TimeoutException()

            with pytest.raises(RuntimeError):
                perform_punch(mock_driver, mock_button, PUNCH_OUT)

        mock_button.click.assert_called_once()
