"""
security 包 — Day4 E 轨安全决策表达层（Security）骨架

标记：D4_SKELETON / NOT_IPC_CONTRACT / NOT_PERSISTENCE_CONTRACT

承载安全决策与策略边界的最小类型：决策类型、决策结果与策略协议骨架。
仅从 .contracts 导出骨架类型；不实现任何识别器、授权存储、KYSEC、ACL 或删除。

范围边界：
- 不是 IPC 协议、不是持久化契约、不是已冻结公开 API。
- 不实现敏感信息检测正则、KYSEC 规则、ACL、Tool 真实性判断或遗忘执行。

Day6 扩展（本包职责范围说明，不改变包级公开面）：
- 自 Day6 起新增 source_admission 子模块（事件级多源业务准入策略，
  标记 D6E_SOURCE_ADMISSION）：在 A 轨 PipelineResult 输出之后、抽取之前，
  将安全红线、用户隔离、质量 Gate 与 Tool 真实状态转换为可测试的
  ALLOW_EXTRACTION / AUDIT_ONLY / REJECT 决策（不抽取、不持久化）。
- 包级公开 __all__ 仍只暴露 Day4 骨架安全决策类型；source_admission 的
  类型须通过 security.source_admission 显式导入（不进入包顶层命名空间）。
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