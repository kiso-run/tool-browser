"""Tests for browser semantic validator."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))
from validator import repair_args, validate_args


def test_validate_args_accepts_navigate_with_url():
    assert validate_args({"action": "navigate", "url": "https://example.com"}, {}) == []


def test_validate_args_rejects_missing_url_for_navigate():
    errors = validate_args({"action": "navigate"}, {})
    assert "navigate requires non-empty `url`." in errors


def test_validate_args_rejects_missing_element_for_click():
    errors = validate_args({"action": "click"}, {})
    assert "click requires non-empty `element`." in errors


def test_validate_args_rejects_missing_fill_fields():
    errors = validate_args({"action": "fill", "element": "  "}, {})
    assert "fill requires non-empty `element`." in errors
    assert "fill requires non-empty `value`." in errors


def test_repair_args_trims_string_fields():
    repaired = repair_args(
        {"action": " fill ", "element": " [2] ", "value": " hello "},
        {},
    )
    assert repaired == {"action": "fill", "element": "[2]", "value": "hello"}
