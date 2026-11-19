import asyncio
import re
import uuid
import requests
import yt_dlp
from typing import List, Dict, Any, Optional
from urllib.parse import urlsplit


def normalize_source_url(query: str) -> str:
    if re.match(r"(?:(?:www|m|music|open|api)\.)?(?:youtube\.com|youtu\.be|soundcloud\.com|spotify\.com)/", query, re.I):
        return "https://" + query
    return query

def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class MusicSearchEngine:
    """Multi-platform search engine supporting YouTube, SoundCloud, Spotify, and Direct Links."""

    @staticmethod
    def _clean_title(title: str) -> str:
        # Clean unwanted suffixes
        return re.sub(r'\(Official\s*(Music\s*)?Video\)|\[Official\s*(Music\s*)?Video\]|\(Lyrics\)|\[Lyrics\]|\(Official Audio\)', '', title, flags=re.IGNORECASE).strip()

    async def search(self, query: str, platform: str = "youtube", limit: int = 8) -> List[Dict[str, Any]]:
        query = normalize_source_url(query.strip())
        if not query:
            return []

        if query.lower().startswith(("http://", "https://")):
            try:
                host = urlsplit(query).hostname
            except ValueError:
                return []
            if host == "open.spotify.com":
                return await self._resolve_spotify_link(query)
            return await self._extract_direct_url(query)

        platform = platform.lower()
        if platform == "soundcloud":
            return await self._search_soundcloud(query, limit)
        elif platform == "spotify":
            return await self._search_spotify_style(query, limit)
        else:
            return await self._search_youtube(query, limit)

    async def _search_youtube(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _exec():
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': f'ytsearch{limit}',
                'skip_download': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    res = ydl.extract_info(f'ytsearch{limit}:{query}', download=False)
                    entries = res.get('entries', []) if res else []
                    results = []
                    for e in entries:
                        if not e:
                            continue
                        video_id = e.get('id')
                        url = f"https://www.youtube.com/watch?v={video_id}" if video_id else e.get('webpage_url') or e.get('url')
                        if not url:
                            continue
                        thumb = e.get('thumbnail') or (e.get('thumbnails')[-1].get('url') if e.get('thumbnails') else '')
                        dur = e.get('duration') or 0
                        results.append({
                            'id': str(uuid.uuid4())[:8],
                            'title': e.get('title', 'Unknown Title'),
                            'url': url,
                            'duration': int(dur),
                            'duration_str': format_duration(dur),
                            'thumbnail': thumb,
                            'uploader': e.get('channel') or e.get('uploader') or 'YouTube',
                            'view_count': e.get('view_count'),
                            'platform': 'youtube'
                        })
                    return results
                except Exception as ex:
                    print(f"[SearchEngine] YouTube search error: {ex}")
                    return []

        return await loop.run_in_executor(None, _exec)

    async def _search_soundcloud(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _exec():
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': f'scsearch{limit}',
                'skip_download': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    res = ydl.extract_info(f'scsearch{limit}:{query}', download=False)
                    entries = res.get('entries', []) if res else []
                    results = []
                    for e in entries:
                        if not e:
                            continue
                        dur = e.get('duration') or 0
                        thumb = e.get('thumbnail') or (e.get('thumbnails')[-1].get('url') if e.get('thumbnails') else '')
                        results.append({
                            'id': str(uuid.uuid4())[:8],
                            'title': e.get('title', 'Unknown Title'),
                            'url': e.get('url') or e.get('webpage_url') or '',
                            'duration': int(dur),
                            'duration_str': format_duration(dur),
                            'thumbnail': thumb,
                            'uploader': e.get('uploader') or 'SoundCloud',
                            'platform': 'soundcloud'
                        })
                    return results
                except Exception as ex:
                    print(f"[SearchEngine] SoundCloud search error: {ex}")
                    return []

        return await loop.run_in_executor(None, _exec)

    async def _search_spotify_style(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Search Spotify style: searches YouTube Music for studio tracks with Spotify tag."""
        loop = asyncio.get_event_loop()
        def _exec():
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': f'ytsearch{limit}',
                'skip_download': True,
            }
            # Add 'Audio' or 'Official Audio' to prioritize high quality Spotify-like music tracks
            spotify_query = f"{query} Audio"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    res = ydl.extract_info(f'ytsearch{limit}:{spotify_query}', download=False)
                    entries = res.get('entries', []) if res else []
                    results = []
                    for e in entries:
                        if not e:
                            continue
                        url = e.get('url') or e.get('webpage_url') or f"https://www.youtube.com/watch?v={e.get('id')}"
                        thumb = e.get('thumbnail') or (e.get('thumbnails')[-1].get('url') if e.get('thumbnails') else '')
                        dur = e.get('duration') or 0
                        results.append({
                            'id': str(uuid.uuid4())[:8],
                            'title': self._clean_title(e.get('title', 'Unknown Title')),
                            'url': url,
                            'duration': int(dur),
                            'duration_str': format_duration(dur),
                            'thumbnail': thumb,
                            'uploader': e.get('uploader') or e.get('channel') or 'Spotify Music',
                            'platform': 'spotify'
                        })
                    return results
                except Exception as ex:
                    print(f"[SearchEngine] Spotify style search error: {ex}")
                    return []

        return await loop.run_in_executor(None, _exec)

    async def _resolve_spotify_link(self, spotify_url: str) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _exec():
            try:
                # Use Spotify public oEmbed endpoint
                r = requests.get("https://open.spotify.com/oembed", params={"url": spotify_url}, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    track_title = data.get('title', '')
                    thumbnail = data.get('thumbnail_url', '')

                    # Search YouTube for matching audio stream
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': True,
                        'default_search': 'ytsearch1',
                        'skip_download': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        res = ydl.extract_info(f"ytsearch1:{track_title} Audio", download=False)
                        entries = res.get('entries', []) if res else []
                        if entries and entries[0]:
                            e = entries[0]
                            dur = e.get('duration') or 0
                            return [{
                                'id': str(uuid.uuid4())[:8],
                                'title': track_title,
                                'url': e.get('url') or f"https://www.youtube.com/watch?v={e.get('id')}",
                                'duration': int(dur),
                                'duration_str': format_duration(dur),
                                'thumbnail': thumbnail or e.get('thumbnail', ''),
                                'uploader': 'Spotify',
                                'platform': 'spotify'
                            }]
            except Exception as ex:
                print(f"[SearchEngine] Error resolving Spotify link: {ex}")
            return []

        return await loop.run_in_executor(None, _exec)

    async def _extract_direct_url(self, url: str) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _exec():
            platform = "url"
            if "youtube.com" in url or "youtu.be" in url:
                platform = "youtube"
            elif "soundcloud.com" in url:
                platform = "soundcloud"
            elif "spotify.com" in url:
                platform = "spotify"

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'skip_download': True,
                'js_runtimes': {'node': {}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    res = ydl.extract_info(url, download=False)
                    if not res:
                        return []
                    entries = res.get('entries', []) if 'entries' in res else [res]
                    results = []
                    for e in entries:
                        if not e:
                            continue
                        dur = e.get('duration') or 0
                        thumb = e.get('thumbnail') or (e.get('thumbnails')[-1].get('url') if e.get('thumbnails') else '')
                        results.append({
                            'id': str(uuid.uuid4())[:8],
                            'title': e.get('title', 'Audio Stream'),
                            'url': e.get('webpage_url') or e.get('url') or url,
                            'duration': int(dur),
                            'duration_str': format_duration(dur),
                            'thumbnail': thumb,
                            'uploader': e.get('channel') or e.get('uploader') or platform.capitalize(),
                            'view_count': e.get('view_count'),
                            'platform': platform
                        })
                    return results
                except Exception as ex:
                    print(f"[SearchEngine] Direct URL extract error: {ex}")
                    # Return basic item for direct audio streams
                    return [{
                        'id': str(uuid.uuid4())[:8],
                        'title': url.split('/')[-1] or 'Audio Stream',
                        'url': url,
                        'duration': 0,
                        'duration_str': '--:--',
                        'thumbnail': '',
                        'uploader': 'Direct Stream',
                        'platform': platform
                    }]

        return await loop.run_in_executor(None, _exec)

search_engine = MusicSearchEngine()
