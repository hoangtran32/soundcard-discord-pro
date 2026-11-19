"""Start one authenticated SoundCard server with private runtime data."""

import json
import os
from pathlib import Path

import uvicorn


def read_data(filename, expected_type):
    try:
        data = json.loads((Path("data") / filename).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SystemExit(f"Provide a valid private data/{filename} file.") from None
    if not isinstance(data, expected_type):
        raise SystemExit(f"Invalid format in private data/{filename}.")
    return data


def main():
    try:
        password = Path("data/share-password.txt").read_text(encoding="utf-8").strip()
    except OSError:
        raise SystemExit("Provide private data/share-password.txt.") from None
    if len(password) < 24:
        raise SystemExit("Use a share password of at least 24 characters.")

    config = read_data("config.json", dict)
    rooms = read_data("rooms.json", list)
    if not rooms:
        raise SystemExit("Configure at least one Discord voice channel before deploying.")
    for room in rooms:
        if not isinstance(room, dict) or not all(
            str(room.get(field, "")).isdigit() for field in ("guild_id", "channel_id")
        ) or not (room.get("bot_token") or config.get("global_token")):
            raise SystemExit("Each Discord channel needs a server ID, channel ID, and bot token.")

    os.environ["SOUNDCARD_SHARE_PASSWORD"] = password
    uvicorn.run(
        "server:app", host="0.0.0.0", port=8000, workers=1,
        access_log=False, timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()
