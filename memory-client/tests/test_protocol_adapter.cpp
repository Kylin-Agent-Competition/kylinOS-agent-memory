// test_protocol_adapter.cpp — 协议编解码单元测试（L0）
//
// 覆盖：
//   - encode/decode round-trip
//   - 不完整包（缓冲不足）
//   - 声明长度超限
//   - envelope 构造与解析（含可选字段省略）
//   - envelope 协议错误（缺 protocol_version / 错误类型 / payload 非 object）
//   - envelope 顶层非 JSON object
//   - 多包连续解码（流式）

#include "protocol_adapter.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QtTest>

namespace client = kylin::memory::client::v1;

class ProtocolAdapterTest final : public QObject {
    Q_OBJECT

private slots:
    void encodeDecodeRoundTrips();
    void decodeRejectsIncompletePacket();
    void decodeRejectsOversizedPacket();
    void decodeRejectsInvalidJson();
    void decodeRejectsNonObjectJson();
    void decodeConsumesMultiplePacketsInOneBuffer();
    void buildEnvelopeOmitsEmptyOptionalFields();
    void buildEnvelopeIncludesOptionalFieldsWhenProvided();
    void parseEnvelopeAcceptsValidWithOptionalFields();
    void parseEnvelopeRejectsMissingProtocolVersion();
    void parseEnvelopeRejectsUnsupportedProtocolVersion_data();
    void parseEnvelopeRejectsUnsupportedProtocolVersion();
    void parseEnvelopeRejectsNonStringProtocolVersion();
    void parseEnvelopeRejectsMissingMethod();
    void parseEnvelopeRejectsNonStringMethod();
    void parseEnvelopeRejectsEmptyMethod();
    void parseEnvelopeRejectsNonObjectPayload();
    void parseEnvelopeReadsOptionalFields();
    // parseResponse 测试（FRZ-IPC-006 §6.2 响应结构）
    void parseResponseAcceptsValidOk();
    void parseResponseAcceptsValidError();
    void parseResponseRejectsMissingStatus();
    void parseResponseRejectsInvalidStatus();
    void parseResponseRejectsMissingRequestId();
    void parseResponseRejectsMissingTraceId();
    void parseResponseRejectsMissingServerTs();
    void parseResponseRejectsOkWithoutData();
    void parseResponseRejectsMissingProtocolVersion();
    // error response 校验（MEDIUM-01）
    void parseResponseRejectsErrorWithoutErrorCode();
    void parseResponseRejectsErrorWithoutMessage();
    void parseResponseRejectsErrorWithNonStringErrorCode();
    void parseResponseRejectsErrorWithNonStringMessage();
    // error_code 冻结枚举校验（HIGH-01: isValidErrorCode 接入生产 parser）
    void parseResponseRejectsUnknownErrorCode();
    void parseResponseAcceptsAllFrozenErrorCodes();
    // server_ts ISO 8601 UTC 校验（MEDIUM-01）
    void parseResponseRejectsInvalidServerTs();
    void parseResponseRejectsEmptyServerTs();
    void parseResponseRejectsDateOnlyServerTs();
    // uint32 高位长度头边界测试（HIGH-03）
    void decodeRejectsHighBitSetLength();
    void decodeRejectsMaxUint32Length();
    void decodeRejectsJustOverLimit();
};

void ProtocolAdapterTest::encodeDecodeRoundTrips()
{
    QJsonObject envelope = client::buildEnvelope(
        client::methods::kMemoryRetrieve,
        QJsonObject{
            {QStringLiteral("schema_version"), QStringLiteral("1.0")},
            {QStringLiteral("user_id"), QStringLiteral("local-user")},
            {QStringLiteral("session_id"), QStringLiteral("session-001")},
            {QStringLiteral("query_text"), QStringLiteral("继续昨天的任务")},
            {QStringLiteral("scene"), QStringLiteral("software_development")},
            {QStringLiteral("max_context_tokens"), 800},
        },
        QStringLiteral("req-001"),
        QStringLiteral("trc-001"),
        5000);

    const auto packet = client::encodeEnvelope(envelope);
    QVERIFY(packet.has_value());

    const auto decoded = client::decodePacket(*packet);
    QVERIFY(decoded.error.ok());
    QVERIFY(decoded.envelope.has_value());
    QCOMPARE(decoded.consumed, packet->size());
    QCOMPARE(*decoded.envelope, envelope);

    const auto [parts, parseError] = client::parseEnvelope(*decoded.envelope);
    QVERIFY(parseError.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->method, client::methods::kMemoryRetrieve);
    QCOMPARE(parts->requestId, QStringLiteral("req-001"));
    QCOMPARE(parts->traceId, QStringLiteral("trc-001"));
    QVERIFY(parts->deadlineMs.has_value());
    QCOMPARE(*parts->deadlineMs, 5000);
}

