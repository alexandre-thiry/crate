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
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, COMM, ID3NoHeaderError, TALB
from mutagen.mp3 import MP3
from urllib.parse import quote
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
import yt_dlp
from thefuzz import fuzz

# --- Paths ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STAGING_DIR = os.path.expanduser("~/Desktop/Music/_staging/")
ARCHIVE_FILE = os.path.join(PROJECT_DIR, "archive.txt")
FAILED_FILE = os.path.join(PROJECT_DIR, "failed.txt")
SOURCES_FILE = os.path.join(PROJECT_DIR, "sources.txt")
COOKIES_FILE = os.path.join(PROJECT_DIR, "soundcloud.cookies")
SPOTIFY_CACHE = os.path.join(PROJECT_DIR, ".cache")

# --- Thresholds ---
DEDUP_THRESHOLD    = 90   # min similarity to treat two tracks as duplicates
TITLE_THRESHOLD    = 80   # min song-title match (artist ignored) — rejects other songs by the same artist
DURATION_THRESHOLD = 60   # min artist + title match when the length matches
VERIFY_THRESHOLD   = 85   # min artist + title match when the expected length is unknown
DURATION_TOLERANCE = 4    # seconds — candidates further than this from the expected length are rejected
RELAXED_TOLERANCE  = 10   # seconds — second try when nothing passes, clean results only (no video/live/remix markers)
SEARCH_RESULTS     = 5    # candidates checked per YouTube search

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

def get_spotify(config):
    """Log in to Spotify. Spotify refresh tokens expire after 6 months —
    when that happens, discard the cached token and redo the browser login."""
    auth = SpotifyOAuth(
        client_id=config["spotify_client_id"],
        client_secret=config["spotify_client_secret"],
        redirect_uri=config["spotify_redirect_uri"],
        scope="playlist-read-private",
        cache_path=SPOTIFY_CACHE,
    )
    try:
        auth.get_access_token(as_dict=False)
    except SpotifyOauthError as e:
        if "invalid_grant" not in str(e):
            raise
        print("  Spotify login expired (6-month limit). Opening browser to log in again...")
        if os.path.exists(SPOTIFY_CACHE):
            os.remove(SPOTIFY_CACHE)
        auth.get_access_token(as_dict=False)
    return spotipy.Spotify(auth_manager=auth)


def fetch_spotify_tracks(config, playlist_id):
    # Any Spotify failure stops the run — continuing would silently skip every Spotify track
    try:
        sp = get_spotify(config)
        results = sp.playlist_tracks(playlist_id)
    except Exception as e:
        print(f"  ERROR: Spotify failed: {e}")
        print("  Stopping so Spotify tracks aren't silently skipped. See: crate help")
        sys.exit(1)

    if not results:
        print("  ERROR: playlist_tracks returned None")
        sys.exit(1)

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


def fetch_soundcloud_tracks(url):
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

