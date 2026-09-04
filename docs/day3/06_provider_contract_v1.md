# 06 轨道 A — Provider v1 输入输出契约

> **文档状态：生命周期契约变更待 Gate 审批** — 见下方"生命周期契约 Gate 变更记录"。
> 注意：生命周期语义变更（进程级单例/配置锁定/close-restart 模型 B 等）尚未经 Reviewer 批准，
> 审批通过前不得视为接口已重新冻结。原有接口签名（embed/embed_batch/get_dimension/model_info）不受影响。
>
> 有宿主证据的结论均标注出处（证据文件:行号），无证据的接口标记为 UNTESTED。

## 生命周期契约 Gate 变更记录（P1-5）

Day4 实现引入了对 Day3 冻结契约的生命周期语义变更，按接口冻结 Gate 要求记录如下：

| 项 | 内容 |
|----|------|
| **变更原因** | 麒麟实测 SDK 不允许同一进程 session 销毁后重建（destroy→create 会阻塞挂起）；SDK 动态库禁止 dlclose 后重载（Abort）。为满足 P0-1 生命周期安全，Provider 改为进程级单例。 |
| **影响范围** | EmbeddingProvider 生命周期语义；Bridge destroy_session 终态；配置锁定。接口签名（embed/embed_batch/get_dimension/model_info）不变。 |
| **close/restart 定义（模型 B）** | close() 释放实例引用并置 CLOSED；close 后可重新 start()（重新取得引用）。close 后未 restart 调用 embed() 抛 ERR_SESSION_DESTROYED。未启动 close 为 no-op。 |
| **配置冲突规则** | 进程内首个实例的 so_path 被锁定；后续不同路径实例抛 ERR_CONFIG_CONFLICT。相同/None 路径可共享。 |
| **初始化失败恢复规则** | 首次初始化失败（如 so 不存在）且无引用时重置单例，允许后续实例用正确路径重建。初始化 embed 失败保持 INITIALIZING，下次 start 重试。 |
| **失败恢复与 fatal 终态（P1-1）** | dlsym 缺失 / init_session 失败：首次失败保留原始错误码（`ERR_DLSYM_FAILED`→Provider `ERR_SDK_NOT_LOADED`；`ERR_SESSION_INIT`→Provider `ERR_SESSION_FAILED`），同时置 Bridge fatal 终态（已 dlclose/destroy，禁止进程内重试避免危险生命周期）；fatal 后任何重试/调用返回 `ERR_FATAL_FAILURE`（Provider 0x0203），要求进程重启。.so 不存在、create_session 返回 NULL、初始化 embed 失败为可安全重试路径（不置 fatal）。 |
| **并发初始化策略** | 当前为骨架无类级锁；Memory Service 启动链路为单线程，暂不阻塞（已登记 TD-A-005-06）。 |
| **进程退出清理责任** | 共享 Bridge 由 Python 解释器退出时析构（destroy_session + dlclose 一次）。 |
| **生效 Commit** | 见 PR 证据（`evidence/l2-kylin-vm/day4_verify_latest.log` 被测 commit，EMBED-CALL-003 tested_commit）。 |
| **测试证据** | 生命周期 4 路径麒麟 VM 实测（P0-1）；引用计数/配置冲突/失败恢复 pytest（P1-1/P1-2/P1-4）。 |
| **审批** | 待 Reviewer 确认（本记录随 PR #17 提交）。 |

## EmbeddingProvider

### 职责

封装 Embedding SDK C ABI，向上层（Memory Service 的 domain/service 层）提供文本向量化能力。
不暴露 `dlopen`、`dlsym`、D-Bus 连接等底层细节。

### 证据基线

以下事实来自 Day 1 + Day 2 麒麟 VM 实测：

