#!/usr/bin/env bash
# =============================================================================
# D14A systemd --user uninstall / rollback（无源码/无个人 venv 依赖）
# 用法: bash uninstall.sh rollback [--keep-unit] [--keep-prefix]
#   默认删除 install_prefix、恢复 unit/symlink 备份。
#   --keep-prefix: 保留已安装的发布包目录（仅停止/禁用服务 + 移除 symlink/unit）
# 升级回退（PR#152 D14A R2）：先读取事务元数据
#   ${XDG_STATE_HOME:-$HOME/.local/state}/kylin-memory/d14a-install-txn/txn.meta
#   存在且记录有旧状态时，精确恢复旧 launcher（普通文件字节 / symlink target）、
#   旧 unit（字节恢复 + cmp 自检）、旧 prefix（目录级回迁），任一步失败即 fail-closed：
#   非零退出 + 可诊断错误，且不删除事务目录与备份体（绝不留错向清理）。
#   无事务、或事务记录为“无旧状态”时，回到 clean-state removal 语义（含清理历史
#   *.bak.*）。存在安装事务时 rollback 总是完整恢复旧状态（--keep-* 仅作用于
#   无事务清理路径）。
# =============================================================================
set -euo pipefail

UNIT_NAME="kylin-memory"
UNIT_DST="$HOME/.config/systemd/user/${UNIT_NAME}.service"
BIN_SYMLINK="$HOME/.local/bin/kylin-memory-server"
INSTALL_PREFIX="${INSTALL_PREFIX:-${XDG_DATA_HOME:-$HOME/.local/share}/kylin-memory-d14a}"
TXN_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/kylin-memory/d14a-install-txn"
KEEP_UNIT=0
KEEP_PREFIX=0

[ "${1:-}" = "rollback" ] || { echo "用法: $0 rollback [--keep-unit] [--keep-prefix]" >&2; exit 2; }
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --keep-unit) KEEP_UNIT=1; shift ;;
    --keep-prefix) KEEP_PREFIX=1; shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[d14a-rollback] $*"; }
die() { echo "[d14a-rollback] ERROR: $*" >&2; exit 1; }
# restore fail-closed：任一步恢复失败即中止，事务与备份体一律保留
restore_fail() {
  echo "[d14a-rollback] ERROR: $*（事务与备份保留于 $TXN_DIR，未删除）" >&2
  exit 1
}

systemctl --user stop "$UNIT_NAME" 2>/dev/null || true
systemctl --user disable "$UNIT_NAME" 2>/dev/null || true

# ── 解析事务元数据（存在 txn.meta 时进入事务化路径） ──
META="$TXN_DIR/txn.meta"
TXN_ACTIVE=0
TXN_INSTALL_PREFIX=""
TXN_UNIT_PATH=""
TXN_BIN_SYMLINK_PATH=""
TXN_OLD_PREFIX_BACKUP=""
TXN_OLD_PREFIX_DIR=""
TXN_OLD_UNIT_BACKUP=""
TXN_OLD_UNIT_FILE=""
TXN_OLD_LAUNCHER_KIND=""
TXN_OLD_LAUNCHER_FILE=""
TXN_OLD_LAUNCHER_TARGET=""
if [ -f "$META" ]; then
  TXN_ACTIVE=1
  local_txn_format=""
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    key="${line%%=*}"
    val="${line#*=}"
    case "$key" in
      TXN_FORMAT) local_txn_format="$val" ;;
      INSTALL_PREFIX) TXN_INSTALL_PREFIX="$val" ;;
      UNIT_PATH) TXN_UNIT_PATH="$val" ;;
      BIN_SYMLINK_PATH) TXN_BIN_SYMLINK_PATH="$val" ;;
      OLD_PREFIX_BACKUP) TXN_OLD_PREFIX_BACKUP="$val" ;;
      OLD_PREFIX_DIR) TXN_OLD_PREFIX_DIR="$val" ;;
      OLD_UNIT_BACKUP) TXN_OLD_UNIT_BACKUP="$val" ;;
      OLD_UNIT_FILE) TXN_OLD_UNIT_FILE="$val" ;;
      OLD_LAUNCHER_KIND) TXN_OLD_LAUNCHER_KIND="$val" ;;
      OLD_LAUNCHER_FILE) TXN_OLD_LAUNCHER_FILE="$val" ;;
      OLD_LAUNCHER_TARGET) TXN_OLD_LAUNCHER_TARGET="$val" ;;
      *) : ;;
    esac
  done < "$META"
  [ "$local_txn_format" = "1" ] || die "事务元数据格式未知（TXN_FORMAT=$local_txn_format），保留事务目录: $TXN_DIR"
  [ -n "$TXN_INSTALL_PREFIX" ] || die "事务元数据缺少 INSTALL_PREFIX，保留事务目录: $TXN_DIR"
  [ -n "$TXN_UNIT_PATH" ] || die "事务元数据缺少 UNIT_PATH，保留事务目录: $TXN_DIR"
  [ -n "$TXN_BIN_SYMLINK_PATH" ] || die "事务元数据缺少 BIN_SYMLINK_PATH，保留事务目录: $TXN_DIR"
