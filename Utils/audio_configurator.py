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
            return res[0]

    # search in singles, digital releases
    releases = []
    for a, t in queries:
        res = d.search(track=t, artist=a, type='release')
        if res:
            releases.extend(list(res))
            break

    if releases:
        # filer and sort by year (take the earliest version)
        valid_releases = [r for r in releases if getattr(r, 'year', None)]
        if valid_releases:
            valid_releases.sort(key=lambda r: int(r.year))
            return valid_releases[0]

        # in case you can't get the year, take the first
        return releases[0]

    # common search
    for a, t in queries:
        res = d.search(track=t, artist=a)
        if res:
            return res[0]

    if not first_match:
        raise Exception(f"Nothing found in Discogs for: {artist} - {track_title}")

    return first_match

def _set_album_title(full_obj, master) -> str:
    return getattr(full_obj, 'title', '') or getattr(master, 'title', '')

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

    main_genre = _resolve_genre(all_genres, all_styles)

    return main_genre

def _resolve_genre(genres: list[str], styles: list[str]) -> str:
    all_tags_lower = [t.lower() for t in (genres + styles)]
    primary_genre = genres[0] if genres else "Unknown"

    GENRE_BLACKLIST = {
        "experimental", "abstract", "ballad", "vocal",
        "spoken word", "field recording", "lo-fi"
    }

    # filter the blacklisted ones
    valid_styles = [s for s in styles if s.lower() not in GENRE_BLACKLIST]
    first_valid_style = valid_styles[0] if valid_styles else ""

    # soundtracks
    if any(tag in all_tags_lower for tag in ["soundtrack", "score", "theme"]): return "Soundtrack"

    # hip-hop or rap
    if "hip hop" in all_tags_lower or "rap" in all_tags_lower: return "Hip-Hop/Rap"

    # priority should be sorted from the most specific to most abstract one

    # pop
    if "pop" in all_tags_lower:
        # specific ones
        POP_PRIORITY = ["city pop", "synth-pop", "synthpop", "electropop", "indie pop"]
        for pop_style in POP_PRIORITY:
            for s in valid_styles:
                if pop_style in s.lower():
                    return s
        return "Pop"

    # classical
    if "classical" in all_tags_lower:
        CLASSICAL_PRIORITY = ["neoclassical", "modern classical", "contemporary", "minimalism", "chamber"]
        for c_style in CLASSICAL_PRIORITY:
            for s in valid_styles:
                if c_style in s.lower():
                    return s
        return "Classical"

    # other subgenres
    PRIORITY_SUBGENRES = [
        # for rock and metal
        "blackgaze",
        "post-black metal",
        "post-rock",
        "post-metal",
        "shoegaze",
        "dsbm",
        "dungeon synth",
        "thrash metal",
        "death metal",
        "doom metal",
        "stoner rock",

        # for electronic / wave / ambient
        "synthwave",
        "darksynth",
        "vaporwave",
        "vapourwave",
        "dark ambient",
        "ambient",
        "deep house",
        "drum n bass",
        "liquid funk",

        # for jazz / funk / other
        "jazz-funk",
        "city pop"
    ]

    for target in PRIORITY_SUBGENRES:
        for style in styles:
            if target in style.lower(): return style

    # default
    return first_valid_style if first_valid_style else primary_genre

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
    if not tracklist: return None

    target_clean = normalize_string(track_title).lower()

    # exact match or substr
    for track in tracklist:
        t_title = _get_field(track, 'title', '')
        track_clean = normalize_string(t_title).lower()
        if target_clean == track_clean or target_clean in track_clean or track_clean in target_clean: return track

    # if not found
    return tracklist[0]

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
    return 1, int(clean_num) if clean_num else 1

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

def _get_field(obj, key: str, default=""):
    if isinstance(obj, dict): return obj.get(key, default) or default

    # discogs_client.Track objects contains raw data in '.data'
    data_dict = getattr(obj, 'data', None)
    if isinstance(data_dict, dict) and key in data_dict:
        val = data_dict.get(key)
        if val is not None: return val

    return getattr(obj, key, default) or default

def _clean_artist_name(name_str: str) -> str:
    if not name_str:
        return ""
    # remove discogs suffixes
    return re.sub(r'\s*\(\d+\)$', '', str(name_str)).strip()

