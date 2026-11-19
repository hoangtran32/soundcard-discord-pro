import asyncio
import random
import time
from typing import Dict, List, Optional, Any, Callable
import discord
from core.config_manager import config_manager
from core.playlist_manager import playlist_manager
from core.room_manager import room_manager
from core.audio_source import StreamDispatcher, DynamicBroadcasterAudioSource

class DiscordBotWorker:
    """Manages a single Discord Bot instance for voice connections."""
    def __init__(self, token: str, loop: asyncio.AbstractEventLoop):
        self.token = token.strip()
        self.loop = loop
        
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        
        self.client = discord.Client(intents=intents)
        self.ready = asyncio.Event()
        self.voice_clients: Dict[str, discord.VoiceClient] = {}  # channel_id -> VoiceClient
        self.active_sources: Dict[str, DynamicBroadcasterAudioSource] = {}  # channel_id -> Source
        self._bg_task: Optional[asyncio.Task] = None

        # Register event handlers
        @self.client.event
        async def on_ready():
            print(f"[DiscordBotWorker] Bot logged in as {self.client.user}!")
            self.ready.set()

        @self.client.event
        async def on_voice_state_update(member, before, after):
            if member == self.client.user and after.channel is None and before.channel:
                ch_id = str(before.channel.id)
                if ch_id in self.voice_clients:
                    del self.voice_clients[ch_id]
                if ch_id in self.active_sources:
                    del self.active_sources[ch_id]

    async def start(self):
        if self._bg_task and not self._bg_task.done():
            if self.ready.is_set():
                return True
        else:
            self._bg_task = self.loop.create_task(self._run_client())
        try:
            await asyncio.wait_for(self.ready.wait(), timeout=15.0)
            return True
        except Exception as e:
            print(f"[DiscordBotWorker] Login timed out or failed: {e}")
            return False

    async def _run_client(self):
        try:
            await self.client.start(self.token)
        except Exception as e:
            print(f"[DiscordBotWorker] Client error: {e}")
        finally:
            self.ready.clear()

    async def join_voice(self, guild_id: str, channel_id: str) -> Optional[discord.VoiceClient]:
        if not self.ready.is_set():
            ok = await self.start()
            if not ok:
                return None

        try:
            guild = self.client.get_guild(int(guild_id))
            if not guild:
                guild = await self.client.fetch_guild(int(guild_id))
            
            channel = guild.get_channel(int(channel_id))
            if not channel:
                channel = await self.client.fetch_channel(int(channel_id))

            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) or channel.guild.id != guild.id:
                print(f"[DiscordBotWorker] Channel {channel_id} is not a voice channel in the configured server.")
                return None

            # Check if bot already has a voice client in this guild
            vc = guild.voice_client
            if vc and vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
            else:
                try:
                    vc = await channel.connect(timeout=15.0, reconnect=True)
                except discord.ClientException:
                    # If already connected, fetch guild voice client
                    vc = guild.voice_client

            if vc and vc.is_connected() and vc.channel.id == channel.id:
                self.voice_clients[str(channel_id)] = vc
                return vc
        except Exception as e:
            print(f"[DiscordBotWorker] Error joining voice {channel_id}: {e}")
            # Check if despite error, bot is already in channel
            try:
                guild = self.client.get_guild(int(guild_id))
                vc = guild.voice_client if guild else None
                if vc and vc.is_connected() and vc.channel.id == int(channel_id):
                    self.voice_clients[str(channel_id)] = vc
                    return vc
            except Exception:
                pass
            return None

    async def leave_voice(self, channel_id: str):
        ch_id = str(channel_id)
        if ch_id in self.voice_clients:
            vc = self.voice_clients[ch_id]
            try:
                if vc.is_connected() and str(vc.channel.id) == ch_id:
                    await vc.disconnect(force=True)
            except Exception:
                pass
            self.voice_clients.pop(ch_id, None)
        self.active_sources.pop(ch_id, None)

    async def close(self):
        for vc in list(self.voice_clients.values()):
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
        self.voice_clients.clear()
        self.active_sources.clear()
        if not self.client.is_closed():
            await self.client.close()


