#!/usr/bin/env python3
"""
Crate — sort.py
Reads analysis.csv and moves audio files (MP3, WAV) from ~/Desktop/Music/_staging/
into ~/Desktop/Music/house/ subfolders based on energy score.

Usage:
  venv/bin/python sort.py           # dry run — preview and write sort_overrides.txt
  venv/bin/python sort.py --apply   # apply sort_overrides.txt and move files

Workflow:
  1. Run without --apply to preview where each track will go
  2. Edit sort_overrides.txt to change any assignments
  3. Run with --apply to move files — sort_overrides.txt is deleted automatically

Thresholds:
  Peak    — energy >= 70
  Warm Up — energy 59–69
  Closing — energy < 59
"""

import csv
import os
import shutil
import sys

# --- Paths ---
PROJECT_DIR    = os.path.dirname(os.path.abspath(__file__))
STAGING_DIR    = os.path.expanduser("~/Desktop/Music/_staging/")
HOUSE_DIR      = os.path.expanduser("~/Desktop/Music/house/")
OUTPUT_CSV     = os.path.join(PROJECT_DIR, "analysis.csv")
OVERRIDES_FILE = os.path.join(PROJECT_DIR, "sort_overrides.txt")

# --- Thresholds ---
PEAK_THRESHOLD    = 70.0
CLOSING_THRESHOLD = 59.0

FOLDERS = {
    "peak":    os.path.join(HOUSE_DIR, "peak"),
    "warm up": os.path.join(HOUSE_DIR, "warm up"),
    "closing": os.path.join(HOUSE_DIR, "closing"),
}


def get_playlist(energy):
    if energy >= PEAK_THRESHOLD:
        return "peak"
    elif energy >= CLOSING_THRESHOLD:
        return "warm up"
    else:
        return "closing"


def load_overrides():
    """
    Parse sort_overrides.txt into a dict of {filename: playlist}.
    Each line format: "filename.mp3 → playlist"
    """
    overrides = {}
    if not os.path.exists(OVERRIDES_FILE):
        print("ERROR: sort_overrides.txt not found. Run without --apply first.")
        return None
    with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if " → " not in line:
                print(f"  WARNING: skipping malformed line {i}: {line!r}")
                continue
            filename, playlist = line.split(" → ", 1)
            playlist = playlist.strip().lower()
            if playlist not in FOLDERS:
                print(f"  WARNING: unknown playlist {playlist!r} on line {i} — must be peak, warm up, or closing")
                continue
            overrides[filename.strip()] = playlist
    return overrides


def dry_run():
    if not os.path.exists(OUTPUT_CSV):
        print("ERROR: analysis.csv not found. Run analyze.py first.")
        return

    tracks = []
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                filename = row["filename"]
                energy = float(row["energy"])
                src = os.path.join(STAGING_DIR, filename)
                if os.path.exists(src):
                    tracks.append((filename, energy))
            except (KeyError, ValueError):
                pass

    if not tracks:
        print("No tracks found in _staging/ to sort.")
        return

    print(f"DRY RUN — {len(tracks)} tracks to sort\n")

    lines = []
    counts = {"peak": 0, "warm up": 0, "closing": 0}
    for filename, energy in tracks:
        playlist = get_playlist(energy)
        counts[playlist] += 1
        print(f"  [{playlist.upper():7}]  {filename}")
        lines.append(f"{filename} → {playlist}")

    with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
        f.write("# Edit the playlist for any track, then run: venv/bin/python sort.py --apply\n")
        f.write("# Valid playlists: peak, warm up, closing\n\n")
        f.write("\n".join(lines) + "\n")

    print(f"\nSummary: {counts['peak']} peak, {counts['warm up']} warm up, {counts['closing']} closing")
    print(f"\nsort_overrides.txt written — edit it if needed, then run:")
    print(f"  venv/bin/python sort.py --apply")


def apply_sort():
    overrides = load_overrides()
    if overrides is None:
        return

    moved = {"peak": 0, "warm up": 0, "closing": 0}
    skipped = 0
    not_found = 0

    for filename, playlist in overrides.items():
        src = os.path.join(STAGING_DIR, filename)
        if not os.path.exists(src):
            not_found += 1
            continue

        dst = os.path.join(FOLDERS[playlist], filename)
        if os.path.exists(dst):
            skipped += 1
            continue

        shutil.move(src, dst)
        moved[playlist] += 1
        print(f"  [{playlist.upper():7}]  {filename}")

    print(f"\nDone.")
    print(f"  Peak:    {moved['peak']} tracks")
    print(f"  Warm Up: {moved['warm up']} tracks")
    print(f"  Closing: {moved['closing']} tracks")
    if skipped:
        print(f"  Skipped: {skipped} (already in destination)")
    if not_found:
        print(f"  Missing: {not_found} (listed in overrides but not found in _staging/)")

    os.remove(OVERRIDES_FILE)
    print(f"\nsort_overrides.txt deleted.")


if __name__ == "__main__":
    if "--apply" in sys.argv:
        apply_sort()
    else:
        dry_run()
