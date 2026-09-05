// ============================================================================
// D13-C 端到端会话评测 · 主演示稳定性复测 L0 Mock 契约测试
// （CANDIDATE / Demo / Prototype）
//
// 范围（S1~S6 共 6 个稳定性 test slot）：
//   S1. stability_replay_5rounds        主演示编排复跑 5 轮稳定性
//   S2. stop_reason_semantics           PostTurn stop_reason 透传语义
//   S3. retry_semantics                 retry_of_turn_id 透传 + 非 retry 必须为空
//   S4. deadline_timeout_client_block   客户端 5000ms deadline timeout fail-closed
//   S5. cross_session_isolation_replay  跨会话隔离复跑（A/B session 反复切换）
//   S6. reset_clears_pending_no_writeback  Reset 清 pending 防 stale response 回写
//
// 重要声明：
//   - 本测试仅为 memory-client 侧 L0 稳定性 Mock 契约验证；
//   - 不代表真实 AI Assistant Hook / Chat DB / ChatRecord / model_request 已接入；
//   - 不关闭 C-D13，也不宣称 Runtime 已在麒麟 VM 验证（L2 由 B/D 轨另行归档）。
// ============================================================================
#include "mock_gateway_server.h"
#include "protocol_adapter.h"
#include "memory_client.h"
#include "view_models/memory_view_model.h"

#include <QObject>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QString>
#include <QStringList>
#include <QTest>
#include <QEventLoop>
#include <QTimer>
#include <QSignalSpy>
#include <QCoreApplication>
#include <QTime>
#include <QDebug>

#include <functional>
#include <memory>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

namespace {

constexpr const char* kUserId    = "local-user";
constexpr const char* kSessionA  = "session-stab-0001";
constexpr const char* kSessionB  = "session-stab-0002";
constexpr const char* kScene     = "software_development";
constexpr const char* kOrigText1 = "帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点";
constexpr const char* kOrigText2 = "提醒我上次提到的 Vector 删除一致性规则";

// ── D5 memory.retrieve：返回一个合法 MemoryContext
//    sessionTag 参与区分 Session A/B，使两者可做正对照。
QJsonObject buildMemoryContext(const QString& sessionTag)
{
    const bool isSessionA = (sessionTag == QLatin1String(kSessionA));
    QJsonArray ids;
    if (isSessionA) {
        ids.append(QStringLiteral("km-pref-001"));
        ids.append(QStringLiteral("km-know-002"));
    } else {
        ids.append(QStringLiteral("km-pref-001"));
        ids.append(QStringLiteral("km-know-002"));
        ids.append(QStringLiteral("km-pref-sessionB-003"));
    }
    QJsonArray ctxItems;
    ctxItems.append(QJsonObject{
        {QStringLiteral("memory_id"), QStringLiteral("km-pref-001")},
        {QStringLiteral("version_id"), QStringLiteral("v1")},
        {QStringLiteral("entry_type"), QStringLiteral("preference")},
        {QStringLiteral("content"), QStringLiteral("用户偏好中文输出 / 80 字摘要")},
        {QStringLiteral("summary"), QStringLiteral("用户偏好中文输出 / 80 字摘要")},
    });
    ctxItems.append(QJsonObject{
        {QStringLiteral("memory_id"), QStringLiteral("km-know-002")},
        {QStringLiteral("version_id"), isSessionA
            ? QStringLiteral("v1") : QStringLiteral("v2")},
        {QStringLiteral("entry_type"), QStringLiteral("knowledge")},
        {QStringLiteral("content"), isSessionA
            ? QStringLiteral("Vector 删除一致性：SQLite→Outbox→Vector 顺序 + 幂等重放")
            : QStringLiteral("[Session-B] Vector 删除一致性：SQLite→Outbox→Vector 顺序 + 幂等重放 + Cascade 外键校验")},
        {QStringLiteral("summary"), isSessionA
            ? QStringLiteral("Vector 删除一致性：SQLite→Outbox→Vector 顺序 + 幂等重放")
            : QStringLiteral("[Session-B] Vector 删除一致性：SQLite→Outbox→Vector 顺序 + 幂等重放 + Cascade 外键校验")},
    });
    if (!isSessionA) {
        ctxItems.append(QJsonObject{
            {QStringLiteral("memory_id"), QStringLiteral("km-pref-sessionB-003")},
            {QStringLiteral("version_id"), QStringLiteral("v1")},
            {QStringLiteral("entry_type"), QStringLiteral("preference")},
            {QStringLiteral("content"), QStringLiteral("[跨会话偏好-SESS-B] editor=Qt Creator / tab_size=2 / output=zh-CN；仅在 session B 请求中出现")},
            {QStringLiteral("summary"), QStringLiteral("[跨会话偏好-SESS-B] editor=Qt Creator / tab_size=2 / output=zh-CN；仅在 session B 请求中出现")},
        });
    }
    return QJsonObject{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("query_id"), isSessionA
            ? QStringLiteral("q-d13c-sess-A")
            : QStringLiteral("q-d13c-sess-B")},
        {QStringLiteral("selected_memory_ids"), ids},
        {QStringLiteral("context_version"), QStringLiteral("1.0")},
        {QStringLiteral("token_budget"), isSessionA ? 800 : 900},
        {QStringLiteral("injection_status"), QStringLiteral("injected")},
        {QStringLiteral("actual_token_count"), isSessionA ? 246 : 358},
        {QStringLiteral("memory_items"), ctxItems},
    };
}

