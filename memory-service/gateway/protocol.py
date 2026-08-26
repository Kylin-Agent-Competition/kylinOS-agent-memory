"""protocol.py — D4D IPC 协议（FRZ-IPC-001/002/003/004/006，按冻结实现）

契约来源：deliverables/D4_IPC_PROTOCOL_FREEZE_20260807.md + FORMAL_FREEZE_20260817.md
  - FRZ-IPC-001：4 字节 Big-Endian uint32 长度 + UTF-8 JSON，最大 65536 字节（64KB）
  - FRZ-IPC-002：错误码枚举 5 项（含 TIMEOUT，2026-08-17 补充）
  - FRZ-IPC-003：protocol_version 固定 "1.0"
  - FRZ-IPC-004：deadline_ms 字段与超时语义
  - FRZ-IPC-006：请求 7 字段 / 响应 6 字段 + 错误附加字段

注意：本模块是新 Gateway 的冻结实现（ALIGN-001~005 要求新代码按冻结写），
与 embedding/protocol.py（旧实现，4MiB/独立错误码域，偏离已登记）互不依赖。
"""

from __future__ import annotations

import json
import struct
from typing import Any, Dict, Optional, Tuple

HEADER_LEN = 4
MAX_MSG_LEN = 65536  # FRZ-IPC-001：64KB（冻结）

PROTOCOL_VERSION = "1.0"  # FRZ-IPC-003（冻结）

# FRZ-IPC-002 错误码枚举（5 项，冻结；仅允许 ADR 新增）
ERROR_CODE_UNSUPPORTED_METHOD = "UNSUPPORTED_METHOD"
ERROR_CODE_INVALID_REQUEST = "INVALID_REQUEST"
ERROR_CODE_PROTOCOL_ERROR = "PROTOCOL_ERROR"
ERROR_CODE_INTERNAL_ERROR = "INTERNAL_ERROR"
ERROR_CODE_TIMEOUT = "TIMEOUT"

# 内部异常类型 → 冻结错误码映射（FRZ-IPC-002 §2.2 安全映射规则）
INTERNAL_ERROR_MAP = {
    "UNKNOWN_METHOD": ERROR_CODE_UNSUPPORTED_METHOD,
    "INVALID_MESSAGE": ERROR_CODE_INVALID_REQUEST,
    "PROTOCOL_ERROR": ERROR_CODE_PROTOCOL_ERROR,
    "TIMEOUT": ERROR_CODE_TIMEOUT,
    "INTERNAL_ERROR": ERROR_CODE_INTERNAL_ERROR,
}

# 请求必填字段（FRZ-IPC-006 §6.1：7 字段，protocol_version/request_id/trace_id/
# method/deadline_ms/payload 必填；idempotency_key 可选）
REQUIRED_REQUEST_FIELDS = (
    "protocol_version",
    "request_id",
    "trace_id",
    "method",
    "deadline_ms",
    "payload",
)


class ProtocolError(Exception):
    """协议层错误（帧/JSON/字段级）。"""

    def __init__(self, message: str, error_code: str = ERROR_CODE_PROTOCOL_ERROR) -> None:
        super().__init__(message)
        self.error_code = error_code


class IncompletePacket(Exception):
    """缓冲区不足一个完整包（调用方继续收数据）。"""


class RequestValidationError(Exception):
    """请求字段校验失败（FRZ-IPC-006）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = ERROR_CODE_INVALID_REQUEST


def safe_error_code(raw: str) -> str:
    """内部错误字符串 → 冻结枚举（FRZ-IPC-002 §2.2 安全映射，禁止泄漏 traceback）。"""
    return INTERNAL_ERROR_MAP.get(raw, ERROR_CODE_INTERNAL_ERROR)


# ── 线协议编解码（FRZ-IPC-001） ──


def encode(msg: Dict[str, Any]) -> bytes:
    """dict → 长度前缀 JSON 帧（4B BE + UTF-8 JSON，64KB 上限）。"""
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_MSG_LEN:
        raise ProtocolError(f"message too large: {len(body)} > {MAX_MSG_LEN}")
    return struct.pack(">I", len(body)) + body


def decode_packet(buf: bytes) -> Tuple[Dict[str, Any], bytes]:
    """缓冲区解析一个完整包。

    Returns:
        (msg_dict, remaining_buf)。

    Raises:
        IncompletePacket: 数据不足一个完整包。
        ProtocolError: 长度非法 / 非法 UTF-8 / JSON 解码失败 / 非 dict。
    """
    if len(buf) < HEADER_LEN:
        raise IncompletePacket()
    (body_len,) = struct.unpack(">I", buf[:HEADER_LEN])
    if body_len > MAX_MSG_LEN:
        raise ProtocolError(f"declared length too large: {body_len} > {MAX_MSG_LEN}")
    if len(buf) < HEADER_LEN + body_len:
        raise IncompletePacket()
    body = buf[HEADER_LEN : HEADER_LEN + body_len]
    try:
        msg = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc
    if not isinstance(msg, dict):
        raise ProtocolError(f"message must be dict, got {type(msg).__name__}")
    return msg, buf[HEADER_LEN + body_len :]


# ── 请求校验（FRZ-IPC-003/004/006） ──


def validate_request(msg: Dict[str, Any]) -> None:
    """校验请求 envelope（协议版本 + 必填字段 + deadline_ms 类型）。

    Raises:
        ProtocolError: protocol_version 不匹配（FRZ-IPC-003）。
        RequestValidationError: 必填字段缺失 / 类型错误（FRZ-IPC-006）。
    """
    if msg.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolError(
            f"unsupported protocol_version: {msg.get('protocol_version')!r}"
        )
    for field in REQUIRED_REQUEST_FIELDS:
        if field not in msg:
            raise RequestValidationError(f"missing required field: {field}")
    deadline = msg["deadline_ms"]
    if not isinstance(deadline, int) or deadline <= 0:
        raise RequestValidationError("deadline_ms must be positive int")
    payload = msg["payload"]
    if not isinstance(payload, dict):
        raise RequestValidationError("payload must be object")


# ── 响应构造（FRZ-IPC-006 §6.2） ──


def build_response(
    *,
    request_id: str,
    trace_id: str,
    status: str = "ok",
    data: Optional[Dict[str, Any]] = None,
    server_ts: Optional[str] = None,
    error_code: Optional[str] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """构造响应 envelope（6 字段 + 错误附加字段）。"""
    import datetime

    resp: Dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "trace_id": trace_id,
        "status": status,
        "data": data if data is not None else {},
        "server_ts": server_ts
        or datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if status == "error":
        resp["error_code"] = error_code or ERROR_CODE_INTERNAL_ERROR
        resp["message"] = message or "internal error"
    return resp


def build_error_response(
    *,
    request_id: str,
    trace_id: str,
    error_code: str,
    message: str,
) -> Dict[str, Any]:
    """构造错误响应（status="error" + error_code/message，不含堆栈）。"""
    return build_response(
        request_id=request_id,
        trace_id=trace_id,
        status="error",
        error_code=error_code,
        message=message,
    )
