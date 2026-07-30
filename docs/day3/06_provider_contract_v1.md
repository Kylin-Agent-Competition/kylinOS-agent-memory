# 06 轨道 A — Provider v1 输入输出契约

> **文档状态：骨架已建立** — 接口定义已冻结，Provider 实现尚未编码，未经过麒麟 VM 端到端验证。
>
> 有宿主证据的结论均标注出处（证据文件:行号），无证据的接口标记为 UNTESTED。

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
| 错误码枚举 | 15 个不重叠值 | 麒麟 VM 实测，2026-07-30 |
| .so 不存在时 dlopen | 返回错误，不崩溃 | 麒麟 VM 实测，2026-07-30（DF-L1-001） |
| dlsym 不存在符号 | 返回 NULL，不崩溃 | 麒麟 VM 实测，2026-07-30（DF-L1-002） |
| init_model(错误模型名) | 返回 errorCode=10，SDK 自动 fallback | 麒麟 VM 实测，2026-07-30（DF-L1-006） |
| Runtime 短暂停用 | SDK 自动重连 6 次（每次间隔 1s），最终成功 | 麒麟 VM 实测，2026-07-30（DF-L1-003） |
| 并发调用（4 线程） | 全部返回 dim=768，无冲突 | 麒麟 VM 实测，2026-07-30（DF-L1-015） |

### 接口定义

```python
class EmbeddingProvider:
    """
    Embedding 向量化服务。
    每次调用均通过 C++ Bridge 走 dlopen → dlsym → text_embedding 路径。
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
| `ERR_EMBED_FAILED` | `ERR_EMBED_CALL` | 直接映射 |
| `ERR_SDK_ERROR` | `ERR_EMBED_ERROR` | 直接映射 |
| `ERR_MODEL_INVALID` | `ERR_MODEL_INVALID` | `init_model` 返回 errorCode=10；SDK 自动 fallback 到默认模型，后续 `text_embedding()` 不受影响 |
| `ERR_TIMEOUT` | `ERR_TIMEOUT` | 直接映射 |
| `ERR_INVALID_TEXT` | 无对应 Bridge 码 | 应用层校验，不进入 Bridge |

| Provider 错误码 | 触发条件 | 状态 |
|:------:|---------|:----:|
| `ERR_SDK_NOT_LOADED` | `dlopen` / `dlsym` 失败 | UNTESTED |
| `ERR_SESSION_FAILED` | `create_session` / `init_session` 异常 | UNTESTED |
| `ERR_EMBED_FAILED` | `text_embedding` 返回 false | UNTESTED |
| `ERR_SDK_ERROR` | `embedding_result_get_error_code != 0` | UNTESTED |
| `ERR_MODEL_INVALID` | `init_model` 返回 errorCode=10；后续 embed 自动使用默认模型 | HOST_VERIFIED / E4 |
| `ERR_TIMEOUT` | 超过 `timeout_ms` | UNTESTED |
| `ERR_INVALID_TEXT` | `text` 为 None 或非字符串类型 | SOURCE_VERIFIED |

## ExtractionProvider

### 职责

从 Turn 事件（用户文本 + 助手回复 + Tool Result）中提取偏好和知识候选。
采用 规则优先 + LLM 结构化抽取 + Pydantic 校验 的策略（见架构文档 §6）。

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
    collected_at: datetime

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
    scope: Literal["global", "session", "project"]  # 待架构文档确认后调整
    confidence: float
    evidence: str
    source_event_id: str

@dataclass
class KnowledgeCandidate:
    fact: str
    category: str                  # fact | procedure | case | template | constraint
    conditions: str | None
    source_event_id: str
    confidence: float
```

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
