# avatar-musetalk

Service wrapper for MuseTalk (fixed video -> lip sync -> video frames).

This module provides a minimal HTTP + WebSocket interface so TEN extensions can
stream audio and receive video frames. The runner now invokes MuseTalk's
inference pipeline (requires model weights and dependencies).

## Layout

- `app/server.py`: FastAPI + WebSocket entry.
- `app/musetalk_runner.py`: inference adapter (stub).
- `app/video_cache.py`: placeholder frame cache.
- `Dockerfile`: GPU runtime image.

## 环境变量

- `AVATAR_MUSETALK_HOST` (default `0.0.0.0`)
- `AVATAR_MUSETALK_PORT` (default `7800`)
- `AVATAR_MUSETALK_PUBLIC_BASE_URL` (default `http://127.0.0.1:7800`)
- `MUSE_TALK_DIR`: MuseTalk repo 路径（子模块，默认 `third_party/musetalk`）。
- `MUSE_TALK_VIDEO_ROOT`: path to fixed video files.
- `MUSE_TALK_AVATARS_ROOT`: 预处理 avatar 资源目录（默认 `/data/avatars`）。
- `MUSE_TALK_CACHE_DIR`: 预处理缓存目录（默认 `~/.cache/musetalk`）。
- `MUSE_TALK_AUDIO_FEAT`: `audio2feature`（默认）或 `transformers`，控制音频特征提取实现。
- `MUSE_TALK_WHISPER_TINY_PATH`: whisper tiny 模型路径（默认 `${MUSE_TALK_WHISPER_DIR}/tiny.pt`）。
- `MUSE_TALK_AUDIO_RESAMPLE`: 音频重采样目标（默认 `16000`）。
- `MUSE_TALK_BACKEND`: `musetalk`（默认）或 `livetalking`，切换到 MuseReal/MuseASR 流水线。
- `MUSE_TALK_LIVETALKING_ROOT`: LiveTalking 项目根目录（包含 `data/avatars` 与 `models`）。
- `MUSE_TALK_LIVETALKING_SRC`: LiveTalking `src` 目录（包含 `live_digital_human`）。
- `MUSE_TALK_LIVETALKING_FPS`: LiveTalking 后端帧率（默认 50）。
- `MUSE_TALK_LIVETALKING_BATCH`: LiveTalking batch size（默认 16）。
## 构建提示

- Docker build 请从仓库根目录执行，这样 `third_party/musetalk` 才能被复制进镜像。

## GPU 部署（参考）

> 备注（ms-gpu）：模型已存在于  
> `/home/mssj/ten-framework/third_party/musetalk/models`

默认路径假设：
- 仓库目录：`/home/<user>/ten-framework`
- MuseTalk 子模块：`/home/<user>/ten-framework/third_party/musetalk`
- 模型目录：`/home/<user>/ten-framework/third_party/musetalk/models`
- 服务端口：`7800`

一键部署脚本在本目录下：`deploy_gpu.sh`

```bash
cd /home/<user>/ten-framework/tools/avatar-musetalk
bash deploy_gpu.sh
```

脚本会：
1. 创建虚拟环境：`~/venvs/avatar-musetalk`（使用 `virtualenv`）。
2. 安装 PyTorch CUDA 版本（cu118）+ torchvision。
3. 安装 MuseTalk 与服务依赖。
4. 安装 OpenMMLab 依赖（mmengine/mmcv/mmdet/mmpose）。
5. 启动 `uvicorn` 服务（`0.0.0.0:7800`），日志输出到 `~/avatar-musetalk.log`。

健康检查：
```bash
curl http://127.0.0.1:7800/health
```

常见说明：
- 若 `/` 分区空间不足，脚本会用 `/home/<user>/tmp` 作为临时目录和 pip 缓存，
  避免 “No space left on device”。
- 若需要代理，执行前设置：
  `PROXY_CMD=proxy bash deploy_gpu.sh`

## API

- `POST /v1/sessions`
  - body: `{ "video_path": "...", "fps": 25, "width": 0, "height": 0, "pixel_fmt": "rgb24" }`
  - 或使用预处理 avatar：`{ "avatar_id": "muse_libai", "fps": 25, "width": 0, "height": 0, "pixel_fmt": "rgb24" }`
  - response: `{ "session_id": "...", "ws_url": "..." }`
- `POST /v1/cache/warmup`
  - body: `{ "video_path": "...", "fps": 25, "width": 0, "height": 0, "pixel_fmt": "rgb24" }`
  - 或使用预处理 avatar：`{ "avatar_id": "muse_libai", "fps": 25, "width": 0, "height": 0, "pixel_fmt": "rgb24" }`
  - response: `{ "cache_key": "..." }`
- `WS /v1/sessions/{session_id}/stream`
  - client -> server: `{ "type": "audio", "data": "<base64 pcm>", "sample_rate": 24000 }`
  - server -> client: `{ "type": "frame", "data": "<base64>" , "width": 512, "height": 512, "pixel_fmt": "rgb24", "timestamp_ms": 0 }`

## 预处理缓存说明

服务会在首次使用时对固定视频做预处理（逐帧解码、bbox/landmark、mask、latent）。结果会持久化到 `MUSE_TALK_CACHE_DIR`，下次同样参数会直接复用缓存，避免等待。

可用 warmup 接口提前生成缓存：
```bash
curl -X POST http://127.0.0.1:7800/v1/cache/warmup \
  -H 'Content-Type: application/json' \
  -d '{"video_path":"/path/to/video.mp4","fps":25,"width":0,"height":0,"pixel_fmt":"rgb24"}'
```

## 预处理 Avatar 模式（推荐）

如果已有 MuseTalk 预处理资源（例如 `data/avatars/<avatar_id>`，包含
`full_imgs/`、`coords.pkl`、`latents.pt`、`mask/`、`mask_coords.pkl`），
可直接走 avatar 模式，跳过视频预处理，显著降低启动延迟：

```bash
export MUSE_TALK_AVATARS_ROOT=/home/mssj/LiveTalking/xzx-ai-msg/data/avatars
curl -X POST http://127.0.0.1:7800/v1/cache/warmup \
  -H 'Content-Type: application/json' \
  -d '{"avatar_id":"muse_libai","fps":12,"width":0,"height":0,"pixel_fmt":"rgb24"}'
```

## Next steps

- Make sure `third_party/musetalk` submodule is initialized and model weights are downloaded into `third_party/musetalk/models`.
- Tune latency: chunk size, batch size, and GPU settings.
