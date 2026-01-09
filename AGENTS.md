# Repository Guidelines

## 项目结构与模块组织
本仓库包含核心运行时与 AI Agents 两大部分。`core/` 存放 C/C++ 运行时、Rust 的 tman 与工具库；`ai_agents/` 包含 Agent 示例、Python 扩展、Go 服务与前端；`packages/` 提供多语言 addon loader 与示例应用；`tests/` 为运行时与管理器测试；`tools/` 与 `build/` 为构建辅助与产物。AI 扩展主要在 `ai_agents/agents/ten_packages/extension/`，示例工程在 `ai_agents/agents/examples/`。

## 构建、测试与开发命令
核心构建使用 `task` 与 `tgn`：
```bash
task gen        # 生成 GN/Ninja 构建文件
task build      # 构建核心框架
task gen-tman   # 生成 tman 构建
task build-tman # 构建 tman
```
AI Agents 相关命令在 `ai_agents/`：
```bash
cd ai_agents
task lint                  # Python 扩展 lint
task format                # black 格式化
task test                  # 运行所有测试
task test-extension EXTENSION=agents/ten_packages/extension/elevenlabs_tts_python
```
前端与脚本格式化使用 Biome：`npm run lint`、`npm run format`。

## 编码风格与命名规范
Python 使用 black（默认行宽 80）；Go 使用 `gofmt`；TypeScript/JavaScript 使用 Biome 配置。新代码优先使用 TypeScript，并保持现有目录命名与模块分层一致。不要手改生成文件，如 `BUILD.gn`、`compile_commands.json`、`out/`、`.ten/`、`node_modules/`、`build/`。

## 测试指南
测试框架以 `task test` 为入口，扩展测试位于 `ai_agents/agents/ten_packages/extension/*/tests/`，核心测试位于 `tests/`。新增功能需补充单元或集成测试，UI 变更应包含必要的手动验证说明。

## 提交与 PR 规范
提交信息采用 Conventional Commits，例如 `feat: add new ASR integration`、`fix: resolve memory leak`。PR 需说明变更内容与原因，关联 Issue（如 `Fixes #123`），UI 变更需截图，提交前请运行 `task format` 与 `task lint` 并确保测试通过。

## 环境与配置提示
`ai_agents/.env.example` 是环境变量模板，复制为 `ai_agents/.env` 后填入各类 API key。扩展运行依赖 `PYTHONPATH` 设置（见 `ai_agents/Taskfile.yml`），如需单独运行示例请进入 `ai_agents/agents/examples/<example>` 并执行 `task install`、`task run`。

## 记录
当需要让任意 app 使用定制的 `ten_ai_base` 时，将该 app 的 `tenapp/manifest.json` 中 `ten_ai_base` 依赖改为路径依赖 `/ten_ai_base`（例如 `ai_agents/agents/examples/voice-assistant/tenapp/manifest.json`）。
当前仓库中 `ten_ai_base` 是 git 子模块；在容器环境中通过 `docker-compose` 把仓库里的 `ten_ai_base` 挂载到 `/ten_ai_base`，因此路径依赖可直接生效。若 app 仍使用 `type: system, name: ten_ai_base` 的版本依赖，就不会自动使用定制版；非容器环境需调整路径或改用本地绝对路径。

### 开发环境容器启动记录
使用最新 `dev` 分支代码重启开发容器（执行于仓库根目录）：
```bash
git pull --rebase --autostash origin dev
docker compose -f ai_agents/docker-compose.yml down
docker compose -f ai_agents/docker-compose.yml up -d --build
```
容器名称通常为 `ten_agent_dev`，可用 `docker compose -f ai_agents/docker-compose.yml ps` 查看状态。

### ai-msg 启动记录（按 README 流程）
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

## App / Graph / Agent 与启动逻辑
### 概念
- app：对应一个 `tenapp/` 目录（`manifest.json` + 图配置），一个 app 可包含多个 graph。
- graph：可视化流程定义（Designer 里编辑/查看）。
- agent：运行时实例（某个 graph 的进程/会话）。

### 服务与职责
- 前端 3000：页面展示与 RTC 加入逻辑。
- Go API 8080：控制面（`/start`、`/stop`、`/ping`），负责拉起/停止 agent。
- Designer 49483：图编辑器，支持加载多个 app 的 graph 供编辑。

### 启动与交互逻辑
- Go API Server 启动时绑定 `-tenapp_dir`，`/start` 只会启动该目录下的 graph（内部执行 `tman run start`）。
- Designer 同时加载多个 app 不会改变 8080 可启动的范围，只是用于编辑/浏览。
- 前端进入页面会自动加入 RTC channel；该 channel 由前端生成并缓存（刷新时通常复用），不需要提前创建。
- 点击 Connect 仅触发 `/start`，不负责加入房间；即使未启动 agent，前端也已在 channel 内。
- `/start` 会把前端的 channel 信息写入 agent 属性（例如 `agora_rtc.channel`），用于让 agent 进入同一房间；未启动时不会有 agent 加入。
- Designer 也可以直接启动 agent（执行 `tman run start`）。只要 graph 的 `agora_rtc` 配置好 channel 等属性，启动时 agent 会直接加入该 channel，无需 3000 页面点击 Connect。
- 结论：**启动 agent** 和 **前端 Connect** 是两件事；Connect 只是触发 `/start`，而“加入 channel”发生在前端页面加载时或 agent 启动时。

### Agent 与前端“能聊天”的关键属性（以 `agora_rtc` 为主）
- `agora_rtc.app_id`：必须是有效的 Agora App ID（通常来自 `AGORA_APP_ID`）。
- `agora_rtc.token`：需要有效 token；走 8080 `/start` 会自动生成并注入（基于 `AGORA_APP_ID`/`AGORA_APP_CERTIFICATE`），Designer 直接启动时需自行填入。
- `agora_rtc.channel`：必须与前端页面进入时使用的 channel 一致（前端会自动生成/缓存）。
- `agora_rtc.remote_stream_id`：必须等于前端 `userId`（前端启动时随机生成并缓存）。
- `agora_rtc.stream_id`：agent 自己的 uid（任意未占用的整数即可）。
- `agora_rtc.subscribe_audio` / `publish_audio` / `publish_data`：保持 `true`，保证音频与数据通道都能收发。
