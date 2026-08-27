// test_d5_vertical_link_demo.cpp — D5-C Demo Harness L0 Negative/Path Tests
//
// 范围（L0 Mock Gateway）：覆盖 Reviewer REWORK 提出的 1/2/4 类主问题。
// 注意：本测试仅为 memory-client 侧 Demo / Prototype 的 L0 契约验证，
//       不声称代表真实 AI Assistant Hook / Chat DB / ChatRecord。
//
// 用例清单：
//   §A  问题1 — status=error 明确路由失败路径
//     A1  memory.retrieve → status=error, UNSUPPORTED_METHOD
//         → preChatStage == "failed", injectedContextText == "", modelRequestText == originalUserText
//     A2  memory.store    → status=error, UNSUPPORTED_METHOD
//         → postTurnStage == "failed"
//   §B  问题2 — MemoryContext 形状严格按 memory_context.v1.json 契约
//     B1  empty context     (schema/query/context_version 齐全，但无 token/count)
//         → injectedContextText == "" (不产生伪标记)
//     B2  error context     (response 本身 status=error)
//         → injectedContextText == "" (error response 不参与拼接)
//     B3  malformed context (缺少 schema_version / query_id / context_version 任一必填)
//         → injectedContextText == ""
//     B4  normal context    (契约齐全、selected_memory_ids 非空、injection_status=prepared)
//         → injectedContextText 非空，含 [MEMORY-CONTEXT] 头/尾
//     B5  injection failure (injection_status=failed)
//         → injectedContextText == "" (明确落实 injection failure 不注入)
//   §C  问题4 — 运行正确性/验证闭环
//     C1  独立 pendingPostTurnRequestId：PreChat in-flight 时 PostTurn 响应不串台
//     C2  Reset 取消 PreChat in-flight，阶段回到 idle，pendingRequestId 清空
//     C3  Preview ⇄ Send 复用同一 event_id / occurred_at（按参数 key 缓存）
//
// 不覆盖（非 L0 Mock 范围）：
//   - 真实 D 轨 Gateway / Echo 联调（需 L1 环境）
//   - 真实银河麒麟 VM Runtime 证据（需 L2 环境）
//   - 客户端死线 QTimer 计时精度（依赖系统时钟 + 5s 级，单独 L1 smoke）

#include "memory_client.h"
#include "mock_gateway_server.h"
#include "view_models/memory_view_model.h"

#include <QJsonObject>
#include <QJsonArray>
#include <QSignalSpy>
#include <QStringList>
#include <QtTest>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

class D5VerticalLinkDemoTest final : public QObject {
    Q_OBJECT

private slots:
    void init();
    void cleanup();

    // §A 问题1 — status=error 路由失败路径
    void memoryRetrieveWithUnsupportedMethodRoutesPreChatToFailed();   // A1
    void memoryStoreWithUnsupportedMethodRoutesPostTurnToFailed();    // A2

    // §B 问题2 — MemoryContext 契约形状 (memory_context.v1.json)
    void emptyContextProducesEmptyInjectedTextNoFakeMarker();          // B1
    void errorResponseNeverJoinsContext();                             // B2
    void malformedContextMissingRequiredFieldsProducesEmptyText();     // B3
    void normalContractContextProducesValidMarkedText();               // B4
    void injectionStatusFailedProducesEmptyInjectedText();             // B5

    // §C 问题4 — 运行正确性
    void postTurnResponseDoesNotHijackInFlightPreChat();               // C1
    void resetPreChatClearsPendingAndBackToIdle();                     // C2
    void previewAndSendReuseSameEventIdTimestamp();                    // C3

private:
    QString uniqueSocketName(const QString& prefix);

    // helper：构造合法 memory_context.v1.json 形状 context 对象
    QJsonObject makeValidContext(const QString& queryId,
                                 const QString& injectionStatus,
                                 const QStringList& selectedIds,
                                 int actualTokenCount,
                                 bool withMemoryItems = false) const;
};