class DiscordAudioStreamer:
    """Central SoundCard streamer managing bots, audio dispatcher, rooms, and playlist progression."""
    def __init__(self):
        self.bots: Dict[str, DiscordBotWorker] = {}
        self.dispatcher: Optional[StreamDispatcher] = None
        self.current_track: Optional[Dict[str, Any]] = None
        self.active_album: Optional[Dict[str, Any]] = None
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.connection_start_times: Dict[str, float] = {}

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def _get_bot_for_token(self, token: str) -> Optional[DiscordBotWorker]:
        if not token or not self.loop:
            return None
        token = token.strip()
        if token not in self.bots:
            self.bots[token] = DiscordBotWorker(token, self.loop)
        return self.bots[token]

    def sync_rooms_status(self):
        """Actively synchronizes room status with the bot's real Discord voice connection."""
        now = time.time()
        for r in room_manager.get_all():
            token = r.get("bot_token") or config_manager.get("global_token", "")
            if not token or token not in self.bots:
                if r.get("status") not in ("connecting", "disconnected"):
                    r["status"] = "disconnected"
                continue

            bot = self.bots[token]
            if not bot.client.is_ready():
                if r.get("status") == "connecting" and now - self.connection_start_times.get(r["id"], now) > 15:
                    r["status"] = "disconnected"
                continue

            try:
                guild = bot.client.get_guild(int(r["guild_id"]))
                vc = guild.voice_client if guild else None

                if vc and vc.is_connected() and str(vc.channel.id) == str(r["channel_id"]):
                    ping = int(vc.latency * 1000) if hasattr(vc, "latency") and vc.latency and vc.latency < 5 else 25
                    if self.is_playing and vc.is_playing():
                        r["status"] = "playing"
                    else:
                        r["status"] = "connected"
                    r["ping"] = ping
                    # Keep voice client reference up to date
                    bot.voice_clients[str(r["channel_id"])] = vc
                else:
                    if r.get("status") == "connecting":
                        if now - self.connection_start_times.get(r["id"], now) > 15:
                            r["status"] = "disconnected"
                    else:
                        r["status"] = "disconnected"
            except Exception:
                pass

    async def connect_room(self, room_id: str) -> bool:
        room = room_manager.get_room(room_id)
        if not room:
            return False

        token = room.get("bot_token") or config_manager.get("global_token", "")
        if not token:
            room_manager.set_status(room_id, "error - missing token")
            return False

        room_manager.set_status(room_id, "connecting")
        self.connection_start_times[room_id] = time.time()

        bot = self._get_bot_for_token(token)
        if not bot:
            room_manager.set_status(room_id, "error")
            return False

        vc = await bot.join_voice(room["guild_id"], room["channel_id"])
        
        # Brief yield to let voice handshake stabilize
        await asyncio.sleep(0.3)
        self.sync_rooms_status()

        if room.get("status") in ("connected", "playing") or (
            vc and vc.is_connected() and str(vc.channel.id) == str(room["channel_id"])
        ):
            ping = int(vc.latency * 1000) if vc and hasattr(vc, "latency") and vc.latency and vc.latency < 5 else 25
            room_manager.set_status(room_id, "connected", ping=ping)
            
            # If music is already playing, attach immediately
            if self.is_playing and self.dispatcher and self.dispatcher.running:
                self._attach_room_to_dispatcher(bot, room["channel_id"])
                room_manager.set_status(room_id, "playing")
            return True
        room_manager.set_status(room_id, "error")
        return False

    async def disconnect_room(self, room_id: str) -> bool:
        room = room_manager.get_room(room_id)
        if not room:
            return False

        token = room.get("bot_token") or config_manager.get("global_token", "")
        if token in self.bots:
            await self.bots[token].leave_voice(room["channel_id"])
        room_manager.set_status(room_id, "disconnected")
        self.sync_rooms_status()
        return True

    async def connect_all_selected_rooms(self):
        selected_rooms = room_manager.get_selected()
        for r in selected_rooms:
            await self.connect_room(r["id"])

    async def disconnect_all_rooms(self):
        for r in room_manager.get_all():
            await self.disconnect_room(r["id"])

    def _attach_room_to_dispatcher(self, bot: DiscordBotWorker, channel_id: str, guild_id: Optional[str] = None):
        ch_id = str(channel_id)
        vc = bot.voice_clients.get(ch_id)
        if not vc and guild_id:
            try:
                guild = bot.client.get_guild(int(guild_id))
                candidate = guild.voice_client if guild else None
                if candidate and candidate.is_connected() and str(candidate.channel.id) == ch_id:
                    vc = candidate
                    bot.voice_clients[ch_id] = candidate
            except Exception:
                pass

        if vc and vc.is_connected() and str(vc.channel.id) == ch_id:
            try:
                if vc.is_playing():
                    vc.stop()
                source = self.dispatcher.add_subscriber()
                bot.active_sources[ch_id] = source
                vc.play(source)
                print(f"[DiscordAudioStreamer] Attached audio stream to voice channel {channel_id}")
            except Exception as e:
                print(f"[DiscordAudioStreamer] Error attaching voice client {channel_id}: {e}")

    async def play_track(self, track: Dict[str, Any], seek_seconds: float = 0.0):
        if not self.loop:
            return

        # Stop previous dispatcher if any
        if self.dispatcher:
            self.dispatcher.stop()
            self.dispatcher = None

        self.current_track = track
        audio_url = track.get("url") or track.get("stream_url", "")
        volume = float(config_manager.get("volume", 1.0))
        
        try:
            safe_title = str(track.get('title', 'Unknown')).encode('ascii', errors='replace').decode('ascii')
            print(f"[DiscordAudioStreamer] Playing: {safe_title}")
        except Exception:
            pass

        # Create new stream dispatcher
        self.dispatcher = StreamDispatcher(
            url_or_path=audio_url,
            volume=volume,
            seek_seconds=seek_seconds,
            on_end=self._on_track_finished
        )
        self.dispatcher.start(self.loop)
        self.is_playing = True
        self.is_paused = False

        # Attach to all currently connected and selected voice channels
        selected_rooms = room_manager.get_selected()
        for r in selected_rooms:
            token = r.get("bot_token") or config_manager.get("global_token", "")
            if token in self.bots:
                bot = self.bots[token]
                ch_id = str(r["channel_id"])
                g_id = str(r.get("guild_id", ""))
                self._attach_room_to_dispatcher(bot, ch_id, g_id)
                room_manager.set_status(r["id"], "playing")

    async def _on_track_finished(self):
        self.is_playing = False
        repeat_mode = config_manager.get("repeat_mode", "off")
        
        if repeat_mode == "one" and self.current_track:
            await self.play_track(self.current_track)
            return

        await self.next_track()

    def playback_tracks(self):
        return self.active_album["tracks"] if self.active_album else playlist_manager.get_selected()

    async def next_track(self):
        selected_items = self.playback_tracks()
        if not selected_items:
            self.stop()
            return

        shuffle = config_manager.get("shuffle", False)
        repeat_mode = config_manager.get("repeat_mode", "off")

        if shuffle:
            next_item = random.choice(selected_items)
            await self.play_track(next_item)
            return

        curr_id = self.current_track.get("id") if self.current_track else None
        current_idx = -1
        for i, item in enumerate(selected_items):
            if item.get("id") == curr_id:
                current_idx = i
                break

        next_idx = current_idx + 1
        if next_idx >= len(selected_items):
            if repeat_mode == "all":
                next_idx = 0
            else:
                self.stop()
                return

        await self.play_track(selected_items[next_idx])

    async def prev_track(self):
        selected_items = self.playback_tracks()
        if not selected_items:
            self.stop()
            return

        curr_id = self.current_track.get("id") if self.current_track else None
        current_idx = 0
        for i, item in enumerate(selected_items):
            if item.get("id") == curr_id:
                current_idx = i
                break

        prev_idx = current_idx - 1
        if prev_idx < 0:
            prev_idx = len(selected_items) - 1

        await self.play_track(selected_items[prev_idx])

    def pause(self):
        if self.dispatcher:
            self.dispatcher.set_pause(True)
            self.is_paused = True

    def resume(self):
        if self.dispatcher:
            self.dispatcher.set_pause(False)
            self.is_paused = False

    def stop(self):
        if self.dispatcher:
            self.dispatcher.stop()
            self.dispatcher = None
        self.is_playing = False
        self.is_paused = False
        self.sync_rooms_status()

    async def seek(self, seconds: float):
        if self.current_track:
            await self.play_track(self.current_track, seek_seconds=seconds)

    def set_volume(self, volume: float):
        config_manager.set("volume", volume)
        if self.dispatcher:
            self.dispatcher.set_volume(volume)

    def get_state(self) -> Dict[str, Any]:
        self.sync_rooms_status()
        pos = self.dispatcher.position_seconds if self.dispatcher else 0.0
        vu = self.dispatcher.current_vu if self.dispatcher else 0.0
        spectrum = self.dispatcher.current_spectrum if self.dispatcher else [0] * 16
        album_preview = None
        if self.active_album:
            tracks = self.playback_tracks()
            current_id = self.current_track["id"] if self.current_track else None
            current_index = next((i for i, track in enumerate(tracks) if track["id"] == current_id), -1)
            upcoming = tracks[current_index + 1:current_index + 6]
            album_preview = {
                "name": self.active_album["name"],
                "remaining": len(tracks) - current_index - 1,
                "upcoming": [{"title": track["title"], "duration_str": track["duration_str"],
                              "duration": track["duration"]} for track in upcoming],
            }

        return {
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "position": round(pos, 1),
            "current_track": self.current_track,
            "album_queue": album_preview,
            "volume": config_manager.get("volume", 1.0),
            "repeat_mode": config_manager.get("repeat_mode", "off"),
            "shuffle": config_manager.get("shuffle", False),
            "vu_meter": round(vu, 3),
            "spectrum": spectrum,
            "connected_rooms_count": len([r for r in room_manager.get_all() if r.get("status") in ("connected", "playing")]),
            "selected_rooms_count": len(room_manager.get_selected()),
            "selected_tracks_count": len(playlist_manager.get_selected()),
            "total_tracks_count": len(playlist_manager.get_all())
        }

streamer = DiscordAudioStreamer()
