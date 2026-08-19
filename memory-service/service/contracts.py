"""
service/contracts.py — Day4 E 轨 Service 编排边界骨架

标记：D4_SKELETON / NOT_IPC_CONTRACT / NOT_PERSISTENCE_CONTRACT

本模块仅为 E 轨业务编排层（Service）的内部最小边界骨架，用于为后续偏好/知识
治理服务、冲突编排服务和遗忘编排服务提供承载结构。它：

- 不是 IPC 协议（IPC envelope 由 memory-service/embedding/protocol.py 承载）；
- 不是持久化契约（不定义 Repository、UoW、SQLite、Outbox、FTS5 或 Vector 结构）；
- 不是已冻结的公开 API / 跨轨公共协议；
- 不实现任何业务算法、冲突判定、遗忘执行、检索或存储逻辑。

复用约束：
- NonEmptyStr / AwareDatetime 复用自 domain.common（不重复定义）。
- Preference / Knowledge / Conflict / ForgetPlan 引用自 domain 包，仅作内部
  编排目标集合引用，不复导出（不在本模块 __all__）。
- 本模块不复制 domain 或 pipeline 中已存在的同名 Enum / Pydantic 模型。
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Protocol, Union

from pydantic import BaseModel, ConfigDict

from domain import Conflict, ForgetPlan, Knowledge, Preference
from domain.common import NonEmptyStr


class OperationOutcomeStatus(str, Enum):
    """Service 编排操作的结果边界状态（新建，与既有状态枚举语义正交）。

    语义边界：
    - SourceBusinessStatus（pipeline.schemas）：MemorySourceEvent 的业务结果；
    - ProcessingStatus（pipeline.schemas）：清洗流水线内部处理状态；
    - MemoryStatus（domain.enums）：记忆生命周期状态；
    - ForgetPlanStatus（domain.enums）：遗忘计划执行状态机；
    - ResolutionStatus（domain.enums）：冲突消解状态。
    以上均与本枚举不同——本枚举只表达一次 Service 编排操作的结果边界：
    ok（成功）/ degraded（部分成功或降级）/ blocked（被系统侧阻断）/
    rejected（被业务或安全规则拒绝）。
    """

    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class ServiceRequestContext(BaseModel):
    """内部业务编排上下文（非 IPC envelope）。

    仅承载编排所需的归属与追踪信息；IPC envelope 由
    memory-service/embedding/protocol.py 承载，本类型不定义任何传输结构。

    对齐 D3 §7.1：user_id 为用户归属隔离键，*禁止模型生成，
    actor_id 为实际发起者（同一 user_id 下可有多个 actor_id）；
    此处仅做结构承载，不实现任何生成或校验链路。
    """

    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyStr  # 用户归属隔离键（D3 §7.1 / SEC-UI-01/07），*禁止模型生成
    actor_id: NonEmptyStr  # 实际发起者（D3 §7.1 / SEC-UI-07）
    trace_id: Optional[str] = None
    session_id: Optional[str] = None


# 编排目标实体集合（内部引用别名）：仅表达 Service 可编排的四类 Domain 业务对象，
# 不构成新的"自有类型"，也不对外冻结跨轨公共协议。
DomainEntity = Union[Preference, Knowledge, Conflict, ForgetPlan]


class OperationOutcome(BaseModel):
    """Service 操作结果边界（不含实体明文，不绑定 SQLite/Vector/IPC）。"""

    model_config = ConfigDict(extra="forbid")

    status: OperationOutcomeStatus
    reason: Optional[str] = None
    affected_entity_ids: Optional[List[str]] = None


class ServiceOperation(Protocol):
    """Service 编排操作协议骨架（仅方法签名，未实现任何业务逻辑）。

    后续业务服务实现时按各自编排流程给出具体入参语义与返回细化；
    本骨架仅固定最小边界签名，不实现识别、判定、存储或执行。
    """

    def execute(self, ctx: ServiceRequestContext) -> OperationOutcome:
        ...


__all__ = [
    "ServiceRequestContext",
    "OperationOutcomeStatus",
    "OperationOutcome",
    "DomainEntity",
    "ServiceOperation",
]