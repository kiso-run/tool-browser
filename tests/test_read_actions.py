"""Tests for do_text, do_links, do_forms and their extraction helpers."""
import pytest
from unittest.mock import MagicMock

from run import (
    _ensure_page,
    do_forms,
    do_links,
    do_text,
    extract_forms,
    extract_links,
    extract_text,
    load_state,
    save_state,
)
from conftest import make_mock_page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_el(text="", attrs=None):
    """Simple mock element with inner_text and get_attribute."""
    el = MagicMock()
    el.inner_text.return_value = text
    attrs_dict = attrs or {}
    el.get_attribute.side_effect = lambda k: attrs_dict.get(k)
    return el


def _page_with_body_text(text, title="Test", url="https://example.com"):
    """Page where body.inner_text() returns *text* and no content containers exist."""
    page = make_mock_page(url=url, title=title)
    body = _mock_el(text)
    page.query_selector.side_effect = lambda sel: body if sel == "body" else None
    page.evaluate.return_value = None
    return page


# ---------------------------------------------------------------------------
# _ensure_page
# ---------------------------------------------------------------------------

class TestEnsurePage:
    def test_raises_without_url_or_state(self, tmp_path):
        page = make_mock_page()
        with pytest.raises(ValueError, match="navigate"):
            _ensure_page(page, {}, tmp_path / "state.json")

    def test_navigates_with_inline_url(self, tmp_path):
        sf = tmp_path / "state.json"
        page = make_mock_page(url="https://example.com")
        _ensure_page(page, {"url": "https://example.com"}, sf)
        page.goto.assert_called_once_with("https://example.com", timeout=30000)

    def test_navigates_from_state(self, tmp_path):
        sf = tmp_path / "state.json"
        save_state(sf, "https://saved.com")
        page = make_mock_page(url="https://saved.com")
        _ensure_page(page, {}, sf)
        page.goto.assert_called_once_with("https://saved.com", timeout=30000)

    def test_saves_state_after_inline_url(self, tmp_path):
        sf = tmp_path / "state.json"
        page = make_mock_page(url="https://redirected.com")
        _ensure_page(page, {"url": "https://original.com"}, sf)
        assert load_state(sf) == "https://redirected.com"

    def test_saves_state_after_state_url(self, tmp_path):
        """State is updated even when navigating from saved URL (handles redirects)."""
        sf = tmp_path / "state.json"
        save_state(sf, "https://old.com")
        page = make_mock_page(url="https://redirected.com")
        _ensure_page(page, {}, sf)
        assert load_state(sf) == "https://redirected.com"


# ---------------------------------------------------------------------------
# do_text
# ---------------------------------------------------------------------------

class TestDoText:
    def test_requires_url_or_state(self, tmp_path):
        page = make_mock_page()
        with pytest.raises(ValueError, match="navigate"):
            do_text(page, {}, tmp_path / "state.json")

    def test_uses_state_url(self, tmp_path):
        sf = tmp_path / "state.json"
        save_state(sf, "https://example.com")
        page = _page_with_body_text("Hello world")
        do_text(page, {}, sf)
        page.goto.assert_called_once_with("https://example.com", timeout=30000)

    def test_uses_inline_url(self, tmp_path):
        sf = tmp_path / "state.json"
        page = _page_with_body_text("Hello world")
        do_text(page, {"url": "https://inline.com"}, sf)
        page.goto.assert_called_once_with("https://inline.com", timeout=30000)

    def test_inline_url_saves_state(self, tmp_path):
        sf = tmp_path / "state.json"
        page = _page_with_body_text("Hello")
        page.url = "https://inline.com"
        do_text(page, {"url": "https://inline.com"}, sf)
        from run import load_state
        assert load_state(sf) == "https://inline.com"

    def test_with_selector(self, tmp_path):
        sf = tmp_path / "state.json"
        save_state(sf, "https://example.com")
        article = _mock_el("Article content here")
        page = make_mock_page()
        page.query_selector.return_value = article
        page.evaluate.return_value = None
        result = do_text(page, {"selector": "article"}, sf)
        assert "Article content here" in result

    def test_selector_not_found(self, tmp_path):
        sf = tmp_path / "state.json"
        save_state(sf, "https://example.com")
        page = make_mock_page()
        page.query_selector.return_value = None
        page.evaluate.return_value = None
        with pytest.raises(ValueError, match="Selector not found"):
            do_text(page, {"selector": ".nope"}, sf)


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_body_fallback(self):
        page = _page_with_body_text("Main page content")
        result = extract_text(page)
        assert "Main page content" in result
        assert "Page: Test" in result
        assert "URL: https://example.com" in result

    def test_content_container_preferred(self):
        """If <main> exists with text, use it over body."""
        page = make_mock_page()
        main_el = _mock_el("Main area content")
        body_el = _mock_el("Nav stuff\nMain area content\nFooter stuff")
        page.evaluate.return_value = None

        def qs(sel):
            if sel == "main":
                return main_el
            if sel == "body":
                return body_el
            return None

        page.query_selector.side_effect = qs
        result = extract_text(page)
        assert "Main area content" in result
        assert "Footer stuff" not in result

    def test_with_explicit_selector(self):
        page = make_mock_page()
        div = _mock_el("Scoped text")
        page.query_selector.return_value = div
        result = extract_text(page, selector=".content")
        assert "Scoped text" in result

    def test_selector_not_found_raises(self):
        page = make_mock_page()
        page.query_selector.return_value = None
        with pytest.raises(ValueError, match="Selector not found"):
            extract_text(page, selector=".missing")

    def test_empty_body(self):
        page = _page_with_body_text("")
        result = extract_text(page)
        assert "Page: Test" in result
        assert "URL: https://example.com" in result

    def test_strips_noise(self):
        """Verify that page.evaluate is called to strip noise selectors."""
        page = _page_with_body_text("Clean text")
        extract_text(page)
        page.evaluate.assert_called_once()
        call_args = page.evaluate.call_args
        assert "remove()" in call_args[0][0]


