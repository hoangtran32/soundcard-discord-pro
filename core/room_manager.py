import json
import os
import uuid
import time
from typing import List, Dict, Any, Optional

class RoomManager:
    def __init__(self, filepath: str = "data/rooms.json"):
        self.filepath = filepath
        self._ensure_file()
        self.rooms: List[Dict[str, Any]] = self.load()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            # Include default sample or empty
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump([], f, indent=4, ensure_ascii=False)

    def load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                rooms = json.load(f)
                # Reset runtime connection status on startup
                for r in rooms:
                    r["status"] = "disconnected"
                    r["ping"] = 0
                return rooms
        except Exception as e:
            print(f"[RoomManager] Error loading rooms: {e}")
            return []

    def save(self):
        try:
            # We don't necessarily want to persist temporary status as connected
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.rooms, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[RoomManager] Error saving rooms: {e}")

    def add_room(self, name: str, guild_id: str, channel_id: str, bot_token: str = "") -> Dict[str, Any]:
        room_id = str(uuid.uuid4())[:8]
        room = {
            "id": room_id,
            "name": name.strip() or f"Voice Room {channel_id[-4:]}",
            "guild_id": str(guild_id).strip(),
            "channel_id": str(channel_id).strip(),
            "bot_token": bot_token.strip(),
            "selected": True,  # Default selected for playback
            "status": "disconnected",
            "ping": 0,
            "created_at": int(time.time())
        }
        self.rooms.append(room)
        self.save()
        return room

    def update_room(self, room_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for r in self.rooms:
            if r["id"] == room_id:
                r.update(data)
                self.save()
                return r
        return None

    def delete_room(self, room_id: str) -> bool:
        original_len = len(self.rooms)
        self.rooms = [r for r in self.rooms if r["id"] != room_id]
        if len(self.rooms) != original_len:
            self.save()
            return True
        return False

    def set_selected(self, room_id: str, selected: bool):
        for r in self.rooms:
            if r["id"] == room_id:
                r["selected"] = selected
                break
        self.save()

    def select_all(self, selected: bool = True):
        for r in self.rooms:
            r["selected"] = selected
        self.save()

    def set_status(self, room_id: str, status: str, ping: int = 0):
        for r in self.rooms:
            if r["id"] == room_id:
                r["status"] = status
                r["ping"] = ping
                break

    def get_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        for r in self.rooms:
            if r["id"] == room_id:
                return r
        return None

    def get_selected(self) -> List[Dict[str, Any]]:
        return [r for r in self.rooms if r.get("selected", False)]

    def get_all(self) -> List[Dict[str, Any]]:
        return self.rooms

room_manager = RoomManager()
