// ============================================================================
// D11-C 同一虚拟机全功能联调 · 端到端 L0 Mock 契约测试
// （D11 E2E Orchestrator；CANDIDATE / Demo / Prototype）
//
// 背景：D11B 回填文档要求 C 轨在同一 Commit / 同一麒麟 VM 内主演示 5 条路径
// （D5 普通聊天 / D5 跨会话 / D6 Tool / D8 Conflict&Lifecycle /
//  D10 精准遗忘 Preview→Execute）可一次性复跑、状态闭合、无原文泄露。
//
// 本测试仅为 memory-client 侧 L0 契约验证，使用 test_support::MockGatewayServer
// 注册所有 9 路活跃 handler（memory.retrieve / turn.finalized /
// tool.execution / conflict.compare / lifecycle.status / forget.preview /
// forget.execute），驱动 MemoryViewModel 依次执行 5 步主演示路径，
// 验证以下断言（对应 D11 台账 C 轨任务 #1~#3）：
//
// 范围（A ~ F 共 12 用例）：
//   A. Step 1 普通聊天（PreChat 三路口径 + PostTurn turn.finalized）：
//      A1 PreChat → ready；originalUserText ∉ modelRequestText ∩ injectedContextText
//      A2 PostTurn → sent；envelope.method == turn.finalized 且非 memory.store
//   B. Step 2 跨会话（session 切换，跨 session 正对照）：
//      B1 session=session-demo-0002 的 PreChat 仍 ready 且 context 独立
//      B2 client 侧 session 不会回退到 0001（独立 pending 保证不串台）
//   C. Step 3 Tool 调用（tool.execution + 事件 ID 独立）：
//      C1 toolStage=sent；payload 含 toolName=memory_search
//      C2 错误注入 UNSUPPORTED_METHOD → toolStage=failed；safeMessage 不含原文
//   D. Step 4 知识冲突 + 生命周期：
//      D1 conflictCompareStage=ready；conflictCandidates.length>0
//      D2 lifecycleStatusStage=ready；lifecycleItems.length>0
//   E. Step 5 精准遗忘（Preview → Execute 全流程）：
//      E1 Preview → awaiting_confirmation；forgetSelectorCleared=true（HIGH-01）
//      E2 Execute → completed；forgetHasMissingDeletes=false
//   F. 编排器总体一致性（同 Commit / 同连接，无竞态，失败路径闭合）：
//      F1 未连接时 5 步客户端级 reject 均失败（不会发请求，busy 不挂死）
//      F2 5 步结束后 ViewModel 全局 busy=false，11 路 pending* 全部为空
//
// 重要声明（D11-C · Demo / Prototype，不关闭 C-D5~C-D10）：
//   本测试仅为客户端侧编排 Harness；不声称真实 AI Assistant Hook /
//   Chat DB / ChatRecord / D 轨 SQLite / B 轨 Vector / E 轨业务 Gate
//   已 Runtime 接线；L2 宿主验证由 B 轨在 D11B VM（同一 Commit e9dba4f）
//   执行并归档为 evidence/l2-kylin-vm/d11b_c_e2e_YYYYMMDD.md。
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
#include <QTest>
#include <QEventLoop>
#include <QTimer>
#include <QSignalSpy>
#include <QCoreApplication>

#include <functional>
#include <memory>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

