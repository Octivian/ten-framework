#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/ten-framework}"
VENV_DIR="${VENV_DIR:-$HOME/venvs/avatar-musetalk}"
MUSE_TALK_DIR="${MUSE_TALK_DIR:-$PROJECT_DIR/third_party/musetalk}"
PORT="${PORT:-7800}"
LOG_FILE="${LOG_FILE:-$HOME/avatar-musetalk.log}"
TMP_BASE="${TMP_BASE:-$HOME/tmp}"

if [[ -n "${PROXY_CMD:-}" ]]; then
  # Example: PROXY_CMD=proxy
  eval "${PROXY_CMD}"
fi

mkdir -p "$TMP_BASE/pip-cache" "$TMP_BASE/pip-tmp" "$HOME/venvs"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m pip install --user virtualenv
  "$HOME/.local/bin/virtualenv" "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

export TMPDIR="$TMP_BASE/pip-tmp"
export PIP_CACHE_DIR="$TMP_BASE/pip-cache"

pip install -U pip

pip install torch==2.1.2+cu118 torchvision==0.16.2+cu118 \
  --index-url https://download.pytorch.org/whl/cu118

pip install -r "$PROJECT_DIR/tools/avatar-musetalk/requirements.txt"

# OpenMMLab stack (CUDA ops required by MuseTalk preprocessing)
pip install openmim tabulate rich requests pyyaml colorama model-index
mim install mmengine
mim install mmcv==2.1.0
mim install mmdet==3.2.0
mim install mmpose==1.3.2

# Start service
cd "$PROJECT_DIR/tools/avatar-musetalk"
MUSE_TALK_DIR="$MUSE_TALK_DIR" \
nohup python -m uvicorn app.server:app \
  --host 0.0.0.0 --port "$PORT" \
  > "$LOG_FILE" 2>&1 &

echo "avatar-musetalk started on :$PORT"
echo "log: $LOG_FILE"
echo "health: curl http://127.0.0.1:$PORT/health"

