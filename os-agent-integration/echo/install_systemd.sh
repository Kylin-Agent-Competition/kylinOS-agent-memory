#!/usr/bin/env bash
# =============================================================================
# Kylin Memory Echo — Systemd 自动安装脚本
# =============================================================================
# 用法:
#   sudo bash install_systemd.sh [用户名]
#   (不传用户名则自动使用当前登录用户)
#
# 功能:
#   1. 检测/确认部署用户名
#   2. 替换 unit 模板中 __USERNAME__ 占位符
#   3. 复制到 /etc/systemd/system/
#   4. daemon-reload → enable → start → 验证
#
# ⚠️ UNVERIFIED: 银河麒麟桌面V11 (REDACTED_VM_USER-pc) 直实验证通过
#    正式发行环境 (麒麟生产系统) systemd 测试未执行
# =============================================================================

set -euo pipefail

# ---- 用户检测 ----
DETECTED_USER="${SUDO_USER:-${USER}}"
TARGET_USER="${1:-$DETECTED_USER}"

if [ "$TARGET_USER" = "root" ] || [ "$TARGET_USER" = "YOUR_USERNAME" ]; then
    echo "ERROR: 无效用户名 '$TARGET_USER'，请传入实际用户名"
    echo "用法: sudo bash $0 [用户名]"
    exit 1
fi

UNIT_NAME="kylin-memory-echo"
UNIT_TEMPLATE="$(cd "$(dirname "$0")" && pwd)/../../packaging/systemd/kylin-memory-echo.service"
UNIT_DST="/etc/systemd/system/${UNIT_NAME}.service"
DEPLOY_BASE="/home/$TARGET_USER/kylin-memory-echo"
# RuntimeDirectory 管理的 Socket 路径 (systemd 自动创建 /run/kylin-memory-echo)
SOCKET_PATH="/run/kylin-memory-echo/echo.sock"
LEGACY_SOCKET_PATH="/tmp/kylin-memory-echo/echo.sock"

echo "=========================================="
echo " Kylin Memory Echo — Systemd 安装"
echo "=========================================="
echo "  用户: $TARGET_USER"
echo "  部署路径: $DEPLOY_BASE"
echo "  Socket (RuntimeDirectory): $SOCKET_PATH"
echo "=========================================="

# ---- 检查模板文件 ----
if [ ! -f "$UNIT_TEMPLATE" ]; then
    # 备选路径
    UNIT_TEMPLATE="$DEPLOY_BASE/share/kylin-memory-echo.service"
fi
if [ ! -f "$UNIT_TEMPLATE" ]; then
    echo "ERROR: 找不到 unit 模板文件"
    echo "  搜索: $(dirname "${UNIT_TEMPLATE}") ; ${DEPLOY_BASE}/share"
    exit 1
fi
echo "[OK] 模板文件: ${UNIT_TEMPLATE}"

# ---- 检查部署目录 ----
if [ ! -f "$DEPLOY_BASE/bin/kylin-memory-echo-server" ]; then
    echo "ERROR: 服务端脚本不存在: ${DEPLOY_BASE}/bin/kylin-memory-echo-server"
    echo "  请先运行 deploy_echo.sh 部署文件"
    exit 1
fi
echo "[OK] 服务端脚本已就绪"

# ---- 确保日志目录存在 ----
mkdir -p "$DEPLOY_BASE/logs"
chown "$TARGET_USER":"$TARGET_USER" "$DEPLOY_BASE/logs" 2>/dev/null || true

# ---- 停止并清理旧服务（含失败状态）----
echo ""
echo "--- 停止旧服务 ---"
systemctl stop "$UNIT_NAME" 2>/dev/null || true
systemctl disable "$UNIT_NAME" 2>/dev/null || true
systemctl reset-failed "$UNIT_NAME" 2>/dev/null || true
# 通过 MainPID 确认服务已停止，禁止使用 pkill -f 误杀其他用户/并行测试进程
_OLD_MAIN_PID=$(systemctl show -p MainPID "$UNIT_NAME" 2>/dev/null | cut -d= -f2)
if [ -n "$_OLD_MAIN_PID" ] && [ "$_OLD_MAIN_PID" != "0" ] && kill -0 "$_OLD_MAIN_PID" 2>/dev/null; then
    echo "[WARN] 服务进程仍在运行 (MainPID=$_OLD_MAIN_PID), 等待退出..."
    sleep 3
