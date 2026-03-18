"""Tests for timeout constants."""
from run import (
    _TIMEOUT_GLOBAL_SECS,
    _TIMEOUT_NAV_MS,
    _TIMEOUT_ACTION_MS,
    _TIMEOUT_IDLE_MS,
    _TIMEOUT_COOKIE_MS,
    _TIMEOUT_PROBE_MS,
)


def test_timeout_values():
    assert _TIMEOUT_GLOBAL_SECS == 60
    assert _TIMEOUT_NAV_MS == 30_000
    assert _TIMEOUT_ACTION_MS == 10_000
    assert _TIMEOUT_IDLE_MS == 5_000
    assert _TIMEOUT_COOKIE_MS == 2_000
    assert _TIMEOUT_PROBE_MS == 500
