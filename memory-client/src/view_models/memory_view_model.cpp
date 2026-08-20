#include "view_models/memory_view_model.h"

#include <QJsonObject>

namespace kylin::memory::client::v1 {

namespace {

QString stateToString(MemoryClient::ConnectionState state)
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

}  // namespace

MemoryViewModel::MemoryViewModel(QObject* parent)
    : QObject(parent)
{
    connect(&client_, &MemoryClient::connectionStateChanged,
            this, &MemoryViewModel::onConnectionStateChanged);
    connect(&client_, &MemoryClient::lastErrorChanged,
            this, &MemoryViewModel::onLastErrorChanged);
    connect(&client_, &MemoryClient::responseReceived,
            this, &MemoryViewModel::onResponseReceived);
    connect(&client_, &MemoryClient::requestFailed,
            this, &MemoryViewModel::onRequestFailed);
    connect(&client_, &MemoryClient::connectionError,
            this, &MemoryViewModel::onConnectionError);
}

MemoryViewModel::~MemoryViewModel() = default;

QString MemoryViewModel::socketPath() const
{
    return client_.socketPath();
}

void MemoryViewModel::setSocketPath(const QString& path)
{
    if (client_.socketPath() == path) {
        return;
    }
    client_.setSocketPath(path);
    emit socketPathChanged();
}

QString MemoryViewModel::connectionState() const
{
    return stateToString(client_.connectionState());
}

QString MemoryViewModel::lastError() const
{
    return client_.lastError();
}

void MemoryViewModel::connectToService()
{
    client_.connectToService();
}

void MemoryViewModel::disconnectFromService()
{
    client_.disconnectFromService();
}

void MemoryViewModel::sendHealth()
{
    setBusy(true);
    const QString id = client_.sendHealthRequest();
    if (id.isEmpty()) {
        setBusy(false);
        return;
    }
    setLastRequestId(id);
}

void MemoryViewModel::sendMemoryQuery(const QJsonObject& payload)
{
    setBusy(true);
    const QString id = client_.sendRequest(methods::kMemoryRetrieve, payload);
    if (id.isEmpty()) {
        setBusy(false);
        return;
    }
    setLastRequestId(id);
}

void MemoryViewModel::onConnectionStateChanged()
{
    emit connectionStateChanged();
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected
        && busy_) {
        // 连接断开/未连接时，in-flight 请求会由 requestFailed 单独回报；
        // busy 在那里清零，此处不重复清。
    }
}

void MemoryViewModel::onLastErrorChanged()
{
    emit lastErrorChanged();
}

void MemoryViewModel::onResponseReceived(
    const QString& requestId, const QJsonObject& envelope)
{
    Q_UNUSED(requestId)
    setLastResponse(envelope);
    setBusy(false);
}

void MemoryViewModel::onRequestFailed(
    const QString& requestId, const QString& errorCode, const QString& safeMessage)
{
    if (requestId == lastRequestId_ || requestId.isEmpty()) {
        setBusy(false);
    }
    emit requestFailed(requestId, errorCode, safeMessage);
}

void MemoryViewModel::onConnectionError(const QString& safeMessage)
{
    Q_UNUSED(safeMessage)
    // 已通过 lastErrorChanged 与 connectionStateChanged 暴露，此处保持简单。
}

void MemoryViewModel::setBusy(bool value)
{
    if (busy_ == value) {
        return;
    }
    busy_ = value;
    emit busyChanged();
}

void MemoryViewModel::setLastRequestId(const QString& id)
{
    if (lastRequestId_ == id) {
        return;
    }
    lastRequestId_ = id;
    emit lastRequestIdChanged();
}

void MemoryViewModel::setLastResponse(const QJsonObject& envelope)
{
    lastResponse_ = envelope;
    emit lastResponseChanged();
}

}  // namespace kylin::memory::client::v1
