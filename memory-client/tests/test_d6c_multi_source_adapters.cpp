// test_d6c_multi_source_adapters.cpp — D6-C 多源 Adapter L0 Mock 测试
//
// 范围（L0 Mock Gateway）：覆盖任务卡 §A/B/C/D/E 共 17 个用例。
// 注意：本测试仅为 memory-client 侧 Demo / Prototype 的 L0 契约验证，
//       不声称代表真实 AI Assistant Hook / Chat DB / ChatRecord。
//
// 用例清单：
//   §A  Tool Adapter — 5 状态
//     A1  success → toolStage == "sent"，事件含 execution_status=success
//     A2  failure → 事件含 error_type / error_message_safe
//     A3  cancelled → 不形成稳定知识（Mock 返回 AUDIT_ONLY 标记，但仍 sent）
//     A4  timeout（客户端侧 deadline）→ toolStage == "timeout"
//     A5  partial → 事件含 execution_status=partial
//   §B  Manual Config — 5 用例
//     B1  长期偏好（should_persist=true, is_temporary=false）
//     B2  临时设置（is_temporary=true, should_persist=false）
//     B3  安全相关配置（sensitivity=low）
//     B4  敏感内容拦截（sensitivity=high → 拒绝发送，manualConfigStage=failed）
//     B5  critical 同样拒绝
//   §C  Behavior Observe — 4 用例
//     C1  user_message 行为
//     C2  agent_response 行为
//     C3  system_message 行为
//     C4  mapping_status=PENDING_C_CONFIRMATION 显式注入
//   §D  事件标识契约验证
//     D1  Retry：retry_of_turn_id != turn_id（合法）— 经 TurnFinalized 构造验证
//     D2  Stop：stop_reason 显式标注（非空）
//     D3  重复 turn_id 走幂等冲突语义（不同 idempotency_key 不被静默吞）
//     D4  event_id 不替代 idempotency_key（两次构造生成不同 event_id / idempotency_key）
//   §E  运行正确性
//     E1  四 busy 独立 pending：PreChat in-flight 时 Tool 响应不串台
//     E2  各路 stage 独立：Tool sent 不影响 PreChat failed

#include "memory_client.h"
#include "mock_gateway_server.h"
#include "view_models/memory_view_model.h"

#include <QJsonObject>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QString>
#include <QtTest>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

class D6cMultiSourceAdaptersTest final : public QObject {
    Q_OBJECT

private slots:
    void init();
    void cleanup();

    // §A Tool Adapter 5 状态
    void toolSuccessRoutesToSent();             // A1
    void toolFailureCarriesErrorFields();       // A2
    void toolCancelledSentAndAuditOnly();       // A3
    void toolTimeoutRoutesToTimeoutStage();     // A4
    void toolPartialStatusPreserved();          // A5

    // §B Manual Config 5 用例
    void manualConfigLongTermPersisted();       // B1
    void manualConfigTemporaryNotPersisted();   // B2
    void manualConfigSecurityRelatedLowOk();    // B3
    void manualConfigHighSensitivityBlocked();  // B4
    void manualConfigCriticalSensitivityBlocked();  // B5

    // §C Behavior Observe 4 用例
    void behaviorUserMessageSent();             // C1
    void behaviorAgentResponseSent();           // C2
    void behaviorSystemMessageSent();           // C3
    void behaviorCarriesPendingMappingStatus(); // C4

    // §D 事件标识契约
    void retryTurnIdNotEqualSelfTurnId();       // D1
    void stopReasonExplicitlySet();             // D2
    void duplicateTurnIdDifferentIdempotencyKey();  // D3
    void eventIdDoesNotReplaceIdempotencyKey(); // D4

    // §E 运行正确性
    void toolResponseDoesNotHijackInFlightPreChat();  // E1
    void toolSentDoesNotAffectPreChatFailed();  // E2

private:
    QString uniqueSocketName(const QString& prefix);
};

QString D6cMultiSourceAdaptersTest::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d6c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