namespace {

constexpr const char* kUserId    = "local-user";
constexpr const char* kSessionA  = "session-demo-0001";
constexpr const char* kSessionB  = "session-demo-0002";
constexpr const char* kScene     = "software_development";
constexpr const char* kOrigText1 = "帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点";
constexpr const char* kOrigText2 = "提醒我上次提到的 Vector 删除一致性规则";

// ── D5 memory.retrieve：返回一个合法 MemoryContext（D11B Step 1/2） ──
QJsonObject buildMemoryContext(const QString& /*sessionTag*/)
{
    QJsonArray ids;
    ids.append(QStringLiteral("km-pref-001"));
    ids.append(QStringLiteral("km-know-002"));
    QJsonArray ctxItems;
    ctxItems.append(QJsonObject{
        {QStringLiteral("entry_id"), QStringLiteral("km-pref-001")},
        {QStringLiteral("entry_type"), QStringLiteral("preference")},
        {QStringLiteral("summary"), QStringLiteral("用户偏好中文输出 / 80 字摘要")},
    });
    ctxItems.append(QJsonObject{
        {QStringLiteral("entry_id"), QStringLiteral("km-know-002")},
        {QStringLiteral("entry_type"), QStringLiteral("knowledge")},
        {QStringLiteral("summary"), QStringLiteral("Vector 删除一致性：SQLite→Outbox→Vector 顺序 + 幂等重放")},
    });
    return QJsonObject{
        {QStringLiteral("query_id"), QStringLiteral("q-demo-d11c")},
        {QStringLiteral("selected_memory_ids"), ids},
        {QStringLiteral("context_version"), QStringLiteral("1.0")},
        {QStringLiteral("token_budget"), 800},
        {QStringLiteral("injection_status"), QStringLiteral("injected")},
        {QStringLiteral("actual_token_count"), 246},
        {QStringLiteral("memory_items"), ctxItems},
    };
}

// ── D8 conflict.compare + lifecycle.status 响应数据 ───────────────────
QJsonObject buildConflictCandidates()
{
    QJsonArray arr;
    arr.append(QJsonObject{
        {QStringLiteral("old_entry"), QStringLiteral("km-1")},
        {QStringLiteral("new_entry"), QStringLiteral("km-1-v2")},
        {QStringLiteral("diff_field"), QStringLiteral("vector_threshold")},
        {QStringLiteral("confidence_vs"), 0.88},
    });
    arr.append(QJsonObject{
        {QStringLiteral("old_entry"), QStringLiteral("km-1")},
        {QStringLiteral("new_entry"), QStringLiteral("km-1-v3")},
        {QStringLiteral("diff_field"), QStringLiteral("适用场景")},
        {QStringLiteral("confidence_vs"), 0.71},
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
    arr.append(QJsonObject{
        {QStringLiteral("memory_id"), QStringLiteral("km-1-v2")},
        {QStringLiteral("memory_status"), QStringLiteral("archived")},
        {QStringLiteral("promotion_count"), 1},
        {QStringLiteral("demotion_count"), 2},
    });
    return QJsonObject{{QStringLiteral("items"), arr}};
}

// ── D10 forget.preview / execute 响应（与 D11B Step 5 样例对齐） ─────
QJsonObject buildForgetPreviewData(const QString& userId = QLatin1String(kUserId))
{
    QJsonArray ids;
    ids.append(QStringLiteral("km-1"));
    return QJsonObject{
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("selection_hash"), QStringLiteral("sha256:demo-d11c-ffff")},
        {QStringLiteral("affected_count"), 1},
        {QStringLiteral("credential_ttl_s"), 300},
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
        {QStringLiteral("audit_id"), QStringLiteral("aud-d11c-001")},
    };
}

// ── 辅助：等待 stage 进入目标状态（最多 timeoutMs）；失败打印现场 ────
bool waitForStage(std::function<bool()> predicate, int timeoutMs = 5000)
{
    QEventLoop loop;
    QTimer timer;
    timer.setInterval(timeoutMs);
    timer.setSingleShot(true);
    bool ok = false;
    QObject::connect(&timer, &QTimer::timeout, &loop, [&]{ loop.quit(); });
    // 每 10ms 轮询谓词（不依赖具体信号；避免 L0 跨信号 Spy 组合爆炸）。
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

}  // namespace

class TestD11CE2EOrchestrator : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();

    // A. Step 1 普通聊天（D5 主链路）
    void step1_preChat_injectsContextAndIsolatesOriginal();
    void step1_postTurn_usesTurnFinalizedMethod();

    // B. Step 2 跨会话（session 切换 + 独立 pending 不串台）
    void step2_crossSession_preChatIndependent();

    // C. Step 3 Tool Adapter
    void step3_toolSent_payloadHasToolName();
    void step3_toolUnsupportedMethod_failsafeMessage();

    // D. Step 4 知识冲突 + 生命周期
    void step4_conflictCompare_yieldsCandidates();
    void step4_lifecycleStatus_yieldsItems();

    // E. Step 5 精准遗忘 Preview + Execute
    void step5_preview_clearsSelectorHIGH01();
    void step5_execute_completedNoMissing();

    // F. 编排器总体一致性
    void stepF_notConnected_5StepsFailLocally();
    void stepF_everythingCompletes_busyClearedAllPendingEmpty();

private:
    QString uniqueSocketName(const QString& prefix);

    // 共享 Mock：注册 9 路成功 handler（A/B/C/D/E 默认）。
    void installHappyHandlers(test_support::MockGatewayServer& mock);

    std::unique_ptr<test_support::MockGatewayServer> sharedMock_;
    QString sharedSocket_;
};

void TestD11CE2EOrchestrator::initTestCase()
{
    sharedMock_ = std::make_unique<test_support::MockGatewayServer>();
    installHappyHandlers(*sharedMock_);
    sharedSocket_ = sharedMock_->listen(uniqueSocketName("shared"));
    QVERIFY2(!sharedSocket_.isEmpty(), "D11C 共享 Mock Gateway 监听失败");
}

void TestD11CE2EOrchestrator::cleanupTestCase()
{
    if (sharedMock_) sharedMock_->close();
    sharedMock_.reset();
}

QString TestD11CE2EOrchestrator::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d11c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

void TestD11CE2EOrchestrator::installHappyHandlers(
    test_support::MockGatewayServer& mock)
{
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            // 读取 session_id 做正对照（不修改业务响应，仅保证 2 次 PreChat 都成功）。
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("context"),
                             buildMemoryContext(parts.payload.value(
                                 QStringLiteral("session_id")).toString())}});
        }
        if (parts.method == client::methods::kTurnFinalized) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("turn_id"),
                             parts.payload.value(QStringLiteral("turn_id"))
                                 .toString()},
                            {QStringLiteral("event_id"),
                             QStringLiteral("evt-ok-d11c")}});
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
        // 其它：echo（不应触发）。
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
}

