# 麒麟 OS Agent 多源融合偏好与知识记忆系统
# 安装与部署指南

> 建议仓库路径：`docs/deployment/INSTALLATION_GUIDE.md`  
> 文档状态：Competition RC 安装说明  
> 编写基线：2026-09-11，仓库 `Kylin-Agent-Competition/kylinOS-agent-memory`  
> 参考主线状态：`main@e88ad2c88237cdf979007116390a0d1ec40d0597`

---

## 1. 文档目的

本文用于说明麒麟 OS Agent 记忆系统从源码检查、Memory Service 发布包构建、银河麒麟 V11 安装、systemd 用户服务启动，到 Host Integration RC 接入真实麒灵助手、验证与回滚的完整流程。

本文优先面向比赛评审、交付验收与团队复现，不替代源码中的模块级开发文档。所有“通过”“可用”“已验证”结论均应以对应 Commit、manifest、测试日志和 `evidence/` 证据为准。

### 1.1 当前发布状态说明

截至本指南基线，仓库已经完成 D14A 发布包机制和 post-D15D Host Integration RC3 实机验证，但 **当前 main 在 PR #181 后发生了 runtime/package-impacting drift**，历史 D15D release identity 已被标记为过期，不能直接把历史 `L3_READY=true` 视为当前 main 的正式发布闭包。

因此：

- 本指南中的 D14A 打包、安装、systemd、真实 SDK 与 Host RC 流程均来自当前仓库已有实现；
- 比赛最终提交前，应在最终冻结 Commit 上重新构建正式发布包；
- 最终包应重新完成 clean Kylin VM 安装、验证、回滚与 evidence 绑定；
- 不应将历史包、历史 manifest 或旧 evidence 直接声明为当前 main 的正式发布结果。

---

## 2. 支持范围

### 2.1 目标运行平台

| 项目 | 当前竞赛支持范围 |
|---|---|
| 操作系统 | 银河麒麟桌面操作系统 V11 |
| 已验证主机环境 | Kylin V11 2603 x86_64 |
| CPU 架构 | x86_64 / amd64 |
| Python | Python 3，发布构建脚本默认 `/usr/bin/python3.12`，最低要求 `>=3.10` |
| 服务管理 | `systemd --user` |
| 数据库 | SQLite + Alembic |
| 本地 IPC | Unix Domain Socket |
| Embedding | 银河麒麟 CoreAI Embedding SDK |
| AI 助手 Host RC | 麒灵助手 3.0.67 已完成受控实机验证 |

当前竞赛验收范围不包含龙芯部署、非 x86_64 交叉编译或任意版本麒灵助手兼容性承诺。

### 2.2 开发环境与运行环境的区别

- **WSL2 / Ubuntu 22.04**：用于日常开发、L0/L1、文档、CI 对齐和普通单元/组件验证。
- **银河麒麟 V11 VM**：用于 L2/L3、真实 SDK、systemd、Kaiming、真实助手 Host Integration、安装与回滚验证。

WSL 测试成功不能替代银河麒麟宿主证据，也不能标记为 `HOST_VERIFIED`。

---

## 3. 仓库中的部署相关组件

```text
kylinOS-agent-memory/
├── memory-service/                    # Python Memory Service
├── cpp-bridge/                        # pybind11 + CoreAI Embedding SDK Bridge
├── migrations/                        # Alembic migrations
├── config/                            # 配置示例
├── packaging/
│   ├── release/                       # D14A 正式发布包构建/安装/验证/回滚
│   └── systemd/                       # systemd 用户服务 unit
├── os-agent-integration/
│   └── host-memory-bridge/            # post-D15D Host Integration RC
├── scripts/                           # 基线、门禁、VM 验证脚本
├── evidence/                          # L0-L3 / Kylin VM 证据
└── docs/                              # 架构、ADR、发布与测试文档
```

