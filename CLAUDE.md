# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

TEN is an open-source framework for real-time multimodal conversational AI. The repository contains:
- **Core Framework** (`/core`): C/C++ runtime, Rust package manager (tman), utilities
- **AI Agents** (`/ai_agents`): Agent examples, 60+ extensions (ASR, TTS, LLM), Go server, Next.js playground
- **Packages** (`/packages`): Core addon loaders, example apps and extensions for all supported languages
- **Tests** (`/tests`): Comprehensive test suites for runtime, manager, and integrations

## Build Commands

### Core Framework (GN/Ninja build system)

```bash
# Generate build files (vars: OS=linux|mac|win, ARCH=x64|arm64, BUILD_TYPE=debug|release)
task gen -- <extra_args>

# Build framework
task build

# Build tman (package manager) only
task gen-tman
task build-tman

# Clean
task clean
```

The `tgn` wrapper handles GN generation and Ninja builds:
```bash
tgn gen linux x64 debug -- log_level=1 ten_enable_ten_rust=true
tgn build linux x64 debug
```

### AI Agents Development

```bash
cd ai_agents

# Lint all Python extensions
task lint

# Lint specific extension
task lint-extension EXTENSION=deepgram_asr_python

# Format Python code
task format

# Check formatting
task check

# Run all tests (server + extensions)
task test

# Test specific extension
task test-extension EXTENSION=agents/ten_packages/extension/elevenlabs_tts_python

# Test without reinstalling deps
task test-extension-no-install EXTENSION=<path>
```

### Docker Development Environment (Recommended)

AI Agents 开发推荐使用 Docker 环境，确保依赖一致性。

**Step 1: 启动 Docker 容器**
```bash
cd ai_agents                    # 必须在 ai_agents 目录下执行
cp .env.example .env            # 首次运行需要配置环境变量
docker compose up -d            # 启动 ten_agent_dev 容器
```

**Step 2: 进入容器运行 Example**
```bash
# 进入容器
docker compose exec ten_agent_dev bash

# 在容器内，进入示例目录并安装依赖
cd /app/agents/examples/voice-assistant-realtime/tenapp
tman install                    # 安装扩展依赖
./scripts/install_python_deps.sh  # 安装 Python 依赖
```

**Step 3: 启动服务（在容器内）**
```bash
# 启动 tenapp（主应用）
tman run start

# 新终端：启动 Go API Server
docker compose exec ten_agent_dev bash -c "cd /app/server && go run main.go -tenapp_dir=/app/agents/examples/voice-assistant-realtime/tenapp"

# 新终端：启动前端
docker compose exec ten_agent_dev bash -c "cd /app/playground && npm run dev"

# 新终端：启动 TMAN Designer（可选）
docker compose exec ten_agent_dev bash -c "cd /app/agents/examples/voice-assistant-realtime/tenapp && tman designer"
```

**访问地址:**
- Frontend: http://localhost:3000
- API Server: http://localhost:8080
- TMAN Designer: http://localhost:49483

**注意事项:**
- 容器将 `ai_agents/` 挂载到 `/app`，代码修改实时生效
- 如需挂载外部依赖包（如 ten_ai_base），需在 `docker-compose.yml` 的 volumes 中添加
- 环境变量配置在 `ai_agents/.env` 文件中

### Running Agent Examples (Without Docker)

```bash
cd ai_agents/agents/examples/voice-assistant
task install    # Install dependencies
task run        # Run everything (API server, frontend, TMAN Designer)

# Individual components
task run-api-server    # Go server on :8080
task run-frontend      # Next.js on :3000
task run-gd-server     # TMAN Designer on :49483
```

### Integration Tests

```bash
# ASR guarder tests
task asr-guarder-test EXTENSION=azure_asr_python CONFIG_DIR=tests/configs

# TTS guarder tests
task tts-guarder-test EXTENSION=bytedance_tts_duplex CONFIG_DIR=tests/configs
```

## Architecture

### Graph-Based Extension System

TEN uses a graph-based architecture where extensions (modular AI components) are connected via configuration:

```
Audio Input → ASR Extension → LLM Extension → TTS Extension → Audio Output
```

**Extension Types:** ASR, TTS, LLM, Vision/MLLM, RTC, Tools

**Graph Configuration** (`property.json`):
```json
{
  "ten": {
    "predefined_graphs": [{
      "name": "voice_assistant",
      "graph": {
        "nodes": [
          {"name": "stt", "addon": "deepgram_asr_python", "property": {...}},
          {"name": "llm", "addon": "openai_llm2_python", "property": {...}}
        ],
        "connections": [
          {"extension": "main_control", "data": [{"name": "asr_result", "source": [{"extension": "stt"}]}]}
        ]
      }
    }]
  }
}
```

**Connection Types:** `data`, `cmd`, `audio_frame`, `video_frame`

### Key Directories

