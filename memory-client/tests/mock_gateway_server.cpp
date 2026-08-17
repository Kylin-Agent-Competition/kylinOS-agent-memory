#include "mock_gateway_server.h"

#include <QCoreApplication>
#include <QUuid>

namespace kylin::memory::client::v1::test_support {

MockGatewayServer::MockGatewayServer(QObject* parent)
    : QObject(parent)
{
    connect(&server_, &QLocalServer::newConnection,
            this, &MockGatewayServer::handleNewConnection);
    server_.setSocketOptions(QLocalServer::UserAccessOption);
}

MockGatewayServer::~MockGatewayServer()
{
    close();
}

QString MockGatewayServer::listen(const QString& socketName)
{
    QString name = socketName.isEmpty()
                       ? QStringLiteral("kylin-memory-mock-%1")
                             .arg(QUuid::createUuid().toString(QUuid::WithoutBraces))
                       : socketName;
    // 移除可能残留的同名 socket
    QLocalServer::removeServer(name);
    if (!server_.listen(name)) {
        return {};
    }
    return server_.serverName();
}

void MockGatewayServer::setHandler(Handler handler)
{
    handler_ = std::move(handler);
}

void MockGatewayServer::close()
{
    for (auto& conn : connections_) {
        if (conn->socket) {
            conn->socket->disconnect(this);
            conn->socket->abort();
            conn->socket->deleteLater();
            conn->socket = nullptr;
        }
    }
    connections_.clear();
    if (server_.isListening()) {
        server_.close();
    }
}

void MockGatewayServer::handleNewConnection()
{
    QLocalSocket* socket = server_.nextPendingConnection();
    if (!socket) {
        return;
    }
    auto conn = std::make_unique<Connection>();
    conn->socket = socket;
    QLocalSocket* raw = socket;
    connections_.push_back(std::move(conn));
    connect(raw, &QLocalSocket::readyRead, this, [this, raw]() {
        for (auto& conn : connections_) {
            if (conn->socket == raw) {
                conn->buffer.append(raw->readAll());
                while (true) {
                    DecodeResult decoded = decodePacket(conn->buffer);
                    if (decoded.error.kind == ProtocolErrorKind::IncompletePacket) {
                        return;
                    }
                    if (!decoded.error.ok()) {
                        conn->buffer.clear();
                        raw->abort();
                        return;
                    }
                    conn->buffer = conn->buffer.mid(decoded.consumed);
                    if (!decoded.envelope.has_value()) {
                        continue;
                    }
                    const auto [parts, parseError] = parseEnvelope(*decoded.envelope);
                    if (!parseError.ok()) {
                        continue;
                    }
                    received_.push_back({parts.method, parts.payload,
                                         parts.requestId, parts.traceId,
                                         parts.deadlineMs});

                    QJsonObject response = handler_
                                               ? handler_(parts)
                                               : *decoded.envelope;
                    const auto packet = encodeEnvelope(response);
                    if (packet.has_value()) {
                        raw->write(*packet);
                        raw->flush();
                    }
                }
                break;
            }
        }
    });
}

}  // namespace kylin::memory::client::v1::test_support