# ---------------------------------------------------------------------------
# do_links
# ---------------------------------------------------------------------------

class TestDoLinks:
    def test_requires_url_or_state(self, tmp_path):
        page = make_mock_page()
        with pytest.raises(ValueError, match="navigate"):
            do_links(page, {}, tmp_path / "state.json")

    def test_with_inline_url(self, tmp_path):
        sf = tmp_path / "state.json"
        page = make_mock_page()
        page.query_selector_all.return_value = []
        do_links(page, {"url": "https://example.com"}, sf)
        page.goto.assert_called_once_with("https://example.com", timeout=30000)

    def test_passes_selector(self, tmp_path):
        sf = tmp_path / "state.json"
        save_state(sf, "https://example.com")
        page = make_mock_page()
        page.query_selector_all.return_value = []
        do_links(page, {"selector": "nav"}, sf)
        page.query_selector_all.assert_called_once_with("nav a[href]")


# ---------------------------------------------------------------------------
# extract_links
# ---------------------------------------------------------------------------

class TestExtractLinks:
    def test_basic_links(self):
        page = make_mock_page()
        links = [
            _mock_el("Home", {"href": "https://example.com/"}),
            _mock_el("About", {"href": "https://example.com/about"}),
        ]
        page.query_selector_all.return_value = links
        result = extract_links(page)
        assert "1. Home — https://example.com/" in result
        assert "2. About — https://example.com/about" in result

    def test_filters_javascript_and_hash(self):
        page = make_mock_page()
        links = [
            _mock_el("Real", {"href": "https://example.com/page"}),
            _mock_el("JS", {"href": "javascript:void(0)"}),
            _mock_el("Hash", {"href": "#"}),
        ]
        page.query_selector_all.return_value = links
        result = extract_links(page)
        assert "Real" in result
        assert "JS" not in result
        assert "Hash" not in result.split("\n", 3)[-1]  # Not in the links section

    def test_deduplicates_hrefs(self):
        page = make_mock_page()
        links = [
            _mock_el("Link A", {"href": "https://example.com/page"}),
            _mock_el("Link B", {"href": "https://example.com/page"}),
        ]
        page.query_selector_all.return_value = links
        result = extract_links(page)
        assert "1. Link A" in result
        assert "Link B" not in result

    def test_skips_empty_text(self):
        page = make_mock_page()
        links = [
            _mock_el("", {"href": "https://example.com/empty"}),
            _mock_el("Visible", {"href": "https://example.com/visible"}),
        ]
        page.query_selector_all.return_value = links
        result = extract_links(page)
        assert "1. Visible" in result
        assert "empty" not in result

    def test_no_links_message(self):
        page = make_mock_page()
        page.query_selector_all.return_value = []
        result = extract_links(page)
        assert "(no links found)" in result

    def test_scoped_selector(self):
        page = make_mock_page()
        page.query_selector_all.return_value = []
        extract_links(page, selector="main")
        page.query_selector_all.assert_called_once_with("main a[href]")


# ---------------------------------------------------------------------------
# do_forms
# ---------------------------------------------------------------------------

