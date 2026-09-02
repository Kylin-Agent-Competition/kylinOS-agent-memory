#include "memory_client.h"

#include <QDateTime>
#include <QJsonDocument>
#include <QJsonObject>
#include <QUuid>

namespace kylin::memory::client::v1 {

namespace {

constexpr const char* kErrNotConnected = "ERR_NOT_CONNECTED";
constexpr const char* kErrEncodeFailed = "ERR_ENCODE_FAILED";
constexpr const char* kErrConnectionClosing = "ERR_CONNECTION_CLOSING";
constexpr const char* kErrProtocol = "ERR_PROTOCOL";
constexpr const char* kErrClientTimeout = "TIMEOUT";  // TD-022：与服务端冻结错误码 TIMEOUT 对齐
constexpr const char* kErrReconnectMax = "ERR_RECONNECT_MAX";

// FRZ-IPC-006 §6.1: deadline_ms 必填；默认 5000ms（客户端侧）。
constexpr int kDefaultDeadlineMs = 5000;
// TD-022：客户端 deadline 追加 100ms 容差（网络/调度抖动）。
constexpr int kClientDeadlineGraceMs = 100;

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
    case MemoryClient::ConnectionState::Reconnecting:
        return QStringLiteral("reconnecting");
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

// ────────────────────────────────────────────────────────────────────────────
MemoryClient::MemoryClient(QObject* parent)
    : QObject(parent)
{
    const QByteArray xdgRuntime = qgetenv("XDG_RUNTIME_DIR");
    if (!xdgRuntime.isEmpty()) {
        socketPath_ = QString::fromUtf8(xdgRuntime)
                      + QStringLiteral("/kylin-memory/memory.sock");
    }

    socket_ = new QLocalSocket(this);
    reconnectTimer_ = new QTimer(this);
    reconnectTimer_->setSingleShot(true);
    connect(reconnectTimer_, &QTimer::timeout, this, [this]() {
        // TD-IPC-004：退避窗口结束，执行下一次重连尝试。
        if (connectionState_ != ConnectionState::Reconnecting) {
            return;
        }
        setConnectionState(ConnectionState::Connecting);
        receiveBuffer_.clear();
        socket_->connectToServer(socketPath_);
    });

    connect(socket_, &QLocalSocket::connected, this, &MemoryClient::handleSocketConnected);
    connect(socket_, &QLocalSocket::disconnected, this, &MemoryClient::handleSocketDisconnected);
    connect(socket_, SIGNAL(errorOccurred(QLocalSocket::LocalSocketError)),
            this, SLOT(handleSocketErrorOccurred(QLocalSocket::LocalSocketError)));
    connect(socket_, &QLocalSocket::readyRead, this, &MemoryClient::handleSocketReadyRead);
}

MemoryClient::~MemoryClient()
{
    cancelReconnectTimer();
    // 析构：清除所有客户端 deadline 计时器与 pending。
    for (auto& [id, timer] : clientDeadlineTimers_) {
        if (timer) {
            timer->stop();
            timer->deleteLater();
        }
    }
    clientDeadlineTimers_.clear();
    pendingRequests_.clear();

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

void MemoryClient::setAutoReconnectEnabled(bool enabled)
{
    if (autoReconnectEnabled_ == enabled) return;
    autoReconnectEnabled_ = enabled;
    emit autoReconnectEnabledChanged();
    if (!enabled) {
        cancelReconnectTimer();
    }
}

void MemoryClient::connectToService()
{
    if (connectionState_ == ConnectionState::Connected
        || connectionState_ == ConnectionState::Connecting
        || connectionState_ == ConnectionState::Reconnecting) {
        return;
    }
    if (socketPath_.isEmpty()) {
        setLastError(QStringLiteral("Socket path is empty."));
        emit connectionError(QStringLiteral("Socket path is empty."));
        return;
    }
    cancelReconnectTimer();
    manualDisconnectInProgress_ = false;
    reconnectAttempts_ = 0;  // 全新连接，重置重连计数
    receiveBuffer_.clear();
    setConnectionState(ConnectionState::Connecting);
    socket_->connectToServer(socketPath_);
}

void MemoryClient::disconnectFromService()
{
    if (connectionState_ == ConnectionState::Disconnected) {
        return;
    }
    // TD-IPC-004：显式 Stop → 取消重连、不触发自动重连。
    cancelReconnectTimer();
    manualDisconnectInProgress_ = true;
    setConnectionState(ConnectionState::Closing);
    failInFlightRequests(kErrConnectionClosing, QStringLiteral("Connection is closing."));
    socket_->disconnectFromServer();
}

void MemoryClient::retryConnect()
{
    // D12-C：显式 Retry。先 clean disconnect（不触发 auto-reconnect），再 connect。
    const bool oldAuto = autoReconnectEnabled_;
    autoReconnectEnabled_ = false;  // 临时禁用避免 disconnect 触发重连
    cancelReconnectTimer();
    manualDisconnectInProgress_ = true;
    if (socket_->state() != QLocalSocket::UnconnectedState) {
        socket_->abort();
    }
    failInFlightRequests(kErrConnectionClosing, QStringLiteral("Retry connect; in-flight requests cancelled."));
    setConnectionState(ConnectionState::Disconnected);
    autoReconnectEnabled_ = oldAuto;  // 恢复原值
    manualDisconnectInProgress_ = false;
    connectToService();
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

    // TD-022：注册 pending 并启动客户端 deadline 计时器（deadline_ms + grace）。
    PendingRequest pr;
    pr.method = method;
    pr.traceId = requestId;
    pr.deadlineEpochMs = QDateTime::currentMSecsSinceEpoch()
                         + static_cast<qint64>(kDefaultDeadlineMs) + kClientDeadlineGraceMs;
    pendingRequests_.emplace(requestId.toStdString(), pr);
    startClientDeadlineTimer(requestId, kDefaultDeadlineMs + kClientDeadlineGraceMs);
    return requestId;
}

QString MemoryClient::sendHealthRequest()
{
    return sendRequest(methods::kHealth, QJsonObject{});
}

QString MemoryClient::sendMemoryStoreRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kMemoryStore, payload);
}

QString MemoryClient::sendTurnFinalizedEvent(const QJsonObject& eventJson)
{
    if (connectionState_ != ConnectionState::Connected) {
        emit requestFailed({}, kErrNotConnected, QStringLiteral("Client is not connected."));
        return {};
    }

    const QString requestId = generateRequestId();

    QString traceId = requestId;
    const QJsonValue metadataValue = eventJson.value(QStringLiteral("metadata"));
    if (metadataValue.isObject()) {
        const QString metaTrace = metadataValue.toObject()
            .value(QStringLiteral("trace_id")).toString();
        if (!metaTrace.isEmpty()) {
            traceId = metaTrace;
        }
    }

    const QJsonObject envelope = buildEnvelope(
        methods::kTurnFinalized, eventJson, requestId, traceId, kDefaultDeadlineMs);
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

    PendingRequest pr;
    pr.method = methods::kTurnFinalized;
    pr.traceId = traceId;
    pr.deadlineEpochMs = QDateTime::currentMSecsSinceEpoch()
                         + static_cast<qint64>(kDefaultDeadlineMs) + kClientDeadlineGraceMs;
    pendingRequests_.emplace(requestId.toStdString(), pr);
    startClientDeadlineTimer(requestId, kDefaultDeadlineMs + kClientDeadlineGraceMs);
    return requestId;
}

QString MemoryClient::sendPreferenceListRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kPreferenceList, payload);
}
QString MemoryClient::sendPreferenceCreateRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kPreferenceCreate, payload);
}
QString MemoryClient::sendPreferenceUpdateRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kPreferenceUpdate, payload);
}
QString MemoryClient::sendPreferenceRollbackRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kPreferenceRollback, payload);
}
QString MemoryClient::sendPreferenceHistoryRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kPreferenceHistory, payload);
}

