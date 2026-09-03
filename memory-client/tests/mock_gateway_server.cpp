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
    // D12-C FAIL-2 修复（TD-IPC-001 同型漏洞）：server_.close() 不会删除
    //   socket 文件 / abstract name，导致客户端重连时 "connectToServer(path)"
    //   可能因残留文件返回成功（Linux domain socket 的 path-exists 行为）。
    //   这里显式 removeServer(serverName) 让客户端重连必定失败，验证完整
    //   3 次指数退避上限路径。
    QString name;
    if (server_.isListening()) {
        name = server_.serverName();
    }
    if (server_.isListening()) {
        server_.close();
    }
    if (!name.isEmpty()) {
        QLocalServer::removeServer(name);
    }
}

bool MockGatewayServer::sendRawEnvelope(const QJsonObject& envelope)
{
    for (auto& conn : connections_) {
        if (conn->socket && conn->socket->state() == QLocalSocket::ConnectedState) {
            const auto packet = encodeEnvelope(envelope);
            if (packet.has_value()) {
                conn->socket->write(*packet);
                conn->socket->flush();
                return true;
            }
            return false;
        }
    }
    return false;
}

bool MockGatewayServer::sendRawBytes(const QByteArray& raw)
{
    for (auto& conn : connections_) {
        if (conn->socket && conn->socket->state() == QLocalSocket::ConnectedState) {
            conn->socket->write(raw);
            conn->socket->flush();
            return true;
        }
    }
    return false;
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
                    if (!parseError.ok() || !parts.has_value()) {
                        continue;
                    }
                    received_.push_back({parts->method, parts->payload,
                                         parts->requestId, parts->traceId,
                                         parts->deadlineMs});

                    QJsonObject response = handler_
                                               ? handler_(*parts)
                                               : buildSuccessResponse(
                                                   parts->requestId,
                                                   parts->traceId,
                                                   QJsonObject{{QStringLiteral("echo"),
                                                                parts->method}});

                    // 测试后门：若 handler 返回的 envelope 含 "__malformed__": true，
                    // 则跳过正常编码，向客户端写入畸形字节流，用于验证客户端协议错误
                    // 处理路径（不可恢复错误 → 触发 connectionError 并断连）。
                    static const QString kMalformedKey = QStringLiteral("__malformed__");
                    if (response.value(kMalformedKey).toBool()) {
                        // 写入超大声明长度头，触发 DeclaredLengthTooLarge。
                        const quint32 oversized = kMaxMessageLen + 1u;
                        char bad[4];
                        bad[0] = static_cast<char>((oversized >> 24) & 0xFF);
                        bad[1] = static_cast<char>((oversized >> 16) & 0xFF);
                        bad[2] = static_cast<char>((oversized >> 8) & 0xFF);
                        bad[3] = static_cast<char>(oversized & 0xFF);
                        raw->write(bad, 4);
                        raw->flush();
                        continue;
                    }
                    // 测试后门：若 handler 返回 "__hold__": true，则不回包
                    // （不 encodeEnvelope、不 write），用于 L0 制造"请求 in-flight
                    // → reset → 延迟响应"竞态。requestId/traceId 已经 push 到
                    // received_，外层稍后可通过 sendRawEnvelope 单独注入。
                    static const QString kHoldKey = QStringLiteral("__hold__");
                    if (response.value(kHoldKey).toBool()) {
                        continue;
                    }

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
