import sys
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import asyncio
import math
import os
import glob
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.album_api import get_owned_album, require_album_origin, require_profile, router as album_router
from core.album_library import album_library
from core.config_manager import config_manager
from core.playlist_manager import playlist_manager
from core.room_manager import room_manager
from core.discord_streamer import streamer
from core.search_engine import search_engine
from core.web_share import (
    SHARED, authenticated, protect_shared_web, require_local_admin, same_origin,
    shared_search_query, shared_search_results, shared_track_url,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    album_library.initialize()
    loop = asyncio.get_running_loop()
    streamer.set_event_loop(loop)
    broadcast_task = asyncio.create_task(_ws_broadcast_loop())
    print("[Server] SoundCard Discord backend started successfully!")
    yield
    broadcast_task.cancel()
    streamer.stop()
    await streamer.disconnect_all_rooms()
    for bot in streamer.bots.values():
        await bot.close()

app = FastAPI(title="SoundCard Discord API", lifespan=lifespan)
app.include_router(album_router)

if SHARED:
    app.middleware("http")(protect_shared_web)
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
BACKGROUND_DIR = os.path.join(BASE_DIR, "background")

os.makedirs(BACKGROUND_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/background/{filename}")
async def get_background_file(filename: str):
    file_path = os.path.realpath(os.path.join(BACKGROUND_DIR, filename))
    if os.path.dirname(file_path) != os.path.realpath(BACKGROUND_DIR) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Background file not found")
    return FileResponse(file_path)

@app.get("/")
async def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>SoundCard Discord Server Running</h1>")

active_websockets: List[WebSocket] = []
room_connections = asyncio.Lock()


def browser_config():
    config = config_manager.load()
    if not SHARED:
        return {**config, "albums_enabled": True}
    fields = ("current_background", "bg_blur", "bg_brightness", "glass_opacity", "volume")
    return {**{field: config.get(field) for field in fields}, "shared": True, "albums_enabled": True}


def browser_room(room):
    if not SHARED or room is None:
        return room
    fields = ("id", "name", "guild_id", "channel_id", "selected", "status", "ping")
    return {field: room.get(field) for field in fields}


def browser_rooms():
    return [browser_room(room) for room in room_manager.get_all()]


async def play_in_selected_rooms(track, album=None):
    if not SHARED:
        streamer.active_album = album
        await streamer.play_track(track)
        return
    async with room_connections:
        streamer.sync_rooms_status()
        rooms = room_manager.get_selected()
        if not rooms:
            raise HTTPException(status_code=409, detail="Hãy chọn một kênh thoại Discord.")
        connected = False
        for room in rooms:
            if room["status"] in {"connected", "playing"} or await streamer.connect_room(room["id"]):
                connected = True
        if not connected:
            raise HTTPException(status_code=503, detail="Bot chưa kết nối được vào kênh Discord đã chọn.")
        streamer.active_album = album
        await streamer.play_track(track)

@app.websocket("/ws/player")
async def websocket_player(websocket: WebSocket):
    if SHARED and (not authenticated(websocket) or not same_origin(websocket)):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        streamer.sync_rooms_status()
        await websocket.send_json({
            "type": "state_update",
            "state": streamer.get_state(),
            "rooms": browser_rooms(),
            "config": browser_config()
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
    except Exception:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

async def _ws_broadcast_loop():
    """Real-time broadcast loop for VU meter, position, and synced room connection status."""
    while True:
        try:
            if active_websockets:
                streamer.sync_rooms_status()
                payload = {
                    "type": "tick",
                    "state": streamer.get_state(),
                    "rooms": browser_rooms()
                }
                dead = []
                for ws in active_websockets:
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead.append(ws)
                for d in dead:
                    if d in active_websockets:
                        active_websockets.remove(d)
            await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.5)

# --- REST API Endpoints ---

# State
@app.get("/api/state")
async def get_state():
    streamer.sync_rooms_status()
    return streamer.get_state()

# Search API (YouTube, SoundCloud, Spotify, Direct URLs)
@app.post("/api/search")
async def search_music(payload: Dict[str, Any] = Body(...)):
    query = payload.get("query", "").strip()
    platform = payload.get("platform", "youtube").lower()
    limit = int(payload.get("limit", 8))
    if not query:
        return {"results": []}
    if SHARED:
        query = shared_search_query(query)
        limit = max(1, min(limit, 12))
    results = await search_engine.search(query, platform=platform, limit=limit)
    if SHARED:
        results = shared_search_results(results)
    return {"results": results, "platform": platform, "query": query}

# Player Controls
@app.post("/api/player/play")
async def player_play(payload: Dict[str, Any] = Body(default={})):
    track_id = payload.get("id")
    if track_id:
        track = next((t for t in playlist_manager.get_all() if t.get("id") == track_id), None)
        if track:
            await play_in_selected_rooms(track)
            return {"status": "ok", "playing": track}
        raise HTTPException(status_code=404, detail="Track not found")
    
    if streamer.is_paused:
        streamer.resume()
        return {"status": "resumed"}

    if streamer.active_album:
        album = streamer.active_album
        track = album["tracks"][0]
        await play_in_selected_rooms(track, album)
        return {"status": "ok", "playing": track}

    selected = playlist_manager.get_selected()
    if selected:
        await play_in_selected_rooms(selected[0])
        return {"status": "ok", "playing": selected[0]}
    
    all_tracks = playlist_manager.get_all()
    if all_tracks:
        await play_in_selected_rooms(all_tracks[0])
        return {"status": "ok", "playing": all_tracks[0]}

    return {"status": "empty_playlist"}

@app.post("/api/albums/{album_id}/play", dependencies=[Depends(require_album_origin)])
async def play_album(album_id: str, payload: Dict[str, Any] = Body(default={}),
                     username: str = Depends(require_profile)):
    album = get_owned_album(username, album_id)
    tracks = album["tracks"]
    if not tracks:
        raise HTTPException(409, "Hãy thêm bài hát vào album trước khi phát.")
    track_id = payload.get("track_id")
    track = next((item for item in tracks if item["id"] == track_id), None) if track_id else tracks[0]
    if track is None:
        raise HTTPException(404, "Không tìm thấy bài trong album.")
    await play_in_selected_rooms(track, album)
    return {"status": "ok", "playing": track}

@app.post("/api/player/pause")
async def player_pause():
    streamer.pause()
    return {"status": "paused"}

@app.post("/api/player/resume")
async def player_resume():
    streamer.resume()
    return {"status": "resumed"}

@app.post("/api/player/stop")
async def player_stop():
    streamer.stop()
    return {"status": "stopped"}

@app.post("/api/player/next")
async def player_next():
    await streamer.next_track()
    return {"status": "ok", "current": streamer.current_track}

@app.post("/api/player/prev")
async def player_prev():
    await streamer.prev_track()
    return {"status": "ok", "current": streamer.current_track}

@app.post("/api/player/seek")
async def player_seek(payload: Dict[str, Any] = Body(...)):
    seconds = float(payload.get("seconds", 0))
    if not math.isfinite(seconds) or seconds < 0:
        raise HTTPException(status_code=400, detail="Vị trí phát không hợp lệ.")
    await streamer.seek(seconds)
    return {"status": "ok", "seconds": seconds}

@app.post("/api/player/volume")
async def player_volume(payload: Dict[str, Any] = Body(...)):
    volume = float(payload.get("volume", 1.0))
    if not math.isfinite(volume) or not 0 <= volume <= 2:
        raise HTTPException(status_code=400, detail="Âm lượng phải nằm trong khoảng 0–200%.")
    streamer.set_volume(volume)
    return {"status": "ok", "volume": volume}

@app.post("/api/player/repeat")
async def player_repeat(payload: Dict[str, Any] = Body(...)):
    mode = payload.get("mode", "off")
    if mode not in ("off", "one", "all"):
        raise HTTPException(status_code=400, detail="Chế độ lặp không hợp lệ.")
    config_manager.set("repeat_mode", mode)
    return {"status": "ok", "repeat_mode": mode}

@app.post("/api/player/shuffle")
async def player_shuffle(payload: Dict[str, Any] = Body(...)):
    shuffle = bool(payload.get("shuffle", False))
    config_manager.set("shuffle", shuffle)
    return {"status": "ok", "shuffle": shuffle}

# Playlist Management
@app.get("/api/playlist")
async def get_playlist():
    return playlist_manager.get_all()

@app.post("/api/playlist/add")
async def playlist_add(payload: Dict[str, Any] = Body(...)):
    url = payload.get("url", "").strip()
    platform = payload.get("platform", "youtube")
    if not url:
        raise HTTPException(status_code=400, detail="URL or search query is required")
    if SHARED:
        query = shared_search_query(url)
        results = shared_search_results(await search_engine.search(query, platform=platform, limit=1))
        if not results:
            raise HTTPException(status_code=404, detail="Không tìm được bài có thể phát.")
        items = [playlist_manager.add_item_direct(track) for track in results]
        return {"status": "ok", "added": items, "total": len(playlist_manager.get_all())}
    try:
        items = await playlist_manager.add_url_or_query(url, platform=platform)
        return {"status": "ok", "added": items, "total": len(playlist_manager.get_all())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/playlist/add-direct")
async def playlist_add_direct(payload: Dict[str, Any] = Body(...)):
    item = payload.get("track")
    if not item:
        raise HTTPException(status_code=400, detail="Track data required")
    if SHARED:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            raise HTTPException(status_code=400, detail="Dữ liệu bài hát không hợp lệ.")
        url = shared_track_url(item["url"])
        if not url or url.startswith("https://open.spotify.com/"):
            raise HTTPException(status_code=400, detail="Hãy tìm bài bằng thanh tìm kiếm trước khi thêm.")
        fields = ("title", "duration_str", "thumbnail", "uploader", "platform")
        duration = item.get("duration")
        item = {field: str(item.get(field) or "")[:500] for field in fields}
        item.update(url=url, duration=max(0, duration) if type(duration) is int else 0)
    added = playlist_manager.add_item_direct(item)
    return {"status": "ok", "track": added, "total": len(playlist_manager.get_all())}

@app.post("/api/playlist/select")
async def playlist_select(payload: Dict[str, Any] = Body(...)):
    item_id = payload.get("id")
    selected = bool(payload.get("selected", True))
    playlist_manager.set_selected(item_id, selected)
    return {"status": "ok", "id": item_id, "selected": selected}

@app.post("/api/playlist/select-all")
async def playlist_select_all(payload: Dict[str, Any] = Body(...)):
    selected = bool(payload.get("selected", True))
    playlist_manager.select_all(selected)
    return {"status": "ok", "selected": selected}

@app.delete("/api/playlist/{item_id}")
async def playlist_delete(item_id: str):
    ok = playlist_manager.delete_item(item_id)
    return {"status": "ok", "deleted": ok}

@app.post("/api/playlist/clear")
async def playlist_clear():
    playlist_manager.clear()
    return {"status": "ok"}

@app.post("/api/playlist/reorder")
async def playlist_reorder(payload: Dict[str, Any] = Body(...)):
    ids = payload.get("ids", [])
    playlist_manager.reorder(ids)
    return {"status": "ok"}

# Voice Room Management
@app.get("/api/rooms")
async def get_rooms():
    streamer.sync_rooms_status()
    return browser_rooms()

@app.post("/api/rooms/add", dependencies=[Depends(require_local_admin)])
async def room_add(payload: Dict[str, Any] = Body(...)):
    name = payload.get("name", "")
    guild_id = payload.get("guild_id", "")
    channel_id = payload.get("channel_id", "")
    bot_token = payload.get("bot_token", "")
    if not guild_id or not channel_id:
        raise HTTPException(status_code=400, detail="guild_id and channel_id are required")
    room = room_manager.add_room(name, guild_id, channel_id, bot_token)
    return {"status": "ok", "room": room}

@app.put("/api/rooms/{room_id}", dependencies=[Depends(require_local_admin)])
async def room_update(room_id: str, payload: Dict[str, Any] = Body(...)):
    room = room_manager.update_room(room_id, payload)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"status": "ok", "room": room}

@app.delete("/api/rooms/{room_id}", dependencies=[Depends(require_local_admin)])
async def room_delete(room_id: str):
    await streamer.disconnect_room(room_id)
    ok = room_manager.delete_room(room_id)
    return {"status": "ok", "deleted": ok}

@app.post("/api/rooms/select")
async def room_select(payload: Dict[str, Any] = Body(...)):
    room_id = payload.get("id")
    selected = bool(payload.get("selected", True))
    room_manager.set_selected(room_id, selected)
    return {"status": "ok", "id": room_id, "selected": selected}

@app.post("/api/rooms/select-all")
async def room_select_all(payload: Dict[str, Any] = Body(...)):
    selected = bool(payload.get("selected", True))
    room_manager.select_all(selected)
    return {"status": "ok", "selected": selected}

@app.post("/api/rooms/{room_id}/connect")
async def room_connect(room_id: str):
    async with room_connections:
        ok = await streamer.connect_room(room_id)
        streamer.sync_rooms_status()
        return {"status": "ok" if ok else "failed", "room": browser_room(room_manager.get_room(room_id))}

@app.post("/api/rooms/{room_id}/disconnect")
async def room_disconnect(room_id: str):
    async with room_connections:
        await streamer.disconnect_room(room_id)
        streamer.sync_rooms_status()
        return {"status": "ok", "room": browser_room(room_manager.get_room(room_id))}

@app.post("/api/rooms/connect-all")
async def rooms_connect_all():
    async with room_connections:
        await streamer.connect_all_selected_rooms()
        streamer.sync_rooms_status()
        return {"status": "ok", "rooms": browser_rooms()}

@app.post("/api/rooms/disconnect-all")
async def rooms_disconnect_all():
    async with room_connections:
        await streamer.disconnect_all_rooms()
        streamer.sync_rooms_status()
        return {"status": "ok", "rooms": browser_rooms()}

# Background & Configuration
@app.get("/api/backgrounds")
async def get_backgrounds():
    exts = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif")
    files = []
    for ext in exts:
        for p in glob.glob(os.path.join(BACKGROUND_DIR, ext)):
            files.append(os.path.basename(p))
    return {"files": files, "current": config_manager.get("current_background")}

@app.post("/api/backgrounds/select", dependencies=[Depends(require_local_admin)])
async def select_background(payload: Dict[str, Any] = Body(...)):
    filename = payload.get("filename", "")
    file_path = os.path.join(BACKGROUND_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image does not exist in background folder")
    config_manager.set("current_background", filename)
    return {"status": "ok", "current_background": filename}

@app.get("/api/config")
async def get_config():
    return browser_config()

@app.post("/api/config", dependencies=[Depends(require_local_admin)])
async def update_config(payload: Dict[str, Any] = Body(...)):
    config_manager.update(payload)
    return {"status": "ok", "config": config_manager.load()}

def run_server(host: str = "127.0.0.1", port: int = 8765):
    uvicorn.run("server:app", host=host, port=port, log_level="info", reload=False)

if __name__ == "__main__":
    run_server()
