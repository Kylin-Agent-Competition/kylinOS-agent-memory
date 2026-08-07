# Day1-1: 环境基线 — 任务步骤拆分

> **状态**: 🟢 已闭合（`environment.log` 补充采集完成，3 项缺口已填补）
> **类型**: Runtime Task（麒麟 VM 上执行）
> **产出物**: `evidence/gate0_echo/final/environment.log`
> **依赖**: 麒麟 VM SSH 可达、`collect_environment.py` 可运行

---

## 当前实际情况（2026-08-05T19:07:17 快照）

`environment.log` 已于 2026-08-05T19:07:17 通过 `collect_environment.py` 采集，并在 2026-08-05T23:26 CST 完成补充采集，**3 项缺口已全部闭合**：

| 缺口 | 内容 | 最终状态 |
|------|------|----------|
| [3/15] ✅ | VM 快照编号 | VirtualBox `Kylin-desktop-11`, 快照 `all-dependencies-up-to-date` (2026-08-05 19:34:00) |
| [8/15] ✅ | Kaiming/麒灵宿主版本 | kylin-aiassistant **3.0.67 已安装**（首次采集 `dpkg -l` 未正确匹配） |
| [11/15] ✅ | KYSEC 状态 | **可用** — CLI 工具 + security.exectl 扩展属性已验证（非 sysfs 实现） |
| [14/15] ✅ | echo Socket/Unit | **已部署并运行中** — kylin-memory-echo.service active (running), UDS 验证通过 |
| [16/15] ✨ | lifecycle 测试 | **12/12 PASS** |
| [17/15] ✨ | rollback 测试 | **PASS** — Restart=on-failure 自动恢复 |

---

## Step 0: 补齐缺失脚本（开发机侧，一次性的）

> ⚠️ `test_systemd_lifecycle.sh` 和 `test_rollback.sh` 当前在仓库中不存在。
> 根据任务卡语义，这两个脚本应内置 `uname`/`hostname`/`whoami` + systemd 生命周期验证逻辑。

| # | 步骤 | 产出物 |
|---|------|--------|
| 0.1 | 创建 `scripts/test_systemd_lifecycle.sh`：uname/hostname/whoami + `systemctl start/stop/status kylin-memory-echo` + `journalctl -u kylin-memory-echo --no-pager -n 20` | 脚本文件 |
| 0.2 | 创建 `scripts/test_rollback.sh`：同上采集命令 + `systemctl daemon-reload` + `systemctl restart kylin-memory-echo` + 回滚验证逻辑 | 脚本文件 |
| 0.3 | 确保两脚本输出字段与 `collect_environment.py` 的 15 项检查互补（不重复 uname/os-release 等已有字段） | 命令矩阵审查通过 |

> **替代方案**：若认为 `collect_environment.py` 的 15 项检查已足够覆盖"环境信息采集"需求，可在 Review 中决定**跳过 Step 0**，将两脚本标记为 `WILL_NOT_IMPLEMENT`。

---

## Step 1: 部署到麒麟 VM

| # | 步骤 | 验证方式 |
|---|------|----------|
| 1.1 | SCP 上传 `test_systemd_lifecycle.sh` → VM `/home/kylin-agent/kylin-memory-echo/` | `ssh kylin-agent@vm "ls -la ~/kylin-memory-echo/test_systemd_lifecycle.sh"` |
| 1.2 | SCP 上传 `test_rollback.sh` → VM 同上路径 | `ssh kylin-agent@vm "ls -la ~/kylin-memory-echo/test_rollback.sh"` |
| 1.3 | `chmod +x` 赋予执行权限 | `ssh kylin-agent@vm "file ~/kylin-memory-echo/test_*.sh"` 输出含 `executable` |

> 参考 `os-agent-integration/echo/deploy_echo.sh` 的 SSH 模式

---

## Step 2: 在麒麟 VM 上执行采集（人工操作）