QJsonObject buildConflictCandidates()
{
    QJsonArray arr;
    arr.append(QJsonObject{
        {QStringLiteral("old_entry"), QStringLiteral("km-1")},
        {QStringLiteral("new_entry"), QStringLiteral("km-1-v2")},
        {QStringLiteral("diff_field"), QStringLiteral("vector_threshold")},
        {QStringLiteral("confidence_vs"), 0.88},
    });
    return QJsonObject{{QStringLiteral("candidates"), arr}};
}

QJsonObject buildLifecycleItems()
{
    QJsonArray arr;
    arr.append(QJsonObject{
        {QStringLiteral("memory_id"), QStringLiteral("km-1")},
        {QStringLiteral("memory_status"), QStringLiteral("active")},
        {QStringLiteral("promotion_count"), 3},
        {QStringLiteral("demotion_count"), 0},
    });
    return QJsonObject{{QStringLiteral("items"), arr}};
}

QJsonObject buildForgetPreviewData()
{
    QJsonArray ids;
    ids.append(QStringLiteral("km-1"));
    return QJsonObject{
        {QStringLiteral("user_id"), QLatin1String(kUserId)},
        {QStringLiteral("selection_hash"), QStringLiteral("sha256:demo-d13c-stab")},
        {QStringLiteral("affected_count"), 1},
        {QStringLiteral("credential_ttl_s"), 300},
        {QStringLiteral("confirmation_credential"),
         QStringLiteral("cred-d13c-stab-7f3a-9c2e")},
        {QStringLiteral("forget_mode"), QStringLiteral("single_item")},
        {QStringLiteral("target_type"), QStringLiteral("knowledge")},
        {QStringLiteral("is_cascade"), false},
        {QStringLiteral("selector_cleared"), true},
        {QStringLiteral("resolved_target_ids_preview_snippet"), ids},
    };
}

QJsonObject buildForgetExecuteData()
{
    return QJsonObject{
        {QStringLiteral("executed_count"), 1},
        {QStringLiteral("delete_mode"), QStringLiteral("soft")},
        {QStringLiteral("audit_id"), QStringLiteral("aud-d13c-stab-001")},
    };
}

// ── 辅助：等待 stage 进入目标状态（最多 timeoutMs） ──────────────────
bool waitForStage(std::function<bool()> predicate, int timeoutMs = 5000)
{
    QEventLoop loop;
    QTimer timer;
    timer.setInterval(timeoutMs);
    timer.setSingleShot(true);
    bool ok = false;
    QObject::connect(&timer, &QTimer::timeout, &loop, [&]{ loop.quit(); });
    QTimer poller;
    poller.setInterval(10);
    QObject::connect(&poller, &QTimer::timeout, &loop, [&]{
        if (predicate()) { ok = true; loop.quit(); }
    });
    timer.start();
    poller.start();
    loop.exec();
    return ok;
}

