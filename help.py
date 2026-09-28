#!/usr/bin/env python3
"""
Crate — help.py
Prints a quick reference: overview first, details after.

Usage:
  crate help
"""

HELP = """
CRATE — quick reference
=======================

COMMANDS
  crate run        full pipeline: yt-dlp check → sync → analyze → sort preview → apply? [y/n]
  crate sync       download new tracks from Spotify + SoundCloud → ~/Desktop/Music/_staging/
  crate analyze    score every track in _staging/ for energy (0–100) → analysis.csv
  crate sort       preview where each track goes → writes sort_overrides.txt
  crate sort --apply   move tracks into house/peak, house/warm up, house/closing
  crate rename     fix filenames to "Track Name - Artist" from ID3 tags (--apply to rename)
  crate update     check PyPI for newer yt-dlp + other dependencies
  crate help       this page

TYPICAL WORKFLOW
  1. crate run
  2. At "Apply sort?", answer y — or n to open sort_overrides.txt, edit it,
     then run: crate sort --apply
  3. Import the house/ folders into rekordbox


─────────────────────────────────────────────────────────────────────────────
SYNC — how downloads work
─────────────────────────────────────────────────────────────────────────────
  Fetches both playlists, dedupes them (SoundCloud version wins on a ≥90% match),
  skips anything in archive.txt, then tries each new track in this order,
  stopping at the first success:

    1. exact SoundCloud search    scsearch1:"Artist - Title"   (with Go+ cookies)
    2. fuzzy SoundCloud search    scsearch1:Artist - Title
    3. exact YouTube search       ytsearch1:"Artist - Title"
    4. fuzzy YouTube search       ytsearch1:Artist - Title

  Each result is verified before downloading:
    - title match ≥ 85%                          → accept
    - title match ≥ 60% AND duration within ±8s  → accept ("duration rescue")
    - otherwise                                  → reject, try the next strategy

  Output: 320kbps MP3 named "Track Name - Artist.mp3", tagged, with cover art.

  Quality
    Every file is 320kbps, but real quality depends on the source.
    - SoundCloud gives you whatever the uploader uploaded — often a 128–160kbps
      file, even with Go+.
    - YouTube audio is usually full-range (~20kHz) and often as good or better.
    - For tracks you'll play out on a big system, buy the lossless file
      (Beatport, Bandcamp, Traxsource).

  DRM-protected tracks
    Many label releases on SoundCloud are DRM protected and can't be downloaded
    ("This video is DRM protected"). Sync falls back to YouTube automatically.
    Other options: buy the track, or stream it in rekordbox via SoundCloud Go+.

  Rate limiting (HTTP 429)
    SoundCloud throttles bulk requests. Sync waits 3s between tracks, 10s after
    any 429, and retries each search after 10s → 30s → 60s before falling back
    to YouTube. If every SC search is getting 429s:
      → stop the run (Ctrl+C), connect to a VPN (new IP), and rerun
      → or wait 30–60 minutes
    Back-to-back runs are what usually trigger it.

  Tracking files (project root)
    archive.txt   tracks downloaded — skipped on future runs
    failed.txt    tracks that failed all 4 strategies + reason (retried every run)
    sources.txt   where each track came from (SC or YT)

  Failed tracks are never archived, so they're retried automatically next run.
  To force a re-download, delete the MP3 and remove its line from archive.txt.


─────────────────────────────────────────────────────────────────────────────
ANALYZE — energy score
─────────────────────────────────────────────────────────────────────────────
  energy = 0.4 × loudness (RMS) + 0.3 × brightness (spectral centroid)
         + 0.3 × percussiveness (HPSS)

  Each part is normalized against the whole library, so scores are RELATIVE —
  existing scores shift a little when new tracks are added. That's expected.
  analysis.csv is also the cache: only new tracks get analyzed.
  Slow: ~15–30 min for 300+ tracks. Keep the lid open:
    caffeinate -i venv/bin/python analyze.py


─────────────────────────────────────────────────────────────────────────────
SORT — into house folders
─────────────────────────────────────────────────────────────────────────────
  peak      energy ≥ 70
  warm up   energy 59–69
  closing   energy < 59

  crate sort           preview + write sort_overrides.txt ("file.mp3 → peak")
  (edit the file)      change any line to peak / warm up / closing
  crate sort --apply   move files, then delete sort_overrides.txt

  Thresholds live at the top of sort.py. A new preview overwrites
  sort_overrides.txt — apply your edits before running another sort.


─────────────────────────────────────────────────────────────────────────────
RENAME — fix filenames
─────────────────────────────────────────────────────────────────────────────
  For tracks you added by hand. Reads ID3 tags and renames to
  "Track Name - Artist.ext". Dry run by default; crate rename --apply to do it.


─────────────────────────────────────────────────────────────────────────────
UPDATE — keep yt-dlp working
─────────────────────────────────────────────────────────────────────────────
  YouTube and SoundCloud change often; an old yt-dlp breaks downloads.
  crate update:
    - yt-dlp: upgraded automatically, then smoke tested (1 SC search +
      1 YouTube download). If the test fails you're asked whether to roll back.
    - other packages: asks before each upgrade (librosa may shift energy scores)
    - rewrites requirements.txt to match
  crate run also checks yt-dlp first and offers to update it.


─────────────────────────────────────────────────────────────────────────────
TROUBLESHOOTING
─────────────────────────────────────────────────────────────────────────────
  YouTube "HTTP Error 403: Forbidden"       → crate update
  SoundCloud "HTTP Error 404" on searches   → crate update
  "429 Too Many Requests" / "rate limited"  → VPN or wait 30–60 min, rerun
  "This video is DRM protected"             → normal, falls back to YouTube
  .webp / .jpg / .part files in _staging/   → leftovers from failed downloads;
                                              delete them and rerun crate sync
  SC download sounds dull / low quality     → uploader's file was low bitrate;
                                              buy the track if it matters
  Track in failed.txt                       → check the reason; retried each run
  Stopping a run                            → Ctrl+C (safe — nothing half-archived)
  SC cookies expired / Go+ not working      → re-export soundcloud.cookies from
                                              the browser (Get cookies.txt Locally)
"""


if __name__ == "__main__":
    print(HELP)
