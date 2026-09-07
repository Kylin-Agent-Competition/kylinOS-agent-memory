// ============================================================================
// D10C 精准遗忘 L0 Mock 契约测试
// （forget.preview / forget.execute；CANDIDATE / pending ADR；
//  业务契约 v0.3 冻结；Runtime Hard/Cascade/Full Reset fail-closed）
// 范围：
//   A. forget.preview 模式互斥（SEC-FORGET-03）：5 模式合法 + 跨模式字段拒绝
//   B. Preview → selection_hash + affected_count + credential_ttl +
//      resolved_target_ids + selector 明文清除 (§四.8 HIGH-01)
//   C. Preview → Execute 状态机（idle→previewing→awaiting→executing→completed）
//   D. Execute 漏删保护 (v0.3/MEDIUM-03)：executed != affected → stage=failed
//   E. 跨用户操作拒绝 (C-D10 #3)：响应 user_id 不匹配 → forgetCrossUserBlocked=true
//   F. Execute 必须基于成功 Preview：stage != awaiting_confirmation → 拒绝
//   G. 独立 busy/pending + 未连接拒绝
//   H. UNSUPPORTED_METHOD / status=error → stage=failed，无伪结果
//   I. full_reset 携带 target_* → 拒绝
//   J. Hard Delete Runtime fail-closed：错误响应不自动降级软删后报成功
// 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 另行在 VM 验证）。
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

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

namespace {

constexpr const char* kDemoUserId = "u1";
constexpr const char* kDemoAltUserId = "u2";
constexpr const char* kDemoPlanId = "fp-20260901-001";
constexpr const char* kDemoSelectionHash = "sha256:abcd1234ef56";
constexpr const int kDemoAffectedCount = 3;
constexpr const int kDemoTtl = 300;
// v0.3 HIGH-02 凭据链：Mock preview 返回的 confirmation_credential
// 与后续 Execute 调用传入 token 必须完全一致，否则 runForgetExecutePipeline
// 在客户端侧直接 fail-closed，根本走不到 Mock Execute handler。
constexpr const char* kDemoConfirmationCredential = "credential-demo-32b";
constexpr const char* kDemoHardDeleteCredential = "cred-demo-hard";

// 构造 forget.preview 成功 data（含 selection_hash / affected_count /
// credential_ttl_s / resolved_target_ids_preview_snippet / selector_cleared /
// forget_mode / target_type / is_cascade / confirmation_credential）。
QJsonObject buildPreviewSuccessData(
    const QString& userId = QLatin1String(kDemoUserId),
    const QString& cred = QLatin1String(kDemoConfirmationCredential))
{
    QJsonArray ids;
    ids.append(QStringLiteral("km-1"));
    ids.append(QStringLiteral("km-2"));
    ids.append(QStringLiteral("km-3"));
    return QJsonObject{
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("selection_hash"), QString::fromUtf8(kDemoSelectionHash)},
        {QStringLiteral("affected_count"), kDemoAffectedCount},
        {QStringLiteral("credential_ttl_s"), kDemoTtl},
        {QStringLiteral("forget_mode"), QStringLiteral("single_item")},
        {QStringLiteral("target_type"), QStringLiteral("knowledge")},
        {QStringLiteral("is_cascade"), false},
        {QStringLiteral("selector_cleared"), true},
        // HIGH-02 凭据链必填：v0.3 要求 Preview 返回一次性 confirmation_credential
        // 供 Execute 再次校验；缺值会被 ViewModel runForgetExecutePipeline
        // 门禁 fail-closed。
        {QStringLiteral("confirmation_credential"), cred},
        {QStringLiteral("resolved_target_ids_preview_snippet"), ids},
    };
}

// forget.execute 一致执行数据（executed_count == affected_count）
QJsonObject buildExecuteConsistentData()
{
    return QJsonObject{
        {QStringLiteral("executed_count"), kDemoAffectedCount},
        {QStringLiteral("delete_mode"), QStringLiteral("soft")},
        {QStringLiteral("audit_id"), QStringLiteral("aud-forget-001")},
    };
}

// forget.execute 漏删数据（executed_count < affected_count → MEDIUM-03）
QJsonObject buildExecuteMissingData()
{
    return QJsonObject{
        {QStringLiteral("executed_count"), kDemoAffectedCount - 1},
    };
}

} // namespace