// ── 主演示编排：5 步全流程（PreChat → PostTurn → Tool → Conflict/Lifecycle → Forget）
//    返回 true 表示全部成功完成；任一步失败立即返回 false。
bool runMainDemoOnce(client::MemoryViewModel& vm, int round,
                     const QString& sessionA,
                     const QString& sessionB)
{
    // Step 1-A PreChat
    vm.runPreChatPipeline(
        QLatin1String(kUserId), sessionA, QLatin1String(kScene),
        800, QString::fromUtf8(kOrigText1));
    if (!waitForStage([&]{ return vm.preChatStage() == "ready"; })) return false;

    // Step 1-B PostTurn
    const QString turnId = QStringLiteral("turn-stab-%1").arg(round);
    const QString traceId = QStringLiteral("tr-stab-%1").arg(round);
    vm.runPostTurnPipeline(
        QLatin1String(kUserId), sessionA, turnId, traceId,
        QStringLiteral("msg-stab-%1").arg(round),
        QStringLiteral("final assistant text"), "ended", "stop");
    if (!waitForStage([&]{ return vm.postTurnStage() == "sent"; })) return false;

    // Step 2 cross-session PreChat
    vm.runPreChatPipeline(
        QLatin1String(kUserId), sessionB, QLatin1String(kScene),
        900, QString::fromUtf8(kOrigText2));
    if (!waitForStage([&]{ return vm.preChatStage() == "ready"; })) return false;

    // Step 3 Tool
    vm.runToolPipeline(
        QLatin1String(kUserId), sessionB,
        QStringLiteral("turn-stab-tool-%1").arg(round),
        QStringLiteral("tc-stab-%1").arg(round),
        "memory_search", "success",
        "{}", "{}", "", "", true, false);
    if (!waitForStage([&]{ return vm.toolStage() == "sent"; })) return false;

    // Step 4 Conflict + Lifecycle
    vm.runConflictComparePipeline("km-1", false);
    if (!waitForStage([&]{ return vm.conflictCompareStage() == "ready"; })) return false;
    vm.runLifecycleStatusPipeline(QLatin1String(kUserId), "km-1", {});
    if (!waitForStage([&]{ return vm.lifecycleStatusStage() == "ready"; })) return false;

    // Step 5 Preview + Execute
    const QString planId = QStringLiteral("plan-stab-%1").arg(round);
    vm.runForgetPreviewPipeline(
        QLatin1String(kUserId), planId, "single_item", "knowledge",
        QStringLiteral("selector-stab-%1").arg(round), "km-1",
        "", "", "", true, false);
    if (!waitForStage([&]{ return vm.forgetStage() == "awaiting_confirmation"; })) return false;
    const QString cred = vm.forgetConfirmationCredential();
    if (cred.isEmpty()) return false;
    vm.runForgetExecutePipeline(
        QLatin1String(kUserId), planId, cred, "", "soft");
    if (!waitForStage([&]{ return vm.forgetStage() == "completed"; })) return false;

    return true;
}

}  // namespace

class TestD13CStability : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();

    // S1. 主演示编排复跑 5 轮稳定性
    void s1_stability_replay_5rounds();
    // S2. PostTurn stop_reason 透传语义
    void s2_stop_reason_semantics();
    // S3. retry_of_turn_id 透传 + 非 retry 必须为空
    void s3_retry_semantics();
    // S4. 客户端 5000ms deadline timeout fail-closed
    void s4_deadline_timeout_client_block();
    // S5. 跨会话隔离复跑（A/B session 反复切换）
    void s5_cross_session_isolation_replay();
    // S6. Reset 清 pending 防 stale response 回写
    void s6_reset_clears_pending_no_writeback();

private:
    QString uniqueSocketName(const QString& prefix);
    void installHappyHandlers(test_support::MockGatewayServer& mock);

    std::unique_ptr<test_support::MockGatewayServer> sharedMock_;
    QString sharedSocket_;
};

void TestD13CStability::initTestCase()
{
    sharedMock_ = std::make_unique<test_support::MockGatewayServer>();
    installHappyHandlers(*sharedMock_);
    sharedSocket_ = sharedMock_->listen(uniqueSocketName("shared"));
    QVERIFY2(!sharedSocket_.isEmpty(), "D13C 共享 Mock Gateway 监听失败");
}

void TestD13CStability::cleanupTestCase()
{
    if (sharedMock_) sharedMock_->close();
    sharedMock_.reset();
}

QString TestD13CStability::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d13c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