fi

# ── clean-state removal：无事务、或事务无旧状态时使用 ──
# 路径参数（M-3）：调用方可传入事务记录路径（TXN_*），清理不依赖 rollback 时的
# 实时默认/env 派生值；默认参数回落实时变量（无事务清理路径）。
clean_state_removal() {
  local c_unit="${1:-$UNIT_DST}"
  local c_symlink="${2:-$BIN_SYMLINK}"
  local c_prefix="${3:-$INSTALL_PREFIX}"

  if [ -e "$c_symlink" ] || [ -L "$c_symlink" ]; then
    rm -f "$c_symlink" || die "无法移除 symlink: $c_symlink"
    log "已移除 symlink: $c_symlink"
  fi
  if [ "$KEEP_UNIT" -eq 0 ]; then
    rm -f "$c_unit" || die "无法移除 unit: $c_unit"
    rm -f "$c_unit".bak.* 2>/dev/null || true
    systemctl --user daemon-reload || true
    log "已移除 unit: $c_unit"
  else
    log "已停止并禁用 ${UNIT_NAME}（--keep-unit）"
  fi
  if [ "$KEEP_PREFIX" -eq 0 ] && [ -d "$c_prefix" ]; then
    rm -rf "$c_prefix" || die "无法移除 install_prefix: $c_prefix"
    rm -rf "$c_prefix".bak.* 2>/dev/null || true
    log "已移除 install_prefix: $c_prefix"
  fi
}

