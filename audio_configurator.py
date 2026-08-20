import asyncio
import os
import discogs_client
import re
import aiohttp
import unicodedata
import roman
import mutagen
from dotenv import load_dotenv
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TDRC, TYER, TCON, TPOS, TRCK, APIC, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

load_dotenv()

DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")
d = discogs_client.Client('MyTelegramMusicBot/0.6', user_token=DISCOGS_TOKEN)

def search_track_via_master(artist: str, track_title: str) -> dict | None:
    try:
        clean_artist = normalize_string(artist)
        clean_title = normalize_string(track_title)

        queries = [(artist, track_title)]
        if (clean_artist, clean_title) != (artist, track_title):
            queries.append((clean_artist, clean_title))

        first_match = None

        # search in master releases
        for a, t in queries:
            res = d.search(track=t, artist=a, type='master')
            if res:
                first_match = res[0]
                break

        # search in singles, digital releases
        if not first_match:
            for a, t in queries:
                res = d.search(track=t, artist=a, type='release')
                if res:
                    first_match = res[0]
                    break

        # common search
        if not first_match:
            for a, t in queries:
                res = d.search(track=t, artist=a)
                if res:
                    first_match = res[0]
                    break

        if not first_match:
            raise Exception(f"Nothing found in Discogs for: {artist} - {track_title}")

        if isinstance(first_match, discogs_client.Master):
            master = first_match
            release = getattr(master, 'main_release', None)
            album_name = getattr(master, 'title', '')
        else:
            release = first_match
            master = getattr(release, 'master', None)
            album_name = getattr(release, 'title', '')

        # metadata source
        source_obj = release if release else master
        album_artist = artist

        raw_artists = getattr(source_obj, 'artists', None)
        if not raw_artists and master:
            raw_artists = getattr(master, 'artists', None)

        if raw_artists and len(raw_artists) > 0:
            first_artist = raw_artists[0]
            name_str = getattr(first_artist, 'name', '') or (
                first_artist.get('name') if isinstance(first_artist, dict) else str(first_artist)
            )
            if name_str:
                album_artist = re.sub(r'\s*\(\d+\)$', '', name_str).strip()

        m_genres = getattr(master, 'genres', []) if master else []
        m_styles = getattr(master, 'styles', []) if master else []
        r_genres = getattr(release, 'genres', []) if release else []
        r_styles = getattr(release, 'styles', []) if release else []

        all_genres = list(set(m_genres + m_styles + r_genres + r_styles))

        year = None
        if master:
            year = getattr(master, 'year', None)
        if not year and release:
            year = getattr(release, 'year', None)

        # search for track in the list
        tracklist = getattr(source_obj, 'tracklist', [])
        matched_track = None

        if tracklist:
            target_clean = normalize_string(track_title).lower()

            for track in tracklist:
                track_clean = normalize_string(track.title).lower()
                if target_clean in track_clean or track_clean in target_clean:
                    matched_track = track
                    break

            if not matched_track:
                matched_track = tracklist[0]

        position = matched_track.position if matched_track else "1"
        found_title = matched_track.title if matched_track else track_title

        # artists for current track
        track_artists_raw = getattr(matched_track, 'artists', None) if matched_track else None
        extra_artists_raw = getattr(matched_track, 'extraartists', None) if matched_track else None

        target_artists = track_artists_raw if track_artists_raw else raw_artists

        track_artists_list = []
        artists_with_joins = []

        if target_artists:
            for a in target_artists:
                name = getattr(a, 'name', '') or (a.get('name') if isinstance(a, dict) else str(a))
                if not name:
                    continue

                clean_name = re.sub(r'\s*\(\d+\)$', '', name).strip()
                if not clean_name:
                    continue

                track_artists_list.append(clean_name)

                raw_join = getattr(a, 'join', '') or (a.get('join') if isinstance(a, dict) else '')
                artists_with_joins.append((clean_name, raw_join.strip()))

        artist_str = ""
        num_artists = len(artists_with_joins)

        if num_artists > 0:
            for i, (name, join_str) in enumerate(artists_with_joins):
                if i == 0:
                    artist_str = name
                else:
                    prev_join = artists_with_joins[i - 1][1]

                    # if Discogs has "join" (feat., vs., &)
                    if prev_join: artist_str += f" {prev_join} {name}"
                    # if last artist in the list
                    elif i == num_artists - 1: artist_str += f" & {name}"
                    # other cases
                    else: artist_str += f", {name}"

        if not artist_str:
            artist_str = album_artist

        if extra_artists_raw:
            feat_artists = []
            for ea in extra_artists_raw:
                role = getattr(ea, 'role', '') or (ea.get('role') if isinstance(ea, dict) else '')
                if 'feat' in role.lower() or 'guest' in role.lower():
                    ea_name = getattr(ea, 'name', '') or (ea.get('name') if isinstance(ea, dict) else str(ea))
                    clean_ea_name = re.sub(r'\s*\(\d+\)$', '', ea_name).strip()
                    if clean_ea_name and clean_ea_name not in track_artists_list:
                        feat_artists.append(clean_ea_name)
                        track_artists_list.append(clean_ea_name)

            if feat_artists:
                artist_str += f" feat. {', '.join(feat_artists)}"

        artist_str = re.sub(r'\s+', ' ', artist_str).strip()

        disc_number, track_number = parse_position(position)

        return {
            "album": album_name,
            "album_artist": album_artist,
            "title": found_title,
            "artists": artist_str,
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

async def apply_tags(file_path: str, tags: dict, cover_url: str | None = None) -> None:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    cover_bytes = None
    if cover_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cover_url) as resp:
                    if resp.status == 200:
                        cover_bytes = await resp.read()
        except Exception as e:
            print(f"Error getting the cover: {e}")

    def _write_tags():
        audio_type = mutagen.File(file_path)
        if audio_type is None:
            raise ValueError("Audio file type is not supported!")

        ext = os.path.splitext(file_path)[1].lower()

        # format the year
        raw_year = str(tags.get("year", "")).strip()
        year_str = re.sub(r'\D', '', raw_year)[:4] if raw_year else ""

        # for .mp3
        if ext == '.mp3':
            try:
                audio = ID3(file_path)
            except ID3NoHeaderError:
                audio = ID3()

            audio.add(TIT2(encoding=3, text=tags.get("title", "")))
            audio.add(TPE1(encoding=3, text=tags.get("artists", "")))
            audio.add(TPE2(encoding=3, text=tags.get("album_artist", "")))
            audio.add(TALB(encoding=3, text=tags.get("album", "")))

            if year_str:
                audio.add(TDRC(encoding=3, text=year_str))
                audio.add(TYER(encoding=3, text=year_str))

            if tags.get("genres"):
                audio.add(TCON(encoding=3, text=", ".join(tags["genres"])))
            if tags.get("disc_number"):
                audio.add(TPOS(encoding=3, text=str(tags["disc_number"])))
            if tags.get("track_number"):
                audio.add(TRCK(encoding=3, text=str(tags["track_number"])))

            if cover_bytes:
                audio.add(APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc='Cover',
                    data=cover_bytes
                ))
            audio.save(file_path, v2_version=3)

        # .flac
        elif ext == '.flac':
            audio = FLAC(file_path)
            audio["title"] = tags.get("title", "")
            audio["artist"] = tags.get("artists", "")
            audio["album"] = tags.get("album", "")
            audio["albumartist"] = tags.get("album_artist", "")
            if year_str:
                audio["date"] = year_str
            if tags.get("genres"):
                audio["genre"] = tags["genres"]
            if tags.get("disc_number"):
                audio["discnumber"] = str(tags["disc_number"])
            if tags.get("track_number"):
                audio["tracknumber"] = str(tags["track_number"])

            if cover_bytes:
                image = Picture()
                image.type = 3
                image.mime = "image/jpeg"
                image.data = cover_bytes
                audio.clear_pictures()
                audio.add_picture(image)
            audio.save()

    await asyncio.to_thread(_write_tags)

async def setup_tags(artist_name, title_name):
    return await asyncio.to_thread(search_track_via_master, artist_name, title_name)  # launching in a different thread