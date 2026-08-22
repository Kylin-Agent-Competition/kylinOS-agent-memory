// test_memory_client_mock.cpp — MemoryClient ↔ MockGateway 契约测试（L0）
//
// 覆盖：
//   - 客户端连接 Mock Gateway 并发出 health 请求，收到 FRZ-IPC-006 响应
//   - 自定义 handler 决定响应（验证客户端 parseResponse 路径）
//   - request_id 关联：响应带 request_id 时正确匹配
//   - 未连接时发送请求：requestFailed 报 ERR_NOT_CONNECTED
//   - 服务端不存在时连接失败：connectionError 信号
//   - 协议错误（服务端发送畸形包）触发 connectionError 并断连
//   - 未知 request_id 响应被丢弃（不转发给上层）
//
// 注意：本测试为 L0 Mock 契约测试，非 L2 麒麟 VM Runtime 证据。
// 不冒充真实 Memory Service 联调（L1）或麒麟 VM 链路（L2）。

#include "memory_client.h"
#include "mock_gateway_server.h"

#include <QJsonObject>
#include <QSignalSpy>
#include <QtTest>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

class MemoryClientMockTest final : public QObject {
    Q_OBJECT

private slots:
    void connectAndSendHealthReceivesResponse();
    void customHandlerReturnsDifferentResponse();
    void sendRequestWhileDisconnectedFails();
    void connectToMissingServerEmitsConnectionError();
    void malformedServerPacketTriggersConnectionError();
    void healthResponseCarriesRequestIdForMatching();
    void unknownRequestIdResponseIsDropped();

private:
    QString uniqueSocketName(const QString& prefix);
};

QString MemoryClientMockTest::uniqueSocketName(const QString& prefix)
{
    // 使用 /tmp 文件系统绝对路径 UDS（而非 Linux 抽象命名空间），
    // 确保在 WSL/容器/最小化 Linux 环境下跨进程稳定可连。
    return QStringLiteral("/tmp/kylin-mock-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

void MemoryClientMockTest::connectAndSendHealthReceivesResponse()
{
    test_support::MockGatewayServer mock;
    const QString socket = mock.listen(uniqueSocketName("echo"));
    QVERIFY(!socket.isEmpty());

    client::MemoryClient client;
    client.setSocketPath(socket);

    QSignalSpy connectedSpy(&client, &client::MemoryClient::connectionStateChanged);
    QSignalSpy responseSpy(&client, &client::MemoryClient::responseReceived);
    QSignalSpy failedSpy(&client, &client::MemoryClient::requestFailed);

    client.connectToService();

    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);
    QVERIFY(connectedSpy.count() >= 2);

    const QString requestId = client.sendHealthRequest();
    QVERIFY(!requestId.isEmpty());

    QTRY_VERIFY_WITH_TIMEOUT(responseSpy.count() >= 1, 5000);
    QCOMPARE(failedSpy.count(), 0);

    const auto args = responseSpy.takeFirst();
    QCOMPARE(args.at(0).toString(), requestId);
    const QJsonObject envelope = args.at(1).value<QJsonObject>();

    // 使用 parseResponse 校验响应结构（FRZ-IPC-006 §6.2）
    const auto [parts, err] = client::parseResponse(envelope);
    QVERIFY(err.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->status, QStringLiteral("ok"));
    QCOMPARE(parts->requestId, requestId);
    QCOMPARE(parts->traceId, requestId);
    QVERIFY(!parts->serverTs.isEmpty());
    QVERIFY(parts->data.contains(QStringLiteral("echo")));

    QCOMPARE(mock.receivedRequests().size(), static_cast<std::size_t>(1));
    QCOMPARE(mock.receivedRequests().front().method,
             client::methods::kHealth);
}

void MemoryClientMockTest::customHandlerReturnsDifferentResponse()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts)
                        -> QJsonObject {
        // 服务端：生成 FRZ-IPC-006 标准成功响应。
        return client::buildSuccessResponse(
            parts.requestId,
            parts.traceId,
            QJsonObject{{QStringLiteral("status"), QStringLiteral("ok")}});
    });
    const QString socket = mock.listen(uniqueSocketName("custom"));
    QVERIFY(!socket.isEmpty());

    client::MemoryClient client;
    client.setSocketPath(socket);

    QSignalSpy stateSpy(&client, &client::MemoryClient::connectionStateChanged);
    QSignalSpy responseSpy(&client, &client::MemoryClient::responseReceived);

    client.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);

    const QString requestId = client.sendHealthRequest();
    QVERIFY(!requestId.isEmpty());

    QTRY_VERIFY_WITH_TIMEOUT(responseSpy.count() >= 1, 5000);
    const auto args = responseSpy.takeFirst();
    QCOMPARE(args.at(0).toString(), requestId);
    const QJsonObject envelope = args.at(1).value<QJsonObject>();

    const auto [parts, err] = client::parseResponse(envelope);
    QVERIFY(err.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->status, QStringLiteral("ok"));
    QCOMPARE(parts->requestId, requestId);
    QCOMPARE(parts->data.value(QStringLiteral("status")).toString(),
             QStringLiteral("ok"));
}

