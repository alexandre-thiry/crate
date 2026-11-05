import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from sync import pick_candidates, relaxed_candidates, title_score, DURATION_TOLERANCE, RELAXED_TOLERANCE


def cand(title, uploader="", duration=None, source="yt", url=None):
    return {"title": title, "uploader": uploader, "duration": duration, "source": source,
            "url": url or f"https://example.com/{title}"}


# (artist, title, expected length from Spotify, length of the music video Crate downloaded)
MUSIC_VIDEO_CASES = [
    ("Maroon 5", "Payphone", 231, 279),
    ("David Guetta", "Play Hard", 201, 242),
    ("Timbaland", "The Way I Are", 179, 212),
    ("Avicii", "Wake Me Up", 247, 272),
    ("USHER", "DJ Got Us Fallin' In Love", 221, 246),
    ("Pitbull", "International Love", 227, 248),
    ("Sean Paul", "She Doesn't Mind", 228, 246),
    ("Avicii", "The Nights", 177, 191),
    ("Britney Spears", "Gimme More", 251, 241),
    ("Flo Rida", "Whistle", 225, 234),
    ("Far East Movement", "Like A G6", 217, 225),
    ("Rihanna", "We Found Love", 215, 276),
    ("Rihanna", "Don't Stop The Music", 267, 233),
    ("Icona Pop", "I Love It", 157, 180),
    ("Rihanna", "Only Girl (In The World)", 236, 252),
    ("Katy Perry", "Dark Horse", 216, 225),
    ("LMFAO", "Sorry For Party Rocking", 206, 439),
    ("LMFAO", "Party Rock Anthem", 262, 376),
    ("Drake", "Nonstop", 238, 316),
    ("Drake", "Laugh Now Cry Later", 261, 301),
]


@pytest.mark.parametrize("artist,title,expected,video_length", MUSIC_VIDEO_CASES)
def test_official_audio_beats_music_video(artist, title, expected, video_length):
    video = cand(f"{artist} - {title} (Official Music Video)", artist, video_length)
    audio = cand(title, f"{artist} - Topic", expected, source="ytmusic")
    passing, rejected = pick_candidates([video, audio], f"{artist} - {title}", expected)
    assert passing == [audio]
    assert [c for c, _ in rejected] == [video]
    assert "music video" in rejected[0][1]


@pytest.mark.parametrize("track,expected,short", [
    ("Pitbull - Give Me Everything (feat. Nayer)", 252,
     cand("Pitbull - Give Me Everything Feat Nayer Live HP Pavilion San Jose", "Pitbull", 44)),
    ("JAŸ-Z - Ni**as In Paris", 219, cand("JAŸ-Z - Ni**as In Paris (ft. Kanye West)", "JAŸ-Z", 74)),
    ("Kungs - This Girl (Kungs Vs. Cookin' On 3 Burners)", 196,
     cand("Kungs Vs. Cookin' On 3 Burners - This Girl", "Kungs", 94.5, source="sc")),
])
def test_short_sources_rejected(track, expected, short):
    passing, rejected = pick_candidates([short], track, expected)
    assert passing == []
    assert "length" in rejected[0][1]


def test_length_within_tolerance_passes():
    c = cand("Payphone", "Maroon 5 - Topic", 231 + DURATION_TOLERANCE, source="ytmusic")
    passing, _ = pick_candidates([c], "Maroon 5 - Payphone", 231)
    assert passing == [c]


def test_same_artist_wrong_song_rejected_even_with_matching_length():
    wrong = cand("The Days", "Avicii - Topic", 177, source="ytmusic")
    passing, rejected = pick_candidates([wrong], "Avicii - The Nights", 177)
    assert passing == []
    assert "title" in rejected[0][1]


def test_remix_of_original_rejected_by_title():
    remix = cand("Te Bote Remix", "Casper Magico", 276)
    passing, _ = pick_candidates([remix], "Darell - Te Boté", 276)
    assert passing == []


