// ============================================================================
// D11-C 同一虚拟机全功能联调 · 端到端 L0 Mock 契约测试
// （D11 E2E Orchestrator；CANDIDATE / Demo / Prototype）
//
// 本轮 Reviewer E REWORK 修复点：
//   HIGH-02  §E 新增 confirmation_credential 闭环：
//     - buildForgetPreviewData 补 confirmation_credential（D10 v0.3 必填）
//     - E2 改用 vm.forgetConfirmationCredential() 替代硬编码 "credential-demo-32b"
//     - 新增 E3：错误 / 不匹配 credential → Execute fail-closed
//   MEDIUM-02 §B 跨会话正对照：
//     - buildMemoryContext(sessionTag) 对 A/B 两个 session 返回可区分的 Context
//     - step2_crossSession 捕获两次请求的 payload.session_id，断言 0001 → 0002
//     - 断言 injectedContextText A ≠ B（证明第二次 context 确实来自新 session 请求）
//   修正用例数：A1/A2/B1/C1/C2/D1/D2/E1/E2/E3/F1/F2 = 共 **11** 个独立 test slot。
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

// ── D5 memory.retrieve：返回一个合法 MemoryContext
//    MEDIUM-02 修复：sessionTag 参与区分 Session A/B，使两者可做正对照。
QJsonObject buildMemoryContext(const QString& sessionTag)
{
    const bool isSessionA = (sessionTag == QLatin1String(kSessionA));
    QJsonArray ids;
    if (isSessionA) {
        ids.append(QStringLiteral("km-pref-001"));
        ids.append(QStringLiteral("km-know-002"));
    } else {
        // Session B：额外展示「跨会话持久化 preference」条目，正对照用
        ids.append(QStringLiteral("km-pref-001"));
        ids.append(QStringLiteral("km-know-002"));
        ids.append(QStringLiteral("km-pref-sessionB-003"));
    }
    QJsonArray ctxItems;
    ctxItems.append(QJsonObject{
        {QStringLiteral("entry_id"), QStringLiteral("km-pref-001")},
        {QStringLiteral("entry_type"), QStringLiteral("preference")},
        {QStringLiteral("summary"), QStringLiteral("用户偏好中文输出 / 80 字摘要")},
    });
    ctxItems.append(QJsonObject{
        {QStringLiteral("entry_id"), QStringLiteral("km-know-002")},
        {QStringLiteral("entry_type"), QStringLiteral("knowledge")},
        {QStringLiteral("summary"), isSessionA
            ? QStringLiteral("Vector 删除一致性：SQLite→Outbox→Vector 顺序 + 幂等重放")
            : QStringLiteral("[Session-B] Vector 删除一致性：SQLite→Outbox→Vector 顺序 + 幂等重放 + Cascade 外键校验")},
    });
    if (!isSessionA) {
        // MEDIUM-02：Session B 独有的跨会话持久化偏好条目
        ctxItems.append(QJsonObject{
            {QStringLiteral("entry_id"), QStringLiteral("km-pref-sessionB-003")},
            {QStringLiteral("entry_type"), QStringLiteral("preference")},
            {QStringLiteral("summary"), QStringLiteral("[跨会话偏好-SESS-B] editor=Qt Creator / tab_size=2 / output=zh-CN；仅在 session B 请求中出现")},
        });
    }
    return QJsonObject{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("query_id"), isSessionA
            ? QStringLiteral("q-demo-d11c-sess-A")
            : QStringLiteral("q-demo-d11c-sess-B")},
        {QStringLiteral("selected_memory_ids"), ids},
        {QStringLiteral("context_version"), QStringLiteral("1.0")},
        {QStringLiteral("token_budget"), isSessionA ? 800 : 900},
        {QStringLiteral("injection_status"), QStringLiteral("injected")},
        {QStringLiteral("actual_token_count"), isSessionA ? 246 : 358},
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

// ── D10 forget.preview / execute 响应
//    HIGH-02 修复：preview 响应必须包含 confirmation_credential（绑定
//    user_id+forget_plan_id+selection_hash，带 TTL）；Execute 必须与之完全匹配。
QJsonObject buildForgetPreviewData(const QString& userId = QLatin1String(kUserId),
                                   const QString& cred = QLatin1String("cred-forget-demo-7f3a-9c2e"))
{
    QJsonArray ids;
    ids.append(QStringLiteral("km-1"));
    return QJsonObject{
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("selection_hash"), QStringLiteral("sha256:demo-d11c-ffff")},
        {QStringLiteral("affected_count"), 1},
        {QStringLiteral("credential_ttl_s"), 300},
        // HIGH-02：D10 v0.3 必填 — 绑定 user_id+plan+selection_hash 的一次性凭据
        {QStringLiteral("confirmation_credential"), cred},
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
    void step1_preChat_injectsContextAndIsolatesOriginal();  // A1
    void step1_postTurn_usesTurnFinalizedMethod();           // A2

    // B. Step 2 跨会话（session 切换 + session_id 正对照 + 可区分 Context）
    void step2_crossSession_preChatIndependent();            // B1

    // C. Step 3 Tool Adapter
    void step3_toolSent_payloadHasToolName();                // C1
    void step3_toolUnsupportedMethod_failsafeMessage();     // C2

    // D. Step 4 知识冲突 + 生命周期
    void step4_conflictCompare_yieldsCandidates();           // D1
    void step4_lifecycleStatus_yieldsItems();                // D2

    // E. Step 5 精准遗忘 Preview + Execute（HIGH-02：凭据链闭环）
    void step5_preview_clearsSelectorHIGH01();               // E1
    void step5_execute_matchingCredentialSucceeds();         // E2 (REWORK)
    void step5_execute_wrongCredentialFailClosed();          // E3 (NEW)

    // F. 编排器总体一致性
    void stepF_notConnected_5StepsFailLocally();             // F1
    void stepF_everythingCompletes_busyClearedAllPendingEmpty(); // F2

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
            // MEDIUM-02：用 session_id 驱动 buildMemoryContext，A/B 返回不同内容
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
            // HIGH-02：Mock 侧也做凭据校验（模拟 D 轨二次校验）；
            // 不匹配返回 INVALID_CONFIRMATION_CREDENTIAL error。
            const QString expectedCred = QStringLiteral("cred-forget-demo-7f3a-9c2e");
            const QString actualCred = parts.payload.value(
                QStringLiteral("confirmation_token")).toString();
            if (actualCred != expectedCred) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    QStringLiteral("INVALID_CONFIRMATION_CREDENTIAL"),
                    QStringLiteral("Server rejected: confirmation_credential mismatch or expired."));
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
        800, QString::fromUtf8(kOrigText1));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));

    // 三路口径：originalUserText 必须严格等于用户输入，不能在
    // injectedContextText 内出现任何子串。
    const QString original = vm.originalUserText();
    QCOMPARE(original, QString::fromUtf8(kOrigText1));
    QVERIFY(vm.textIsolationVerified());
    // 原文隔离核心：injectedContextText 不得包含 originalUserText 子串。
    const QString injected = vm.injectedContextText();
    QVERIFY2(!injected.contains(original.left(8)),
             qPrintable(QStringLiteral("D11C-A1 injectedContextText 含 originalUserText 子串！原文隔离违例，注入=%1")
                            .arg(injected.left(120))));
    // modelRequestText = originalUserText + separator + injectedContextText
    // （ViewModel 设计如此；MEDIUM-03 修复 README 口径与此一致）
    // 原文隔离仅约束 injectedContextText 不含原文，modelRequestText 允许含
    // original（因为 model request = 用户查询 + 上下文注入，设计所需）。
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