void ProtocolAdapterTest::decodeRejectsIncompletePacket()
{
    const auto packet = client::encodeEnvelope(
        client::buildEnvelope(client::methods::kHealth, QJsonObject{}));
    QVERIFY(packet.has_value());

    // 仅发 2 字节 → 缺包头
    auto truncated = client::decodePacket(packet->left(2));
    QCOMPARE(truncated.error.kind, client::ProtocolErrorKind::IncompletePacket);
    QVERIFY(!truncated.envelope.has_value());
    QCOMPARE(truncated.consumed, 0);

    // 有完整包头但 body 不完整
    truncated = client::decodePacket(packet->left(4 + 5));
    QCOMPARE(truncated.error.kind, client::ProtocolErrorKind::IncompletePacket);
    QCOMPARE(truncated.consumed, 0);
}

void ProtocolAdapterTest::decodeRejectsOversizedPacket()
{
    QByteArray buffer;
    const quint32 oversized = client::kMaxMessageLen + 1;
    buffer.append(static_cast<char>((oversized >> 24) & 0xFF));
    buffer.append(static_cast<char>((oversized >> 16) & 0xFF));
    buffer.append(static_cast<char>((oversized >> 8) & 0xFF));
    buffer.append(static_cast<char>(oversized & 0xFF));
    buffer.append(QByteArray(8, 'x'));

    const auto decoded = client::decodePacket(buffer);
    QCOMPARE(decoded.error.kind, client::ProtocolErrorKind::DeclaredLengthTooLarge);
    QCOMPARE(decoded.consumed, 0);
}

void ProtocolAdapterTest::decodeRejectsInvalidJson()
{
    QByteArray buffer;
    const QByteArray body = "{\"method\":\"health\", broken";
    const quint32 length = static_cast<quint32>(body.size());
    buffer.append(static_cast<char>((length >> 24) & 0xFF));
    buffer.append(static_cast<char>((length >> 16) & 0xFF));
    buffer.append(static_cast<char>((length >> 8) & 0xFF));
    buffer.append(static_cast<char>(length & 0xFF));
    buffer.append(body);

    const auto decoded = client::decodePacket(buffer);
    QCOMPARE(decoded.error.kind, client::ProtocolErrorKind::InvalidJson);
    QCOMPARE(decoded.consumed, 0);
}

void ProtocolAdapterTest::decodeRejectsNonObjectJson()
{
    QByteArray buffer;
    const QByteArray body = "[1, 2, 3]";
    const quint32 length = static_cast<quint32>(body.size());
    buffer.append(static_cast<char>((length >> 24) & 0xFF));
    buffer.append(static_cast<char>((length >> 16) & 0xFF));
    buffer.append(static_cast<char>((length >> 8) & 0xFF));
    buffer.append(static_cast<char>(length & 0xFF));
    buffer.append(body);

    const auto decoded = client::decodePacket(buffer);
    QCOMPARE(decoded.error.kind, client::ProtocolErrorKind::EnvelopeNotObject);
}