```
core/
├── src/ten_runtime/     # C/C++ runtime engine
├── src/ten_manager/     # Rust package manager (tman)
├── src/ten_rust/        # Rust bindings
└── src/ten_utils/       # Utility libraries

ai_agents/
├── agents/ten_packages/extension/   # 60+ extensions
├── agents/ten_packages/system/      # ten_ai_base, ten_runtime_python
├── agents/examples/                 # Agent examples
├── server/                          # Go API server
└── playground/                      # Next.js frontend

packages/
├── core_addon_loaders/    # Python, Node.js, Go addon loaders
├── core_apps/             # Default apps per language
└── example_extensions/    # Extension examples

tests/
├── ten_runtime/integration/   # C++, Go, Python, Node.js integration tests
├── ten_manager/               # Package manager tests
└── local_registry/            # Test package registry
```

### Language Stack

- **C/C++**: Core runtime (`core/src/ten_runtime/`, `core/src/ten_utils/`)
- **Rust**: Package manager, bindings (`core/src/ten_manager/`, `core/src/ten_rust/`)
- **Go**: API server, some extensions (`ai_agents/server/`)
- **Python**: AI extensions (`ai_agents/agents/ten_packages/extension/`)
- **TypeScript**: Frontend (`ai_agents/playground/`)

## Python Extension Development

Extensions require specific PYTHONPATH:
```bash
export PYTHONPATH="./agents/ten_packages/system/ten_runtime_python/lib:./agents/ten_packages/system/ten_runtime_python/interface:./agents/ten_packages/system/ten_ai_base/interface"
```

**Extension Structure:**
```
extension_name/
├── manifest.json    # Metadata, dependencies, API interface
├── property.json    # Configuration (supports ${env:VAR_NAME})
├── addon.py         # Registration with @register_addon_as_extension
├── extension.py     # Main logic inheriting base class
└── tests/bin/start  # Test runner script
```

**Base Classes:** `AsyncASRBaseExtension`, `AsyncTTSBaseExtension`, `LLMBaseExtension` in `ten_ai_base`

## TEN Manager (tman)

Package manager for TEN framework:
```bash
tman install              # Install dependencies from manifest.json
tman install --standalone # Install for standalone testing
tman run start            # Run tenapp
tman designer             # Start visual graph editor
```

## Auto-Generated Files (Do Not Modify)

These are managed by build tools:
- `manifest-lock.json`, `compile_commands.json`, `BUILD.gn`
- `.gn`, `.gnfiles`, `out/`, `.ten/`, `bin/`, `.release/`
- `build/`, `node_modules/`, `*.log`

## Environment Configuration

Copy `.env.example` to `.env` and configure:
- **RTC:** `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`
- **LLM:** `OPENAI_API_KEY`, `AZURE_OPENAI_*`
- **ASR:** `DEEPGRAM_API_KEY`, `AZURE_ASR_*`
- **TTS:** `ELEVENLABS_TTS_KEY`, `AZURE_TTS_*`

## Coding Style & Naming Conventions

Python 使用 black（默认行宽 80）；Go 使用 `gofmt`；TypeScript/JavaScript 使用 Biome 配置。新代码优先使用 TypeScript，并保持现有目录命名与模块分层一致。不要手改生成文件，如 `BUILD.gn`、`compile_commands.json`、`out/`、`.ten/`、`node_modules/`、`build/`。

## Testing Guidelines

测试框架以 `task test` 为入口，扩展测试位于 `ai_agents/agents/ten_packages/extension/*/tests/`，核心测试位于 `tests/`。新增功能需补充单元或集成测试，UI 变更应包含必要的手动验证说明。

## Commit & PR Conventions

提交信息采用 Conventional Commits，例如 `feat: add new ASR integration`、`fix: resolve memory leak`。PR 需说明变更内容与原因，关联 Issue（如 `Fixes #123`），UI 变更需截图，提交前请运行 `task format` 与 `task lint` 并确保测试通过。

## Notes & Records

### Custom ten_ai_base Usage

当需要让任意 app 使用定制的 `ten_ai_base` 时，将该 app 的 `tenapp/manifest.json` 中 `ten_ai_base` 依赖改为路径依赖 `/ten_ai_base`（例如 `ai_agents/agents/examples/voice-assistant/tenapp/manifest.json`）。
当前仓库中 `ten_ai_base` 是 git 子模块；在容器环境中通过 `docker-compose` 把仓库里的 `ten_ai_base` 挂载到 `/ten_ai_base`，因此路径依赖可直接生效。若 app 仍使用 `type: system, name: ten_ai_base` 的版本依赖，就不会自动使用定制版；非容器环境需调整路径或改用本地绝对路径。

### avatar-musetalk Module Location & Wiring

