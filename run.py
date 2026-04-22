#!/usr/bin/env python3
"""
Crate — run.py
Runs the full pipeline in order:
  1. sync.py    — download new tracks
  2. analyze.py — score energy (only new tracks)
  3. sort.py    — preview sort, then optionally apply

Usage:
  venv/bin/python run.py
"""

import os
import subprocess
import sys

PYTHON = sys.executable
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(label, script):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}\n")
    result = subprocess.run([PYTHON, os.path.join(PROJECT_DIR, script)])
    if result.returncode != 0:
        print(f"\nERROR: {script} failed. Stopping.")
        sys.exit(1)


def main():
    run_step("Step 1 / 3 — Syncing new tracks", "sync.py")
    run_step("Step 2 / 3 — Analyzing energy", "analyze.py")

    print(f"\n{'='*60}")
    print(f"  Step 3 / 3 — Sorting into playlists")
    print(f"{'='*60}\n")

    # Dry run first so user can review sort_overrides.txt
    result = subprocess.run([PYTHON, os.path.join(PROJECT_DIR, "sort.py")])
    if result.returncode != 0:
        print("\nERROR: sort.py failed. Stopping.")
        sys.exit(1)

    overrides_file = os.path.join(PROJECT_DIR, "sort_overrides.txt")
    if not os.path.exists(overrides_file):
        print("\nNothing to sort.")
        return

    print("\nReview sort_overrides.txt and edit any assignments if needed.")
    answer = input("Apply sort? [y/n]: ").strip().lower()
    if answer == "y":
        result = subprocess.run([PYTHON, os.path.join(PROJECT_DIR, "sort.py"), "--apply"])
        if result.returncode != 0:
            print("\nERROR: sort.py --apply failed.")
            sys.exit(1)
    else:
        print("Sort skipped. Run 'venv/bin/python sort.py --apply' when ready.")


if __name__ == "__main__":
    main()
