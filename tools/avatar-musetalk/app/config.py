from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[2]


@dataclass
class ServiceConfig:
    backend: str = os.getenv("MUSE_TALK_BACKEND", "musetalk")
    host: str = os.getenv("AVATAR_MUSETALK_HOST", "0.0.0.0")
    port: int = int(os.getenv("AVATAR_MUSETALK_PORT", "7800"))
    public_base_url: str = os.getenv(
        "AVATAR_MUSETALK_PUBLIC_BASE_URL", "http://127.0.0.1:7800"
    )

    # MuseTalk repo path (submodule)
    musetalk_dir: str = os.getenv(
        "MUSE_TALK_DIR", str(REPO_ROOT / "third_party" / "musetalk")
    )
    models_dir: str = os.getenv(
        "MUSE_TALK_MODELS_DIR", str(Path(musetalk_dir) / "models")
    )

    whisper_dir: str = os.getenv(
        "MUSE_TALK_WHISPER_DIR", str(Path(models_dir) / "whisper")
    )
    whisper_tiny_path: str = os.getenv(
        "MUSE_TALK_WHISPER_TINY_PATH",
        str(Path(whisper_dir) / "tiny.pt"),
    )
    unet_model_path: str = os.getenv(
        "MUSE_TALK_UNET_PATH",
        str(Path(models_dir) / "musetalkV15" / "unet.pth"),
    )
    unet_config: str = os.getenv(
        "MUSE_TALK_UNET_CONFIG",
        str(Path(models_dir) / "musetalkV15" / "musetalk.json"),
    )
    vae_type: str = os.getenv("MUSE_TALK_VAE_TYPE", "sd-vae")

    # Inference settings
    gpu_id: int = int(os.getenv("MUSE_TALK_GPU_ID", "0"))
    batch_size: int = int(os.getenv("MUSE_TALK_BATCH_SIZE", "8"))
    use_float16: bool = os.getenv("MUSE_TALK_FP16", "1") == "1"
    version: str = os.getenv("MUSE_TALK_VERSION", "v15")
    bbox_shift: int = int(os.getenv("MUSE_TALK_BBOX_SHIFT", "0"))
    extra_margin: int = int(os.getenv("MUSE_TALK_EXTRA_MARGIN", "10"))
    parsing_mode: str = os.getenv("MUSE_TALK_PARSING_MODE", "jaw")
    left_cheek_width: int = int(os.getenv("MUSE_TALK_LEFT_CHEEK_WIDTH", "90"))
    right_cheek_width: int = int(os.getenv("MUSE_TALK_RIGHT_CHEEK_WIDTH", "90"))
    audio_feature_backend: str = os.getenv(
        "MUSE_TALK_AUDIO_FEAT", "audio2feature"
    )
    audio_feat_left: int = int(os.getenv("MUSE_TALK_AUDIO_FEAT_LEFT", "2"))
    audio_feat_right: int = int(os.getenv("MUSE_TALK_AUDIO_FEAT_RIGHT", "2"))
    audio_resample_rate: int = int(os.getenv("MUSE_TALK_AUDIO_RESAMPLE", "16000"))

    # Path to fixed video assets
    video_root: str = os.getenv("MUSE_TALK_VIDEO_ROOT", "/data/videos")
    avatars_root: str = os.getenv(
        "MUSE_TALK_AVATARS_ROOT",
        str(Path("/data/avatars")),
    )
    # LiveTalking integration paths
    livetalking_root: str = os.getenv(
        "MUSE_TALK_LIVETALKING_ROOT",
        "/home/mssj/LiveTalking/xzx-ai-msg",
    )
    livetalking_src: str = os.getenv(
        "MUSE_TALK_LIVETALKING_SRC",
        "/home/mssj/LiveTalking/xzx-ai-msg/src",
    )
    # Persistent cache directory for preprocessing artifacts
    cache_dir: str = os.getenv(
        "MUSE_TALK_CACHE_DIR",
        str(Path.home() / ".cache" / "musetalk"),
    )

    # Default output settings
    default_fps: int = int(os.getenv("AVATAR_MUSETALK_FPS", "25"))
    default_width: int = int(os.getenv("AVATAR_MUSETALK_WIDTH", "0"))
    default_height: int = int(os.getenv("AVATAR_MUSETALK_HEIGHT", "0"))
    default_pixel_fmt: str = os.getenv("AVATAR_MUSETALK_PIXEL_FMT", "rgb24")
    default_binary_frames: bool = (
        os.getenv("AVATAR_MUSETALK_BINARY_FRAMES", "1") == "1"
    )

    # LiveTalking pipeline settings (MuseReal)
    livetalking_fps: int = int(os.getenv("MUSE_TALK_LIVETALKING_FPS", "50"))
    livetalking_batch_size: int = int(
        os.getenv("MUSE_TALK_LIVETALKING_BATCH", "16")
    )
    livetalking_stride_left: int = int(
        os.getenv("MUSE_TALK_LIVETALKING_STRIDE_LEFT", "10")
    )
    livetalking_stride_mid: int = int(
        os.getenv("MUSE_TALK_LIVETALKING_STRIDE_MID", "8")
    )
    livetalking_stride_right: int = int(
        os.getenv("MUSE_TALK_LIVETALKING_STRIDE_RIGHT", "10")
    )
    livetalking_tts: str = os.getenv("MUSE_TALK_LIVETALKING_TTS", "edgetts")
    livetalking_ref_file: str = os.getenv(
        "MUSE_TALK_LIVETALKING_REF_FILE", "zh-CN-YunxiaNeural"
    )
    livetalking_ref_text: str = os.getenv(
        "MUSE_TALK_LIVETALKING_REF_TEXT", ""
    )
    livetalking_tts_server: str = os.getenv(
        "MUSE_TALK_LIVETALKING_TTS_SERVER", "http://127.0.0.1:9880"
    )
