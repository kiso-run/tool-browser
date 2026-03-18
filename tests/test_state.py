"""Tests for save_state / load_state."""
import json
import threading

import pytest

from run import load_state, save_state


def test_save_and_load(tmp_path):
    f = tmp_path / "state.json"
    save_state(f, "https://example.com/page")
    assert load_state(f) == "https://example.com/page"


def test_load_missing(tmp_path):
    assert load_state(tmp_path / "nonexistent.json") is None


def test_load_corrupt(tmp_path):
    f = tmp_path / "state.json"
    f.write_text("not json{{{")
    assert load_state(f) is None


def test_load_missing_url_key(tmp_path):
    f = tmp_path / "state.json"
    f.write_text(json.dumps({"other": "value"}))
    assert load_state(f) is None


def test_save_overwrites(tmp_path):
    f = tmp_path / "state.json"
    save_state(f, "https://first.com")
    save_state(f, "https://second.com")
    assert load_state(f) == "https://second.com"


def test_concurrent_state_writes(tmp_path):
    """Document that concurrent writes may corrupt state (write_text is not atomic)."""
    state_file = tmp_path / "state.json"
    errors = []

    def writer(url):
        for _ in range(50):
            try:
                save_state(state_file, url)
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=writer, args=("http://example.com/a",))
    t2 = threading.Thread(target=writer, args=("http://example.com/b",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    # After concurrent writes, file should still be valid JSON
    # (this may occasionally fail — documenting the risk)
    result = load_state(state_file)
    assert result is not None  # load_state returns None on corruption
    assert result.startswith("http://")


def test_load_state_handles_corruption(tmp_path):
    """load_state returns None on corrupted state file."""
    state_file = tmp_path / "state.json"
    state_file.write_text("not valid json {{{")
    result = load_state(state_file)
    assert result is None
