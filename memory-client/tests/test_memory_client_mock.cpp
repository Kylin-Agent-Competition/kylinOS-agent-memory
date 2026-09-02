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

#include <QFile>
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
    // D12-C TD-022：客户端 deadline 超时 → TIMEOUT；迟到响应丢弃
    void clientSideDeadlineTimeoutEmitsRequestFailedAndLateResponseDropped();
    // D12-C TD-IPC-004：意外断开触发 3 次指数退避自动重连（最终失败）
    void unexpectedDisconnectTriggersThreeReconnectBackoff();
    // D12-C TD-IPC-004：显式 disconnect（Stop）不应触发自动重连
    void intentionalStopDoesNotTriggerAutoReconnect();
    // D12-C TD-IPC-004：重连成功时 reconnectAttempts 归零
    void disconnectWhileAutoReconnectSuppressesFurtherRetries();

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

// D12-C TD-022 §C-2：
//   客户端级 deadline_ms + 100ms 超时后：
//   (1) requestFailed(TIMEOUT) 必触发；
//   (2) pendingRequests_ 同步 expire/cancel（mock 不会再响应 TIMEOUT）；
//   (3) 迟到响应（过期后服务端才回）必须被丢弃，不再上抛 responseReceived。
void MemoryClientMockTest::clientSideDeadlineTimeoutEmitsRequestFailedAndLateResponseDropped()
{
    test_support::MockGatewayServer mock;
    // Mock：用 "__hold__" 后门暂不回包，让客户端侧先 deadline TIMEOUT；
    //       测试再用 sendRawEnvelope 注入迟到响应验证丢弃逻辑。
    mock.setHandler([](const client::EnvelopeParts&) -> QJsonObject {
        return QJsonObject{{QStringLiteral("__hold__"), true}};
    });
    const QString socket = mock.listen(uniqueSocketName("timeout-late"));
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

    // 等待客户端侧 deadline（默认 5000ms + 100ms 容差 → 5.1s）。
    // 为了加速 L0，我们把等待设定为 5500ms，确保 timeout 必触发。
    QTRY_COMPARE_WITH_TIMEOUT(failedSpy.count(), 1, 8000);
    const auto args = failedSpy.takeFirst();
    QCOMPARE(args.at(0).toString(), requestId);
    QCOMPARE(args.at(1).toString(), QStringLiteral("TIMEOUT"));  // TD-022：对齐 FRZ-IPC-002
    QCOMPARE(responseSpy.count(), 0);

    // TD-022：迟到响应（late response）—— 过期后才到，必须丢弃。
    // 伪造"已过 deadline"的成功 envelope，并通过 Mock::sendRawEnvelope 下发。
    QJsonObject late = client::buildSuccessResponse(
        requestId,
        requestId,
        QJsonObject{{QStringLiteral("echo"), QStringLiteral("late")}});
    QVERIFY(mock.sendRawEnvelope(late));
    QTest::qWait(300);  // 等待 readyRead 处理

    QCOMPARE(responseSpy.count(), 0);   // 迟到响应不得上抛
    QCOMPARE(failedSpy.count(), 0);     // 迟到响应不得产生新 TIMEOUT/失败
}

