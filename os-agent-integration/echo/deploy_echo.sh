#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Echo — 部署脚本
# =============================================================================
# 通过 SSH 将 Echo 服务端和客户端传输到麒麟 VM，创建目录，设置权限。
#
# 用法 (在 Windows 开发机上执行):
#   bash deploy_echo.sh <麒麟VM_IP> [麒麟用户名] [SSH端口]
#
# 默认: 用户 kylin, 端口 22
# =============================================================================

set -euo pipefail

# ---- 依赖检查 ----
for cmd in ssh scp; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "❌ 缺少依赖: $cmd 未安装或不在 PATH 中"
        echo "   请安装 OpenSSH 客户端: apt-get install openssh-client (麒麟) 或 Git for Windows (Windows)"
        exit 1
    fi
done

KYLIN_HOST="${1:-}"
KYLIN_USER="${2:-kylin}"
KYLIN_PORT="${3:-22}"

if [ -z "$KYLIN_HOST" ]; then
    echo "Usage: $0 <麒麟VM_IP> [麒麟用户名] [SSH端口]"
    echo "Example: $0 REDACTED_VM_IP kylin 22"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 端口号范围校验
if ! [[ "$KYLIN_PORT" =~ ^[0-9]+$ ]] || [[ "$KYLIN_PORT" -lt 1 || "$KYLIN_PORT" -gt 65535 ]]; then
    echo "❌ 无效端口号: $KYLIN_PORT (需为 1-65535)"
    exit 1
fi
# 主机名/IP 非空校验
if [[ -z "$KYLIN_HOST" ]]; then
    echo "❌ 主机地址不能为空"
    exit 1
fi

SSH_OPTS="-p $KYLIN_PORT -o ConnectTimeout=10 -o StrictHostKeyChecking=no"
SCP_OPTS="-P $KYLIN_PORT -o ConnectTimeout=10 -o StrictHostKeyChecking=no"
REMOTE_BASE="/home/$KYLIN_USER/kylin-memory-echo"

echo "=========================================="
echo " Kylin Memory Echo — 部署"
echo "=========================================="
echo "  目标: $KYLIN_USER@$KYLIN_HOST:$KYLIN_PORT"
echo "  远程路径: $REMOTE_BASE"
echo "=========================================="

# Step 1: 创建远程目录
echo ""
echo "[1/5] 创建远程目录..."
ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "
    mkdir -p $REMOTE_BASE/bin
    mkdir -p $REMOTE_BASE/share
    mkdir -p $REMOTE_BASE/logs
    echo '目录已创建'
"

# Step 2: 传输 Echo 服务端
echo ""
echo "[2/5] 传输 Echo 服务端..."
scp $SCP_OPTS "$SCRIPT_DIR/memory_echo_server.py" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/bin/kylin-memory-echo-server"

# Step 3: 传输 Echo 客户端 (源码)
echo ""
echo "[3/5] 传输 Echo 客户端源码..."
scp $SCP_OPTS "$SCRIPT_DIR/echo_client.cpp" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/"
scp $SCP_OPTS "$SCRIPT_DIR/kaiming_memory_client.cpp" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/"

# Step 4: 传输 CMakeLists.txt 和脚本
echo ""
echo "[4/5] 传输构建文件和脚本..."
scp $SCP_OPTS "$SCRIPT_DIR/CMakeLists.txt" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/"
scp $SCP_OPTS "$SCRIPT_DIR/kysec_authorize.sh" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/share/"
scp $SCP_OPTS "$SCRIPT_DIR/test_rollback.sh" \
    "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/share/"

# 传输 systemd service unit
if [ -f "$PROJECT_DIR/packaging/systemd/kylin-memory-echo.service" ]; then
    scp $SCP_OPTS "$PROJECT_DIR/packaging/systemd/kylin-memory-echo.service" \
        "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/share/"
fi

