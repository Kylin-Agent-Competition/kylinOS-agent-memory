# 麒麟 OS Agent 多源融合偏好与知识记忆系统

## 项目定位

本项目面向银河麒麟桌面操作系统 V11（x86_64）上的官方 AI 助手，构建本地化的多源融合偏好与知识记忆能力，通过 Memory Service、语义检索、偏好管理与 OS Agent 集成，为助手提供可控、可审计、可回滚的长期记忆链路。

## 赛题核心目标

构建一个运行在银河麒麟操作系统上的 Agent 记忆系统，使官方 AI 助手能够在本地安全、高效地存取用户偏好、对话上下文与结构化知识，并覆盖多源接入、偏好版本化、知识融合、冲突处理、检索、遗忘与端侧集成等场景。

## 当前阶段

仓库已经从早期 Gate 0 / 工程基线阶段进入 **post-D15D competition RC / 当前 main 重建待办阶段**。

需要严格区分“历史 D15D release identity”与“当前 main”：

- 2026-09-10 的 D15D historical closeout 曾达到 `L3_READY=true / release_ready=false / production_ready=false`；该结论仅对当时的 release identity / evidence root 有效。
- PR #181 之后 `memory-service/` 与 `migrations/` 出现 runtime/package-impacting drift，旧 release identity 对当前 main 已标记为 `HISTORICAL_VALID_AT_RELEASE_COMMIT / SUPERSEDED_FOR_CURRENT_MAIN`。
- 当前 release freshness 状态为 `RUNTIME_EVIDENCE_STALE_PENDING_REBUILD`，并且 `frozen_package_lock_valid=false`、`rebuild_required=true`、`rebuild_completed=false`、`host_vm_required=true`、`host_vm_completed=false`。
- PR #183 的 Host Integration RC3 证明了 post-D15D 真实助手链路仍可在 Kylin V11 上运行，但**不等同于重新取得当前 main 的正式 L3 release closure，也不生成新的正式 release identity**。

因此，不得把历史 `L3_READY=true` 或旧 release evidence 表述为当前 main 的 Gate PASS；当前 main 若要重新取得正式发布闭包，仍需在最终 runtime freeze 后完成 clean rebuild、真实 Kylin VM 验证与新的 release identity 绑定。

## 已实现与已验证能力

### Memory Service

- Python 本地 Memory Service
- SQLite 结构化记忆真源与 Alembic 迁移
- Unix Domain Socket 本地 IPC
- 偏好、知识、遗忘与检索相关的候选 / 验证链路已经实现
- `preference.*` 为 `CANDIDATE_SYNC`，production 默认不注册；未显式激活时返回 `UNSUPPORTED_METHOD`
- `forget.preview / forget.execute` 属于 validation / candidate 路径，production 默认不注册；未显式激活时返回 `UNSUPPORTED_METHOD`
- `event.ingest`、`turn.finalized` 等 validation seam 同样按显式 profile 激活，不应表述为默认 production registry 已启用
- Host Integration RC 通过可回滚的 user-level systemd drop-in 显式激活所需 candidate handlers；这不改变默认 production profile 的注册边界
- Embedding / Vector / FTS / RRF 等检索与评测支撑
- systemd 用户级运行与验证脚本

### 客户端与 OS 集成

- C++ / Qt 侧 Memory Client 与契约测试
- `os-agent-integration/` 下的 OS Agent 集成层
- Host Memory Bridge：读取真实麒灵助手 Chat DB 中的用户消息并同步显式偏好
- Memory Context Sync：将 active preference 生成到 `$XDG_RUNTIME_DIR`
- pre-chat hook：在不修改用户原始聊天文本的前提下向真实 `chatAsync` 请求注入 Memory Context
- 用户级 launcher / desktop / autostart / systemd 集成，可卸载和回滚

### Kylin V11 Host Integration RC

已在 Kylin V11 2603 x86_64 与真实麒灵助手 3.0.67 环境完成 Host Integration RC3 回归：

- Assistant binary identity preflight：PASS
- runtime library host / Kaiming sandbox identity：PASS
- downstream `chatAsync` ABI preflight：PASS
- Kaiming installed-hook / context visibility：PASS
- Memory Service / Host Bridge / Context Sync：active
- cursor 已支持 `{db_identity, generation, rowid}`，兼容旧整数 cursor，并覆盖运行期 DB clear / replacement / rowid regression
- Runtime verifier：PASS
- 当前真实助手请求记录 `chatAsync injected=1`
- 用户请求未显式指定 Rust 时，active Rust 偏好可影响真实助手语言选择
- Internal Memory Context 写入 Chat DB：0 rows