| 事实 | 值 | 出处 |
|------|-----|------|
| .so 路径 | /usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1 | `embedding_abi_symbols.log:7` |
| 向量维度 | 768 | `minimal_embedding_run.log:38-47`、`day2_smoke_run.log` |
| L2 范数 | 1.000000（单位向量） | `day2_smoke_run.log` 全部 10 用例 |
| 默认模型 | ensemble-embd_gte-base_uint8-text | `minimal_embedding_run.log:33-37` |
| 空文本 | dim=768, 不崩溃 | `minimal_embedding_run.log:46-47` |
| 超长文本(~2170 bytes) | dim=768, 不截断 | `day2_smoke_run.log` TC-1 |
| 重复调用确定性 | 5 次结果一致 | `day2_smoke_run.log` TC-8 |
| Bridge 契约头文件编译 | g++ -fsyntax-only 通过 | 麒麟 VM 实测，2026-07-30 |
| 错误码枚举 | 18 个不重叠值（含 ERR_SESSION_DESTROYED / ERR_FATAL_FAILURE） | 麒麟 VM 实测 + test_bridge_errors 唯一性断言 |
| .so 不存在时 dlopen | 返回错误，不崩溃 | 麒麟 VM 实测，2026-07-30（DF-L1-001） |
| dlsym 不存在符号 | 返回 NULL，不崩溃 | 麒麟 VM 实测，2026-07-30（DF-L1-002） |
| init_model(错误模型名) | 返回 errorCode=10，SDK 自动 fallback | 麒麟 VM 实测，2026-07-30（DF-L1-006） |
| Runtime 短暂停用 | SDK 自动重连 6 次（每次间隔 1s），最终成功 | 麒麟 VM 实测，2026-07-30（DF-L1-003） |
| 并发调用（4 线程） | 全部返回 dim=768，无冲突 | 麒麟 VM 实测，2026-07-30（DF-L1-015） |

### 接口定义

```python
class EmbeddingProvider:
    """
    Embedding 向量化服务（进程级单例）。
    通过进程级单例 Bridge 共享 SDK 会话：首次 start() 加载动态库并初始化模型，
    后续调用复用已有 session（不销毁重建——SDK 不允许同进程 session 销毁后重建）。
    生命周期语义（Day4 实现 + Gate 变更记录，见文档头部）：
    - so_path 仅进程内首个实例生效（全局路径锁定），不同路径抛 ERR_CONFIG_CONFLICT；
    - close() 释放引用并置 CLOSED；close 后可重新 start()（模型 B）；
    - close() 后未 restart 调用 embed() 抛 ERR_SESSION_DESTROYED；
    - 初始化失败可重试（INITIALIZING 状态），首次失败无引用时允许恢复。
    """

    def embed(self, text: str, *, timeout_ms: int = 5000) -> EmbeddingResult:
        """
        单条文本向量化。

        输入:
            text: 待向量化的文本，任意长度（SDK 实际限制见 Day 2 TC-1：~2170 bytes 内不截断）。
            timeout_ms: 单次调用超时（毫秒），默认 5000。

        返回:
            EmbeddingResult
        """

    def embed_batch(self, texts: list[str], *, timeout_ms: int = 30000) -> list[EmbeddingResult]:
        """
        批量文本向量化（应用层批处理，SDK 无原生批量接口）。

        输入:
            texts: 文本列表。
            timeout_ms: 整批完成的墙钟时间上限（毫秒），默认 30000。
                        [PLACEHOLDER] 并行策略未定，此值为占位，待实测后调整。
                        当前实现假设顺序调用，单批总超时 = timeout_ms。

        返回:
            与输入顺序一致的 EmbeddingResult 列表。
        """

    def get_dimension(self) -> int:
        """
        返回当前模型的向量维度。

        返回:
            768（GTE 模型固定值，Day 1 + Day 2 多用例实测确认）
        """

    def model_info(self) -> ModelInfo:
        """
        返回当前加载模型的元信息。

        返回:
            ModelInfo(name, dim, ondevice)
        """
```

### 数据结构

```python
@dataclass
class EmbeddingResult:
    vector: list[float]       # dim=768（Day 1/2 宿主证据确认）
    dimension: int            # 768
    l2_norm: float            # 1.0（Day 2 全部 10 用例实测确认）
    error_code: int           # 0=成功（非零见下方错误码表）
    error_message: str | None # 成功时为 None

@dataclass
class ModelInfo:
    name: str                 # 模型名，如 "ensemble-embd_gte-base_uint8-text"
    dimension: int            # 768
    ondevice: bool            # ASSUMED True（本地模型，未经 SDK API 验证）
    loaded: bool              # 是否已加载
```

### 错误码

Provider 层错误码与 Bridge 层错误码的映射关系：

