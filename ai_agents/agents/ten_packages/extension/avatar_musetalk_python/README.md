# avatar_musetalk_python

TEN extension that streams PCM audio to the avatar-musetalk service and emits video frames.

## Configuration

See `property.json` for defaults:
- `service_base_url`: MuseTalk service URL.
- `video_path`: fixed avatar video path (resolved by the service).
- `avatar_id`: preprocessed avatar id under `MUSE_TALK_AVATARS_ROOT` (preferred).
- `output_width` / `output_height`: 0 keeps source size.
- `output_fps`: output FPS.
- `pixel_fmt`: rgb24/bgr24/rgba/bgra/nv12/nv21/i420/i422.
- `input_audio_sample_rate`: PCM sample rate.
- `min_chunk_ms`: minimum audio chunk size sent to service.

## IO

- Input: `audio_frame` (PCM)
- Output: `video_frame` (raw video frames) using `ten_env.send_video_frame()`

## 使用前置（必须先启服务）

该扩展依赖 `tools/avatar-musetalk` 服务，未启动服务会导致连接失败。

本地或 GPU 机器启动示例：
```bash
cd tools/avatar-musetalk
bash deploy_gpu.sh
```

健康检查：
```bash
curl http://127.0.0.1:7800/health
```

如果服务运行在远端，请把 `service_base_url` 指向远端地址，
例如 `http://<GPU_IP>:7800`。

## Notes

This is a minimal adapter. Replace the service stub in `tools/avatar-musetalk`
with real MuseTalk inference.