QString MemoryClient::sendToolExecutionEvent(const QJsonObject& eventJson)
{
    return sendEventEnvelope(methods::kToolExecution, eventJson);
}
QString MemoryClient::sendManualConfigEvent(const QJsonObject& eventJson)
{
    return sendEventEnvelope(methods::kManualConfigIngest, eventJson);
}
QString MemoryClient::sendBehaviorEvent(const QJsonObject& eventJson)
{
    return sendEventEnvelope(methods::kBehaviorObserve, eventJson);
}

QString MemoryClient::sendEventEnvelope(const QString& method, const QJsonObject& eventJson)
{
    if (connectionState_ != ConnectionState::Connected) {
        emit requestFailed({}, kErrNotConnected, QStringLiteral("Client is not connected."));
        return {};
    }

    const QString requestId = generateRequestId();
    QString traceId = requestId;
    const QJsonValue metadataValue = eventJson.value(QStringLiteral("metadata"));
    if (metadataValue.isObject()) {
        const QString metaTrace = metadataValue.toObject()
            .value(QStringLiteral("trace_id")).toString();
        if (!metaTrace.isEmpty()) {
            traceId = metaTrace;
        }
    }

    const QJsonObject envelope = buildEnvelope(
        method, eventJson, requestId, traceId, kDefaultDeadlineMs);
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

    PendingRequest pr;
    pr.method = method;
    pr.traceId = traceId;
    pr.deadlineEpochMs = QDateTime::currentMSecsSinceEpoch()
                         + static_cast<qint64>(kDefaultDeadlineMs) + kClientDeadlineGraceMs;
    pendingRequests_.emplace(requestId.toStdString(), pr);
    startClientDeadlineTimer(requestId, kDefaultDeadlineMs + kClientDeadlineGraceMs);
    return requestId;
}

