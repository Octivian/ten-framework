from __future__ import annotations

import base64
import asyncio
import struct
import uuid
from typing import Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from .config import ServiceConfig
from .musetalk_runner import MuseTalkRunner, SessionState
from .schemas import (
    AudioMessage,
    ErrorMessage,
    FrameMessage,
    SessionCreateRequest,
    SessionCreateResponse,
    WarmupRequest,
    WarmupResponse,
)


app = FastAPI()
config = ServiceConfig()
runner = MuseTalkRunner(config)

sessions: Dict[str, SessionState] = {}

FRAME_MAGIC = b"AVF1"
FRAME_HEADER = struct.Struct("!4sBHHI")
PIXEL_FMT_TO_CODE = {
    "rgb24": 1,
    "bgr24": 2,
    "rgba": 3,
    "bgra": 4,
    "i420": 5,
    "yuv420p": 5,
    "nv12": 6,
    "nv21": 7,
    "i422": 8,
}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/sessions", response_model=SessionCreateResponse)
async def create_session(payload: SessionCreateRequest) -> SessionCreateResponse:
    if not payload.video_path and not payload.avatar_id:
        raise HTTPException(
            status_code=400, detail="video_path or avatar_id is required"
        )

    session_id = uuid.uuid4().hex
    session = SessionState(
        session_id=session_id,
        video_path=payload.video_path or "",
        avatar_id=payload.avatar_id,
        fps=payload.fps or config.default_fps,
        width=payload.width or config.default_width,
        height=payload.height or config.default_height,
        pixel_fmt=(payload.pixel_fmt or config.default_pixel_fmt).lower(),
        sample_rate=payload.sample_rate or 24000,
        binary_frames=(
            payload.binary_frames
            if payload.binary_frames is not None
            else config.default_binary_frames
        ),
    )
    sessions[session_id] = session
    await runner.ensure_session(session)

    ws_base = config.public_base_url
    if ws_base.startswith("http://"):
        ws_base = "ws://" + ws_base[len("http://") :]
    elif ws_base.startswith("https://"):
        ws_base = "wss://" + ws_base[len("https://") :]

    ws_url = f"{ws_base}/v1/sessions/{session_id}/stream"
    return SessionCreateResponse(session_id=session_id, ws_url=ws_url)


@app.post("/v1/cache/warmup", response_model=WarmupResponse)
async def warmup_cache(payload: WarmupRequest) -> WarmupResponse:
    if not payload.video_path and not payload.avatar_id:
        raise HTTPException(
            status_code=400, detail="video_path or avatar_id is required"
        )

    cache_key = await runner.warmup_session(
        video_path=payload.video_path or "",
        avatar_id=payload.avatar_id,
        fps=payload.fps or config.default_fps,
        width=payload.width or config.default_width,
        height=payload.height or config.default_height,
        pixel_fmt=payload.pixel_fmt or config.default_pixel_fmt,
        sample_rate=payload.sample_rate or 24000,
    )
    return WarmupResponse(cache_key=cache_key)


@app.websocket("/v1/sessions/{session_id}/stream")
async def stream(session_id: str, websocket: WebSocket) -> None:
    await websocket.accept()

    session = sessions.get(session_id)
    if session is None:
        await websocket.send_text(
            ErrorMessage(message="session not found").model_dump_json()
        )
        await websocket.close()
        return

    async def _send_frames() -> None:
        while True:
            frame = await asyncio.to_thread(runner.pop_frame, session, 1.0)
            if frame is None:
                await asyncio.sleep(0.001)
                continue
            if session.binary_frames:
                fmt_code = PIXEL_FMT_TO_CODE.get(frame.pixel_fmt, 0)
                header = FRAME_HEADER.pack(
                    FRAME_MAGIC,
                    fmt_code,
                    frame.width,
                    frame.height,
                    frame.timestamp_ms,
                )
                await websocket.send_bytes(header + frame.data)
            else:
                payload = FrameMessage(
                    data=base64.b64encode(frame.data).decode("utf-8"),
                    width=frame.width,
                    height=frame.height,
                    pixel_fmt=frame.pixel_fmt,
                    timestamp_ms=frame.timestamp_ms,
                    eof=False,
                )
                await websocket.send_text(payload.model_dump_json())

    sender_task = None
    try:
        if runner.supports_streaming(session):
            sender_task = asyncio.create_task(_send_frames())

        while True:
            raw = await websocket.receive_text()
            try:
                message = AudioMessage.model_validate_json(raw)
            except Exception:
                await websocket.send_text(
                    ErrorMessage(message="invalid audio message").model_dump_json()
                )
                continue

            audio_bytes = base64.b64decode(message.data)
            if runner.supports_streaming(session):
                runner.enqueue_audio(session, audio_bytes)
                continue

            frames = await runner.render(audio_bytes, session)
            for frame in frames:
                payload = FrameMessage(
                    data=base64.b64encode(frame.data).decode("utf-8"),
                    width=frame.width,
                    height=frame.height,
                    pixel_fmt=frame.pixel_fmt,
                    timestamp_ms=frame.timestamp_ms,
                    eof=False,
                )
                await websocket.send_text(payload.model_dump_json())
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_text(
            ErrorMessage(message=f"stream error: {exc}").model_dump_json()
        )
        await websocket.close()
    finally:
        if sender_task is not None:
            sender_task.cancel()
        runner.stop_session(session)
