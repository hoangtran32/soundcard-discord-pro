import json
import os
import uuid
import time
from typing import List, Dict, Any, Optional
from core.search_engine import search_engine, format_duration

class PlaylistManager:
    def __init__(self, filepath: str = "data/playlist.json"):
        self.filepath = filepath
        self._ensure_file()
        self.items: List[Dict[str, Any]] = self.load()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump([], f, indent=4, ensure_ascii=False)

    def load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[PlaylistManager] Error loading playlist: {e}")
            return []

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.items, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[PlaylistManager] Error saving playlist: {e}")

    async def add_url_or_query(self, query_or_url: str, platform: str = "youtube") -> List[Dict[str, Any]]:
        """Extract metadata for URL or search query using the multi-platform engine."""
        query_or_url = query_or_url.strip()
        if not query_or_url:
            return []

        results = await search_engine.search(query_or_url, platform=platform, limit=1)
        if not results:
            # Fallback basic item
            results = [{
                "id": str(uuid.uuid4())[:8],
                "title": query_or_url,
                "url": query_or_url,
                "duration": 0,
                "duration_str": "--:--",
                "thumbnail": "",
                "uploader": "Web Audio",
                "platform": platform
            }]

        for item in results:
            item["selected"] = True
            item["added_at"] = int(time.time())
            self.items.append(item)

        self.save()
        return results

    def add_item_direct(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Add a track from search result directly."""
        clean_item = {
            "id": item.get("id") or str(uuid.uuid4())[:8],
            "title": item.get("title", "Unknown Title"),
            "url": item.get("url", ""),
            "duration": item.get("duration", 0),
            "duration_str": item.get("duration_str", "--:--"),
            "thumbnail": item.get("thumbnail", ""),
            "uploader": item.get("uploader", "Audio"),
            "platform": item.get("platform", "youtube"),
            "selected": True,
            "added_at": int(time.time())
        }
        self.items.append(clean_item)
        self.save()
        return clean_item

    def add_local_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(file_path):
            return None
        filename = os.path.basename(file_path)
        name, _ = os.path.splitext(filename)
        item = {
            "id": str(uuid.uuid4())[:8],
            "title": name,
            "url": file_path,
            "duration": 0,
            "duration_str": "Local File",
            "thumbnail": "",
            "uploader": "Local Storage",
            "platform": "local",
            "selected": True,
            "added_at": int(time.time())
        }
        self.items.append(item)
        self.save()
        return item

    def delete_item(self, item_id: str) -> bool:
        original_len = len(self.items)
        self.items = [i for i in self.items if i.get("id") != item_id]
        if len(self.items) != original_len:
            self.save()
            return True
        return False

    def delete_multiple(self, item_ids: List[str]):
        id_set = set(item_ids)
        self.items = [i for i in self.items if i.get("id") not in id_set]
        self.save()

    def set_selected(self, item_id: str, selected: bool):
        for item in self.items:
            if item.get("id") == item_id:
                item["selected"] = selected
                break
        self.save()

    def select_all(self, selected: bool = True):
        for item in self.items:
            item["selected"] = selected
        self.save()

    def reorder(self, item_ids: List[str]):
        item_map = {item["id"]: item for item in self.items}
        reordered = []
        for i_id in item_ids:
            if i_id in item_map:
                reordered.append(item_map[i_id])
        for item in self.items:
            if item["id"] not in item_ids:
                reordered.append(item)
        self.items = reordered
        self.save()

    def get_selected(self) -> List[Dict[str, Any]]:
        return [i for i in self.items if i.get("selected", False)]

    def get_all(self) -> List[Dict[str, Any]]:
        return self.items

    def clear(self):
        self.items = []
        self.save()

playlist_manager = PlaylistManager(
    "data/shared-playlist.json" if "SOUNDCARD_SHARE_PASSWORD" in os.environ else "data/playlist.json"
)