class TestD10CForgetting : public QObject {
    Q_OBJECT

private slots:
    // A. forget.preview 模式互斥（SEC-FORGET-03）：5 合法 + 1 拒绝
    void previewModeMutex_singleItem_onlyTargetId();
    void previewModeMutex_session_onlySessionId();
    void previewModeMutex_topic_onlyTopic();
    void previewModeMutex_timeWindow_onlyTimeRange();
    void previewModeMutex_fullReset_noTargets();
    void previewRejects_crossModeSelector();

    // B. Preview 投影 + selector 明文清除 HIGH-01
    void previewSuccess_projectsFieldsAndClearsSelector();

    // C. 状态机：idle → previewing → awaiting → executing → completed
    void stateMachine_previewThenExecute_completed();

    // D. Execute 漏删保护（v0.3/MEDIUM-03）
    void executeMissingDeletes_mustNotEnterCompleted();

    // E. 跨用户操作拒绝（C-D10 #3）
    void crossUserMismatch_blockedAndFailed();

    // F. Execute 必须基于 awaiting_confirmation
    void executeWithoutPreview_rejected();

    // G. 未连接拒绝 + 独立 busy
    void previewRejects_whenNotConnected();
    void previewBusy_isIndependentFromExecute();

    // H. UNSUPPORTED_METHOD / error → failed，无伪结果
    void unsupportedMethod_routesToFailed();

    // I. full_reset 携带 target_* → 拒绝
    void fullResetWithTargets_rejected();

    // J. Hard Delete fail-closed（错误不自动降级 soft）
    void hardDeleteFailClosed_noAutoDowngrade();

private:
    QString uniqueSocketName(const QString& prefix);
};

QString TestD10CForgetting::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d10c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

// ── A1 single_item：仅 target_id 合法 ──────────────────────────────────────
void TestD10CForgetting::previewModeMutex_singleItem_onlyTargetId()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
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

    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        QStringLiteral("删除过时知识"),
        QStringLiteral("km-1"),   // targetId（single_item 合法）
        {}, {}, {},               // 无其他 target_*
        true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);
    QCOMPARE(vm.forgetAffectedCount(), kDemoAffectedCount);
    mock.close();
}

// ── A2 session：仅 target_session_id 合法 ─────────────────────────────────
void TestD10CForgetting::previewModeMutex_session_onlySessionId()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
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

    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("session"), QStringLiteral("all"),
        QStringLiteral("清空会话 s1"),
        {},                       // 无 target_id
        QStringLiteral("sess-001"),  // target_session_id（session 合法）
        {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);
    mock.close();
}

// ── A3 topic：仅 target_topic 合法 ─────────────────────────────────────────
void TestD10CForgetting::previewModeMutex_topic_onlyTopic()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a3"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("topic"), QStringLiteral("event"),
        QStringLiteral("删除周报相关主题"),
        {}, {},
        QStringLiteral("项目周报格式"),  // target_topic（topic 合法）
        {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);
    mock.close();
}

// ── A4 time_window：仅 target_time_range 合法 ──────────────────────────────
void TestD10CForgetting::previewModeMutex_timeWindow_onlyTimeRange()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a4"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("time_window"), QStringLiteral("preference"),
        QStringLiteral("删除上周过时偏好"),
        {}, {}, {},
        QStringLiteral("2026-08-01/2026-08-31"),  // time_range（合法）
        true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);
    mock.close();
}

// ── A5 full_reset：不携带任何 target_* 合法 ────────────────────────────────
void TestD10CForgetting::previewModeMutex_fullReset_noTargets()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a5"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // full_reset：不携带任何 target_* 是合法的
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("full_reset"), QStringLiteral("all"),
        QStringLiteral("重置全部记忆"),
        {}, {}, {}, {},   // 无任何 target_*
        true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);
    mock.close();
}

