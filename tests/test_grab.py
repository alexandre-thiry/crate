import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grab import parse_link, folder_name, playlist_dir, GRAB_DIR


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


def test_folder_name_rejects_empty():
    assert folder_name("   ") is None
    assert folder_name("...") is None


def test_folder_name_allows_former_reserved_names():
    assert folder_name("house") == "house"


def test_playlist_dir_by_source():
    assert playlist_dir("spotify", "reggaeton") == os.path.join(GRAB_DIR, "Spotify", "reggaeton")
    assert playlist_dir("soundcloud", "mashups") == os.path.join(GRAB_DIR, "SoundCloud", "mashups")


def test_playlist_dir_rejects_empty_name():
    assert playlist_dir("spotify", "  ") is None


def test_grab_dir_location():
    assert GRAB_DIR == os.path.expanduser("~/Desktop/Music/Downloaded Playlists")