void TestD13CStability::installHappyHandlers(
    test_support::MockGatewayServer& mock)
{
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            const QString sid = parts.payload.value(
                QStringLiteral("session_id")).toString();
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("context"),
                             buildMemoryContext(sid)}});
        }
        if (parts.method == client::methods::kTurnFinalized) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("turn_id"),
                             parts.payload.value(QStringLiteral("turn_id"))
                                 .toString()},
                            {QStringLiteral("event_id"),
                             QStringLiteral("evt-ok-d13c")}});
        }
        if (parts.method == QLatin1String("tool.execution")) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("tool_call_id"),
                             parts.payload.value(QStringLiteral("tool_call_id"))
                                 .toString()},
                            {QStringLiteral("ingested"), true}});
        }
        if (parts.method == QLatin1String("conflict.compare")) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildConflictCandidates());
        }
        if (parts.method == QLatin1String("lifecycle.status")) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildLifecycleItems());
        }
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildForgetPreviewData());
        }
        if (parts.method == client::methods::kForgetExecute) {
            const QString expectedCred = QStringLiteral("cred-d13c-stab-7f3a-9c2e");
            const QString actualCred = parts.payload.value(
                QStringLiteral("confirmation_token")).toString();
            if (actualCred != expectedCred) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    QStringLiteral("INVALID_CONFIRMATION_CREDENTIAL"),
                    QStringLiteral("Server rejected: credential mismatch or expired."));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildForgetExecuteData());
        }
        if (parts.method == client::methods::kHealth) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{
                    {QStringLiteral("status"), QStringLiteral("ok")},
                    {QStringLiteral("db"), QStringLiteral("ok")},
                });
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
}

// ── S1 · 主演示编排复跑 5 轮稳定性 ─────────────────────────────────────
//
// 验证点：
//   1. 5 轮 5 步全部成功（无 hang、无 stage 错乱）
//   2. 每轮结束 busy=false、forgetSelectorCleared=true、forgetHasMissingDeletes=false
//   3. 5 轮之间 resetAllPipelines() 后 stage 全部 idle
//   4. textIsolationVerified 在所有轮次均为 true
//   5. forgetConfirmationCredential 每轮都被刷新（非空）
void TestD13CStability::s1_stability_replay_5rounds()
{
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }, 1500));

    const int kRounds = 5;
    for (int round = 0; round < kRounds; ++round) {
        const bool ok = runMainDemoOnce(
            vm, round,
            QLatin1String(kSessionA), QLatin1String(kSessionB));
        QVERIFY2(ok,
                 qPrintable(QStringLiteral("D13C-S1 round %1 主演示编排失败")
                                .arg(round)));

        // 每轮结束断言：busy=false、安全护栏通过
        QVERIFY2(!vm.busy(),
                 qPrintable(QStringLiteral("D13C-S1 round %1 busy 未清零")
                                .arg(round)));
        QVERIFY2(vm.textIsolationVerified(),
                 qPrintable(QStringLiteral("D13C-S1 round %1 原文隔离违例")
                                .arg(round)));
        QVERIFY2(vm.forgetSelectorCleared(),
                 qPrintable(QStringLiteral("D13C-S1 round %1 selector 未清除")
                                .arg(round)));
        QVERIFY2(!vm.forgetHasMissingDeletes(),
                 qPrintable(QStringLiteral("D13C-S1 round %1 漏删保护触发")
                                .arg(round)));
        QVERIFY2(!vm.forgetCrossUserBlocked(),
                 qPrintable(QStringLiteral("D13C-S1 round %1 误触跨用户拦截")
                                .arg(round)));

        // 5 路最终 stage 一致性
        QCOMPARE(vm.preChatStage(), QStringLiteral("ready"));
        QCOMPARE(vm.postTurnStage(), QStringLiteral("sent"));
        QCOMPARE(vm.toolStage(), QStringLiteral("sent"));
        QCOMPARE(vm.conflictCompareStage(), QStringLiteral("ready"));
        QCOMPARE(vm.lifecycleStatusStage(), QStringLiteral("ready"));
        QCOMPARE(vm.forgetStage(), QStringLiteral("completed"));

        // 非 last round：resetAllPipelines 后 stage 回 idle
        if (round < kRounds - 1) {
            vm.resetAllPipelines();
            QCOMPARE(vm.preChatStage(), QStringLiteral("idle"));
            QCOMPARE(vm.postTurnStage(), QStringLiteral("idle"));
            QCOMPARE(vm.toolStage(), QStringLiteral("idle"));
            QCOMPARE(vm.conflictCompareStage(), QStringLiteral("idle"));
            QCOMPARE(vm.lifecycleStatusStage(), QStringLiteral("idle"));
            QCOMPARE(vm.forgetStage(), QStringLiteral("idle"));
        }
    }
}

