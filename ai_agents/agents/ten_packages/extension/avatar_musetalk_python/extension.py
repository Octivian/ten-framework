#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from __future__ import annotations

import asyncio
import base64
import json
import traceback
import time
from dataclasses import dataclass
from typing import Optional
import struct

import requests
import websockets

from ten_ai_base.config import BaseConfig
from ten_runtime import (
    AsyncExtension,
    AsyncTenEnv,
    AudioFrame,
    PixelFmt,
    VideoFrame,
)


@dataclass
class AvatarMuseTalkConfig(BaseConfig):
    service_base_url: str = "http://127.0.0.1:7800"
    video_path: str = ""
    avatar_id: str = ""
    output_width: int = 0
    output_height: int = 0
    output_fps: int = 25
    pixel_fmt: str = "rgb24"
    input_audio_sample_rate: int = 24000
    video_frame_name: str = "video_frame"
    min_chunk_ms: int = 200
    max_buffer_chunks: int = 200
    binary_frames: bool = True
    video_timestamp_offset_ms: int = 0
    audio_realtime_pacing: bool = True
    audio_pacing_scale: float = 1.0

    def validate_params(self) -> None:
        required_fields = {
            "service_base_url": self.service_base_url,
        }
        for field_name, value in required_fields.items():
            if not value or (isinstance(value, str) and value.strip() == ""):
                raise ValueError(
                    f"Required field is missing or empty: {field_name}"
                )
        if not (self.video_path and self.video_path.strip()) and not (
            self.avatar_id and self.avatar_id.strip()
        ):
            raise ValueError("Either video_path or avatar_id is required")


PIXEL_FMT_MAP = {
    "rgb24": PixelFmt.RGB24,
    "bgr24": PixelFmt.BGR24,
    "rgba": PixelFmt.RGBA,
    "bgra": PixelFmt.BGRA,
    "i420": PixelFmt.I420,
    "i422": PixelFmt.I422,
    "nv12": PixelFmt.NV12,
    "nv21": PixelFmt.NV21,
}

FRAME_MAGIC = b"AVF1"
FRAME_HEADER = struct.Struct("!4sBHHI")
CODE_TO_PIXEL_FMT = {
    1: "rgb24",
    2: "bgr24",
    3: "rgba",
    4: "bgra",
    5: "i420",
    6: "nv12",
    7: "nv21",
    8: "i422",
}