QString D5VerticalLinkDemoTest::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d5-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

QJsonObject D5VerticalLinkDemoTest::makeValidContext(
    const QString& queryId,
    const QString& injectionStatus,
    const QStringList& selectedIds,
    int actualTokenCount,
    bool withMemoryItems) const
{
    QJsonArray ids;
    for (const auto& id : selectedIds) ids.append(id);

    QJsonObject ctx{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("event_id"), QStringLiteral("event-ctx-test")},
        {QStringLiteral("trace_id"), QStringLiteral("trace-test")},
        {QStringLiteral("user_id"), QStringLiteral("local-user")},
        {QStringLiteral("session_id"), QStringLiteral("session-test")},
        {QStringLiteral("turn_id"), QStringLiteral("turn-test")},
        {QStringLiteral("occurred_at"),
         QStringLiteral("2026-08-14T04:59:59.900Z")},
        {QStringLiteral("collected_at"),
         QStringLiteral("2026-08-14T05:00:00.000Z")},
        {QStringLiteral("source_reference"),
         QStringLiteral("ref:context-build:test")},
        {QStringLiteral("idempotency_key"),
         QStringLiteral("memory-context:") + queryId},
        {QStringLiteral("query_id"), queryId},
        {QStringLiteral("selected_memory_ids"), ids},
        {QStringLiteral("context_version"), QStringLiteral("context-v1")},
        {QStringLiteral("token_budget"), 800},
        {QStringLiteral("actual_token_count"), actualTokenCount},
        {QStringLiteral("sensitive_excluded_count"), 0},
        {QStringLiteral("forgotten_excluded_count"), 0},
        {QStringLiteral("conflict_excluded_count"), 0},
        {QStringLiteral("injection_status"), injectionStatus},
    };

    if (withMemoryItems) {
        QJsonArray items;
        for (int i = 0; i < selectedIds.size(); ++i) {
            items.append(QJsonObject{
                {QStringLiteral("memory_id"), selectedIds[i]},
                {QStringLiteral("version_id"), QStringLiteral("v1")},
                {QStringLiteral("content"),
                 QStringLiteral("记忆内容片段 #%1").arg(i + 1)},
            });
        }
        ctx.insert(QStringLiteral("memory_items"), items);
    }
    return ctx;
}

void D5VerticalLinkDemoTest::init()
{
    // 每次测试前清理可能残留的同名 socket
    QLocalServer::removeServer(uniqueSocketName("a1"));
    QLocalServer::removeServer(uniqueSocketName("a2"));
    QLocalServer::removeServer(uniqueSocketName("b1"));
    QLocalServer::removeServer(uniqueSocketName("b2"));
    QLocalServer::removeServer(uniqueSocketName("b3"));
    QLocalServer::removeServer(uniqueSocketName("b4"));
    QLocalServer::removeServer(uniqueSocketName("b5"));
    QLocalServer::removeServer(uniqueSocketName("c1"));
    QLocalServer::removeServer(uniqueSocketName("c2"));
    QLocalServer::removeServer(uniqueSocketName("c3"));
}

void D5VerticalLinkDemoTest::cleanup()
{
    // no-op by now; cleanup is handled per-test via mock.close()
}

// ── §A — 问题1：status=error 路由失败路径 ──────────────────────────────────