// ── S2 · PostTurn stop_reason 透传语义 ──────────────────────────────────
//
// 验证点：
//   - stop_reason ∈ {"stop","length","content_filter","tool_use","error"}
//     必须原样透传到 metadata.stop_reason
//   - finalization_reason 与 stop_reason 配合：ended/aborted/timeout 等
void TestD13CStability::s2_stop_reason_semantics()
{
    test_support::MockGatewayServer mock;
    QStringList capturedStopReasons;
    QStringList capturedFinalizationReasons;
    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kTurnFinalized) {
            // ADR-010: stop_reason / finalization_reason 在事件顶层，不在 metadata 内
            capturedStopReasons.append(
                parts.payload.value(QStringLiteral("stop_reason")).toString());
            capturedFinalizationReasons.append(
                parts.payload.value(QStringLiteral("finalization_reason")).toString());
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("event_id"),
                             QStringLiteral("evt-s2")}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("s2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // 4 个 stop_reason 覆盖典型语义
    const QStringList stopReasons = {
        "stop", "length", "content_filter", "tool_use"
    };
    const QStringList finalizationReasons = {
        "ended", "truncated", "filtered", "ended"
    };
    for (int i = 0; i < stopReasons.size(); ++i) {
        vm.runPostTurnPipeline(
            QLatin1String(kUserId), QLatin1String(kSessionA),
            QStringLiteral("turn-s2-%1").arg(i),
            QStringLiteral("tr-s2-%1").arg(i),
            QStringLiteral("msg-s2-%1").arg(i),
            QStringLiteral("assistant-text-%1").arg(i),
            finalizationReasons[i], stopReasons[i]);
        QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "sent"; }));
        vm.resetPostTurnPipeline();
        QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "idle"; }));
    }

    QCOMPARE(capturedStopReasons.size(), 4);
    QCOMPARE(capturedStopReasons.at(0), QStringLiteral("stop"));
    QCOMPARE(capturedStopReasons.at(1), QStringLiteral("length"));
    QCOMPARE(capturedStopReasons.at(2), QStringLiteral("content_filter"));
    QCOMPARE(capturedStopReasons.at(3), QStringLiteral("tool_use"));
    QCOMPARE(capturedFinalizationReasons.at(0), QStringLiteral("ended"));
    QCOMPARE(capturedFinalizationReasons.at(1), QStringLiteral("truncated"));
    QCOMPARE(capturedFinalizationReasons.at(2), QStringLiteral("filtered"));
    QCOMPARE(capturedFinalizationReasons.at(3), QStringLiteral("ended"));
}

