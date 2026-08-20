#include "protocol_adapter.h"

#include <QDataStream>
#include <QJsonDocument>
#include <QJsonValue>

#include <climits>

namespace kylin::memory::client::v1 {

const QString kProtocolVersionQString = QStringLiteral("1.0");
const QString kMethodKey = QStringLiteral("method");
const QString kPayloadKey = QStringLiteral("payload");
const QString kProtocolVersionKey = QStringLiteral("protocol_version");
const QString kRequestIdKey = QStringLiteral("request_id");
const QString kTraceIdKey = QStringLiteral("trace_id");
const QString kDeadlineMsKey = QStringLiteral("deadline_ms");
const QString kIdempotencyKeyKey = QStringLiteral("idempotency_key");
// 响应字段名（FRZ-IPC-006 §6.2）
const QString kStatusKey = QStringLiteral("status");
const QString kDataKey = QStringLiteral("data");
const QString kServerTsKey = QStringLiteral("server_ts");
const QString kErrorCodeKey = QStringLiteral("error_code");
const QString kMessageKey = QStringLiteral("message");

// D 冻结方法路由表（FRZ-IPC-007）
namespace methods {
const QString kEcho = QStringLiteral("echo");
const QString kHealth = QStringLiteral("health");
const QString kMemoryRetrieve = QStringLiteral("memory.retrieve");
const QString kMemoryStore = QStringLiteral("memory.store");
const QString kEvidenceRecord = QStringLiteral("evidence.record");
}  // namespace methods

// D 冻结服务端错误码枚举（FRZ-IPC-002，5 项）
namespace error_codes {
const QString kUnsupportedMethod = QStringLiteral("UNSUPPORTED_METHOD");
const QString kInvalidRequest = QStringLiteral("INVALID_REQUEST");
const QString kProtocolError = QStringLiteral("PROTOCOL_ERROR");
const QString kInternalError = QStringLiteral("INTERNAL_ERROR");
const QString kTimeout = QStringLiteral("TIMEOUT");
}  // namespace error_codes

namespace {

ProtocolError makeError(ProtocolErrorKind kind, const QString& message)
{
    return {kind, message};
}

ProtocolError errorFromKind(ProtocolErrorKind kind)
{
    switch (kind) {
    case ProtocolErrorKind::None:
        return {ProtocolErrorKind::None, {}};
    case ProtocolErrorKind::IncompletePacket:
        return makeError(kind, QStringLiteral("Incomplete packet; more bytes expected."));
    case ProtocolErrorKind::DeclaredLengthTooLarge:
        return makeError(kind, QStringLiteral("Declared length exceeds the protocol limit."));
    case ProtocolErrorKind::InvalidUtf8:
        return makeError(kind, QStringLiteral("Payload is not valid UTF-8."));
    case ProtocolErrorKind::InvalidJson:
        return makeError(kind, QStringLiteral("Payload is not valid JSON."));
    case ProtocolErrorKind::EnvelopeNotObject:
        return makeError(kind, QStringLiteral("Envelope root must be a JSON object."));
    case ProtocolErrorKind::MissingProtocolVersion:
        return makeError(kind, QStringLiteral("Envelope is missing protocol_version."));
    case ProtocolErrorKind::UnsupportedProtocolVersion:
        return makeError(kind, QStringLiteral("Unsupported protocol_version value."));
    case ProtocolErrorKind::MissingOrInvalidMethod:
        return makeError(kind, QStringLiteral("Envelope method is missing or invalid."));
    case ProtocolErrorKind::PayloadNotObject:
        return makeError(kind, QStringLiteral("Envelope payload must be a JSON object."));
    case ProtocolErrorKind::MissingStatus:
        return makeError(kind, QStringLiteral("Response is missing status field."));
    case ProtocolErrorKind::InvalidStatus:
        return makeError(kind, QStringLiteral("Response status must be 'ok' or 'error'."));
    case ProtocolErrorKind::MissingServerTs:
        return makeError(kind, QStringLiteral("Response is missing server_ts field."));
    }
    return {ProtocolErrorKind::None, {}};
}

// 读取 4 字节大端长度前缀。返回 -1 表示缓冲不足。
qint32 readHeader(const QByteArray& buffer)
{
    if (buffer.size() < kHeaderLen) {
        return -1;
    }
    return static_cast<qint32>(
        (static_cast<unsigned char>(buffer[0]) << 24)
        | (static_cast<unsigned char>(buffer[1]) << 16)
        | (static_cast<unsigned char>(buffer[2]) << 8)
        | static_cast<unsigned char>(buffer[3]));
}

}  // namespace

std::optional<QByteArray> encodeEnvelope(const QJsonObject& envelope)
{
    const QJsonDocument document(envelope);
    const QByteArray body = document.toJson(QJsonDocument::Compact);
    if (body.size() > kMaxMessageLen) {
        return std::nullopt;
    }

    QByteArray packet;
    packet.reserve(kHeaderLen + body.size());
    const quint32 length = static_cast<quint32>(body.size());
    packet.append(static_cast<char>((length >> 24) & 0xFF));
    packet.append(static_cast<char>((length >> 16) & 0xFF));
    packet.append(static_cast<char>((length >> 8) & 0xFF));
    packet.append(static_cast<char>(length & 0xFF));
    packet.append(body);
    return packet;
}

DecodeResult decodePacket(const QByteArray& buffer)
{
    DecodeResult result;
    const qint32 declared = readHeader(buffer);
    if (declared < 0) {
        result.error = errorFromKind(ProtocolErrorKind::IncompletePacket);
        return result;
    }

    if (declared > kMaxMessageLen) {
        result.error = errorFromKind(ProtocolErrorKind::DeclaredLengthTooLarge);
        return result;
    }

    if (buffer.size() < kHeaderLen + declared) {
        result.error = errorFromKind(ProtocolErrorKind::IncompletePacket);
        return result;
    }

    const QByteArray body = buffer.mid(kHeaderLen, declared);
    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(body, &parseError);
    if (parseError.error != QJsonParseError::NoError) {
        result.error = errorFromKind(ProtocolErrorKind::InvalidJson);
        return result;
    }
    if (!document.isObject()) {
        result.error = errorFromKind(ProtocolErrorKind::EnvelopeNotObject);
        return result;
    }

    result.envelope = document.object();
    result.consumed = kHeaderLen + declared;
    return result;
}

QJsonObject buildEnvelope(
    const QString& method,
    const QJsonObject& payload,
    const QString& requestId,
    const QString& traceId,
    std::optional<int> deadlineMs)
{
    QJsonObject envelope{
        {kProtocolVersionKey, kProtocolVersionQString},
        {kMethodKey, method},
        {kPayloadKey, payload.isEmpty() ? QJsonObject{} : payload},
    };
    if (!requestId.isEmpty()) {
        envelope.insert(kRequestIdKey, requestId);
    }
    if (!traceId.isEmpty()) {
        envelope.insert(kTraceIdKey, traceId);
    }
    if (deadlineMs.has_value()) {
        envelope.insert(kDeadlineMsKey, *deadlineMs);
    }
    return envelope;
}

std::pair<std::optional<EnvelopeParts>, ProtocolError> parseEnvelope(
    const QJsonObject& envelope)
{
    EnvelopeParts parts;

    const QJsonValue versionValue = envelope.value(kProtocolVersionKey);
    if (versionValue.isUndefined() || versionValue.isNull()) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::MissingProtocolVersion)};
    }
    if (!versionValue.isString()) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::UnsupportedProtocolVersion)};
    }
    const QString version = versionValue.toString();
    if (version != kProtocolVersionQString) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::UnsupportedProtocolVersion)};
    }

    const QJsonValue methodValue = envelope.value(kMethodKey);
    if (!methodValue.isString() || methodValue.toString().isEmpty()) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::MissingOrInvalidMethod)};
    }
    parts.method = methodValue.toString();

    const QJsonValue payloadValue = envelope.value(kPayloadKey);
    if (payloadValue.isUndefined() || payloadValue.isNull()) {
        parts.payload = QJsonObject{};
    } else if (!payloadValue.isObject()) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::PayloadNotObject)};
    } else {
        parts.payload = payloadValue.toObject();
    }

    const QJsonValue requestIdValue = envelope.value(kRequestIdKey);
    if (requestIdValue.isString()) {
        parts.requestId = requestIdValue.toString();
    }

    const QJsonValue traceIdValue = envelope.value(kTraceIdKey);
    if (traceIdValue.isString()) {
        parts.traceId = traceIdValue.toString();
    }

    const QJsonValue deadlineValue = envelope.value(kDeadlineMsKey);
    if (deadlineValue.isDouble()) {
        const double raw = deadlineValue.toDouble();
        if (raw >= 0 && raw <= static_cast<double>(INT_MAX) && raw == static_cast<int>(raw)) {
            parts.deadlineMs = static_cast<int>(raw);
        }
    }

    return {parts, {}};
}