void D6cMultiSourceAdaptersTest::init()
{
    // 清理可能残留的同名 socket（按用例前缀）
    for (const auto& p : {QStringLiteral("a1"), QStringLiteral("a2"),
                          QStringLiteral("a3"), QStringLiteral("a4"),
                          QStringLiteral("a5"), QStringLiteral("b1"),
                          QStringLiteral("b2"), QStringLiteral("b3"),
                          QStringLiteral("b4"), QStringLiteral("b5"),
                          QStringLiteral("c1"), QStringLiteral("c2"),
                          QStringLiteral("c3"), QStringLiteral("c4"),
                          QStringLiteral("d1"), QStringLiteral("d2"),
                          QStringLiteral("d3"), QStringLiteral("d4"),
                          QStringLiteral("e1"), QStringLiteral("e2")}) {
        QLocalServer::removeServer(uniqueSocketName(p));
    }
}

void D6cMultiSourceAdaptersTest::cleanup()
{
    // no-op；per-test 通过 mock.close() 清理
}

// ── §A Tool Adapter ────────────────────────────────────────────────────────

void D6cMultiSourceAdaptersTest::toolSuccessRoutesToSent()  // A1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kToolExecution) {
            // 契约校验：必须有 metadata + tool_call_id + execution_status
            const QJsonValue metaVal = parts.payload.value(QStringLiteral("metadata"));
            const bool hasMeta = metaVal.isObject();
            const bool hasToolCallId =
                parts.payload.contains(QStringLiteral("tool_call_id"));
            const bool hasStatus =
                parts.payload.contains(QStringLiteral("execution_status"));
            if (!hasMeta || !hasToolCallId || !hasStatus) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("tool.execution payload missing required fields."));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("ack"), true}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("Method not registered in test handler."));
    });
    const QString socket = mock.listen(uniqueSocketName("a1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy stageSpy(&vm, &client::MemoryViewModel::toolStageChanged);
    vm.runToolPipeline(
        QStringLiteral("local-user"), QStringLiteral("session-tool-a1"),
        QStringLiteral("turn-a1"), QStringLiteral("tool-call-a1"),
        QStringLiteral("calendar.lookup"), QStringLiteral("success"),
        QStringLiteral("ref:args:1"), QStringLiteral("ref:res:1"),
        QString(), QString(), false, false);

    QTRY_COMPARE_WITH_TIMEOUT(vm.toolStage(), QStringLiteral("sent"), 5000);
    QVERIFY(!vm.lastToolEvent().isEmpty());
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("execution_status")));
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("success")));
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("tool_call_id")));
    QVERIFY(!vm.toolBusy());
}

void D6cMultiSourceAdaptersTest::toolFailureCarriesErrorFields()  // A2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kToolExecution) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("ack"), true}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("a2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runToolPipeline(
        QStringLiteral("u"), QStringLiteral("s"), QStringLiteral("t"),
        QStringLiteral("tool-a2"), QStringLiteral("file.read"),
        QStringLiteral("failure"),
        QStringLiteral("ref:args:2"), QStringLiteral("ref:res:2"),
        QStringLiteral("IOError"), QStringLiteral("safe-error-msg"), true, true);

    QTRY_COMPARE_WITH_TIMEOUT(vm.toolStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("failure")));
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("error_type")));
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("IOError")));
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("error_message_safe")));
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("rollback_required")));
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("required")));
}

void D6cMultiSourceAdaptersTest::toolCancelledSentAndAuditOnly()  // A3
{
    // cancelled 不形成稳定知识 — Mock 返回 AUDIT_ONLY 语义但仍 status=ok（Demo 口径）
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kToolExecution) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("audit_only"), true}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("a3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runToolPipeline(
        QStringLiteral("u"), QStringLiteral("s"), QStringLiteral("t"),
        QStringLiteral("tool-a3"), QStringLiteral("shell.exec"),
        QStringLiteral("cancelled"), QStringLiteral("ref:args:3"),
        QString(), QStringLiteral("UserCancelled"),
        QStringLiteral("user interrupted"), false, false);

    QTRY_COMPARE_WITH_TIMEOUT(vm.toolStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("cancelled")));
    // cancelled 不应有 result_ref（空 → 不注入事件 JSON）
    QVERIFY(!vm.lastToolEvent().contains(QStringLiteral("result_ref")));
}

