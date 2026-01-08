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

## Additional Documentation

- **AI Agents Guide:** See `ai_agents/CLAUDE.md` for detailed extension development patterns
- **Contributing:** See `docs/code-of-conduct/contributing.md`
- **Official Docs:** https://theten.ai/docs
