#include "memory_client.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QUuid>

namespace kylin::memory::client::v1 {

namespace {

constexpr const char* kErrNotConnected = "ERR_NOT_CONNECTED";
constexpr const char* kErrEncodeFailed = "ERR_ENCODE_FAILED";
constexpr const char* kErrConnectionClosing = "ERR_CONNECTION_CLOSING";
constexpr const char* kErrProtocol = "ERR_PROTOCOL";

QString connectionStateToString(MemoryClient::ConnectionState state)
{
    switch (state) {
    case MemoryClient::ConnectionState::Disconnected:
        return QStringLiteral("disconnected");
    case MemoryClient::ConnectionState::Connecting:
        return QStringLiteral("connecting");
    case MemoryClient::ConnectionState::Connected:
        return QStringLiteral("connected");
    case MemoryClient::ConnectionState::Closing:
        return QStringLiteral("closing");
    }
    return QStringLiteral("unknown");
}

QString protocolErrorKindToString(ProtocolErrorKind kind)
{
    switch (kind) {
    case ProtocolErrorKind::None:
        return {};
    case ProtocolErrorKind::IncompletePacket:
        return QStringLiteral("ERR_INCOMPLETE");
    case ProtocolErrorKind::DeclaredLengthTooLarge:
        return QStringLiteral("ERR_OVERSIZED");
    case ProtocolErrorKind::InvalidUtf8:
        return QStringLiteral("ERR_INVALID_UTF8");
    case ProtocolErrorKind::InvalidJson:
        return QStringLiteral("ERR_INVALID_JSON");
    case ProtocolErrorKind::EnvelopeNotObject:
        return QStringLiteral("ERR_INVALID_ENVELOPE");
    case ProtocolErrorKind::MissingProtocolVersion:
        return QStringLiteral("ERR_MISSING_PROTOCOL_VERSION");
    case ProtocolErrorKind::UnsupportedProtocolVersion:
        return QStringLiteral("ERR_UNSUPPORTED_PROTOCOL_VERSION");
    case ProtocolErrorKind::MissingOrInvalidMethod:
        return QStringLiteral("ERR_INVALID_METHOD");
    case ProtocolErrorKind::PayloadNotObject:
        return QStringLiteral("ERR_INVALID_PAYLOAD");
    }
    return QStringLiteral("ERR_UNKNOWN");
}

}  // namespace

MemoryClient::MemoryClient(QObject* parent)
    : QObject(parent)
{
    socket_ = new QLocalSocket(this);
    connect(socket_, &QLocalSocket::connected, this, &MemoryClient::handleSocketConnected);
    connect(socket_, &QLocalSocket::disconnected, this, &MemoryClient::handleSocketDisconnected);
    connect(socket_, &QLocalSocket::errorOccurred, this, &MemoryClient::handleSocketErrorOccurred);
    connect(socket_, &QLocalSocket::readyRead, this, &MemoryClient::handleSocketReadyRead);
}

MemoryClient::~MemoryClient()
{
    if (socket_) {
        socket_->disconnect(this);
        socket_->abort();
    }
}

void MemoryClient::setSocketPath(const QString& path)
{
    if (socketPath_ == path) {
        return;
    }
    socketPath_ = path;
    emit socketPathChanged();
}

void MemoryClient::connectToService()
{
    if (connectionState_ == ConnectionState::Connected
        || connectionState_ == ConnectionState::Connecting) {
        return;
    }
    if (socketPath_.isEmpty()) {
        setLastError(QStringLiteral("Socket path is empty."));
        emit connectionError(QStringLiteral("Socket path is empty."));
        return;
    }
    receiveBuffer_.clear();
    setConnectionState(ConnectionState::Connecting);
    socket_->connectToServer(socketPath_);
}

void MemoryClient::disconnectFromService()
{
    if (connectionState_ == ConnectionState::Disconnected) {
        return;
    }
    setConnectionState(ConnectionState::Closing);
    failInFlightRequests(kErrConnectionClosing, QStringLiteral("Connection is closing."));
    socket_->disconnectFromServer();
}

QString MemoryClient::sendRequest(const QString& method, const QJsonObject& payload)
{
    if (connectionState_ != ConnectionState::Connected) {
        emit requestFailed({}, kErrNotConnected, QStringLiteral("Client is not connected."));
        return {};
    }
    if (method.isEmpty()) {
        emit requestFailed({}, kErrProtocol, QStringLiteral("Method must not be empty."));
        return {};
    }

    const QString requestId = generateRequestId();
    const QJsonObject envelope = buildEnvelope(method, payload, requestId);
    const auto packet = encodeEnvelope(envelope);
    if (!packet.has_value()) {
        emit requestFailed(requestId, kErrEncodeFailed,
                           QStringLiteral("Failed to encode request envelope."));
        return {};
    }

    const qint64 written = socket_->write(*packet);
    if (written != packet->size()) {
        emit requestFailed(requestId, kErrEncodeFailed,
                           QStringLiteral("Failed to write request to socket."));
        return {};
    }
    socket_->flush();

    pendingRequests_.emplace(requestId.toStdString(), method);
    return requestId;
}

QString MemoryClient::sendHealthRequest()
{
    return sendRequest(methods::kMemoryHealth, QJsonObject{});
}

void MemoryClient::handleSocketConnected()
{
    setConnectionState(ConnectionState::Connected);
    setLastError({});
}

void MemoryClient::handleSocketDisconnected()
{
    setConnectionState(ConnectionState::Disconnected);
    failInFlightRequests(kErrConnectionClosing, QStringLiteral("Connection closed by peer."));
}

void MemoryClient::handleSocketErrorOccurred(QLocalSocket::LocalSocketError error)
{
    // QLocalSocket::UnknownSocketError 是通用错误；使用 tr() 风格的固定安全消息，
    // 不暴露文件路径或凭据。
    Q_UNUSED(error)
    const QString safeMessage = QStringLiteral("Local socket error occurred.");
    setLastError(safeMessage);
    if (connectionState_ == ConnectionState::Connecting) {
        setConnectionState(ConnectionState::Disconnected);
    }
    emit connectionError(safeMessage);
}

void MemoryClient::handleSocketReadyRead()
{
    receiveBuffer_.append(socket_->readAll());

    while (true) {
        DecodeResult decoded = decodePacket(receiveBuffer_);
        if (decoded.error.kind == ProtocolErrorKind::IncompletePacket) {
            // 等待更多数据。
            return;
        }
        if (!decoded.error.ok()) {
            setLastError(decoded.error.safeMessage);
            emit connectionError(decoded.error.safeMessage);
            // 不可恢复的协议错误：关闭连接以避免半包污染后续请求。
            receiveBuffer_.clear();
            socket_->abort();
            setConnectionState(ConnectionState::Disconnected);
            failInFlightRequests(kErrProtocol, decoded.error.safeMessage);
            return;
        }

        receiveBuffer_ = receiveBuffer_.mid(decoded.consumed);

        if (decoded.envelope.has_value()) {
            // envelope 校验：必须包含 protocol_version 与 method（不强制
            // request_id，以容忍服务端在出错时不回传）。
            const auto [parts, parseError] = parseEnvelope(*decoded.envelope);
            if (!parseError.ok()) {
                emit connectionError(parseError.safeMessage);
                continue;
            }
            const QString requestId = parts.requestId;
            if (pendingRequests_.erase(requestId.toStdString()) == 0) {
                // 未知 request_id：仍转发响应，便于上层诊断；不暴露原文。
                emit responseReceived(requestId, *decoded.envelope);
            } else {
                emit responseReceived(requestId, *decoded.envelope);
            }
        }
    }
}

void MemoryClient::setConnectionState(ConnectionState state)
{
    if (connectionState_ == state) {
        return;
    }
    connectionState_ = state;
    emit connectionStateChanged();
}

void MemoryClient::setLastError(const QString& message)
{
    if (lastError_ == message) {
        return;
    }
    lastError_ = message;
    emit lastErrorChanged();
}

void MemoryClient::failInFlightRequests(const QString& errorCode, const QString& safeMessage)
{
    if (pendingRequests_.empty()) {
        return;
    }
    for (const auto& [id, _] : pendingRequests_) {
        emit requestFailed(QString::fromStdString(id), errorCode, safeMessage);
    }
    pendingRequests_.clear();
}

QString MemoryClient::generateRequestId() const
{
    return QStringLiteral("req_%1").arg(
        QUuid::createUuid().toString(QUuid::WithoutBraces));
}

}  // namespace kylin::memory::client::v1