| Provider 错误码 | Bridge 错误码（C++） | 说明 |
|:------:|:----:|------|
| `ERR_SDK_NOT_LOADED` | `ERR_SO_NOT_FOUND` / `ERR_DLOPEN_FAILED` / `ERR_DLSYM_FAILED` | Bridge 层错误向上聚合 |
| `ERR_SESSION_FAILED` | `ERR_SESSION_CREATE` / `ERR_SESSION_INIT` | 任一失败均映射 |
| `ERR_SESSION_DESTROYED` | `ERR_SESSION_DESTROYED`（Bridge destroy 终态） | 会话已销毁不可重建；Provider 层 close 后未 restart 也抛此码 |
| `ERR_FATAL_FAILURE` | `ERR_FATAL_FAILURE`（fatal 终态后重试/调用） | 不可恢复终态（已 dlclose/destroy），需进程重启；首次失败保留原始码（`ERR_DLSYM_FAILED` / `ERR_SESSION_INIT`） |
| `ERR_EMBED_FAILED` | `ERR_EMBED_CALL` | 直接映射 |
| `ERR_SDK_ERROR` | `ERR_EMBED_ERROR` | 直接映射 |
| `ERR_MODEL_INVALID` | `ERR_MODEL_INVALID` | `init_model` 返回 errorCode=10；SDK 自动 fallback 到默认模型，后续 `text_embedding()` 不受影响 |
| `ERR_TIMEOUT` | `ERR_TIMEOUT` | 直接映射 |
| `ERR_INVALID_TEXT` | 无对应 Bridge 码 | 应用层校验，不进入 Bridge |
| `ERR_CONFIG_CONFLICT` | 无对应 Bridge 码 | Provider 单例配置锁定：so_path 与首实例不一致 |

| Provider 错误码 | 触发条件 | 状态 |
|:------:|---------|:----:|
| `ERR_SDK_NOT_LOADED` | `dlopen` / `dlsym` 失败 | UNTESTED |
| `ERR_SESSION_FAILED` | `create_session` / `init_session` 异常 | UNTESTED |
| `ERR_SESSION_DESTROYED` | Bridge destroy 终态后 create/embed；Provider close 后未 restart embed | SOURCE_VERIFIED（麒麟 VM destroy 终态 CTest） |
| `ERR_FATAL_FAILURE` | dlsym 缺失 / init_session 失败首次失败即进入 fatal 终态；fatal 后重试/调用 | SOURCE_VERIFIED（WSL 假 SDK + Provider pytest；麒麟 VM L2 全绿，最新轮次见 evidence/l2-kylin-vm/day4_verify_latest.log） |
| `ERR_EMBED_FAILED` | `text_embedding` 返回 false | UNTESTED |
| `ERR_SDK_ERROR` | `embedding_result_get_error_code != 0` | UNTESTED |
| `ERR_MODEL_INVALID` | `init_model` 返回 errorCode=10；后续 embed 自动使用默认模型 | HOST_VERIFIED / E4 |
| `ERR_TIMEOUT` | 超过 `timeout_ms` | UNTESTED |
| `ERR_INVALID_TEXT` | `text` 为 None 或非字符串类型 | SOURCE_VERIFIED |
| `ERR_CONFIG_CONFLICT` | 单例 so_path 与首实例不一致 | SOURCE_VERIFIED（麒麟 VM test_config_conflict_raises） |

## ExtractionProvider

### 职责

从 Turn 事件（用户文本 + 助手回复 + Tool Result）中提取偏好和知识候选。
采用 规则优先 + LLM 结构化抽取 + Pydantic 校验 的策略（待架构文档 §6 补齐后确认）。

### 接口定义

```python
class ExtractionProvider:
    """
    偏好/知识提取服务。
    输入为标准化的 TurnFinalizedEvent，输出为提取候选列表。
    """

    def extract_preferences(
        self, event: TurnFinalizedEvent
    ) -> list[PreferenceCandidate]:
        """
        从一次完整回合中提取偏好候选。

        输入:
            event: 标准化的回合完成事件。

        返回:
            偏好候选列表（可能为空）。
        """

    def extract_knowledge(
        self, event: TurnFinalizedEvent
    ) -> list[KnowledgeCandidate]:
        """
        从一次完整回合中提取知识候选。

        输入:
            event: 标准化的回合完成事件。

        返回:
            知识候选列表（可能为空）。
        """
```

### 数据结构

