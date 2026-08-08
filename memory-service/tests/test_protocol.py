"""
test_protocol.py — 轨道 A Day5 UDS 长度前缀 JSON 协议测试

覆盖：encode/decode_packet 的正常、分包、粘包、非法输入。
本地可跑（不依赖 kylin_embedding / SDK）。

pytest 风格：正式可被 pytest 收集。
"""

import json

import pytest

from embedding.protocol import (
    PROTOCOL_VERSION,
    IncompletePacket,
    ProtocolError,
    build_envelope,
    decode_packet,
    encode,
    parse_envelope,
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


# ── 架构 4.4 envelope（协议版本/method/payload/可观测字段） ──


def test_build_envelope_fields():
    """build_envelope：protocol_version/method/payload + 可选 request_id/trace_id/deadline_ms。"""
    env = build_envelope("memory.embed", {"text": "hi"},
                         request_id="req-1", trace_id="trc-1", deadline_ms=150)
    assert env["protocol_version"] == PROTOCOL_VERSION == "1.0"
    assert env["method"] == "memory.embed"
    assert env["payload"] == {"text": "hi"}
    assert env["request_id"] == "req-1"
    assert env["trace_id"] == "trc-1"
    assert env["deadline_ms"] == 150


def test_parse_envelope_valid():
    """parse_envelope：合法 envelope 返回规范化字段。"""
    env = build_envelope("memory.embed", {"text": "x"},
                         request_id="r", trace_id="t")
    method, payload, rid, tid, deadline = parse_envelope(
        env, expected_methods={"memory.embed"})
    assert method == "memory.embed"
    assert payload == {"text": "x"}
    assert rid == "r" and tid == "t"
    assert deadline is None


def test_parse_envelope_missing_version():
    """缺 protocol_version → ProtocolError。"""
    with pytest.raises(ProtocolError, match="protocol_version"):
        parse_envelope({"method": "memory.embed", "payload": {}})


def test_parse_envelope_bad_version():
    """protocol_version 不兼容 → ProtocolError。"""
    with pytest.raises(ProtocolError, match="protocol_version"):
        parse_envelope({"protocol_version": "0.9", "method": "memory.embed",
                         "payload": {}})


def test_parse_envelope_unknown_method():
    """method 不在白名单 → ProtocolError。"""
    with pytest.raises(ProtocolError, match="unknown method"):
        parse_envelope({"protocol_version": "1.0", "method": "memory.nope",
                         "payload": {}}, expected_methods={"memory.embed"})


def test_parse_envelope_bad_payload():
    """payload 非 dict → ProtocolError。"""
    with pytest.raises(ProtocolError, match="payload"):
        parse_envelope({"protocol_version": "1.0", "method": "memory.embed",
                         "payload": "not-dict"})
