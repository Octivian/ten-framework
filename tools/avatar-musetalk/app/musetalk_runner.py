from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
import pickle
import glob
from pathlib import Path
from typing import Dict, List, Optional
from types import SimpleNamespace
import types
import threading
import queue
import time

import numpy as np
import torch
import cv2
import librosa
import resampy

from .config import ServiceConfig
from .video_cache import VideoCache, VideoInfo


@dataclass
class SessionState:
    session_id: str
    video_path: str
    avatar_id: str | None
    fps: int
    width: int
    height: int
    pixel_fmt: str
    sample_rate: int
    binary_frames: bool = False
    cache_key: str | None = None
    backend: str | None = None
    backend_state: object | None = None


@dataclass
class FramePayload:
    width: int
    height: int
    pixel_fmt: str
    timestamp_ms: int
    data: bytes


@dataclass
class AvatarMaterials:
    frame_list_cycle: List[np.ndarray]
    coord_list_cycle: List[tuple]
    input_latent_list_cycle: List[torch.Tensor]
    mask_list_cycle: List[np.ndarray]
    mask_coords_list_cycle: List[tuple]


@dataclass
class LiveTalkingState:
    musereal: object
    quit_event: threading.Event
    loop: asyncio.AbstractEventLoop
    loop_thread: threading.Thread
    render_thread: threading.Thread
    video_queue: queue.Queue
    audio_buffer: np.ndarray
    frame_index: int
    fps: int
    chunk_size: int
    audio_pacing_start: float | None
    audio_pacing_samples: int


