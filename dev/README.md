# dev/ — 开发专用目录

## ⚠️ 重要声明

本目录下的所有配置、脚本和文件均为 **开发验证环境** 专用，**不可直接用于生产/正式发行环境**。

本目录从 `packaging/` 迁移而来，目的是防止开发验证过程中产生的临时配置污染正式发行环境。

## 目录结构

| 目录 | 说明 |
|------|------|
| `packaging/systemd/` | systemd service unit — **开发环境配置** |
| `packaging/kaiming/` | Kaiming 包打包配置 — **开发环境配置** |
| `scripts/` | 开发辅助脚本 |

## 与正式环境的差异

- systemd unit 中的 `__USERNAME__` 占位符使用开发账号 (REDACTED_VM_USER)，而非正式发行账号
- 路径使用 `/home/REDACTED_VM_USER/kylin-memory-echo/`，非标准部署路径
- 安全加固标注为「开发验证环境，非生产环境」
- 正式发行环境 (麒麟生产系统) 下的 systemd 测试未通过，详见 `ENVIRONMENT_NOTICE.md`

## 迁移记录

- 迁移日期: 2026-08-03
- 迁移来源: `packaging/`
- 迁移原因: 隔离开发与正式发行环境，防止交叉污染