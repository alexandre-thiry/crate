# Crate

Automatically sync and download your Spotify and SoundCloud playlists as high-quality MP3s, tagged and ready to import into rekordbox.

---

## What It Does

Crate pulls your master playlist from both Spotify and SoundCloud, merges them into one deduplicated list, and downloads every track you don't already have — in the best quality available. Files land in a staging folder named and tagged correctly, ready for rekordbox.

**Full pipeline:**
1. Fetch all tracks from your Spotify playlist (artist, title, duration)
2. Fetch all tracks from your SoundCloud playlist (artist, title, duration)
3. Merge both lists and remove duplicates using fuzzy matching
4. For each track not already downloaded, attempt download in priority order:
   - Exact search on SoundCloud (Go+ quality, 256kbps AAC source)
   - Fuzzy search on SoundCloud
   - Exact search on YouTube (fallback)
   - Fuzzy search on YouTube (last resort)
5. Verify each search result actually matches the intended track before downloading
6. Save as 320kbps MP3 to `~/Desktop/Music/_staging/`
7. Write ID3 tags (artist, title) and embed cover art
8. Log everything — what downloaded, from where, what failed

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
pip install spotipy yt-dlp thefuzz mutagen python-dotenv
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

You need to be logged in to SoundCloud Go+ in your browser, then export your cookies to a file named `soundcloud.cookies` in the project root. The recommended way is the [cookies.txt](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) browser extension — export for `soundcloud.com` in Netscape format.

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

## Usage

```bash
source venv/bin/activate
python3 sync.py
```

That's it. Run it whenever you want to sync new tracks. Already-downloaded tracks are skipped automatically.

**Example output:**
```
Fetching Spotify tracks...
  total tracks reported by Spotify: 312
  312 tracks found
Fetching SoundCloud tracks...
  248 track URLs found, resolving metadata...
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

---

## Output Files

| File | What's in it |
|------|-------------|
| `~/Desktop/Music/_staging/` | Downloaded MP3s, named `Track Name - Artist.mp3` |
| `archive.txt` | Every successfully downloaded track (used to skip on next run) |
| `sources.txt` | Source of each download — `Artist - Title — SC` or `— YT` |
| `failed.txt` | Tracks that couldn't be found — `Artist - Title — reason` |

**File naming:** `Track Name - Artist.mp3`
Example: `Crowd Control - Fisher.mp3`

**ID3 tags written:** Title, Artist — readable by rekordbox on import.

To check which tracks came from YouTube:
```bash
grep " — YT" sources.txt
```

To check quality of your downloaded files (requires ffmpeg):
```bash
for f in ~/Desktop/Music/_staging/*.mp3; do
  bitrate=$(ffprobe -v quiet -show_entries format=bit_rate \
    -of default=noprint_wrappers=1:nokey=1 "$f")
  printf "%4d kbps  %s\n" "$((bitrate / 1000))" "$(basename "$f")"
done | sort -n
```

---

## How Verification Works

Crate doesn't blindly download the first search result. Before accepting any result, it checks whether it actually matches the track you asked for.

**Two ways a result can pass:**

1. **Title match** — fuzzy similarity between the search query and the returned title is ≥ 85%. Noise like `(Extended Mix)`, `feat. Someone`, and collab notation (`x ArtistName`) is stripped before comparing.

2. **Duration rescue** — if the title score is between 60–84% but the returned track's duration is within ±8 seconds of the expected duration (from Spotify/SoundCloud metadata), it passes anyway. This handles tracks where the title is formatted differently but the song is the same.

If neither condition is met, that strategy is rejected and the next one is tried.

---

## How Deduplication Works

Both Spotify and SoundCloud playlists are fetched separately. Before downloading, they are merged:

- SoundCloud tracks form the base list (preferred — Go+ quality)
- Each Spotify track is compared against the merged list using `fuzz.ratio`
- If similarity ≥ 90%, it's treated as the same track and skipped
- If no match, it's added to the list

This means if you have a track in both playlists, Crate keeps the SoundCloud version.

---

## SoundCloud Rate Limiting

SoundCloud throttles bulk requests. Crate handles this automatically:

- **3 second delay** between each track download (default)
- **Adaptive delay** — if SoundCloud returns a 429 (Too Many Requests) at any point during a run, the delay automatically increases to 10 seconds for all remaining tracks
- **Exponential backoff** on individual 429s — waits 10s, then 30s, then 60s before giving up on SoundCloud and falling back to YouTube

If you're consistently seeing many YouTube fallbacks on long runs, increase `TRACK_DELAY` at the top of `sync.py`.

---

## Configuration

All tunable constants are at the top of `sync.py`:

```python
# Matching
DEDUP_THRESHOLD    = 90   # % similarity to treat two tracks as duplicates
VERIFY_THRESHOLD   = 85   # min score to accept a search result on title alone
DURATION_THRESHOLD = 60   # min score when duration match rescues a result
DURATION_TOLERANCE = 8    # seconds — how close durations must be for a rescue

# Rate limiting
TRACK_DELAY           = 3    # seconds between tracks (normal)
TRACK_DELAY_AFTER_429 = 10   # seconds between tracks after a 429 is hit
SC_RETRY_WAITS        = [10, 30, 60]  # backoff sequence on SC 429s
```

---

## Idempotency

Crate is safe to run repeatedly. Every successfully downloaded track is appended to `archive.txt`. On the next run, the full playlist is re-fetched but anything in the archive is skipped. Only new tracks are downloaded.

Failed tracks are logged to `failed.txt` but are retried on the next run (they are not in the archive). If a previously failed track succeeds, it is moved from `failed.txt` to `archive.txt` automatically.

---

## Project Structure

```
crate/
├── sync.py              # Main script — run this
├── .env                 # Credentials (never committed)
├── soundcloud.cookies   # SC session cookies (never committed)
├── archive.txt          # Downloaded track log (never committed)
├── failed.txt           # Failed track log (never committed)
├── sources.txt          # SC/YT source log (never committed)
├── venv/                # Python virtual environment
└── README.md
```

---

## After Downloading — Genre Sorting

Once tracks are in `_staging/`, a separate Claude Code session can sort them into genre folders automatically:

- Reads `~/Desktop/Music/_staging/`
- Classifies each track by genre based on artist and title knowledge
- Creates genre subfolders dynamically (Tech House, Afro House, Melodic House, etc.)
- Moves tracks into the correct folder
- Anything uncertain goes to `~/Desktop/Music/Unsorted/` for manual review

This is a separate interactive step — not part of `sync.py`.

---

## License

Personal use. Not affiliated with Spotify or SoundCloud.
