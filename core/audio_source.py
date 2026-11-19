import asyncio
import io
import math
import os
import struct
import subprocess
import sys
import time
from typing import List, Optional, Callable
import discord
import numpy as np

# Discord voice constants
SAMPLE_RATE = 48000
CHANNELS = 2
FRAME_SIZE = 960  # 20ms at 48kHz
FRAME_BYTES = FRAME_SIZE * CHANNELS * 2  # 3840 bytes per 20ms frame

class DynamicBroadcasterAudioSource(discord.AudioSource):
    """
    Lightweight audio source plugged into a specific discord.VoiceClient.
    Reads frames from the central StreamDispatcher's queue.
    """
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self._is_finished = False

    def read(self) -> bytes:
        try:
            # Non-blocking get
            frame = self.queue.get_nowait()
            return frame
        except (asyncio.QueueEmpty, Exception):
            # Return silence frame to keep voice connection alive without jitter
            return b'\x00' * FRAME_BYTES

    def is_opus(self) -> bool:
        return False

    def cleanup(self):
        self._is_finished = True


class StreamDispatcher:
    """
    Streams audio using yt-dlp piped into FFmpeg or direct FFmpeg input.
    Decodes stream to 48kHz 16-bit stereo PCM.
    Pushes 20ms PCM frames to all subscribed voice channel queues synchronously.
    Computes visualizer frequency data and position.
    """
    def __init__(self, url_or_path: str, volume: float = 1.0, seek_seconds: float = 0.0, on_end: Optional[Callable] = None):
        self.url_or_path = url_or_path
        self.volume = max(0.0, min(volume, 2.0))
        self.seek_seconds = seek_seconds
        self.on_end = on_end

        self.process_ytdl: Optional[subprocess.Popen] = None
        self.process_ffmpeg: Optional[subprocess.Popen] = None
        self.running = False
        self.paused = False
        self.position_seconds = seek_seconds

        self.queues: List[asyncio.Queue] = []
        self.current_spectrum: List[int] = [0] * 16
        self.current_vu: float = 0.0

        self._task: Optional[asyncio.Task] = None

    def add_subscriber(self) -> DynamicBroadcasterAudioSource:
        q = asyncio.Queue(maxsize=50)
        self.queues.append(q)
        return DynamicBroadcasterAudioSource(q)

    def remove_subscriber(self, source: DynamicBroadcasterAudioSource):
        if source.queue in self.queues:
            self.queues.remove(source.queue)

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(vol, 2.0))

    def set_pause(self, paused: bool):
        self.paused = paused

    def start(self, loop: asyncio.AbstractEventLoop):
        self.running = True
        self._task = loop.create_task(self._stream_loop())

    async def _stream_loop(self):
        is_web_url = self.url_or_path.startswith(('http://', 'https://'))
        is_direct_audio_file = any(self.url_or_path.lower().endswith(ext) for ext in ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'))

        try:
            if is_web_url and not is_direct_audio_file:
                # Use yt-dlp piped into ffmpeg for YouTube / SoundCloud / Web streams
                ytdl_cmd = [
                    sys.executable, '-m', 'yt_dlp',
                    '--ignore-config',
                    '--js-runtimes', 'node',
                    '--no-playlist',
                    '-q', '--no-warnings',
                    '-f', 'bestaudio/best',
                    '-o', '-'
                ]
                if self.seek_seconds > 0:
                    ytdl_cmd.extend(['--postprocessor-args', f'ffmpeg:-ss {self.seek_seconds}'])

                ytdl_cmd.extend(['--', self.url_or_path])

                ffmpeg_cmd = [
                    'ffmpeg',
                    '-nostdin',
                    '-loglevel', 'warning',
                    '-i', 'pipe:0'
                ]
                if self.seek_seconds > 0:
                    ffmpeg_cmd.extend(['-ss', str(self.seek_seconds)])
                ffmpeg_cmd.extend([
                    '-f', 's16le',
                    '-ar', str(SAMPLE_RATE),
                    '-ac', str(CHANNELS),
                    'pipe:1'
                ])

                self.process_ytdl = subprocess.Popen(
                    ytdl_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=10 ** 7
                )
                self.process_ffmpeg = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=self.process_ytdl.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=FRAME_BYTES * 10
                )
                if self.process_ytdl.stdout:
                    self.process_ytdl.stdout.close()
            else:
                # Direct file or direct MP3 URL
                cmd = ['ffmpeg']
                if self.seek_seconds > 0:
                    cmd.extend(['-ss', str(self.seek_seconds)])
                if is_web_url:
                    cmd.extend(['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5'])
                cmd.extend([
                    '-nostdin',
                    '-loglevel', 'warning',
                    '-i', self.url_or_path,
                    '-f', 's16le',
                    '-ar', str(SAMPLE_RATE),
                    '-ac', str(CHANNELS),
                    'pipe:1'
                ])
                self.process_ffmpeg = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=FRAME_BYTES * 10
                )
        except Exception as e:
            print(f"[StreamDispatcher] Error starting audio pipeline: {e}")
            if self.on_end:
                if asyncio.iscoroutinefunction(self.on_end):
                    await self.on_end()
                else:
                    self.on_end()
            return

        frame_duration = 0.020  # 20ms
        next_frame_time = time.monotonic()

        while self.running and self.process_ffmpeg and self.process_ffmpeg.poll() is None:
            if self.paused:
                self._calc_silence_visualizer()
                await asyncio.sleep(0.02)
                continue

            # Read 1 frame of PCM (3840 bytes)
            raw_bytes = await asyncio.to_thread(self.process_ffmpeg.stdout.read, FRAME_BYTES)
            if not raw_bytes or len(raw_bytes) < FRAME_BYTES:
                break

            processed_bytes = self._process_pcm(raw_bytes)

            # Distribute to all voice channels
            for q in list(self.queues):
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(processed_bytes)
                except asyncio.QueueFull:
                    pass

            self.position_seconds += frame_duration
            next_frame_time += frame_duration
            delay = next_frame_time - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_frame_time = time.monotonic()

        self.running = False
        self._calc_silence_visualizer()
        self.stop()

        if self.on_end:
            try:
                if asyncio.iscoroutinefunction(self.on_end):
                    await self.on_end()
                else:
                    self.on_end()
            except Exception as ex:
                print(f"[StreamDispatcher] on_end callback error: {ex}")

    def _process_pcm(self, raw_bytes: bytes) -> bytes:
        try:
            pcm_data = np.frombuffer(raw_bytes, dtype=np.int16)
            if self.volume != 1.0:
                scaled = np.clip(pcm_data.astype(np.float32) * self.volume, -32768, 32767).astype(np.int16)
                out_bytes = scaled.tobytes()
                analysis_data = scaled
            else:
                out_bytes = raw_bytes
                analysis_data = pcm_data

            rms = np.sqrt(np.mean(analysis_data.astype(np.float32) ** 2))
            self.current_vu = min(1.0, float(rms / 16000.0))

            fft_vals = np.abs(np.fft.rfft(analysis_data[::2]))
            if len(fft_vals) >= 16:
                chunks = np.array_split(fft_vals[:256], 16)
                spectrum = [int(min(100, np.mean(c) / 100)) for c in chunks]
                self.current_spectrum = spectrum
            else:
                self.current_spectrum = [int(self.current_vu * 100)] * 16

            return out_bytes
        except Exception:
            return raw_bytes

    def _calc_silence_visualizer(self):
        self.current_vu = max(0.0, self.current_vu * 0.8)
        self.current_spectrum = [int(x * 0.75) for x in self.current_spectrum]

    def stop(self):
        self.running = False
        if self.process_ffmpeg:
            try:
                self.process_ffmpeg.kill()
            except Exception:
                pass
            self.process_ffmpeg = None
        if self.process_ytdl:
            try:
                self.process_ytdl.kill()
            except Exception:
                pass
            self.process_ytdl = None
        if self._task and not self._task.done() and self._task is not asyncio.current_task(loop=self._task.get_loop()):
            self._task.cancel()
