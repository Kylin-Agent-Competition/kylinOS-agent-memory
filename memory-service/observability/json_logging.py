"""json_logging.py — JSON 结构化日志 Formatter + PII 脱敏 filter（T3.2）

契约（checklist 6.4 / T3.2）：
  - 每行 JSON：{ts, level, logger, trace_id, request_id, method, message}
  - trace_id/request_id/method 来自 `observability.request_context` 线程局部
    （Gateway _dispatch 设置/清理，见 server.py）
  - PII 脱敏 filter：日志 message 不得含 content 正文 / API Key / 密码 / Token /
    私钥；业务层日志点自行遵守 + 本 filter 兜底（发现敏感模式 → 掩码或降级）
  - 与现有文本日志兼容：setup_logging 提供 json_logs 开关（T3.4），
    production 默认 JSON，测试可关

实现：
  - JsonFormatter(logging.Formatter)：格式化单行 JSON（ensure_ascii=False，UTF-8）
  - PiiSanitizeFilter(logging.Filter)：message 中敏感模式掩码
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from observability.request_context import get_request_context

# 敏感模式（兜底脱敏；业务日志点仍须自行遵守「禁止记录 content/PII」）
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|private[_-]?key)\s*[=:]\s*\S+"),
    re.compile(r"\b[0-9a-f]{32,}\b"),  # 长 hex（疑似 token/私钥片段）
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),  # OpenAI 风格 sk- key
]
_MASK = "***REDACTED***"


def sanitize_message(message: str) -> str:
    """message 脱敏（PII 兜底 filter）。"""
    for pattern in _SENSITIVE_PATTERNS:
        message = pattern.sub(_MASK, message)
    return message


class PiiSanitizeFilter(logging.Filter):
    """日志 message 脱敏 filter（所有 handler 挂载，兜底防 PII 泄漏）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = sanitize_message(record.getMessage())
            record.args = ()  # 已合并进 msg，避免二次格式化重复脱敏
        except Exception:  # noqa: BLE001 格式化失败不阻塞日志
            pass
        return True


class JsonFormatter(logging.Formatter):
    """单行 JSON 日志 Formatter（UTF-8，ensure_ascii=False）。"""

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_request_context()
        entry: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": ctx.get("trace_id", ""),
            "request_id": ctx.get("request_id", ""),
            "method": ctx.get("method", ""),
            "message": sanitize_message(record.getMessage()),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)
