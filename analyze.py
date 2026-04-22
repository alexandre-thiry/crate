#!/usr/bin/env python3
"""
Crate — analyze.py
Scans ~/Desktop/Music/_staging/ for MP3s, computes a composite energy score
(0–100) from RMS loudness, spectral brightness, and percussive content, then
writes analysis.csv to the project root sorted by energy descending.

analysis.csv doubles as a cache: raw values for already-analyzed tracks are
loaded at startup so only new tracks need to be processed.
"""

import csv
import os

import librosa
import numpy as np

# --- Paths ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STAGING_DIR = os.path.expanduser("~/Desktop/Music/_staging/")
OUTPUT_CSV  = os.path.join(PROJECT_DIR, "analysis.csv")

# --- Energy formula weights ---
W_RMS        = 0.4   # raw loudness
W_CENTROID   = 0.3   # spectral brightness (high = brighter/harsher)
W_PERCUSSIVE = 0.3   # percussive vs harmonic content ratio

# --- CSV columns ---
FIELDNAMES = ["filename", "energy", "raw_rms", "raw_centroid", "raw_percussive"]


def normalize_energy(raw_values):
    """
    Normalize a list of raw floats to 0–100 relative to the maximum.
    Returns a list of floats in the same order as the input.
    """
    if not raw_values:
        return []
    max_val = max(raw_values)
    if max_val == 0:
        return [0.0] * len(raw_values)
    return [round((v / max_val) * 100, 1) for v in raw_values]


def load_cache():
    """
    Load raw values from an existing analysis.csv.
    Returns a dict of {filename: {raw_rms, raw_centroid, raw_percussive}}.
    """
    cache = {}
    if not os.path.exists(OUTPUT_CSV):
        return cache
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cache[row["filename"]] = {
                    "raw_rms":        float(row["raw_rms"]),
                    "raw_centroid":   float(row["raw_centroid"]),
                    "raw_percussive": float(row["raw_percussive"]),
                }
            except (KeyError, ValueError):
                # Old CSV format without raw columns — skip, will re-analyze
                pass
    return cache


def analyze_track(filepath):
    """
    Load an audio file and return (rms, centroid, percussive_ratio).
    - rms: mean RMS energy (raw float)
    - centroid: mean spectral centroid in Hz
    - percussive_ratio: mean RMS of percussive layer / mean RMS of full signal
    Returns (None, None, None) on error.
    """
    try:
        y, sr = librosa.load(filepath, mono=True)
        rms = float(np.mean(librosa.feature.rms(y=y)))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        _, y_percussive = librosa.effects.hpss(y)
        percussive_ratio = float(np.mean(librosa.feature.rms(y=y_percussive))) / (rms + 1e-6)
        return rms, centroid, percussive_ratio
    except Exception as e:
        print(f"  WARNING: could not analyze {os.path.basename(filepath)}: {e}")
        return None, None, None


def main():
    mp3_files = sorted([
        f for f in os.listdir(STAGING_DIR)
        if f.lower().endswith(".mp3") or f.lower().endswith(".wav")
    ])

    if not mp3_files:
        print("No MP3 files found in _staging/. Nothing to analyze.")
        return

    cache = load_cache()
    new_files = [f for f in mp3_files if f not in cache]

    print(f"Found {len(mp3_files)} tracks — {len(cache)} cached, {len(new_files)} new\n")

    # Analyze only new tracks
    for i, filename in enumerate(new_files, 1):
        filepath = os.path.join(STAGING_DIR, filename)
        print(f"[{i}/{len(new_files)}] {filename}")
        rms, centroid, percussive_ratio = analyze_track(filepath)
        if rms is None:
            continue
        cache[filename] = {
            "raw_rms":        rms,
            "raw_centroid":   centroid,
            "raw_percussive": percussive_ratio,
        }

    # Only keep entries for files still in _staging/ (handles deleted tracks)
    active = {f: cache[f] for f in mp3_files if f in cache}

    if not active:
        print("No tracks could be analyzed.")
        return

    # Renormalize everything together so scores are always relative to the full library
    filenames       = list(active.keys())
    norm_rms        = normalize_energy([active[f]["raw_rms"]        for f in filenames])
    norm_centroid   = normalize_energy([active[f]["raw_centroid"]   for f in filenames])
    norm_percussive = normalize_energy([active[f]["raw_percussive"] for f in filenames])

    results = []
    for f, n_rms, n_cent, n_perc in zip(filenames, norm_rms, norm_centroid, norm_percussive):
        energy = round(W_RMS * n_rms + W_CENTROID * n_cent + W_PERCUSSIVE * n_perc, 1)
        results.append({
            "filename":       f,
            "energy":         energy,
            "raw_rms":        active[f]["raw_rms"],
            "raw_centroid":   active[f]["raw_centroid"],
            "raw_percussive": active[f]["raw_percussive"],
        })

    results.sort(key=lambda r: r["energy"], reverse=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print(f"\nDone. {len(results)} tracks in {OUTPUT_CSV}")
    if new_files:
        print(f"  {len([f for f in new_files if f in active])} new tracks analyzed and added to cache.")


if __name__ == "__main__":
    main()
