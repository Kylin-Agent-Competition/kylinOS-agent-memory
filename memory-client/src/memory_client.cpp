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

// FRZ-IPC-006 §6.1: 请求中 request_id/trace_id/deadline_ms 为必填字段。
// sendRequest 始终填充这三个字段；默认超时 5000ms（延迟预算参考值）。
constexpr int kDefaultDeadlineMs = 5000;

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
    case ProtocolErrorKind::MissingStatus:
        return QStringLiteral("ERR_MISSING_STATUS");
    case ProtocolErrorKind::InvalidStatus:
        return QStringLiteral("ERR_INVALID_STATUS");
    case ProtocolErrorKind::MissingRequestId:
        return QStringLiteral("ERR_MISSING_REQUEST_ID");
    case ProtocolErrorKind::MissingTraceId:
        return QStringLiteral("ERR_MISSING_TRACE_ID");
    case ProtocolErrorKind::MissingData:
        return QStringLiteral("ERR_MISSING_DATA");
    case ProtocolErrorKind::MissingServerTs:
        return QStringLiteral("ERR_MISSING_SERVER_TS");
    case ProtocolErrorKind::MissingErrorCode:
        return QStringLiteral("ERR_MISSING_ERROR_CODE");
    case ProtocolErrorKind::MissingErrorMessage:
        return QStringLiteral("ERR_MISSING_ERROR_MESSAGE");
    case ProtocolErrorKind::InvalidErrorCode:
        return QStringLiteral("ERR_INVALID_ERROR_CODE");
    case ProtocolErrorKind::InvalidServerTs:
        return QStringLiteral("ERR_INVALID_SERVER_TS");
    case ProtocolErrorKind::MissingDeadlineMs:
        return QStringLiteral("ERR_MISSING_DEADLINE_MS");
    case ProtocolErrorKind::InvalidDeadlineMs:
        return QStringLiteral("ERR_INVALID_DEADLINE_MS");
    }
    return QStringLiteral("ERR_UNKNOWN");
}

}  // namespace

MemoryClient::MemoryClient(QObject* parent)
    : QObject(parent)
{
    // FRZ-IPC-005 / ALIGN-005: 默认 UDS 路径 $XDG_RUNTIME_DIR/kylin-memory/memory.sock
    const QByteArray xdgRuntime = qgetenv("XDG_RUNTIME_DIR");
    if (!xdgRuntime.isEmpty()) {
        socketPath_ = QString::fromUtf8(xdgRuntime)
                      + QStringLiteral("/kylin-memory/memory.sock");
    }

    socket_ = new QLocalSocket(this);
    connect(socket_, &QLocalSocket::connected, this, &MemoryClient::handleSocketConnected);
    connect(socket_, &QLocalSocket::disconnected, this, &MemoryClient::handleSocketDisconnected);
    // 使用字符串 SIGNAL/SLOT 语法避免 Qt 5.15 中 QIODevice::errorOccurred 与
    // QLocalSocket::errorOccurred 的重载解析歧义（两者参数枚举类型不同）。
    connect(socket_, SIGNAL(errorOccurred(QLocalSocket::LocalSocketError)),
            this, SLOT(handleSocketErrorOccurred(QLocalSocket::LocalSocketError)));
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
    // FRZ-IPC-006 §6.1: request_id/trace_id/deadline_ms 为必填字段。
    // trace_id 复用 request_id（单客户端场景下两者相同不影响链路追踪）。
    const QJsonObject envelope = buildEnvelope(
        method, payload, requestId, requestId, kDefaultDeadlineMs);
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
    return sendRequest(methods::kHealth, QJsonObject{});
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
            // FRZ-IPC-006 §6.2: 使用 parseResponse 严格校验响应结构。
            const auto [responseParts, parseError] = parseResponse(*decoded.envelope);
            if (!parseError.ok() || !responseParts.has_value()) {
                // 非法响应：不上抛给上层，报 connectionError 并断连。
                setLastError(parseError.safeMessage);
                emit connectionError(parseError.safeMessage);
                receiveBuffer_.clear();
                socket_->abort();
                setConnectionState(ConnectionState::Disconnected);
                failInFlightRequests(kErrProtocol, parseError.safeMessage);
                return;
            }

            const QString& requestId = responseParts->requestId;

            // pending request 门禁：未知 request_id 不作为正常响应上抛。
            auto it = pendingRequests_.find(requestId.toStdString());
            if (it == pendingRequests_.end()) {
                // 未知/重复/迟到响应：丢弃，不转发。
                continue;
            }

            // trace_id 关联校验：客户端发送时 trace_id 复用 request_id，
            // 响应应回显相同的 trace_id。
            if (responseParts->traceId != requestId) {
                // trace_id 不匹配：可能是伪造响应，丢弃。
                pendingRequests_.erase(it);
                emit requestFailed(requestId, kErrProtocol,
                    QStringLiteral("Response trace_id mismatch."));
                continue;
            }

            pendingRequests_.erase(it);
            emit responseReceived(requestId, *decoded.envelope);
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