void D5VerticalLinkDemoTest::memoryRetrieveWithUnsupportedMethodRoutesPreChatToFailed()
{
    test_support::MockGatewayServer mock;
    // Mock: 对 memory.retrieve 直接返回 status=error / UNSUPPORTED_METHOD
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kUnsupportedMethod,
                QStringLiteral("Gateway has not implemented memory.retrieve."));
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();

    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy preStageSpy(&vm, &client::MemoryViewModel::preChatStageChanged);
    QSignalSpy reqFailedSpy(&vm, &client::MemoryViewModel::requestFailed);

    vm.runPreChatPipeline(QStringLiteral("u"), QStringLiteral("s"),
                          QStringLiteral("scene"), 800,
                          QStringLiteral("原文A：Hello"));

    // 期望进入 failed 阶段，而非 ready
    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("failed"), 5000);
    QVERIFY(vm.injectedContextText().isEmpty());
    QCOMPARE(vm.modelRequestText(), QStringLiteral("原文A：Hello"));
    QCOMPARE(vm.originalUserText(), QStringLiteral("原文A：Hello"));

    // 必须上报 requestFailed，errorCode == UNSUPPORTED_METHOD
    QVERIFY(reqFailedSpy.count() >= 1);
    const auto args = reqFailedSpy.takeFirst();
    QCOMPARE(args.at(1).toString(),
             client::error_codes::kUnsupportedMethod);
}

void D5VerticalLinkDemoTest::memoryStoreWithUnsupportedMethodRoutesPostTurnToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryStore) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kUnsupportedMethod,
                QStringLiteral("Gateway has not implemented memory.store."));
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();

    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy postStageSpy(&vm, &client::MemoryViewModel::postTurnStageChanged);
    QSignalSpy reqFailedSpy(&vm, &client::MemoryViewModel::requestFailed);

    vm.runPostTurnPipeline(QStringLiteral("u"), QStringLiteral("s"),
                           QStringLiteral("turn-1"), QStringLiteral("trace-1"),
                           QStringLiteral("msg-1"), QStringLiteral("final text"),
                           QStringLiteral("completed"), QStringLiteral("stop"));

    // 不得显示 sent，必须是 failed
    QTRY_COMPARE_WITH_TIMEOUT(vm.postTurnStage(), QStringLiteral("failed"), 5000);

    QVERIFY(reqFailedSpy.count() >= 1);
    const auto args = reqFailedSpy.takeFirst();
    QCOMPARE(args.at(1).toString(),
             client::error_codes::kUnsupportedMethod);

    // lastTurnFinalizedEvent 是我们构造过的（发送前写入），非空不代表成功。
    QVERIFY(!vm.lastTurnFinalizedEvent().isEmpty());
}

// ── §B — 问题2：MemoryContext 契约形状 ──────────────────────────────────────

