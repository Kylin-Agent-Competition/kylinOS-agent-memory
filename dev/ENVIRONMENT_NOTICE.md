# 开发环境 vs 正式发行环境 — 差异说明

## 概述

本文档记录本分支 (`feature/kaiming-uds-echo`) 在 **开发验证环境** (银河麒麟桌面操作系统 V11, REDACTED_VM_USER-pc) 和 **正式发行环境** (麒麟生产系统) 之间的已知差异。

## 1. systemd 配置

### 开发环境 (已验证通过 — ECHO-002 Phase C: 16/16 PASS)

| 项目 | 值 |
|------|-----|
| 主机 | REDACTED_VM_USER-pc |
| 用户 | REDACTED_VM_USER (管理员) |
| systemd unit 路径 | `/etc/systemd/system/kylin-memory-echo.service` |
| 占位符 `__USERNAME__` | REDACTED_VM_USER |
| 部署路径 | `/home/REDACTED_VM_USER/kylin-memory-echo/` |
| 测试时间 | 2026-08-03 |
| 测试结果 | **PASS** — daemon-reload/enable/start/socket/UDS/stop/disable 全部通过 |

### 正式发行环境 (未测试 / 未通过)

| 项目 | 值 |
|------|-----|
| 状态 | **未在正式发行环境中测试** |
| 原因 | 正式发行麒麟生产系统使用不同用户体系和安全策略 |
| 风险 | systemd unit 中的硬编码路径、用户依赖、安全策略可能与生产环境冲突 |
| 结论 | **本 systemd unit 不可直接用于正式发行** |

### 差异点

1. **用户隔离**: 开发环境使用 REDACTED_VM_USER 管理员账号；正式发行环境应使用专用系统账户
2. **路径差异**: 开发环境使用 `/home/REDACTED_VM_USER/`；正式发行应使用标准系统路径
3. **KYSEC 安全策略**: 开发环境 ACL 临时授权 (setfacl u:kylin-aiassistant)；正式发行需定义正式安全策略
4. **安全加固**: 当前 service unit 标注为「开发验证环境，非生产环境」
5. **Service sandboxing**: `NoNewPrivileges=yes` + `RestrictAddressFamilies=AF_UNIX` 仅适用于开发

## 2. 证据记录

在 `evidence/index.yaml` 中:

- **ECHO-001** (SUPERSEDED, v6): 明确记录了 "systemd unit (kylin-memory-echo.service) 未执行完整生命周期测试"
- **ECHO-002** (HOST_VERIFIED, v7): Phase C systemd 16/16 PASS — **但这是在开发环境 REDACTED_VM_USER-pc 上执行的**

## 3. 建议的操作

在正式发布前:

1. 将 systemd unit 中的占位符替换为正式环境配置
2. 使用专用服务账户替代开发者账户
3. 更新安全加固策略 (SELinux/AppArmor/KYSEC)
4. 在麒麟正式发行环境中执行完整 systemd 生命周期测试
5. 移除或标记所有开发环境专用路径

---

*本文档生成于: 2026-08-03*
*关联 Commit: 0a363318ab9a630f2171c56d6873aa1c9436df27*
*关联分支: feature/kaiming-uds-echo*