// ── A6 跨模式携带 → SEC-FORGET-03 客户端侧拒绝 ────────────────────────────
void TestD10CForgetting::previewRejects_crossModeSelector()
{
    // 不连接 Mock（客户端侧立即失败，不走 IPC）
    test_support::MockGatewayServer mock;
    const QString socket = mock.listen(uniqueSocketName("a6"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // single_item 同时携带 target_session_id → 立即拒绝
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {},
        QStringLiteral("km-1"),      // 合法 target_id
        QStringLiteral("sess-001"),  // 非法：跨模式携带 session_id
        {}, {}, true, false);
    // 客户端侧校验：立即进入 failed，不发送 IPC
    QCOMPARE(vm.forgetStage(), QStringLiteral("failed"));
    QVERIFY(!vm.forgetPreviewError().isEmpty());
    mock.close();
}

// ── B. Preview 投影 + selector 明文清除 (§四.8 HIGH-01) ──────────────────
void TestD10CForgetting::previewSuccess_projectsFieldsAndClearsSelector()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("b"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        QStringLiteral("SENTINEL_FORGET_TEXT 删除某偏好"),
        QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);

    QCOMPARE(vm.forgetSelectionHash(), QString::fromUtf8(kDemoSelectionHash));
    QCOMPARE(vm.forgetAffectedCount(), kDemoAffectedCount);
    QCOMPARE(vm.forgetCredentialTtlSeconds(), kDemoTtl);
    QCOMPARE(vm.forgetResolvedTargets().size(), kDemoAffectedCount);
    // §四.8 HIGH-01：selector 明文清除状态 = true
    QVERIFY(vm.forgetSelectorCleared());
    mock.close();
}

// ── C. 状态机 Preview → Execute → completed ───────────────────────────────
void TestD10CForgetting::stateMachine_previewThenExecute_completed()
{
    int step = 0;
    test_support::MockGatewayServer mock;
    mock.setHandler([&step](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            step = 1;
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
        }
        if (parts.method == client::methods::kForgetExecute) {
            step = 2;
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildExecuteConsistentData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // Step 1: Preview
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);
    QCOMPARE(step, 1);

    // Step 2: Execute
    vm.runForgetExecutePipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("credential-demo-32b"),
        QStringLiteral("idem-fp-001"),
        QStringLiteral("soft"));
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("completed"), 5000);
    QCOMPARE(step, 2);
    QCOMPARE(vm.forgetExecutedCount(), kDemoAffectedCount);
    QVERIFY(!vm.forgetHasMissingDeletes());
    mock.close();
}

// ── D. 漏删保护（v0.3/MEDIUM-03：executed < affected → failed）───────────
void TestD10CForgetting::executeMissingDeletes_mustNotEnterCompleted()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
        }
        if (parts.method == client::methods::kForgetExecute) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildExecuteMissingData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("d"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // Preview
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);

    // Execute：漏删 → 不得进入 completed
    vm.runForgetExecutePipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("credential-demo-32b"), {}, {});
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("failed"), 5000);
    QVERIFY(vm.forgetHasMissingDeletes());
    mock.close();
}

// ── E. 跨用户操作拒绝（C-D10 #3）──────────────────────────────────────────
void TestD10CForgetting::crossUserMismatch_blockedAndFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            // 响应返回 user_id=u2，但请求携带 user_id=u1 → 客户端预检拒绝
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                buildPreviewSuccessData(QString::fromUtf8(kDemoAltUserId)));
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("e"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // 请求 userId=u1，但响应 data.user_id=u2（见 lambda 中 buildPreviewSuccessData(u2)）
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId) /*u1*/, QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("failed"), 5000);
    QVERIFY(vm.forgetCrossUserBlocked());
    mock.close();
}

// ── F. Execute 必须基于 awaiting_confirmation（门禁）────────────────────
void TestD10CForgetting::executeWithoutPreview_rejected()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        // 对 forget.preview 返回错误 → stage=failed，便于非 awaiting 状态
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kInvalidRequest,
                QStringLiteral("plan not found"));
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("f"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // 先使 stage=failed（非 awaiting_confirmation）
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QStringLiteral("reset-stage-plan"),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-x"), {}, {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("failed"), 5000);

    // 在 stage != awaiting_confirmation 时调用 Execute → 立即客户端侧拒绝
    vm.runForgetExecutePipeline(
        QString::fromUtf8(kDemoUserId), QStringLiteral("reset-stage-plan"),
        QStringLiteral("any-credential"), {}, {});
    QCOMPARE(vm.forgetStage(), QStringLiteral("failed"));
    // 验证错误消息包含必须先有 Preview 的门禁描述
    QVERIFY(vm.forgetExecuteError().contains(QStringLiteral(
        "prior successful forget.preview")));
    mock.close();
}

// ── G1. 未连接拒绝 ──────────────────────────────────────────────────────────
void TestD10CForgetting::previewRejects_whenNotConnected()
{
    client::MemoryViewModel vm;
    // 不连接
    QCOMPARE(vm.connectionState(), QStringLiteral("disconnected"));
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QCOMPARE(vm.forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm.forgetPreviewError().contains(QStringLiteral("not connected")));
}