- 服务封装：`tools/avatar-musetalk`（FastAPI + WebSocket，已接入 MuseTalk 推理流程）
- MuseTalk repo：`third_party/musetalk`（子模块），并设置 `MUSE_TALK_DIR`
- TEN 扩展：`ai_agents/agents/ten_packages/extension/avatar_musetalk_python`
- 典型接线：`bytedance_tts_duplex -> avatar_musetalk_python -> agora_rtc (video_frame)`
- 本地启动示例：
```bash
cd tools/avatar-musetalk
python3 -m uvicorn app.server:app --host 0.0.0.0 --port 7800
```

### Dev Container Startup

使用最新 `dev` 分支代码重启开发容器（执行于仓库根目录）：
```bash
git pull --rebase --autostash origin dev
docker compose -f ai_agents/docker-compose.yml down
docker compose -f ai_agents/docker-compose.yml up -d --build
```
容器名称通常为 `ten_agent_dev`，可用 `docker compose -f ai_agents/docker-compose.yml ps` 查看状态。

### ai-msg Startup (Following README)

进入容器后执行：
```bash
cd /app/agents/examples/ai-msg
task install
task run
```
说明：在 amd64 容器（QEMU）环境里，`task install` 的前端依赖安装使用 bun 可能触发 `Illegal instruction`。可用以下方式绕过并启动前端：
```bash
cd /app/playground
npm install
npm run dev -- -H 0.0.0.0 -p 3000
```
其余服务可单独启动：
```bash
cd /app/agents/examples/ai-msg
task run-gd-server   # 49483
task run-api-server  # 8080
```

### Designer Startup Directory Rule

Designer 需要在**目标 app 的 tenapp 目录**启动，否则图会处于 `app=None` 的临时状态，导致连接校验失败（例如提示"Destination extension ... not found in the installed packages for app 'None'"）。

正确方式（示例以 voice_assistant 为例）：
```bash
cd /app/agents/examples/voice-assistant/tenapp
tman designer
```

如果需要编辑其他 app，请切到对应的 `tenapp` 目录重新启动 Designer。这样才能正常添加/连接该 app 依赖的节点。

## App / Graph / Agent Concepts & Startup Logic

### Concepts

- app：对应一个 `tenapp/` 目录（`manifest.json` + 图配置），一个 app 可包含多个 graph。
- graph：可视化流程定义（Designer 里编辑/查看）。
- agent：运行时实例（某个 graph 的进程/会话）。

### Services & Responsibilities

- 前端 3000：页面展示与 RTC 加入逻辑。
- Go API 8080：控制面（`/start`、`/stop`、`/ping`），负责拉起/停止 agent。
- Designer 49483：图编辑器，支持加载多个 app 的 graph 供编辑。

### Startup & Interaction Logic

- Go API Server 启动时绑定 `-tenapp_dir`，`/start` 只会启动该目录下的 graph（内部执行 `tman run start`）。
- Designer 同时加载多个 app 不会改变 8080 可启动的范围，只是用于编辑/浏览。
- 前端进入页面会自动加入 RTC channel；该 channel 由前端生成并缓存（刷新时通常复用），不需要提前创建。
- 点击 Connect 仅触发 `/start`，不负责加入房间；即使未启动 agent，前端也已在 channel 内。
- `/start` 会把前端的 channel 信息写入 agent 属性（例如 `agora_rtc.channel`），用于让 agent 进入同一房间；未启动时不会有 agent 加入。
- Designer 也可以直接启动 agent（执行 `tman run start`）。只要 graph 的 `agora_rtc` 配置好 channel 等属性，启动时 agent 会直接加入该 channel，无需 3000 页面点击 Connect。
- 结论：**启动 agent** 和 **前端 Connect** 是两件事；Connect 只是触发 `/start`，而"加入 channel"发生在前端页面加载时或 agent 启动时。

### Key Properties for Agent-Frontend Communication (agora_rtc)

- `agora_rtc.app_id`：必须是有效的 Agora App ID（通常来自 `AGORA_APP_ID`）。
- `agora_rtc.token`：需要有效 token；走 8080 `/start` 会自动生成并注入（基于 `AGORA_APP_ID`/`AGORA_APP_CERTIFICATE`），Designer 直接启动时需自行填入。
- `agora_rtc.channel`：必须与前端页面进入时使用的 channel 一致（前端会自动生成/缓存）。
- `agora_rtc.remote_stream_id`：必须等于前端 `userId`（前端启动时随机生成并缓存）。
- `agora_rtc.stream_id`：agent 自己的 uid（任意未占用的整数即可）。
- `agora_rtc.subscribe_audio` / `publish_audio` / `publish_data`：保持 `true`，保证音频与数据通道都能收发。

## Additional Documentation

- **AI Agents Guide:** See `ai_agents/CLAUDE.md` for detailed extension development patterns
- **Contributing:** See `docs/code-of-conduct/contributing.md`
- **Official Docs:** https://theten.ai/docs