正式发布入口以 `packaging/release/` 为准。历史 `packaging/systemd/` 中依赖源码 checkout / 个人 venv 的旧安装方式仅作历史参考，不作为最终比赛安装入口。

---

## 4. 安装前准备

### 4.1 获取源码并确认基线

```bash
git clone https://github.com/Kylin-Agent-Competition/kylinOS-agent-memory.git
cd kylinOS-agent-memory

git rev-parse HEAD
git status --short
```

用于正式构建时必须满足：

```text
1. 当前 HEAD 是准备交付的冻结 Commit；
2. 工作区 clean；
3. 后续 build 的 --source-commit 与该 HEAD 一致。
```

如需执行仓库基线检查：

```bash
./scripts/verify_repository_baseline.sh
```

### 4.2 Python 依赖

Memory Service 的主要 Python 依赖由以下文件管理：

```text
memory-service/requirements.txt
```

当前依赖包括：

```text
pydantic >=2,<3
sqlalchemy >=2.0,<2.1
alembic >=1.13
rfc8785 >=0.1.4,<0.2
tomli >=2.0（仅 Python <3.11）
pytest >=8
pybind11 >=2.11
```

源码开发环境可执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r memory-service/requirements.txt
```

> 正式 D14A 发布包自身包含运行 Python 环境，不要求目标机依赖开发者个人 `.venv`。

### 4.3 构建工具

D14A 发布包构建脚本要求能够构建 `cpp-bridge`，至少需要：

```text
Python >= 3.10
python3-dev
cmake
C/C++ build toolchain
git
sha256sum
```

Host Integration RC 当前从源码 checkout 安装时还需要 `g++` 编译 pre-chat hook。

### 4.4 银河麒麟 Embedding SDK

D14A 当前冻结的真实 SDK 路径为：

```text
/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0
```

安装脚本会 fail-closed 校验 SDK 文件、版本和 SHA-256。缺失或 identity 不一致时，不应通过修改安装脚本、跳过 Gate 或替换成 fake SDK 获得“安装成功”。

可先检查：

```bash
ls -l /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0

dpkg-query -W -f='${Version}\n' libkylin-coreai-embedding 2>/dev/null || true

sha256sum /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0
```

---

## 5. 推荐安装方式：D14A 自包含发布包

这是比赛交付时推荐使用的 Memory Service 安装方式。

### 5.1 冻结最终源码 Commit

在正式构建机器上：

```bash
cd kylinOS-agent-memory

git status --short
SOURCE_COMMIT="$(git rev-parse HEAD)"
echo "$SOURCE_COMMIT"
```

必须确认：

```bash
[ -z "$(git status --porcelain)" ] && echo "WORKTREE_CLEAN=PASS"
```

不要使用“随手记下的旧 SHA”。最终比赛包必须绑定最终冻结 Commit。

### 5.2 构建发布包

在银河麒麟 V11 x86_64、真实 SDK 可用的环境执行：

```bash
bash packaging/release/build_release_package.sh \
  --source-commit "$SOURCE_COMMIT"
```

脚本默认输出到：

```text
/tmp/kylin-d14a-dist/
```

典型产物：

```text
/tmp/kylin-d14a-dist/kylin-memory-a-d14a-0.1.0-d14a/
├── bin/kylin-memory-server
├── runtime/app/
├── runtime/bridge/
├── runtime/python/
├── config/config.toml.example
├── systemd/
├── VERSION
├── manifest.json
└── SHA256SUMS
```

构建过程中会执行：

```text
Git source identity Gate
→ Python / SDK 环境 Gate
→ cpp-bridge 构建
→ 自包含 runtime 组装
→ 包内 Alembic migration smoke
→ manifest / SHA256SUMS 生成
```

构建失败时不要直接复制未完成目录作为正式发布包。

### 5.3 检查包身份

```bash
PKG="/tmp/kylin-d14a-dist/kylin-memory-a-d14a-0.1.0-d14a"

