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

from Models.file_model import AudioFile
from Models.main_models import Album, Track

load_dotenv()

DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")
d = discogs_client.Client('MyTelegramMusicBot/0.6', user_token=DISCOGS_TOKEN)

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
async def _get_cover_from_itunes(album_name: str, album_artist: str) -> str | None:
    url = "https://itunes.apple.com/search"
    params = {
        "term": f"{album_artist} {album_name}",
        "entity": "album",
        "limit": 1
    }

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

    return None

def _apply_mp3_tags(file_path: str, track: Track, album: Album, cover_bytes: bytes | None) -> None:
    try: audio = ID3(file_path)
    except ID3NoHeaderError: audio = ID3()

    # main
    audio.add(TIT2(encoding=3, text=track.title))
    audio.add(TPE1(encoding=3, text=track.artists))
    audio.add(TPE2(encoding=3, text=album.artist))
    audio.add(TALB(encoding=3, text=album.title))

    # year
    if album.year:
        year_str = re.sub(r'\D', '', str(album.year))[:4]
        if year_str:
            audio.add(TDRC(encoding=3, text=year_str))
            audio.add(TYER(encoding=3, text=year_str))


    if album.main_genre: audio.add(TCON(encoding=3, text=album.main_genre))     # genre
    if track.disc: audio.add(TPOS(encoding=3, text=str(track.disc)))            # disc

    # track / track count
    if track.position:
        trck_val = f"{track.position}/{album.total_tracks}" if album.total_tracks else str(track.position)
        audio.add(TRCK(encoding=3, text=trck_val))

    # cover
    if cover_bytes:
        audio.add(APIC(
            encoding=3,
            mime='image/jpeg',
            type=3,
            desc='Cover',
            data=cover_bytes
        ))

    audio.save(file_path, v2_version=3)


def _apply_flac_tags(file_path: str, track: Track, album: Album, cover_bytes: bytes | None) -> None:
    audio = FLAC(file_path)
    audio["title"] = track.title
    audio["artist"] = track.artists
    audio["album"] = album.title
    audio["albumartist"] = album.artist

    if album.year:
        year_str = re.sub(r'\D', '', str(album.year))[:4]
        if year_str:
            audio["date"] = year_str

    if album.main_genre:
        audio["genre"] = album.main_genre if isinstance(album.main_genre, list) else [str(album.main_genre)]

    if track.disc: audio["discnumber"] = str(track.disc)
    if track.position: audio["tracknumber"] = str(track.position)
    if album.total_tracks: audio["tracktotal"] = str(album.total_tracks)

    if cover_bytes:
        image = Picture()
        image.type = 3
        image.mime = "image/jpeg"
        image.data = cover_bytes
        audio.clear_pictures()
        audio.add_picture(image)

    audio.save()