void ProtocolAdapterTest::decodeConsumesMultiplePacketsInOneBuffer()
{
    const auto p1 = client::encodeEnvelope(client::buildEnvelope(
        client::methods::kHealth, QJsonObject{}, QStringLiteral("req-1")));
    const auto p2 = client::encodeEnvelope(client::buildEnvelope(
        client::methods::kMemoryRetrieve, QJsonObject{}, QStringLiteral("req-2")));
    QVERIFY(p1.has_value());
    QVERIFY(p2.has_value());

    QByteArray buffer;
    buffer.append(*p1);
    buffer.append(*p2);

    auto decoded = client::decodePacket(buffer);
    QVERIFY(decoded.error.ok());
    QVERIFY(decoded.envelope.has_value());
    QCOMPARE(decoded.consumed, p1->size());
    buffer = buffer.mid(decoded.consumed);

    decoded = client::decodePacket(buffer);
    QVERIFY(decoded.error.ok());
    QVERIFY(decoded.envelope.has_value());
    QCOMPARE(decoded.consumed, p2->size());
}

void ProtocolAdapterTest::buildEnvelopeOmitsEmptyOptionalFields()
{
    const QJsonObject envelope = client::buildEnvelope(
        client::methods::kHealth, QJsonObject{});

    QVERIFY(!envelope.contains(client::kRequestIdKey));
    QVERIFY(!envelope.contains(client::kTraceIdKey));
    QVERIFY(!envelope.contains(client::kDeadlineMsKey));
    QCOMPARE(envelope.value(client::kProtocolVersionKey).toString(),
             QStringLiteral("1.0"));
    QCOMPARE(envelope.value(client::kMethodKey).toString(),
             client::methods::kHealth);
    QVERIFY(envelope.value(client::kPayloadKey).isObject());
}

void ProtocolAdapterTest::buildEnvelopeIncludesOptionalFieldsWhenProvided()
{
    const QJsonObject envelope = client::buildEnvelope(
        client::methods::kMemoryRetrieve,
        QJsonObject{{QStringLiteral("k"), 1}},
        QStringLiteral("req-1"),
        QStringLiteral("trc-1"),
        2500);

    QCOMPARE(envelope.value(client::kRequestIdKey).toString(), QStringLiteral("req-1"));
    QCOMPARE(envelope.value(client::kTraceIdKey).toString(), QStringLiteral("trc-1"));
    QCOMPARE(envelope.value(client::kDeadlineMsKey).toInt(), 2500);
}

void ProtocolAdapterTest::parseEnvelopeAcceptsValidWithOptionalFields()
{
    QJsonObject envelope = client::buildEnvelope(
        client::methods::kHealth,
        QJsonObject{{QStringLiteral("ok"), true}},
        QStringLiteral("req-1"),
        QStringLiteral("trc-1"),
        1500);

    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(err.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->method, client::methods::kHealth);
    QCOMPARE(parts->requestId, QStringLiteral("req-1"));
    QCOMPARE(parts->traceId, QStringLiteral("trc-1"));
    QVERIFY(parts->deadlineMs.has_value());
    QCOMPARE(*parts->deadlineMs, 1500);
    QCOMPARE(parts->payload.value(QStringLiteral("ok")).toBool(), true);
}