RC3 单次真实回归仅用于证明修复后的端到端链路仍然成立，不作为正式偏好准确率指标，也不替代当前 main 所需的正式 release rebuild / L3 closure。

详细说明见：

- [Host Memory Integration RC README](os-agent-integration/host-memory-bridge/README.md)
- [Kylin V11 Host E2E evidence](evidence/l2-kylin-vm/host-memory-e2e-20260911/)
- [D15D TaskCard / release freshness](docs/D15D_TaskCard_20260906.md)
- [D15D Version Manifest](docs/day15/D15D_VERSION_MANIFEST.json)

## 关键语义边界

pre-chat hook 的失败语义已经明确区分：

- **memory augmentation fail-open on the validated ABI**：context 缺失、请求形态不支持或无法注入时，原始请求继续转发给真实 `OsAssistant::chatAsync`。
- **ABI resolution fail-closed**：若 downstream `chatAsync` 无法通过 `RTLD_NEXT` 解析，则记录 `ABI_FAIL_CLOSED real-chatAsync-not-found`，不会通过未知 ABI 做不安全调用。

因此，本项目不宣称在任意 Assistant binary / library 漂移情况下都能无条件 fail-open。

## 运行与开发环境

- **运行时 OS**：银河麒麟桌面操作系统 V11 x86_64
- **实机证据环境**：Kylin V11 VirtualBox VM
- **开发环境**：WSL2（开发、单测、文档、打包）
- **CI**：GitHub Actions
- **目标架构**：x86_64

当前竞赛验收范围不包含龙芯部署、非 x86_64 交叉编译或将本 RC 宣称为通用生产版本。

## 核心技术路线

- **结构化记忆真源**：SQLite
- **Schema 迁移**：Alembic
- **语义索引**：Vector（可重建，非真源）
- **文本检索与融合**：FTS / RRF
- **本地 IPC**：Unix Domain Socket + 长度前缀 JSON
- **Memory Service**：Python 3、asyncio、Pydantic
- **C++ / UI 侧**：C++17、Qt 5、QML、QLocalSocket
- **SDK Bridge**：pybind11 + CMake
- **官方助手集成**：Kaiming sandbox + user-scoped launcher + `LD_PRELOAD` pre-chat hook

## 仓库目录说明

| 目录 | 说明 |
|------|------|
| `memory-service/` | Python 记忆服务核心 |
| `cpp-bridge/` | pybind11 C++ / Python SDK Bridge |
| `memory-client/` | Qt / QML 记忆客户端 |
| `os-agent-integration/` | OS Agent Hook、Host Bridge 与官方 AI 助手集成 |
| `migrations/` | SQLite / Alembic schema 迁移 |
| `config/` | 配置模板与示例 |
| `packaging/` | systemd、发布与打包相关内容 |
| `scripts/` | 环境检查、门禁与自动化脚本 |
| `tests/` | 跨模块自动化测试 |
| `datasets/` | 合成 / 脱敏数据集 |
| `evaluation/` | 检索与记忆评测 |
| `evidence/` | Gate 0–L3、Kylin VM 与运行时证据 |
| `deliverables/` | 交付物清单 |
| `docs/` | 架构、API、部署、ADR、发布与审计文档 |
| `.github/` | GitHub Actions 与协作配置 |

## 测试与证据层级

| 层级 | 环境 | 说明 |
|------|------|
| **L0** | WSL2 / CI | 单元测试、静态检查、Mock、C++/Qt contract |
| **L1** | WSL2 / CI | 组件集成、本地 IPC、发布与 provenance 门禁 |
| **L2** | Kylin VM | Runtime Test、真实 SDK / Assistant 环境验证 |
| **L3** | Kylin VM 干净快照 / 冻结证据 | 发布前全链路验收与证据封存 |

当前 CI 已覆盖 repository baseline、Memory Client L0、QML smoke、OS Agent contract，以及 Host Integration RC pytest 与 sealed evidence closure。CI / RC3 PASS 不应替代当前 main 的正式 release freshness / L3 closure 判断。

## 快速开始

### 1. 克隆与仓库基线

```bash
git clone <repository-url>
cd kylinOS-agent-memory

./scripts/verify_repository_baseline.sh
```

### 2. 开发 / 本地验证 Memory Service

开发验证可直接启动：

```bash
PYTHONPATH=memory-service python memory-service/app.py
```

生产式 schema 初始化必须先执行 Alembic 迁移，再使用 `--no-migrate`：

