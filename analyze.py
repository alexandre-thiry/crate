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
