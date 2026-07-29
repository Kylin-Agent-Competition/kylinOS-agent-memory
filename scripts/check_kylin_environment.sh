#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo " 麒麟 OS Agent 记忆系统 - 环境信息采集"
echo "=========================================="
echo ""

echo "[1/10] 系统信息 (uname)"
uname -a
echo ""

echo "[2/10] 操作系统发行版"
if [ -f /etc/os-release ]; then
    cat /etc/os-release
else
    echo "/etc/os-release 不存在"
fi
echo ""

echo "[3/10] 机器架构"
uname -m
echo ""

echo "[4/10] Python 版本"
if command -v python3 &>/dev/null; then
    python3 --version
else
    echo "python3 未安装"
fi
echo ""

echo "[5/10] GCC 版本"
if command -v gcc &>/dev/null; then
    gcc --version | head -1
else
    echo "gcc 未安装"
fi
echo ""

echo "[6/10] G++ 版本"
if command -v g++ &>/dev/null; then
    g++ --version | head -1
else
    echo "g++ 未安装"
fi
echo ""

echo "[7/10] CMake 版本"
if command -v cmake &>/dev/null; then
    cmake --version | head -1
else
    echo "cmake 未安装"
fi
echo ""

echo "[8/10] Git 版本"
if command -v git &>/dev/null; then
    git --version
else
    echo "git 未安装"
fi
echo ""

echo "[9/10] 虚拟化检测"
if command -v systemd-detect-virt &>/dev/null; then
    systemd-detect-virt || echo "无虚拟化或无 systemd"
else
    echo "systemd-detect-virt 不可用"
fi
echo ""

echo "[10/10] 常用命令与路径检查"

check_cmd() {
    local cmd="$1"
    if command -v "$cmd" &>/dev/null; then
        echo "  ✓ $cmd 可用"
    else
        echo "  ✗ $cmd 不可用"
    fi
}

check_cmd gcc
check_cmd g++
check_cmd cmake
check_cmd make
check_cmd python3
check_cmd pip3
check_cmd git
check_cmd sqlite3
check_cmd nc
check_cmd curl
echo ""

echo "项目根目录检查"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "  项目目录: ${PROJECT_ROOT}"
if [ -d "${PROJECT_ROOT}/memory-service" ]; then
    echo "  ✓ memory-service/ 存在"
else
    echo "  ✗ memory-service/ 不存在"
fi
if [ -d "${PROJECT_ROOT}/cpp-bridge" ]; then
    echo "  ✓ cpp-bridge/ 存在"
else
    echo "  ✗ cpp-bridge/ 不存在"
fi
echo ""

echo "Runtime Socket 路径检查（仅报告状态）"
SOCKET_PATH="${KMA_SOCKET_PATH:-/tmp/kylin-memory-service.sock}"
if [ -S "${SOCKET_PATH}" ]; then
    echo "  ✓ Socket 存在: ${SOCKET_PATH}"
else
    echo "  未找到 Socket: ${SOCKET_PATH}（未启动服务时正常）"
fi
echo ""

echo "Vector/Embedding 路径检查（仅报告状态）"
if [ -d "${PROJECT_ROOT}/models" ]; then
    echo "  ✓ models/ 存在"
else
    echo "  models/ 不存在（尚未部署模型）"
fi
echo ""

echo "=========================================="
echo " 环境信息采集完成"
echo "=========================================="
