"""
test_protocol.py — 轨道 A Day5 UDS 长度前缀 JSON 协议测试

覆盖：encode/decode_packet 的正常、分包、粘包、非法输入。
本地可跑（不依赖 kylin_embedding / SDK）。

pytest 风格：正式可被 pytest 收集。
"""

import json

import pytest

from embedding.protocol import (
    MAX_MSG_LEN,
    PROTOCOL_VERSION,
    IncompletePacket,
    ProtocolError,
    build_envelope,
    build_error_envelope,
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
                         request_id="r", trace_id="t", deadline_ms=150)
    method, payload, rid, tid, deadline = parse_envelope(
        env, expected_methods={"memory.embed"})
    assert method == "memory.embed"
    assert payload == {"text": "x"}
    assert rid == "r" and tid == "t"
    assert deadline == 150


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
    """payload 非 dict → ProtocolError（INVALID_REQUEST）。"""
    with pytest.raises(ProtocolError, match="payload"):
        parse_envelope({"protocol_version": "1.0", "method": "memory.embed",
                         "request_id": "r", "trace_id": "t", "deadline_ms": 100,
                         "payload": "not-dict"})


# ── 错误 envelope typed-ID 收敛（FRZ-IPC-006 §6.2，PR#57 R5 / H-2） ──

@pytest.mark.parametrize("field, bad", [
    ("request_id", {"nested": 1}),
    ("trace_id", {"nested": 1}),
    ("request_id", 123),
    ("trace_id", 456),
    ("request_id", True),
    ("trace_id", False),
    ("request_id", []),
    ("trace_id", None),
])
def test_build_error_envelope_typed_id_converged(field, bad):
    """非法 typed request_id/trace_id（dict/int/bool/list/None）→ 收敛为空串 str。"""
    kwargs = {"request_id": "r", "trace_id": "t"}
    kwargs[field] = bad
    env = build_error_envelope("INVALID_REQUEST", "boom", **kwargs)
    assert isinstance(env["request_id"], str)
    assert isinstance(env["trace_id"], str)
    # 被污染字段收敛为空串；另一字段保持原字符串
    assert env[field] == ""


def test_build_error_envelope_empty_str_id_preserved():
    """空串 request_id/trace_id 恒为 str（不被 or '' 之外的逻辑改动）。"""
    env = build_error_envelope("INVALID_REQUEST", "boom",
                               request_id="", trace_id="")
    assert env["request_id"] == "" and isinstance(env["request_id"], str)
    assert env["trace_id"] == "" and isinstance(env["trace_id"], str)


# ── 错误语义分类（FRZ-IPC-002 §2.1，PR#57 R3） ──

def test_parse_envelope_unknown_method_code():
    """unknown method → code=UNSUPPORTED_METHOD（不再归 PROTOCOL_ERROR）。"""
    with pytest.raises(ProtocolError) as exc:
        parse_envelope(
            {"protocol_version": "1.0", "method": "memory.nope",
             "request_id": "r", "trace_id": "t", "deadline_ms": 100,
             "payload": {}},
            expected_methods={"memory.embed"})
    assert exc.value.code == "UNSUPPORTED_METHOD"


@pytest.mark.parametrize("field", ["request_id", "trace_id", "deadline_ms", "payload"])
def test_parse_envelope_missing_required_field(field):
    """缺必填字段 → code=INVALID_REQUEST。"""
    env = {"protocol_version": "1.0", "method": "memory.embed",
           "request_id": "r", "trace_id": "t", "deadline_ms": 100,
           "payload": {"text": "x"}}
    del env[field]
    with pytest.raises(ProtocolError) as exc:
        parse_envelope(env, expected_methods={"memory.embed"})
    assert exc.value.code == "INVALID_REQUEST"


@pytest.mark.parametrize("field,bad", [
    ("request_id", ""),
    ("trace_id", ""),
    ("request_id", 123),
    ("trace_id", 456),
    ("deadline_ms", "5000"),
    ("deadline_ms", 0),
    ("deadline_ms", True),
    ("deadline_ms", -1),
])
def test_parse_envelope_invalid_field_type(field, bad):
    """空串 / 错误类型 / 非法值 → INVALID_REQUEST。"""
    env = {"protocol_version": "1.0", "method": "memory.embed",
           "request_id": "r", "trace_id": "t", "deadline_ms": 100,
           "payload": {"text": "x"}}
    env[field] = bad
    with pytest.raises(ProtocolError) as exc:
        parse_envelope(env, expected_methods={"memory.embed"})
    assert exc.value.code == "INVALID_REQUEST"


# ── 0 长度消息 + MAX_MSG_LEN 边界（PR#57 第 8 节） ──

def test_decode_zero_length_rejected():
    """0 长度消息 → ProtocolError（显式拒绝）。"""
    with pytest.raises(ProtocolError):
        decode_packet(b"\x00\x00\x00\x00")


def test_max_msg_len_boundary():
    """MAX_MSG_LEN 边界：65537 声明长度拒绝，65536（=上限）不因超限拒绝。"""
    # 65537 → 超限拒绝
    with pytest.raises(ProtocolError, match="too large"):
        decode_packet((MAX_MSG_LEN + 1).to_bytes(4, "big") + b"x")
    # 65536（恰好等于上限）→ 不触发"too large"，仅因缓冲不足 → IncompletePacket
    with pytest.raises(IncompletePacket):
        decode_packet(MAX_MSG_LEN.to_bytes(4, "big") + b"x")


def test_encode_rejects_over_max():
    """encode：body 超过 MAX_MSG_LEN → ProtocolError。"""
    big = {"text": "x" * (MAX_MSG_LEN + 1)}
    with pytest.raises(ProtocolError):
        encode(big)
