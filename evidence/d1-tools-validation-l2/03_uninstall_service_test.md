# uninstall_memory_service.sh 卸载测试

| 字段 | 内容 |
| --- | --- |
| Commit | 824a3c38fb885387a16029c20940156d97e6d68d |
| 分支 | KylinOS-agent-memory/feat/d1-baseline-setup |
| 银河麒麟版本 | Kylin V11 |
| 架构 | x86_64 |
| VirtualBox 虚拟机 | Kylin-V11-2603-D1-Baseline |
| VirtualBox 快照 | Kylin-V11-2603-D1-Baseline |
| 执行时间 | 2026-07-30T17:03:48+08:00 |
| 操作者 | ZhouYifan |

## 前置条件
- kylin-memory.service 已安装并运行（由 install_memory_service.sh 安装）

## 执行命令
```bash
cd ~/projects/kylin-memory-sdk
./tools/uninstall_memory_service.sh
```

## 退出码
`0` (成功)

## stdout
```
[UNINSTALL] Kylin Memory Service
[UNINSTALL] Capturing pre-uninstall state...
  Pre-uninstall service state: active
[UNINSTALL] Stopping service...
  [OK] Service stopped
[UNINSTALL] Disabling service...
  [OK] Service disabled
[UNINSTALL] Removing unit file...
  [OK] Unit file removed
[UNINSTALL] Reloading systemd daemon...
  [OK] Daemon reloaded
[UNINSTALL] Verifying uninstall...
  [PASS] Service is not active
not-found
  [PASS] Service is not enabled
  [PASS] Unit file removed
[UNINSTALL] Keeping user data (use --purge-data to remove)

=== Uninstall Complete ===
Note: User data directories preserved (use --purge-data to remove).
```

## 执行前状态
- kylin-memory.service: active (running), enabled
- Unit 文件: ~/.config/systemd/user/kylin-memory.service 存在
- 用户数据目录: ~/.config/kylin-memory/, ~/.local/share/kylin-memory/, ~/.local/state/kylin-memory/ 均存在

## 执行后状态
- systemctl --user status kylin-memory.service: "Unit kylin-memory.service could not be found."
- Unit 文件: 已删除
- 残留 symlink: 已清理
- 用户数据目录: 已保留（默认行为，未被 --purge-data 清理）

## 验证项说明
| 检查项 | 结果 |
| --- | --- |
| 服务停止 | PASS (is-active = false) |
| 服务禁用 | PASS (is-enabled = "not-found") |
| Unit 文件删除 | PASS (文件不存在) |
| 残留链接清理 | PASS |
| daemon-reload | PASS |
| 用户数据保留 | PASS (默认行为) |

## 已知限制
- 无