// ── S3 · retry_of_turn_id 透传 + 非 retry 必须为空 ──────────────────────
//
// 验证点：
//   - 非 retry 路径：retry_of_turn_id 必须为空字符串（不携带）
//   - retry 路径：retry_of_turn_id 必须等于上一次失败的 turn_id
//   - finalization_reason="retry" 时 retryOfTurnId 必须显式提供
void TestD13CStability::s3_retry_semantics()
{
    test_support::MockGatewayServer mock;
    QStringList capturedRetryOfIds;
    QStringList capturedFinalizationReasons;
    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kTurnFinalized) {
            // DRIFT-B fix（rebase main 后契约）：retry_of_turn_id 是
            // TurnFinalizedEvent 事件顶层字段，不在 metadata 嵌套内。
            capturedRetryOfIds.append(
                parts.payload.value(QStringLiteral("retry_of_turn_id")).toString());
            // ADR-010: finalization_reason 在事件顶层
            capturedFinalizationReasons.append(
                parts.payload.value(QStringLiteral("finalization_reason")).toString());
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("event_id"),
                             QStringLiteral("evt-s3")}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("s3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // ① 第一次失败（非 retry）：retry_of_turn_id 必须为空（真实走 IPC）
    vm.runPostTurnPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionA),
        "turn-s3-001", "tr-s3-001", "msg-s3-001",
        "assistant-failed", "ended", "error");
    QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "sent"; }));
    vm.resetPostTurnPipeline();
    QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "idle"; }));

    // ② retry：构造 retry 事件并经生产 MemoryClient::sendRequest 真实发送到 Mock
    const QJsonObject retryEvent = vm.buildTurnFinalizedEventJson(
        QLatin1String(kUserId), QLatin1String(kSessionA),
        "turn-s3-002", "tr-s3-002", "msg-s3-002",
        "assistant-retry", "retry", "stop",
        "turn-s3-001" /* retryOfTurnId */);
    // builder 字段透传（DRIFT-B：retry_of_turn_id/finalization_reason 在事件顶层）
    QCOMPARE(retryEvent.value(QStringLiteral("retry_of_turn_id")).toString(),
             QStringLiteral("turn-s3-001"));
    QCOMPARE(retryEvent.value(QStringLiteral("finalization_reason")).toString(),
             QStringLiteral("retry"));

    client::MemoryClient rawClient;
    rawClient.setSocketPath(socket);
    rawClient.connectToService();
    QVERIFY(waitForStage(
        [&]{ return rawClient.connectionState()
                 == client::MemoryClient::ConnectionState::Connected; }));
    const QString rawRequestId = rawClient.sendRequest(
        client::methods::kTurnFinalized, retryEvent);
    QVERIFY2(!rawRequestId.isEmpty(),
             "D13C-S3 MemoryClient::sendRequest 必须成功发出 retry 请求");
    QVERIFY2(waitForStage([&]{ return capturedFinalizationReasons.size() >= 2; }, 3000),
             qPrintable(QStringLiteral("D13C-S3 retry 未到达 Mock，已收到 %1 条")
                            .arg(capturedFinalizationReasons.size())));

    // ③ 后续非 retry 真实发送：retry_of_turn_id 必须为空
    vm.runPostTurnPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionA),
        "turn-s3-003", "tr-s3-003", "msg-s3-003",
        "assistant-final", "ended", "stop");
    QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "sent"; }));
    QVERIFY2(waitForStage([&]{ return capturedFinalizationReasons.size() >= 3; }, 3000),
             qPrintable(QStringLiteral("D13C-S3 第 3 条请求未到达 Mock，已收到 %1 条")
                            .arg(capturedFinalizationReasons.size())));

    // 最终断言（真实 IPC 捕获顺序：① ended/空 → ② retry/父id → ③ ended/空）
    QCOMPARE(capturedRetryOfIds.size(), 3);
    QCOMPARE(capturedFinalizationReasons.at(0), QStringLiteral("ended"));
    QVERIFY2(capturedRetryOfIds.at(0).isEmpty(),
             "D13C-S3 非 retry 路径 retry_of_turn_id 必须为空");
    QCOMPARE(capturedFinalizationReasons.at(1), QStringLiteral("retry"));
    QCOMPARE(capturedRetryOfIds.at(1), QStringLiteral("turn-s3-001"));
    QVERIFY2(capturedRetryOfIds.at(1) != QStringLiteral("turn-s3-002"),
             "D13C-S3 retry_of_turn_id 不得等于当前 turn id");
    QCOMPARE(capturedFinalizationReasons.at(2), QStringLiteral("ended"));
    QVERIFY2(capturedRetryOfIds.at(2).isEmpty(),
             "D13C-S3 后续非 retry 路径 retry_of_turn_id 必须为空");
}

// ── S4 · 客户端 5000ms deadline timeout fail-closed ─────────────────────
//
// 验证点：
//   - Mock 对 memory.retrieve 不回响应 → 客户端 5000ms deadline timeout
//   - timeout 后 preChatStage=failed/timeout、preChatBusy=false
//   - busy 不会挂死（deadlock-free）
//   - 后续 resetPreChatPipeline 后可重新发起请求（不死锁）
void TestD13CStability::s4_deadline_timeout_client_block()
{
    test_support::MockGatewayServer mock;
    int retrieveCount = 0;
    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            ++retrieveCount;
            // 故意不回响应（__hold__ 让 Mock 不 write 任何字节），触发客户端 deadline timeout
            return QJsonObject{{QStringLiteral("__hold__"), true}};
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("s4"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // 发起 PreChat 请求 → Mock 不回 → 等待 deadline timeout
    QTime t;
    t.start();
    vm.runPreChatPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionA),
        QLatin1String(kScene), 800,
        QString::fromUtf8(kOrigText1));

    // R5：配置断言 —— 实现实际使用的 deadline 默认值必须是冻结的 5000ms
    QVERIFY2(client::kDefaultDeadlineMs == 5000,
             qPrintable(QStringLiteral("D13C-S4 kDefaultDeadlineMs 必须 == 5000，"
                                        "实际=%1")
                            .arg(client::kDefaultDeadlineMs)));

    // 等待进入 failed / timeout 终态（最多 8000ms，留余量给 5000ms deadline）
    const bool reached = waitForStage(
        [&]{ return vm.preChatStage() == "failed"
                || vm.preChatStage() == "timeout"; }, 8000);
    const int elapsed = t.elapsed();

    QVERIFY2(reached,
             qPrintable(QStringLiteral("D13C-S4 deadline timeout 未触发，"
                                       "preChatStage=%1（应进入 failed/timeout）")
                            .arg(vm.preChatStage())));
    // 诊断：输出 stage/error 便于排查
    qDebug() << "D13C-S4: elapsed=" << elapsed << "ms stage=" << vm.preChatStage()
             << "error=" << vm.lastError() << "retrieveCount=" << retrieveCount;
    // R5：行为断言 —— 围绕 5000ms 的 CI 容差窗口（4500ms~6500ms），防止实现回退成
    // 2.1s/3s/10s 超时仍被误判为“5000ms deadline 通过”。
    QVERIFY2(elapsed >= 4500 && elapsed <= 6500,
             qPrintable(QStringLiteral("D13C-S4 deadline 未落在 5000ms 窗口 "
                                        "elapsed=%1ms（期望 4500~6500ms），stage=%2 error=%3")
                            .arg(elapsed).arg(vm.preChatStage()).arg(vm.lastError())));
    QVERIFY2(!vm.preChatBusy(),
             "D13C-S4 timeout 后 preChatBusy 必须为 false（无 hang）");
    QVERIFY2(!vm.busy(),
             "D13C-S4 timeout 后 busy 必须为 false（无死锁）");
    QVERIFY2(retrieveCount >= 1,
             "D13C-S4 必须已发出 memory.retrieve 请求");

    // 后续：reset 后可重新发起（不死锁、可恢复）
    vm.resetPreChatPipeline();
    QCOMPARE(vm.preChatStage(), QStringLiteral("idle"));
    QVERIFY(!vm.preChatBusy());
}