QString MemoryClient::sendKnowledgeDetailRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kKnowledgeDetail, payload);
}
QString MemoryClient::sendConflictCompareRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kConflictCompare, payload);
}
QString MemoryClient::sendLifecycleStatusRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kLifecycleStatus, payload);
}
QString MemoryClient::sendContextAssembleRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kContextAssemble, payload);
}
QString MemoryClient::sendForgetPreviewRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kForgetPreview, payload);
}
QString MemoryClient::sendForgetExecuteRequest(const QJsonObject& payload)
{
    return sendRequest(methods::kForgetExecute, payload);
}

// ────────────────────────────────────────────────────────────────────────────
// 槽实现
// ────────────────────────────────────────────────────────────────────────────

void MemoryClient::handleSocketConnected()
{
    setConnectionState(ConnectionState::Connected);
    setLastError({});
    reconnectAttempts_ = 0;       // 连接成功，重连计数清零
    emit reconnectAttemptsChanged();
    // TD-IPC-004：重连成功通知（success=true）
    emit reconnectFinished(true, reconnectAttempts_);
}

void MemoryClient::handleSocketDisconnected()
{
    // TD-IPC-004：区分"显式 Stop"和"意外断开"。
    cancelReconnectTimer();
    // 先取消所有客户端 deadline（连接已断，pending 全部失败）
    for (auto& [id, timer] : clientDeadlineTimers_) {
        if (timer) { timer->stop(); timer->deleteLater(); }
    }
    clientDeadlineTimers_.clear();

    failInFlightRequests(kErrConnectionClosing, QStringLiteral("Connection closed by peer."));

    if (manualDisconnectInProgress_) {
        // Stop：不触发重连，进入 Disconnected。
        manualDisconnectInProgress_ = false;
        setConnectionState(ConnectionState::Disconnected);
        return;
    }

    // 意外断开：autoReconnectEnabled → 尝试 3 次指数退避。
    if (autoReconnectEnabled_ && reconnectAttempts_ < maxReconnectAttempts_) {
        startReconnectBackoff();
    } else {
        // 达到最大重连次数或已禁用 auto reconnect
        if (reconnectAttempts_ >= maxReconnectAttempts_) {
            setLastError(QStringLiteral("Maximum reconnect attempts reached."));
            emit connectionError(QStringLiteral("Maximum reconnect attempts reached."));
            emit reconnectFinished(false, reconnectAttempts_);
        }
        setConnectionState(ConnectionState::Disconnected);
    }
}

void MemoryClient::handleSocketErrorOccurred(QLocalSocket::LocalSocketError error)
{
    Q_UNUSED(error)
    const QString safeMessage = QStringLiteral("Local socket error occurred.");
    setLastError(safeMessage);
    if (connectionState_ == ConnectionState::Connecting) {
        // 连接失败 → 触发重连逻辑（走 disconnected 路径可能不来，直接处理）
        cancelReconnectTimer();
        if (!manualDisconnectInProgress_
            && autoReconnectEnabled_
            && reconnectAttempts_ < maxReconnectAttempts_) {
            startReconnectBackoff();
            emit connectionError(safeMessage);
            return;
        }
        if (reconnectAttempts_ >= maxReconnectAttempts_) {
            setLastError(QStringLiteral("Maximum reconnect attempts reached."));
            emit reconnectFinished(false, reconnectAttempts_);
        }
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
            return;
        }
        if (!decoded.error.ok()) {
            setLastError(decoded.error.safeMessage);
            emit connectionError(decoded.error.safeMessage);
            receiveBuffer_.clear();
            socket_->abort();
            // 协议错误不触发重连（可能是对端不兼容或被攻击），直接断开。
            manualDisconnectInProgress_ = false;
            setConnectionState(ConnectionState::Disconnected);
            failInFlightRequests(kErrProtocol, decoded.error.safeMessage);
            return;
        }

        receiveBuffer_ = receiveBuffer_.mid(decoded.consumed);

        if (decoded.envelope.has_value()) {
            const auto [responseParts, parseError] = parseResponse(*decoded.envelope);
            if (!parseError.ok() || !responseParts.has_value()) {
                setLastError(parseError.safeMessage);
                emit connectionError(parseError.safeMessage);
                receiveBuffer_.clear();
                socket_->abort();
                manualDisconnectInProgress_ = false;
                setConnectionState(ConnectionState::Disconnected);
                failInFlightRequests(kErrProtocol, parseError.safeMessage);
                return;
            }

            const QString& requestId = responseParts->requestId;
            const std::string ridStd = requestId.toStdString();

            // TD-022：先检查 deadline 是否已过期（绝对时间戳）。
            //   过期 → 视为迟到响应（late response），丢弃并清理。
            auto it = pendingRequests_.find(ridStd);
            if (it == pendingRequests_.end()) {
                continue;  // 未知/重复/已过期（TIMEOUT 已触发）响应：丢弃。
            }

            // deadline 过期保护（兜底）。
            const qint64 nowMs = QDateTime::currentMSecsSinceEpoch();
            if (it->second.deadlineEpochMs > 0 && nowMs > it->second.deadlineEpochMs) {
                expirePendingRequest(requestId, kErrClientTimeout,
                    QStringLiteral("Late response received after deadline; dropped."));
                continue;
            }

            // trace_id 关联校验
            if (responseParts->traceId != it->second.traceId) {
                expirePendingRequest(requestId, kErrProtocol,
                    QStringLiteral("Response trace_id mismatch."));
                continue;
            }

            // 成功路径：取消 deadline timer、擦除 pending、上抛响应。
            cancelClientDeadlineFor(requestId);
            pendingRequests_.erase(it);
            emit responseReceived(requestId, *decoded.envelope);
        }
    }
}

