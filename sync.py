#!/usr/bin/env python3
"""
Crate — sync.py
Fetches tracks from Spotify and SoundCloud playlists, deduplicates,
and downloads new tracks to ~/Desktop/Music/_staging/
"""

import os
import re
import sys
import time

from dotenv import load_dotenv
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, ID3NoHeaderError, TALB
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import yt_dlp
from thefuzz import fuzz

# --- Paths ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STAGING_DIR = os.path.expanduser("~/Desktop/Music/_staging/")
ARCHIVE_FILE = os.path.join(PROJECT_DIR, "archive.txt")
FAILED_FILE = os.path.join(PROJECT_DIR, "failed.txt")
SOURCES_FILE = os.path.join(PROJECT_DIR, "sources.txt")
COOKIES_FILE = os.path.join(PROJECT_DIR, "soundcloud.cookies")

# --- Thresholds ---
DEDUP_THRESHOLD    = 90   # min similarity to treat two tracks as duplicates
VERIFY_THRESHOLD   = 85   # min partial_ratio to accept a yt-dlp result on title alone
DURATION_THRESHOLD = 60   # min partial_ratio when duration match rescues a low score
DURATION_TOLERANCE = 8    # seconds — duration must match within this to rescue

# --- Rate limiting ---
TRACK_DELAY         = 3     # seconds between each track download (avoids SC throttling)
TRACK_DELAY_AFTER_429 = 10  # seconds between tracks after a 429 has been hit
SC_RETRY_WAITS      = [10, 30, 60]  # exponential backoff for SC 429 retries


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    load_dotenv()
    config = {
        "spotify_client_id":     os.getenv("SPOTIFY_CLIENT_ID"),
        "spotify_client_secret": os.getenv("SPOTIFY_CLIENT_SECRET"),
        "spotify_redirect_uri":  os.getenv("SPOTIFY_REDIRECT_URI"),
        "spotify_playlist_id":   os.getenv("SPOTIFY_PLAYLIST_ID"),
        "soundcloud_playlist_url": os.getenv("SOUNDCLOUD_PLAYLIST_URL"),
    }
    missing = [k for k, v in config.items() if not v]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
    return config


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_spotify_tracks(config):
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=config["spotify_client_id"],
        client_secret=config["spotify_client_secret"],
        redirect_uri=config["spotify_redirect_uri"],
        scope="playlist-read-private",
    ))

    try:
        results = sp.playlist_tracks(config["spotify_playlist_id"])
    except Exception as e:
        print(f"  ERROR calling playlist_tracks: {e}")
        return []

    if not results:
        print("  ERROR: playlist_tracks returned None")
        return []

    print(f"  total tracks reported by Spotify: {results.get('total', 'unknown')}")

    tracks = []
    page = 1
    while results:
        items = results.get("items") or []
        print(f"  page {page}: {len(items)} items")
        for item in items:
            track = item.get("track") or item.get("item")
            if not track:
                print(f"    WARNING: item with no track field: {item}")
                continue
            artist = track["artists"][0]["name"] if track.get("artists") else ""
            title = track.get("name", "")
            duration_ms = track.get("duration_ms")
            duration = round(duration_ms / 1000) if duration_ms else None
            if artist and title:
                tracks.append((f"{artist} - {title}", duration))
            else:
                print(f"    WARNING: missing artist or title — artist={artist!r} title={title!r}")
        results = sp.next(results) if results.get("next") else None
        page += 1

    return tracks


