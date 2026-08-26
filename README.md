# 麒麟 OS Agent 多源融合偏好与知识记忆系统

## 项目定位

为银河麒麟桌面操作系统 V11（x86_64）上的官方 AI 助手提供多源融合偏好与知识记忆服务，通过本地 Memory Service 实现长短期记忆管理、语义检索和偏好推理。

## 赛题核心目标

构建一个运行在银河麒麟操作系统上的、具备多源融合能力的 Agent 记忆系统，使官方 AI 助手能够在本地安全、高效地存取用户偏好、对话上下文和结构化知识。

## 当前阶段

**当前仅完成工程仓库与协作基线初始化，业务代码尚未开始。**

官方 AI 助手 Hook、Memory Context、真实 Tool Result 和 Kaiming→UDS 仍需在 Gate 0 中取得银河麒麟虚拟机证据。

## 当前明确未完成的内容

- Memory Service（Python）尚未实现
- C++ Bridge（pybind11）尚未实现
- Memory Client（QML/QLocalSocket）尚未实现
- 官方 AI 助手 Hook 未集成
- 真实 Tool Result 处理链路未建立
- Kaiming 包分发通道未打通
- 性能指标未达成

## 最终运行环境

- **运行时 OS**：银河麒麟桌面操作系统 V11 x86_64（VirtualBox 虚拟机）
- **开发环境**：WSL2（日常开发、快速单测、文档维护）
- **Agent 沙箱**：Windows + Reasonix（代码分析与静态检查，不可替代麒麟宿主证据）
- **不安排**：龙芯机器部署、交叉编译、实机调试；非 x86_64 架构不属于本项目验收范围

## 核心技术路线

- **结构化记忆真源**：SQLite
- **语义索引**：Vector（可重建，非真源）
- **本地 IPC**：Unix Domain Socket + 长度前缀 JSON
- **Memory Service**：Python 3.10+、asyncio、Pydantic v2
- **C++ 侧**：C++17、Qt 5、QML、QLocalSocket
- **SDK Bridge**：pybind11 + CMake

## 仓库目录说明

| 目录 | 说明 |
|------|------|
| `memory-service/` | Python 记忆服务核心 |
| `cpp-bridge/` | pybind11 C++/Python SDK Bridge |
| `memory-client/` | QML 侧记忆客户端 |
| `os-agent-integration/` | OS Agent Hook 与官方 AI 助手集成 |
| `migrations/` | SQLite schema 迁移 |
| `config/` | 配置模板与示例 |
| `packaging/` | systemd 服务、Kaiming 包打包 |
| `scripts/` | 环境检查与自动化脚本 |
| `tests/` | 自动化测试 |
| `datasets/` | 合成/脱敏数据集 |
| `evaluation/` | 检索与记忆评测 |
| `evidence/` | Gate 0–L3 证据包 |
| `deliverables/` | 交付物清单 |
| `docs/` | 文档（架构、API、部署、ADR 等） |
| `.github/` | GitHub 协作模板与 CI |

## 责任轨道（A–E）

| 轨道 | 责任范围 |
|------|----------|
| **A** | Embedding、提取 Provider、数据质量与性能可靠性 |
| **B** | Vector、FTS5、应用层 RRF、索引一致性与检索评测 |
| **C** | OS Agent Hook、MemoryClient、Tool/Turn Adapter 与 QML |
| **D** | IPC、SQLite、Outbox、虚拟机成品化与发布，Reviewer 1 |
| **E** | 记忆业务、安全、数据集和业务指标，Reviewer 2 |

## 测试层级

| 层级 | 环境 | 说明 |
|------|------|------|
| **L0** | WSL2 / CI | 单元测试、静态检查、Mock |
| **L1** | WSL2 | 组件集成测试、本地 IPC |
| **L2** | 麒麟 VM | Runtime Test、真实环境验收 |
| **L3** | 麒麟 VM 干净快照 | 发布前全链路验收 |

## Gate 0 四项关键认证

1. 仓库与协作基线可验证
2. 环境信息可在麒麟虚拟机中采集
3. 技术方案与架构经 A–E 评审
4. 基线文档与 ADR 就位

## 快速开始

> **注意**：当前阶段尚无业务代码。以下为占位说明。

```bash
# 克隆仓库
git clone <repository-url>
cd kylinOS-agent-memory

# 检查仓库基线
scripts/verify_repository_baseline.sh

# 检查麒麟虚拟机环境（需在虚拟机内运行）
scripts/check_kylin_environment.sh
```

## D4D Memory Service 启动与迁移（重要）

生产环境启动前**必须先执行 Alembic 迁移**，再以 `--no-migrate` 启动——否则 `init_schema`（`metadata.create_all`）与 Alembic 两套建表路径的 default 语义会分叉（`create_all` 使用 Python 侧 default，Alembic 使用 DB 侧 `server_default`），且 `create_all` 建的库后续 `alembic upgrade head` 会因表已存在而冲突：

```bash
# 1. 生产唯一建表路径：先执行迁移
PYTHONPATH=memory-service python -m alembic -c migrations/alembic.ini upgrade head

# 2. 以 --no-migrate 启动（跳过 create_all）
PYTHONPATH=memory-service python memory-service/app.py --no-migrate
```

开发/验证可省略迁移，直接 `PYTHONPATH=memory-service python memory-service/app.py`（内部走 `init_schema` 快速建库，启动日志会提示此为开发模式）。

## 文档索引

| 文档 | 位置 |
|------|------|
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

## 安全与知识产权

- 本仓库处于竞赛研发阶段，版权见 [LICENSE](LICENSE)。
- 不捆绑官方 SDK 二进制、系统库、模型或 Kaiming 包，见 [NOTICE](NOTICE)。
- 禁止提交 API Key、密码、私钥、数据库、未脱敏数据、虚拟机镜像，见 [SECURITY.md](SECURITY.md)。
