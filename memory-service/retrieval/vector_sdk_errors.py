"""Vector SDK VectorDB::StatusCode -> B 层 RetrievalError 映射（V002）。

来源：libkysdk-vector-engine-client 1.2.0.0-0k0.7 的
include/kysdk-vector-engine-client/types/Status.h（Milvus-Lite 派生）。

V002 实测结论（Kylin V11，2026-08-22）：运行库对多数校验类错误统一返回
SERVER_FAILED(1002)，具体原因只体现在 Message() 中，并未使用头文件里
的 INVALID_AGUMENT(1000) / DIMENSION_NOT_EQUAL(2000) / VECTOR_IS_EMPTY(2001)
等细分码。因此本模块对 1002 做消息级细分，对其余码做静态码表映射。
本模块是纯函数，不依赖 SDK / SQLite / 麒麟宿主，只输出结构化 RetrievalError。
"""

from __future__ import annotations

from enum import IntEnum

from retrieval.contracts import RetrievalError, RetrievalErrorCode


class VectorSdkStatusCode(IntEnum):
    """VectorDB::StatusCode 的整数值（与 SDK 头文件保持一致）。"""

    OK = 0
    UNKNOWN_ERROR = 1
    NOT_SUPPORTED = 2
    NOT_CONNECTED = 3
    APPID_EMPTY = 4
    INVALID_AGUMENT = 1000  # SDK 原始拼写，保持原样
    RPC_FAILED = 1001
    SERVER_FAILED = 1002
    TIMEOUT = 1003
    DATABASE_INIT_FAILED = 1100
    DIMENSION_NOT_EQUAL = 2000
    VECTOR_IS_EMPTY = 2001
    JSON_PARSE_ERROR = 2002


_SDK_TO_RETRIEVAL: dict[int, tuple[RetrievalErrorCode, bool]] = {
    int(VectorSdkStatusCode.UNKNOWN_ERROR): (RetrievalErrorCode.INTERNAL, False),
    int(VectorSdkStatusCode.NOT_SUPPORTED): (RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, False),
    int(VectorSdkStatusCode.NOT_CONNECTED): (RetrievalErrorCode.PROVIDER_UNAVAILABLE, True),
    int(VectorSdkStatusCode.APPID_EMPTY): (RetrievalErrorCode.INVALID_ARGUMENT, False),
    int(VectorSdkStatusCode.INVALID_AGUMENT): (RetrievalErrorCode.INVALID_ARGUMENT, False),
    int(VectorSdkStatusCode.RPC_FAILED): (RetrievalErrorCode.PROVIDER_UNAVAILABLE, True),
    int(VectorSdkStatusCode.SERVER_FAILED): (RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, False),
    int(VectorSdkStatusCode.TIMEOUT): (RetrievalErrorCode.DEADLINE_EXCEEDED, True),
    int(VectorSdkStatusCode.DATABASE_INIT_FAILED): (RetrievalErrorCode.PROVIDER_NOT_READY, False),
    int(VectorSdkStatusCode.DIMENSION_NOT_EQUAL): (RetrievalErrorCode.DIMENSION_MISMATCH, False),
    int(VectorSdkStatusCode.VECTOR_IS_EMPTY): (RetrievalErrorCode.INVALID_ARGUMENT, False),
    int(VectorSdkStatusCode.JSON_PARSE_ERROR): (RetrievalErrorCode.INVALID_ARGUMENT, False),
}


def _refine_server_failed(message: str) -> RetrievalErrorCode:
    """SERVER_FAILED(1002) 的消息级细分（基于 V002 实测消息）。"""
    lowered = message.lower()
    if "collection not found" in lowered:
        return RetrievalErrorCode.PROVIDER_NOT_READY
    if "dimension" in lowered or "dim(" in lowered or "vector size" in lowered:
        return RetrievalErrorCode.DIMENSION_MISMATCH
    if "expr" in lowered or "invalid parameter" in lowered or "num_rows" in lowered:
        return RetrievalErrorCode.INVALID_ARGUMENT
    return RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR


def map_sdk_status(
    status_code: int,
    message: str,
    *,
    provider: str = "vector_sdk",
    stage: str = "provider",
) -> RetrievalError:
    """把 SDK 错误状态码映射为结构化 RetrievalError。

    未知状态码 fail-closed 为 INTERNAL；OK（成功）不应传入。SERVER_FAILED
    会按消息进一步细分到维度不匹配 / 非法参数 / 集合未就绪。
    """
    if status_code == int(VectorSdkStatusCode.OK):
        raise ValueError("OK 表示成功，不应映射为错误")
    if status_code == int(VectorSdkStatusCode.SERVER_FAILED):
        code = _refine_server_failed(message)
        retryable = False
    else:
        code, retryable = _SDK_TO_RETRIEVAL.get(
            status_code, (RetrievalErrorCode.INTERNAL, False)
        )
    return RetrievalError(
        code=code,
        message=message.strip() or code.value,
        retryable=retryable,
        stage=stage,
        provider=provider,
        details={"sdk_status_code": int(status_code)},
    )
