#!/usr/bin/env python3
"""
Crate — sort.py
Reads analysis.csv and moves MP3s from ~/Desktop/Music/_staging/
into ~/Desktop/Music/house/ subfolders based on energy score.

Thresholds:
  Peak    — energy >= 70
  Warm Up — energy 59–69
  Closing — energy < 59
"""

import csv
import os
import shutil

# --- Paths ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STAGING_DIR = os.path.expanduser("~/Desktop/Music/_staging/")
HOUSE_DIR   = os.path.expanduser("~/Desktop/Music/house/")
OUTPUT_CSV  = os.path.join(PROJECT_DIR, "analysis.csv")

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


def main():
    if not os.path.exists(OUTPUT_CSV):
        print("ERROR: analysis.csv not found. Run analyze.py first.")
        return

    # Load scores from CSV
    tracks = []
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                tracks.append((row["filename"], float(row["energy"])))
            except (KeyError, ValueError):
                pass

    if not tracks:
        print("ERROR: analysis.csv is empty or malformed.")
        return

    moved = {"peak": 0, "warm up": 0, "closing": 0}
    skipped = 0
    not_found = 0

    for filename, energy in tracks:
        src = os.path.join(STAGING_DIR, filename)
        if not os.path.exists(src):
            not_found += 1
            continue

        playlist = get_playlist(energy)
        dst = os.path.join(FOLDERS[playlist], filename)

        if os.path.exists(dst):
            skipped += 1
            continue

        shutil.move(src, dst)
        moved[playlist] += 1
        print(f"[{playlist.upper():7}] {filename}")

    print(f"\nDone.")
    print(f"  Peak:    {moved['peak']} tracks")
    print(f"  Warm Up: {moved['warm up']} tracks")
    print(f"  Closing: {moved['closing']} tracks")
    if skipped:
        print(f"  Skipped: {skipped} (already in destination)")
    if not_found:
        print(f"  Missing: {not_found} (in CSV but not in _staging/)")


if __name__ == "__main__":
    main()