cat "$PKG/VERSION"
python3 -m json.tool "$PKG/manifest.json" | less
( cd "$PKG" && sha256sum -c SHA256SUMS )
```

正式交付时建议单独记录：

```text
source_commit
package_version
manifest.json SHA-256
SHA256SUMS SHA-256
构建时间
构建环境
```

---

## 6. 在银河麒麟 V11 安装 Memory Service

### 6.1 将发布包传入目标 VM

可以使用 WinSCP、SCP 或受控共享目录传输完整发布包目录。

示例：

```bash
PKG="$HOME/packages/kylin-memory-a-d14a-0.1.0-d14a"
```

检查关键文件：

```bash
test -f "$PKG/manifest.json"
test -f "$PKG/SHA256SUMS"
test -x "$PKG/bin/kylin-memory-server"
test -x "$PKG/systemd/install.sh"
```

### 6.2 获取可信的 source identity

安装器要求调用方显式传入完整 40 位：

```text
EXPECT_SOURCE_COMMIT
```

这个值应来自正式冻结记录/构建记录，而不是安装过程中临时从被测包“反推”。

示例：

```bash
EXPECT_SOURCE_COMMIT="<最终冻结 Commit 的 40 位 SHA>"
```

### 6.3 执行安装

默认安装前缀为：

```text
$XDG_DATA_HOME/kylin-memory-d14a
```

若 `XDG_DATA_HOME` 未设置，则等价于：

```text
~/.local/share/kylin-memory-d14a
```

执行：

```bash
EXPECT_SOURCE_COMMIT="$EXPECT_SOURCE_COMMIT" \
  bash "$PKG/systemd/install.sh" install
```

若希望显式指定安装前缀：

```bash
INSTALL_PREFIX="$HOME/.local/share/kylin-memory-d14a"

EXPECT_SOURCE_COMMIT="$EXPECT_SOURCE_COMMIT" \
INSTALL_PREFIX="$INSTALL_PREFIX" \
  bash "$PKG/systemd/install.sh" install
```

安装器会在产生正式副作用前执行包完整性和 identity Gate，包括：

```text
manifest / SHA256SUMS 三向一致性
package_name / package_version
source_commit
SDK path / version / SHA-256
VERSION 与 manifest 对齐
受管理文件 hash / size
```

之后完成发布包复制、数据库迁移、用户级 systemd 安装与服务启动。

### 6.4 主要安装位置

正常安装后主要路径为：

```text
安装前缀：    ~/.local/share/kylin-memory-d14a/
launcher：    ~/.local/bin/kylin-memory-server
systemd unit：~/.config/systemd/user/kylin-memory.service
数据库：      ~/.local/share/kylin-memory/kylin_memory.db   （默认）
UDS：         $XDG_RUNTIME_DIR/kylin-memory/memory.sock
配置：        ~/.config/kylin-memory/config.toml            （可选）
```

服务为用户级服务，不要求使用 root 启动 Memory Service。

---

## 7. 配置说明

### 7.1 配置优先级

当前配置优先级：

```text
CLI > 环境变量 > ~/.config/kylin-memory/config.toml > 默认值
```

### 7.2 主要环境变量

```text
KYLIN_MEMORY_SOCKET
KYLIN_MEMORY_DB
KYLIN_MEMORY_DEADLINE_MS
KYLIN_MEMORY_RETRIEVE_DEADLINE_MS
KYLIN_MEMORY_OUTBOX_POLL_INTERVAL_S
KYLIN_MEMORY_OUTBOX_MAX_RETRIES
KYLIN_MEMORY_EMBEDDING_MODEL
KYLIN_MEMORY_LOG_LEVEL
```

默认关键路径/值：

```text
Socket:   $XDG_RUNTIME_DIR/kylin-memory/memory.sock
Database: ~/.local/share/kylin-memory/kylin_memory.db
Deadline: 5000 ms
Retrieve: 150 ms
Log:      INFO
```

### 7.3 config.toml

配置文件缺失时服务可以使用默认值启动，因此**不需要为了首次安装而创建 `config.toml`**。

> 当前 D14A builder 会优先把仓库的 `config/environment.example` 复制为发布包内的 `config/config.toml.example`。该文件本质上是环境变量示例，包含 `KYLIN_MEMORY_*=...` 形式内容，**不是可直接复制为 `~/.config/kylin-memory/config.toml` 的 TOML 模板**。在 builder 修复前，请不要执行 `cp "$PKG/config/config.toml.example" ~/.config/kylin-memory/config.toml`。

确需覆盖默认配置时，可以手工创建一个有效 TOML。例如下面只覆盖 deadline、outbox、embedding 与日志级别，Socket 与数据库路径继续使用程序默认值：

```bash
mkdir -p ~/.config/kylin-memory
cat > ~/.config/kylin-memory/config.toml <<'EOF'
[deadline]
default_ms = 5000