void ProtocolAdapterTest::parseEnvelopeRejectsMissingProtocolVersion()
{
    QJsonObject envelope{
        {client::kMethodKey, client::methods::kHealth},
        {client::kPayloadKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingProtocolVersion);
    QVERIFY(!parts.has_value());
}

void ProtocolAdapterTest::parseEnvelopeRejectsUnsupportedProtocolVersion_data()
{
    QTest::addColumn<QString>("version");

    QTest::newRow("major-2") << QStringLiteral("2.0");
    QTest::newRow("major-0") << QStringLiteral("0.9");
    QTest::newRow("non-numeric") << QStringLiteral("v1");
    QTest::newRow("empty") << QStringLiteral("");
}

void ProtocolAdapterTest::parseEnvelopeRejectsUnsupportedProtocolVersion()
{
    QFETCH(QString, version);
    QJsonObject envelope{
        {client::kProtocolVersionKey, version},
        {client::kMethodKey, client::methods::kHealth},
        {client::kPayloadKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::UnsupportedProtocolVersion);
    QVERIFY(!parts.has_value());
}

void ProtocolAdapterTest::parseEnvelopeRejectsNonStringProtocolVersion()
{
    QJsonObject envelope{
        {client::kProtocolVersionKey, 1},
        {client::kMethodKey, client::methods::kHealth},
        {client::kPayloadKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::UnsupportedProtocolVersion);
    QVERIFY(!parts.has_value());
}

void ProtocolAdapterTest::parseEnvelopeRejectsMissingMethod()
{
    QJsonObject envelope{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kPayloadKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingOrInvalidMethod);
    QVERIFY(!parts.has_value());
}

void ProtocolAdapterTest::parseEnvelopeRejectsNonStringMethod()
{
    QJsonObject envelope{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kMethodKey, 42},
        {client::kPayloadKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingOrInvalidMethod);
}

void ProtocolAdapterTest::parseEnvelopeRejectsEmptyMethod()
{
    QJsonObject envelope{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kMethodKey, QString{}},
        {client::kPayloadKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingOrInvalidMethod);
}

void ProtocolAdapterTest::parseEnvelopeRejectsNonObjectPayload()
{
    QJsonObject envelope{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kMethodKey, client::methods::kHealth},
        {client::kPayloadKey, QStringLiteral("not-an-object")},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::PayloadNotObject);
}

void ProtocolAdapterTest::parseEnvelopeReadsOptionalFields()
{
    QJsonObject envelope{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kMethodKey, client::methods::kHealth},
        {client::kPayloadKey, QJsonObject{}},
        {client::kRequestIdKey, QStringLiteral("req-only")},
    };
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(err.ok());
    QCOMPARE(parts->requestId, QStringLiteral("req-only"));
    QVERIFY(parts->traceId.isEmpty());
    QVERIFY(!parts->deadlineMs.has_value());
}

// ── parseResponse 测试（FRZ-IPC-006 §6.2）──────────────────────────────────

void ProtocolAdapterTest::parseResponseAcceptsValidOk()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-001")},
        {client::kTraceIdKey, QStringLiteral("trc-001")},
        {client::kStatusKey, QStringLiteral("ok")},
        {client::kDataKey, QJsonObject{{QStringLiteral("status"), QStringLiteral("healthy")}}},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:00:00Z")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(err.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->status, QStringLiteral("ok"));
    QCOMPARE(parts->requestId, QStringLiteral("req-001"));
    QCOMPARE(parts->traceId, QStringLiteral("trc-001"));
    QCOMPARE(parts->serverTs, QStringLiteral("2026-08-20T12:00:00Z"));
    QCOMPARE(parts->data.value(QStringLiteral("status")).toString(), QStringLiteral("healthy"));
    QVERIFY(parts->errorCode.isEmpty());
    QVERIFY(parts->message.isEmpty());
}

void ProtocolAdapterTest::parseResponseAcceptsValidError()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-002")},
        {client::kTraceIdKey, QStringLiteral("trc-002")},
        {client::kStatusKey, QStringLiteral("error")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:01:00Z")},
        {client::kErrorCodeKey, QStringLiteral("UNSUPPORTED_METHOD")},
        {client::kMessageKey, QStringLiteral("Method not supported")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(err.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->status, QStringLiteral("error"));
    QCOMPARE(parts->errorCode, QStringLiteral("UNSUPPORTED_METHOD"));
    QCOMPARE(parts->message, QStringLiteral("Method not supported"));
}

void ProtocolAdapterTest::parseResponseRejectsMissingStatus()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-003")},
        {client::kTraceIdKey, QStringLiteral("trc-003")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:02:00Z")},
        {client::kDataKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingStatus);
}

void ProtocolAdapterTest::parseResponseRejectsInvalidStatus()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-004")},
        {client::kTraceIdKey, QStringLiteral("trc-004")},
        {client::kStatusKey, QStringLiteral("warning")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:03:00Z")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::InvalidStatus);
}

void ProtocolAdapterTest::parseResponseRejectsMissingRequestId()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kTraceIdKey, QStringLiteral("trc-005")},
        {client::kStatusKey, QStringLiteral("ok")},
        {client::kDataKey, QJsonObject{}},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:04:00Z")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingRequestId);
}

void ProtocolAdapterTest::parseResponseRejectsMissingTraceId()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-006")},
        {client::kStatusKey, QStringLiteral("ok")},
        {client::kDataKey, QJsonObject{}},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:05:00Z")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingTraceId);
}