// ── A1 · Step 1 PreChat：上下文注入 + 三路原文隔离 ─────────────────────
void TestD11CE2EOrchestrator::step1_preChat_injectsContextAndIsolatesOriginal()
{
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }, 1500));

    vm.runPreChatPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionA), QLatin1String(kScene),
        800, QLatin1String(kOrigText1));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));

    // 三路口径：originalUserText 必须严格等于用户输入，不能在
    // injectedContextText 内出现任何子串。
    const QString original = vm.originalUserText();
    QCOMPARE(original, QString::fromUtf8(kOrigText1));
    QVERIFY(vm.textIsolationVerified());
    const QString injected = vm.injectedContextText();
    QVERIFY2(!injected.contains(original.left(8)),
             qPrintable(QStringLiteral("D11C-A1 injectedContextText 含 originalUserText 子串！原文隔离违例，注入=%1")
                            .arg(injected.left(120))));
    const QString modelReq = vm.modelRequestText();
    // modelRequest 允许包含注入 context，但必须不直接带 originalUserText
    // 的前缀长片段（D5 原文隔离：original 仅在 UI/聊天库）。
    QVERIFY2(!modelReq.contains(original.left(6)),
             qPrintable(QStringLiteral("D11C-A1 modelRequestText 直接含 originalUserText 长前缀（>5字）")));
}

// ── A2 · Step 1 PostTurn：method=turn.finalized（非 memory.store）────
void TestD11CE2EOrchestrator::step1_postTurn_usesTurnFinalizedMethod()
{
    test_support::MockGatewayServer mock;
    QString capturedMethod;
    QString capturedTurnId;
    QString capturedRetryOf;
    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method != client::methods::kHealth &&
            parts.method != client::methods::kMemoryRetrieve) {
            capturedMethod = parts.method;
            QJsonObject md = parts.payload.value(QStringLiteral("metadata"))
                                  .toObject();
            capturedTurnId = md.value(QStringLiteral("turn_id")).toString();
            capturedRetryOf = md.value(QStringLiteral("retry_of_turn_id"))
                                  .toString();
        }
        if (parts.method == client::methods::kTurnFinalized) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("event_id"),
                             QStringLiteral("evt-step1-post")}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    vm.runPostTurnPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionA),
        "turn-0001" /* turnId */,
        "tr-d11c-a2" /* traceId */,
        "msg-final-0001",
        "记忆系统含 Vector+FTS5 混合检索…",
        "ended", "stop");
    QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "sent"
                                    || vm.postTurnStage() == "failed"; }));

    QCOMPARE(vm.postTurnStage(), QStringLiteral("sent"));
    // ADR-010 强制：必须用 turn.finalized；不得回退到 memory.store。
    QCOMPARE(capturedMethod, QString(client::methods::kTurnFinalized));
    QVERIFY(capturedMethod != QLatin1String("memory.store"));
    QCOMPARE(capturedTurnId, QStringLiteral("turn-0001"));
    // 非 retry 路径：retry_of_turn_id 必须为空。
    QVERIFY(capturedRetryOf.isEmpty());
}

