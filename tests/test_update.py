import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from update import is_newer, parse_requirements, update_pins


def test_is_newer_date_versions():
    assert is_newer("2026.8.19", "2026.3.17")
    assert not is_newer("2026.3.17", "2026.8.19")


def test_is_newer_equal():
    assert not is_newer("2026.8.19", "2026.8.19")


def test_is_newer_zero_padded_and_extra_part():
    assert not is_newer("2026.08.19", "2026.8.19")
    assert is_newer("2026.8.19.1", "2026.8.19")


def test_is_newer_numeric_not_string_compare():
    assert is_newer("0.11.0", "0.9.2")


def test_parse_requirements():
    text = "mutagen==1.47.0\n\nyt-dlp==2026.8.19\n# comment\n"
    assert parse_requirements(text) == [("mutagen", "1.47.0"), ("yt-dlp", "2026.8.19")]


def test_update_pins_only_changes_given_packages():
    text = "mutagen==1.47.0\nyt-dlp==2026.3.17\nlibrosa==0.11.0\n"
    result = update_pins(text, {"yt-dlp": "2026.8.19"})
    assert result == "mutagen==1.47.0\nyt-dlp==2026.8.19\nlibrosa==0.11.0\n"


def test_update_pins_empty():
    text = "mutagen==1.47.0\n"
    assert update_pins(text, {}) == text