async def _download_cover_bytes(cover_url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        print(f"Failed to download cover from {cover_url}: {e}")
    return None

async def apply_tags(file_path: str, track: Track, album: Album, cover_url: str | None) -> None:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # download bytes async
    cover_bytes = await _download_cover_bytes(cover_url) if cover_url else None

    ext = os.path.splitext(file_path)[1].lower()

    def _write():
        audio_type = mutagen.File(file_path)
        if audio_type is None:
            raise ValueError(f"Audio file type '{ext}' is not supported by mutagen!")

        if ext == '.mp3':
            _apply_mp3_tags(file_path, track, album, cover_bytes)
        elif ext == '.flac':
            _apply_flac_tags(file_path, track, album, cover_bytes)
        else:
            raise NotImplementedError(f"Format {ext} is not implemented yet.")

    # file I/O in another thread
    await asyncio.to_thread(_write)

def _search_for_track_match(artist: str | None, track_title: str | None):
    if artist is None or track_title is None: raise Exception("Artist or Track Title is Null!")

    clean_artist = normalize_string(artist)
    clean_title = normalize_string(track_title)

    first_match = None

    queries = [(artist, track_title)]
    if (clean_artist, clean_title) != (artist, track_title):
        queries.append((clean_artist, clean_title))

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

    return first_match

def _set_album_title(full_obj, master) -> str:
    return getattr(full_obj, 'title', '') or getattr(master, 'title', '')

def _clean_artist_name(name_str: str) -> str:
    if not name_str:
        return ""
    # remove suffixes
    return re.sub(r'\s*\(\d+\)$', '', name_str).strip()

def _set_album_artist(metadata, master) -> str:
    raw_artists = None
    for obj in (metadata, master):
        if obj is None: continue
        raw_artists = getattr(obj, 'artists', None)
        if raw_artists: break

    if not raw_artists:
        return "Unknown Artist"

    first_artist = raw_artists[0]
    name_str = ""

    # discogs_client may return Artist, dict or str
    if hasattr(first_artist, 'name'): name_str = first_artist.name
    elif isinstance(first_artist, dict): name_str = first_artist.get('name', '')
    else: name_str = str(first_artist)

    cleaned = _clean_artist_name(name_str)
    return cleaned or "Unknown Artist"

def _set_album_genres(master, release):
    m_genres = getattr(master, 'genres', []) if master else []
    m_styles = getattr(master, 'styles', []) if master else []
    r_genres = getattr(release, 'genres', []) if release else []
    r_styles = getattr(release, 'styles', []) if release else []

    all_genres = list(dict.fromkeys(m_genres + r_genres))
    all_styles = list(dict.fromkeys(m_styles + r_styles))

    # first in 'styles' as a main genre if available
    if all_styles: main_genre = all_styles[0]
    elif all_genres: main_genre = all_genres[0]
    else: main_genre = "Unknown"

    return main_genre


def _set_album_year(metadata, master) -> str:
    # year of master
    if master and getattr(master, 'year', None): return str(master.year)

    # specific release
    if metadata:
        rel_year = getattr(metadata, 'year', None)
        if rel_year: return str(rel_year)

        released_str = getattr(metadata, 'released', None)
        if released_str:
            match = re.search(r'\b(19\d\d|20\d\d)\b', str(released_str))
            if match: return match.group(1)

    return ""

def _set_track_count(source_obj) -> int:
    tracklist = getattr(source_obj, 'tracklist', [])
    if not tracklist:
        return 0
    # take only real tracks
    actual_tracks = [
        t for t in tracklist
        if getattr(t, 'type_', 'track') == 'track' or getattr(t, 'type', 'track') == 'track'
    ]
    return len(actual_tracks) or len(tracklist)

def _search_for_track(metadata, track_title):
    tracklist = getattr(metadata, 'tracklist', [])
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

    return matched_track

def _parse_position(position: str):
    if not position: return 1, 1

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

    # roman
    try:
        num = roman.fromRoman(position)
        return 1, num
    except roman.InvalidRomanNumeralError:
        pass

    # just a num
    clean_num = re.sub(r'\D', '', position)
    return 1, clean_num or int(position)

def _extract_artist_info(target_artists: list) -> tuple[list[str], list[tuple[str, str]]]:
    clean_names: list[str] = []
    artists_with_joins: list[tuple[str, str]] = []

    for a in target_artists:
        if isinstance(a, str): name, raw_join = a, ""
        else:
            name = getattr(a, 'name', '') or (a.get('name') if isinstance(a, dict) else str(a))
            raw_join = getattr(a, 'join', '') or (a.get('join') if isinstance(a, dict) else '')

        if not name: continue

        clean_name = re.sub(r'\s*\(\d+\)$', '', name).strip()
        if not clean_name: continue

        clean_names.append(clean_name)
        artists_with_joins.append((clean_name, str(raw_join).strip()))

    return clean_names, artists_with_joins

def _build_main_artist_string(artists_with_joins: list[tuple[str, str]]) -> str:
    num_artists = len(artists_with_joins)
    if num_artists == 0: return ""

    result = []
    for i, (name, _) in enumerate(artists_with_joins):
        if i == 0: result.append(name)
        else:
            prev_join = artists_with_joins[i - 1][1]
            if prev_join: result.append(f"{prev_join} {name}")
            elif i == num_artists - 1: result.append(f"& {name}")
            else: result.append(f", {name}")

    return " ".join(result)

def _extract_feat_artists(extra_artists_raw: list | None, existing_artists: list[str]) -> list[str]:
    if not extra_artists_raw or not isinstance(extra_artists_raw, (list, tuple)): return []

    feat_artists = []
    for ea in extra_artists_raw:
        role = getattr(ea, 'role', '') or (ea.get('role') if isinstance(ea, dict) else '')
        role_str = str(role).lower()

        if 'feat' in role_str or 'guest' in role_str:
            ea_name = getattr(ea, 'name', '') or (ea.get('name') if isinstance(ea, dict) else str(ea))
            clean_ea_name = re.sub(r'\s*\(\d+\)$', '', str(ea_name)).strip()

            if clean_ea_name and clean_ea_name not in existing_artists and clean_ea_name not in feat_artists:
                feat_artists.append(clean_ea_name)

    return feat_artists

def _set_track_artists(matched_track_data, album_artist: str | None) -> str:
    track_artists_raw = getattr(matched_track_data, 'artists', None)
    extra_artists_raw = getattr(matched_track_data, 'extraartists', None)

    if track_artists_raw and isinstance(track_artists_raw, (list, tuple)): target_artists = list(track_artists_raw)
    elif album_artist and album_artist != "Unknown Artist": target_artists = [album_artist]
    else: target_artists = []

    track_artists_list, artists_with_joins = _extract_artist_info(target_artists)

    artist_str = _build_main_artist_string(artists_with_joins)
    if not artist_str: artist_str = album_artist if (album_artist and album_artist != "Unknown Artist") else ""

    feat_artists = _extract_feat_artists(extra_artists_raw, existing_artists=track_artists_list)
    if feat_artists:
        if artist_str: artist_str += f" feat. {', '.join(feat_artists)}"
        else: artist_str = f"feat. {', '.join(feat_artists)}"

    return re.sub(r'\s+', ' ', artist_str).strip() or (album_artist or "Unknown Artist")

def _fetch_full_release(search_result):
    if not search_result:
        return None, None

    try:
        # master release
        if isinstance(search_result, discogs_client.Master):
            master = search_result
            release = getattr(master, 'main_release', None) or master
            return release, master

        # specific release
        if isinstance(search_result, discogs_client.Release):
            release = search_result
            master = getattr(release, 'master', None)
            return release, master

    except Exception as e:
        print(f"Error resolving full release/master: {e}")

    return search_result, None

def _search_for_tags(file: AudioFile):
    track = Track(title=file.title, artists=file.artist, file_path=file.file_path)
    album = Album()

    first_match = _search_for_track_match(track.artists, track.title)               # first match in search
    full_obj, master = _fetch_full_release(first_match)

    album.title = _set_album_title(full_obj, master)                        # album title
    album.artist = _set_album_artist(full_obj, master)                      # album artist
    album.main_genre = _set_album_genres(master, full_obj)                  # main genre if possible to obtain
    album.year = _set_album_year(full_obj, master)                          # year
    album.total_tracks = _set_track_count(full_obj)                         # tracks count

    matched_track_data = _search_for_track(full_obj, track.title)           # search for track in the list
    track.title = getattr(matched_track_data, 'title', track.title)         # track title (just in case if the orig one is wrong)
    track.artists = _set_track_artists(matched_track_data, album.artist)    # artists for a specific track (including ',', '&' and 'feat.')
    position = getattr(matched_track_data, 'position', '1')                 # pos on disc
    track.disc, track.position = _parse_position(position)                  # need to parse

    return track, album

async def setup_tags(audio_file: AudioFile):
    return await asyncio.to_thread(_search_for_tags, audio_file)  # launching in a different thread

async def get_album_cover(album_name: str, album_artist:str):
    return await _get_cover_from_itunes(album_name, album_artist) # launching in a different thread