// ── S5 · 跨会话隔离复跑（A/B session 反复切换） ─────────────────────────
//
// 验证点：
//   - 5 轮 A/B 切换：每轮 A→B→A→B 顺序
//   - 每次 A 的 injectedContextText 不含 "SESS-B" 标记
//   - 每次 B 的 injectedContextText 含 "跨会话偏好-SESS-B" 标记
//   - A 与 B 的 injectedContextText 严格不同（防串台）
//   - textIsolationVerified 在所有切换后均为 true
void TestD13CStability::s5_cross_session_isolation_replay()
{
    test_support::MockGatewayServer mock;
    QStringList capturedSessionIds;
    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            const QString sid = parts.payload.value(
                QStringLiteral("session_id")).toString();
            capturedSessionIds.append(sid);
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("context"),
                             buildMemoryContext(sid)}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("s5"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    const int kRounds = 5;
    QString lastInjectedA;
    QString lastInjectedB;
    for (int round = 0; round < kRounds; ++round) {
        // Session A
        vm.runPreChatPipeline(
            QLatin1String(kUserId), QLatin1String(kSessionA),
            QLatin1String(kScene), 800,
            QString::fromUtf8(kOrigText1));
        QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
        const QString injectedA = vm.injectedContextText();
        QVERIFY2(!injectedA.isEmpty(),
                 qPrintable(QStringLiteral("D13C-S5 round %1 A injected 为空")
                                .arg(round)));
        QVERIFY2(!injectedA.contains(QStringLiteral("SESS-B")),
                 qPrintable(QStringLiteral("D13C-S5 round %1 A injected 不应含 SESS-B 标记")
                                .arg(round)));
        QVERIFY2(vm.textIsolationVerified(),
                 qPrintable(QStringLiteral("D13C-S5 round %1 A 原文隔离违例")
                                .arg(round)));
        lastInjectedA = injectedA;

        // Session B
        vm.runPreChatPipeline(
            QLatin1String(kUserId), QLatin1String(kSessionB),
            QLatin1String(kScene), 900,
            QString::fromUtf8(kOrigText2));
        QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
        const QString injectedB = vm.injectedContextText();
        QVERIFY2(!injectedB.isEmpty(),
                 qPrintable(QStringLiteral("D13C-S5 round %1 B injected 为空")
                                .arg(round)));
        QVERIFY2(injectedB.contains(QStringLiteral("跨会话偏好-SESS-B")),
                 qPrintable(QStringLiteral("D13C-S5 round %1 B injected 应含 SESS-B 标记：%1")
                                .arg(injectedB.left(200))));
        QVERIFY2(vm.textIsolationVerified(),
                 qPrintable(QStringLiteral("D13C-S5 round %1 B 原文隔离违例")
                                .arg(round)));
        QVERIFY2(injectedA != injectedB,
                 qPrintable(QStringLiteral("D13C-S5 round %1 A/B injected 串台")
                                .arg(round)));
        lastInjectedB = injectedB;

        vm.resetPreChatPipeline();
    }

    // 跨会话隔离核心：5 轮 A/B 切换，session_id 顺序严格 = A→B→A→B→A→B→A→B→A→B
    QCOMPARE(capturedSessionIds.size(), kRounds * 2);
    for (int i = 0; i < capturedSessionIds.size(); ++i) {
        const bool expectA = (i % 2 == 0);
        QCOMPARE(capturedSessionIds.at(i),
                 expectA ? QString::fromLatin1(kSessionA)
                         : QString::fromLatin1(kSessionB));
    }
}

