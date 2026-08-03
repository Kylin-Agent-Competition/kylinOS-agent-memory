"""
protocol.py — 轨道 A Day5 UDS 长度前缀 JSON 协议

协议格式（与 memory-service README 约定一致）：
  每个消息 = 4 字节大端长度前缀 + UTF-8 JSON body

示例:
  b'\x00\x00\x00\x2f' + b'{"type": "embed", "text": "hello"}'

职责：
  - encode(msg_dict) -> bytes
  - decode_packet(buf) -> (msg_dict, remaining_buf)
"""

from __future__ import annotations

import json
import struct
from typing import Any, Dict, Tuple

HEADER_LEN = 4
MAX_MSG_LEN = 4 * 1024 * 1024  # 4 MiB 上限（防恶意超大包）


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