std::pair<std::optional<ResponseParts>, ProtocolError> parseResponse(
    const QJsonObject& envelope)
{
    // 先校验 protocol_version（与请求相同）。
    const QJsonValue versionValue = envelope.value(kProtocolVersionKey);
    if (versionValue.isUndefined() || versionValue.isNull()) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::MissingProtocolVersion)};
    }
    if (!versionValue.isString() || versionValue.toString() != kProtocolVersionQString) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::UnsupportedProtocolVersion)};
    }

    ResponseParts parts;

    // status（必填，"ok" 或 "error"）
    const QJsonValue statusValue = envelope.value(kStatusKey);
    if (statusValue.isUndefined() || statusValue.isNull() || !statusValue.isString()) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::MissingStatus)};
    }
    const QString status = statusValue.toString();
    if (status != QStringLiteral("ok") && status != QStringLiteral("error")) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::InvalidStatus)};
    }
    parts.status = status;

    // request_id（回显，字符串）
    const QJsonValue requestIdValue = envelope.value(kRequestIdKey);
    if (requestIdValue.isString()) {
        parts.requestId = requestIdValue.toString();
    }

    // trace_id（回显，字符串）
    const QJsonValue traceIdValue = envelope.value(kTraceIdKey);
    if (traceIdValue.isString()) {
        parts.traceId = traceIdValue.toString();
    }

    // server_ts（必填，ISO 8601 UTC 字符串）
    const QJsonValue serverTsValue = envelope.value(kServerTsKey);
    if (serverTsValue.isUndefined() || serverTsValue.isNull() || !serverTsValue.isString()) {
        return {std::nullopt, errorFromKind(ProtocolErrorKind::MissingServerTs)};
    }
    parts.serverTs = serverTsValue.toString();

    // data（成功时必填，对象）
    const QJsonValue dataValue = envelope.value(kDataKey);
    if (dataValue.isObject()) {
        parts.data = dataValue.toObject();
    }

    // 错误时额外字段
    if (status == QStringLiteral("error")) {
        const QJsonValue errorCodeValue = envelope.value(kErrorCodeKey);
        if (errorCodeValue.isString()) {
            parts.errorCode = errorCodeValue.toString();
        }
        const QJsonValue messageValue = envelope.value(kMessageKey);
        if (messageValue.isString()) {
            parts.message = messageValue.toString();
        }
    }

    return {parts, {}};
}

}  // namespace kylin::memory::client::v1