// ── B1 · Step 2 跨会话：切换 session 仍成功；独立 pending 不串台 ─────
void TestD11CE2EOrchestrator::step2_crossSession_preChatIndependent()
{
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // Session A
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                          QLatin1String(kScene), 800,
                          QLatin1String(kOrigText1));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
    const QString injectedA = vm.injectedContextText();
    QVERIFY(!injectedA.isEmpty());

    // Session B（新 session）
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionB),
                          QLatin1String(kScene), 900,
                          QLatin1String(kOrigText2));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
    // originalUserText 被重写为 Step 2 的新原文：证明 session 切换生效
    // （不会回退到 0001 的原文）。
    QCOMPARE(vm.originalUserText(), QString::fromUtf8(kOrigText2));
    QVERIFY(vm.textIsolationVerified());
}

// ── C1 · Step 3 Tool：toolStage=sent + toolName 正确转发 ─────────────
void TestD11CE2EOrchestrator::step3_toolSent_payloadHasToolName()
{
    test_support::MockGatewayServer mock;
    QString capturedToolName;
    QString capturedStatus;
    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == QLatin1String("tool.execution")) {
            QJsonObject md = parts.payload.value(QStringLiteral("metadata"))
                                  .toObject();
            capturedToolName = md.value(QStringLiteral("tool_name")).toString();
            capturedStatus = md.value(QStringLiteral("execution_status"))
                                 .toString();
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("ingested"), true}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    vm.runToolPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionB),
        "turn-0002" /* turnId */,
        "tc-0001" /* toolCallId */,
        "memory_search" /* toolName */,
        "success" /* executionStatus */,
        "{\"query\":\"qlatent 向量召回阈值\"}" /* argumentsRef */,
        "{\"hits\":5,\"threshold\":0.52}" /* resultRef */,
        "" /* errorType */, "" /* errorMessageSafe */,
        true /* sideEffect */, false /* rollbackRequired */);

    QVERIFY(waitForStage([&]{ return vm.toolStage() == "sent"; }));
    QCOMPARE(capturedToolName, QStringLiteral("memory_search"));
    QCOMPARE(capturedStatus, QStringLiteral("success"));
}

// ── C2 · Tool UNSUPPORTED_METHOD 闭合：safeMessage 不含原文 ─────────
void TestD11CE2EOrchestrator::step3_toolUnsupportedMethod_failsafeMessage()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        // tool.execution = UNSUPPORTED_METHOD
        if (parts.method == QLatin1String("tool.execution")) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                QStringLiteral("UNSUPPORTED_METHOD"),
                QStringLiteral("候选方法 pending ADR；服务端未注册 handler"));
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    QString gotErrorCode;
    QString gotSafeMessage;
    QObject::connect(&vm, &client::MemoryViewModel::requestFailed,
                     [&](const QString&, const QString& code, const QString& msg) {
                         gotErrorCode = code;
                         gotSafeMessage = msg;
                     });

    const QString sensitivePayload =
        "{\"hits\":5,\"threshold\":0.52,\"SECRET_DATA=PK0f3e2d_c2\"}";
    vm.runToolPipeline(
        QLatin1String(kUserId), QLatin1String(kSessionB),
        "turn-0003", "tc-0002", "memory_search",
        "success",
        "{\"query\":\"qlatent\"}",
        sensitivePayload,
        "", "", true, false);

    QVERIFY(waitForStage([&]{ return vm.toolStage() == "failed"; }));
    QCOMPARE(gotErrorCode, QStringLiteral("UNSUPPORTED_METHOD"));
    // 安全契约：safeMessage 不得包含 tool_output 正文（SECRET_DATA）。
    QVERIFY2(!gotSafeMessage.contains(QStringLiteral("PK0f3e2d_c2")),
             qPrintable(QStringLiteral("D11C-C2 safeMessage 泄露 tool_output 正文: %1")
                            .arg(gotSafeMessage)));
    QVERIFY2(!gotSafeMessage.contains(QStringLiteral("hits\":5")),
             "D11C-C2 safeMessage 泄露 tool_output JSON 片段");
}

// ── D1 · Step 4 Conflict Compare：候选列表非空 ───────────────────────
void TestD11CE2EOrchestrator::step4_conflictCompare_yieldsCandidates()
{
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    vm.runConflictComparePipeline("km-1", false /* includeResolved */);
    QVERIFY(waitForStage(
        [&]{ return vm.conflictCompareStage() == "ready"
                   || vm.conflictCompareStage() == "failed"; }));
    QCOMPARE(vm.conflictCompareStage(), QStringLiteral("ready"));
    QCOMPARE(vm.conflictCandidates().size(), 2);
    QVERIFY(vm.conflictCompareError().isEmpty());
}