# 传输证据收集脚本 (如果存在)
EVIDENCE_DIR="$PROJECT_DIR/evidence/gate0_echo"
if [ -d "$EVIDENCE_DIR" ]; then
    echo ""
    echo "[4b/5] 传输证据收集脚本..."
    ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "mkdir -p $REMOTE_BASE/evidence"
    for f in "$EVIDENCE_DIR"/*.py "$EVIDENCE_DIR"/*.sh; do
        if [ -f "$f" ]; then
            scp $SCP_OPTS "$f" "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/evidence/"
        fi
    done
fi

# Step 5: 设置权限
echo ""
echo "[5/5] 设置文件权限..."
ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "
    chmod +x $REMOTE_BASE/bin/kylin-memory-echo-server
    chmod +x $REMOTE_BASE/share/*.sh 2>/dev/null || true
    chmod +x $REMOTE_BASE/evidence/*.py 2>/dev/null || true
    chmod +x $REMOTE_BASE/evidence/*.sh 2>/dev/null || true
    echo '权限已设置'
"

# Step 6: 安装 systemd 服务（可选）
echo ""
echo "[--systemd] 若要安装 systemd 服务，请在麒麟 VM 上执行:"
echo "  sudo bash $REMOTE_BASE/share/install_systemd.sh $KYLIN_USER"
echo ""

# 传输 systemd 安装脚本
if [ -f "$SCRIPT_DIR/install_systemd.sh" ]; then
    scp $SCP_OPTS "$SCRIPT_DIR/install_systemd.sh" \
        "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/share/install_systemd.sh"
    ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "chmod +x $REMOTE_BASE/share/install_systemd.sh"
    echo "[--systemd] install_systemd.sh 已传输"
fi

# ---- 传输 LD_PRELOAD connect() Hook ----
HOOK_DIR="$PROJECT_DIR/os-agent-integration/patches"
if [ -f "$HOOK_DIR/libconnect_hook.c" ]; then
    echo ""
    echo "[--hook] 传输 connect() hook 文件..."
    ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "
        mkdir -p $REMOTE_BASE/src/hook
        mkdir -p $REMOTE_BASE/lib
        mkdir -p $REMOTE_BASE/logs/hook_tests
    "
    scp $SCP_OPTS "$HOOK_DIR/libconnect_hook.c" \
        "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/src/hook/"
    scp $SCP_OPTS "$HOOK_DIR/CMakeLists.txt" \
        "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/src/hook/"
    scp $SCP_OPTS "$HOOK_DIR/test_connect_hook.sh" \
        "$KYLIN_USER@$KYLIN_HOST:$REMOTE_BASE/share/test_connect_hook.sh"
    ssh $SSH_OPTS "$KYLIN_USER@$KYLIN_HOST" "
        chmod +x $REMOTE_BASE/share/test_connect_hook.sh
        echo 'Hook 文件已传输'
    "
    echo "[--hook] libconnect_hook.c + test_connect_hook.sh 已传输"
fi

echo ""
echo "=========================================="
echo " 部署完成!"
echo "=========================================="
echo ""
echo "远程路径: $REMOTE_BASE"
echo ""
echo "下一步 (在麒麟 VM 上):"
echo "  1. 构建客户端 (cmake 干净构建):"
echo "     ssh $KYLIN_USER@$KYLIN_HOST"
echo "     cd $REMOTE_BASE"
echo "     cmake -S . -B build && cmake --build build"
echo "     # 二进制输出: build/echo_client, build/kaiming_memory_client"
echo ""
echo "  2. 启动服务端 (手动 --dev 模式):"
echo "     python3 $REMOTE_BASE/bin/kylin-memory-echo-server --dev &"
echo ""
echo "  3. 测试连通性:"
echo "     $REMOTE_BASE/bin/echo_client --method echo --message 'Hello'"
echo "     $REMOTE_BASE/bin/echo_client --method health"
echo "     $REMOTE_BASE/bin/echo_client --method memory.retrieve"
echo ""
echo "  4. KYSEC 授权:"
echo "     sudo bash $REMOTE_BASE/share/kysec_authorize.sh authorize"
echo ""
echo "  5. Systemd 安装 (推荐，根治服务管理):"
echo "     sudo bash $REMOTE_BASE/share/install_systemd.sh $KYLIN_USER"
echo ""
echo "  6. 回退测试:"
echo "     bash $REMOTE_BASE/share/test_rollback.sh"
echo ""
echo "  7. 收集证据 (在麒麟 VM 上):"
echo "     使用 check_kylin_environment.sh 收集环境基线"
echo "     或手动收集: uname -a > $REMOTE_BASE/logs/environment.log 等"
