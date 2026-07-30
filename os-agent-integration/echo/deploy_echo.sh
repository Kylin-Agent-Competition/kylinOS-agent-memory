#!/bin/bash
# ============================================================================
# 麒麟 OS Agent 记忆系统 · Gate 0 SPIKE
# Kaiming → UDS Echo 构建、安装、启动、回退一体化脚本
#
# 用法:
#   ./deploy_echo.sh build     # 构建 echo_client
#   ./deploy_echo.sh install   # 安装 echo_server + echo_client 到 /opt/kylin-memory
#   ./deploy_echo.sh start     # 启动 echo_server (直接前台 / systemd --user)
#   ./deploy_echo.sh stop      # 停止 echo_server
#   ./deploy_echo.sh test      # 运行 echo_client 测试
#   ./deploy_echo.sh status    # 检查状态
#   ./deploy_echo.sh backup    # 备份当前状态
#   ./deploy_echo.sh rollback  # 回退到最近备份
#   ./deploy_echo.sh full      # build + install + start + test 一键全流程
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL_DIR="/opt/kylin-memory/echo"
BUILD_DIR="$SCRIPT_DIR/build"
BACKUP_DIR="$INSTALL_DIR/backups"
SOCK_DIR="${XDG_RUNTIME_DIR:-/tmp}/kylin-memory"
SOCK_PATH="$SOCK_DIR/memory.sock"

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── build ─────────────────────────────────────────────────────
cmd_build() {
    log_info "Building echo_client..."
    mkdir -p "$BUILD_DIR"
    cd "$BUILD_DIR"
    cmake "$SCRIPT_DIR" -DCMAKE_BUILD_TYPE=Release
    make -j"$(nproc)"
    log_info "Build complete: $BUILD_DIR/echo_client"
    ls -la "$BUILD_DIR/echo_client"
}

# ── install ───────────────────────────────────────────────────
cmd_install() {
    log_info "Installing to $INSTALL_DIR..."
    sudo mkdir -p "$INSTALL_DIR" "$BACKUP_DIR"
    
    # 备份旧版本
    if [ -f "$INSTALL_DIR/memory_echo_server.py" ]; then
        BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
        log_info "Backing up to $BACKUP_DIR/$BACKUP_NAME"
        sudo mkdir -p "$BACKUP_DIR/$BACKUP_NAME"
        sudo cp "$INSTALL_DIR/memory_echo_server.py" "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true
        sudo cp "$INSTALL_DIR/echo_client" "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true
        echo "$BACKUP_NAME" > /tmp/kylin_memory_last_backup
    fi

    # 安装服务端
    sudo cp "$SCRIPT_DIR/memory_echo_server.py" "$INSTALL_DIR/"
    sudo chmod 755 "$INSTALL_DIR/memory_echo_server.py"
    
    # 安装客户端（如果已构建）
    if [ -f "$BUILD_DIR/echo_client" ]; then
        sudo cp "$BUILD_DIR/echo_client" "$INSTALL_DIR/"
        sudo chmod 755 "$INSTALL_DIR/echo_client"
    fi

    # 安装 systemd user service
    mkdir -p "$HOME/.config/systemd/user/"
    cp "$PROJECT_ROOT/packaging/systemd/kylin-memory-echo.service" "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload 2>/dev/null || true

    log_info "Install complete"
    log_info "  Server: $INSTALL_DIR/memory_echo_server.py"
    log_info "  Client: $INSTALL_DIR/echo_client"
    log_info "  Socket: $SOCK_PATH"
}

# ── start ─────────────────────────────────────────────────────
cmd_start() {
    log_info "Starting Memory Echo Server..."

    # 确保 socket 目录存在
    mkdir -p "$SOCK_DIR"
    chmod 700 "$SOCK_DIR"

    # 清理残留 socket
    rm -f "$SOCK_PATH"

    # 启动方式 1: systemd --user (推荐)
    if command -v systemctl &>/dev/null; then
        log_info "Using systemd --user"
        systemctl --user start kylin-memory-echo 2>/dev/null || {
            log_warn "systemd start failed, trying direct"
            nohup python3 "$INSTALL_DIR/memory_echo_server.py" > /tmp/kylin-memory-echo.log 2>&1 &
            echo $! > /tmp/kylin-memory-echo.pid
        }
    else
        # 启动方式 2: 直接前台
        nohup python3 "$INSTALL_DIR/memory_echo_server.py" > /tmp/kylin-memory-echo.log 2>&1 &
        echo $! > /tmp/kylin-memory-echo.pid
        log_info "Started (PID: $(cat /tmp/kylin-memory-echo.pid))"
    fi

    # 等待 socket 就绪
    for i in $(seq 1 10); do
        if [ -S "$SOCK_PATH" ]; then
            log_info "Socket ready: $SOCK_PATH"
            return 0
        fi
        sleep 0.5
    done
    log_error "Socket not ready after 5s"
    return 1
}

