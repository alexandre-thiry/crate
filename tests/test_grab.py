import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grab import parse_link, folder_name


def test_parse_link_spotify_url():
    assert parse_link("https://open.spotify.com/playlist/0wEGGfxJMbPZK8KexciY2u") == \
        ("spotify", "0wEGGfxJMbPZK8KexciY2u")


def test_parse_link_spotify_url_with_query_and_locale():
    assert parse_link("https://open.spotify.com/intl-fr/playlist/0wEGGfxJMbPZK8KexciY2u?si=abc123") == \
        ("spotify", "0wEGGfxJMbPZK8KexciY2u")


def test_parse_link_spotify_uri():
    assert parse_link("spotify:playlist:0wEGGfxJMbPZK8KexciY2u") == \
        ("spotify", "0wEGGfxJMbPZK8KexciY2u")


def test_parse_link_soundcloud_set():
    url = "https://soundcloud.com/ixcily/sets/dj-master-playlist?si=xyz"
    assert parse_link(url) == ("soundcloud", url)


def test_parse_link_soundcloud_short_link():
    url = "https://on.soundcloud.com/AbCdEf"
    assert parse_link(url) == ("soundcloud", url)


def test_parse_link_rejects_other_links():
    assert parse_link("https://open.spotify.com/album/123") is None
    assert parse_link("https://www.youtube.com/playlist?list=abc") is None
    assert parse_link("not a link") is None


def test_folder_name_sanitizes():
    assert folder_name("Techno: Late / Night?") == "Techno_ Late _ Night_"


def test_folder_name_strips_whitespace_and_dots():
    assert folder_name("  Summer 26... ") == "Summer 26"


def test_folder_name_rejects_reserved_and_empty():
    assert folder_name("house") is None
    assert folder_name("House") is None
    assert folder_name("_staging") is None
    assert folder_name("Unsorted") is None
    assert folder_name("   ") is None
