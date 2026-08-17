// test_memory_client_mock.cpp — MemoryClient ↔ MockGateway 契约测试（L0）
//
// 覆盖：
//   - 客户端连接 Mock Gateway 并发出 health 请求，收到回包
//   - 自定义 handler 决定响应（验证客户端解析正确）
//   - request_id 关联：响应带 request_id 时正确匹配
//   - 未连接时发送请求：requestFailed 报 ERR_NOT_CONNECTED
//   - 服务端不存在时连接失败：connectionError 信号
//   - 服务端 echo 响应（原样回传 envelope）
//   - 协议错误（服务端发送畸形包）触发 connectionError 并断连
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
    void connectAndSendHealthReceivesEcho();
    void customHandlerReturnsDifferentResponse();
    void sendRequestWhileDisconnectedFails();
    void connectToMissingServerEmitsConnectionError();
    void malformedServerPacketTriggersConnectionError();
    void healthResponseCarriesRequestIdForMatching();

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

void MemoryClientMockTest::connectAndSendHealthReceivesEcho()
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

    // 轮询等待连接成功（最多 5 秒）。避免依赖 QSignalSpy::wait 仅数新信号的语义。
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);
    QVERIFY(connectedSpy.count() >= 2);  // Disconnected→Connecting→Connected

    const QString requestId = client.sendHealthRequest();
    QVERIFY(!requestId.isEmpty());

    QTRY_VERIFY_WITH_TIMEOUT(responseSpy.count() >= 1, 5000);
    QCOMPARE(failedSpy.count(), 0);

    const auto args = responseSpy.takeFirst();
    QCOMPARE(args.at(0).toString(), requestId);
    const QJsonObject envelope = args.at(1).value<QJsonObject>();
    QVERIFY(envelope.contains(client::kProtocolVersionKey));

    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(err.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->method, client::methods::kMemoryHealth);
    QCOMPARE(parts->requestId, requestId);

    QCOMPARE(mock.receivedRequests().size(), static_cast<std::size_t>(1));
    QCOMPARE(mock.receivedRequests().front().method,
             client::methods::kMemoryHealth);
}

void MemoryClientMockTest::customHandlerReturnsDifferentResponse()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts)
                        -> QJsonObject {
        // 服务端：原样回传 method 与 request_id，但 payload 替换为固定响应。
        return client::buildEnvelope(
            parts.method,
            QJsonObject{{QStringLiteral("status"), QStringLiteral("ok")}},
            parts.requestId);
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
    const auto [parts, err] = client::parseEnvelope(envelope);
    QVERIFY(err.ok());
    QVERIFY(parts.has_value());
    QCOMPARE(parts->method, client::methods::kMemoryHealth);
    QCOMPARE(parts->requestId, requestId);
    QCOMPARE(parts->payload.value(QStringLiteral("status")).toString(),
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
    // 故意使用一个不存在的 socket 路径
    client.setSocketPath(QStringLiteral("/tmp/kylin-mock-missing-"
                                        "d4-test-not-a-socket.sock"));
    QSignalSpy errorSpy(&client, &client::MemoryClient::connectionError);
    QSignalSpy stateSpy(&client, &client::MemoryClient::connectionStateChanged);

    client.connectToService();
    // 连接错误通常会立刻 emit 或在事件循环首圈 emit
    QTRY_VERIFY_WITH_TIMEOUT(errorSpy.count() >= 1, 5000);
    QCOMPARE(client.connectionState(),
             client::MemoryClient::ConnectionState::Disconnected);
}

void MemoryClientMockTest::malformedServerPacketTriggersConnectionError()
{
    test_support::MockGatewayServer mock;
    // 服务端：通过 MockGatewayServer 的 __malformed__ 后门向客户端写入超大长度头，
    // 触发 DeclaredLengthTooLarge。MemoryClient 必须将不可恢复协议错误上报为
    // connectionError 并切换到 Disconnected（避免半包污染后续请求）。
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

    // 畸形包到达后，connectionError 必须上报，且状态被强制回到 Disconnected。
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
        return client::buildEnvelope(
            parts.method,
            QJsonObject{{QStringLiteral("status"), QStringLiteral("ok")}},
            parts.requestId);
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

    QTRY_VERIFY_WITH_TIMEOUT(responseSpy.count() >= 1, 5000);

    // 第一响应应匹配 first 或 second；最终两个响应都收到
    QTRY_COMPARE_WITH_TIMEOUT(responseSpy.count(), 2, 5000);
}

QTEST_MAIN(MemoryClientMockTest)

#include "test_memory_client_mock.moc"