// D12-C TD-IPC-004 §C-1：意外断开后最多 3 次指数退避重连，达到上限后 reconnectFinished(false,3)。
void MemoryClientMockTest::unexpectedDisconnectTriggersThreeReconnectBackoff()
{
    test_support::MockGatewayServer mock;
    const QString socket = mock.listen(uniqueSocketName("auto-reconnect-max"));
    QVERIFY(!socket.isEmpty());

    client::MemoryClient client;
    client.setSocketPath(socket);
    QVERIFY(client.autoReconnectEnabled());

    QSignalSpy stateSpy(&client, &client::MemoryClient::connectionStateChanged);
    QSignalSpy reconnectFinishedSpy(&client, &client::MemoryClient::reconnectFinished);

    client.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);
    QCOMPARE(client.reconnectAttempts(), 0);

    // Mock 服务端关闭 socket（模拟意外断开），再关闭 server（让后续重连失败以便
    // 验证"最多3次"行为与 reconnectFinished 信号）。
    mock.close();

    // 重连总窗口：500ms+1000ms+2000ms = 3500ms。给 8s 余量确保信号触发。
    QTRY_COMPARE_WITH_TIMEOUT(reconnectFinishedSpy.count(), 1, 10000);
    {
        const auto args = reconnectFinishedSpy.takeFirst();
        QCOMPARE(args.at(0).toBool(), false);
        QCOMPARE(args.at(1).toInt(), 3);
    }
    QCOMPARE(client.reconnectAttempts(), 3);
    QCOMPARE(client.connectionState(), client::MemoryClient::ConnectionState::Disconnected);

    // 状态序列应含：Connecting→Connected→Disconnected→Reconnecting×3→Disconnected。
    QVERIFY(stateSpy.count() >= 6);
}

// D12-C TD-IPC-004 §C-1：显式 disconnect（Stop）不计入意外断开，不触发自动重连。
void MemoryClientMockTest::intentionalStopDoesNotTriggerAutoReconnect()
{
    test_support::MockGatewayServer mock;
    const QString socket = mock.listen(uniqueSocketName("stop-no-reconnect"));
    QVERIFY(!socket.isEmpty());

    client::MemoryClient client;
    client.setSocketPath(socket);
    QVERIFY(client.autoReconnectEnabled());

    QSignalSpy reconnectFinishedSpy(&client, &client::MemoryClient::reconnectFinished);

    client.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Connected,
        5000);

    // 显式 Stop → 立即断开，不触发 auto-reconnect。
    client.disconnectFromService();
    QTRY_COMPARE_WITH_TIMEOUT(
        client.connectionState(),
        client::MemoryClient::ConnectionState::Disconnected,
        5000);
    QCOMPARE(client.reconnectAttempts(), 0);
    // reconnectFinished 只在自动重连流程结束时才发射。
    QCOMPARE(reconnectFinishedSpy.count(), 0);
}

// D12-C TD-IPC-004：autoReconnect 退避计时窗口中显式 disconnect → 停止重连、
// reconnectAttempts 不再递增（Stop 语义优先）。
void MemoryClientMockTest::disconnectWhileAutoReconnectSuppressesFurtherRetries()
{
    // 不启动任何 Mock server：connect 会直接失败 → 进入 auto-reconnect 窗口。
    const QString nonexistent = uniqueSocketName("no-server");
    // 确保路径不存在：QLocalServer 未启动 → socket 绝不存在。
    QFile::remove(nonexistent);

    client::MemoryClient client;
    client.setSocketPath(nonexistent);
    QVERIFY(client.autoReconnectEnabled());

    QSignalSpy stateSpy(&client, &client::MemoryClient::connectionStateChanged);

    client.connectToService();
    // 等连接失败 → 进入 reconnecting（attempt 1 触发，此时会 start backoff）。
    QTRY_COMPARE_WITH_TIMEOUT(client.reconnectAttempts() >= 1, true, 6000);
    QVERIFY(client.reconnectAttempts() <= 3);

    // 显式 Stop：退避窗口应立即停止，重连次数不再增加。
    client.disconnectFromService();
    QCOMPARE(client.connectionState(), client::MemoryClient::ConnectionState::Disconnected);
    const int attemptsAtStop = client.reconnectAttempts();

    // 再等待 3s（应覆盖 attempt2/3 的退避窗口总和 3000ms）；尝试次数必须不变。
    QTest::qWait(3500);
    QCOMPARE(client.reconnectAttempts(), attemptsAtStop);
    QCOMPARE(client.connectionState(), client::MemoryClient::ConnectionState::Disconnected);
    Q_UNUSED(stateSpy);
}

QTEST_MAIN(MemoryClientMockTest)

#include "test_memory_client_mock.moc"
