import asyncio
import os
import discogs_client
import re
import aiohttp
import unicodedata
import roman
from dotenv import load_dotenv

load_dotenv()

DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")
d = discogs_client.Client('MyTelegramMusicBot/0.6', user_token=DISCOGS_TOKEN)

def search_track_via_master(artist: str, track_title: str) -> dict | None:
    try:
        results = d.search(track=track_title, artist=artist, type='master')

        if not results:
            clean_artist = normalize_string(artist)
            clean_title = normalize_string(track_title)

            if clean_artist != artist or clean_title != track_title:
                results = d.search(track=clean_title, artist=clean_artist, type='master')

            if not results:
                raise Exception(f"Nothing found in Discogs for: {artist}/{clean_artist} - {track_title}/{clean_title}")

        if not results:
            raise Exception("Search didn't go as planned..")

        master_summary = results[0]
        master = d.master(master_summary.id)

        release = getattr(master, 'main_release', None)

        album_name = getattr(master, 'title', '')

        source_obj = release if release else master

        m_genres = getattr(master, 'genres', []) or []
        m_styles = getattr(master, 'styles', []) or []
        r_genres = getattr(release, 'genres', []) or []
        r_styles = getattr(release, 'styles', []) or []

        all_genres = list(set(m_genres + m_styles + r_genres + r_styles))

        year = getattr(master, 'year', None) or getattr(release, 'year', '')

        # search for track in the list
        tracklist = getattr(source_obj, 'tracklist', [])
        matched_track = None

        if tracklist:
            for track in tracklist:
                if track_title.lower() in track.title.lower():
                    matched_track = track
                    break
            if not matched_track:
                matched_track = tracklist[0]

        position = matched_track.position if matched_track else "1"
        found_title = matched_track.title if matched_track else track_title

        disc_number, track_number = parse_position(position)

        return {
            "album": album_name,
            "artist": artist,
            "title": found_title,
            "year": str(year) if year else "",
            "genres": all_genres,
            "disc_number": disc_number,
            "track_number": track_number,
            "position": position
        }

    except Exception as e:
        raise e

def parse_position(position: str) -> tuple[str, str]:
    if not position:
        return "1", "1"

    # '1-05' or '2-1'
    if "-" in position:
        parts = position.split("-", 1)
        disc = re.sub(r'\D', '', parts[0]) or "1"
        track = re.sub(r'\D', '', parts[1]) or parts[1]
        return disc, track

    # vinil A1, B2, C1, D2
    vinyl_match = re.match(r'^([A-Z])(\d+)$', position, re.IGNORECASE)
    if vinyl_match:
        side, track_num = vinyl_match.groups()
        side_code = ord(side.upper()) - ord('A')
        disc_num = str((side_code // 2) + 1)
        return disc_num, track_num

    try:
        num = roman.fromRoman(position)
        return "1", str(num)
    except roman.InvalidRomanNumeralError:
        num = 1

    # just a num
    clean_num = re.sub(r'\D', '', position)
    return "1", clean_num or position

def normalize_string(text: str) -> str:
    if not text: return ""

    # replace to empties
    text = re.sub(r"['’‘`\"“”]", "", text)

    # need for standardization
    text = ''.join(
        c for c in unicodedata.normalize('NFKD', text)
        if unicodedata.category(c) != 'Mn'
    )

    text = re.sub(r'\s+', ' ', text).strip()

    return text

# maybe move to another file in future
async def get_cover_from_itunes(artist: str, album: str) -> str | None:
    url = "https://itunes.apple.com/search"
    params = {
        "term": f"{artist} {album}",
        "entity": "album",
        "limit": 1
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    # parsing json the right way
                    data = await resp.json(content_type=None)
                    results = data.get("results")

                    if results:
                        raw_cover = results[0].get("artworkUrl100")
                        if raw_cover:
                            return raw_cover.replace("100x100bb", "1000x1000bb")
    except Exception as e:
        raise e

    return None

async def setup_tags(artist_name, title_name):
    return await asyncio.to_thread(search_track_via_master, artist_name, title_name)  # launching in a different thread