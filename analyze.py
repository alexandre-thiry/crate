#!/usr/bin/env python3
"""
Crate — analyze.py
Scans ~/Desktop/Music/_staging/ for MP3s, computes RMS energy (0-100)
and BPM via LibROSA, and writes analysis.csv to the project root.
"""

import csv
import os

import librosa
import numpy as np

# --- Paths ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STAGING_DIR = os.path.expanduser("~/Desktop/Music/_staging/")
OUTPUT_CSV  = os.path.join(PROJECT_DIR, "analysis.csv")


def normalize_energy(raw_values):
    """
    Normalize a list of raw RMS floats to 0–100 relative to the maximum.
    Returns a list of floats in the same order as the input.
    """
    if not raw_values:
        return []
    max_val = max(raw_values)
    if max_val == 0:
        return [0.0] * len(raw_values)
    return [round((v / max_val) * 100, 1) for v in raw_values]


def analyze_track(filepath):
    """
    Load an MP3 and return (raw_rms, bpm).
    raw_rms is the mean RMS energy as a float.
    bpm is rounded to 1 decimal place.
    Returns (None, None) on error.
    """
    try:
        y, sr = librosa.load(filepath, mono=True)
        rms = float(np.mean(librosa.feature.rms(y=y)))
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = round(float(tempo), 1)
        return rms, bpm
    except Exception as e:
        print(f"  WARNING: could not analyze {os.path.basename(filepath)}: {e}")
        return None, None


def main():
    mp3_files = sorted([
        f for f in os.listdir(STAGING_DIR) if f.lower().endswith(".mp3")
    ])

    if not mp3_files:
        print("No MP3 files found in _staging/. Nothing to analyze.")
        return

    print(f"Analyzing {len(mp3_files)} tracks in {STAGING_DIR}\n")

    results = []
    for i, filename in enumerate(mp3_files, 1):
        filepath = os.path.join(STAGING_DIR, filename)
        raw_rms, bpm = analyze_track(filepath)
        if raw_rms is None:
            continue
        results.append({"filename": filename, "raw_rms": raw_rms, "bpm": bpm})
        print(f"[{i}/{len(mp3_files)}] {filename}  →  bpm={bpm}")

    if not results:
        print("No tracks could be analyzed.")
        return

    raw_values = [r["raw_rms"] for r in results]
    normalized = normalize_energy(raw_values)

    for r, energy in zip(results, normalized):
        r["energy"] = energy

    results.sort(key=lambda r: r["energy"], reverse=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "energy", "bpm"])
        writer.writeheader()
        for r in results:
            writer.writerow({"filename": r["filename"], "energy": r["energy"], "bpm": r["bpm"]})

    print(f"\nDone. Results written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
