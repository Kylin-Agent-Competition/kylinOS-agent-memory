"""
test_protocol.py — 轨道 A Day5 UDS 长度前缀 JSON 协议测试

覆盖：encode/decode_packet 的正常、分包、粘包、非法输入。
本地可跑（不依赖 kylin_embedding / SDK）。

pytest 风格：正式可被 pytest 收集。
"""

import json

import pytest

from embedding.protocol import (
    IncompletePacket,
    ProtocolError,
    decode_packet,
    encode,
)


def test_encode_decode_roundtrip():
    msg = {"type": "embed", "text": "你好"}
    buf = encode(msg)
    # 4 字节长度前缀 + JSON body
    assert len(buf) > 4
    decoded, remaining = decode_packet(buf)
    assert decoded == msg
    assert remaining == b""


def test_decode_incomplete_raises():
    msg = {"type": "embed", "text": "x"}
    buf = encode(msg)
    # 只给一半数据 → IncompletePacket
    with pytest.raises(IncompletePacket):
        decode_packet(buf[:len(buf) // 2])
    # 连长度前缀都不够 → IncompletePacket
    with pytest.raises(IncompletePacket):
        decode_packet(b"\x00")


def test_decode_multiple_packets():
    m1 = {"type": "ping"}
    m2 = {"type": "embed", "text": "hello"}
    buf = encode(m1) + encode(m2)
    d1, rest = decode_packet(buf)
    assert d1 == m1
    d2, rest2 = decode_packet(rest)
    assert d2 == m2
    assert rest2 == b""


def test_decode_invalid_json():
    # 声明长度 10 但内容不是 JSON
    bad = b"\x00\x00\x00\x0a" + b"not-json!!"
    with pytest.raises(ProtocolError):
        decode_packet(bad)


def test_decode_non_dict():
    body = json.dumps([1, 2, 3]).encode()
    buf = len(body).to_bytes(4, "big") + body
    with pytest.raises(ProtocolError):
        decode_packet(buf)


def test_oversize_rejected():
    # 声明超大长度 → ProtocolError
    bad = b"\xff\xff\xff\xff" + b"x"
    with pytest.raises(ProtocolError):
        decode_packet(bad)