def test_music_video_rejected_even_at_exact_length():
    video = cand("Pitbull - Timber (Official Video)", "Pitbull", 204)
    lyrics = cand("Pitbull - Timber (Lyrics) ft. Ke$ha", "7clouds", 203)
    passing, rejected = pick_candidates([video, lyrics], "Pitbull - Timber", 204)
    assert passing == [lyrics]
    assert rejected[0][1] == "music video"


def test_topic_preferred_over_lyric_video():
    lyrics = cand("Calvin Harris & Disciples - How Deep Is Your Love (Lyrics)", "Dan Music", 212)
    topic = cand("How Deep Is Your Love", "Calvin Harris - Topic", 213)
    passing, _ = pick_candidates([lyrics, topic], "Calvin Harris - How Deep Is Your Love", 212)
    assert passing[0] is topic


def test_official_audio_preferred_over_lyric_video():
    lyrics = cand("Calvin Harris & Disciples - How Deep Is Your Love (Lyrics)", "Dan Music", 212)
    audio = cand("Calvin Harris & Disciples - How Deep Is Your Love (Audio)", "Calvin Harris", 213)
    passing, _ = pick_candidates([lyrics, audio], "Calvin Harris - How Deep Is Your Love", 212)
    assert passing[0] is audio


def test_remix_not_penalized_when_track_is_a_remix():
    remix = cand("Joys (SOSA Extended Remix)", "Roberto Surace", 300)
    other = cand("Roberto Surace - Joys (SOSA Extended Remix) (Lyrics)", "lyricsguy", 300)
    passing, _ = pick_candidates([other, remix], "Roberto Surace - Joys (SOSA Extended Remix)", 300)
    assert passing[0] is other  # no penalty for either, so original order wins


def test_live_in_song_title_not_penalized():
    c1 = cand("T.I. - Live Your Life (Lyrics)", "lyrics", 200)
    c2 = cand("Live Your Life", "T.I.", 201)
    passing, _ = pick_candidates([c1, c2], "T.I. - Live Your Life", 200)
    assert passing[0] is c1


def test_unknown_expected_length_falls_back_to_strict_title_match():
    good = cand("Maroon 5 - Payphone", "Maroon 5", 279)
    passing, _ = pick_candidates([good], "Maroon 5 - Payphone", None)
    assert passing == [good]


def test_unknown_candidate_length_rejected_when_expected_known():
    c = cand("Payphone", "Maroon 5", None)
    passing, rejected = pick_candidates([c], "Maroon 5 - Payphone", 231)
    assert passing == []
    assert "length" in rejected[0][1]


@pytest.mark.parametrize("track,returned", [
    ("Booba - Dolce Camara - Snight B Remix", "Booba - Dolce Camara (Snight B Remix)"),
    ("Florence Eve 🎶 - Sidney Charles - This jam is fresh", "Sidney Charles - This Jam Is Fresh"),
    ("Macklemore - Can't Hold Us (feat. Ray Dalton)", "Can't Hold Us - Macklemore & Ryan Lewis (feat. Ray Dalton)"),
    ("Maroon 5 - Payphone", "Payphone - Maroon 5"),
])
def test_title_score_matches_real_variants(track, returned):
    assert title_score(track, returned) >= 80