void ProtocolAdapterTest::parseResponseRejectsMissingServerTs()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-007")},
        {client::kTraceIdKey, QStringLiteral("trc-007")},
        {client::kStatusKey, QStringLiteral("ok")},
        {client::kDataKey, QJsonObject{}},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingServerTs);
}

void ProtocolAdapterTest::parseResponseRejectsOkWithoutData()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-008")},
        {client::kTraceIdKey, QStringLiteral("trc-008")},
        {client::kStatusKey, QStringLiteral("ok")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:06:00Z")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingData);
}

void ProtocolAdapterTest::parseResponseRejectsMissingProtocolVersion()
{
    QJsonObject response{
        {client::kRequestIdKey, QStringLiteral("req-009")},
        {client::kTraceIdKey, QStringLiteral("trc-009")},
        {client::kStatusKey, QStringLiteral("ok")},
        {client::kDataKey, QJsonObject{}},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:07:00Z")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingProtocolVersion);
}

// ── error response 校验测试（MEDIUM-01）───────────────────────────────

void ProtocolAdapterTest::parseResponseRejectsErrorWithoutErrorCode()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-err-1")},
        {client::kTraceIdKey, QStringLiteral("trc-err-1")},
        {client::kStatusKey, QStringLiteral("error")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:10:00Z")},
        {client::kMessageKey, QStringLiteral("Something went wrong")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingErrorCode);
}

void ProtocolAdapterTest::parseResponseRejectsErrorWithoutMessage()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-err-2")},
        {client::kTraceIdKey, QStringLiteral("trc-err-2")},
        {client::kStatusKey, QStringLiteral("error")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:11:00Z")},
        {client::kErrorCodeKey, QStringLiteral("INTERNAL_ERROR")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingErrorMessage);
}

void ProtocolAdapterTest::parseResponseRejectsErrorWithNonStringErrorCode()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-err-3")},
        {client::kTraceIdKey, QStringLiteral("trc-err-3")},
        {client::kStatusKey, QStringLiteral("error")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:12:00Z")},
        {client::kErrorCodeKey, 42},
        {client::kMessageKey, QStringLiteral("Bad")},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingErrorCode);
}

void ProtocolAdapterTest::parseResponseRejectsErrorWithNonStringMessage()
{
    QJsonObject response{
        {client::kProtocolVersionKey, QStringLiteral("1.0")},
        {client::kRequestIdKey, QStringLiteral("req-err-4")},
        {client::kTraceIdKey, QStringLiteral("trc-err-4")},
        {client::kStatusKey, QStringLiteral("error")},
        {client::kServerTsKey, QStringLiteral("2026-08-20T12:13:00Z")},
        {client::kErrorCodeKey, QStringLiteral("TIMEOUT")},
        {client::kMessageKey, 42},
    };
    const auto [parts, err] = client::parseResponse(response);
    QVERIFY(!err.ok());
    QCOMPARE(err.kind, client::ProtocolErrorKind::MissingErrorMessage);
}

// ── uint32 高位长度头边界测试（HIGH-03）───────────────────────────────

void ProtocolAdapterTest::decodeRejectsHighBitSetLength()
{
    // 0x80000000 — 高位为 1，声明长度 2147483648，远超 64KB 上限。
    // 旧代码用 qint32 会解析为 -2147483648，误判为 IncompletePacket。
    QByteArray packet;
    packet.append(static_cast<char>(0x80));
    packet.append(static_cast<char>(0x00));
    packet.append(static_cast<char>(0x00));
    packet.append(static_cast<char>(0x00));
    packet.append("{}");  // body（不会被读取，但确保缓冲区有数据）
    const auto result = client::decodePacket(packet);
    QCOMPARE(result.error.kind, client::ProtocolErrorKind::DeclaredLengthTooLarge);
}

void ProtocolAdapterTest::decodeRejectsMaxUint32Length()
{
    // 0xFFFFFFFF — 最大 uint32，声明长度 4294967295。
    QByteArray packet;
    packet.append(static_cast<char>(0xFF));
    packet.append(static_cast<char>(0xFF));
    packet.append(static_cast<char>(0xFF));
    packet.append(static_cast<char>(0xFF));
    packet.append("{}");
    const auto result = client::decodePacket(packet);
    QCOMPARE(result.error.kind, client::ProtocolErrorKind::DeclaredLengthTooLarge);
}