# ── stop ──────────────────────────────────────────────────────
cmd_stop() {
    log_info "Stopping Memory Echo Server..."

    # systemd stop
    systemctl --user stop kylin-memory-echo 2>/dev/null || true

    # 直接 kill
    if [ -f /tmp/kylin-memory-echo.pid ]; then
        PID=$(cat /tmp/kylin-memory-echo.pid)
        kill "$PID" 2>/dev/null && log_info "Killed PID $PID" || true
        rm -f /tmp/kylin-memory-echo.pid
    fi

    # 清理 socket
    rm -f "$SOCK_PATH"
    log_info "Stopped"
}

# ── test ──────────────────────────────────────────────────────
cmd_test() {
    log_info "Running UDS Echo Test..."

    if [ ! -S "$SOCK_PATH" ]; then
        log_error "Socket not found: $SOCK_PATH (run 'start' first)"
        return 1
    fi

    if [ -f "$INSTALL_DIR/echo_client" ]; then
        "$INSTALL_DIR/echo_client"
    elif [ -f "$BUILD_DIR/echo_client" ]; then
        "$BUILD_DIR/echo_client"
    else
        log_error "echo_client not found (run 'build' first)"
        return 1
    fi
}

# ── status ────────────────────────────────────────────────────
cmd_status() {
    echo "=== Memory Echo Service Status ==="
    echo "Socket path: $SOCK_PATH"
    if [ -S "$SOCK_PATH" ]; then
        echo -e "Socket: ${GREEN}EXISTS${NC}"
        ls -la "$SOCK_PATH"
    else
        echo -e "Socket: ${RED}NOT FOUND${NC}"
    fi
    echo ""
    echo "Install dir: $INSTALL_DIR"
    ls -la "$INSTALL_DIR/" 2>/dev/null || echo "(empty)"
    echo ""
    echo "Process:"
    ps aux | grep memory_echo_server | grep -v grep || echo "(not running)"
    echo ""
    if [ -f /tmp/kylin-memory-echo.log ]; then
        echo "=== Last 10 log lines ==="
        tail -10 /tmp/kylin-memory-echo.log
    fi
}

# ── backup ────────────────────────────────────────────────────
cmd_backup() {
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"
    log_info "Creating backup: $BACKUP_NAME"
    sudo mkdir -p "$BACKUP_DIR/$BACKUP_NAME"
    sudo cp "$INSTALL_DIR/memory_echo_server.py" "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true
    sudo cp "$INSTALL_DIR/echo_client" "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || true
    echo "$BACKUP_NAME" > /tmp/kylin_memory_last_backup
    log_info "Backup saved to $BACKUP_DIR/$BACKUP_NAME"
}

# ── rollback ──────────────────────────────────────────────────
cmd_rollback() {
    if [ -f /tmp/kylin_memory_last_backup ]; then
        BACKUP_NAME=$(cat /tmp/kylin_memory_last_backup)
    else
        # 取最新备份
        BACKUP_NAME=$(ls -1t "$BACKUP_DIR" 2>/dev/null | head -1)
    fi

    if [ -z "$BACKUP_NAME" ] || [ ! -d "$BACKUP_DIR/$BACKUP_NAME" ]; then
        log_error "No backup found in $BACKUP_DIR"
        return 1
    fi

    log_warn "Rolling back to: $BACKUP_NAME"

    # 停止服务
    cmd_stop

    # 恢复文件
    if [ -f "$BACKUP_DIR/$BACKUP_NAME/memory_echo_server.py" ]; then
        sudo cp "$BACKUP_DIR/$BACKUP_NAME/memory_echo_server.py" "$INSTALL_DIR/"
        log_info "Restored: memory_echo_server.py"
    fi
    if [ -f "$BACKUP_DIR/$BACKUP_NAME/echo_client" ]; then
        sudo cp "$BACKUP_DIR/$BACKUP_NAME/echo_client" "$INSTALL_DIR/"
        log_info "Restored: echo_client"
    fi

    # 重启服务
    cmd_start
    log_info "Rollback complete"
}

# ── full ──────────────────────────────────────────────────────
cmd_full() {
    log_info "=== FULL DEPLOY PIPELINE ==="
    cmd_build
    cmd_install
    cmd_start
    sleep 1
    cmd_test
    cmd_status
    log_info "=== FULL DEPLOY COMPLETE ==="
}

# ── 主入口 ────────────────────────────────────────────────────
case "${1:-}" in
    build)    cmd_build ;;
    install)  cmd_install ;;
    start)    cmd_start ;;
    stop)     cmd_stop ;;
    test)     cmd_test ;;
    status)   cmd_status ;;
    backup)   cmd_backup ;;
    rollback) cmd_rollback ;;
    full)     cmd_full ;;
    *)
        echo "Usage: $0 {build|install|start|stop|test|status|backup|rollback|full}"
        exit 1
        ;;
esac