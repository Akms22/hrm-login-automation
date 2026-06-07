"""
test_punch_properties.py — Property-Based Tests for HRM Punch Automation
Uses Hypothesis to verify universal properties across all valid inputs.

Install: pip install hypothesis
Run:     pytest test_punch_properties.py -v
"""
import re
import pytest
from datetime import datetime
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from punch import (
    validate_credentials,
    parse_mode,
    resolve_punch_action,
    is_duplicate_action,
    log_step,
)

# ---------------------------------------------------------------------------
# Property 1: Invalid credentials are always rejected
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

@given(
    username=st.one_of(st.none(), st.just(""), st.text(alphabet=" \t\n\r")),
    password=st.one_of(st.none(), st.just(""), st.text(alphabet=" \t\n\r")),
)
@settings(max_examples=20)
def test_invalid_credentials_always_rejected(username, password):
    """
    Property 1: For any blank/None credential combination,
    validate_credentials() MUST raise SystemExit(1).

    **Validates: Requirements 1.4**
    """
    with pytest.raises(SystemExit) as exc:
        validate_credentials(username, password)
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Property 3a: Auto mode hour 0–11 → punch-in
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

@given(hour=st.integers(min_value=0, max_value=11))
@settings(max_examples=12)
def test_auto_mode_morning_is_punch_in(hour):
    """
    Property 3a: For any hour in [0, 11], resolve_punch_action('auto', hour)
    MUST return 'punch-in'.

    **Validates: Requirements 2.4**
    """
    assert resolve_punch_action("auto", current_hour=hour) == "punch-in"


# ---------------------------------------------------------------------------
# Property 3b: Auto mode hour 12–23 → punch-out
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

@given(hour=st.integers(min_value=12, max_value=23))
@settings(max_examples=12)
def test_auto_mode_afternoon_is_punch_out(hour):
    """
    Property 3b: For any hour in [12, 23], resolve_punch_action('auto', hour)
    MUST return 'punch-out'.

    **Validates: Requirements 2.4**
    """
    assert resolve_punch_action("auto", current_hour=hour) == "punch-out"


# ---------------------------------------------------------------------------
# Property 4: Invalid mode strings are always rejected
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------

VALID_MODES_LOWER = {"in", "out", "auto"}


@given(
    mode=st.text(min_size=1).filter(
        lambda s: s.strip().lower() not in VALID_MODES_LOWER
    )
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_invalid_mode_always_rejected(mode, monkeypatch):
    """
    Property 4: For any string not in {in, out, auto} (case-insensitive),
    parse_mode() MUST raise SystemExit(1).

    **Validates: Requirements 2.6**
    """
    monkeypatch.delenv("HRM_PUNCH_MODE", raising=False)
    with pytest.raises(SystemExit) as exc:
        parse_mode(argv=["--mode", mode])
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Property 6: Duplicate action detection is always correct
# Validates: Requirements 4.4
# ---------------------------------------------------------------------------

@given(
    state=st.sampled_from(["punched-in", "punched-out"]),
    action=st.sampled_from(["punch-in", "punch-out"]),
)
@settings(max_examples=4)
def test_duplicate_action_detection(state, action):
    """
    Property 6: is_duplicate_action(state, action) is True iff the action
    matches the current state (would be a no-op double punch).

    **Validates: Requirements 4.4**
    """
    result = is_duplicate_action(state, action)
    expected = (
        (state == "punched-in" and action == "punch-in")
        or (state == "punched-out" and action == "punch-out")
    )
    assert result == expected


# ---------------------------------------------------------------------------
# Property 7: log_step output always contains step name and ISO-8601 timestamp
# Validates: Requirements 6.3
# ---------------------------------------------------------------------------

@given(
    step_name=st.text(min_size=1, max_size=50),
    event=st.sampled_from(["START", "END"]),
)
@settings(max_examples=20)
def test_log_step_contains_step_name_and_timestamp(step_name, event):
    """
    Property 7: For any step_name and event, log_step() output MUST contain
    the step_name and a valid ISO-8601 formatted timestamp (YYYY-MM-DDTHH:MM:SS).

    **Validates: Requirements 6.3**
    """
    import io
    from contextlib import redirect_stdout
    fixed_dt = datetime(2024, 6, 15, 9, 30, 0)
    buf = io.StringIO()
    with redirect_stdout(buf):
        log_step(step_name, event, dt=fixed_dt)
    output = buf.getvalue()
    assert step_name in output
    iso_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    assert re.search(iso_pattern, output), (
        f"No ISO-8601 timestamp found in output: {output!r}"
    )