```python
@dataclass
class TurnFinalizedEvent:
    session_id: str
    user_text: str
    assistant_text: str
    tool_results: list[ToolResult] | None
    source: Literal["chat", "tool_result", "manual_config"]  # 事件来源
    occurred_at: datetime
    captured_at: datetime  # DRIFT-001：Canonical 采集时间写字段（唯一真源）

@dataclass
class ToolResult:
    tool_name: str
    arguments: dict
    status: str                    # success | failure | cancelled
    result: str | None
    error: str | None

@dataclass
class PreferenceCandidate:
    key: str
    value: str
    scope: Literal["global", "topic", "tool", "session", "time_window"]  # E 轨 Schema §2.9 五值（Day7 契约演进同步）
    confidence: float
    evidence: str
    source_event_id: str

@dataclass
class KnowledgeCandidate:
    fact: str
    # 知识类别（E 轨业务 Schema §2.6 六值；Day8 契约演进自五值：
    # procedure → workflow 命名对齐 E 轨，新增 failure_experience）
    category: str                  # fact | workflow | case | template | constraint | failure_experience
    conditions: str | None
    evidence: str | None           # Day8 新增：证据描述（架构 TABLE 21）
    source_event_id: str
    confidence: float
    # Day8 新增六类结构化字段（架构 TABLE 21，全可选）：
    # steps/expected_result（workflow）、problem/outcome/reproducible（case）、
    # template_body/parameters（template）、priority（constraint）、
    # failure_reason/avoid_condition/alternative（failure）
```

> **DRIFT-001 字段演进说明（2026-09-03，Schema 漂移治理）**
> - `TurnFinalizedEvent` 采集时间 **Canonical 写字段为 `captured_at`**；`collected_at` 不再是 dataclass 可写字段，仅保留为 **legacy 只读 alias**（读 `event.collected_at` 返回 `event.captured_at`）。
> - **legacy 输入兼容**：构造/传输仍可传 `collected_at=`（含 `TurnFinalizedEvent(**payload)`），实现层将其归一为 `captured_at`；两字段同时提供且不一致时按冻结纪律拒绝（fail-closed）。
> - **边界**：D 轨 IPC metadata 的 `collected_at` 为 legacy transport 名称，由 transport→business Adapter 归一（TD-060，C/D 实现 handoff）；本契约只收敛 A 轨 Provider 对象字段，不改变 transport 层。

> **ExtractionProvider 所有接口状态：UNTESTED** — 需 LLM 集成和标注数据集完成后才能验证。

## 错误处理原则

Provider 层区分两种失败模式：

| 模式 | 含义 | 处理方式 |
|:----:|------|---------|
| **异常** | 非预期错误（SDK 崩溃、连接断开） | 向上透传，不吞不降级 |
| **降级** | 预期内的受限响应（超时、低置信度） | 返回降级结果 + 记录日志，不阻塞调用链 |

具体规则：
- EmbeddingProvider 超时后返回 `ERR_TIMEOUT`，不重试
- ExtractionProvider 超时后返回空候选列表（降级），不阻塞 Turn 事件处理
- 超时由调用方（Service 层）通过 `asyncio.wait_for` 或 `concurrent.futures` 控制

## 未冻结项（待后续 Day 确认）

| 项目 | 原因 |
|------|------|
| `embed_batch` 的并行策略 | 按顺序/并发/分批未定，取决于 Provider 封装后的实测吞吐 |
| ExtractionProvider 详细策略参数 | 规则阈值和 LLM prompt 模板需在数据集上调试 |
| 精确的 `timeout_ms` 默认值 | 需在完整 Memory Service 链路上实测后调整 |

## Bridge 契约头文件验证结果

2026-07-30 在麒麟 VM 实测：

```bash
g++ -std=c++17 -I. -fsyntax-only cpp-bridge/bridge_error_contract.h
# → HEADER_SYNTAX_EXIT=0

g++ -std=c++17 -I. -fsyntax-only cpp-bridge/bridge_error_contract.h cpp-bridge/embedding_abi_compat.h
# → JOINT_SYNTAX_EXIT=0

g++ -std=c++17 -I. /tmp/test_error_codes.cpp -o /tmp/test_error_codes && /tmp/test_error_codes
# → 错误码无重叠: PASS
# → ok.is_ok()=1, ok.value=768
# → fail.is_fail()=1, fail.error=257
# → ERROR_CODE_TEST_EXIT=0
```
