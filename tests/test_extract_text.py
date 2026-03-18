"""Tests for extract_text() — noise stripping and content container logic."""
from unittest.mock import MagicMock, call

import pytest
from conftest import make_mock_page, make_mock_element
from run import extract_text


def test_with_css_selector_returns_scoped_text():
    page = make_mock_page(title="Docs", url="https://example.com/docs")
    scoped = MagicMock()
    scoped.inner_text.return_value = "Scoped content here"
    page.query_selector.return_value = scoped

    result = extract_text(page, selector=".main-content")

    page.query_selector.assert_called_once_with(".main-content")
    assert "Scoped content here" in result
    assert result.startswith("Page: Docs\nURL: https://example.com/docs")


def test_with_css_selector_not_found_raises():
    page = make_mock_page()
    page.query_selector.return_value = None

    with pytest.raises(ValueError, match="Selector not found: '.missing'"):
        extract_text(page, selector=".missing")


def test_without_selector_removes_noise_and_uses_content_container():
    page = make_mock_page(title="Article", url="https://example.com/article")

    main_el = MagicMock()
    main_el.inner_text.return_value = "Main article text"

    def qs_side_effect(sel):
        if sel == "main":
            return main_el
        return None

    page.query_selector.side_effect = qs_side_effect

    result = extract_text(page)

    # Noise removal evaluate was called
    page.evaluate.assert_called_once()
    assert "Main article text" in result


def test_without_selector_tries_article_container():
    page = make_mock_page(title="Blog", url="https://example.com/blog")

    article_el = MagicMock()
    article_el.inner_text.return_value = "Blog post body"

    def qs_side_effect(sel):
        if sel == "article":
            return article_el
        return None

    page.query_selector.side_effect = qs_side_effect

    result = extract_text(page)
    assert "Blog post body" in result


def test_without_selector_tries_role_main_container():
    page = make_mock_page(title="App", url="https://example.com/app")

    role_main = MagicMock()
    role_main.inner_text.return_value = "App content"

    def qs_side_effect(sel):
        if sel == "[role='main']":
            return role_main
        return None

    page.query_selector.side_effect = qs_side_effect

    result = extract_text(page)
    assert "App content" in result


def test_falls_back_to_body_when_no_content_container():
    page = make_mock_page(title="Plain", url="https://example.com/plain")

    body = MagicMock()
    body.inner_text.return_value = "Body fallback text"

    def qs_side_effect(sel):
        if sel == "body":
            return body
        return None

    page.query_selector.side_effect = qs_side_effect

    result = extract_text(page)
    assert "Body fallback text" in result


def test_empty_body_returns_header_with_empty_text():
    page = make_mock_page(title="Empty", url="https://example.com/empty")

    body = MagicMock()
    body.inner_text.return_value = ""

    def qs_side_effect(sel):
        if sel == "body":
            return body
        return None

    page.query_selector.side_effect = qs_side_effect

    result = extract_text(page)
    assert result.startswith("Page: Empty\nURL: https://example.com/empty")
    # After header + blank line, text should be empty
    lines = result.split("\n")
    assert lines[0] == "Page: Empty"
    assert lines[1] == "URL: https://example.com/empty"


def test_content_container_with_empty_text_skipped():
    """If a content container exists but has empty text, skip to next."""
    page = make_mock_page(title="Skip", url="https://example.com/skip")

    empty_main = MagicMock()
    empty_main.inner_text.return_value = "   "  # whitespace only

    article_el = MagicMock()
    article_el.inner_text.return_value = "Real content"

    body = MagicMock()
    body.inner_text.return_value = "Body text"

    def qs_side_effect(sel):
        if sel == "main":
            return empty_main
        if sel == "article":
            return article_el
        if sel == "body":
            return body
        return None

    page.query_selector.side_effect = qs_side_effect

    result = extract_text(page)
    assert "Real content" in result