// ── G2. Preview busy 与 Execute busy 独立（不串台）────────────────────────
void TestD10CForgetting::previewBusy_isIndependentFromExecute()
{
    // 初始状态均为 false
    test_support::MockGatewayServer mock;
    // 让 handler 延迟一小段时间才返回 → 期间可观测 busy 状态
    int delayMs = 60;
    mock.setHandler([delayMs](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            QEventLoop loop;
            QTimer::singleShot(delayMs, &loop, &QEventLoop::quit);
            loop.exec();
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, buildPreviewSuccessData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("g2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    QCOMPARE(vm.forgetPreviewBusy(), false);
    QCOMPARE(vm.forgetExecuteBusy(), false);

    // 启动 Preview
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    // 在 handler 60ms 延迟窗口内，Preview busy=true，Execute busy 仍保持 false
    QTest::qWait(20);
    QVERIFY(vm.forgetPreviewBusy());
    QVERIFY(!vm.forgetExecuteBusy());

    // 等待完成
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);
    QCOMPARE(vm.forgetPreviewBusy(), false);
    mock.close();
}

// ── H. UNSUPPORTED_METHOD → failed，无伪结果 ──────────────────────────────
void TestD10CForgetting::unsupportedMethod_routesToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        // 模拟生产 Gateway：对 forget.preview 返回 UNSUPPORTED_METHOD
        if (parts.method == client::methods::kForgetPreview) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kUnsupportedMethod,
                QStringLiteral("forget.preview: CANDIDATE / pending ADR."));
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("h"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("failed"), 5000);
    // 不得产生伪 selection_hash 或 affected_count 非默认值
    QVERIFY(vm.forgetSelectionHash().isEmpty());
    QCOMPARE(vm.forgetAffectedCount(), 0);
    mock.close();
}

// ── I. full_reset 携带 target_* → 拒绝 ────────────────────────────────────
void TestD10CForgetting::fullResetWithTargets_rejected()
{
    test_support::MockGatewayServer mock;
    const QString socket = mock.listen(uniqueSocketName("i"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // full_reset + 携带 target_id → SEC-FORGET-03 客户端侧拒绝
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("full_reset"), QStringLiteral("all"),
        {},
        QStringLiteral("km-1"),   // 非法：full_reset 不应携带 target_*
        {}, {}, {}, true, false);
    QCOMPARE(vm.forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm.forgetPreviewError().contains(QStringLiteral(
        "full_reset mode must not carry")));
    mock.close();
}

// ── J. Hard Delete fail-closed（MEDIUM-04：错误不自动降级 soft）─────────
void TestD10CForgetting::hardDeleteFailClosed_noAutoDowngrade()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kForgetPreview) {
            // 返回 hard delete 专用凭据：确保后续 Execute 先过客户端凭据链门禁
            // 再到 Mock Execute handler，验证 Hard Delete Runtime fail-closed
            // 是服务端返回错误而非客户端凭据校验失败。
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                buildPreviewSuccessData(
                    QString::fromUtf8(kDemoUserId),
                    QString::fromUtf8(kDemoHardDeleteCredential)));
        }
        if (parts.method == client::methods::kForgetExecute) {
            // ADR-016 可信输入来源未接线 → Runtime fail-closed，返回错误
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kInvalidRequest,
                QStringLiteral("Hard Delete Runtime fail-closed: ADR-016 input source not wired."));
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("j"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // Step 1: Preview OK
    vm.runForgetPreviewPipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("single_item"), QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("awaiting_confirmation"), 5000);

    // Step 2: Execute delete_mode=hard → fail-closed，不得自动降级
    vm.runForgetExecutePipeline(
        QString::fromUtf8(kDemoUserId), QString::fromUtf8(kDemoPlanId),
        QStringLiteral("cred-demo-hard"), {},
        QStringLiteral("hard"));
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.forgetStage(), QStringLiteral("failed"), 5000);
    QVERIFY(vm.forgetExecuteError().contains(QStringLiteral("fail-closed")));
    // executed_count 保持 -1（未执行），不得伪造完成数量
    QCOMPARE(vm.forgetExecutedCount(), -1);
    mock.close();
}

QTEST_MAIN(TestD10CForgetting)
#include "test_d10c_forgetting.moc"
