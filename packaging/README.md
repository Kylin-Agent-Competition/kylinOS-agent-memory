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

以下命令在银河麒麟 V11 x86_64 虚拟机执行；构建产物需先传输到目标 VM。

```bash
# 0. 发布包根（以步骤 1 构建日志尾部 [d14a-build] DONE: <DIST> 为准）
PKG="/tmp/kylin-d14a-dist/kylin-memory-a-d14a-0.1.0-d14a"

# 1. 构建发布包（前置：python3-dev + cmake + 真实 SDK）
#    --source-commit 必填（fail-closed）：打包源必须等于 git HEAD，短 SHA 会被展开为
#    40 位完整 SHA 后写入 manifest；worktree 非 clean 或与 HEAD 不一致时构建直接失败。
bash packaging/release/build_release_package.sh --source-commit <40位HEAD完整SHA>

# 2. 目标 VM 安装（仅发布包 + 前置系统依赖）
#    EXPECT_SOURCE_COMMIT 必填（fail-closed）：即正式包对应的 source identity ——
#    build_release_package.sh 打包时写入包内 manifest.json 的 source_commit（40 位完整 SHA）
#    或冻结构建记录中的同一值。不得从被测包或当前 checkout 推断，不得使用短 SHA；
#    缺失或与 manifest 不符时，安装先于任何复制/迁移/systemd 副作用即非零失败。
INSTALL_PREFIX="${INSTALL_PREFIX:-$HOME/.local/share/kylin-memory-d14a}"
EXPECT_SOURCE_COMMIT=<40位完整SHA，来自正式包对应source identity> \
  bash "$PKG/systemd/install.sh" install

# 3. 验证（真实独立 embedding server 必须先运行；verify 不会代劳启动）
#    embedding server 由独立进程提供（真实 SDK，持默认 socket /tmp/kylin-d14a-embed.sock）：
PYTHONPATH="$PKG/runtime/app:$PKG/runtime/bridge" \
  "$PKG/runtime/python/bin/python" -m embedding.server \
  --socket /tmp/kylin-d14a-embed.sock &
EMBED_PID=$!   # 该 PID 即 --embed-pid：真实 embedding server 的 PID，不是 gateway PID、不是任意 Python PID
#    verify 从已安装前缀运行，通过 embedding.sock 做真实 memory.embed（dim=768、非 fake），
#    并从 /proc/$EMBED_PID/maps 校验 embedding server 实际加载的 SDK .so SHA == 契约冻结值；
#    embedding.sock 未就绪或 --embed-pid 缺失/无效时 verify fail-closed 非零退出。
#    PID 获取方式与当前实现一致，正式部署场景由 runbook 固化。
bash "$INSTALL_PREFIX/systemd/verify.sh" --embed-pid "$EMBED_PID"

# 4.（可选）全链路自动 smoke（install → start → verify(real SDK) → restart → rollback 断言）
#    前置：真实 SDK 已装、当前用户 systemd --user 可用；smoke 自身启动独立 embedding server
#    完成真实 SDK 验证，无需手动先行启动。--prefix 须为隔离安装前缀（不得回退真实用户默认），
#    --expect-source-commit 与步骤 2 同一 40 位值，均必填 fail-closed。
bash packaging/release/package_smoke.sh \
  --package "$PKG" \
  --prefix "$HOME/.local/share/kylin-memory-d14a-smoke" \
  --expect-source-commit <40位完整SHA，同步骤2>

# 5. 回退（uninstall 依据事务目录 txn.meta 精确恢复上次旧状态）
bash "$PKG/systemd/uninstall.sh" rollback
```