// ── B1 · Step 2 跨会话：session 切换 + session_id 正对照 + 可区分 Context
void TestD11CE2EOrchestrator::step2_crossSession_preChatIndependent()
{
    // MEDIUM-02：自建 Mock 并捕获两次请求的 session_id，确保 A=0001 / B=0002，
    // 同时 buildMemoryContext 已对两 session 返回差异化内容，断言 injected A≠B。
    test_support::MockGatewayServer mock;
    QStringList capturedSessionIds;   // 按请求顺序捕获 memory.retrieve 的 session_id
    installHappyHandlers(mock);
    // 在 happy handler 基础上叠加 session_id 捕获逻辑
    mock.setHandler([&](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kMemoryRetrieve) {
            const QString sid = parts.payload.value(
                QStringLiteral("session_id")).toString();
            capturedSessionIds.append(sid);
            // 复用 buildMemoryContext（已对 A/B 返回不同 entry_id/summary/token）
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("context"),
                             buildMemoryContext(sid)}});
        }
        // 其他方法沿用 happy 路径
        if (parts.method == client::methods::kTurnFinalized) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("turn_id"),
                             parts.payload.value(QStringLiteral("turn_id")).toString()},
                            {QStringLiteral("event_id"), QStringLiteral("evt-ok")}});
        }
        if (parts.method == QLatin1String("tool.execution")) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("ingested"), true}});
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
            const QString ec = parts.payload.value(
                QStringLiteral("confirmation_token")).toString();
            if (ec != QLatin1String("cred-forget-demo-7f3a-9c2e")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    QStringLiteral("INVALID_CONFIRMATION_CREDENTIAL"),
                    QStringLiteral("credential mismatch"));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildForgetExecuteData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // Session A (session-demo-0001)
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                          QLatin1String(kScene), 800,
                          QString::fromUtf8(kOrigText1));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
    const QString injectedA = vm.injectedContextText();
    QVERIFY(!injectedA.isEmpty());

    // Session B (session-demo-0002)
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionB),
                          QLatin1String(kScene), 900,
                          QString::fromUtf8(kOrigText2));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
    const QString injectedB = vm.injectedContextText();
    QVERIFY(!injectedB.isEmpty());

    // MEDIUM-02 §1：Gateway 收到的 session_id 顺序 = 0001 → 0002
    QCOMPARE(capturedSessionIds.size(), 2);
    QCOMPARE(capturedSessionIds.at(0), QString::fromLatin1(kSessionA));
    QCOMPARE(capturedSessionIds.at(1), QString::fromLatin1(kSessionB));

    // MEDIUM-02 §2：两次返回的 Context 可区分（A 不含 SESS-B 条目，B 含）
    QVERIFY2(!injectedA.contains(QStringLiteral("SESS-B")),
             "D11C-B1 Session A injected 不应包含 Session-B 专用条目");
    QVERIFY2(injectedB.contains(QStringLiteral("跨会话偏好-SESS-B")),
             qPrintable(QStringLiteral("D11C-B1 Session B injected 应含跨会话偏好：%1")
                            .arg(injectedB.left(200))));
    QVERIFY2(injectedA != injectedB,
             "D11C-B1 两次 session 的 injectedContextText 应不同（正对照防串台）");

    // originalUserText 被重写为 Step 2 的新原文：证明 session 切换生效。
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
            capturedToolName = parts.payload.value(QStringLiteral("tool_name")).toString();
            capturedStatus = parts.payload.value(QStringLiteral("execution_status")).toString();
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

