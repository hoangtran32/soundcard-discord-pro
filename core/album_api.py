import hashlib
import hmac
import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.album_library import album_library
from core.playlist_manager import playlist_manager
from core.search_engine import search_engine
from core.web_share import SHARED, playable_search_track, shared_search_query


COOKIE = "soundcard_profile"
SESSION_KEY = secrets.token_bytes(32)
SESSION_AGE = 7 * 24 * 60 * 60


def require_album_origin(request: Request):
    origin = request.headers.get("origin")
    scheme = "https" if SHARED else request.url.scheme
    if origin is not None and origin != f"{scheme}://{request.headers.get('host')}":
        raise HTTPException(403, "Yêu cầu hồ sơ không hợp lệ.")


router = APIRouter(prefix="/api", dependencies=[Depends(require_album_origin)])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class AlbumName(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class AlbumSearch(BaseModel):
    query: str = Field(min_length=1, max_length=300)


class TrackSelection(BaseModel):
    ids: list[str] = Field(min_length=1)


class SearchResult(BaseModel):
    track: dict


def signature(value):
    return hmac.new(SESSION_KEY, value.encode(), hashlib.sha256).hexdigest()


def current_profile(request: Request):
    token = request.cookies.get(COOKIE, "")
    value, separator, digest = token.rpartition(":")
    username, _, expiry = value.rpartition(":")
    if separator and expiry.isascii() and expiry.isdigit() and len(expiry) <= 12:
        if int(expiry) > time.time() and hmac.compare_digest(signature(value).encode(), digest.encode()):
            return username
    return None


def require_profile(request: Request):
    username = current_profile(request)
    if not username:
        raise HTTPException(401, "Hãy đăng nhập hồ sơ album trước.")
    return username


def start_profile(response, username):
    value = f"{username}:{int(time.time()) + SESSION_AGE}"
    response.set_cookie(COOKIE, f"{value}:{signature(value)}", max_age=SESSION_AGE,
                        httponly=True, secure=SHARED, samesite="strict")
    return {"username": username}


def get_owned_album(username, album_id):
    album = album_library.get_album(username, album_id)
    if album is None:
        raise HTTPException(404, "Không tìm thấy album.")
    return album


@router.get("/profile")
def get_profile(request: Request):
    return {"username": current_profile(request)}


@router.post("/profile/register", status_code=201)
def register_profile(payload: Credentials, response: Response):
    username = payload.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,31}", username):
        raise HTTPException(400, "Tên đăng nhập cần 3–32 ký tự gồm chữ không dấu, số, dấu chấm, gạch ngang hoặc gạch dưới.")
    if not album_library.register(username, payload.password):
        raise HTTPException(409, "Tên đăng nhập này đã được dùng.")
    return start_profile(response, username)


@router.post("/profile/login")
def login_profile(payload: Credentials, response: Response):
    username = payload.username.strip().lower()
    if not album_library.verify(username, payload.password):
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu album chưa đúng.")
    return start_profile(response, username)


@router.post("/profile/logout")
def logout_profile(response: Response):
    response.delete_cookie(COOKIE, httponly=True, secure=SHARED, samesite="strict")
    return {"username": None}


@router.get("/albums")
def list_albums(username: str = Depends(require_profile)):
    return album_library.list_albums(username)


@router.post("/albums", status_code=201)
def create_album(payload: AlbumName, username: str = Depends(require_profile)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Hãy nhập tên album.")
    return album_library.create_album(username, name)


@router.get("/albums/{album_id}")
def get_album(album_id: str, username: str = Depends(require_profile)):
    return get_owned_album(username, album_id)


@router.delete("/albums/{album_id}")
def delete_album(album_id: str, username: str = Depends(require_profile)):
    if not album_library.delete_album(username, album_id):
        raise HTTPException(404, "Không tìm thấy album.")
    return {"status": "ok"}


def save_tracks(username, album_id, candidates):
    tracks = [track for candidate in candidates if (track := playable_search_track(candidate))]
    if not tracks:
        raise HTTPException(400, "Không tìm thấy bài có thể lưu vào album. Hãy thử link YouTube hoặc SoundCloud.")
    added = album_library.add_tracks(username, album_id, tracks)
    if added is None:
        raise HTTPException(404, "Không tìm thấy album.")
    return {"added": added, "album": get_owned_album(username, album_id)}


@router.post("/albums/{album_id}/tracks/search")
async def add_searched_track(album_id: str, payload: AlbumSearch, username: str = Depends(require_profile)):
    get_owned_album(username, album_id)
    query = shared_search_query(payload.query.strip())
    return save_tracks(username, album_id, await search_engine.search(query, limit=1))


@router.post("/albums/{album_id}/tracks/from-playlist")
def add_playlist_tracks(album_id: str, payload: TrackSelection, username: str = Depends(require_profile)):
    get_owned_album(username, album_id)
    selected = set(payload.ids)
    tracks = [track for track in playlist_manager.get_all() if track["id"] in selected]
    return save_tracks(username, album_id, tracks)


@router.post("/albums/{album_id}/tracks/from-search")
def add_search_result(album_id: str, payload: SearchResult, username: str = Depends(require_profile)):
    return save_tracks(username, album_id, [payload.track])


@router.delete("/albums/{album_id}/tracks/{track_id}")
def delete_album_track(album_id: str, track_id: str, username: str = Depends(require_profile)):
    if not album_library.delete_track(username, album_id, track_id):
        raise HTTPException(404, "Không tìm thấy bài trong album.")
    return get_owned_album(username, album_id)