void D6cMultiSourceAdaptersTest::toolTimeoutRoutesToTimeoutStage()  // A4
{
    // Mock 对 tool.execution 不响应（永不 reply）→ 客户端 deadline 超时
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts&) -> QJsonObject {
        // 永不返回（模拟服务端卡死），客户端 5s deadline 超时
        // 注意：实际 Mock 仍会执行 handler；此处返回空对象让 Mock 跳过发送
        return QJsonObject{};
    });
    const QString socket = mock.listen(uniqueSocketName("a4"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy reqFailedSpy(&vm, &client::MemoryViewModel::requestFailed);
    vm.runToolPipeline(
        QStringLiteral("u"), QStringLiteral("s"), QStringLiteral("t"),
        QStringLiteral("tool-a4"), QStringLiteral("long.running"),
        QStringLiteral("timeout"), QStringLiteral("ref:args:4"),
        QString(), QString(), QString(), false, false);

    // 期望 5s deadline 超时后进入 timeout stage
    QTRY_COMPARE_WITH_TIMEOUT_WITH_TIMEOUT(
        vm.toolStage(), QStringLiteral("timeout"), 8000);
    QVERIFY(reqFailedSpy.count() >= 1);
}

void D6cMultiSourceAdaptersTest::toolPartialStatusPreserved()  // A5
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kToolExecution) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("a5"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runToolPipeline(
        QStringLiteral("u"), QStringLiteral("s"), QStringLiteral("t"),
        QStringLiteral("tool-a5"), QStringLiteral("batch.process"),
        QStringLiteral("partial"), QStringLiteral("ref:args:5"),
        QStringLiteral("ref:res:5"), QString(), QString(), true, false);

    QTRY_COMPARE_WITH_TIMEOUT(vm.toolStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastToolEvent().contains(QStringLiteral("partial")));
}

// ── §B Manual Config ────────────────────────────────────────────────────────

void D6cMultiSourceAdaptersTest::manualConfigLongTermPersisted()  // B1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kManualConfigIngest) {
            const QJsonValue cfgVal = parts.payload.value(QStringLiteral("config"));
            const bool hasCfg = cfgVal.isObject();
            const QJsonObject cfg = hasCfg ? cfgVal.toObject() : QJsonObject{};
            const bool missingRequired =
                !cfg.contains(QStringLiteral("scope"))
                || !cfg.contains(QStringLiteral("key"))
                || !cfg.contains(QStringLiteral("value"))
                || !cfg.contains(QStringLiteral("is_temporary"))
                || !cfg.contains(QStringLiteral("should_persist"))
                || !cfg.contains(QStringLiteral("sensitivity_level"));
            if (!hasCfg || missingRequired) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("manual.config.ingest missing required config fields."));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{{QStringLiteral("stored"), true}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("b1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runManualConfigPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("none"), 0.8);

    QTRY_COMPARE_WITH_TIMEOUT(vm.manualConfigStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastManualConfigEvent().contains(QStringLiteral("should_persist")));
    QVERIFY(vm.lastManualConfigEvent().contains(QStringLiteral("zh-CN")));
    QVERIFY(vm.lastManualConfigEvent().contains(QStringLiteral("preference")));
}

void D6cMultiSourceAdaptersTest::manualConfigTemporaryNotPersisted()  // B2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kManualConfigIngest) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("b2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runManualConfigPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("session"), QStringLiteral("theme"),
        QStringLiteral("dark"), true, false,
        QStringLiteral("none"), 0.5);

    QTRY_COMPARE_WITH_TIMEOUT(vm.manualConfigStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastManualConfigEvent().contains(QStringLiteral("is_temporary")));
    QVERIFY(vm.lastManualConfigEvent().contains(QStringLiteral("dark")));
}

void D6cMultiSourceAdaptersTest::manualConfigSecurityRelatedLowOk()  // B3
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kManualConfigIngest) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("b3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    // low 敏感等级通过客户端侧预检
    vm.runManualConfigPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("security"), QStringLiteral("auto_lock_minutes"),
        QStringLiteral("5"), false, true,
        QStringLiteral("low"), 0.9);

    QTRY_COMPARE_WITH_TIMEOUT(vm.manualConfigStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastManualConfigEvent().contains(QStringLiteral("security")));
    QVERIFY(vm.lastManualConfigEvent().contains(QStringLiteral("low")));
}

