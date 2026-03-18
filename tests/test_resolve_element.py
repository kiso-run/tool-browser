"""Tests for resolve_element() — [N] refs and CSS selectors."""
from unittest.mock import MagicMock

import pytest
from conftest import make_mock_page, make_mock_element
from run import resolve_element


def test_bracket_ref_resolves_first_element():
    el1 = make_mock_element(tag="button", text="Submit")
    el2 = make_mock_element(tag="a", text="Link")
    page = make_mock_page(elements=[el1, el2])

    result = resolve_element(page, "[1]")
    assert result is el1


def test_bare_number_also_works():
    el1 = make_mock_element(tag="button", text="Submit")
    el2 = make_mock_element(tag="a", text="Link")
    page = make_mock_page(elements=[el1, el2])

    result = resolve_element(page, "2")
    assert result is el2


def test_out_of_range_raises_with_count():
    el1 = make_mock_element(tag="button", text="Only")
    page = make_mock_page(elements=[el1])

    with pytest.raises(ValueError, match=r"Element \[5\] not found \(page has 1 elements\)"):
        resolve_element(page, "[5]")


def test_zero_ref_raises():
    el1 = make_mock_element(tag="button", text="Only")
    page = make_mock_page(elements=[el1])

    with pytest.raises(ValueError, match=r"Element \[0\] not found"):
        resolve_element(page, "[0]")


def test_css_selector_resolves_via_query_selector():
    el = make_mock_element(tag="input", text="")
    page = make_mock_page()
    page.query_selector.return_value = el

    result = resolve_element(page, "#search-input")
    page.query_selector.assert_called_with("#search-input")
    assert result is el


def test_css_selector_not_found_raises():
    page = make_mock_page()
    page.query_selector.return_value = None

    with pytest.raises(ValueError, match="Element not found: '.nonexistent'"):
        resolve_element(page, ".nonexistent")