[retrieve]
deadline_ms = 150

[outbox]
poll_interval_s = 1
max_retries = 3

[embedding]
model = "default"

[log]
level = "INFO"
EOF
```

创建后可先做 TOML 语法检查，再重启服务：

```bash
python3 - <<'PY'
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

path = Path.home() / ".config/kylin-memory/config.toml"
with path.open("rb") as f:
    tomllib.load(f)
print("CONFIG_TOML_PARSE=PASS")
PY

systemctl --user restart kylin-memory
```

如果只需要默认值，删除该文件即可恢复默认配置路径：

```bash
rm -f ~/.config/kylin-memory/config.toml
systemctl --user restart kylin-memory
```

> 配置文件存在但 TOML 无法解析时，Memory Service 会 fail-fast；不要把 shell 环境变量格式误写进 `config.toml`。也不要把 SSH 密码、API Key、Token、私钥等敏感信息提交到仓库或正式 evidence。

---

## 8. systemd 服务检查

### 8.1 查看状态

```bash
systemctl --user status kylin-memory --no-pager
```

### 8.2 查看日志

```bash
journalctl --user -u kylin-memory -n 100 --no-pager
```

实时观察：

```bash
journalctl --user -u kylin-memory -f
```

### 8.3 检查 Socket

```bash
printf 'XDG_RUNTIME_DIR=%s\n' "$XDG_RUNTIME_DIR"
ls -l "$XDG_RUNTIME_DIR/kylin-memory/memory.sock"
```

服务 unit 使用：

```text
RuntimeDirectory=kylin-memory
RuntimeDirectoryMode=0700
```

正常运行时 Runtime 目录应保持用户隔离。

### 8.4 检查数据库迁移

生产服务使用 `--no-migrate` 启动，因此数据库 schema 应由 Alembic 先行管理。

可检查：

```bash
sqlite3 ~/.local/share/kylin-memory/kylin_memory.db \
  'select version_num from alembic_version;'
```

不要在同一个正式数据库上混用 `metadata.create_all` 与 Alembic 作为首次建表路径。

---

## 9. 真实 Embedding SDK 验证

D14A `verify.sh` 要求真实、独立的 embedding server 已运行。验证器不会替你启动它。

### 9.1 启动独立 embedding server

```bash
export INSTALL_PREFIX="${INSTALL_PREFIX:-$HOME/.local/share/kylin-memory-d14a}"

PYTHONPATH="$INSTALL_PREFIX/runtime/app:$INSTALL_PREFIX/runtime/bridge" \
  "$INSTALL_PREFIX/runtime/python/bin/python" -m embedding.server \
  --socket /tmp/kylin-d14a-embed.sock &