def fetch_soundcloud_tracks(config):
    url = config["soundcloud_playlist_url"]
    print(f"  URL: {url}")

    flat_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "cookiefile": COOKIES_FILE,
    }

    # Step 1: Get the list of track URLs from the playlist (flat, no full extraction)
    track_urls = []
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"  ERROR fetching SoundCloud playlist: {e}")
            return []

        if not info:
            print("  ERROR: yt-dlp returned no info for the SoundCloud URL")
            return []

        if "entries" not in info:
            print(f"  ERROR: no 'entries' in response. Keys: {list(info.keys())}")
            return []

        for entry in info["entries"]:
            if not entry:
                continue
            entry_url = entry.get("url") or entry.get("webpage_url")
            if entry_url:
                track_urls.append(entry_url)

    print(f"  {len(track_urls)} track URLs found, resolving metadata...")

    # Step 2: Resolve each URL individually to get full title + uploader + duration
    meta_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": COOKIES_FILE,
    }

    tracks = []
    with yt_dlp.YoutubeDL(meta_opts) as ydl:
        for i, track_url in enumerate(track_urls, 1):
            track_info = None
            for attempt in range(3):
                try:
                    track_info = ydl.extract_info(track_url, download=False)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < 2:
                        wait = (attempt + 1) * 3
                        print(f"  rate limited, retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"  WARNING: could not resolve {track_url}: {e}")
                        break
            if not track_info:
                continue

            title = track_info.get("title") or ""
            uploader = track_info.get("uploader") or track_info.get("channel") or ""
            duration = track_info.get("duration")  # seconds, may be None
            if not title:
                print(f"  WARNING: no title for {track_url}, skipping")
                continue

            track_str = f"{uploader} - {title}" if uploader else title
            tracks.append((track_str, duration))
            print(f"  [{i}/{len(track_urls)}] {track_str}")

    return tracks


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_tracks(spotify_tracks, sc_tracks):
    """
    Both inputs are lists of (track_str, duration) tuples.
    SC tracks are preferred; Spotify tracks are added only if no duplicate found.
    Returns a deduplicated list of (track_str, duration) tuples.
    """
    merged = list(sc_tracks)
    merged_strs = [t[0] for t in merged]

    for sp_track, sp_dur in spotify_tracks:
        is_dup = any(
            fuzz.ratio(sp_track.lower(), existing.lower()) >= DEDUP_THRESHOLD
            for existing in merged_strs
        )
        if not is_dup:
            merged.append((sp_track, sp_dur))
            merged_strs.append(sp_track)

    return merged


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------

def load_archive():
    if not os.path.exists(ARCHIVE_FILE):
        return set()
    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def load_failed():
    if not os.path.exists(FAILED_FILE):
        return set()
    with open(FAILED_FILE, "r", encoding="utf-8") as f:
        tracks = set()
        for line in f:
            line = line.strip()
            if line:
                tracks.add(line.split(" — ")[0])
        return tracks


def remove_from_failed(track):
    if not os.path.exists(FAILED_FILE):
        return
    with open(FAILED_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    kept = [l for l in lines if not l.strip().startswith(track + " —") and l.strip() != track]
    with open(FAILED_FILE, "w", encoding="utf-8") as f:
        f.writelines(kept)


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def split_artist_title(intended_track):
    """Split 'Artist - Title' into (artist, title). Returns (intended_track, '') if no separator."""
    if ' - ' in intended_track:
        artist, title = intended_track.split(' - ', 1)
        return artist.strip(), title.strip()
    return intended_track.strip(), ''


def write_tags(filepath, artist, title):
    try:
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()
        tags['TIT2'] = TIT2(encoding=3, text=title)
        tags['TPE1'] = TPE1(encoding=3, text=artist)
        tags['TPE2'] = TPE2(encoding=3, text=artist)
        tags.delall('TALB')
        tags.save(filepath)
    except Exception as e:
        print(f"  WARNING: could not write tags: {e}")


def clean_for_compare(s):
    """Strip noise added by platforms before fuzzy comparison — only used for matching, never for file naming."""
    # Remove version/edit suffixes in parentheses or brackets
    s = re.sub(r'\s*\([^)]*\)', '', s)
    s = re.sub(r'\s*\[[^\]]*\]', '', s)
    # Remove feat./ft./featuring clauses
    s = re.sub(r'\s+(?:feat\.?|ft\.?|featuring)\s+[^-]+', '', s, flags=re.IGNORECASE)
    # Remove collab notation " x Collab" or " X Collab" only when it appears before " - "
    # (leaves legitimate "&" in artist names like "Oden & Fatzo" untouched)
    s = re.sub(r'\s+[xX]\s+[^-]+(?=\s+-\s+)', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def duration_matches(expected, returned):
    """True if both durations are known and within DURATION_TOLERANCE seconds."""
    if expected is None or returned is None:
        return False
    return abs(expected - returned) <= DURATION_TOLERANCE


def try_download(query, intended_track, expected_duration=None, use_cookies=False, label=""):
    """
    Single download attempt for the given search query.

    Verification logic:
      - PASS if title/full score >= VERIFY_THRESHOLD (85)
      - PASS if score >= DURATION_THRESHOLD (60) AND duration matches within tolerance
      - FAIL otherwise

    Downloads to STAGING_DIR as 'Title - Artist.mp3' with ID3 tags.
    Returns (output_path, hit_429) on success, (None, hit_429) on failure.
    hit_429 is True if SC rate-limited at any point so the caller can adapt pacing.
    """
    artist, title = split_artist_title(intended_track)
    safe_name = sanitize_filename(f"{title} - {artist}") if title else sanitize_filename(intended_track)
    outtmpl = os.path.join(STAGING_DIR, f"{safe_name}.%(ext)s")
    output_mp3 = os.path.join(STAGING_DIR, f"{safe_name}.mp3")

    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
    }
    if use_cookies:
        base_opts["cookiefile"] = COOKIES_FILE

    # Step 1: Extract info without downloading (exponential backoff on SC 429)
    info = None
    hit_429 = False
    with yt_dlp.YoutubeDL(base_opts) as ydl:
        attempts = SC_RETRY_WAITS + [None] if use_cookies else [None]
        for wait in attempts:
            try:
                info = ydl.extract_info(query, download=False)
                break
            except Exception as e:
                if use_cookies and "429" in str(e) and wait is not None:
                    hit_429 = True
                    print(f"\n  SC rate limited, waiting {wait}s...", end=" ", flush=True)
                    time.sleep(wait)
                else:
                    return None, hit_429

        if not info:
            return None, hit_429

        # Search queries return a playlist wrapper with entries
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                return None
            result = entries[0]
            # If the entry is a bare URL reference with no title, resolve it
            if not result.get("title") and result.get("url"):
                try:
                    result = ydl.extract_info(result["url"], download=False)
                except Exception:
                    return None
        else:
            result = info

        if not result or not result.get("title"):
            return None

        # Step 2: Verify the result matches the intended track
        returned_title    = result.get("title", "")
        uploader          = result.get("uploader") or result.get("channel") or ""
        returned_full     = f"{uploader} - {returned_title}" if uploader else returned_title
        returned_duration = result.get("duration")  # seconds, may be None

        clean_query = clean_for_compare(intended_track).lower()
        score_title = fuzz.partial_ratio(clean_query, clean_for_compare(returned_title).lower())
        score_full  = fuzz.partial_ratio(clean_query, clean_for_compare(returned_full).lower())
        best_score  = max(score_title, score_full)

        dur_match   = duration_matches(expected_duration, returned_duration)
        passed      = best_score >= VERIFY_THRESHOLD or (best_score >= DURATION_THRESHOLD and dur_match)

        verdict = "PASS" if passed else "FAIL"
        if passed and best_score < VERIFY_THRESHOLD:
            verdict += " (duration rescue)"

        platform = "SoundCloud" if use_cookies else "YouTube"
        exp_dur_str = f"{expected_duration}s" if expected_duration is not None else "unknown"
        ret_dur_str = f"{returned_duration}s" if returned_duration is not None else "unknown"

        print(f"  [DEBUG] Platform:      {platform} ({label})")
        print(f"  [DEBUG] Title query:   {intended_track}")
        print(f"  [DEBUG] Title result:  {returned_title}")
        print(f"  [DEBUG] Full result:   {returned_full}")
        print(f"  [DEBUG] Score (title): {score_title} | Score (full): {score_full} | {verdict}")
        print(f"  [DEBUG] Duration:      expected={exp_dur_str}  returned={ret_dur_str}  match={dur_match}")

        if not passed:
            return None, hit_429

        track_url = result.get("webpage_url") or result.get("url")
        if not track_url:
            return None, hit_429

    # Step 3: Download using the verified URL
    download_opts = {
        **base_opts,
        "format": "bestaudio/best",
        "writethumbnail": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {
                "key": "EmbedThumbnail",
                "already_have_thumbnail": False,
            },
        ],
        "outtmpl": outtmpl,
    }

    with yt_dlp.YoutubeDL(download_opts) as ydl:
        try:
            ydl.download([track_url])
        except Exception:
            return None, hit_429

    if os.path.exists(output_mp3):
        write_tags(output_mp3, artist, title or intended_track)
        return output_mp3, hit_429

    # Fallback: rename if postprocessor produced a different extension
    for ext in ["m4a", "aac", "mp4", "webm", "opus", "ogg"]:
        candidate = os.path.join(STAGING_DIR, f"{safe_name}.{ext}")
        if os.path.exists(candidate):
            os.rename(candidate, output_mp3)
            write_tags(output_mp3, artist, title or intended_track)
            return output_mp3, hit_429

    return None, hit_429


def download_track(track, expected_duration=None):
    """
    Tries all 4 download strategies in priority order.
    Returns (success: bool, source: str | None, reason: str | None, hit_429: bool).
    source is 'SC' or 'YT' on success, None on failure.
    """
    strategies = [
        (f'scsearch1:"{track}"', True,  "exact SC", "SC"),
        (f'scsearch1:{track}',   True,  "fuzzy SC", "SC"),
        (f'ytsearch1:"{track}"', False, "exact YT", "YT"),
        (f'ytsearch1:{track}',   False, "fuzzy YT", "YT"),
    ]

    ever_429 = False
    for query, use_cookies, label, source in strategies:
        print(f"  → {label}...", end=" ", flush=True)
        result, hit_429 = try_download(query, track, expected_duration=expected_duration,
                                       use_cookies=use_cookies, label=label)
        if hit_429:
            ever_429 = True
        if result:
            print("✓")
            return True, source, None, ever_429
        print("✗")

    return False, None, "not found on SC or YT", ever_429


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    config = load_config()
    os.makedirs(STAGING_DIR, exist_ok=True)

    print("Fetching Spotify tracks...")
    spotify_tracks = fetch_spotify_tracks(config)
    print(f"  {len(spotify_tracks)} tracks found")

    print("Fetching SoundCloud tracks...")
    sc_tracks = fetch_soundcloud_tracks(config)
    print(f"  {len(sc_tracks)} tracks found")

    print("Merging and deduplicating...")
    all_tracks = deduplicate_tracks(spotify_tracks, sc_tracks)
    print(f"  {len(all_tracks)} unique tracks total")

    archive = load_archive()
    failed = load_failed()
    new_tracks = [(t, d) for t, d in all_tracks if t not in archive]
    skipped_count = len(all_tracks) - len(new_tracks)
    print(f"  {skipped_count} already in archive, {len(new_tracks)} to download\n")

    downloaded_count = 0
    failed_count = 0
    sc_count = 0
    yt_count = 0
    current_delay = TRACK_DELAY

    for i, (track, duration) in enumerate(new_tracks, 1):
        if i > 1:
            time.sleep(current_delay)
        print(f"[{i}/{len(new_tracks)}] {track}")
        success, source, reason, hit_429 = download_track(track, expected_duration=duration)

        if hit_429 and current_delay < TRACK_DELAY_AFTER_429:
            current_delay = TRACK_DELAY_AFTER_429
            print(f"  SC throttling detected — increasing track delay to {current_delay}s for remaining downloads")

        if success:
            with open(ARCHIVE_FILE, "a", encoding="utf-8") as f:
                f.write(f"{track}\n")
            with open(SOURCES_FILE, "a", encoding="utf-8") as f:
                f.write(f"{track} — {source}\n")
            if track in failed:
                remove_from_failed(track)
                failed.discard(track)
            downloaded_count += 1
            if source == "SC":
                sc_count += 1
            else:
                yt_count += 1
        else:
            if track not in failed:
                with open(FAILED_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{track} — {reason}\n")
                failed.add(track)
            failed_count += 1

    print(f"\nDone. {downloaded_count} downloaded ({sc_count} from SC, {yt_count} from YT), "
          f"{skipped_count} skipped, {failed_count} failed.")


if __name__ == "__main__":
    main()
