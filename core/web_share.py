import base64
import hashlib
import hmac
import os
import re
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, Response
from core.search_engine import normalize_source_url


PASSWORD = os.environ.get("SOUNDCARD_SHARE_PASSWORD")
SHARED = PASSWORD is not None
COOKIE_NAME = "__Host-soundcard"
if SHARED and len(PASSWORD) < 24:
    raise RuntimeError("SOUNDCARD_SHARE_PASSWORD must be at least 24 characters.")

if SHARED:
    BASIC_AUTH = "Basic " + base64.b64encode(f"music:{PASSWORD}".encode()).decode()
    COOKIE_VALUE = hmac.new(PASSWORD.encode(), b"soundcard-browser", hashlib.sha256).hexdigest()


def authenticated(connection: Request | WebSocket) -> bool:
    authorization = connection.headers.get("authorization", "").encode()
    cookie = connection.cookies.get(COOKIE_NAME, "").encode()
    return hmac.compare_digest(authorization, BASIC_AUTH.encode()) or hmac.compare_digest(
        cookie, COOKIE_VALUE.encode()
    )


def same_origin(connection: Request | WebSocket) -> bool:
    origin = connection.headers.get("origin")
    return origin is None or origin == f"https://{connection.headers.get('host')}"


async def protect_shared_web(request: Request, call_next):
    if request.method == "GET" and request.url.path == "/healthz":
        response = Response(status_code=204, headers={"Access-Control-Allow-Origin": "*"})
    elif not authenticated(request):
        response = JSONResponse(
            {"detail": "Đăng nhập để điều khiển nhạc."},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="SoundCard Discord", charset="UTF-8"'},
        )
    elif request.method not in {"GET", "HEAD"} and not same_origin(request):
        response = JSONResponse({"detail": "Yêu cầu không hợp lệ."}, status_code=403)
    else:
        response = await call_next(request)
        if request.url.path == "/" and response.status_code == 200:
            response.set_cookie(
                COOKIE_NAME, COOKIE_VALUE, secure=True, httponly=True, samesite="strict"
            )

    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; connect-src 'self' wss:; "
        "img-src 'self' https: data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
        "https://cdnjs.cloudflare.com; font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
    )
    return response


def require_local_admin():
    if SHARED:
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên trên máy chạy bot có quyền này.")


def shared_track_url(value: str) -> str | None:
    """Return a canonical URL for a single track on a supported provider."""
    try:
        url = urlsplit(value)
        host = url.hostname
        if url.scheme not in {"http", "https"} or url.netloc.lower() != host:
            return None
    except ValueError:
        return None

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        if url.path == "/watch" and host != "youtu.be":
            video = parse_qs(url.query).get("v", [""])[0]
        else:
            path = re.fullmatch(r"/(?:shorts/|live/)?([\w-]{11})/?", url.path, re.ASCII)
            video = path[1] if path else ""
        if re.fullmatch(r"[\w-]{11}", video, re.ASCII):
            return f"https://www.youtube.com/watch?v={video}"

    if host in {"soundcloud.com", "www.soundcloud.com"} and re.fullmatch(
        r"/[\w-]+/[\w-]+/?", url.path, re.ASCII
    ):
        return f"https://soundcloud.com{url.path.rstrip('/')}"
    if host == "api.soundcloud.com" and re.fullmatch(r"/tracks/\d+/?", url.path, re.ASCII):
        return f"https://api.soundcloud.com{url.path.rstrip('/')}"
    if host == "open.spotify.com" and re.fullmatch(r"/track/[a-zA-Z0-9]{22}/?", url.path):
        return f"https://open.spotify.com{url.path.rstrip('/')}"
    return None


def shared_search_query(query: str) -> str:
    query = normalize_source_url(query)
    if len(query) <= 300 and (url := shared_track_url(query)):
        return url
    if len(query) <= 300 and "://" not in query:
        return query
    raise HTTPException(status_code=400, detail="Hãy nhập tên bài hoặc link một bài YouTube, SoundCloud hay Spotify.")


def playable_search_track(item: object, provider_only: bool = True) -> dict | None:
    if not isinstance(item, dict) or not isinstance(item.get("url"), str):
        return None
    raw_url = item["url"]
    url = shared_track_url(raw_url)
    if url is None and not provider_only:
        try:
            parsed = urlsplit(raw_url)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                url = raw_url
        except ValueError:
            return None
    if not url or url.startswith("https://open.spotify.com/"):
        return None
    fields = ("title", "duration_str", "thumbnail", "uploader", "platform")
    track = {field: str(item.get(field) or "")[:500] for field in fields}
    duration = item.get("duration")
    return {**track, "url": url, "duration": max(0, duration) if type(duration) is int else 0}


def shared_search_results(results: list[dict]) -> list[dict]:
    return [{**track, "url": url} for track in results if (url := shared_track_url(track["url"]))]