EMBED_PID=$!
echo "EMBED_PID=$EMBED_PID"
```

### 9.2 执行发布包验证

```bash
bash "$INSTALL_PREFIX/systemd/verify.sh" --embed-pid "$EMBED_PID"
```

验证链会检查真实 embedding socket、维度、进程身份以及该 embedding server 实际加载的 SDK `.so` identity。

不要把 gateway PID、任意 Python PID 或 fake embedding server 作为 `--embed-pid`。

---

## 10. 全链路 Package Smoke

在隔离安装前缀中可执行：

```bash
bash packaging/release/package_smoke.sh \
  --package "$PKG" \
  --prefix "$HOME/.local/share/kylin-memory-d14a-smoke" \
  --expect-source-commit "$EXPECT_SOURCE_COMMIT"
```

该流程用于验证：

```text
install
→ start
→ real SDK verify
→ restart
→ rollback assertion
```

正式比赛提交前，建议在干净银河麒麟 VM 快照上执行一次完整 L3 流程，并把日志、Commit、系统版本、包 identity 与 SHA-256 固化到 evidence。

---

## 11. Host Integration RC：接入真实麒灵助手

### 11.1 当前边界

当前仓库提供的是 **post-D15D controlled Host Integration RC**，已经在：

```text
Kylin V11 2603 x86_64
麒灵助手 3.0.67
```

上完成受控实机验证。

它证明真实助手链路可工作，但不代表：

```text
release_ready=true
production_ready=true
任意麒灵助手版本均兼容
Host RC 单次结果等同于正式 >=85% 偏好准确率评测
```

### 11.2 前置条件

先确认 D14A Memory Service 已安装：

```bash
test -x ~/.local/bin/kylin-memory-server && echo "MEMORY_SERVER=READY"
```

当前 source-checkout Host installer 会构建 C++ hook，因此还需要：

```bash
command -v g++
```

### 11.3 安装 Host Integration RC

在仓库源码目录执行：

```bash
bash os-agent-integration/host-memory-bridge/install_host_integration_rc.sh
```

安装器在修改助手启动路径前会执行受控兼容性预检，包括：

```text
已验证 Assistant binary identity
hook ABI export
Kaiming no-UI probe
installed hook / runtime context 在 sandbox 中可见并可加载
```

Host RC 使用用户级可回滚 override，不修改官方 Assistant ELF。

### 11.4 注销并重新登录

Host RC 设计要求安装后进行一次：

```text
log out → log in
```

重新登录后，用户链路为：

```text
kylin-memory.service
→ kylin-memory-host-bridge.service
→ kylin-memory-context-sync.service
→ XDG autostart override
→ kaiming run
→ inside-sandbox wrapper
→ pre-chat hook
→ 原始 /usr/bin/kylin-aiassistant
```

### 11.5 Runtime 验证

重新登录后：

```bash
bash os-agent-integration/host-memory-bridge/verify_host_integration_rc.sh --runtime
```

只有真实 Runtime 检查成功后，才能将本次 Host Integration 记录为对应 Commit/环境的宿主证据。

---

## 12. 源码模式启动（仅开发与排障）

如果只需要开发/调试 Memory Service，而不是比赛正式安装，可在源码 checkout 中运行。

### 12.1 创建 venv

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r memory-service/requirements.txt
```

### 12.2 开发模式启动

```bash
PYTHONPATH=memory-service python memory-service/app.py
```

### 12.3 模拟生产 schema 管理方式

```bash
PYTHONPATH=memory-service \
python -m alembic -c migrations/alembic.ini upgrade head

PYTHONPATH=memory-service \
python memory-service/app.py --no-migrate
```

源码模式用于开发，不等于最终自包含发布包验收。

---

## 13. 卸载与回滚

### 13.1 Memory Service 发布包回滚

D14A 安装器在覆盖既有状态前会把旧状态保存到私有事务目录。发布包内 rollback：

```bash
bash "$PKG/systemd/uninstall.sh" rollback
```

事务状态目录位于：

```text
${XDG_STATE_HOME:-$HOME/.local/state}/kylin-memory/d14a-install-txn
```