def _extract_all_artists(matched_track, release_obj, default_album_artist: str) -> str:
    track_artists = _get_field(matched_track, 'artists', None)
    release_artists = _get_field(release_obj, 'artists', None)

    target_artists = track_artists if (track_artists and len(track_artists) > 0) else release_artists

    main_artists = []
    feat_artists = []

    # main artists
    if target_artists and isinstance(target_artists, (list, tuple)):
        for item in target_artists:
            name = _clean_artist_name(_get_field(item, 'name'))
            join = str(_get_field(item, 'join')).strip().lower()

            if not name: continue

            # check the (feat, ft) join word
            if any(ft in join for ft in ('feat', 'ft', 'featuring')):
                if name not in feat_artists: feat_artists.append(name)
            elif name not in main_artists: main_artists.append(name)

    # if none then album_artist
    if not main_artists and default_album_artist and default_album_artist != "Unknown Artist":
        main_artists.append(default_album_artist)

    # parsing extraartists (both track and release)
    track_extras = _get_field(matched_track, 'extraartists', []) or []
    release_extras = _get_field(release_obj, 'extraartists', []) or []
    all_extras = list(track_extras) + list(release_extras)

    for item in all_extras:
        role = str(_get_field(item, 'role')).lower()
        if any(keyword in role for keyword in ('feat', 'guest', 'featuring')):
            name = _clean_artist_name(_get_field(item, 'name'))
            if name and name not in main_artists and name not in feat_artists:
                feat_artists.append(name)

    # parsing track title if there are any (feat. Artist)
    track_title = str(_get_field(matched_track, 'title', ''))
    title_feat_match = re.search(r'[\(\[]\s*(?:feat|ft|featuring)\.?\s+([^\)\]]+)[\)\]]', track_title, re.IGNORECASE)
    if title_feat_match:
        raw_feats = title_feat_match.group(1)
        split_feats = re.split(r'\s*(?:,|&|\band\b)\s*', raw_feats, flags=re.IGNORECASE)
        for f in split_feats:
            cleaned = _clean_artist_name(f)
            if cleaned and cleaned not in main_artists and cleaned not in feat_artists: feat_artists.append(cleaned)

    # build str
    if main_artists:
        if len(main_artists) == 1: base_str = main_artists[0]
        elif len(main_artists) == 2: base_str = f"{main_artists[0]} & {main_artists[1]}"
        else: base_str = ", ".join(main_artists[:-1]) + f" & {main_artists[-1]}"
    else:
        base_str = default_album_artist or ""

    if feat_artists:
        feat_str = f"feat. {', '.join(feat_artists)}"
        return f"{base_str} {feat_str}".strip() if base_str else feat_str

    return base_str or "Unknown Artist"

def _fetch_full_release(search_result):
    if not search_result: return None, None

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

    return search_result, None

def _set_track_artists_and_title(track_data, full_obj, track: Track, album: Album):
    # take title from Discogs
    raw_track_title = _get_field(track_data, 'title', track.title)

    # clear title from parentheses like (feat. ...)
    track.title = re.sub(
        r'\s*[\(\[]\s*(?:feat|ft|featuring)\.?\s+[^\)\]]+[\)\]]',
        '',
        raw_track_title,
        flags=re.IGNORECASE
    ).strip()

    track.artists = _extract_all_artists(track_data, full_obj, album.artist)

def _search_for_tags(file: AudioFile):
    track = Track(title=file.title, artists=file.artist, file_path=file.file_path)
    album = Album()

    first_match = _search_for_track_match(track.artists, track.title)               # first match in search
    full_obj, master = _fetch_full_release(first_match)

    album.title = _set_album_title(full_obj, master)                                # album title
    album.artist = _set_album_artist(full_obj, master)                              # album artist
    album.main_genre = _set_album_genres(master, full_obj)                          # main genre if possible to obtain
    album.year = _set_album_year(full_obj, master)                                  # year
    album.total_tracks = _set_track_count(full_obj)                                 # tracks count

    matched_track_data = _search_for_track(full_obj, track.title)                   # search for track in the list
    _set_track_artists_and_title(matched_track_data, full_obj, track, album)        # track title and artists ; single void method, I know...
    position = getattr(matched_track_data, 'position', '1')                         # pos on disc
    track.disc, track.position = _parse_position(position)                          # need to parse

    return track, album

async def setup_tags(audio_file: AudioFile):
    return await asyncio.to_thread(_search_for_tags, audio_file)  # launching in a different thread

async def get_album_cover(album_name: str, album_artist:str):
    return await _get_cover_from_itunes(album_name, album_artist) # launching in a different thread