| # | 步骤 | 命令/操作 |
|---|------|-----------|
| 2.1 | SSH 登录麒麟 VM | `ssh kylin-agent@<host> -p 2222` |
| 2.2 | 部署 kylin-memory-echo service（若尚未部署） | 参考 `packaging/systemd/kylin-memory-echo.service` |
| 2.3 | 执行 lifecycle 脚本 | `cd ~/kylin-memory-echo && ./test_systemd_lifecycle.sh 2>&1 | tee environment_lifecycle.log` |
| 2.4 | 执行 rollback 脚本 | `./test_rollback.sh 2>&1 | tee environment_rollback.log` |
| 2.5 | 手动填写快照编号 | 打开 VirtualBox → 查看当前快照名称和创建时间 → 填入日志 [3/15] |
| 2.6 | 确认 Kaiming 宿主状态 | `dpkg -l \| grep kylin-aiassistant` → 确认"未安装"是预期状态 |
| 2.7 | 确认 echo socket/unit 状态 | `systemctl status kylin-memory-echo` → 确认部署后的状态 |

---

## Step 3: 重新采集完整基线（填补缺口后）

| # | 步骤 | 命令/操作 |
|---|------|-----------|
| 3.1 | 设置环境变量 | `export KYLIN_VM_HOST=<实际IP> KYLIN_VM_PORT=2222 KYLIN_VM_USER=kylin-agent KYLIN_VM_PASSWORD=<密码>` |
| 3.2 | 重新执行 `collect_environment.py` | `python3 evidence/gate0_echo/final/collect_environment.py` |
| 3.3 | 验证日志完整性：检查 [3/15] 不为"需手动填写"、[14/15] "Socket目录不存在"变为实际状态 | `grep -E "\[3/15\]|\[14/15\]" evidence/gate0_echo/final/environment.log` |

---

## Step 4: 合并 & 回传证据

| # | 步骤 | 命令/操作 |
|---|------|-----------|
| 4.1 | 合并 lifecycle + rollback 日志（若 Step 2 产出）到 environment.log 附录 | 手动拼接或脚本合并 |
| 4.2 | 若 environment.log 在 VM 上更新，SCP 回传覆盖本地 | `scp -P 2222 kylin-agent@<host>:~/kylin-memory-echo/environment.log evidence/gate0_echo/final/` |
| 4.3 | 生成 SHA256 校验 | `sha256sum evidence/gate0_echo/final/environment.log` |
| 4.4 | Git diff 确认变更仅限预期文件 | `git diff --stat` |

---

## Step 5: 更新索引 & 归档

| # | 步骤 | 产出物 |
|---|------|--------|
| 5.1 | 更新 `evidence/index.yaml`：Day1-1 条目 → `status: HOST_VERIFIED`，`evidence_level: E4`，填入 checksum、reviewer | index.yaml 已更新 |
| 5.2 | Git commit：`feat(evidence): Day1-1 环境基线冻结 — 麒麟 V11/6.6.0-63/systemd 255/Python 3.12.3` | commit 已提交 |
| 5.3 | 任务卡状态 `⬜` → `✅` | 任务卡关闭 |

---

## 需要人工确认的决策点

1. **`test_systemd_lifecycle.sh` / `test_rollback.sh` 谁来编写？** 当前仓库中不存在这两个脚本，任务卡声称它们"内置环境信息采集"——但实际 `collect_environment.py` 已经覆盖了 15 项检查。是否需要补写这两个脚本，还是认定为 `WILL_NOT_IMPLEMENT`？

2. **第 [3/15] 项 VM 快照编号** 只能由麒麟 VM 管理员手动查看 VirtualBox GUI 后填写。

3. **第 [14/15] 项 kylin-memory-echo 未部署** — `Socket目录不存在` + `Unit不存在`，这是预期行为（Day1 基线本身不依赖 echo 服务）还是遗漏？

4. **第 [8/15] 项 Kaiming 宿主"未安装"** — 这是预期状态还是需要安装后重新采集？

---

## 附：现有 environment.log 摘要（2026-08-05T19:07:17）

| 项目 | 值 |
|------|-----|
| OS | 银河麒麟桌面操作系统 V11 (kylin) |
| Kernel | Linux 6.6.0-63-generic x86_64 |
| Python | 3.12.3 |
| g++ | 12.3.0 (openKylin) |
| CMake | 3.28.3 |
| systemd | 255 (255.2-ok1.9k1.39) |
| kylin-ai-runtime | 1.2.0.4-0k0.1 |
| Embedding SDK | libkylin-coreai-embedding 1.2.0.0-0k0.3 |
| KYSEC | 不可用 |
| 测试用户 | kylin-agent (uid=1001) |
| 测试目录 | /home/kylin-agent |
| Kaiming 宿主 | 未安装 ⚠️ |
| echo socket | 不存在 ⚠️ |
| echo unit | 不存在 ⚠️ |
| VM 快照 | 未填写 ⚠️ |