回滚目标不是简单“删掉新文件”，而是恢复安装前被捕获的旧 prefix / unit / launcher 状态。

### 13.2 Host Integration RC 回滚

```bash
bash os-agent-integration/host-memory-bridge/uninstall_host_integration_rc.sh
```

该卸载器会恢复首次安装前已存在的用户 desktop/autostart/drop-in override；若原先不存在，则移除 RC override，使系统级麒灵助手入口重新生效。

### 13.3 回滚后检查

```bash
systemctl --user daemon-reload
systemctl --user status kylin-memory --no-pager || true

ls -l ~/.local/bin/kylin-memory-server 2>/dev/null || true
ls -l ~/.config/systemd/user/kylin-memory.service 2>/dev/null || true
```

如为正式 L3，应同时记录回滚后的服务、文件、数据库和助手启动路径状态。

---

## 14. 常见问题与排障

### 14.1 `pip` 出现 DNS 解析失败

若源码环境安装依赖出现：

```text
[Errno -3] Temporary failure in name resolution
```

先区分系统网络与 Python DNS：

```bash
python - <<'PY'
import socket
for host in ("pypi.org", "files.pythonhosted.org"):
    try:
        print(host, socket.getaddrinfo(host, 443)[:2])
    except Exception as exc:
        print(host, "FAIL", repr(exc))
PY
```

若在线依赖不稳定，正式复现更建议准备经过验证的离线 Wheelhouse，而不是在比赛现场依赖即时 PyPI 网络。

### 14.2 `systemctl --user` 不可用

检查：

```bash
systemctl --user status
loginctl show-user "$USER"
echo "$XDG_RUNTIME_DIR"
```

Memory Service 当前按用户级 systemd 设计，不应为了绕过用户会话问题擅自改成 root system service。

### 14.3 服务启动后立即退出

```bash
systemctl --user status kylin-memory --no-pager
journalctl --user -u kylin-memory -n 200 --no-pager
```

重点检查：

```text
Alembic schema 是否已迁移
config.toml 是否非法
数据库路径是否可写
UDS runtime 目录是否可创建
发布包 runtime 是否完整
```

### 14.4 SDK identity 不匹配

不要修改冻结哈希绕过。先确认：

```bash
dpkg-query -W -f='${Version}\n' libkylin-coreai-embedding
sha256sum /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1.0.0
```

若系统 SDK 真正升级，应走新的兼容性验证、ABI/运行证据和 release identity，而不是继续沿用旧包 PASS 结论。

### 14.5 Host Integration installer 拒绝助手版本

这是预期的 fail-closed 行为。当前 RC 只对已验证的 Assistant binary / ABI 作明确兼容性声明。

不要通过删除 SHA、ABI 或 Kaiming preflight 强制安装。应先完成目标版本的兼容性验证，再更新冻结契约和测试。

### 14.6 Socket 不存在

```bash
systemctl --user is-active kylin-memory
journalctl --user -u kylin-memory -n 100 --no-pager
find "$XDG_RUNTIME_DIR" -maxdepth 3 -name 'memory.sock' -ls
```

若服务 active 但 Socket 不存在，应按真实日志定位，不要用创建空文件代替 UDS。

---

## 15. 比赛现场最短安装演示流程

最终比赛包冻结后，建议现场只展示已经提前在干净 VM 验证过的固定流程。

```bash
# 1. 确认包
PKG="$HOME/packages/kylin-memory-a-d14a-0.1.0-d14a"
EXPECT_SOURCE_COMMIT="<最终冻结 40 位 SHA>"

# 2. 安装
EXPECT_SOURCE_COMMIT="$EXPECT_SOURCE_COMMIT" \
  bash "$PKG/systemd/install.sh" install

# 3. 服务状态
systemctl --user status kylin-memory --no-pager

# 4. Socket
ls -l "$XDG_RUNTIME_DIR/kylin-memory/memory.sock"

# 5. Host Integration RC（如现场演示真实助手）
cd ~/kylinOS-agent-memory
bash os-agent-integration/host-memory-bridge/install_host_integration_rc.sh

# 6. 注销/重新登录后
bash os-agent-integration/host-memory-bridge/verify_host_integration_rc.sh --runtime
```