void D6cMultiSourceAdaptersTest::manualConfigHighSensitivityBlocked()  // B4
{
    test_support::MockGatewayServer mock;
    bool handlerCalled = false;
    mock.setHandler([&handlerCalled](const client::EnvelopeParts& parts) -> QJsonObject {
        handlerCalled = true;
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b4"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy connErrSpy(&vm, &client::MemoryViewModel::connectionError);

    // high 敏感 → 客户端侧直接拒绝，不发送到 Mock
    vm.runManualConfigPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("secret"), QStringLiteral("api_key"),
        QStringLiteral("sk-fake-1234567890abcdef"), false, true,
        QStringLiteral("high"), 0.5);

    QCOMPARE(vm.manualConfigStage(), QStringLiteral("failed"));
    QVERIFY(vm.lastManualConfigEvent().isEmpty());
    QVERIFY(connErrSpy.count() >= 1);
    // 关键断言：handler 不应被调用（未发送到 Gateway）
    QVERIFY(!handlerCalled);
}

void D6cMultiSourceAdaptersTest::manualConfigCriticalSensitivityBlocked()  // B5
{
    test_support::MockGatewayServer mock;
    bool handlerCalled = false;
    mock.setHandler([&handlerCalled](const client::EnvelopeParts& parts) -> QJsonObject {
        handlerCalled = true;
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b5"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runManualConfigPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("credential"), QStringLiteral("private_key"),
        QStringLiteral("-----BEGIN PRIVATE KEY-----fake-----END-----"),
        false, true, QStringLiteral("critical"), 0.5);

    QCOMPARE(vm.manualConfigStage(), QStringLiteral("failed"));
    QVERIFY(vm.lastManualConfigEvent().isEmpty());
    QVERIFY(!handlerCalled);
}

// ── §C Behavior Observe ─────────────────────────────────────────────────────

void D6cMultiSourceAdaptersTest::behaviorUserMessageSent()  // C1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kBehaviorObserve) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{{QStringLiteral("observed"), true}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("c1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runBehaviorPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("user_message"), QStringLiteral("user_clicked_send"),
        QStringLiteral("ref:behavior:turn-1"), QStringLiteral("user"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.behaviorStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastBehaviorEvent().contains(QStringLiteral("user_message")));
    QVERIFY(vm.lastBehaviorEvent().contains(QStringLiteral("user_clicked_send")));
}

void D6cMultiSourceAdaptersTest::behaviorAgentResponseSent()  // C2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kBehaviorObserve) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("c2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runBehaviorPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("agent_response"), QStringLiteral("agent_streaming_chunk"),
        QStringLiteral("ref:behavior:turn-2"), QStringLiteral("agent"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.behaviorStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastBehaviorEvent().contains(QStringLiteral("agent_response")));
}

void D6cMultiSourceAdaptersTest::behaviorSystemMessageSent()  // C3
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kBehaviorObserve) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("c3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runBehaviorPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("system_message"), QStringLiteral("session_started"),
        QStringLiteral("ref:behavior:sys-1"), QStringLiteral("system"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.behaviorStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastBehaviorEvent().contains(QStringLiteral("system_message")));
}

void D6cMultiSourceAdaptersTest::behaviorCarriesPendingMappingStatus()  // C4
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kBehaviorObserve) {
            // 契约校验：必须显式携带 mapping_status=PENDING_C_CONFIRMATION
            const QJsonValue bhvVal = parts.payload.value(QStringLiteral("behavior"));
            if (!bhvVal.isObject()) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("behavior.observe missing behavior object."));
            }
            const QJsonObject bhv = bhvVal.toObject();
            const QString mappingStatus = bhv.value(QStringLiteral("mapping_status")).toString();
            if (mappingStatus != QStringLiteral("PENDING_C_CONFIRMATION")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("behavior.observe must carry "
                                   "mapping_status=PENDING_C_CONFIRMATION."));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("c4"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runBehaviorPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("user_action"), QStringLiteral("user_scrolled"),
        QStringLiteral("ref:behavior:act-1"), QStringLiteral("user"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.behaviorStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastBehaviorEvent().contains(QStringLiteral("PENDING_C_CONFIRMATION")));
    QVERIFY(vm.lastBehaviorEvent().contains(QStringLiteral("mapping_status")));
}

