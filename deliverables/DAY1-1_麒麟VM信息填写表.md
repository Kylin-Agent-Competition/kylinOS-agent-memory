# Day1-1: 麒麟 VM 信息填写表

> 请在下表中填写麒麟 VM 的实际信息，填写完成后将用于闭合 `environment.log` 的 3 项缺口。

---

## 1. SSH 连接信息

| 字段 | 值（请填写） | 备注 |
|------|-------------|------|
| Host / IP | `_______________` | 麒麟 VM 的 IP 地址 |
| SSH 端口 | `_______________` | 默认 2222 |
| 登录用户 | `_______________` | 当前使用 `kylin-agent` |
| 登录密码 | `_______________` | 仅本地保存，不提交仓库 |

---

## 2. 虚拟化 / 快照信息（填补 [3/15] 缺口）

| 字段 | 值（请填写） | 备注 |
|------|-------------|------|
| 虚拟化平台 | `VirtualBox` | 如 VirtualBox / VMware / KVM |
| 虚拟机名称 | `Kylin-desktop-11` | VirtualBox 中的 VM 名称 |
| 当前快照名称 | `all-dependencies-up-to-date` | 从 VirtualBox GUI → 快照列表获取 |
| 快照创建时间 | `2026-08-05 19:34:00` | 格式: `YYYY-MM-DD HH:MM:SS` |
| 快照描述 | `Day 1 前干净快照` | 如"Day1 基线前干净快照" |

---

## 3. 操作系统信息（已采集，供核对）

| 字段 | 已采集值 | 是否正确？（✓/✗） | 修正值（如不正确） |
|------|---------|-------------------|-------------------|
| OS 名称 | 银河麒麟桌面操作系统 V11 | `true` | true|
| 内核版本 | Linux 6.6.0-63-generic x86_64 | `true` | true|
| systemd 版本 | 255 (255.2-ok1.9k1.39) | `true` | true|
| Python 版本 | 3.12.3 | 'true` | true|
| g++ 版本 | 12.3.0 (openKylin) | `true` | true|
| CMake 版本 | 3.28.3 | `true` | true|

---

## 4. Kaiming / 麒灵宿主状态（填补 [8/15] 缺口）

| 字段 | 状态 | 说明 |
|------|------|------|
| kylin-aiassistant 是否已安装？ | `[√] 已安装` `[ ] 未安装` | `dpkg -l \| grep kylin-aiassistant` 结果 |
| 如已安装，版本号 | `3.0.67` | |
| 「未安装」是否为预期状态？ | `[ ] 是，预期` `[ ] 否，需安装` | 需与架构师确认 |
| 麒麟 AI Runtime 版本 | `1.2.0.4-0k0.1` ✓ 已采集 | |
| Embedding SDK 版本 | `libkylin-coreai-embedding 1.2.0.0-0k0.3` ✓ 已采集 | |

---

## 5. kylin-memory-echo 服务部署状态（填补 [14/15] 缺口）

| 字段 | 状态 | 说明 |
|------|------|------|
| echo service unit 文件是否存在？ | `[x] 已部署` `[ ] 未部署` | `/etc/systemd/system/kylin-memory-echo.service` |
| echo socket 目录是否存在？ | `[x] 存在` `[ ] 不存在` | `/run/kylin-memory-echo/` |
| echo 服务当前运行状态 | `[x] active (running)` `[ ] inactive` `[ ] 未安装` | `systemctl status kylin-memory-echo` — 自 2026-08-05 20:54:26 CST 起运行 |
| 「未部署」是否为预期状态？ | `[ ] 是，Day1 基线不依赖` `[x] 否，需部署` | 已部署并运行中，无需额外操作 |
| 若需部署，部署用户 | `kylin-agent` | systemd unit 中 `User=kylin-agent`（`__USERNAME__` 占位符已替换） |

---

## 6. 附加采集项（`test_systemd_lifecycle.sh` / `test_rollback.sh`）

| 字段 | 值（请填写） | 说明 |
|------|-------------|------|
| 是否需要编写并运行 lifecycle 脚本？ | `[x] 是` `[ ] 否（跳过 Step 0）` | `_run_section6_final.py` 通过 SSH 执行：daemon-reload → enable → start → stop → start → UDS 验证 |
| lifecycle 测试结果 | `[x] PASS` `[ ] FAIL` `[ ] 未执行` | 12/12 lifecycle 步骤 PASS（无破坏性：保留 unit 文件，仅 stop/start 循环） |
| rollback 测试结果 | `[x] PASS` `[ ] FAIL` `[ ] 未执行` | kill 后 systemd `Restart=on-failure` 自动恢复，socket + UDS 通信均恢复 |
| KYSEC 可用性 | `[x] 可用` ✓ 已验证 (2026-08-05 23:26 CST) | `kysec_set -n exectl -v verified` 写入 → `kysec_get -n exectl` 返回 `verified` → rollback `setfattr -x security.exectl` 清除成功。全链路 authorize→rollback 通过。KYSEC 通过 CLI 工具 + 扩展属性实现，非 /sys/kernel/security/kylin sysfs。 |

---

## 7. 证据元数据（用于 index.yaml 更新）

| 字段 | 值（请填写） | 说明 |
|------|-------------|------|
| Reviewer（审查人） | `谢嘉然` | 人工审查此基线的人 |
| 采集人 | `周子腾` | 在麒麟 VM 上执行采集的人 |
| 采集日期 | `2026-08-05` | 重新采集的日期（若重新采集） |
| environment.log 的 SHA256 | `cdf60d8414e8efb76827737df99ac133f9c00adef3b296e006bc1aec53f78a29` | `sha256sum environment.log` 输出 |
| 已知限制 / 异常 | `/sys/kernel/security/kylin sysfs 不存在（银河麒麟桌面 V11 未暴露该接口）；KYSEC 通过 kysec_set/kysec_get CLI + security.exectl 扩展属性实现，已验证可用。kylin-aiassistant 用户不存在（ACL 跳过）。` | sysfs 缺失不影响 KYSEC 功能；kylin-aiassistant 用户待后续确认 |

---

## 填写说明

1. **打勾项**：`[ ]` 改为 `[x]` 即可，如 `[x] 已安装`
2. **横线项**：将 `_______________` 替换为实际值
3. **核对项**：已采集值正确打 `✓`，不正确填写修正值
4. 填写完成后请通知项目管理员进行 Review，之后：
   - 更新 `evidence/gate0_echo/final/environment.log`（重新采集）
   - 更新 `evidence/index.yaml`（条目状态）