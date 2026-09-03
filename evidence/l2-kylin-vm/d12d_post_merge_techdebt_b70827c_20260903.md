# D12D Post-Merge 技术债跟进 —— 麒麟 VM L2（b70827c 绑定）

- 任务卡：`docs/day12/10_d12d_post_merge_techdebt_task_card.md`（D12D-PostMerge-01）
- 分支 / 被测提交：`fix/d12d-post-merge-techdebt` @ `b70827c5e9c9e014ae2c025eb01d0adfaabd4ef9`
- 执行日期：2026-09-03
- VM：`kylin-agent-pc`，银河麒麟桌面 V11（VERSION_ID=v11, KYLIN_RELEASE_ID=2603），kernel `6.6.0-76-generic`
- 用户：`kylin-agent`（uid=1000），`$XDG_RUNTIME_DIR=/run/user/1000`
- 执行前 VirtualBox 快照：`d12d-post-merge-pre-b70827c-20260903-1828`（可回退）

## 结论摘要

| TD | 状态变化 | 关键证据 |
|---|---|---|
| TD-KYSEC-001 | Open → In Progress | 单二进制 exectl 授权→执行→撤销真实 PASS；全局策略未改动 |
| TD-DEPLOY-001 | Open → In Progress | 部署树对齐 b70827c + install RC=0 + rollback 资产就绪 |
| TD-049 | Open → In Progress | 正式 Socket 0700/0600 路径权限 PASS；legacy socket 无候选 |
| TD-055 | 保持 Open | 服务重启 PASS；OS 重启 / C→D→B 真实输入未执行 |

## 执行动作清单

1. **只读基线核对**（`git bundle` 传输 + VM `git checkout b70827c`）：
   - 原 VM 部署树 `~/kylinOS-agent-memory` 为复制树，`.git` 指向失效主机 worktree 路径（`E:/Kylin-memory-dev/main/.git/worktrees/d8d-impl-build`），无法提供 `git rev-parse` 身份。
   - 以 `b70827c.bundle`（SHA-256 `438586a60602b3fe2ccf763b0a1d35ef97ab68156e7f132971ea6fa88e140130`）在 VM 建真实 checkout，`HEAD=b70827c`，`git status` clean（仅新增 verify 脚本为 untracked）。
   - 原树保留为 `~/kylinOS-agent-memory.b70827c-backup`（回退资产）。
2. **只读 verify**（`scripts/verify_d12d_post_merge_techdebt_vm.sh --output …`，RC=0）：
   - identity/commit/user/kernel 记录；KySec 模块/服务/工具 help/TPM-bypass 采集；
   - wrapper/unit/venv 依赖/install 脚本 bash -n；UDS `memory.retrieve` → `ok`，`context_count=0`，`degraded=false`（真实空上下文降级，非生产级检索）。
   - 敏感标记 journal 扫描：0 命中。
   - 此日志为安装前基线：`~/.config/kylin-memory` 尚不存在，`stat` 记录了 RC=1；最终权限结论仅取安装后的 `1834` 日志。
3. **部署对齐 b70827c + install**：
   - `packaging/systemd/kylin-memory.service`（含 `RuntimeDirectoryMode=0700`）安装到 `~/.config/systemd/user/`（旧 unit 已 `.bak` 备份），`daemon-reload` + `restart`；
   - `install_kylin_memory.sh install` RC=0：wrapper/unit 均生成 `.bak.20260903_183250` 备份，socket OK，两次重启 active。
   - 校验：RuntimeDir `700`、config/share `700`、socket `600`、DB `600`。
4. **--service-restart 模式**（`verify_...sh --service-restart --output …`，RC=0）：restart 后 active，socket 存在，UDS `memory.retrieve` ok。
5. **KySec 单二进制验证**（授权范围：人工确认 CLI 参数与目标二进制后执行）：
   - 候选：`/bin/true` 副本 `~/.local/share/kylin-memory/kysec_probe_true`（SHA-256 `3897d1f00041be1a0fecb71c7357547e37c548e57821c652ffe39a9583d01679`）；
   - 流程：`kysec_get` BEFORE=unknown → `sudo kysec_set -n exectl -v verified` → `kysec_get` AFTER=verified → 执行 ok → `sudo kysec_set -n exectl -x` → AFTER=unknown → 删除副本。
   - 全局策略核对前后均 `exec: off`（未开启、未写全局策略）；日志不含密码（`sudo -n` 凭据已提前缓存，无密码回显）。
6. **C→D→B 真实输入**：本 VM 无 kylin-memory-client 编译产物、无 Kaiming Hook 输入链路（助手 GUI 驱动）→ 未执行，TD-055 保持 Open。

## 证据文件与 SHA-256

| 文件 | SHA-256 |
|---|---|
| `d12d-post-merge-verify-readonly-20260903_1831.log` | `0b717e30779e921d9a0dc88c3dc30462bcc55a10e0f8207a16b9d48a2cea2cbe` |
| `d12d-post-merge-verify-restart-20260903_1832.log` | `78dbd3e955a2a85694120d83cbb26321e8c91326cbfd045f003622c5fc6d79c0` |
| `d12d-post-merge-kysec-b70827c-20260903.log` | `5d508ece82f3f01f1e422691f21499d0f3374deb6c5b6da0ad30e083b36111f1` |
| `d12d-post-merge-install-b70827c-20260903.log` | `f1d76957ab0d16a56da8a96e0e5b6689910e077f6a09029cb7f04b616bc3de1c` |
| `d12d-post-merge-verify-final-readonly-20260903_1834.log` | `f0e0031b83036581f7bfe0a0dbc405da4713c53f9dbadbb0b4d2c4b82fcbd523` |

安装日志不单独打印 Git SHA；其部署提交绑定由同一 VM、同一时间窗中安装前/后两份 verify 原始日志的 `tested_commit=b70827c5e9c9e014ae2c025eb01d0adfaabd4ef9` 共同支撑。该关联已登记为限制，不能替代日志内的独立提交标识。

## 边界声明（证据诚实）

- 本批为 **VM L2 只读/受控验证**，不构成成品环境（生产麒麟）systemd 测试通过声明。
- `memory.retrieve` 空上下文为真实降级路径，不等于生产级检索闭环；D→C→B 未用真实 C 轨输入跑通。
- KySec exec 全局为 `off`，仅验证单文件 exectl 规则写入/显示/撤销，未做强制阻断验证。
- TD 状态变化为 evidence-based 初判，**关闭须经 D 主审 + Reviewer E 复核**（见技术债登记表）。
