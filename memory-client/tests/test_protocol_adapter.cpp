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

QTEST_APPLESS_MAIN(ProtocolAdapterTest)

#include "test_protocol_adapter.moc"