```bash
PYTHONPATH=memory-service python -m alembic -c migrations/alembic.ini upgrade head
PYTHONPATH=memory-service python memory-service/app.py --no-migrate
```

> 不要混用 `metadata.create_all` 与 Alembic 作为同一生产数据库的首次建表路径，否则 default 语义和后续 migration history 可能分叉。

> `preference.*`、`forget.preview / forget.execute`、`event.ingest`、`turn.finalized` 等 candidate / validation handlers 并非默认 production registry 的组成部分；仅在相应显式 profile / RC drop-in 中启用。未启用时按契约返回 `UNSUPPORTED_METHOD`。

### 3. Host Integration RC（Kylin V11）

前提：D14A Memory Service RC 已安装，并存在：

```text
~/.local/bin/kylin-memory-server
```

在 Kylin V11 桌面用户会话中执行：

```bash
bash os-agent-integration/host-memory-bridge/install_host_integration_rc.sh
```

该 RC installer 会通过可回滚的 user-level systemd drop-in 显式启用 Host Integration 验证所需的 candidate handlers；这不表示默认 production profile 已注册这些方法。

安装完成后按提示重新登录，并运行：

```bash
bash os-agent-integration/host-memory-bridge/verify_host_integration_rc.sh --runtime
```

更完整的安装、Kaiming、回滚和 failure semantics 说明见：

[os-agent-integration/host-memory-bridge/README.md](os-agent-integration/host-memory-bridge/README.md)

## 责任轨道（A–E）

| 轨道 | 责任范围 |
|------|----------|
| **A** | Embedding、提取 Provider、数据质量与性能可靠性 |
| **B** | Vector、FTS5、应用层 RRF、索引一致性与检索评测 |
| **C** | OS Agent Hook、MemoryClient、Tool / Turn Adapter 与 QML |
| **D** | IPC、SQLite、Outbox、虚拟机成品化与发布，Reviewer 1 |
| **E** | 记忆业务、安全、数据集和业务指标，Reviewer 2 |

## 文档索引

| 文档 | 位置 |
|------|------|
| Host Integration RC | [os-agent-integration/host-memory-bridge/README.md](os-agent-integration/host-memory-bridge/README.md) |
| D15D release freshness | [docs/D15D_TaskCard_20260906.md](docs/D15D_TaskCard_20260906.md) |
| D15D version manifest | [docs/day15/D15D_VERSION_MANIFEST.json](docs/day15/D15D_VERSION_MANIFEST.json) |
| 贡献指南 | [CONTRIBUTING.md](CONTRIBUTING.md) |
| 安全策略 | [SECURITY.md](SECURITY.md) |
| 变更日志 | [CHANGELOG.md](CHANGELOG.md) |
| 架构设计 | [docs/architecture/](docs/architecture/) |
| ADR | [docs/adr/](docs/adr/) |
| 技术债务 | [docs/technical-debt/TECHNICAL_DEBT_REGISTER.md](docs/technical-debt/TECHNICAL_DEBT_REGISTER.md) |
| 基线文档 | [docs/baseline/](docs/baseline/) |
| 部署指南 | [docs/deployment/](docs/deployment/) |
| 测试指南 | [docs/testing/](docs/testing/) |
| 安全指南 | [docs/security/](docs/security/) |
| Kylin Host E2E evidence | [evidence/l2-kylin-vm/host-memory-e2e-20260911/](evidence/l2-kylin-vm/host-memory-e2e-20260911/) |

## 结果声明与限制

当前仓库用于竞赛提交与可复现实验验证。

已经有证据支持的结论，应以仓库中的测试、manifest、运行日志和 evidence 为准；对于尚未完成或尚未取得正式量化证据的赛题指标，不在 README 中扩大宣称。

特别地，本项目当前不宣称：

- 当前 main 已重新取得正式 `L3_READY=true`
- 当前 main 已完成新的 release identity / frozen package lock
- `release_ready=true`
- `production_ready=true`
- 默认 production registry 已启用 `preference.*` 或 `forget.*` candidate handlers
- RC3 单次实机回归等同于正式偏好准确率 100%
- 任意版本麒灵助手都与当前 pre-chat ABI 兼容

## 安全与知识产权

- 本仓库处于竞赛研发阶段，版权见 [LICENSE](LICENSE)。
- 不捆绑官方 SDK 二进制、系统库、模型或 Kaiming 包，见 [NOTICE](NOTICE)。
- 禁止提交 API Key、密码、私钥、数据库、未脱敏数据、虚拟机镜像，见 [SECURITY.md](SECURITY.md)。
