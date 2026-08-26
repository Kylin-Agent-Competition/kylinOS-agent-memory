"""D4D 协议测试：FRZ-IPC-001/002/003/004/006（长度前缀 JSON / 错误码 / 版本 / 字段）"""

from __future__ import annotations

import json

import pytest

from gateway import protocol as proto


# ── FRZ-IPC-001 线协议 ──


def test_encode_decode_roundtrip():
    msg = {"protocol_version": "1.0", "method": "echo", "payload": {"a": 1}}
    frame = proto.encode(msg)
    # 帧头 4 字节大端
    assert frame[:4] == len(json.dumps(msg, ensure_ascii=False).encode("utf-8")).to_bytes(4, "big")
    decoded, rest = proto.decode_packet(frame)
    assert decoded == msg
    assert rest == b""


def test_decode_multiple_packets_in_buffer():
    m1 = {"method": "echo", "payload": {}}
    m2 = {"method": "health", "payload": {}}
    buf = proto.encode(m1) + proto.encode(m2)
    d1, rest = proto.decode_packet(buf)
    d2, rest2 = proto.decode_packet(rest)
    assert d1 == m1 and d2 == m2 and rest2 == b""


def test_encode_64kb_limit():
    # 超过 64KB（FRZ-IPC-001：最大 65536 字节）→ ProtocolError
    big = {"payload": {"x": "a" * 70000}}
    with pytest.raises(proto.ProtocolError, match="too large"):
        proto.encode(big)


def test_decode_declared_length_too_large():
    # 声明长度超过 64KB → PROTOCOL_ERROR
    buf = (70000).to_bytes(4, "big") + b"{}"
    with pytest.raises(proto.ProtocolError, match="too large"):
        proto.decode_packet(buf)


def test_decode_invalid_json():
    body = b"{not json"
    buf = len(body).to_bytes(4, "big") + body
    with pytest.raises(proto.ProtocolError, match="invalid JSON"):
        proto.decode_packet(buf)


def test_decode_non_dict():
    body = b"[1,2,3]"
    buf = len(body).to_bytes(4, "big") + body
    with pytest.raises(proto.ProtocolError, match="must be dict"):
        proto.decode_packet(buf)


def test_decode_incomplete():
    full = proto.encode({"method": "echo"})
    with pytest.raises(proto.IncompletePacket):
        proto.decode_packet(full[:2])
    with pytest.raises(proto.IncompletePacket):
        proto.decode_packet(full[:-1])


# ── FRZ-IPC-003 protocol_version ──


def test_validate_version_mismatch():
    with pytest.raises(proto.ProtocolError, match="unsupported protocol_version"):
        proto.validate_request(
            {"protocol_version": "2.0", "request_id": "r", "trace_id": "t",
             "method": "echo", "deadline_ms": 100, "payload": {}}
        )


# ── FRZ-IPC-006 请求字段 ──


def test_validate_missing_field():
    with pytest.raises(proto.RequestValidationError, match="missing required field"):
        proto.validate_request(
            {"protocol_version": "1.0", "request_id": "r", "method": "echo",
             "deadline_ms": 100, "payload": {}}
        )


def test_validate_bad_deadline():
    for bad in (0, -1, "100"):
        with pytest.raises(proto.RequestValidationError):
            proto.validate_request(
                {"protocol_version": "1.0", "request_id": "r", "trace_id": "t",
                 "method": "echo", "deadline_ms": bad, "payload": {}}
            )


def test_validate_bad_payload():
    with pytest.raises(proto.RequestValidationError, match="payload"):
        proto.validate_request(
            {"protocol_version": "1.0", "request_id": "r", "trace_id": "t",
             "method": "echo", "deadline_ms": 100, "payload": "not-object"}
        )


def test_validate_ok_with_idempotency_key():
    # idempotency_key 可选（FRZ-IPC-006 §6.1）
    proto.validate_request(
        {"protocol_version": "1.0", "request_id": "r", "trace_id": "t",
         "method": "memory.store", "deadline_ms": 100,
         "idempotency_key": "uuid", "payload": {}}
    )


# ── FRZ-IPC-002 错误码与安全映射 ──


def test_safe_error_code_mapping():
    assert proto.safe_error_code("UNKNOWN_METHOD") == "UNSUPPORTED_METHOD"
    assert proto.safe_error_code("INVALID_MESSAGE") == "INVALID_REQUEST"
    assert proto.safe_error_code("PROTOCOL_ERROR") == "PROTOCOL_ERROR"
    assert proto.safe_error_code("TIMEOUT") == "TIMEOUT"
    assert proto.safe_error_code("any unknown string") == "INTERNAL_ERROR"


def test_error_code_enum_complete():
    # FRZ-IPC-002 冻结 5 项（含 TIMEOUT，2026-08-17 补充）
    assert proto.ERROR_CODE_UNSUPPORTED_METHOD == "UNSUPPORTED_METHOD"
    assert proto.ERROR_CODE_INVALID_REQUEST == "INVALID_REQUEST"
    assert proto.ERROR_CODE_PROTOCOL_ERROR == "PROTOCOL_ERROR"
    assert proto.ERROR_CODE_INTERNAL_ERROR == "INTERNAL_ERROR"
    assert proto.ERROR_CODE_TIMEOUT == "TIMEOUT"


# ── FRZ-IPC-006 响应结构 ──


def test_build_response_ok():
    resp = proto.build_response(request_id="r1", trace_id="t1", data={"ok": 1})
    assert resp["protocol_version"] == "1.0"
    assert resp["request_id"] == "r1"
    assert resp["trace_id"] == "t1"
    assert resp["status"] == "ok"
    assert resp["data"] == {"ok": 1}
    assert "server_ts" in resp
    assert "error_code" not in resp


def test_build_error_response():
    resp = proto.build_error_response(
        request_id="r1", trace_id="t1", error_code="UNSUPPORTED_METHOD", message="no"
    )
    assert resp["status"] == "error"
    assert resp["error_code"] == "UNSUPPORTED_METHOD"
    assert resp["message"] == "no"
    assert resp["data"] == {}