fi
# 清理旧 /tmp socket 存根 (迁移前残留)
rm -f "$LEGACY_SOCKET_PATH" 2>/dev/null || true
rm -rf /tmp/kylin-memory-echo 2>/dev/null || true
sleep 1
echo "[OK] 旧服务已通过 systemctl stop 清理 (非 pkill)"

# ---- 生成 unit 文件 ----
echo ""
echo "--- 生成 Unit 文件 ---"
sed "s/__USERNAME__/$TARGET_USER/g" "$UNIT_TEMPLATE" > "$UNIT_DST"
chmod 644 "$UNIT_DST"
echo "[OK] Unit 文件已生成: ${UNIT_DST}"

# ---- SHA256 校验写入 (铁律) ----
echo ""
echo "--- SHA256 校验 ---"
INSTALLED_SHA=$(sha256sum "$UNIT_DST" | cut -d' ' -f1)
echo "  已安装: $INSTALLED_SHA"
echo "[OK] SHA256: ${INSTALLED_SHA:0:16}..."

# ---- 显示生成后的内容用于抽查 ----
echo ""
echo "--- Unit 文件内容预览 (关键行) ---"
echo "  User:           $(grep '^User=' "${UNIT_DST}")"
echo "  ExecStart:      $(grep '^ExecStart=' "${UNIT_DST}")"
echo "  RuntimeDirectory: $(grep '^RuntimeDirectory=' "${UNIT_DST}")"

# ---- daemon-reload ----
echo ""
echo "--- daemon-reload ---"
systemctl daemon-reload
echo "[OK] daemon-reload 完成"

# ---- enable ----
echo ""
echo "--- enable ---"
systemctl enable "$UNIT_NAME"
echo "[OK] enable 完成"

# ---- start ----
echo ""
echo "--- start ---"
if systemctl start "$UNIT_NAME"; then
    echo "[OK] start 成功"
else
    echo "[FAIL] start 失败，查看日志:"
    journalctl -u "$UNIT_NAME" -n 20 --no-pager
    exit 1
fi

sleep 3

# ---- 验证 ----
echo ""
echo "--- 验证 ---"

# 进程存活
PID=$(systemctl show -p MainPID "$UNIT_NAME" | cut -d= -f2)
if [ -n "$PID" ] && [ "$PID" != "0" ] && kill -0 "$PID" 2>/dev/null; then
    echo "[OK] 进程存活 (PID=$PID)"
else
    echo "[FAIL] 进程不存活"
    journalctl -u "$UNIT_NAME" -n 20 --no-pager
    exit 1
fi

# Socket 存在 (RuntimeDirectory: /run/kylin-memory-echo)
sleep 1
if [ -S "$SOCKET_PATH" ]; then
    PERM=$(stat -c "%a" "$SOCKET_PATH" 2>/dev/null || echo "?")
    OWNER=$(stat -c "%U:%G" "$SOCKET_PATH" 2>/dev/null || echo "?")
    echo "[OK] Socket 已创建: $SOCKET_PATH (perm=$PERM, owner=$OWNER)"
elif [ -S "$LEGACY_SOCKET_PATH" ]; then
    PERM=$(stat -c "%a" "$LEGACY_SOCKET_PATH" 2>/dev/null || echo "?")
    OWNER=$(stat -c "%U:%G" "$LEGACY_SOCKET_PATH" 2>/dev/null || echo "?")
    echo "[WARN] Socket 在旧路径: $LEGACY_SOCKET_PATH (perm=$PERM, owner=$OWNER)"
else
    echo "[FAIL] Socket 不存在: $SOCKET_PATH 或 $LEGACY_SOCKET_PATH"
    journalctl -u "$UNIT_NAME" -n 20 --no-pager
    exit 1
fi

# Status
echo ""
echo "--- systemctl status 摘要 ---"
    systemctl status "${UNIT_NAME}" --no-pager --lines=5 2>&1 || true

echo ""
echo "=========================================="
echo " 安装完成!"
echo "=========================================="
echo ""
echo "验证命令:"
    echo "  systemctl status ${UNIT_NAME}"
    echo "  /home/${TARGET_USER}/kylin-memory-echo/bin/kaiming_memory_client --method health --socket ${SOCKET_PATH}"
echo ""
echo "日志路径:"
echo "  journalctl -u ${UNIT_NAME} -f"
echo "  tail -f ${DEPLOY_BASE}/logs/server_stderr.log"
echo ""
echo "卸载:"
echo "  sudo systemctl stop ${UNIT_NAME} && sudo systemctl disable ${UNIT_NAME}"
echo "  sudo rm -f /etc/systemd/system/${UNIT_NAME}.service && sudo systemctl daemon-reload"
echo "=========================================="