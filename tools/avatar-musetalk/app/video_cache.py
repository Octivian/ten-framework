from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
from typing import List, Tuple

import cv2


@dataclass
class VideoInfo:
    image_paths: List[str]
    fps: int
    width: int
    height: int


class VideoCache:
    def __init__(self, cache_root: str = "/tmp/avatar-musetalk") -> None:
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def prepare(self, video_path: str) -> VideoInfo:
        resolved = Path(video_path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"video not found: {resolved}")

        if resolved.is_dir():
            image_paths = self._list_images(resolved)
            if not image_paths:
                raise ValueError(f"no images in directory: {resolved}")
            width, height = self._get_image_size(image_paths[0])
            return VideoInfo(image_paths=image_paths, fps=25, width=width, height=height)

        if resolved.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            width, height = self._get_image_size(str(resolved))
            return VideoInfo(image_paths=[str(resolved)], fps=25, width=width, height=height)

        if resolved.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"}:
            return self._extract_video_frames(resolved)

        raise ValueError(f"unsupported video format: {resolved}")

    def _list_images(self, directory: Path) -> List[str]:
        items = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
            items.extend(directory.glob(ext))
        items = sorted(items, key=lambda p: p.name)
        return [str(p) for p in items]

    def _get_image_size(self, image_path: str) -> Tuple[int, int]:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"failed to read image: {image_path}")
        height, width = img.shape[:2]
        return width, height

    def _extract_video_frames(self, video_path: Path) -> VideoInfo:
        stat = video_path.stat()
        key = hashlib.sha1(f"{video_path}:{stat.st_mtime}".encode()).hexdigest()
        out_dir = self.cache_root / key
        out_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(out_dir.glob("*.png"))
        cap = cv2.VideoCapture(str(video_path))
        fps = int(round(cap.get(cv2.CAP_PROP_FPS))) or 25
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if not existing:
            idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                out_path = out_dir / f"{idx:08d}.png"
                cv2.imwrite(str(out_path), frame)
                idx += 1
            cap.release()
        else:
            cap.release()

        image_paths = sorted(out_dir.glob("*.png"))
        return VideoInfo(
            image_paths=[str(p) for p in image_paths],
            fps=fps,
            width=width,
            height=height,
        )