// ── E1 · Step 5 Preview：selector 明文清除 HIGH-01 + 凭据非空 ─────────
void TestD11CE2EOrchestrator::step5_preview_clearsSelectorHIGH01()
{
    client::MemoryViewModel vm;
    vm.setSocketPath(sharedSocket_);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

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

    // HIGH-02：Preview 必须返回 confirmation_credential，客户端侧投影非空
    // （后续 Execute 必须传同一值；否则 fail-closed）。
    QVERIFY2(!vm.forgetConfirmationCredential().isEmpty(),
             "D11C-E1 Preview 响应必须包含 confirmation_credential（D10 v0.3 凭据链）");
    QCOMPARE(vm.forgetCredentialTtlSeconds(), 300);

    QVERIFY(vm.forgetPreviewError().isEmpty());
}

// ── E2 · Step 5 Execute：正确 credential → completed（HIGH-02 正向） ───
void TestD11CE2EOrchestrator::step5_execute_matchingCredentialSucceeds()
{
    test_support::MockGatewayServer mock;
    installHappyHandlers(mock);
    const QString socket = mock.listen(uniqueSocketName("e2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // 先跑 Preview（进入 awaiting_confirmation，并投影 confirmation_credential）。
    vm.runForgetPreviewPipeline(
        QLatin1String(kUserId), "plan-demo-001", "single_item", "knowledge",
        "selector-forget", "km-1", "", "", "", true, false);
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "awaiting_confirmation"; }));

    const QString credFromPreview = vm.forgetConfirmationCredential();
    QVERIFY2(!credFromPreview.isEmpty(),
             "D11C-E2 Preview 必须返回 credential，否则 Execute 无法闭环");

    // HIGH-02 REWORK：Execute 使用 Preview 返回的同一 credential（替代硬编码）
    vm.runForgetExecutePipeline(
        QLatin1String(kUserId), "plan-demo-001",
        credFromPreview,   // 与 Preview 响应中 confirmation_credential 一致
        "" /* idempotencyKey */, "soft" /* deleteMode */);
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "completed"
                                    || vm.forgetStage() == "failed"; }));
    QCOMPARE(vm.forgetStage(), QStringLiteral("completed"));
    QVERIFY(!vm.forgetHasMissingDeletes());
    QCOMPARE(vm.forgetExecutedCount(), 1);
    // HIGH-02：成功 Execute 后一次性凭据被消费（置空，杜绝重放）
    QVERIFY2(vm.forgetConfirmationCredential().isEmpty(),
             "D11C-E2 Execute 成功后 confirmation_credential 必须消费清空（防重放）");
}