def load_archive(archive_file=ARCHIVE_FILE):
    if not os.path.exists(archive_file):
        return set()
    with open(archive_file, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def load_failed(failed_file=FAILED_FILE):
    if not os.path.exists(failed_file):
        return set()
    with open(failed_file, "r", encoding="utf-8") as f:
        tracks = set()
        for line in f:
            line = line.strip()
            if line:
                tracks.add(line.split(" — ")[0])
        return tracks


def remove_from_failed(track, failed_file=FAILED_FILE):
    if not os.path.exists(failed_file):
        return
    with open(failed_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    kept = [l for l in lines if not l.strip().startswith(track + " —") and l.strip() != track]
    with open(failed_file, "w", encoding="utf-8") as f:
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


def write_tags(filepath, artist, title, comment=None):
    try:
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()
        tags['TIT2'] = TIT2(encoding=3, text=title)
        tags['TPE1'] = TPE1(encoding=3, text=artist)
        tags['TPE2'] = TPE2(encoding=3, text=artist)
        tags.delall('TALB')
        if comment:
            tags.delall('COMM')
            tags.add(COMM(encoding=3, lang='eng', desc='', text=comment))
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


def _segments(s):
    """'Artist - Title (Mix)' → ['artist', 'title'] after cleaning, for per-part matching."""
    return [p.strip() for p in clean_for_compare(s).lower().split(" - ") if p.strip()]


def title_score(intended_track, returned_title):
    """Best fuzz.ratio between the intended song title and any ' - ' part of the returned title.
    Ignores the artist so a different song by the same artist scores low."""
    _, title = split_artist_title(intended_track)
    wanted = _segments(title or intended_track)
    got = _segments(returned_title)
    if not wanted or not got:
        return 0

    def score(w, g):
        # A number the intended title doesn't have means a different song ("Serrure #5" vs
        # "Serrure #667", "Bande Organisée 2"), and so does losing the number ("Drill FR 4" vs
        # "Drill FR"). A subset is fine: "Vol. 52/66" vs "#52"
        w_nums, g_nums = set(re.findall(r"\d+", w)), set(re.findall(r"\d+", g))
        if g_nums - w_nums or (w_nums and not g_nums):
            return 0
        return fuzz.ratio(w, g)
    return max(score(w, g) for w in wanted for g in got)


def full_score(intended_track, candidate):
    """Artist + title match: intended track vs returned title, and vs 'uploader - title'."""
    query = clean_for_compare(intended_track).lower()
    title = candidate.get("title") or ""
    uploader = candidate.get("uploader") or ""
    scores = [fuzz.partial_ratio(query, clean_for_compare(title).lower())]
    if uploader:
        scores.append(fuzz.partial_ratio(query, clean_for_compare(f"{uploader} - {title}").lower()))
    return max(scores)


PENALTY_PATTERNS = [r"official\s+(hd\s+)?(music\s+)?video", r"music\s+video", r"\blive\b", r"visuali[sz]er", r"\bremix\b"]


def penalty(candidate, intended_track):
    """Number of video/live/visualizer/remix markers inside the candidate title's brackets."""
    bracketed = " ".join(re.findall(r"[(\[]([^)\]]*)[)\]]", candidate.get("title") or "")).lower()
    patterns = PENALTY_PATTERNS
    if "remix" in intended_track.lower():
        patterns = [p for p in patterns if "remix" not in p]
    return sum(1 for p in patterns if re.search(p, bracketed))


# Not the track asked for: someone else's recording, or the audio was altered.
# Rejected outright unless the intended track itself carries the same marker (e.g. "… - SPED UP").
COPY_PATTERNS = {
    "tribute": r"\btribute\b",
    "cover": r"[(\[][^)\]]*\bcover\b[^)\]]*[)\]]|\bcover\s+(by|version)\b",
    "originally by": r"originally\s+(performed\s+)?by",
    "in the style of": r"in\s+the\s+style\s+of",
    "(by artist)": r"[(\[]\s*by\s+[^)\]]+[)\]]",
    "karaoke": r"karaoke",
    "8D": r"\b8d\b",
    "slowed": r"\bslowed\b",
    "sped up": r"sped[\s-]*up",
    "nightcore": r"nightcore",
    "instrumental": r"\binstrumental\b",
}


def copy_marker(candidate, intended_track):
    """Name of the first cover/altered-version marker in the candidate title, or None."""
    title = candidate.get("title") or ""
    for label, pattern in COPY_PATTERNS.items():
        if re.search(pattern, title, re.I) and not re.search(pattern, intended_track, re.I):
            return label
    return None


def is_preferred(candidate):
    """Official audio: YouTube Music result, 'Artist - Topic' channel, or '(Audio)' in the title."""
    uploader = (candidate.get("uploader") or "").lower()
    bracketed = " ".join(re.findall(r"[(\[]([^)\]]*)[)\]]", candidate.get("title") or "")).lower()
    return candidate.get("source") == "ytmusic" or uploader.endswith("- topic") or "audio" in bracketed


def pick_candidates(candidates, intended_track, expected_duration, tolerance=DURATION_TOLERANCE):
    """
    Checks search results against the intended track.
    Returns (passing, rejected): passing is best-first, rejected is [(candidate, reason)].

    Covers, tributes and altered versions (COPY_PATTERNS) are always rejected.
    Otherwise a candidate passes when its song title matches ≥ TITLE_THRESHOLD and either:
      - its length is within `tolerance` of expected_duration and artist + title ≥ DURATION_THRESHOLD, or
      - the expected length is unknown and artist + title ≥ VERIFY_THRESHOLD.
    Passing candidates are ranked: fewest penalties, then official audio, then closest length, then search order.
    """
    passing, rejected = [], []
    for c in candidates:
        t = title_score(intended_track, c.get("title") or "")
        full = full_score(intended_track, c)
        dur = c.get("duration")
        marker = copy_marker(c, intended_track)
        if marker:
            rejected.append((c, f"copy/altered: {marker}"))
        elif t < TITLE_THRESHOLD:
            rejected.append((c, f"title match {t}%"))
        elif expected_duration is None:
            if full < VERIFY_THRESHOLD:
                rejected.append((c, f"match {full}% (length unknown, needs {VERIFY_THRESHOLD}%)"))
            else:
                passing.append(c)
        elif dur is None:
            rejected.append((c, "length unknown"))
        elif abs(dur - expected_duration) > tolerance:
            rejected.append((c, f"length {dur - expected_duration:+.0f}s"))
        elif full < DURATION_THRESHOLD:
            rejected.append((c, f"match {full}%"))
        else:
            passing.append(c)

    def rank(c):
        diff = abs(c["duration"] - expected_duration) if expected_duration is not None else 0
        return (penalty(c, intended_track), not is_preferred(c), diff)
    passing.sort(key=rank)  # stable: ties keep search order
    return passing, rejected


def relaxed_candidates(candidates, intended_track, expected_duration):
    """Second try when nothing passed: allow up to RELAXED_TOLERANCE off, but only clean candidates
    (no official video / live / visualizer / remix markers) so music videos stay out."""
    passing, _ = pick_candidates(candidates, intended_track, expected_duration, tolerance=RELAXED_TOLERANCE)
    return [c for c in passing if penalty(c, intended_track) == 0]


def describe(candidate):
    dur = candidate.get("duration")
    dur_str = f"{int(dur) // 60}:{int(dur) % 60:02d}" if dur is not None else "?:??"
    return f"\"{candidate.get('title')}\" ({candidate.get('uploader') or '?'}) {dur_str}"


def _to_candidate(entry, source):
    return {
        "title": entry.get("title") or "",
        "uploader": entry.get("uploader") or entry.get("channel") or "",
        "duration": entry.get("duration"),
        "url": entry.get("webpage_url") or entry.get("url"),
        "source": source,
    }


def search_soundcloud(query):
    """Top SoundCloud result for query as a candidate list (with Go+ cookies, backoff on 429).
    Returns (candidates, hit_429)."""
    opts = {"quiet": True, "no_warnings": True, "cookiefile": COOKIES_FILE}
    hit_429 = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = None
        for wait in SC_RETRY_WAITS + [None]:
            try:
                info = ydl.extract_info(query, download=False)
                break
            except Exception as e:
                if "429" in str(e) and wait is not None:
                    hit_429 = True
                    print(f"\n  SC rate limited, waiting {wait}s...", end=" ", flush=True)
                    time.sleep(wait)
                else:
                    return [], hit_429
        if not info:
            return [], hit_429
        entries = [e for e in info.get("entries", [info]) if e]
        candidates = []
        for e in entries[:1]:
            # A bare URL reference with no title needs resolving
            if not e.get("title") and e.get("url"):
                try:
                    e = ydl.extract_info(e["url"], download=False)
                except Exception:
                    continue
            candidates.append(_to_candidate(e, "sc"))
    return candidates, hit_429


def search_youtube(track):
    """Top SEARCH_RESULTS YouTube video results — flat search already includes title, channel and length."""
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{SEARCH_RESULTS}:{track}", download=False)
    except Exception:
        return []
    return [_to_candidate(e, "yt") for e in (info or {}).get("entries") or [] if e]


def search_youtube_music(track):
    """Yields YouTube Music 'Songs' results one at a time. The flat search has no lengths,
    so each result is resolved individually (~2s) — the caller stops at the first that works."""
    url = "https://music.youtube.com/search?q=" + quote(track.replace(" - ", " ")) + "#songs"
    opts = {"quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL({**opts, "extract_flat": True, "playlistend": SEARCH_RESULTS}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return
    with yt_dlp.YoutubeDL(opts) as ydl:
        for e in ((info or {}).get("entries") or [])[:SEARCH_RESULTS]:
            if not e or not e.get("url"):
                continue
            try:
                yield _to_candidate(ydl.extract_info(e["url"], download=False), "ytmusic")
            except Exception:
                continue


def download_candidate(candidate, intended_track, expected_duration, out_dir, use_cookies,
                       tolerance=DURATION_TOLERANCE):
    """
    Downloads one verified candidate to out_dir as 'Title - Artist.mp3' (320kbps, tagged, cover art,
    source URL + original codec/bitrate in the comment tag).
    Deletes the file and returns None if its real length is off by more than `tolerance`.
    """
    artist, title = split_artist_title(intended_track)
    safe_name = sanitize_filename(f"{title} - {artist}") if title else sanitize_filename(intended_track)
    output_mp3 = os.path.join(out_dir, f"{safe_name}.mp3")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ],
        # YouTube thumbnails are 16:9 with the square cover centred — crop the centre square
        # so rekordbox shows it (SC artwork is already square, so the crop is a no-op there)
        "postprocessor_args": {
            "thumbnailsconvertor+ffmpeg_o": ["-c:v", "mjpeg", "-vf", "crop='min(iw,ih)':'min(iw,ih)'"],
        },
        "outtmpl": os.path.join(out_dir, f"{safe_name}.%(ext)s"),
    }
    if use_cookies:
        opts["cookiefile"] = COOKIES_FILE

    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(candidate["url"], download=True)
        except Exception:
            return None

    if not os.path.exists(output_mp3):
        # Fallback: rename if postprocessor produced a different extension
        for ext in ["m4a", "aac", "mp4", "webm", "opus", "ogg"]:
            candidate_file = os.path.join(out_dir, f"{safe_name}.{ext}")
            if os.path.exists(candidate_file):
                os.rename(candidate_file, output_mp3)
                break
        else:
            return None

    if expected_duration is not None:
        actual = MP3(output_mp3).info.length
        if abs(actual - expected_duration) > tolerance:
            print(f"    ✗ downloaded file is {actual - expected_duration:+.0f}s off — deleted")
            os.remove(output_mp3)
            return None

    abr = info.get("abr")
    source = f"{info.get('webpage_url') or candidate['url']} | {info.get('acodec') or '?'} {round(abr) if abr else '?'}kbps"
    write_tags(output_mp3, artist, title or intended_track, comment=source)
    return output_mp3


def try_candidates(candidates, track, expected_duration, out_dir, use_cookies):
    """Verifies candidates, logs every rejection, downloads the best passing one.
    Falls through to the next passing candidate if a download fails its length check."""
    passing, rejected = pick_candidates(candidates, track, expected_duration)
    for c, reason in rejected:
        print(f"    ✗ {describe(c)} — {reason}")
    for c in passing:
        print(f"    ✓ {describe(c)}")
        path = download_candidate(c, track, expected_duration, out_dir, use_cookies)
        if path:
            return path
    return None


def download_track(track, expected_duration=None, out_dir=STAGING_DIR, use_soundcloud=True):
    """
    Tries each source in priority order, stopping at the first verified download:
      1. exact SoundCloud   2. fuzzy SoundCloud   3. YouTube Music songs (top 5)   4. YouTube videos (top 5)
    If nothing passes, one more try over everything seen with RELAXED_TOLERANCE (clean results only).
    Returns (success: bool, source: str | None, reason: str | None, hit_429: bool).
    source is 'SC' or 'YT' on success, None on failure.
    """
    ever_429 = False
    seen = []

    if use_soundcloud:
        for query, label in [(f'scsearch1:"{track}"', "exact SC"), (f"scsearch1:{track}", "fuzzy SC")]:
            print(f"  → {label}")
            candidates, hit_429 = search_soundcloud(query)
            ever_429 = ever_429 or hit_429
            seen += candidates
            if try_candidates(candidates, track, expected_duration, out_dir, use_cookies=True):
                return True, "SC", None, ever_429

    print("  → YT Music")
    for c in search_youtube_music(track):
        seen.append(c)
        if try_candidates([c], track, expected_duration, out_dir, use_cookies=False):
            return True, "YT", None, ever_429

    print("  → YT search")
    candidates = search_youtube(track)
    seen += candidates
    if try_candidates(candidates, track, expected_duration, out_dir, use_cookies=False):
        return True, "YT", None, ever_429

    if expected_duration is not None:
        relaxed = relaxed_candidates(seen, track, expected_duration)
        if relaxed:
            print(f"  → second try (±{RELAXED_TOLERANCE}s, clean results only)")
        for c in relaxed:
            print(f"    ✓ {describe(c)}")
            if download_candidate(c, track, expected_duration, out_dir, use_cookies=c["source"] == "sc",
                                  tolerance=RELAXED_TOLERANCE):
                return True, "SC" if c["source"] == "sc" else "YT", None, ever_429

    return False, None, "no result passed title + length checks", ever_429


def download_all(tracks, out_dir, archive_file, failed_file, sources_file=None):
    """
    Downloads each (track, duration) into out_dir, logging successes to archive_file
    (and sources_file if given) and failures to failed_file.
    Returns (downloaded, sc_count, yt_count, failed_count).
    """
    failed = load_failed(failed_file)
    downloaded_count = 0
    failed_count = 0
    sc_count = 0
    yt_count = 0
    current_delay = TRACK_DELAY

    for i, (track, duration) in enumerate(tracks, 1):
        if i > 1:
            time.sleep(current_delay)
        print(f"[{i}/{len(tracks)}] {track}")
        success, source, reason, hit_429 = download_track(track, expected_duration=duration, out_dir=out_dir)

        if hit_429 and current_delay < TRACK_DELAY_AFTER_429:
            current_delay = TRACK_DELAY_AFTER_429
            print(f"  SC throttling detected — increasing track delay to {current_delay}s for remaining downloads")

        if success:
            with open(archive_file, "a", encoding="utf-8") as f:
                f.write(f"{track}\n")
            if sources_file:
                with open(sources_file, "a", encoding="utf-8") as f:
                    f.write(f"{track} — {source}\n")
            if track in failed:
                remove_from_failed(track, failed_file)
                failed.discard(track)
            downloaded_count += 1
            if source == "SC":
                sc_count += 1
            else:
                yt_count += 1
        else:
            if track not in failed:
                with open(failed_file, "a", encoding="utf-8") as f:
                    f.write(f"{track} — {reason}\n")
                failed.add(track)
            failed_count += 1

    return downloaded_count, sc_count, yt_count, failed_count


def main():
    config = load_config()
    os.makedirs(STAGING_DIR, exist_ok=True)

    print("Fetching Spotify tracks...")
    spotify_tracks = fetch_spotify_tracks(config, config["spotify_playlist_id"])
    print(f"  {len(spotify_tracks)} tracks found")

    print("Fetching SoundCloud tracks...")
    sc_tracks = fetch_soundcloud_tracks(config["soundcloud_playlist_url"])
    print(f"  {len(sc_tracks)} tracks found")

    print("Merging and deduplicating...")
    all_tracks = deduplicate_tracks(spotify_tracks, sc_tracks)
    print(f"  {len(all_tracks)} unique tracks total")

    archive = load_archive()
    new_tracks = [(t, d) for t, d in all_tracks if t not in archive]
    skipped_count = len(all_tracks) - len(new_tracks)
    print(f"  {skipped_count} already in archive, {len(new_tracks)} to download\n")

    downloaded_count, sc_count, yt_count, failed_count = download_all(
        new_tracks, STAGING_DIR, ARCHIVE_FILE, FAILED_FILE, SOURCES_FILE)

    print(f"\nDone. {downloaded_count} downloaded ({sc_count} from SC, {yt_count} from YT), "
          f"{skipped_count} skipped, {failed_count} failed.")


if __name__ == "__main__":
    main()