# ── 事务化恢复：launcher → unit → prefix，任一步失败即 fail-closed ──
tx_rollback() {
  log "存在安装事务（$TXN_DIR），开始精确恢复旧状态…"
  if [ "$KEEP_UNIT" -eq 1 ] || [ "$KEEP_PREFIX" -eq 1 ]; then
    log "注：--keep-* 仅作用于无事务清理路径；检测到旧状态时按事务语义完整恢复"
  fi

  # 1) 旧 launcher：普通文件字节恢复 / symlink target 重建 / 无则保持移除
  case "$TXN_OLD_LAUNCHER_KIND" in
    file)
      [ -f "$TXN_OLD_LAUNCHER_FILE" ] || restore_fail "事务缺少旧 launcher 备份: $TXN_OLD_LAUNCHER_FILE"
      rm -f "$TXN_BIN_SYMLINK_PATH" || restore_fail "无法移除新 launcher: $TXN_BIN_SYMLINK_PATH"
      cp -f "$TXN_OLD_LAUNCHER_FILE" "$TXN_BIN_SYMLINK_PATH" \
        || restore_fail "旧 launcher 恢复失败: $TXN_BIN_SYMLINK_PATH"
      cmp -s "$TXN_OLD_LAUNCHER_FILE" "$TXN_BIN_SYMLINK_PATH" \
        || restore_fail "旧 launcher 恢复后字节不一致: $TXN_BIN_SYMLINK_PATH"
      log "已恢复旧 launcher（普通文件）: $TXN_BIN_SYMLINK_PATH"
      ;;
    symlink)
      [ -n "$TXN_OLD_LAUNCHER_TARGET" ] || restore_fail "事务缺少旧 symlink target"
      rm -f "$TXN_BIN_SYMLINK_PATH" || restore_fail "无法移除新 launcher: $TXN_BIN_SYMLINK_PATH"
      ln -s "$TXN_OLD_LAUNCHER_TARGET" "$TXN_BIN_SYMLINK_PATH" \
        || restore_fail "旧 symlink 重建失败: $TXN_BIN_SYMLINK_PATH"
      [ "$(readlink "$TXN_BIN_SYMLINK_PATH")" = "$TXN_OLD_LAUNCHER_TARGET" ] \
        || restore_fail "旧 symlink 恢复校验失败: $TXN_BIN_SYMLINK_PATH"
      log "已恢复旧 launcher（symlink → $TXN_OLD_LAUNCHER_TARGET）"
      ;;
    none)
      rm -f "$TXN_BIN_SYMLINK_PATH" || restore_fail "无法移除 launcher: $TXN_BIN_SYMLINK_PATH"
      log "旧 launcher 本不存在，保持移除"
      ;;
    *)
      restore_fail "未知旧 launcher 类型: $TXN_OLD_LAUNCHER_KIND"
      ;;
  esac

  # 2) 旧 unit：字节恢复 + cmp 自检；无旧 unit 则移除新 unit
  if [ "$TXN_OLD_UNIT_BACKUP" = present ]; then
    [ -f "$TXN_OLD_UNIT_FILE" ] || restore_fail "事务缺少旧 unit 备份: $TXN_OLD_UNIT_FILE"
    rm -f "$TXN_UNIT_PATH" || restore_fail "无法移除新 unit: $TXN_UNIT_PATH"
    cp -f "$TXN_OLD_UNIT_FILE" "$TXN_UNIT_PATH" || restore_fail "旧 unit 恢复失败: $TXN_UNIT_PATH"
    cmp -s "$TXN_OLD_UNIT_FILE" "$TXN_UNIT_PATH" \
      || restore_fail "旧 unit 恢复后字节不一致: $TXN_UNIT_PATH"
    log "已恢复旧 unit: $TXN_UNIT_PATH"
  else
    rm -f "$TXN_UNIT_PATH" || restore_fail "无法移除新 unit: $TXN_UNIT_PATH"
    log "旧 unit 本不存在，已移除新 unit"
  fi
  systemctl --user daemon-reload || restore_fail "daemon-reload 失败"

  # 3) 旧 prefix：目录级回迁；无旧 prefix 则移除新区
  if [ "$TXN_OLD_PREFIX_BACKUP" = present ]; then
    [ -d "$TXN_OLD_PREFIX_DIR" ] || restore_fail "事务缺少旧 prefix 备份: $TXN_OLD_PREFIX_DIR"
    rm -rf "$TXN_INSTALL_PREFIX" || restore_fail "无法移除新 prefix: $TXN_INSTALL_PREFIX"
    mkdir -p "$(dirname "$TXN_INSTALL_PREFIX")" || restore_fail "无法创建 prefix 父目录"
    mv -f "$TXN_OLD_PREFIX_DIR" "$TXN_INSTALL_PREFIX" || restore_fail "旧 prefix 回迁失败: $TXN_INSTALL_PREFIX"
    [ -d "$TXN_INSTALL_PREFIX" ] || restore_fail "旧 prefix 回迁后校验失败"
    log "已回迁旧 prefix: $TXN_INSTALL_PREFIX"
  else
    rm -rf "$TXN_INSTALL_PREFIX" || restore_fail "无法移除新 prefix: $TXN_INSTALL_PREFIX"
    log "旧 prefix 本不存在，已移除新 prefix"
  fi

  # 全部恢复成功后才清理事务与历史时间戳备份
  rm -rf "$TXN_DIR" || restore_fail "事务目录清理失败（备份仍需保留）"
  rm -f "$TXN_UNIT_PATH".bak.* 2>/dev/null || true
  rm -rf "$TXN_INSTALL_PREFIX".bak.* 2>/dev/null || true
  log "事务已提交并清理: $TXN_DIR"
}

if [ "$TXN_ACTIVE" -eq 1 ]; then
  HAS_OLD=0
  [ "$TXN_OLD_PREFIX_BACKUP" = present ] && HAS_OLD=1
  [ "$TXN_OLD_UNIT_BACKUP" = present ] && HAS_OLD=1
  [ "$TXN_OLD_LAUNCHER_KIND" != "none" ] && HAS_OLD=1
  if [ "$HAS_OLD" -eq 1 ]; then
    tx_rollback
  else
    log "事务记录为无旧状态，按 clean-state 语义清理"
    # M-3：清理使用事务记录路径（TXN_*），不依赖 rollback 时的实时默认/env 派生值，
    # 保证自定义 install prefix 后不带 INSTALL_PREFIX 的 rollback 也不遗留新 prefix。
    clean_state_removal "$TXN_UNIT_PATH" "$TXN_BIN_SYMLINK_PATH" "$TXN_INSTALL_PREFIX"
    rm -rf "$TXN_DIR"
  fi
else
  clean_state_removal
fi

systemctl --user is-active --quiet "$UNIT_NAME" \
  && { echo "[d14a-rollback] ERROR: 服务仍 active" >&2; exit 1; } || true

log "回退完成：服务已停止/禁用，旧状态已恢复或 clean-state 清理完成"