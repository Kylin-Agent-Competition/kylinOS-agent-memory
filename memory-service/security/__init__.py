"""
security 包 — Day4 E 轨安全决策表达层（Security）骨架

标记：D4_SKELETON / NOT_IPC_CONTRACT / NOT_PERSISTENCE_CONTRACT

承载安全决策与策略边界的最小类型：决策类型、决策结果与策略协议骨架。
仅从 .contracts 导出骨架类型；不实现任何识别器、授权存储、KYSEC、ACL 或删除。

范围边界：
- 不是 IPC 协议、不是持久化契约、不是已冻结公开 API。
- 不实现敏感信息检测正则、KYSEC 规则、ACL、Tool 真实性判断或遗忘执行。
"""

from .contracts import (
    SecurityDecision,
    SecurityDecisionType,
    SecurityPolicy,
)

__all__ = [
    "SecurityDecisionType",
    "SecurityDecision",
    "SecurityPolicy",
]