class MuseTalkRunner:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.cache_dir = Path(self.config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.video_cache = VideoCache(str(self.cache_dir / "frames"))
        self._materials: Dict[str, AvatarMaterials] = {}
        self._frame_index: Dict[str, int] = {}
        self._avatar_cache: Dict[str, AvatarMaterials] = {}
        self._livetalking_sessions: Dict[str, LiveTalkingState] = {}
        self._livetalking_model: object | None = None
        self._livetalking_avatars: Dict[str, object] = {}
        self._livetalking_lock = threading.Lock()
        self._livetalking_ready = False

        self.backend = self.config.backend.lower()
        if self.backend == "livetalking":
            self._init_livetalking()
        else:
            self._init_musetalk()

    def _init_musetalk(self) -> None:
        musetalk_dir = Path(self.config.musetalk_dir).resolve()
        if not musetalk_dir.exists():
            raise FileNotFoundError(f"MuseTalk repo not found: {musetalk_dir}")

        sys.path.insert(0, str(musetalk_dir))

        # MuseTalk uses relative paths for model weights; set cwd to repo.
        self._original_cwd = os.getcwd()
        os.chdir(str(musetalk_dir))

        from musetalk.utils.utils import load_all_model
        from musetalk.utils.audio_processor import AudioProcessor
        from musetalk.utils.face_parsing import FaceParsing
        from transformers import WhisperModel
        from musetalk.whisper.audio2feature import Audio2Feature

        self.device = torch.device(
            f"cuda:{self.config.gpu_id}" if torch.cuda.is_available() else "cpu"
        )
        self.vae, self.unet, self.pe = load_all_model(
            unet_model_path=self.config.unet_model_path,
            vae_type=self.config.vae_type,
            unet_config=self.config.unet_config,
            device=self.device,
        )
        self.timesteps = torch.tensor([0], device=self.device)

        if self.config.use_float16 and self.device.type == "cuda":
            self.pe = self.pe.half().to(self.device)
            self.vae.vae = self.vae.vae.half().to(self.device)
            self.unet.model = self.unet.model.half().to(self.device)
            self.weight_dtype = self.unet.model.dtype
        else:
            self.pe = self.pe.to(self.device)
            self.vae.vae = self.vae.vae.to(self.device)
            self.unet.model = self.unet.model.to(self.device)
            self.weight_dtype = self.unet.model.dtype

        self.audio_feature_backend = self.config.audio_feature_backend.lower()
        self.audio2feature = None
        self.audio_processor = None
        self.whisper = None
        if self.audio_feature_backend == "audio2feature":
            self.audio2feature = Audio2Feature(
                model_path=self.config.whisper_tiny_path
            )
        else:
            self.audio_processor = AudioProcessor(
                feature_extractor_path=self.config.whisper_dir
            )
            self.whisper = WhisperModel.from_pretrained(self.config.whisper_dir)
            self.whisper = self.whisper.to(device=self.device, dtype=self.weight_dtype)
            self.whisper.eval()
            self.whisper.requires_grad_(False)

        self.fp = FaceParsing(
            left_cheek_width=self.config.left_cheek_width,
            right_cheek_width=self.config.right_cheek_width,
        )

        from musetalk.utils.preprocessing import coord_placeholder

        self.coord_placeholder = coord_placeholder

        # Restore cwd for service operations; MuseTalk modules already loaded.
        os.chdir(self._original_cwd)

    def _init_livetalking(self) -> None:
        livetalking_src = Path(self.config.livetalking_src).resolve()
        if not livetalking_src.exists():
            raise FileNotFoundError(
                f"LiveTalking src not found: {livetalking_src}"
            )
        musetalk_dir = Path(self.config.musetalk_dir).resolve()
        if not musetalk_dir.exists():
            raise FileNotFoundError(f"MuseTalk repo not found: {musetalk_dir}")

        # Ensure both live_digital_human and musetalk are importable.
        sys.path.insert(0, str(livetalking_src))
        sys.path.insert(0, str(musetalk_dir))

        # Avoid executing live_digital_human/__init__.py (imports aiortc).
        pkg = types.ModuleType("live_digital_human")
        pkg.__path__ = [str(livetalking_src / "live_digital_human")]
        sys.modules["live_digital_human"] = pkg

        from live_digital_human.musereal import (  # type: ignore
            MuseReal,
            load_model,
            load_avatar,
            warm_up,
        )
        # Use thread-safe queues for in-process streaming to avoid mp.Queue
        # closing issues in threaded FastAPI workers.
        try:
            from live_digital_human import musereal as _musereal  # type: ignore
            from live_digital_human import baseasr as _baseasr  # type: ignore
            _musereal.mp.Queue = queue.Queue  # type: ignore[attr-defined]
            _baseasr.mp.Queue = queue.Queue  # type: ignore[attr-defined]
        except Exception:
            # Best-effort: fallback to default mp.Queue if patching fails.
            pass

        self._livetalking_MuseReal = MuseReal
        self._livetalking_load_model = load_model
        self._livetalking_load_avatar = load_avatar
        self._livetalking_warm_up = warm_up
        self._livetalking_ready = True

    @contextlib.contextmanager
    def _chdir(self, path: Path) -> None:
        original = os.getcwd()
        os.chdir(str(path))
        try:
            yield
        finally:
            os.chdir(original)

    def _ensure_livetalking_model(self) -> None:
        if not self._livetalking_ready:
            raise RuntimeError("LiveTalking backend is not initialized")
        if self._livetalking_model is not None:
            return
        with self._livetalking_lock:
            if self._livetalking_model is not None:
                return
            root = Path(self.config.livetalking_root).resolve()
            with self._chdir(root):
                self._livetalking_model = self._livetalking_load_model()
                self._livetalking_warm_up(
                    self.config.livetalking_batch_size, self._livetalking_model
                )

    def _get_livetalking_avatar(self, avatar_id: str) -> object:
        cached = self._livetalking_avatars.get(avatar_id)
        if cached is not None:
            return cached
        root = Path(self.config.livetalking_root).resolve()
        with self._chdir(root):
            avatar = self._livetalking_load_avatar(avatar_id)
        self._livetalking_avatars[avatar_id] = avatar
        return avatar

    async def ensure_session(self, session: SessionState) -> None:
        if self.backend == "livetalking":
            await asyncio.to_thread(self._ensure_livetalking_session, session)
            return

        if session.session_id in self._materials:
            return

        if session.avatar_id:
            materials = await asyncio.to_thread(
                self._load_avatar_materials, session.avatar_id
            )
            self._materials[session.session_id] = materials
            self._frame_index[session.session_id] = 0
            return

        resolved = self._resolve_video_path(session.video_path)
        session.cache_key = self._build_cache_key(session, resolved)

        cached = await asyncio.to_thread(
            self._load_cached_materials, session.cache_key
        )
        if cached is not None:
            self._materials[session.session_id] = cached
            self._frame_index[session.session_id] = 0
            return

        await asyncio.to_thread(self._prepare_session, session, resolved)

    async def warmup_session(
        self,
        video_path: str,
        avatar_id: str | None,
        fps: int,
        width: int,
        height: int,
        pixel_fmt: str,
        sample_rate: int,
    ) -> str:
        if self.backend == "livetalking":
            session = SessionState(
                session_id=f"warmup-{os.getpid()}-{int(asyncio.get_running_loop().time()*1000)}",
                video_path=video_path,
                avatar_id=avatar_id,
                fps=fps,
                width=width,
                height=height,
                pixel_fmt=pixel_fmt,
                sample_rate=sample_rate,
                backend="livetalking",
            )
            await asyncio.to_thread(self._ensure_livetalking_session, session)
            # Immediately stop warmup session to free resources.
            await asyncio.to_thread(self._stop_livetalking_session, session)
            return ""

        session = SessionState(
            session_id=f"warmup-{os.getpid()}-{int(asyncio.get_running_loop().time()*1000)}",
            video_path=video_path,
            avatar_id=avatar_id,
            fps=fps,
            width=width,
            height=height,
            pixel_fmt=pixel_fmt,
            sample_rate=sample_rate,
        )
        await self.ensure_session(session)
        key = session.cache_key or ""
        # drop in-memory cache for warmup-only runs
        self._materials.pop(session.session_id, None)
        self._frame_index.pop(session.session_id, None)
        return key

    def supports_streaming(self, session: SessionState) -> bool:
        return self.backend == "livetalking"

    def enqueue_audio(self, session: SessionState, audio_pcm: bytes) -> None:
        if self.backend != "livetalking":
            return
        self._enqueue_livetalking_audio(session, audio_pcm)

    def pop_frame(
        self, session: SessionState, timeout: float = 1.0
    ) -> Optional[FramePayload]:
        if self.backend != "livetalking":
            return None
        return self._pop_livetalking_frame(session, timeout)

    def stop_session(self, session: SessionState) -> None:
        if self.backend != "livetalking":
            return
        self._stop_livetalking_session(session)

    def _prepare_session(self, session: SessionState, resolved: str) -> None:
        video_info = self.video_cache.prepare(resolved)

        if session.fps <= 0:
            session.fps = video_info.fps
        if session.width <= 0:
            session.width = video_info.width
        if session.height <= 0:
            session.height = video_info.height

        materials = self._prepare_avatar_materials(video_info)
        self._materials[session.session_id] = materials
        self._frame_index[session.session_id] = 0
        if session.cache_key:
            self._save_cached_materials(
                session.cache_key, resolved, session, materials
            )

    def _resolve_video_path(self, video_path: str) -> str:
        path = Path(video_path)
        if path.is_absolute():
            return str(path)
        return str(Path(self.config.video_root) / video_path)

    def _load_avatar_materials(self, avatar_id: str) -> AvatarMaterials:
        cached = self._avatar_cache.get(avatar_id)
        if cached is not None:
            return cached

        avatar_path = Path(self.config.avatars_root) / avatar_id
        if not avatar_path.exists():
            raise FileNotFoundError(f"Avatar not found: {avatar_path}")

        full_imgs_path = avatar_path / "full_imgs"
        coords_path = avatar_path / "coords.pkl"
        latents_path = avatar_path / "latents.pt"
        mask_out_path = avatar_path / "mask"
        mask_coords_path = avatar_path / "mask_coords.pkl"

        input_latent_list_cycle = torch.load(latents_path)
        with coords_path.open("rb") as handle:
            coord_list_cycle = pickle.load(handle)

        img_glob = str(full_imgs_path / "*.[jpJP][pnPN]*[gG]")
        input_img_list = sorted(
            glob.glob(img_glob),
            key=lambda p: int(Path(p).stem),
        )
        frame_list_cycle = self._read_images(input_img_list)

        with mask_coords_path.open("rb") as handle:
            mask_coords_list_cycle = pickle.load(handle)

        mask_glob = str(mask_out_path / "*.[jpJP][pnPN]*[gG]")
        input_mask_list = sorted(
            glob.glob(mask_glob),
            key=lambda p: int(Path(p).stem),
        )
        mask_list_cycle = self._read_images(input_mask_list)

        materials = AvatarMaterials(
            frame_list_cycle=frame_list_cycle,
            coord_list_cycle=coord_list_cycle,
            input_latent_list_cycle=input_latent_list_cycle,
            mask_list_cycle=mask_list_cycle,
            mask_coords_list_cycle=mask_coords_list_cycle,
        )
        self._avatar_cache[avatar_id] = materials
        return materials

    @staticmethod
    def _read_images(paths: List[str]) -> List[np.ndarray]:
        frames: List[np.ndarray] = []
        for img_path in paths:
            frame = cv2.imread(img_path)
            if frame is None:
                raise FileNotFoundError(f"Failed to read image: {img_path}")
            frames.append(frame)
        return frames

    def _build_cache_key(self, session: SessionState, resolved: str) -> str:
        stat = Path(resolved).stat()
        payload = {
            "video_path": resolved,
            "video_mtime": int(stat.st_mtime),
            "video_size": stat.st_size,
            "fps": session.fps,
            "width": session.width,
            "height": session.height,
            "pixel_fmt": session.pixel_fmt,
            "sample_rate": session.sample_rate,
            "bbox_shift": self.config.bbox_shift,
            "extra_margin": self.config.extra_margin,
            "parsing_mode": self.config.parsing_mode,
            "left_cheek_width": self.config.left_cheek_width,
            "right_cheek_width": self.config.right_cheek_width,
            "version": self.config.version,
            "unet_model_path": self.config.unet_model_path,
            "unet_config": self.config.unet_config,
            "vae_type": self.config.vae_type,
            "whisper_dir": self.config.whisper_dir,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _cache_paths(self, key: str) -> tuple[Path, Path, Path]:
        base = self.cache_dir / key
        return base, base / "materials.pt", base / "meta.json"

    def _save_cached_materials(
        self,
        key: str,
        resolved: str,
        session: SessionState,
        materials: AvatarMaterials,
    ) -> None:
        base, materials_path, meta_path = self._cache_paths(key)
        base.mkdir(parents=True, exist_ok=True)

        payload = {
            "frame_list_cycle": materials.frame_list_cycle,
            "coord_list_cycle": materials.coord_list_cycle,
            "input_latent_list_cycle": [
                t.detach().cpu() for t in materials.input_latent_list_cycle
            ],
            "mask_list_cycle": materials.mask_list_cycle,
            "mask_coords_list_cycle": materials.mask_coords_list_cycle,
        }
        tmp_path = materials_path.with_suffix(".pt.tmp")
        torch.save(payload, tmp_path)
        tmp_path.replace(materials_path)

        meta = {
            "schema_version": 1,
            "video_path": resolved,
            "fps": session.fps,
            "width": session.width,
            "height": session.height,
            "pixel_fmt": session.pixel_fmt,
            "sample_rate": session.sample_rate,
            "config": {
                "bbox_shift": self.config.bbox_shift,
                "extra_margin": self.config.extra_margin,
                "parsing_mode": self.config.parsing_mode,
                "left_cheek_width": self.config.left_cheek_width,
                "right_cheek_width": self.config.right_cheek_width,
                "version": self.config.version,
                "unet_model_path": self.config.unet_model_path,
                "unet_config": self.config.unet_config,
                "vae_type": self.config.vae_type,
                "whisper_dir": self.config.whisper_dir,
            },
        }
        tmp_meta = meta_path.with_suffix(".json.tmp")
        tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        tmp_meta.replace(meta_path)

    def _load_cached_materials(self, key: str) -> AvatarMaterials | None:
        _, materials_path, _ = self._cache_paths(key)
        if not materials_path.exists():
            return None
        try:
            payload = torch.load(materials_path, map_location="cpu")
            return AvatarMaterials(
                frame_list_cycle=payload["frame_list_cycle"],
                coord_list_cycle=payload["coord_list_cycle"],
                input_latent_list_cycle=payload["input_latent_list_cycle"],
                mask_list_cycle=payload["mask_list_cycle"],
                mask_coords_list_cycle=payload["mask_coords_list_cycle"],
            )
        except Exception:
            return None

    def _prepare_avatar_materials(self, video_info: VideoInfo) -> AvatarMaterials:
        from musetalk.utils.preprocessing import get_landmark_and_bbox
        from musetalk.utils.blending import get_image_prepare_material

        coord_list, frame_list = get_landmark_and_bbox(
            video_info.image_paths, self.config.bbox_shift
        )

        input_latent_list: List[torch.Tensor] = []
        for bbox, frame in zip(coord_list, frame_list):
            if bbox == self.coord_placeholder:
                continue
            x1, y1, x2, y2 = bbox
            if self.config.version == "v15":
                y2 = min(y2 + self.config.extra_margin, frame.shape[0])
            crop_frame = frame[y1:y2, x1:x2]
            crop_frame = cv2.resize(crop_frame, (256, 256), interpolation=cv2.INTER_LANCZOS4)
            latents = self.vae.get_latents_for_unet(crop_frame)
            input_latent_list.append(latents)

        if not input_latent_list:
            raise RuntimeError("no valid face detected in video frames")

        frame_list_cycle = frame_list + frame_list[::-1]
        coord_list_cycle = coord_list + coord_list[::-1]
        input_latent_list_cycle = input_latent_list + input_latent_list[::-1]

        mask_list_cycle: List[np.ndarray] = []
        mask_coords_list_cycle: List[tuple] = []
        for bbox, frame in zip(coord_list_cycle, frame_list_cycle):
            if bbox == self.coord_placeholder:
                mask_list_cycle.append(np.zeros((1, 1), dtype=np.uint8))
                mask_coords_list_cycle.append((0, 0, 0, 0))
                continue
            x1, y1, x2, y2 = bbox
            mode = self.config.parsing_mode
            mask, crop_box = get_image_prepare_material(
                frame,
                [x1, y1, x2, y2],
                fp=self.fp,
                mode=mode,
            )
            mask_list_cycle.append(mask)
            mask_coords_list_cycle.append(crop_box)

        return AvatarMaterials(
            frame_list_cycle=frame_list_cycle,
            coord_list_cycle=coord_list_cycle,
            input_latent_list_cycle=input_latent_list_cycle,
            mask_list_cycle=mask_list_cycle,
            mask_coords_list_cycle=mask_coords_list_cycle,
        )

    async def render(self, audio_pcm: bytes, session: SessionState) -> List[FramePayload]:
        if self.backend == "livetalking":
            # LiveTalking backend streams frames continuously.
            self._enqueue_livetalking_audio(session, audio_pcm)
            return []
        return await asyncio.to_thread(self._render_sync, audio_pcm, session)

    def _render_sync(self, audio_pcm: bytes, session: SessionState) -> List[FramePayload]:
        materials = self._materials.get(session.session_id)
        if materials is None:
            raise RuntimeError("session not prepared")

        from musetalk.utils.utils import datagen
        from musetalk.utils.blending import get_image_blending

        if self.audio_feature_backend == "audio2feature":
            audio_np = np.frombuffer(audio_pcm, dtype=np.int16).astype(np.float32)
            if audio_np.size == 0:
                return []
            audio_np /= 32768.0
            if session.sample_rate != self.config.audio_resample_rate:
                audio_np = librosa.resample(
                    audio_np,
                    orig_sr=session.sample_rate,
                    target_sr=self.config.audio_resample_rate,
                )
            if self.audio2feature is None:
                raise RuntimeError("audio2feature is not initialized")
            whisper_feature = self.audio2feature.audio2feat(audio_np)
            whisper_chunks = self.audio2feature.feature2chunks(
                feature_array=whisper_feature,
                fps=session.fps,
                audio_feat_length=[
                    self.config.audio_feat_left,
                    self.config.audio_feat_right,
                ],
            )
            whisper_chunks = [torch.from_numpy(chunk) for chunk in whisper_chunks]
        else:
            wav_path = self._write_wav(audio_pcm, session.sample_rate)
            try:
                whisper_input_features, librosa_length = (
                    self.audio_processor.get_audio_feature(
                        wav_path, weight_dtype=self.weight_dtype
                    )
                )
                if whisper_input_features is None:
                    return []
                whisper_chunks = self.audio_processor.get_whisper_chunk(
                    whisper_input_features,
                    self.device,
                    self.weight_dtype,
                    self.whisper,
                    librosa_length,
                    fps=session.fps,
                )
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

        gen = datagen(
            whisper_chunks,
            materials.input_latent_list_cycle,
            batch_size=self.config.batch_size,
            device=self.device,
        )
        results: List[FramePayload] = []
        frame_idx = self._frame_index.get(session.session_id, 0)

        for whisper_batch, latent_batch in gen:
            audio_feature_batch = self.pe(whisper_batch.to(self.device))
            latent_batch = latent_batch.to(device=self.device, dtype=self.unet.model.dtype)
            pred_latents = self.unet.model(
                latent_batch,
                self.timesteps,
                encoder_hidden_states=audio_feature_batch,
            ).sample
            pred_latents = pred_latents.to(device=self.device, dtype=self.vae.vae.dtype)
            recon = self.vae.decode_latents(pred_latents)

            for res_frame in recon:
                idx = frame_idx % len(materials.frame_list_cycle)
                bbox = materials.coord_list_cycle[idx]
                ori_frame = materials.frame_list_cycle[idx]

                if bbox == self.coord_placeholder:
                    combined = ori_frame
                else:
                    x1, y1, x2, y2 = bbox
                    res_frame = cv2.resize(res_frame.astype(np.uint8), (x2 - x1, y2 - y1))
                    mask = materials.mask_list_cycle[idx]
                    mask_crop_box = materials.mask_coords_list_cycle[idx]
                    combined = get_image_blending(
                        ori_frame, res_frame, bbox, mask, mask_crop_box
                    )

                payload = self._frame_to_payload(combined, session, frame_idx)
                results.append(payload)
                frame_idx += 1

        self._frame_index[session.session_id] = frame_idx
        return results

    def _write_wav(self, audio_pcm: bytes, sample_rate: int) -> str:
        import wave

        fd, path = tempfile.mkstemp(suffix=".wav", prefix="musetalk_")
        os.close(fd)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_pcm)
        return path

    def _frame_to_payload(self, frame: np.ndarray, session: SessionState, frame_idx: int) -> FramePayload:
        height, width = frame.shape[:2]
        pixel_fmt = session.pixel_fmt.lower()

        if pixel_fmt == "rgb24":
            data = frame[:, :, ::-1].tobytes()
        elif pixel_fmt == "bgr24":
            data = frame.tobytes()
        elif pixel_fmt == "rgba":
            rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            data = rgba.tobytes()
        elif pixel_fmt == "bgra":
            bgra = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            data = bgra.tobytes()
        elif pixel_fmt in {"i420", "yuv420p"}:
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            data = yuv.tobytes()
            pixel_fmt = "i420"
        else:
            data = frame.tobytes()
            pixel_fmt = "bgr24"

        timestamp_ms = int((frame_idx / max(session.fps, 1)) * 1000)
        return FramePayload(
            width=width,
            height=height,
            pixel_fmt=pixel_fmt,
            timestamp_ms=timestamp_ms,
            data=data,
        )

    def _ensure_livetalking_session(self, session: SessionState) -> None:
        if session.session_id in self._livetalking_sessions:
            session.backend_state = self._livetalking_sessions[session.session_id]
            session.backend = "livetalking"
            return
        if not session.avatar_id:
            raise ValueError("avatar_id is required for LiveTalking backend")

        self._ensure_livetalking_model()
        avatar = self._get_livetalking_avatar(session.avatar_id)

        fps = session.fps or self.config.livetalking_fps
        batch_size = self.config.livetalking_batch_size
        opt = SimpleNamespace(
            sessionid=session.session_id,
            fps=fps,
            batch_size=batch_size,
            l=self.config.livetalking_stride_left,
            m=self.config.livetalking_stride_mid,
            r=self.config.livetalking_stride_right,
            avatar_id=session.avatar_id,
            tts=self.config.livetalking_tts,
            REF_FILE=self.config.livetalking_ref_file,
            REF_TEXT=self.config.livetalking_ref_text or None,
            TTS_SERVER=self.config.livetalking_tts_server,
            customopt=[],
            customvideo_config="",
            model="musetalk",
            transport="webrtc",
            W=session.width or 0,
            H=session.height or 0,
        )

        musereal = self._livetalking_MuseReal(opt, self._livetalking_model, avatar)

        loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        loop_thread = threading.Thread(target=_run_loop, daemon=True)
        loop_thread.start()

        video_queue = queue.Queue(maxsize=max(10, batch_size * 4))

        class AsyncQueueBridge:
            def __init__(self, q: queue.Queue) -> None:
                self._q = q

            async def put(self, item) -> None:
                try:
                    self._q.put_nowait(item)
                except queue.Full:
                    try:
                        self._q.get_nowait()
                    except queue.Empty:
                        pass
                    self._q.put_nowait(item)

            def qsize(self) -> int:
                return self._q.qsize()

        class DropQueue:
            async def put(self, _item) -> None:
                return None

            def qsize(self) -> int:
                return 0

        video_track = SimpleNamespace(_queue=AsyncQueueBridge(video_queue))
        audio_track = SimpleNamespace(_queue=DropQueue())

        quit_event = threading.Event()
        render_thread = threading.Thread(
            target=musereal.render,
            args=(quit_event, loop, audio_track, video_track),
            daemon=True,
        )
        render_thread.start()

        chunk_size = max(1, int(16000 / fps))
        state = LiveTalkingState(
            musereal=musereal,
            quit_event=quit_event,
            loop=loop,
            loop_thread=loop_thread,
            render_thread=render_thread,
            video_queue=video_queue,
            audio_buffer=np.zeros(0, dtype=np.float32),
            frame_index=0,
            fps=fps,
            chunk_size=chunk_size,
            audio_pacing_start=None,
            audio_pacing_samples=0,
        )
        self._livetalking_sessions[session.session_id] = state
        session.backend_state = state
        session.backend = "livetalking"

    def _enqueue_livetalking_audio(self, session: SessionState, audio_pcm: bytes) -> None:
        state = self._livetalking_sessions.get(session.session_id)
        if state is None:
            return
        audio_np = np.frombuffer(audio_pcm, dtype=np.int16).astype(np.float32)
        if audio_np.size == 0:
            return
        audio_np /= 32768.0
        if session.sample_rate != 16000:
            audio_np = resampy.resample(
                audio_np, session.sample_rate, 16000
            )
        if state.audio_buffer.size:
            audio_np = np.concatenate([state.audio_buffer, audio_np])
        chunk = state.chunk_size
        pacing_rate = 16000
        if state.audio_pacing_start is None:
            state.audio_pacing_start = time.monotonic()
            state.audio_pacing_samples = 0
        total = audio_np.shape[0]
        idx = 0
        while total - idx >= chunk:
            frame = audio_np[idx : idx + chunk]
            target = state.audio_pacing_start + (
                state.audio_pacing_samples / pacing_rate
            )
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)
            state.musereal.put_audio_frame(frame, {})
            state.audio_pacing_samples += chunk
            idx += chunk
        state.audio_buffer = audio_np[idx:]

    def _pop_livetalking_frame(
        self, session: SessionState, timeout: float
    ) -> Optional[FramePayload]:
        state = self._livetalking_sessions.get(session.session_id)
        if state is None:
            return None
        try:
            item = state.video_queue.get(timeout=timeout)
        except queue.Empty:
            return None
        # Only drop frames if queue is severely backed up (> 2x batch size).
        # This preserves smooth animation while preventing unbounded latency.
        max_backlog = max(self.config.livetalking_batch_size * 2, 10)
        dropped = 0
        while state.video_queue.qsize() > max_backlog:
            try:
                item = state.video_queue.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        video_frame, _ = item
        pixel_fmt = session.pixel_fmt.lower()
        render_index = state.frame_index + dropped
        if pixel_fmt in {"i420", "yuv420p"}:
            if (
                session.width
                and session.height
                and (
                    session.width != video_frame.width
                    or session.height != video_frame.height
                )
            ):
                frame = video_frame.to_ndarray(format="bgr24")
                frame = cv2.resize(frame, (session.width, session.height))
                payload = self._frame_to_payload(frame, session, render_index)
            else:
                yuv = video_frame.to_ndarray(format="yuv420p")
                payload = FramePayload(
                    width=video_frame.width,
                    height=video_frame.height,
                    pixel_fmt="i420",
                    timestamp_ms=int(
                        (render_index / max(session.fps, 1)) * 1000
                    ),
                    data=yuv.tobytes(),
                )
        else:
            frame = video_frame.to_ndarray(format="bgr24")
            if session.width and session.height:
                frame = cv2.resize(frame, (session.width, session.height))
            payload = self._frame_to_payload(frame, session, render_index)
        state.frame_index = render_index + 1
        return payload

    def _stop_livetalking_session(self, session: SessionState) -> None:
        state = self._livetalking_sessions.pop(session.session_id, None)
        if state is None:
            return
        state.quit_event.set()
        # Let render thread exit before closing multiprocessing queues.
        with contextlib.suppress(Exception):
            state.render_thread.join(timeout=5)
        with contextlib.suppress(Exception):
            if state.loop.is_running():
                state.loop.call_soon_threadsafe(state.loop.stop)
        with contextlib.suppress(Exception):
            state.loop_thread.join(timeout=5)
        with contextlib.suppress(Exception):
            state.musereal.release()
