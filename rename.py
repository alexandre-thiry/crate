#!/usr/bin/env python3
"""
Crate — rename.py
Renames audio files in ~/Desktop/Music/house/ to follow the
"Track Name - Artist.ext" convention using ID3 tags.

For each file:
  1. Read Title (TIT2) and Artist (TPE1) from ID3 tags
  2. Rename to "Title - Artist.ext"
  3. Skip if tags are missing or file already has the correct name

Supports MP3 and WAV. Dry-run by default — pass --apply to rename for real.
"""

import os
import sys
import re

from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.wave import WAVE

HOUSE_DIR = os.path.expanduser("~/Desktop/Music/house/")
AUDIO_EXTS = {".mp3", ".wav"}


def sanitize(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def get_tags(filepath):
    """Return (title, artist) from ID3 tags, or (None, None) if unavailable."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".wav":
            tags = WAVE(filepath)
        else:
            tags = ID3(filepath)
        title  = str(tags.get("TIT2", "")).strip()
        artist = str(tags.get("TPE1", "")).strip()
        return (title or None, artist or None)
    except (ID3NoHeaderError, Exception):
        return None, None


def main():
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("DRY RUN — no files will be renamed. Pass --apply to rename for real.\n")

    renamed = 0
    skipped = 0
    no_tags = 0

    for root, _, files in os.walk(HOUSE_DIR):
        for filename in sorted(files):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in AUDIO_EXTS:
                continue

            filepath = os.path.join(root, filename)
            title, artist = get_tags(filepath)

            if not title or not artist:
                print(f"  NO TAGS  {filename}")
                no_tags += 1
                continue

            new_name = f"{sanitize(title)} - {sanitize(artist)}{ext}"

            if new_name == filename:
                skipped += 1
                continue

            new_path = os.path.join(root, new_name)
            print(f"  RENAME   {filename}")
            print(f"        →  {new_name}")

            if not dry_run:
                if os.path.exists(new_path):
                    print(f"  SKIP (destination already exists)")
                    skipped += 1
                    continue
                os.rename(filepath, new_path)

            renamed += 1

    print(f"\n{'Would rename' if dry_run else 'Renamed'}: {renamed}")
    print(f"Already correct: {skipped}")
    if no_tags:
        print(f"No tags (skipped): {no_tags}")
    if dry_run and renamed > 0:
        print("\nRun with --apply to rename for real:")
        print("  venv/bin/python rename.py --apply")


if __name__ == "__main__":
    main()