// ── E3 · Step 5 Execute：错误 credential → fail-closed（HIGH-02 反向） ─
void TestD11CE2EOrchestrator::step5_execute_wrongCredentialFailClosed()
{
    test_support::MockGatewayServer mock;
    installHappyHandlers(mock);
    const QString socket = mock.listen(uniqueSocketName("e3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QVERIFY(waitForStage([&]{ return vm.connectionState() == "connected"; }));

    // ① Preview 成功 → 得到 credFromPreview
    vm.runForgetPreviewPipeline(
        QLatin1String(kUserId), "plan-demo-001", "single_item", "knowledge",
        "selector-forget", "km-1", "", "", "", true, false);
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "awaiting_confirmation"; }));
    const QString credFromPreview = vm.forgetConfirmationCredential();
    QVERIFY(!credFromPreview.isEmpty());

    // ② 故意使用不匹配的 credential
    QString gotErrCode;
    QString gotErrMsg;
    QObject::connect(&vm, &client::MemoryViewModel::requestFailed,
                     [&](const QString&, const QString& c, const QString& m) {
                         gotErrCode = c; gotErrMsg = m;
                     });
    const QString wrongCred = QStringLiteral("WRONG-CREDENTIAL-h4cked-0000");
    QVERIFY2(wrongCred != credFromPreview, "测试前提：错误 credential 必须与 Preview 值不同");

    vm.runForgetExecutePipeline(
        QLatin1String(kUserId), "plan-demo-001",
        wrongCred,   // 错误凭据
        "", "soft");
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "failed"
                                    || vm.forgetStage() == "completed"; }, 5000));

    // HIGH-02 fail-closed：必须进入 failed，不得伪 completed
    QCOMPARE(vm.forgetStage(), QStringLiteral("failed"));
    // 客户端侧或服务端的错误：必须是凭据不匹配类错误
    const QString errorText = vm.forgetExecuteError() + gotErrCode + gotErrMsg;
    QVERIFY2(errorText.contains(QStringLiteral("credential"))
             || errorText.contains(QStringLiteral("confirmation_token")),
             qPrintable(QStringLiteral("D11C-E3 错误凭据必须 fail-closed，实际错误=%1 | code=%2 | msg=%3")
                            .arg(vm.forgetExecuteError()).arg(gotErrCode).arg(gotErrMsg)));
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

    // Step 5 forget.preview
    vm.runForgetPreviewPipeline(QLatin1String(kUserId), "fp-1", "single_item",
                                "knowledge", "sel", "km-1", "", "", "",
                                true, false);
    QCOMPARE(vm.forgetStage(), QStringLiteral("failed"));

    // fail-closed 护栏：所有 5 路都未进入成功态，且 busy 不会挂死。
    QVERIFY(!vm.busy());
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
                          QString::fromUtf8(kOrigText1));
    QVERIFY(waitForStage([&]{ return vm.preChatStage() == "ready"; }));
    // Step 1-B PostTurn
    vm.runPostTurnPipeline(QLatin1String(kUserId), QLatin1String(kSessionA),
                           "turn-0001", "tr-e2e-0001", "msg-1",
                           "final", "ended", "stop");
    QVERIFY(waitForStage([&]{ return vm.postTurnStage() == "sent"; }));

    // Step 2 cross-session PreChat
    vm.runPreChatPipeline(QLatin1String(kUserId), QLatin1String(kSessionB),
                          QLatin1String(kScene), 800,
                          QString::fromUtf8(kOrigText2));
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

    // Step 5 Preview + Execute（HIGH-02 REWORK：使用 Preview 返回的 credential）
    vm.runForgetPreviewPipeline(QLatin1String(kUserId), "plan-e2e-01",
                                "single_item", "knowledge",
                                "关于 km-1 的 selector", "km-1",
                                "", "", "", true, false);
    QVERIFY(waitForStage([&]{ return vm.forgetStage() == "awaiting_confirmation"; }));
    const QString f2Cred = vm.forgetConfirmationCredential();
    QVERIFY2(!f2Cred.isEmpty(), "D11C-F2 Preview credential 非空（D10 v0.3 凭据链）");
    vm.runForgetExecutePipeline(QLatin1String(kUserId), "plan-e2e-01",
                                f2Cred, "", "soft");
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
