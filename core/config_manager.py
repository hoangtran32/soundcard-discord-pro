import json
import os
from typing import Dict, Any

DEFAULT_CONFIG: Dict[str, Any] = {
    "bot_tokens": [],
    "global_token": "",
    "volume": 1.0,
    "repeat_mode": "off",  # "off", "one", "all"
    "shuffle": False,
    "bitrate": 128,
    "current_background": "cyberpunk_city.jpg",
    "bg_blur": 15,
    "bg_brightness": 65,
    "glass_opacity": 65,
    "accent_color": "#00f2fe",
    "ui_theme": "dark_translucent"
}

class ConfigManager:
    def __init__(self, filepath: str = "data/config.json"):
        self.filepath = filepath
        self._ensure_file()
        self.config = self.load()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = {**DEFAULT_CONFIG, **data}
                return merged
        except Exception as e:
            print(f"[ConfigManager] Error loading config: {e}")
            return DEFAULT_CONFIG.copy()

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Error saving config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save()

    def update(self, new_data: Dict[str, Any]):
        self.config.update(new_data)
        self.save()

config_manager = ConfigManager()
