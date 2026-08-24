"""
protocol.py — 轨道 A Day5 UDS 长度前缀 JSON 协议

协议格式（总体架构文档 4.4 IPC 契约，TABLE 12/48，已冻结）：
  每个消息 = 4 字节大端长度前缀 + UTF-8 JSON body
  body 为 envelope dict：
    {
      "protocol_version": "1.0",
      "request_id": "req_...",
      "trace_id": "trc_...",
      "method": "memory.embed",
      "deadline_ms": 5000,
      "payload": {...}
    }

示例:
  b'\x00\x00\x00\x2f' + b'{"protocol_version": "1.0", "method": "memory.embed", ...}'

职责：
  - encode(msg_dict) -> bytes（长度前缀 JSON）
  - decode_packet(buf) -> (msg_dict, remaining_buf)
  - build_envelope(...) / parse_envelope(...)：架构 4.4 的请求/响应 envelope 构造与校验
"""

from __future__ import annotations

import json
import struct
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

HEADER_LEN = 4
MAX_MSG_LEN = 65536  # 64KB 上限（FRZ-IPC-001 冻结；防恶意超大包）

# 架构 4.4 IPC 契约：协议版本（冻结，TABLE 12/48）
PROTOCOL_VERSION = "1.0"

# FRZ-IPC-004：deadline_ms 无默认值、客户端必须显式设置；build_envelope 兜底用此默认。
DEFAULT_DEADLINE_MS = 5000


class ProtocolError(Exception):
    """协议编解码/校验错误。

    Attributes:
        code: FRZ-IPC-002 冻结错误码语义（PROTOCOL_ERROR / INVALID_REQUEST /
              UNSUPPORTED_METHOD），供 handle_request 层直接映射到冻结枚举，
              避免把所有协议错误一律归为 PROTOCOL_ERROR。
    """

    def __init__(self, message: str, *, code: str = "PROTOCOL_ERROR"):
        super().__init__(message)
        self.code = code