// ── S6 · Reset 清 pending 防 stale response 回写 ────────────────────────
//
// 验证点：
//   1. 发送 Tool / Conflict / Lifecycle 请求 → busy=true + stage=querying/sending
//      Mock 故意不回响应（捕获 requestId 但不回包）
//   2. 用户点击 reset → cancel deadline timer + clear pendingXxxRequestId_
//      + stage=idle
//   3. 旧响应延迟到达（通过 sendRawEnvelope 注入）→ onResponseReceived
//      发现 pending 已空 → 不匹配 → stage 保持 idle（不被回写为 sent/ready）
//
// 关键：必须在 Mock 未响应、仍 busy=true 时 reset，才能真正证明竞态修复。
void TestD13CStability::s6_reset_clears_pending_no_writeback()
{
    test_support::MockGatewayServer mock;
    QString toolRequestId;
    QString toolTraceId;
    bool toolCaptured = false;

    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == QLatin1String("tool.execution")) {
            toolRequestId = parts.requestId;
            toolTraceId = parts.traceId;
            toolCaptured = true;
            // 故意不回响应（__hold__ 让 Mock 不 write 任何字节），制造 in-flight 竞态
            return QJsonObject{{QStringLiteral("__hold__"), true}};
        }
        // 其他方法走 happy 路径
        if (parts.method == client::methods::kMemoryRetrieve) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("context"),
                             buildMemoryContext(QLatin1String(kSessionA))}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("s6"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // ① 发起 Tool 请求 → Mock 捕获但不回包 → busy=true
    vm.runToolPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionA),
        "turn-s6-001", "tc-s6-001", "memory_search", "success",
        "{}", "{}", "", "", true, false);

    // 等待 Mock 捕获到请求（最多 1500ms）
    QVERIFY(waitForStage([&]{ return toolCaptured; }, 1500));
    QVERIFY2(!toolRequestId.isEmpty(),
             "D13C-S6 Mock 必须捕获到 tool.execution 请求");
    QVERIFY2(vm.toolBusy(),
             "D13C-S6 Mock 未回响应时 toolBusy 必须为 true");
    QVERIFY2(vm.toolStage() == QStringLiteral("sending")
                || vm.toolStage() == QStringLiteral("querying"),
             qPrintable(QStringLiteral("D13C-S6 Mock 未回响应时 toolStage 必须为 sending/querying，实际=%1")
                            .arg(vm.toolStage())));

    // ② 用户点击 reset → 清 pending + cancel deadline timer
    vm.resetToolPipeline();
    QCOMPARE(vm.toolStage(), QStringLiteral("idle"));
    QVERIFY(!vm.toolBusy());

    // ③ 等待 100ms 确保 reset 完成后再注入 stale response
    QTest::qWait(100);

    // ④ 通过 sendRawEnvelope 注入延迟 stale response（requestId 与 pending 不匹配）
    //    客户端应不回写 stage（保持 idle）
    const QJsonObject staleResponse = client::buildSuccessResponse(
        toolRequestId, toolTraceId,
        QJsonObject{{QStringLiteral("tool_call_id"), QStringLiteral("tc-s6-001")},
                    {QStringLiteral("ingested"), true}});
    QVERIFY2(mock.sendRawEnvelope(staleResponse),
             "D13C-S6 sendRawEnvelope 注入 stale response 失败（无活动连接）");

    // ⑤ 等待 500ms 观察 stage 是否被回写
    QTest::qWait(500);

    // 关键断言：stage 必须保持 idle（不被 stale response 回写为 sent）
    QVERIFY2(vm.toolStage() == QStringLiteral("idle"),
             qPrintable(QStringLiteral("D13C-S6 stale response 必须被丢弃，"
                                       "toolStage 应保持 idle，实际=%1")
                            .arg(vm.toolStage())));
    QVERIFY2(!vm.toolBusy(),
             "D13C-S6 stale response 不得触发 busy=true");
}

QTEST_GUILESS_MAIN(TestD13CStability)
#include "test_d13c_stability.moc"
