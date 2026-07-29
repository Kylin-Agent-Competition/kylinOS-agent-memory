#!/usr/bin/env bash
set -euo pipefail
# ============================================================
# KYSEC 单文件 verified 放行脚本
# 用途：对需要运行的测试/构建二进制设置 KYSEC verified 标记
# 使用：./tools/kysec_allow.sh [binary_path]
# 注意：只对单个二进制放行，不全局关闭 KYSEC
# 禁止：sudo mm-cli -c -n、sudo kysec_set -n exectl -v verified（全局）
# ============================================================

if [ $# -lt 1 ]; then
    echo "Usage: $0 <binary_path>"
    echo "Example: $0 ~/projects/kylin-memory-sdk/build/test_embedding"
    exit 1
fi

BIN="$1"

if [ ! -f "$BIN" ]; then
    echo "ERROR: Binary not found: $BIN"
    exit 1
fi

echo "[KYSEC] Setting verified for: $BIN"
sudo kysec_set -n exectl -v verified "$BIN"

if [ $? -eq 0 ]; then
    echo "[KYSEC] SUCCESS: $BIN is now verified"
    echo "$(date '+%Y-%m-%d %H:%M:%S') | verified | $BIN" >> ~/.local/state/kylin-memory/kysec_allow.log
else
    echo "[KYSEC] FAILED: $BIN"
    exit 1
fi