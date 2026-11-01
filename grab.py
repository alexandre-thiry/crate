#!/usr/bin/env python3
"""
Crate — grab.py
Downloads any Spotify or SoundCloud playlist from a link into
~/Desktop/Music/Downloaded Playlists/<Spotify|SoundCloud>/<Playlist Name>/, using the same SC → YT search order as sync.py.
Re-running the same link only downloads tracks added since last time.

Usage:
  crate grab <spotify or soundcloud playlist link>
"""

import os
import re
import sys
from urllib.parse import urlparse

import yt_dlp

from sync import (
    COOKIES_FILE, download_all, fetch_soundcloud_tracks, fetch_spotify_tracks,
    get_spotify, load_archive, load_config, sanitize_filename,
)

GRAB_DIR = os.path.expanduser("~/Desktop/Music/Downloaded Playlists")
SOURCE_FOLDERS = {"spotify": "Spotify", "soundcloud": "SoundCloud"}
ARCHIVE_NAME = ".crate-archive.txt"
FAILED_NAME = "failed.txt"


def parse_link(link):
    """Returns ('spotify', playlist_id), ('soundcloud', url), or None if not a playlist link."""
    m = re.fullmatch(r"spotify:playlist:(\w+)", link.strip())
    if m:
        return "spotify", m.group(1)

    parsed = urlparse(link.strip())
    host = parsed.netloc.lower()
    if host == "open.spotify.com":
        m = re.search(r"/playlist/(\w+)", parsed.path)
        return ("spotify", m.group(1)) if m else None
    if host in ("soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"):
        return "soundcloud", link.strip()
    return None


def folder_name(playlist_name):
    """Safe folder name for a playlist, or None if nothing usable is left."""
    name = sanitize_filename(playlist_name).strip().rstrip(".").strip()
    return name or None


def playlist_dir(kind, playlist_name):
    """Landing folder for a playlist: GRAB_DIR/<Spotify|SoundCloud>/<name>, or None if the name is unusable."""
    name = folder_name(playlist_name)
    return os.path.join(GRAB_DIR, SOURCE_FOLDERS[kind], name) if name else None


def spotify_playlist_name(config, playlist_id):
    try:
        return get_spotify(config).playlist(playlist_id, fields="name")["name"]
    except Exception as e:
        print(f"ERROR: could not open Spotify playlist: {e}")
        print("  Only your own, followed, or public playlists can be read.")
        sys.exit(1)


def soundcloud_playlist_name(url):
    opts = {"extract_flat": True, "quiet": True, "no_warnings": True, "cookiefile": COOKIES_FILE}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False).get("title") or ""
    except Exception as e:
        print(f"ERROR: could not open SoundCloud playlist: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: crate grab <spotify or soundcloud playlist link>")
        sys.exit(1)

    link = parse_link(sys.argv[1])
    if not link:
        print("ERROR: not a Spotify or SoundCloud playlist link.")
        sys.exit(1)
    kind, ref = link

    config = load_config()
    if kind == "spotify":
        playlist_name = spotify_playlist_name(config, ref)
    else:
        playlist_name = soundcloud_playlist_name(ref)

    out_dir = playlist_dir(kind, playlist_name)
    if not out_dir:
        print(f"ERROR: can't use playlist name {playlist_name!r} as a folder. Rename the playlist and retry.")
        sys.exit(1)

    archive_file = os.path.join(out_dir, ARCHIVE_NAME)
    failed_file = os.path.join(out_dir, FAILED_NAME)
    os.makedirs(out_dir, exist_ok=True)
    print(f"Playlist: {playlist_name}")
    print(f"Folder:   {out_dir}\n")

    print("Fetching tracks...")
    if kind == "spotify":
        tracks = fetch_spotify_tracks(config, ref)
    else:
        tracks = fetch_soundcloud_tracks(ref)
    # Same track listed twice in a playlist → download once
    unique = {}
    for t, d in tracks:
        unique.setdefault(t, d)
    tracks = list(unique.items())
    print(f"  {len(tracks)} tracks found")
    if not tracks:
        print("Nothing to download.")
        return

    archive = load_archive(archive_file)
    new_tracks = [(t, d) for t, d in tracks if t not in archive]
    skipped_count = len(tracks) - len(new_tracks)
    print(f"  {skipped_count} already downloaded, {len(new_tracks)} to download\n")

    downloaded_count, sc_count, yt_count, failed_count = download_all(
        new_tracks, out_dir, archive_file, failed_file)

    print(f"\nDone. {downloaded_count} downloaded ({sc_count} from SC, {yt_count} from YT), "
          f"{skipped_count} skipped, {failed_count} failed.")
    if failed_count:
        print(f"See {failed_file}")


if __name__ == "__main__":
    main()
