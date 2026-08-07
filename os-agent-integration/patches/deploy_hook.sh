#!/usr/bin/env bash
# =============================================================================
# connect_hook 部署脚本
# =============================================================================
# 通过 SSH 将 connect() hook 源码、测试脚本传输到麒麟 VM，
# 编译 libconnect_hook.so 并运行集成测试。
#
# 用法 (在 Windows 开发机上执行):
#   bash deploy_hook.sh <麒麟VM_IP> [麒麟用户名] [SSH端口]
#
# 默认: 用户 kylin, 端口 22
# =============================================================================

set -euo pipefail

KYLIN_HOST="${1:-}"
KYLIN_USER="${2:-kylin}"
KYLIN_PORT="${3:-22}"

if [ -z "$KYLIN_HOST" ]; then
    echo "Usage: $0 <麒麟VM_IP> [麒麟用户名] [SSH端口]"
    echo "Example: $0 REDACTED_VM_IP kylin 22"
    exit 1
fi

# 端口校验
if ! [[ "$KYLIN_PORT" =~ ^[0-9]+$ ]] || [[ "$KYLIN_PORT" -lt 1 || "$KYLIN_PORT" -gt 65535 ]]; then
    echo "❌ 无效端口号: $KYLIN_PORT"
    exit 1
fi

SSH_OPTS="-p $KYLIN_PORT -o ConnectTimeout=10 -o StrictHostKeyChecking=no"
SCP_OPTS="-P $KYLIN_PORT -o ConnectTimeout=10 -o StrictHostKeyChecking=no"
REMOTE_BASE="/home/$KYLIN_USER/kylin-memory-echo"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=========================================="
echo " Kylin connect() Hook — 部署"
echo "=========================================="
echo "  目标: $KYLIN_USER@$KYLIN_HOST:$KYLIN_PORT"
echo "  远程路径: $REMOTE_BASE"
echo "=========================================="

# ---- Step 1: 创建远程目录 ----
echo ""
echo "[1/4] 创建远程目录..."
ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "
    mkdir -p $REMOTE_BASE/lib
    mkdir -p $REMOTE_BASE/src/hook
    mkdir -p $REMOTE_BASE/logs/hook_tests
    echo '目录已创建'
"

# ---- Step 2: 传输 hook 源码和构建文件 ----
echo ""
echo "[2/4] 传输 hook 源码和构建文件..."

# Hook source
scp $SCP_OPTS "$SCRIPT_DIR/libconnect_hook.c" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/src/hook/"

# CMakeLists (optional, can use gcc directly)
scp $SCP_OPTS "$SCRIPT_DIR/CMakeLists.txt" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/src/hook/"

# Test script
scp $SCP_OPTS "$SCRIPT_DIR/test_connect_hook.sh" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/share/test_connect_hook.sh"

# ---- Step 3: 确保 Echo 服务端已部署 ----
echo ""
echo "[3/4] 检查 Echo 服务端..."
ECHO_PROJECT_SERVER="$PROJECT_DIR/os-agent-integration/echo/memory_echo_server.py"
if [ -f "$ECHO_PROJECT_SERVER" ]; then
    ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "mkdir -p $REMOTE_BASE/bin"
    scp $SCP_OPTS "$ECHO_PROJECT_SERVER" \
        "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/bin/kylin-memory-echo-server"
    ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" \
        "chmod +x $REMOTE_BASE/bin/kylin-memory-echo-server"
    echo "  ✅ Echo 服务端已传输"
else
    echo "  ⚠️  Echo 服务端未找到，请先运行 os-agent-integration/echo/deploy_echo.sh"
fi

# ---- Step 4: 设置权限并编译 ----
echo ""
echo "[4/4] 编译和设置权限..."
ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "
    set -e
    chmod +x $REMOTE_BASE/share/test_connect_hook.sh

    echo '=== 编译 libconnect_hook.so ==='
    cd $REMOTE_BASE/src/hook
    gcc -shared -fPIC -O2 -ldl -Wall -Wextra \
        -o $REMOTE_BASE/lib/libconnect_hook.so \
        libconnect_hook.c

    echo '=== 验证 .so ==='
    file $REMOTE_BASE/lib/libconnect_hook.so
    nm -D $REMOTE_BASE/lib/libconnect_hook.so | grep connect

    echo '✅ 编译完成'
"

echo ""
echo "=========================================="
echo " 部署完成!"
echo "=========================================="
echo ""
echo "远程路径: $REMOTE_BASE"
echo ""
echo "下一步 (在麒麟 VM 上):"
echo ""
echo "  1. 运行完整的集成测试:"
echo "     ssh $KYLIN_USER@$KYLIN_HOST"
echo "     bash $REMOTE_BASE/share/test_connect_hook.sh"
echo ""
echo "  2. 手动验证 hook 拦截:"
echo "     cd $REMOTE_BASE"
echo "     # 先启动 Echo 服务"
echo "     python3 $REMOTE_BASE/bin/kylin-memory-echo-server --dev &"
echo "     # 编译测试客户端"
echo "     echo '#include ...' | gcc -std=c11 -x c - -o /tmp/test_hook"
echo "     # 测试 hook"
echo "     CONNECT_HOOK_DEBUG=1 LD_PRELOAD=$REMOTE_BASE/lib/libconnect_hook.so \\
echo "       $REMOTE_BASE/bin/echo_client --method health"
echo ""
echo "  3. 针对真实 kylin-aiassistant 测试 (需先编译/安装):"
echo "     CONNECT_HOOK_DEBUG=1 \\
echo "     LD_PRELOAD=$REMOTE_BASE/lib/libconnect_hook.so \\
echo "       /opt/kaiming/layers/stable/x86_64/app/cn.kylin.kylin-aiassistant/.../files/bin/kylin-aiassistant"
echo ""
echo "  4. 环境变量参考:"
echo "     CONNECT_HOOK_MATCH='kylin-ai-runtime-unix'  # 匹配子串 (默认)"
echo "     CONNECT_HOOK_REDIRECT='/tmp/kylin-memory-echo/echo.sock'  # 重定向目标 (默认)"
echo "     CONNECT_HOOK_DEBUG=1  # 启用调试日志"
echo ""
echo "  5. 清理:"
echo "     rm -f $REMOTE_BASE/lib/libconnect_hook.so"
echo "     rm -rf $REMOTE_BASE/logs/hook_tests"