正式答辩前应至少完整彩排一次“安装 → 验证 → 实际功能演示 → 回滚”。

---

## 16. 提交前安装验收清单

### A. Source / Package Identity

- [ ] 最终比赛 Commit 已冻结
- [ ] `git status --porcelain` 为空
- [ ] D14A `--source-commit` 与 HEAD 完全一致
- [ ] `manifest.json` 写入完整 40 位 source commit
- [ ] `SHA256SUMS` 全量通过
- [ ] 发布包不依赖源码 checkout 或个人 venv

### B. Kylin Install

- [ ] 干净 Kylin V11 x86_64 VM
- [ ] CoreAI Embedding SDK identity 符合当前 release contract
- [ ] 安装脚本 exit code = 0
- [ ] Alembic upgrade 到当前 head
- [ ] `kylin-memory.service` active
- [ ] UDS 正常创建
- [ ] 数据库路径/权限正确
- [ ] 重启后服务恢复

### C. Real SDK / Runtime

- [ ] 独立 embedding server 使用真实 SDK
- [ ] `verify.sh --embed-pid` 通过
- [ ] 无 fake SDK / fake PID / Mock 冒充 Runtime
- [ ] 关键日志与 package identity 绑定

### D. Host Integration（如作为最终演示链路）

- [ ] 已验证目标麒灵助手 binary / ABI identity
- [ ] Host installer preflight 通过
- [ ] 注销/登录后三项用户服务正常
- [ ] runtime verifier 通过
- [ ] 实际助手请求存在受控 Memory Context 注入证据
- [ ] 原始 UI/Chat DB 用户文本未被篡改

### E. Rollback

- [ ] Memory Service rollback 通过
- [ ] Host Integration uninstall/restore 通过
- [ ] systemd / launcher / override 无非预期残留
- [ ] 回滚日志已保存

### F. Evidence

每次正式安装/验证至少记录：

```text
project
task / release id
branch
commit_sha
package_version
manifest hash
environment / OS version
timestamp
command
exit_code
stdout / stderr
result
limitations
```

---

## 17. 与比赛材料的关系

本安装指南应与以下材料配套提交：

```text
项目 README
技术方案
用户操作说明
测试与效果验证报告
银河麒麟适配测试报告
源代码及规范
效果演示视频
```

比赛材料中应避免把安装流程、功能测试和性能指标混为一体：

- 本文证明“如何部署与复现”；
- 测试报告证明“功能是否正确”；
- 评测报告证明“准确率、召回率、延迟、冲突处理正确率”；
- Kylin 适配报告证明“目标宿主上的真实兼容性”；
- evidence 负责把结论绑定到真实 Commit、环境和命令。

---

## 18. 相关仓库文档

```text
README.md
packaging/README.md
packaging/release/
packaging/systemd/kylin-memory.service
os-agent-integration/host-memory-bridge/README.md
docs/day14/00_d14a_release_package_contract.md
docs/D15D_TaskCard_20260906.md
docs/day15/D15D_VERSION_MANIFEST.json
evidence/l2-kylin-vm/
evidence/l3-kylin-vm/
```

---

## 19. 最终原则

> **安装成功必须可以被验证，验证结果必须可以追溯到 Commit 和发布包 identity。**

> **WSL 通过不能替代银河麒麟 Runtime 通过。**

> **不要通过降低完整性、SDK、ABI、迁移或安全 Gate 获得“绿色结果”。**

> **历史 release evidence 只能证明对应历史 release identity；当前 main 的最终比赛版本需要新的冻结、构建和宿主验证闭环。**