@pytest.mark.parametrize("title,uploader", [
    ("One Kiss (Tribute to Calvin Harris & Dua Lipa)", "Grant Richards - Topic"),
    ("Pompeii (By Bastille)", "Release - Topic"),
    ("Safe and Sound (Capital Cities Tribute)", "Brickbreaker - Topic"),
    ("Blame (8D Audio)", "Luke Muzzic"),
    ("monaco (sped up) - guy2bezbar", "Frenchy Bandana"),
    ("La Rvfleuze - Serrure #5 (SLOWED)", "QUADRABZEZ"),
    ("Payphone (Karaoke Version)", "Sing King"),
    ("Payphone (Cover)", "Some Singer"),
    ("Payphone - Maroon 5 cover by Jane", "Jane"),
    ("Payphone (Originally Performed by Maroon 5)", "Hit Factory"),
    ("Hello (128 BPM Instrumental Tribute To Martin Solveig feat Dragonette)", "Remix Kit - Topic"),
    ("Midnight City (Nightcore)", "nc"),
])
def test_copies_and_altered_versions_rejected(title, uploader):
    track = {
        "One Kiss": "Calvin Harris - One Kiss (with Dua Lipa)", "Pompeii": "Bastille - Pompeii",
        "Safe and Sound": "Capital Cities - Safe And Sound", "Blame": "Calvin Harris - Blame",
        "monaco": "Guy2Bezbar - Monaco", "La Rvfleuze": "La Rvfleuze - Serrure #5",
        "Payphone": "Maroon 5 - Payphone", "Hello": "Martin Solveig - Hello",
        "Midnight City": "M83 - Midnight City",
    }[next(k for k in ["One Kiss", "Pompeii", "Safe and Sound", "Blame", "monaco", "La Rvfleuze",
                       "Payphone", "Hello", "Midnight City"] if title.startswith(k))]
    c = cand(title, uploader, 200)
    passing, rejected = pick_candidates([c], track, 200)
    assert passing == []
    assert "copy/altered" in rejected[0][1]


def test_altered_version_allowed_when_requested():
    c = cand("MONEY ON THE DASH (SPED UP)", "Elley Duhé", 116)
    passing, _ = pick_candidates([c], "Elley Duhé - MONEY ON THE DASH - SPED UP", 116)
    assert passing == [c]


def test_cover_in_song_title_not_rejected():
    c = cand("Cover Me", "Bruce Springsteen - Topic", 207, source="ytmusic")
    passing, _ = pick_candidates([c], "Bruce Springsteen - Cover Me", 207)
    assert passing == [c]


def test_relaxed_tolerance_accepts_real_track_a_few_seconds_off():
    real = cand("One Kiss", "Calvin Harris", 215, source="ytmusic")
    assert pick_candidates([real], "Calvin Harris - One Kiss (with Dua Lipa)", 209)[0] == []
    assert relaxed_candidates([real], "Calvin Harris - One Kiss (with Dua Lipa)", 209) == [real]


def test_relaxed_skips_penalized_and_far_off_candidates():
    video = cand("Calvin Harris, Dua Lipa - One Kiss (Official Video)", "Calvin Harris", 215)
    far = cand("One Kiss", "Calvin Harris", 209 + RELAXED_TOLERANCE + 1, source="ytmusic")
    assert relaxed_candidates([video, far], "Calvin Harris - One Kiss (with Dua Lipa)", 209) == []


@pytest.mark.parametrize("track,returned", [
    ("La Rvfleuze - Serrure #5", "Serrure #667"),
    ("La Rvfleuze - Serrure #5", "La Rvfleuze - Serrure #667 feat. Freeze Corleone"),
    ("13 Organisé - Bande Organisée", "Bande Organisée 2 - SCH / Kofs / JuL"),
    ("Gazo - Drill FR 4", "Drill FR 3"),
    ("Gazo - Drill FR 4", "Drill FR"),
])
def test_title_score_different_numbers_are_different_songs(track, returned):
    assert title_score(track, returned) < 80


@pytest.mark.parametrize("track,returned", [
    ("La Rvfleuze - Serrure #5", "La Rvfleuze - Serrure 5 (Audio Officiel)"),
    ("Gazo - Drill FR 4", "Drill FR 4"),
    ("MK - 17", "17"),
    ("Maroon 5 - Payphone", "Payphone"),
    ("Bizarrap - Quevedo: Bzrp Music Sessions, Vol. 52/66", "QUEVEDO || BZRP Music Sessions #52"),
])
def test_title_score_same_numbers_still_match(track, returned):
    assert title_score(track, returned) >= 80