void MemoryClientMockTest::sendRequestWhileDisconnectedFails()
{
    client::MemoryClient client;
    client.setSocketPath(QStringLiteral("/tmp/does-not-exist-kylin-mock.sock"));

    QSignalSpy failedSpy(&client, &client::MemoryClient::requestFailed);
    const QString id = client.sendHealthRequest();
    QVERIFY(id.isEmpty());
    QCOMPARE(failedSpy.count(), 1);
    const auto args = failedSpy.takeFirst();
    QCOMPARE(args.at(1).toString(), QStringLiteral("ERR_NOT_CONNECTED"));
}

void MemoryClientMockTest::connectToMissingServerEmitsConnectionError()
{
    client::MemoryClient client;
    client.setSocketPath(QStringLiteral("/tmp/kylin-mock-missing-"
                                        "d4-test-not-a-socket.sock"));
    QSignalSpy errorSpy(&client, &client::MemoryClient::connectionError);
    QSignalSpy stateSpy(&client, &client::MemoryClient::connectionStateChanged);

    client.connectToService();
    QTRY_VERIFY_WITH_TIMEOUT(errorSpy.count() >= 1, 5000);
    QCOMPARE(client.connectionState(),
             client::MemoryClient::ConnectionState::Disconnected);
}

void MemoryClientMockTest::malformedServerPacketTriggersConnectionError()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts&)
                        -> QJsonObject {
        return QJsonObject{{QStringLiteral("__malformed__"), true}};
    });
    const QString socket = mock.listen(uniqueSocketName("malformed"));
    QVERIFY(!socket.isEmpty());

    client::MemoryClient client;
    client.setSocketPath(socket);

    QSignalSpy stateSpy(&client, &client::MemoryClient::connectionStateChanged);
    QSignalSpy errorSpy(&client, &client::MemoryClient::connectionError);

    client.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);

    const QString id = client.sendHealthRequest();
    QVERIFY(!id.isEmpty());

    QTRY_VERIFY_WITH_TIMEOUT(errorSpy.count() >= 1, 5000);
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Disconnected,
        5000);
    QVERIFY(!errorSpy.takeFirst().at(0).toString().isEmpty());
}

void MemoryClientMockTest::healthResponseCarriesRequestIdForMatching()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts)
                        -> QJsonObject {
        return client::buildSuccessResponse(
            parts.requestId,
            parts.traceId,
            QJsonObject{{QStringLiteral("status"), QStringLiteral("ok")}});
    });
    const QString socket = mock.listen(uniqueSocketName("match"));
    QVERIFY(!socket.isEmpty());

    client::MemoryClient client;
    client.setSocketPath(socket);

    QSignalSpy stateSpy(&client, &client::MemoryClient::connectionStateChanged);
    QSignalSpy responseSpy(&client, &client::MemoryClient::responseReceived);

    client.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);

    // 连续两个 health 请求，验证 request_id 关联
    const QString first = client.sendHealthRequest();
    const QString second = client.sendHealthRequest();
    QVERIFY(!first.isEmpty());
    QVERIFY(!second.isEmpty());
    QVERIFY(first != second);

    QTRY_COMPARE_WITH_TIMEOUT(responseSpy.count(), 2, 5000);
}

void MemoryClientMockTest::unknownRequestIdResponseIsDropped()
{
    test_support::MockGatewayServer mock;
    // 服务端：返回一个 request_id 不匹配的响应（伪造 ID）。
    mock.setHandler([](const client::EnvelopeParts&)
                        -> QJsonObject {
        return client::buildSuccessResponse(
            QStringLiteral("req_forged_unknown_id"),
            QStringLiteral("req_forged_unknown_id"),
            QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("unknown"));
    QVERIFY(!socket.isEmpty());

    client::MemoryClient client;
    client.setSocketPath(socket);

    QSignalSpy responseSpy(&client, &client::MemoryClient::responseReceived);
    QSignalSpy failedSpy(&client, &client::MemoryClient::requestFailed);

    client.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);

    const QString requestId = client.sendHealthRequest();
    QVERIFY(!requestId.isEmpty());

    // 未知 request_id 的响应应被丢弃，responseReceived 不应触发。
    // 等待一段足够时间确保服务端已响应。
    QTest::qWait(500);
    QCOMPARE(responseSpy.count(), 0);
    QCOMPARE(failedSpy.count(), 0);
}

QTEST_MAIN(MemoryClientMockTest)

#include "test_memory_client_mock.moc"