class TestDoForms:
    def test_requires_url_or_state(self, tmp_path):
        page = make_mock_page()
        with pytest.raises(ValueError, match="navigate"):
            do_forms(page, {}, tmp_path / "state.json")

    def test_with_inline_url(self, tmp_path):
        sf = tmp_path / "state.json"
        page = make_mock_page()
        page.query_selector_all.return_value = []
        do_forms(page, {"url": "https://example.com"}, sf)
        page.goto.assert_called_once_with("https://example.com", timeout=30000)

    def test_passes_selector(self, tmp_path):
        sf = tmp_path / "state.json"
        save_state(sf, "https://example.com")
        page = make_mock_page()
        page.query_selector_all.return_value = []
        do_forms(page, {"selector": "#main"}, sf)
        page.query_selector_all.assert_called_once_with("#main form")


# ---------------------------------------------------------------------------
# extract_forms
# ---------------------------------------------------------------------------

class TestExtractForms:
    def test_no_forms(self):
        page = make_mock_page()
        page.query_selector_all.return_value = []
        result = extract_forms(page)
        assert "(no forms found)" in result

    def test_basic_form(self):
        page = make_mock_page()
        # Build a form mock
        form = MagicMock()
        form.get_attribute.side_effect = lambda k: {
            "action": "/signup",
            "method": "POST",
        }.get(k)

        # Text input field
        field_input = MagicMock()
        field_input.evaluate.return_value = "input"
        field_input.get_attribute.side_effect = lambda k: {
            "type": "text",
            "name": "username",
            "placeholder": "Enter username",
            "required": "",
        }.get(k)
        field_input.inner_text.return_value = ""

        # Submit button
        field_btn = MagicMock()
        field_btn.evaluate.return_value = "input"
        field_btn.get_attribute.side_effect = lambda k: {
            "type": "submit",
            "value": "Sign Up",
        }.get(k)
        field_btn.inner_text.return_value = ""

        form.query_selector_all.return_value = [field_input, field_btn]
        page.query_selector_all.return_value = [form]

        result = extract_forms(page)
        assert "Form 1 (action: /signup, method: POST):" in result
        assert "Enter username" in result
        assert "text, required" in result
        assert "Sign Up" in result
        assert "button" in result

    def test_select_field(self):
        page = make_mock_page()
        form = MagicMock()
        form.get_attribute.side_effect = lambda k: {"action": "/pick", "method": None}.get(k)

        select = MagicMock()
        select.evaluate.return_value = "select"
        select.get_attribute.side_effect = lambda k: {
            "name": "country",
            "required": None,
        }.get(k)
        select.inner_text.return_value = ""

        opt1 = MagicMock()
        opt1.inner_text.return_value = "Italy"
        opt2 = MagicMock()
        opt2.inner_text.return_value = "France"
        select.query_selector_all.return_value = [opt1, opt2]

        form.query_selector_all.return_value = [select]
        page.query_selector_all.return_value = [form]

        result = extract_forms(page)
        assert "country (select): [Italy, France]" in result

    def test_button_tag(self):
        """A <button> element (not input type=submit) is recognized as a button."""
        page = make_mock_page()
        form = MagicMock()
        form.get_attribute.side_effect = lambda k: {"action": "/go"}.get(k)

        btn = MagicMock()
        btn.evaluate.return_value = "button"
        btn.get_attribute.side_effect = lambda k: None
        btn.inner_text.return_value = "Submit Form"

        form.query_selector_all.return_value = [btn]
        page.query_selector_all.return_value = [form]

        result = extract_forms(page)
        assert "[Submit Form] (button)" in result

    def test_textarea_field(self):
        page = make_mock_page()
        form = MagicMock()
        form.get_attribute.side_effect = lambda k: {"action": "/msg"}.get(k)

        ta = MagicMock()
        ta.evaluate.return_value = "textarea"
        ta.get_attribute.side_effect = lambda k: {
            "name": "message",
            "placeholder": "Your message",
            "required": "",
        }.get(k)
        ta.inner_text.return_value = ""

        form.query_selector_all.return_value = [ta]
        page.query_selector_all.return_value = [form]

        result = extract_forms(page)
        assert "Your message (textarea, required)" in result

    def test_method_defaults_to_get(self):
        page = make_mock_page()
        form = MagicMock()
        form.get_attribute.side_effect = lambda k: {"action": "/search"}.get(k)
        form.query_selector_all.return_value = []
        page.query_selector_all.return_value = [form]

        result = extract_forms(page)
        assert "method: GET" in result

    def test_scoped_selector(self):
        page = make_mock_page()
        page.query_selector_all.return_value = []
        extract_forms(page, selector="#main")
        page.query_selector_all.assert_called_once_with("#main form")
