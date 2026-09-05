# Packaging

## 模块定位

负责将 Memory Service 及 Bridge 打包为可部署的发行包，支持 systemd 服务和 Kaiming 包两种分发方式。

## 当前状态（D14A 更新）

- **`release/`（新增，D14A）**：正式 A 轨发布包构建与 systemd 安装/卸载/验证脚本。
  - 产出：`dist/kylin-memory-a-d14a-<version>/`（自包含：runtime/app + runtime/bridge +
    runtime/python + bin/kylin-memory-server 可重定位 launcher + migrations + manifest + SHA256SUMS）。
  - 契约：`docs/day14/00_d14a_release_package_contract.md`。
  - **无源码 checkout / 无个人 venv / 无硬编码开发者路径依赖**。
- **`systemd/`（D11D 骨架，HOST_VERIFIED）**：历史 systemd unit 与 D11D 安装脚本（仍依赖 `--repo`
  与已有 venv，已被 `release/` 取代为 D14A 正式入口，保留作历史参考）。
- **`kaiming/`**：仅目录与职责边界，尚无生产实现（D14A 默认 deferred / out-of-scope，待 D 主审确认）。

## 子目录

| 目录 | 说明 | 状态 |
|------|------|------|
| `release/` | D14A 正式发布包构建 + systemd install/uninstall/verify | **实现完成（D14A）** |
| `systemd/` | 历史 systemd unit 与 D11D 安装脚本 | D11D 骨架（HOST_VERIFIED，历史） |
| `kaiming/` | Kaiming 包打包配置与脚本 | 目录边界（无生产实现，deferred） |

## 验收要求

| 层级 | 要求 |
|------|------|
| **L1** | 发布包构建 + 本地 smoke（install → start → real SDK → restart → rollback） |
| **L3** | 干净麒麟 VM 仅凭发布包安装、调用真实 SDK、异常恢复、D13A 可比性能、无残留依赖 |
| **L2** | 麒麟 VM 中 systemd 服务正常启停（D11D 已验，D14A 发布形态待 L3 复核） |

## 快速开始（D14A）

```bash
# 1. 在具备 python3-dev + cmake + 真实 SDK 的麒麟 VM 上构建发布包
bash packaging/release/build_release_package.sh --source-commit $(git rev-parse HEAD)

# 2. 在干净 VM 上安装（仅发布包 + 前置系统依赖）
bash dist/kylin-memory-a-d14a-0.1.0-d14a/systemd/install.sh install

# 3. 验证
bash dist/kylin-memory-a-d14a-0.1.0-d14a/systemd/verify.sh

# 4. 回退
bash dist/kylin-memory-a-d14a-0.1.0-d14a/systemd/uninstall.sh rollback
```