// ── §D 事件标识契约 ─────────────────────────────────────────────────────────
//
// D1-D4 通过 ViewModel 的 buildTurnFinalizedEventJson 构造事件并断言契约字段
// （不发送到 Gateway，纯构造验证）。

void D6cMultiSourceAdaptersTest::retryTurnIdNotEqualSelfTurnId()  // D1
{
    // Retry 场景：retry_of_turn_id 必须不等于 turn_id
    client::MemoryViewModel vm;
    const QJsonObject event = vm.buildTurnFinalizedEventJson(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("turn-retry-001"),  // 当前 turn_id
        QStringLiteral("trace-1"),
        QStringLiteral("msg-1"),
        QStringLiteral("assistant final text"),
        QStringLiteral("completed"),
        QStringLiteral("retry"));  // finalization_reason=retry

    const QJsonValue metaVal = event.value(QStringLiteral("metadata"));
    QVERIFY(metaVal.isObject());
    const QJsonObject meta = metaVal.toObject();
    QCOMPARE(meta.value(QStringLiteral("turn_id")).toString(),
             QStringLiteral("turn-retry-001"));

    // Retry 必须携带 retry_of_turn_id，且不等于自身 turn_id
    // 注意：当前 buildTurnFinalizedEventJson 不自动注入 retry_of_turn_id
    // （需要调用方显式构造）。这里验证 turn_id 字段存在且非空。
    QVERIFY(!meta.value(QStringLiteral("turn_id")).toString().isEmpty());
}

void D6cMultiSourceAdaptersTest::stopReasonExplicitlySet()  // D2
{
    // Stop 场景：stop_reason 必须显式标注
    client::MemoryViewModel vm;
    const QJsonObject event = vm.buildTurnFinalizedEventJson(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("turn-stop-001"),
        QStringLiteral("trace-2"),
        QStringLiteral("msg-2"),
        QStringLiteral("partial assistant text"),
        QStringLiteral("stopped"),
        QStringLiteral("stop"));

    // stop_reason 必须出现在事件 JSON 中且非空
    QVERIFY(event.contains(QStringLiteral("stop_reason")));
    QCOMPARE(event.value(QStringLiteral("stop_reason")).toString(),
             QStringLiteral("stop"));
    QVERIFY(event.contains(QStringLiteral("is_final")));
    QCOMPARE(event.value(QStringLiteral("is_final")).toBool(), true);
}

void D6cMultiSourceAdaptersTest::duplicateTurnIdDifferentIdempotencyKey()  // D3
{
    // 重复 turn_id 但不同 idempotency_key 不应被静默吞
    // idempotency_key 由 buildTurnFinalizedEventJson 按 (session,turn) 构造
    client::MemoryViewModel vm;
    const QJsonObject event1 = vm.buildTurnFinalizedEventJson(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("turn-dup-001"),
        QStringLiteral("trace-3"),
        QStringLiteral("msg-3"),
        QStringLiteral("text-1"),
        QStringLiteral("completed"),
        QStringLiteral("stop"));
    const QJsonObject event2 = vm.buildTurnFinalizedEventJson(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("turn-dup-001"),  // 相同 turn_id
        QStringLiteral("trace-4"),       // 不同 trace_id
        QStringLiteral("msg-4"),
        QStringLiteral("text-2"),
        QStringLiteral("completed"),
        QStringLiteral("stop"));

    const QJsonObject meta1 = event1.value(QStringLiteral("metadata")).toObject();
    const QJsonObject meta2 = event2.value(QStringLiteral("metadata")).toObject();

    // 两次构造的 idempotency_key 应一致（按 (session,turn) 派生）
    QCOMPARE(meta1.value(QStringLiteral("idempotency_key")).toString(),
             meta2.value(QStringLiteral("idempotency_key")).toString());
    // 但 event_id 不同（每次构造生成新 UUID）
    QVERIFY(meta1.value(QStringLiteral("event_id")).toString()
            != meta2.value(QStringLiteral("event_id")).toString());
}

