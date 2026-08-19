"""
service 包 — Day4 E 轨业务编排层（Service）骨架

标记：D4_SKELETON / NOT_IPC_CONTRACT / NOT_PERSISTENCE_CONTRACT

承载 E 轨业务编排层的最小边界类型：请求上下文、操作结果边界与编排操作协议骨架。
仅从 .contracts 导出骨架类型；不导出 Domain 对象；不实现任何业务算法。

范围边界：
- 不是 IPC 协议、不是持久化契约、不是已冻结公开 API。
- 不实现 Repository / UoW / SQLite / Outbox / FTS5 / Vector / IPC / systemd。
"""

from .contracts import (
    DomainEntity,
    OperationOutcome,
    OperationOutcomeStatus,
    ServiceOperation,
    ServiceRequestContext,
)

__all__ = [
    "ServiceRequestContext",
    "OperationOutcomeStatus",
    "OperationOutcome",
    "DomainEntity",
    "ServiceOperation",
]