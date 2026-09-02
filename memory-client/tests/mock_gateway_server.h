#pragma once

#include <QLocalServer>
#include <QLocalSocket>
#include <QObject>
#include <QJsonObject>

#include <functional>
#include <vector>

#include "protocol_adapter.h"

namespace kylin::memory::client::v1::test_support {

// ============================================================================
// MockGatewayServer — 测试用 Mock Gateway（QLocalServer）
// ============================================================================
//
// 职责：
//   - 监听 QLocalServer（UDS / named pipe）
//   - 接受客户端连接，按长度前缀 JSON 协议解码请求 envelope
//   - 调用用户提供的 handler 决定响应 envelope
//   - 记录最近接收到的请求，供测试断言
//
// 状态：L0 测试基础设施（非生产代码，仅用于 Mock 契约测试）。
// 不实现真实业务逻辑；不得作为生产 Gateway 替代。
// ============================================================================

class MockGatewayServer : public QObject {
    Q_OBJECT

public:
    using Handler = std::function<QJsonObject(const EnvelopeParts&)>;

    explicit MockGatewayServer(QObject* parent = nullptr);
    ~MockGatewayServer() override;

    MockGatewayServer(const MockGatewayServer&) = delete;
    MockGatewayServer& operator=(const MockGatewayServer&) = delete;

    // 启动监听。socketName 为空时自动生成唯一名并返回。
    [[nodiscard]] QString listen(const QString& socketName = {});

    // 设置响应 handler。默认 handler 原样回传 envelope（echo）。
    void setHandler(Handler handler);

    // 最近接收到的请求数据（用于测试断言）。
    struct ReceivedRequest {
        QString method;
        QJsonObject payload;
        QString requestId;
        QString traceId;
        std::optional<int> deadlineMs;
    };
    [[nodiscard]] const std::vector<ReceivedRequest>& receivedRequests() const
    {
        return received_;
    }

    void close();

    // 测试后门：向第一个连接的 socket 直接写入一个 envelope 响应。
    // 用于模拟"延迟到达"的 stale response（MEDIUM-01 stale-response 防回写测试）。
    // 仅在已有客户端连接时有效；无连接时返回 false。
    bool sendRawEnvelope(const QJsonObject& envelope);

private slots:
    void handleNewConnection();

private:
    struct Connection {
        QLocalSocket* socket = nullptr;
        QByteArray buffer;
    };

    QLocalServer server_;
    Handler handler_;
    std::vector<ReceivedRequest> received_;
    std::vector<std::unique_ptr<Connection>> connections_;
};

}  // namespace kylin::memory::client::v1::test_support
