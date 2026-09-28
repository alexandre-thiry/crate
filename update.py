#!/usr/bin/env python3
"""
Crate — update.py
Checks the dependencies in requirements.txt against the latest versions on PyPI.

  - yt-dlp is upgraded automatically (it breaks every few months as YouTube and
    SoundCloud change), then smoke-tested. If the test fails you're asked whether
    to roll back.
  - Every other package is shown and you're asked before upgrading it.
  - requirements.txt is rewritten to match whatever got installed.

Usage:
  venv/bin/python update.py
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from importlib import metadata

PROJECT_DIR  = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(PROJECT_DIR, "requirements.txt")
COOKIES_FILE = os.path.join(PROJECT_DIR, "soundcloud.cookies")

PYPI_TIMEOUT = 5  # seconds

# Smoke test targets. Must be real music: a stale yt-dlp still handles non-music
# YouTube videos and flat SC searches fine, but fails on these with 403/404.
SMOKE_SC_QUERY = "scsearch1:Fisher Losing It"
SMOKE_YT_QUERY = "ytsearch1:Daft Punk One More Time official video"

PACKAGE_NOTES = {
    "librosa": "may shift energy scores vs. the ones cached in analysis.csv",
}


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

def version_tuple(version):
    parts = []
    for part in version.split("."):
        digits = "".join(c for c in part if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest, current):
    return version_tuple(latest) > version_tuple(current)


def parse_requirements(text):
    """Return [(package, pinned_version)] for every 'pkg==ver' line."""
    reqs = []
    for line in text.splitlines():
        line = line.strip()
        if "==" in line and not line.startswith("#"):
            name, ver = line.split("==", 1)
            reqs.append((name.strip(), ver.strip()))
    return reqs


def update_pins(text, new_versions):
    """Rewrite 'pkg==ver' lines for packages in new_versions, leave the rest untouched."""
    lines = []
    for line in text.splitlines(keepends=True):
        name = line.split("==", 1)[0].strip()
        if "==" in line and name in new_versions:
            ending = "\n" if line.endswith("\n") else ""
            line = f"{name}=={new_versions[name]}{ending}"
        lines.append(line)
    return "".join(lines)


def installed_version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def latest_version(package):
    """Latest version on PyPI, or None if PyPI can't be reached."""
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        with urllib.request.urlopen(url, timeout=PYPI_TIMEOUT) as resp:
            return json.load(resp)["info"]["version"]
    except Exception:
        return None


def pip_install(package, version):
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
         f"{package}=={version}"]
    )
    return result.returncode == 0


def save_pins(new_versions):
    if not new_versions:
        return
    with open(REQUIREMENTS, "r", encoding="utf-8") as f:
        text = f.read()
    with open(REQUIREMENTS, "w", encoding="utf-8") as f:
        f.write(update_pins(text, new_versions))
    print("requirements.txt updated.")


def ask(question):
    try:
        return input(f"{question} [y/n]: ").strip().lower() == "y"
    except EOFError:
        print()
        return False


# ---------------------------------------------------------------------------
# yt-dlp
# ---------------------------------------------------------------------------

