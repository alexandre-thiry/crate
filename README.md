# Crate

Automatically sync and download your Spotify and SoundCloud playlists as high-quality MP3s, tagged and ready to import into rekordbox. Includes an energy analysis tool to help sort tracks into DJ playlists.

---

## What It Does

Crate is two tools in one:

**`sync.py` — Download your music**
Pulls your master playlists from Spotify and SoundCloud, merges them into one deduplicated list, and downloads every track you don't already have — in the best quality available. Files land in a staging folder, named and tagged correctly, ready for rekordbox.

**`analyze.py` — Score your tracks by energy**
Scans your staging folder and gives every track a composite energy score (0–100) based on three audio characteristics: loudness, brightness, and how percussive it sounds. Outputs a CSV you can use to sort tracks into warm-up, peak, and closing playlists.

---

## Requirements

- Python 3.x
- [ffmpeg](https://ffmpeg.org/download.html) installed and available in your PATH
- A [Spotify Developer App](https://developer.spotify.com/dashboard) (free)
- A SoundCloud Go+ subscription (for high-quality downloads)
- Your SoundCloud session cookies exported to a file

---

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/alexandre-thiry/crate.git
cd crate
```

**2. Create and activate a virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Create your `.env` file**

Create a file named `.env` in the project root:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
SPOTIFY_PLAYLIST_ID=your_playlist_id_here
SOUNDCLOUD_PLAYLIST_URL=https://soundcloud.com/yourprofile/sets/your-playlist
```

**5. Export your SoundCloud cookies**

You need to be logged in to SoundCloud Go+ in your browser, then export your cookies to a file named `soundcloud.cookies` in the project root. The recommended way is the [Get cookies.txt Locally](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) Chrome extension — export for `soundcloud.com` in Netscape format.

**6. Create your output folders**
```bash
mkdir -p ~/Desktop/Music/_staging
mkdir -p ~/Desktop/Music/Unsorted
```

---

## Spotify Setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Add `http://127.0.0.1:8888/callback` as a Redirect URI in the app settings
4. Copy your Client ID and Client Secret into `.env`
5. Find your playlist ID: open the playlist in Spotify, click Share → Copy link. The ID is the string after `/playlist/` and before `?`

On first run, a browser window will open asking you to authorize the app. After that, credentials are cached automatically.

---

## Syncing Your Music

```bash
source venv/bin/activate
python3 sync.py
```

Run this whenever you want to sync new tracks. Already-downloaded tracks are skipped automatically — it's safe to run as many times as you want.

**Example output:**
```
Fetching Spotify tracks...
  312 tracks found
Fetching SoundCloud tracks...
  248 tracks found
Merging and deduplicating...
  423 unique tracks total
  398 already in archive, 25 to download

[1/25] Fisher - Crowd Control
  → exact SC... ✓
[2/25] Prospa - Don't Stop
  → exact SC... ✓
[3/25] Riordan - Strong Rhyme
  → exact SC... ✗
  → fuzzy SC... ✓
...

Done. 24 downloaded (21 from SC, 3 from YT), 398 skipped, 1 failed.
```

### How downloads work

For every track, Crate tries four strategies in order and stops at the first success:

1. **Exact search on SoundCloud** — best quality (256kbps AAC via SC Go+, encoded to 320kbps MP3)
2. **Fuzzy search on SoundCloud** — if the exact title isn't found
3. **Exact search on YouTube** — fallback
4. **Fuzzy search on YouTube** — last resort

Before accepting any result, Crate verifies it actually matches the track you asked for — see [Verification](#how-verification-works) below.

### Output files

| File | What's in it |
|------|-------------|
| `~/Desktop/Music/_staging/` | Downloaded MP3s, named `Track Name - Artist.mp3` |
| `archive.txt` | Every successfully downloaded track (used to skip on next run) |
| `failed.txt` | Tracks that couldn't be found — `Artist - Title — reason` |

**File naming:** `Track Name - Artist.mp3`
Example: `Crowd Control - Fisher.mp3`

**ID3 tags written:** Title and Artist — readable by rekordbox on import. Cover art is embedded automatically.

---

## Analyzing Track Energy

Once your tracks are in `_staging/`, you can score them all by energy:

```bash
source venv/bin/activate
python3 analyze.py
```

This scans every MP3 in `_staging/`, analyzes each one, and writes `analysis.csv` to the project root. The CSV is sorted by energy score descending — highest energy tracks at the top.

**Example output:**
```
Analyzing 368 tracks in /Users/you/Desktop/Music/_staging/

[1/368] Crowd Control - Fisher.mp3
[2/368] Don't Stop - Prospa.mp3
...

Done. Results written to /Users/you/Desktop/Programming/Projects/crate/analysis.csv
```

### What the energy score measures

Each track gets a score from 0 to 100 based on three things:

| Component | Weight | What it captures |
|-----------|--------|-----------------|
| RMS loudness | 40% | How loud the track is on average — louder = more energy |
| Spectral brightness | 30% | How bright or dark the sound is — bright, cutting tracks score higher than deep, warm ones |
| Percussive content | 30% | How much of the track is drums/percussion vs. pads and chords — more percussion = more energy |

All three are computed locally using [librosa](https://librosa.org/) — no internet connection required, no API calls. Analysis on a full library of 300+ tracks takes roughly 15–30 minutes depending on your machine.

**Important:** scores are relative to the batch you analyze. The loudest/most energetic track in your set anchors at the top and everything else is ranked below it. To compare tracks across different folders, run them all together in one batch.

### Using the CSV

Open `analysis.csv` in Excel, Numbers, or any spreadsheet app. You'll see two columns: filename and energy score. Use it as a starting point to sort tracks into playlists — the scores give you a data-driven first pass, but trust your ears for the final call.

Suggested thresholds (adjust based on your library):

| Playlist | Energy range |
|----------|-------------|
| Peak hour | 75+ |
| Warm up / build | 55–74 |
| Closing / cool down | below 55 |

---

## How Verification Works

Crate doesn't blindly download the first search result. Before accepting any result, it checks whether it actually matches the track you asked for.

**A result passes if either condition is met:**

1. **Title match** — fuzzy similarity between the search query and the returned title is ≥ 85%. Noise like `(Extended Mix)`, `feat. Someone`, and collab notation (`x ArtistName`) is stripped before comparing.

2. **Duration rescue** — if the title score is between 60–84% but the returned track's duration is within ±8 seconds of the expected duration (from Spotify/SoundCloud metadata), it passes anyway. This handles tracks where the title is formatted differently but the song is the same.

If neither condition is met, that strategy is rejected and the next one is tried.

---

## How Deduplication Works

Both Spotify and SoundCloud playlists are fetched separately. Before downloading, they are merged:

- SoundCloud tracks form the base list (preferred — Go+ quality)
- Each Spotify track is compared against the merged list using fuzzy matching
- If similarity ≥ 90%, it's treated as the same track and skipped
- If no match found, it's added to the download list

This means if you have a track in both playlists, Crate downloads the SoundCloud version.

---

## SoundCloud Rate Limiting

SoundCloud throttles bulk requests. Crate handles this automatically:

- **3 second delay** between each track download by default
- **Adaptive delay** — if SoundCloud returns a rate limit error at any point, the delay automatically increases to 10 seconds for all remaining tracks
- **Automatic retry** — on a rate limit error, Crate waits 10s, then 30s, then 60s before giving up on SoundCloud and falling back to YouTube

If you're consistently seeing many YouTube fallbacks on long runs, increase `TRACK_DELAY` at the top of `sync.py`.

---

## Configuration

All tunable settings are at the top of `sync.py`:

```python
# Matching
DEDUP_THRESHOLD    = 90   # % similarity to treat two tracks as duplicates
VERIFY_THRESHOLD   = 85   # min score to accept a search result by title alone
DURATION_THRESHOLD = 60   # min title score when duration can rescue a result
DURATION_TOLERANCE = 8    # seconds — how close durations must be for a rescue

# Rate limiting
TRACK_DELAY           = 3    # seconds between tracks (normal)
TRACK_DELAY_AFTER_429 = 10   # seconds between tracks after a rate limit is hit
SC_RETRY_WAITS        = [10, 30, 60]  # backoff sequence on rate limit errors
```

---

## Project Structure

```
crate/
├── sync.py              # Download script — run this to sync music
├── analyze.py           # Energy analysis — run this to score your tracks
├── requirements.txt     # Python dependencies
├── tests/
│   └── test_analyze.py  # Unit tests for analyze.py
├── .env                 # Credentials (never committed)
├── soundcloud.cookies   # SC session cookies (never committed)
├── archive.txt          # Downloaded track log (never committed)
├── failed.txt           # Failed track log (never committed)
├── venv/                # Python virtual environment
└── README.md
```

---

## License

Personal use. Not affiliated with Spotify or SoundCloud.