def _new_id(prefix: str) -> str:
    """生成 build_envelope 兜底用的 request_id / trace_id。"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def encode(msg: Dict[str, Any]) -> bytes:
    """把 dict 编码为长度前缀 JSON。"""
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_MSG_LEN:
        raise ProtocolError(f"message too large: {len(body)} bytes")
    return struct.pack(">I", len(body)) + body


def decode_packet(buf: bytes) -> Tuple[Dict[str, Any], bytes]:
    """从缓冲区解析一个完整包。

    Returns:
        (msg_dict, remaining_buf)：解析出的消息 + 剩余未消费数据。
        若缓冲区不足一个完整包，抛出 IncompletePacket（调用方继续收数据）。

    Raises:
        ProtocolError: 包长度非法或 JSON 解码失败。
    """
    if len(buf) < HEADER_LEN:
        raise IncompletePacket()

    (body_len,) = struct.unpack(">I", buf[:HEADER_LEN])
    if body_len == 0:
        # 显式拒绝 0 长度消息（合法帧不允许空 body，防解析歧义）
        raise ProtocolError("zero-length message")
    if body_len > MAX_MSG_LEN:
        raise ProtocolError(f"declared length too large: {body_len}")
    if len(buf) < HEADER_LEN + body_len:
        raise IncompletePacket()

    body = buf[HEADER_LEN:HEADER_LEN + body_len]
    try:
        msg = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc

    if not isinstance(msg, dict):
        raise ProtocolError(f"message must be dict, got {type(msg).__name__}")

    return msg, buf[HEADER_LEN + body_len:]


class IncompletePacket(Exception):
    """缓冲区数据不足一个完整包（调用方应继续接收）。"""


# ── 架构 4.4 IPC envelope（请求/响应统一结构） ──


def build_envelope(
    method: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    deadline_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """构造请求 envelope（架构 4.4 IPC 契约示例）。

    Args:
        method: 方法名（如 memory.embed / memory.health）。
        payload: 方法参数 dict。
        request_id / trace_id: 可观测性标识（架构 13.2，TABLE 36）。
        deadline_ms: 整体预算（毫秒）。

    Returns:
        envelope dict（protocol_version/method/payload + 可选字段）。
    """
    env: Dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "method": method,
        # FRZ-IPC-006 §6.1：request_id/trace_id/deadline_ms 为必填契约字段。
        # 客户端未显式提供时兜底生成（保证 build_envelope 产出合法请求）。
        "request_id": request_id or _new_id("req"),
        "trace_id": trace_id or _new_id("trc"),
        "deadline_ms": deadline_ms if deadline_ms is not None else DEFAULT_DEADLINE_MS,
        "payload": payload if payload is not None else {},
    }
    return env


def parse_envelope(
    msg: Dict[str, Any],
    *,
    expected_methods: Optional[set] = None,
) -> Tuple[str, Dict[str, Any], str, str, int]:
    """校验并规范化请求 envelope（FRZ-IPC-006 §6.1 必填字段契约）。

    Returns:
        (method, payload, request_id, trace_id, deadline_ms)

    Raises:
        ProtocolError：携带 `code` 区分错误语义（FRZ-IPC-002 §2.1）：
          - code="PROTOCOL_ERROR"     ：protocol_version 缺失/不兼容、顶层非 dict
          - code="UNSUPPORTED_METHOD" ：method 不在白名单（FRZ-IPC-007）
          - code="INVALID_REQUEST"    ：必填字段缺失/类型错误（method/request_id/
                                        trace_id/deadline_ms/payload）
    """
    if not isinstance(msg, dict):
        raise ProtocolError(f"envelope must be dict, got {type(msg).__name__}",
                            code="PROTOCOL_ERROR")

    version = msg.get("protocol_version")
    if version is None:
        raise ProtocolError("missing protocol_version", code="PROTOCOL_ERROR")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"unsupported protocol_version: {version!r} (expect {PROTOCOL_VERSION!r})",
            code="PROTOCOL_ERROR")

    method = msg.get("method")
    if not isinstance(method, str) or not method:
        raise ProtocolError(
            f"missing/invalid method: {method!r}", code="INVALID_REQUEST")
    if expected_methods is not None and method not in expected_methods:
        raise ProtocolError(
            f"unknown method: {method!r} (expect {sorted(expected_methods)})",
            code="UNSUPPORTED_METHOD")

    request_id = msg.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise ProtocolError(
            f"missing/invalid request_id: {request_id!r}", code="INVALID_REQUEST")

    trace_id = msg.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise ProtocolError(
            f"missing/invalid trace_id: {trace_id!r}", code="INVALID_REQUEST")

    deadline_ms = msg.get("deadline_ms")
    if (isinstance(deadline_ms, bool) or not isinstance(deadline_ms, int)
            or deadline_ms <= 0):
        raise ProtocolError(
            f"missing/invalid deadline_ms: {deadline_ms!r}", code="INVALID_REQUEST")

    payload = msg.get("payload")
    if payload is None:
        raise ProtocolError("missing payload", code="INVALID_REQUEST")
    if not isinstance(payload, dict):
        raise ProtocolError(
            f"payload must be dict, got {type(payload).__name__}", code="INVALID_REQUEST")

    return (method, payload, request_id, trace_id, deadline_ms)


def build_error_envelope(
    code: str,
    message: str,
    *,
    request_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    """FRZ-IPC-006 §6.2 冻结错误 envelope（单一实现，供 server/service 共用）。

    `code` 须已映射到 FRZ-IPC-002 冻结枚举（调用方负责 map_error_code）。
    成功/失败均携带 `data`（§6.2 要求始终存在；错误时为 `{}`）。
    """
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id or "",
        "trace_id": trace_id or "",
        "status": "error",
        "data": {},
        "error_code": code,
        "message": message,
        "server_ts": datetime.now(timezone.utc).isoformat(),
    }