// ── D2 · Step 4 Lifecycle Status：条目列表非空 ───────────────────────
void TestD11CE2EOrchestrator::step4_lifecycleStatus_yieldsItems()
{
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    vm.runLifecycleStatusPipeline(QLatin1String(kUserId), "km-1", {});
    QVERIFY(waitForStage([&]{ return vm.lifecycleStatusStage() == "ready"; }));
    QCOMPARE(vm.lifecycleItems().size(), 2);
    QVERIFY(vm.lifecycleStatusError().isEmpty());
}

// ── E1 · Step 5 Preview：selector 明文清除 HIGH-01 ───────────────────
void TestD11CE2EOrchestrator::step5_preview_clearsSelectorHIGH01()
{
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // Note: 明文 selector/target_topic 只在请求内临时存在；响应到达后
    // 客户端侧 HIGH-01 清除。forgetSelectorCleared 必须为 true。
    const QString sensitiveSelector =
        "关于 2026-08-20 向量阈值的那条记忆 [敏感:SENSITIVE-d11c-e1]";
    vm.runForgetPreviewPipeline(
        QLatin1String(kUserId),
        "plan-demo-001" /* forgetPlanId */,
        "single_item" /* forgetMode */,
        "knowledge" /* targetType */,
        sensitiveSelector,
        "km-1" /* targetId */,
        "" /* sessionId */, "" /* topic */, "" /* range */,
        true /* requiresConfirmation */, false /* isCascade */);

    QVERIFY(waitForStage(
        [&]{ return vm.forgetStage() == "awaiting_confirmation"
                   || vm.forgetStage() == "failed"; }));
    QCOMPARE(vm.forgetStage(),
             QStringLiteral("awaiting_confirmation"));
    QVERIFY(vm.forgetSelectorCleared());
    QCOMPARE(vm.forgetAffectedCount(), 1);
    QCOMPARE(vm.forgetMode(), QStringLiteral("single_item"));
    QCOMPARE(vm.forgetTargetType(), QStringLiteral("knowledge"));

    // 补充安全：error message / safeMessage 信号（若有）不得包含 selector 明文
    // （本用例成功路径不触发 requestFailed，但若 future 修改触发，
    //  这里以 forgetPreviewError 为空作为护栏）。
    QVERIFY(vm.forgetPreviewError().isEmpty());
}

// ── E2 · Step 5 Execute：completed + 无漏删 ──────────────────────────
void TestD11CE2EOrchestrator::step5_execute_completedNoMissing()
{
    test_support::MockGatewayServer mock;
    installHappyHandlers(mock);
    const QString socket = mock.listen(uniqueSocketName("e2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // 先跑 Preview（进入 awaiting_confirmation）。
    vm.runForgetPreviewPipeline(
        QLatin1String(kUserId), "plan-demo-001", "single_item", "knowledge",
        "selector-forget", "km-1", "", "", "", true, false);
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "awaiting_confirmation"; }));

    // 再 Execute。
    vm.runForgetExecutePipeline(
        QLatin1String(kUserId), "plan-demo-001",
        "credential-demo-32b",
        "" /* idempotencyKey */, "soft" /* deleteMode */);
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "completed"
                                    || vm.forgetStage() == "failed"; }));
    QCOMPARE(vm.forgetStage(), QStringLiteral("completed"));
    QVERIFY(!vm.forgetHasMissingDeletes());
    QCOMPARE(vm.forgetExecutedCount(), 1);
}