void ProtocolAdapterTest::decodeRejectsJustOverLimit()
{
    // 0x00010001 = 65537，刚好超过 kMaxMessageLen=65536 一个字节。
    QByteArray packet;
    packet.append(static_cast<char>(0x00));
    packet.append(static_cast<char>(0x01));
    packet.append(static_cast<char>(0x00));
    packet.append(static_cast<char>(0x01));
    packet.append("{}");
    const auto result = client::decodePacket(packet);
    QCOMPARE(result.error.kind, client::ProtocolErrorKind::DeclaredLengthTooLarge);
}

// HIGH-01: isValidErrorCode 接入生产 parseResponse — 未知 error_code 被 reject
void ProtocolAdapterTest::parseResponseRejectsUnknownErrorCode()
{
    QJsonObject response = client::buildErrorResponse(
        QStringLiteral("req-001"),
        QStringLiteral("req-001"),
        QStringLiteral("UNKNOWN_CODE"),
        QStringLiteral("some message"),
        QStringLiteral("2026-08-24T12:00:00Z"));
    const auto [parts, error] = client::parseResponse(response);
    QCOMPARE(error.kind, client::ProtocolErrorKind::InvalidErrorCode);
    QVERIFY(!parts.has_value());
}

// HIGH-01: 冻结 5 项 error_code 全部通过
void ProtocolAdapterTest::parseResponseAcceptsAllFrozenErrorCodes()
{
    const QStringList codes = {
        client::error_codes::kUnsupportedMethod,
        client::error_codes::kInvalidRequest,
        client::error_codes::kProtocolError,
        client::error_codes::kInternalError,
        client::error_codes::kTimeout,
    };
    for (const QString& code : codes) {
        QJsonObject response = client::buildErrorResponse(
            QStringLiteral("req-001"),
            QStringLiteral("req-001"),
            code,
            QStringLiteral("error detail"),
            QStringLiteral("2026-08-24T12:00:00Z"));
        const auto [parts, error] = client::parseResponse(response);
        QVERIFY2(error.ok(), qPrintable(QStringLiteral("Failed for code: ") + code));
        QVERIFY(parts.has_value());
        QCOMPARE(parts->errorCode, code);
    }
}

// MEDIUM-01: server_ts 非法 ISO 8601 UTC 被 reject
void ProtocolAdapterTest::parseResponseRejectsInvalidServerTs()
{
    QJsonObject response = client::buildSuccessResponse(
        QStringLiteral("req-001"),
        QStringLiteral("req-001"),
        QJsonObject{},
        QStringLiteral("abc"));
    const auto [parts, error] = client::parseResponse(response);
    QCOMPARE(error.kind, client::ProtocolErrorKind::InvalidServerTs);
    QVERIFY(!parts.has_value());
}

// MEDIUM-01: server_ts 空字符串被 reject
void ProtocolAdapterTest::parseResponseRejectsEmptyServerTs()
{
    QJsonObject response = client::buildSuccessResponse(
        QStringLiteral("req-001"),
        QStringLiteral("req-001"),
        QJsonObject{},
        QStringLiteral(""));
    const auto [parts, error] = client::parseResponse(response);
    QCOMPARE(error.kind, client::ProtocolErrorKind::InvalidServerTs);
    QVERIFY(!parts.has_value());
}

// MEDIUM-01: server_ts 仅日期（无时间部分）被 reject
void ProtocolAdapterTest::parseResponseRejectsDateOnlyServerTs()
{
    QJsonObject response = client::buildSuccessResponse(
        QStringLiteral("req-001"),
        QStringLiteral("req-001"),
        QJsonObject{},
        QStringLiteral("2026-08-24"));
    const auto [parts, error] = client::parseResponse(response);
    QCOMPARE(error.kind, client::ProtocolErrorKind::InvalidServerTs);
    QVERIFY(!parts.has_value());
}

QTEST_APPLESS_MAIN(ProtocolAdapterTest)

#include "test_protocol_adapter.moc"
