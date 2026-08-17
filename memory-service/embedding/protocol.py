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
from typing import Any, Dict, Optional, Tuple

HEADER_LEN = 4
MAX_MSG_LEN = 4 * 1024 * 1024  # 4 MiB 上限（防恶意超大包）

# 架构 4.4 IPC 契约：协议版本（冻结，TABLE 12/48）
PROTOCOL_VERSION = "1.0"


class ProtocolError(Exception):
    """协议编解码错误。"""


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
        "payload": payload if payload is not None else {},
    }
    if request_id is not None:
        env["request_id"] = request_id
    if trace_id is not None:
        env["trace_id"] = trace_id
    if deadline_ms is not None:
        env["deadline_ms"] = deadline_ms
    return env


def parse_envelope(
    msg: Dict[str, Any],
    *,
    expected_methods: Optional[set] = None,
) -> Tuple[str, Dict[str, Any], Optional[str], Optional[str], Optional[int]]:
    """校验并规范化请求 envelope（架构 4.4）。

    Returns:
        (method, payload, request_id, trace_id, deadline_ms)

    Raises:
        ProtocolError: protocol_version 缺失/不兼容、method 缺失/未知、payload 非 dict。
    """
    if not isinstance(msg, dict):
        raise ProtocolError(f"envelope must be dict, got {type(msg).__name__}")

    version = msg.get("protocol_version")
    if version is None:
        raise ProtocolError("missing protocol_version")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"unsupported protocol_version: {version!r} (expect {PROTOCOL_VERSION!r})")

    method = msg.get("method")
    if not isinstance(method, str) or not method:
        raise ProtocolError("missing/invalid method")
    if expected_methods is not None and method not in expected_methods:
        raise ProtocolError(
            f"unknown method: {method!r} (expect {sorted(expected_methods)})")

    payload = msg.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ProtocolError(f"payload must be dict, got {type(payload).__name__}")

    return (
        method,
        payload,
        msg.get("request_id"),
        msg.get("trace_id"),
        msg.get("deadline_ms"),
    )
