from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    video_path: Optional[str] = Field(
        default=None, description="Relative or absolute path to the fixed video"
    )
    avatar_id: Optional[str] = Field(
        default=None, description="Avatar ID from avatars_root (preprocessed assets)"
    )
    fps: Optional[int] = Field(default=None, description="Output FPS")
    width: Optional[int] = Field(default=None, description="Output width; 0 keeps source")
    height: Optional[int] = Field(default=None, description="Output height; 0 keeps source")
    pixel_fmt: Optional[str] = Field(default=None, description="rgb24|bgr24|rgba|bgra|nv12|nv21|i420|i422")
    sample_rate: Optional[int] = Field(default=None, description="Input audio sample rate")
    binary_frames: Optional[bool] = Field(
        default=None, description="Send video frames as binary WS payloads"
    )


class SessionCreateResponse(BaseModel):
    session_id: str
    ws_url: str


class WarmupRequest(BaseModel):
    video_path: Optional[str] = Field(
        default=None, description="Relative or absolute path to the fixed video"
    )
    avatar_id: Optional[str] = Field(
        default=None, description="Avatar ID from avatars_root (preprocessed assets)"
    )
    fps: Optional[int] = Field(default=None, description="Output FPS")
    width: Optional[int] = Field(default=None, description="Output width; 0 keeps source")
    height: Optional[int] = Field(default=None, description="Output height; 0 keeps source")
    pixel_fmt: Optional[str] = Field(default=None, description="rgb24|bgr24|rgba|bgra|nv12|nv21|i420|i422")
    sample_rate: Optional[int] = Field(default=None, description="Input audio sample rate")


class WarmupResponse(BaseModel):
    cache_key: str


class AudioMessage(BaseModel):
    type: Literal["audio"] = "audio"
    data: str
    sample_rate: int
    seq: Optional[int] = None
    is_final: bool = False


class FrameMessage(BaseModel):
    type: Literal["frame"] = "frame"
    data: str
    width: int
    height: int
    pixel_fmt: str
    timestamp_ms: int
    eof: bool = False


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str