// ────────────────────────────────────────────────────────────────────────────
// 私有辅助
// ────────────────────────────────────────────────────────────────────────────

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

void MemoryClient::setReconnectAttempts(int n)
{
    if (reconnectAttempts_ == n) return;
    reconnectAttempts_ = n;
    emit reconnectAttemptsChanged();
}

void MemoryClient::failInFlightRequests(const QString& errorCode, const QString& safeMessage)
{
    if (pendingRequests_.empty()) {
        return;
    }
    // 拷贝 keys 后遍历，避免 erase 迭代器失效。
    std::vector<std::string> ids;
    ids.reserve(pendingRequests_.size());
    for (const auto& [id, _] : pendingRequests_) {
        ids.push_back(id);
    }
    for (const auto& id : ids) {
        expirePendingRequest(QString::fromStdString(id), errorCode, safeMessage);
    }
    pendingRequests_.clear();  // 兜底：保证全部清空
}

QString MemoryClient::generateRequestId() const
{
    return QStringLiteral("req_%1").arg(
        QUuid::createUuid().toString(QUuid::WithoutBraces));
}

// ── TD-IPC-004 重连辅助 ──────────────────────────────────────────────────────

void MemoryClient::startReconnectBackoff()
{
    cancelReconnectTimer();
    reconnectAttempts_++;
    emit reconnectAttemptsChanged();

    // 指数退避：500ms × 2^(attempt-1)。attempt 1 → 500ms, 2 → 1000ms, 3 → 2000ms。
    const int attempt = reconnectAttempts_;
    const int delayMs = static_cast<int>(reconnectBaseDelay_.count()) * (1 << (attempt - 1));
    setConnectionState(ConnectionState::Reconnecting);

    reconnectTimer_->setInterval(delayMs);
    reconnectTimer_->start();
}

void MemoryClient::cancelReconnectTimer()
{
    if (reconnectTimer_ && reconnectTimer_->isActive()) {
        reconnectTimer_->stop();
    }
}

// ── TD-022 客户端 deadline 超时辅助 ──────────────────────────────────────────

void MemoryClient::startClientDeadlineTimer(const QString& requestId, int deadlineMs)
{
    if (requestId.isEmpty() || deadlineMs <= 0) return;
    cancelClientDeadlineFor(requestId);

    auto* timer = new QTimer(this);
    timer->setSingleShot(true);
    timer->setInterval(deadlineMs);
    const std::string ridStd = requestId.toStdString();
    connect(timer, &QTimer::timeout, this, [this, requestId, ridStd]() {
        clientDeadlineTimers_.erase(ridStd);
        // TD-022：超时后 pendingRequests_ 同步 expire/cancel。
        expirePendingRequest(requestId, kErrClientTimeout,
            QStringLiteral("Client-side deadline exceeded; request aborted."));
    });
    clientDeadlineTimers_.emplace(ridStd, timer);
    timer->start();
}

void MemoryClient::cancelClientDeadlineFor(const QString& requestId)
{
    const std::string ridStd = requestId.toStdString();
    const auto it = clientDeadlineTimers_.find(ridStd);
    if (it == clientDeadlineTimers_.end()) return;
    if (it->second) {
        it->second->stop();
        it->second->deleteLater();
    }
    clientDeadlineTimers_.erase(it);
}

void MemoryClient::expirePendingRequest(
    const QString& requestId,
    const QString& errorCode,
    const QString& safeMessage)
{
    const std::string ridStd = requestId.toStdString();
    cancelClientDeadlineFor(requestId);
    pendingRequests_.erase(ridStd);
    emit requestFailed(requestId, errorCode, safeMessage);
}

}  // namespace kylin::memory::client::v1
