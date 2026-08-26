"""V002：SDK 错误码 -> RetrievalError 映射测试。"""

from __future__ import annotations

import pytest

from retrieval.contracts import RetrievalErrorCode
from retrieval.vector_sdk_errors import VectorSdkStatusCode, map_sdk_status


@pytest.mark.parametrize(
    ("sdk_code", "expected"),
    [
        (VectorSdkStatusCode.UNKNOWN_ERROR, RetrievalErrorCode.INTERNAL),
        (VectorSdkStatusCode.NOT_SUPPORTED, RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR),
        (VectorSdkStatusCode.NOT_CONNECTED, RetrievalErrorCode.PROVIDER_UNAVAILABLE),
        (VectorSdkStatusCode.APPID_EMPTY, RetrievalErrorCode.INVALID_ARGUMENT),
        (VectorSdkStatusCode.INVALID_AGUMENT, RetrievalErrorCode.INVALID_ARGUMENT),
        (VectorSdkStatusCode.RPC_FAILED, RetrievalErrorCode.PROVIDER_UNAVAILABLE),
        (VectorSdkStatusCode.TIMEOUT, RetrievalErrorCode.DEADLINE_EXCEEDED),
        (VectorSdkStatusCode.DATABASE_INIT_FAILED, RetrievalErrorCode.PROVIDER_NOT_READY),
        (VectorSdkStatusCode.DIMENSION_NOT_EQUAL, RetrievalErrorCode.DIMENSION_MISMATCH),
        (VectorSdkStatusCode.VECTOR_IS_EMPTY, RetrievalErrorCode.INVALID_ARGUMENT),
        (VectorSdkStatusCode.JSON_PARSE_ERROR, RetrievalErrorCode.INVALID_ARGUMENT),
    ],
)
def test_map_sdk_status_code(sdk_code, expected):
    err = map_sdk_status(int(sdk_code), "boom")
    assert err.code is expected
    assert err.message == "boom"
    assert err.stage == "provider"
    assert err.provider == "vector_sdk"
    assert err.details["sdk_status_code"] == int(sdk_code)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("collection not found", RetrievalErrorCode.PROVIDER_NOT_READY),
        ("the length(3) of float data should divide the dim(4): invalid parameter", RetrievalErrorCode.DIMENSION_MISMATCH),
        ("vector dimension mismatch, expected vector size(byte) 16, actual 12.: segcore error", RetrievalErrorCode.DIMENSION_MISMATCH),
        ("the num_rows (0) of field (embedding) is not equal to passed num_rows (1): invalid parameter", RetrievalErrorCode.INVALID_ARGUMENT),
        ("expr cannot be empty: invalid parameter", RetrievalErrorCode.INVALID_ARGUMENT),
        ("Invalid expr: this is not a valid expression: invalid parameter", RetrievalErrorCode.INVALID_ARGUMENT),
    ],
)
def test_server_failed_refined_by_message(message, expected):
    err = map_sdk_status(int(VectorSdkStatusCode.SERVER_FAILED), message)
    assert err.code is expected
    assert err.retryable is False


def test_server_failed_unknown_message_is_protocol_error():
    err = map_sdk_status(int(VectorSdkStatusCode.SERVER_FAILED), "some opaque server failure")
    assert err.code is RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR


@pytest.mark.parametrize("sdk_code", [1, 3, 1001, 1003])
def test_retryable(sdk_code):
    err = map_sdk_status(sdk_code, "x")
    assert err.retryable is (sdk_code in (3, 1001, 1003))


def test_unknown_code_fails_closed():
    err = map_sdk_status(999999, "unknown")
    assert err.code is RetrievalErrorCode.INTERNAL
    assert err.retryable is False


def test_ok_raises():
    with pytest.raises(ValueError):
        map_sdk_status(int(VectorSdkStatusCode.OK), "ok")


def test_empty_message_falls_back_to_code():
    err = map_sdk_status(int(VectorSdkStatusCode.RPC_FAILED), "  ")
    assert err.message == RetrievalErrorCode.PROVIDER_UNAVAILABLE.value