@pytest.mark.parametrize("title,uploader", [
    ("Maroon 5 - Payphone (Official Music Video)", "Maroon 5"),
    ("Maroon 5 - Payphone [Official Video]", "Maroon 5"),
    ("Maroon 5 - Payphone (Official 4K Video)", "Maroon 5"),
    ("Maroon 5 - Payphone (Official HD Video)", "Maroon 5"),
    ("Maroon 5 - Payphone (Video)", "Maroon 5"),
    ("Maroon 5 - Payphone | Music Video", "Maroon 5"),
    ("Maroon 5 - Payphone (Video Oficial)", "Maroon 5"),
    ("Maroon 5 - Payphone (Vídeo Oficial)", "Maroon 5"),
    ("Maroon 5 - Payphone (Clip Officiel)", "Maroon 5"),
    ("Maroon 5 - Payphone", "Maroon5VEVO"),
])
def test_music_videos_rejected(title, uploader):
    passing, rejected = pick_candidates([cand(title, uploader, 231)], "Maroon 5 - Payphone", 231)
    assert passing == []
    assert rejected[0][1] == "music video"


@pytest.mark.parametrize("title", [
    "Maroon 5 - Payphone (Lyric Video)",
    "Maroon 5 - Payphone (Official Lyric Video)",
    "Maroon 5 - Payphone (Official Audio)",
    "Maroon 5 - Payphone (Visualizer)",
    "Payphone",
])
def test_non_video_uploads_still_pass(title):
    passing, _ = pick_candidates([cand(title, "Maroon 5", 231)], "Maroon 5 - Payphone", 231)
    assert len(passing) == 1


def test_deduplicate_keeps_spotify_cover_url():
    from sync import deduplicate_tracks
    sp = [("Maroon 5 - Payphone", 231, "https://i.scdn.co/image/abc")]
    sc = [("Someone - Other Song", 200)]
    merged = deduplicate_tracks(sp, sc)
    assert ("Maroon 5 - Payphone", 231, "https://i.scdn.co/image/abc") in merged
    assert ("Someone - Other Song", 200) in merged


def test_embed_cover_replaces_artwork(tmp_path):
    import subprocess
    from mutagen.id3 import ID3, APIC
    from sync import embed_cover
    mp3 = tmp_path / "t.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
                    "-q:a", "9", str(mp3)], check=True)
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/png", type=3, desc="old", data=b"\x89PNGold"))
    tags.save(mp3)
    cover = tmp_path / "cover.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=640x575", "-frames:v", "1",
                    str(cover)], check=True)  # Spotify art is sometimes slightly off-square
    assert embed_cover(str(mp3), cover.as_uri())
    apics = ID3(mp3).getall("APIC")
    assert len(apics) == 1 and apics[0].mime == "image/jpeg"
    out = tmp_path / "out.jpg"
    out.write_bytes(apics[0].data)
    wh = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                        capture_output=True, text=True).stdout.strip()
    w, h = wh.split(",")
    assert w == h and int(w) >= 574  # square (JPEG may round odd sizes down to even)


def test_embed_cover_keeps_existing_art_on_failure(tmp_path):
    import subprocess
    from mutagen.id3 import ID3, APIC
    from sync import embed_cover
    mp3 = tmp_path / "t.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
                    "-q:a", "9", str(mp3)], check=True)
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="yt", data=b"\xff\xd8yt"))
    tags.save(mp3)
    assert not embed_cover(str(mp3), (tmp_path / "missing.jpg").as_uri())
    assert ID3(mp3).getall("APIC")[0].data == b"\xff\xd8yt"


@pytest.mark.parametrize("album_type,expected", [("album", "big"), ("single", "big"), ("compilation", None)])
def test_spotify_cover_skips_compilations(album_type, expected):
    from sync import spotify_cover
    track = {"album": {"album_type": album_type, "images": [{"url": "big"}, {"url": "small"}]}}
    assert spotify_cover(track) == expected


def test_spotify_cover_handles_missing_images():
    from sync import spotify_cover
    assert spotify_cover({"album": {"album_type": "album", "images": []}}) is None
    assert spotify_cover({}) is None