def smoke_test_ytdlp():
    """
    Runs yt-dlp in a subprocess so the freshly installed version is used.
    Returns a list of failure messages (empty = all good).
    """
    failures = []
    ytdlp = [sys.executable, "-m", "yt_dlp", "--quiet", "--no-warnings"]

    print("  Smoke test: SoundCloud search...", end=" ", flush=True)
    cookies = ["--cookies", COOKIES_FILE] if os.path.exists(COOKIES_FILE) else []
    # Full metadata resolve (not --flat-playlist) — that's where a stale yt-dlp 404s.
    # DRM-protected results have no formats, which is fine here.
    cmd = ytdlp + cookies + ["--skip-download", "--ignore-no-formats-error",
                             "--print", "id", SMOKE_SC_QUERY]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        ok = result.returncode == 0 and result.stdout.strip()
        error = result.stderr.strip().splitlines()[-1:] if not ok else []
    except subprocess.TimeoutExpired:
        ok, error = False, ["timed out"]
    print("✓" if ok else "✗")
    if not ok:
        failures.append(f"SoundCloud search failed: {' '.join(error) or 'no results'}")

    print("  Smoke test: YouTube download...", end=" ", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ytdlp + ["-f", "bestaudio",
                       "-o", os.path.join(tmp, "%(id)s.%(ext)s"), SMOKE_YT_QUERY]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            ok = result.returncode == 0 and any(
                not f.endswith(".part") for f in os.listdir(tmp))
            error = result.stderr.strip().splitlines()[-1:] if not ok else []
        except subprocess.TimeoutExpired:
            ok, error = False, ["timed out"]
    print("✓" if ok else "✗")
    if not ok:
        failures.append(f"YouTube download failed: {' '.join(error) or 'no file'}")

    return failures


def upgrade_ytdlp(current, latest):
    """
    Upgrade yt-dlp, smoke test it, and offer a rollback if the test fails.
    Returns the version left installed.
    """
    print(f"\nUpgrading yt-dlp {current} → {latest}...")
    if not pip_install("yt-dlp", latest):
        print("  ERROR: pip install failed — yt-dlp unchanged.")
        return current

    failures = smoke_test_ytdlp()
    if failures:
        # YouTube occasionally 403s a single request even on a working version
        print("  Retrying smoke test once...")
        failures = smoke_test_ytdlp()
    if not failures:
        print(f"  yt-dlp {latest} is working.")
        return latest

    for failure in failures:
        print(f"  {failure}")
    print("  (This can also be SoundCloud rate limiting or a network issue, not the upgrade.)")
    if ask(f"  Roll back to yt-dlp {current}?"):
        if pip_install("yt-dlp", current):
            print(f"  Rolled back to {current}.")
            return current
        print("  ERROR: rollback failed.")
    return latest


def prompt_ytdlp_update():
    """
    Used by run.py before syncing. Offers to update yt-dlp if a newer version exists.
    Stays silent when up to date or when PyPI can't be reached.
    """
    current = installed_version("yt-dlp")
    latest = latest_version("yt-dlp")
    if not current or not latest or not is_newer(latest, current):
        return
    print(f"⚠ yt-dlp {current} → {latest} available. "
          f"Outdated versions often cause 403/404 errors during sync.")
    if ask("Update yt-dlp now before syncing?"):
        installed = upgrade_ytdlp(current, latest)
        if installed != current:
            save_pins({"yt-dlp": installed})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with open(REQUIREMENTS, "r", encoding="utf-8") as f:
        reqs = parse_requirements(f.read())

    print("Checking PyPI for updates...\n")
    outdated = []
    unreachable = 0
    for package, _ in reqs:
        current = installed_version(package)
        latest = latest_version(package)
        if latest is None:
            unreachable += 1
            print(f"  {package:15} {current or 'not installed':12} (couldn't reach PyPI)")
            continue
        if current and is_newer(latest, current):
            outdated.append((package, current, latest))
            print(f"  {package:15} {current:12} → {latest}")
        else:
            print(f"  {package:15} {current or 'not installed':12} up to date")

    if unreachable == len(reqs):
        print("\nCouldn't reach PyPI — are you offline?")
        return
    if not outdated:
        print("\nEverything is up to date.")
        return

    new_versions = {}
    outdated.sort(key=lambda row: row[0] != "yt-dlp")  # yt-dlp first
    for package, current, latest in outdated:
        if package == "yt-dlp":
            installed = upgrade_ytdlp(current, latest)
        else:
            note = PACKAGE_NOTES.get(package)
            print()
            if note:
                print(f"  Note: {package} update {note}.")
            if not ask(f"Update {package} {current} → {latest}?"):
                continue
            installed = latest if pip_install(package, latest) else current
            if installed == current:
                print(f"  ERROR: pip install failed — {package} unchanged.")
        if installed != current:
            new_versions[package] = installed

    print()
    save_pins(new_versions)
    print("Done.")


if __name__ == "__main__":
    main()