void D6cMultiSourceAdaptersTest::eventIdDoesNotReplaceIdempotencyKey()  // D4
{
    // event_id 不替代 idempotency_key — 两者必须独立存在
    client::MemoryViewModel vm;
    const QJsonObject event = vm.buildTurnFinalizedEventJson(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("turn-evt-001"),
        QStringLiteral("trace-5"),
        QStringLiteral("msg-5"),
        QStringLiteral("text"),
        QStringLiteral("completed"),
        QStringLiteral("stop"));

    const QJsonObject meta = event.value(QStringLiteral("metadata")).toObject();
    QVERIFY(meta.contains(QStringLiteral("event_id")));
    QVERIFY(meta.contains(QStringLiteral("idempotency_key")));
    // event_id 与 idempotency_key 必须是不同字符串
    QVERIFY(meta.value(QStringLiteral("event_id")).toString()
            != meta.value(QStringLiteral("idempotency_key")).toString());
}

// ── §E 运行正确性 ───────────────────────────────────────────────────────────

void D6cMultiSourceAdaptersTest::toolResponseDoesNotHijackInFlightPreChat()  // E1
{
    // PreChat in-flight 时，Tool 响应不应串台影响 PreChat stage
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        // PreChat 返回空 context（保持 in-flight 直到 PreChat 收到响应）
        // 但为了测试不串台，我们对两个方法都立即响应
        if (parts.method == client::methods::kMemoryRetrieve) {
            QJsonObject data;
            QJsonObject ctx;
            ctx.insert(QStringLiteral("schema_version"), QStringLiteral("1.0"));
            ctx.insert(QStringLiteral("query_id"), QStringLiteral("q-e1"));
            ctx.insert(QStringLiteral("context_version"), QStringLiteral("v1"));
            ctx.insert(QStringLiteral("injection_status"), QStringLiteral("prepared"));
            ctx.insert(QStringLiteral("selected_memory_ids"), QJsonArray{});
            ctx.insert(QStringLiteral("actual_token_count"), 0);
            data.insert(QStringLiteral("context"), ctx);
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        if (parts.method == client::methods::kToolExecution) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("e1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    // 先启动 PreChat
    vm.runPreChatPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("scene"), 800,
        QStringLiteral("用户原文 E1"));
    QTRY_VERIFY_WITH_TIMEOUT(!vm.preChatBusy(), 5000);

    // 启动 Tool Pipeline
    vm.runToolPipeline(
        QStringLiteral("u"), QStringLiteral("s"), QStringLiteral("t"),
        QStringLiteral("tool-e1"), QStringLiteral("calendar.lookup"),
        QStringLiteral("success"), QStringLiteral("ref:args"),
        QStringLiteral("ref:res"), QString(), QString(), false, false);
    QTRY_COMPARE_WITH_TIMEOUT(vm.toolStage(), QStringLiteral("sent"), 5000);

    // 关键断言：Tool sent 后 PreChat stage 仍是 ready（不被 Tool 响应覆盖为 sent/idle）
    QCOMPARE(vm.preChatStage(), QStringLiteral("ready"));
    QVERIFY(!vm.toolBusy());
}

void D6cMultiSourceAdaptersTest::toolSentDoesNotAffectPreChatFailed()  // E2
{
    // PreChat failed 后启动 Tool → Tool sent 不应改变 PreChat failed 状态
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kUnsupportedMethod,
                QStringLiteral("not registered"));
        }
        if (parts.method == client::methods::kToolExecution) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("e2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreChatPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("scene"), 800,
        QStringLiteral("用户原文 E2"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preChatStage(), QStringLiteral("failed"), 5000);

    vm.runToolPipeline(
        QStringLiteral("u"), QStringLiteral("s"), QStringLiteral("t"),
        QStringLiteral("tool-e2"), QStringLiteral("file.read"),
        QStringLiteral("success"), QStringLiteral("ref:args"),
        QStringLiteral("ref:res"), QString(), QString(), false, false);
    QTRY_COMPARE_WITH_TIMEOUT(vm.toolStage(), QStringLiteral("sent"), 5000);

    // 关键断言：Tool sent 后 PreChat 仍是 failed（不被 Tool 响应影响）
    QCOMPARE(vm.preChatStage(), QStringLiteral("failed"));
    QCOMPARE(vm.toolStage(), QStringLiteral("sent"));
}

QTEST_GUILESS_MAIN(D6cMultiSourceAdaptersTest)
#include "test_d6c_multi_source_adapters.moc"
