#!/bin/bash

set -e

cd "$(dirname "${BASH_SOURCE[0]}")/.."

#export TEN_ENABLE_PYTHON_DEBUG=true
#export TEN_PYTHON_DEBUG_PORT=5678
export PYTHONPATH=$(pwd)/ten_packages/system/ten_ai_base/interface:/usr/local/lib/python3.10/dist-packages:/usr/lib/python3/dist-packages:/usr/lib/python3.10/dist-packages:$PYTHONPATH
export LD_LIBRARY_PATH=$(pwd)/ten_packages/system/agora_rtc_sdk/lib:$(pwd)/ten_packages/extension/agora_rtm/lib:$(pwd)/ten_packages/system/azure_speech_sdk/lib
export NODE_PATH=$(pwd)/ten_packages/system/ten_runtime_nodejs/lib:$NODE_PATH

exec bin/main "$@"