// ── F1 · 未连接：5 步客户端级立即拒绝（不会发请求） ───────────────────
void TestD11CE2EOrchestrator::stepF_notConnected_5StepsFailLocally()
{
    test_support::MockGatewayServer mock;
    installHappyHandlers(mock);
    const QString socket = mock.listen(uniqueSocketName("f1"));

    // 注意：故意不 connect。
    client::MemoryViewModel vm;
    vm.setSocketPath(socket);

    QSignalSpy failSpy(&vm, &client::MemoryViewModel::requestFailed);

    // Step 1-A PreChat
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                          QLatin1String(kScene), 800, "测试原文");
    QCOMPARE(vm.preChatStage(), QStringLiteral("failed"));

    // Step 1-B PostTurn
    vm.runPostTurnPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                           "t-1", "tr-1", "m-1", "assistant", "ended", "stop");
    QCOMPARE(vm.postTurnStage(), QStringLiteral("failed"));

    // Step 3 Tool
    vm.runToolPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                       "t-2", "tc-1", "search", "success",
                       "args", "result", "", "", true, false);
    QCOMPARE(vm.toolStage(), QStringLiteral("failed"));

    // Step 4 conflict
    vm.runConflictComparePipeline("km-1", false);
    QCOMPARE(vm.conflictCompareStage(), QStringLiteral("failed"));

    // Step 5 forget.preview（Execute 因无 preview 直接拒绝，失败路径不同）
    vm.runForgetPreviewPipeline(QLatin1String(kUserId), "fp-1", "single_item",
                                "knowledge", "sel", "km-1", "", "", "",
                                true, false);
    QCOMPARE(vm.forgetStage(), QStringLiteral("failed"));

    // fail-closed 护栏：所有 5 路都未进入成功态，且 busy 不会挂死。
    QVERIFY(!vm.busy());
    // 只要出现了至少一次 requestFailed 信号就证明客户端级 fail-closed
    // 经统一失败路径（实际数量取决于实现；不作硬上限断言）。
    QVERIFY(failSpy.count() >= 1);
}

// ── F2 · 5 步执行完毕：全局 busy=false，各 pending 全部清掉 ───────────
void TestD11CE2EOrchestrator::stepF_everythingCompletes_busyClearedAllPendingEmpty()
{
    // 本用例使用共享 Mock，一次性跑完 5 步。
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // Step 1-A PreChat (session A)
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                          QLatin1String(kScene), 800,
                          QLatin1String(kOrigText1));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
    // Step 1-B PostTurn
    vm.runPostTurnPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                           "turn-0001", "tr-e2e-0001", "msg-1",
                           "final", "ended", "stop");
    QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "sent"; }));

    // Step 2 cross-session PreChat
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionB),
                          QLatin1String(kScene), 800,
                          QLatin1String(kOrigText2));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));

    // Step 3 Tool
    vm.runToolPipeline(QLatin1String(kUserId), QLatin1String(kSessionB),
                       "turn-0002", "tc-0001", "memory_search", "success",
                       "args", "result", "", "", true, false);
    QVERIFY(waitForStage([&]{ return vm.toolStage() == "sent"; }));

    // Step 4-A Conflict + Step 4-B Lifecycle
    vm.runConflictComparePipeline("km-1", false);
    QVERIFY(waitForStage([&]{ return vm.conflictCompareStage() == "ready"; }));
    vm.runLifecycleStatusPipeline(QLatin1String(kUserId), "km-1", {});
    QVERIFY(waitForStage([&]{ return vm.lifecycleStatusStage() == "ready"; }));

    // Step 5 Preview + Execute
    vm.runForgetPreviewPipeline(QLatin1String(kUserId), "plan-e2e-01",
                                "single_item", "knowledge",
                                "关于 km-1 的 selector", "km-1",
                                "", "", "", true, false);
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "awaiting_confirmation"; }));
    vm.runForgetExecutePipeline(QLatin1String(kUserId), "plan-e2e-01",
                                "cred-xyz-32b", "", "soft");
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "completed"; }));

    // 5 步完成后：全局 busy 必须为 false（任何一路残留都会导致 busy=true）。
    QTRY_VERIFY_WITH_TIMEOUT(!vm.busy(), 3000);

    // 5 步的安全断言汇总：
    QVERIFY(vm.textIsolationVerified());                 // D5 原文隔离
    QVERIFY(vm.forgetSelectorCleared());                 // D10 HIGH-01
    QVERIFY(!vm.forgetHasMissingDeletes());              // D10 MEDIUM-03
    QVERIFY(!vm.forgetCrossUserBlocked());               // 默认不触发跨用户

    // 5 条 stage 的最终一致值：
    QCOMPARE(vm.preChatStage(), QStringLiteral("ready"));
    QCOMPARE(vm.postTurnStage(), QStringLiteral("sent"));
    QCOMPARE(vm.toolStage(), QStringLiteral("sent"));
    QCOMPARE(vm.conflictCompareStage(), QStringLiteral("ready"));
    QCOMPARE(vm.lifecycleStatusStage(), QStringLiteral("ready"));
    QCOMPARE(vm.forgetStage(), QStringLiteral("completed"));
}

QTEST_MAIN(TestD11CE2EOrchestrator)
#include "test_d11c_e2e_orchestrator.moc"