class AvatarMuseTalkExtension(AsyncExtension):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.config: Optional[AvatarMuseTalkConfig] = None
        self.ten_env: Optional[AsyncTenEnv] = None
        self._audio_queue: asyncio.Queue[tuple[bytes, int]] = asyncio.Queue()
        self._audio_buffer = bytearray()
        self._audio_buffer_start_ts_ms: Optional[int] = None
        self._sender_task: Optional[asyncio.Task] = None
        self._receiver_task: Optional[asyncio.Task] = None
        self._ws: Optional[websockets.ClientConnection] = None
        self._running = False
        self._audio_chunks = 0
        self._frame_chunks = 0
        self._last_audio_log = 0.0
        self._last_frame_log = 0.0
        self._last_send_log = 0.0
        self._audio_ts_base_ms: Optional[int] = None
        self._video_ts_last_ms: Optional[int] = None
        self._fps_window_start = time.monotonic()
        self._fps_window_frames = 0
        self._audio_send_start: Optional[float] = None
        self._audio_sent_seconds = 0.0
        self._audio_ts_start_ms: Optional[int] = None

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        self.ten_env = ten_env

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        try:
            self.config = await AvatarMuseTalkConfig.create_async(ten_env)
            self.config.validate_params()

            session_info = await asyncio.to_thread(self._create_session)
            ws_url = session_info["ws_url"]

            self._ws = await websockets.connect(ws_url, max_size=None)
            self._running = True

            self._sender_task = asyncio.create_task(self._send_audio_loop())
            self._receiver_task = asyncio.create_task(self._recv_frame_loop())

            ten_env.log_info(
                f"avatar-musetalk connected: session_id={session_info['session_id']}"
            )
        except Exception:
            ten_env.log_error(f"avatar-musetalk start failed: {traceback.format_exc()}")

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        self._running = False
        if self._sender_task:
            self._sender_task.cancel()
        if self._receiver_task:
            self._receiver_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def on_audio_frame(
        self, _ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        if self.config is None:
            return
        if self._audio_ts_base_ms is None:
            try:
                ts = audio_frame.get_timestamp()
                if ts > 0:
                    self._audio_ts_base_ms = ts
                    if self.ten_env:
                        self.ten_env.log_info(
                            f"avatar-musetalk audio ts base set: {ts}ms"
                        )
            except Exception:
                pass
        if not self._running:
            if self._audio_queue.qsize() >= self.config.max_buffer_chunks:
                return
            buf = audio_frame.get_buf()
            try:
                ts_ms = int(audio_frame.get_timestamp())
            except Exception:
                ts_ms = 0
            self._audio_queue.put_nowait((buf, ts_ms))
            return
        buf = audio_frame.get_buf()
        try:
            ts_ms = int(audio_frame.get_timestamp())
        except Exception:
            ts_ms = 0
        self._audio_queue.put_nowait((buf, ts_ms))
        self._audio_chunks += 1
        now = time.monotonic()
        if (
            self.ten_env
            and (now - self._last_audio_log) > 5
            and self._audio_chunks % 10 == 0
        ):
            self._last_audio_log = now
            self.ten_env.log_info(
                f"avatar-musetalk audio queued: chunks={self._audio_chunks}, bytes={len(buf)}"
            )

    def _create_session(self) -> dict:
        assert self.config is not None
        url = f"{self.config.service_base_url}/v1/sessions"
        payload = {
            "fps": self.config.output_fps,
            "width": self.config.output_width,
            "height": self.config.output_height,
            "pixel_fmt": self.config.pixel_fmt,
            "sample_rate": self.config.input_audio_sample_rate,
            "binary_frames": self.config.binary_frames,
        }
        if self.config.video_path:
            payload["video_path"] = self.config.video_path
        if self.config.avatar_id:
            payload["avatar_id"] = self.config.avatar_id
        # Session creation can be slow due to video preprocessing.
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        return resp.json()

    async def _send_audio_loop(self) -> None:
        if self._ws is None or self.config is None:
            return
        bytes_per_sample = 2
        min_chunk_ms = max(self.config.min_chunk_ms, 20)
        min_bytes = int(
            self.config.input_audio_sample_rate
            * bytes_per_sample
            * min_chunk_ms
            / 1000
        )
        while self._running:
            audio_buf, ts_ms = await self._audio_queue.get()
            if not audio_buf:
                continue
            if not self._audio_buffer and ts_ms > 0:
                self._audio_buffer_start_ts_ms = ts_ms
            self._audio_buffer.extend(audio_buf)
            while len(self._audio_buffer) >= min_bytes:
                chunk = bytes(self._audio_buffer[:min_bytes])
                del self._audio_buffer[:min_bytes]
                delay_pre = 0.0
                if self.config.audio_realtime_pacing:
                    if self._audio_send_start is None:
                        self._audio_send_start = time.monotonic()
                        self._audio_sent_seconds = 0.0
                        if self._audio_buffer_start_ts_ms is not None:
                            self._audio_ts_start_ms = self._audio_buffer_start_ts_ms
                    target_time = self._audio_send_start + self._audio_sent_seconds
                    if (
                        self._audio_ts_start_ms is not None
                        and self._audio_buffer_start_ts_ms is not None
                    ):
                        target_time = self._audio_send_start + (
                            (self._audio_buffer_start_ts_ms - self._audio_ts_start_ms)
                            / 1000.0
                        ) * max(self.config.audio_pacing_scale, 0.1)
                    now = time.monotonic()
                    if target_time > now:
                        delay_pre = target_time - now
                        await asyncio.sleep(delay_pre)
                message = {
                    "type": "audio",
                    "data": base64.b64encode(chunk).decode("utf-8"),
                    "sample_rate": self.config.input_audio_sample_rate,
                }
                try:
                    await self._ws.send(json.dumps(message))
                    now = time.monotonic()
                    duration = len(chunk) / (
                        self.config.input_audio_sample_rate * bytes_per_sample
                    )
                    duration *= max(self.config.audio_pacing_scale, 0.1)
                    self._audio_sent_seconds += duration
                    if self._audio_buffer_start_ts_ms is not None:
                        self._audio_buffer_start_ts_ms += int(duration * 1000)
                    if self.config.audio_realtime_pacing and delay_pre <= 0:
                        await asyncio.sleep(duration)
                    if self.ten_env and (now - self._last_send_log) > 5:
                        self._last_send_log = now
                        self.ten_env.log_info(
                            f"avatar-musetalk audio sent: bytes={len(chunk)}"
                        )
                except Exception:
                    if self.ten_env:
                        self.ten_env.log_error(
                            f"avatar-musetalk send failed: {traceback.format_exc()}"
                        )
                    return

    async def _recv_frame_loop(self) -> None:
        if self._ws is None or self.config is None:
            return
        while self._running:
            try:
                raw = await self._ws.recv()
            except Exception:
                if self.ten_env:
                    self.ten_env.log_error(
                        f"avatar-musetalk recv failed: {traceback.format_exc()}"
                    )
                break

            if isinstance(raw, (bytes, bytearray)):
                await self._handle_binary_frame(bytes(raw))
                continue

            try:
                message = json.loads(raw)
            except Exception:
                continue

            if message.get("type") == "frame":
                await self._handle_frame(message)
            elif message.get("type") == "error":
                if self.ten_env:
                    self.ten_env.log_error(
                        f"avatar-musetalk error: {message.get('message')}"
                    )

    async def _handle_frame(self, message: dict) -> None:
        if self.ten_env is None or self.config is None:
            return
        pixel_fmt = message.get("pixel_fmt", "rgb24").lower()
        fmt = PIXEL_FMT_MAP.get(pixel_fmt)
        if fmt is None:
            self.ten_env.log_warn(f"Unsupported pixel format: {pixel_fmt}")
            return

        data = base64.b64decode(message.get("data", ""))
        width = int(message.get("width", 0))
        height = int(message.get("height", 0))
        timestamp_ms = self._map_video_timestamp(
            int(message.get("timestamp_ms", 0))
        )

        frame = VideoFrame.create(self.config.video_frame_name)
        frame.alloc_buf(len(data))
        buf = frame.lock_buf()
        buf[:] = data
        frame.unlock_buf(buf)

        frame.set_width(width)
        frame.set_height(height)
        frame.set_pixel_fmt(fmt)
        frame.set_timestamp(timestamp_ms)

        await self.ten_env.send_video_frame(frame)
        self._frame_chunks += 1
        self._fps_window_frames += 1
        now = time.monotonic()
        if (now - self._fps_window_start) >= 5:
            fps = self._fps_window_frames / (now - self._fps_window_start)
            self._fps_window_start = now
            self._fps_window_frames = 0
            if self.ten_env:
                self.ten_env.log_info(
                    f"avatar-musetalk video fps: {fps:.2f}"
                )
        if (now - self._last_frame_log) > 5 and self._frame_chunks % 10 == 0:
            self._last_frame_log = now
            self.ten_env.log_info(
                "avatar-musetalk video frame sent: "
                f"frames={self._frame_chunks}, size={width}x{height}, fmt={pixel_fmt}"
            )

    async def _handle_binary_frame(self, raw: bytes) -> None:
        if self.ten_env is None or self.config is None:
            return
        if len(raw) < FRAME_HEADER.size:
            return
        magic, fmt_code, width, height, timestamp_ms = FRAME_HEADER.unpack(
            raw[: FRAME_HEADER.size]
        )
        if magic != FRAME_MAGIC:
            return
        pixel_fmt = CODE_TO_PIXEL_FMT.get(fmt_code)
        if pixel_fmt is None:
            self.ten_env.log_warn(f"Unsupported pixel format code: {fmt_code}")
            return
        fmt = PIXEL_FMT_MAP.get(pixel_fmt)
        if fmt is None:
            self.ten_env.log_warn(f"Unsupported pixel format: {pixel_fmt}")
            return

        data = raw[FRAME_HEADER.size :]
        frame = VideoFrame.create(self.config.video_frame_name)
        frame.alloc_buf(len(data))
        buf = frame.lock_buf()
        buf[:] = data
        frame.unlock_buf(buf)

        frame.set_width(width)
        frame.set_height(height)
        frame.set_pixel_fmt(fmt)
        frame.set_timestamp(self._map_video_timestamp(timestamp_ms))

        await self.ten_env.send_video_frame(frame)
        self._frame_chunks += 1
        self._fps_window_frames += 1
        now = time.monotonic()
        if (now - self._fps_window_start) >= 5:
            fps = self._fps_window_frames / (now - self._fps_window_start)
            self._fps_window_start = now
            self._fps_window_frames = 0
            if self.ten_env:
                self.ten_env.log_info(
                    f"avatar-musetalk video fps: {fps:.2f}"
                )
        if (now - self._last_frame_log) > 5 and self._frame_chunks % 10 == 0:
            self._last_frame_log = now
            self.ten_env.log_info(
                "avatar-musetalk video frame sent: "
                f"frames={self._frame_chunks}, size={width}x{height}, fmt={pixel_fmt}"
            )

    def _map_video_timestamp(self, timestamp_ms: int) -> int:
        if self.config is None:
            return timestamp_ms
        offset = self.config.video_timestamp_offset_ms
        if timestamp_ms <= 0:
            return timestamp_ms + offset
        if self._audio_ts_base_ms is None:
            return timestamp_ms + offset
        # Treat small timestamps as relative to session start.
        if timestamp_ms < 10_000_000_000:
            mapped = self._audio_ts_base_ms + timestamp_ms + offset
        else:
            mapped = timestamp_ms + offset
        if self._video_ts_last_ms is not None and mapped < self._video_ts_last_ms:
            mapped = self._video_ts_last_ms
        self._video_ts_last_ms = mapped
        return mapped
