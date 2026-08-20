"""
security/contracts.py — Day4 E 轨 Security 安全决策边界骨架

标记：D4_SKELETON / NOT_IPC_CONTRACT / NOT_PERSISTENCE_CONTRACT

本模块只表达安全决策的业务语义与策略边界（用户归属、规则 ID、allow/deny、
原因、隔离违规标记），为后续安全策略实现提供承载结构。它：

- 不实现任何敏感信息识别器（正则/规则集）、授权存储、KYSEC 规则、ACL；
- 不实现 Tool 真实性判断、遗忘目标解析或真实删除；
- 不是 IPC 协议、不是持久化契约、不是已冻结公开 API。

对齐来源：
- D3_MEMORY_SECURITY_ACCEPTANCE_V1.md（SEC-UI-01..07 / SEC-SENS-* /
  SEC-AUTH-01 规则 ID 语义，仅结构承载，不实现规则引擎）；
- D3_MEMORY_BUSINESS_CONTRACT_V1.md §7.1（user_id 隔离键）、§7.7（脱敏占位）。

复用约束：
- NonEmptyStr 复用自 domain.common（不重复定义）；
- 本模块不复制 domain 或 pipeline 中已存在的同名 Enum / Pydantic 模型。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict

from domain.common import NonEmptyStr


class SecurityDecisionType(str, Enum):
    """安全策略对一次操作的决策类型（新建，与既有枚举语义不同）。

    语义边界：
    - ResolutionStatus（domain.enums）表达冲突消解状态；
    - 本枚举只表达安全策略对一次操作的放行/拒绝/脱敏/升级决策：
      allow（放行）、deny（拒绝）、redact（脱敏占位，对齐 D3 §7.7 /
      SEC-SENS-01/02/04）、escalate（升级待终审，对齐 SEC-AUTH-01 /
      HD-ANNO-05 语义）。
    """

    ALLOW = "allow"
    DENY = "deny"
    REDACT = "redact"
    ESCALATE = "escalate"


class SecurityDecision(BaseModel):
    """安全决策的业务表达（非 ACL 记录、非 KYSEC 规则文件、非真实授权判定结果）。

    仅结构承载：声明安全决策各要素，不实现规则引擎、识别器或授权存储。
    """

    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyStr  # 用户归属边界（D3 §7.1、SEC-UI-*），*禁止模型生成
    rule_id: NonEmptyStr  # 引用 D3 SEC-* 规则 ID（如 "SEC-UI-01"），仅结构承载
    decision: SecurityDecisionType
    reason: Optional[str] = None
    isolation_violation: bool = False  # 跨用户隔离违规标记（D3 §7.1 / 标注规范 §5.3）


class SecurityPolicy(Protocol):
    """安全策略协议骨架（仅方法签名，未实现识别 / 授权 / KYSEC / 删除）。

    与 service 层解耦：入参为原始字符串，不依赖 ServiceRequestContext；
    后续策略实现需细化规则判定与数据来源，本骨架仅固定最小边界签名。
    """

    def evaluate(self, user_id: str, rule_id: str) -> SecurityDecision:
        ...


__all__ = [
    "SecurityDecisionType",
    "SecurityDecision",
    "SecurityPolicy",
]