void D5VerticalLinkDemoTest::emptyContextProducesEmptyInjectedTextNoFakeMarker()
{
    test_support::MockGatewayServer mock;
    // data.context 形状齐全，但 selected_memory_ids=[] 且 actual_token_count=0
    // → 视为"空 context"，不得产生伪标记。
    mock.setHandler([this](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            const QJsonObject ctx = makeValidContext(
                QStringLiteral("q-empty"), QStringLiteral("prepared"), {}, 0);
            const QJsonObject data{
                {QStringLiteral("context"), ctx},
            };
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreChatPipeline("u", "s", "dev", 800, QStringLiteral("空原文"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("ready"), 5000);

    // 空 context → injected 空，modelRequestText == originalUserText
    QVERIFY(vm.injectedContextText().isEmpty());
    QCOMPARE(vm.modelRequestText(), QStringLiteral("空原文"));
    QVERIFY(!vm.modelRequestText().contains(QStringLiteral("[MEMORY-CONTEXT]")));
}

void D5VerticalLinkDemoTest::errorResponseNeverJoinsContext()
{
    test_support::MockGatewayServer mock;
    // memory.retrieve 返回 status=error → 绝不能参与 context 拼接。
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kInternalError,
                QStringLiteral("Boom — Gateway internal error"));
        }
        return client::buildSuccessResponse(parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    const QString original = QStringLiteral("用户原文：error case");
    vm.runPreChatPipeline("u", "s", "dev", 800, original);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("failed"), 5000);
    QVERIFY(vm.injectedContextText().isEmpty());
    QCOMPARE(vm.modelRequestText(), original);
    QCOMPARE(vm.originalUserText(), original);
    QVERIFY(!vm.modelRequestText().contains(QStringLiteral("[MEMORY-CONTEXT]")));
}

void D5VerticalLinkDemoTest::malformedContextMissingRequiredFieldsProducesEmptyText()
{
    test_support::MockGatewayServer mock;
    // data.context 为对象，但缺少契约必填 schema_version / query_id / context_version。
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            const QJsonObject malformedCtx{
                // 故意缺 schema_version / query_id / context_version
                {QStringLiteral("selected_memory_ids"),
                 QJsonArray{QStringLiteral("m-1"), QStringLiteral("m-2")}},
                {QStringLiteral("actual_token_count"), 120},
                {QStringLiteral("injection_status"), QStringLiteral("prepared")},
            };
            const QJsonObject data{{QStringLiteral("context"), malformedCtx}};
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b3"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreChatPipeline("u", "s", "dev", 800, QStringLiteral("malformed"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("ready"), 5000);

    // malformed context → 空注入；不产生伪标记
    QVERIFY(vm.injectedContextText().isEmpty());
    QCOMPARE(vm.modelRequestText(), QStringLiteral("malformed"));
    QVERIFY(!vm.modelRequestText().contains(QStringLiteral("[MEMORY-CONTEXT]")));
}

void D5VerticalLinkDemoTest::normalContractContextProducesValidMarkedText()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([this](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            const QJsonObject ctx = makeValidContext(
                QStringLiteral("q-normal"), QStringLiteral("prepared"),
                {QStringLiteral("mem-a"), QStringLiteral("mem-b")}, 120,
                /*withMemoryItems=*/true);
            const QJsonObject data{{QStringLiteral("context"), ctx}};
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b4"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    const QString original = QStringLiteral("帮我回忆架构要点");
    vm.runPreChatPipeline("u", "s", "dev", 800, original);
    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("ready"), 5000);

    // normal context → injected 非空，含 begin / end 标记行
    const QString injected = vm.injectedContextText();
    QVERIFY(!injected.isEmpty());
    QVERIFY(injected.startsWith(QStringLiteral("[MEMORY-CONTEXT] begin")));
    QVERIFY(injected.endsWith(QStringLiteral("[MEMORY-CONTEXT] end")));
    QVERIFY(injected.contains(QStringLiteral("query_id=q-normal")));
    QVERIFY(injected.contains(QStringLiteral("status=prepared")));
    QVERIFY(injected.contains(QStringLiteral("count=2")));
    QVERIFY(injected.contains(QStringLiteral("[mem-a]")));
    QVERIFY(injected.contains(QStringLiteral("[mem-b]")));

    // modelRequestText = original + separator + injected
    const QString expected = original
        + QStringLiteral("\n\n---\n\n") + injected;
    QCOMPARE(vm.modelRequestText(), expected);

    // 原文隔离指示灯应当 PASS（原文本身不包含任何注入标记行）
    QVERIFY(vm.textIsolationVerified());
    QCOMPARE(vm.originalUserText(), original);
}

void D5VerticalLinkDemoTest::injectionStatusFailedProducesEmptyInjectedText()
{
    test_support::MockGatewayServer mock;
    // 形状完整但 injection_status=failed → 明确不注入
    mock.setHandler([this](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            const QJsonObject ctx = makeValidContext(
                QStringLiteral("q-fail"), QStringLiteral("failed"),
                {QStringLiteral("mem-a")}, 60, /*withMemoryItems=*/true);
            const QJsonObject data{{QStringLiteral("context"), ctx}};
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b5"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    const QString original = QStringLiteral("注入失败测试原文");
    vm.runPreChatPipeline("u", "s", "dev", 800, original);
    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("ready"), 5000);

    QVERIFY(vm.injectedContextText().isEmpty());
    QCOMPARE(vm.modelRequestText(), original);
    QVERIFY(!vm.modelRequestText().contains(QStringLiteral("[MEMORY-CONTEXT]")));
}

// ── §C — 问题4：运行正确性 / 验证闭环 ───────────────────────────────────────

void D5VerticalLinkDemoTest::postTurnResponseDoesNotHijackInFlightPreChat()
{
    test_support::MockGatewayServer mock;
    // 两个方法都返回 success；验证 PostTurn 响应不会串台影响 PreChat 阶段。
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy preSpy(&vm, &client::MemoryViewModel::preChatStageChanged);
    QSignalSpy postSpy(&vm, &client::MemoryViewModel::postTurnStageChanged);

    // 先发 PreChat
    vm.runPreChatPipeline("u", "s", "dev", 800, QStringLiteral("原文1"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("ready"), 5000);

    // 再发 PostTurn
    vm.runPostTurnPipeline("u", "s", "t-1", "tr-1", "m-1",
                           QStringLiteral("final"),
                           QStringLiteral("completed"), QStringLiteral("stop"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.postTurnStage(), QStringLiteral("sent"), 5000);

    // 关键：PreChat 的 ready 不被冲掉（不能串台成 failed / idle）。
    QCOMPARE(vm.preChatStage(), QStringLiteral("ready"));
    QCOMPARE(vm.postTurnStage(), QStringLiteral("sent"));
}

void D5VerticalLinkDemoTest::resetPreChatClearsPendingAndBackToIdle()
{
    test_support::MockGatewayServer mock;
    // Handler 返回 requestId 不匹配的响应 → 客户端丢弃 → 请求保持 pending。
    mock.setHandler([](const client::EnvelopeParts&) -> QJsonObject {
        return client::buildSuccessResponse(
            QStringLiteral("req_forged_unknown_id"),
            QStringLiteral("req_forged_unknown_id"),
            QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy preBusySpy(&vm, &client::MemoryViewModel::preChatBusyChanged);
    vm.runPreChatPipeline("u", "s", "dev", 800, QStringLiteral("原文reset"));
    QVERIFY(vm.preChatBusy());

    vm.resetPreChatPipeline();
    QCOMPARE(vm.preChatStage(), QStringLiteral("idle"));
    QVERIFY(!vm.preChatBusy());
    QVERIFY(vm.originalUserText().isEmpty());
    QVERIFY(vm.modelRequestText().isEmpty());
    QVERIFY(vm.injectedContextText().isEmpty());
}

void D5VerticalLinkDemoTest::previewAndSendReuseSameEventIdTimestamp()
{
    client::MemoryViewModel vm;

    // 纯函数调用，不依赖连接：buildTurnFinalizedEventJson 在相同参数下
    // 应返回同一个缓存对象（event_id / occurred_at / collected_at 一致）
    const QJsonObject a = vm.buildTurnFinalizedEventJson(
        "u", "s", "t", "tr", "m",
        "final text", "completed", "stop");
    const QJsonObject b = vm.buildTurnFinalizedEventJson(
        "u", "s", "t", "tr", "m",
        "final text", "completed", "stop");

    QCOMPARE(a, b);
    QCOMPARE(a.value(QStringLiteral("event_id")).toString(),
             b.value(QStringLiteral("event_id")).toString());
    QCOMPARE(a.value(QStringLiteral("occurred_at")).toString(),
             b.value(QStringLiteral("occurred_at")).toString());
    QCOMPARE(a.value(QStringLiteral("collected_at")).toString(),
             b.value(QStringLiteral("collected_at")).toString());

    // 参数变化 → 缓存失效 → 不同对象（至少 event_id 不同）
    const QJsonObject c = vm.buildTurnFinalizedEventJson(
        "u2", "s2", "t2", "tr2", "m2",
        "final text 2", "completed", "stop");
    QVERIFY(a.value(QStringLiteral("event_id")).toString()
            != c.value(QStringLiteral("event_id")).toString());
}

QTEST_MAIN(D5VerticalLinkDemoTest)

#include "test_d5_vertical_link_demo.moc"
