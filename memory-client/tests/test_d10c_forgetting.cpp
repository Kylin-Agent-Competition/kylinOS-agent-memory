// ============================================================================
// D10C 精准遗忘 L0 Mock 契约测试
// （forget.preview / forget.execute；CANDIDATE / pending ADR；
//  业务契约 v0.3 冻结；Runtime Hard/Cascade/Full Reset fail-closed）
// 范围：
//   A. forget.preview 模式互斥（SEC-FORGET-03）：5 模式 + 跨模式/缺字段拒绝
//   B. Preview → selection_hash + affected_count + credential_ttl + resolved_target_ids
//      + selector 明文清除 (§四.8 HIGH-01) → forgetSelectorCleared=true
//   C. Preview → Execute 状态机（idle→previewing→awaiting_confirmation→executing→completed）
//   D. Execute 漏删保护 (v0.3/MEDIUM-03)：executed != affected → stage=failed
//   E. 跨用户操作拒绝 (C-D10 #3)：响应 user_id 不匹配 → forgetCrossUserBlocked=true
//   F. Execute 必须基于成功 Preview：stage != awaiting_confirmation → 拒绝
//   G. 独立 busy/pending (Preview 与 Execute 不串台) + 未连接拒绝
//   H. UNSUPPORTED_METHOD / status=error → stage=failed，无伪结果
//   I. full_reset 携带 target_* → INVALID_REQUEST（Demo fail-closed）
//   J. Hard Delete Runtime fail-closed：未接 ADR-016 可信来源前，hard 响应
//      status=error 时不自动降级软删后报成功（Demo 验证）
// 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 另行在 VM 验证）。
// ============================================================================
#include <QObject>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QString>
#include <QTest>
#include <QSignalSpy>
#include <QTimer>

#include "mock_gateway_server.h"
#include "protocol_adapter.h"
#include "memory_client.h"
#include "memory_view_model.h"

using namespace kylin::memory::client::v1;

namespace {

constexpr const char* kDemoUserId = "u1";
constexpr const char* kDemoAltUserId = "u2";
constexpr const char* kDemoPlanId = "fp-20260901-001";
constexpr const char* kDemoSelectionHash = "sha256:abcd1234ef56...";
constexpr const int kDemoAffectedCount = 3;
constexpr const int kDemoTtl = 300;

// 构造 forget.preview 成功响应（含 selection_hash / affected_count / credential_ttl_s /
// resolved_target_ids_preview_snippet / selector_cleared=true / forget_mode / target_type /
// is_cascade=false / sensitivity_warning 空）。
QJsonObject buildPreviewSuccessData(const QString& userId = kDemoUserId)
{
    QJsonObject d;
    d.insert(QStringLiteral("user_id"), userId);
    d.insert(QStringLiteral("selection_hash"), kDemoSelectionHash);
    d.insert(QStringLiteral("affected_count"), kDemoAffectedCount);
    d.insert(QStringLiteral("credential_ttl_s"), kDemoTtl);
    d.insert(QStringLiteral("forget_mode"), QStringLiteral("single_item"));
    d.insert(QStringLiteral("target_type"), QStringLiteral("knowledge"));
    d.insert(QStringLiteral("is_cascade"), false);
    d.insert(QStringLiteral("selector_cleared"), true);
    QJsonArray ids;
    ids.append(QStringLiteral("km-1"));
    ids.append(QStringLiteral("km-2"));
    ids.append(QStringLiteral("km-3"));
    d.insert(QStringLiteral("resolved_target_ids_preview_snippet"), ids);
    return d;
}

// 构造 forget.execute 成功数据（executed_count 一致）
QJsonObject buildExecuteConsistentData()
{
    QJsonObject d;
    d.insert(QStringLiteral("executed_count"), kDemoAffectedCount);
    d.insert(QStringLiteral("delete_mode"), QStringLiteral("soft"));
    d.insert(QStringLiteral("audit_id"), QStringLiteral("aud-forget-001"));
    return d;
}

// 构造 forget.execute 漏删数据（executed < affected）
QJsonObject buildExecuteMissingData()
{
    QJsonObject d;
    d.insert(QStringLiteral("executed_count"), kDemoAffectedCount - 1);  // < affected
    return d;
}

} // namespace

class TestD10CForgetting : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();

    // A. forget.preview 模式互斥（SEC-FORGET-03）
    void previewModeMutex_singleItem_onlyTargetId();
    void previewModeMutex_session_onlySessionId();
    void previewModeMutex_topic_onlyTopic();
    void previewModeMutex_timeWindow_onlyTimeRange();
    void previewModeMutex_fullReset_noTargets();
    void previewRejects_crossModeSelector();

    // B. Preview → 投影 + selector 明文清除
    void previewSuccess_projectsFieldsAndClearsSelector();

    // C. 状态机：Preview → Execute → completed
    void stateMachine_previewThenExecute_completed();

    // D. Execute 漏删保护 (MEDIUM-03)
    void executeMissingDeletes_mustNotEnterCompleted();

    // E. 跨用户操作拒绝 (C-D10 #3)
    void crossUserMismatch_blockedAndFailed();

    // F. Execute 必须基于 awaiting_confirmation
    void executeWithoutPreview_rejected();

    // G. 独立 pending / 未连接拒绝
    void previewRejects_whenNotConnected();
    void previewAndExecuteBusy_flagsAreIndependent();

    // H. UNSUPPORTED_METHOD / error 响应 → failed，无伪结果
    void unsupportedMethod_routesToFailed();

    // I. full_reset 携带 target_* → 拒绝
    void fullResetWithTargets_rejected();

    // J. Hard Delete fail-closed：错误响应不自动降级
    void hardDeleteFailClosed_noAutoDowngrade();

private:
    MockGatewayServer* server_;
    MemoryViewModel* vm_;
    QString socketPath_;
};

void TestD10CForgetting::initTestCase()
{
    server_ = new MockGatewayServer();
    socketPath_ = server_->start();
    QVERIFY(!socketPath_.isEmpty());

    vm_ = new MemoryViewModel();
    vm_->setSocketPath(socketPath_);
    QEventLoop loop;
    QTimer::singleShot(50, [&]{ vm_->connectToService(); });
    QTimer::singleShot(500, &loop, &QEventLoop::quit);
    loop.exec();
    QCOMPARE(vm_->connectionState(), QStringLiteral("connected"));
}

void TestD10CForgetting::cleanupTestCase()
{
    delete vm_;
    delete server_;
}

// ── A. 模式互斥（SEC-FORGET-03）─────────────────────────────────────────────

void TestD10CForgetting::previewModeMutex_singleItem_onlyTargetId()
{
    // 合法：single_item 只带 target_id
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        QStringLiteral("删除过时知识"), /*selector*/
        QStringLiteral("km-1"),      /*targetId*/
        {}, {}, {},                   /*sessionId/topic/timeRange*/
        true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
    QCOMPARE(vm_->forgetAffectedCount(), kDemoAffectedCount);
}

void TestD10CForgetting::previewModeMutex_session_onlySessionId()
{
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("session"),
        QStringLiteral("all"),
        QStringLiteral("清空会话 s1"),
        {}, /*targetId*/
        QStringLiteral("sess-001"), /*sessionId*/
        {}, {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
}

void TestD10CForgetting::previewModeMutex_topic_onlyTopic()
{
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("topic"),
        QStringLiteral("event"),
        QStringLiteral("删除周报相关主题"),
        {}, {},
        QStringLiteral("项目周报格式"), /*topic*/
        {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
}

void TestD10CForgetting::previewModeMutex_timeWindow_onlyTimeRange()
{
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("time_window"),
        QStringLiteral("preference"),
        QStringLiteral("删除上周过时偏好"),
        {}, {}, {},
        QStringLiteral("2026-08-01/2026-08-31"),
        true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
}

void TestD10CForgetting::previewModeMutex_fullReset_noTargets()
{
    server_->setNextResponseData(buildPreviewSuccessData());
    // full_reset 不携带任何 target_* 是合法的
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("full_reset"),
        QStringLiteral("all"),
        QStringLiteral("重置全部记忆"),
        {}, {}, {}, {}, /* 无任何 target_* */
        true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
}

void TestD10CForgetting::previewRejects_crossModeSelector()
{
    // single_item 携带 target_session_id → SEC-FORGET-03 拒绝（客户端侧即失败，无需 mock 响应）
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {},
        QStringLiteral("km-1"),      /*合法 target_id*/
        QStringLiteral("sess-001"),  /*非法：跨模式携带 sessionId*/
        {}, {}, true, false);
    QCOMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm_->forgetPreviewError().length() > 0);
}

// ── B. Preview 投影 + selector 清除 (§四.8 HIGH-01) ──────────────────────

void TestD10CForgetting::previewSuccess_projectsFieldsAndClearsSelector()
{
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        QStringLiteral("SENTINEL_FORGET_TEXT_A7F2 删除某偏好"),
        QStringLiteral("km-1"), {}, {}, {},
        true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
    QCOMPARE(vm_->forgetSelectionHash(), QString::fromUtf8(kDemoSelectionHash));
    QCOMPARE(vm_->forgetAffectedCount(), kDemoAffectedCount);
    QCOMPARE(vm_->forgetCredentialTtlSeconds(), kDemoTtl);
    QCOMPARE(vm_->forgetResolvedTargets().size(), kDemoAffectedCount);
    QVERIFY(vm_->forgetSelectorCleared());  // HIGH-01：selector 清除状态
}

// ── C. 状态机 ──────────────────────────────────────────────────────────────

void TestD10CForgetting::stateMachine_previewThenExecute_completed()
{
    // Step 1: Preview
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
    // Step 2: Execute（一致数量）
    server_->setNextResponseData(buildExecuteConsistentData());
    vm_->runForgetExecutePipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("credential-demo-32b"),
        QStringLiteral("idem-fp-001"),
        QStringLiteral("soft"));
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("completed"));
    QCOMPARE(vm_->forgetExecutedCount(), kDemoAffectedCount);
    QVERIFY(!vm_->forgetHasMissingDeletes());
}

// ── D. 漏删保护 (v0.3/MEDIUM-03) ────────────────────────────────────────────

void TestD10CForgetting::executeMissingDeletes_mustNotEnterCompleted()
{
    // Preview first
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
    // Execute：executed < affected → 不得 completed
    server_->setNextResponseData(buildExecuteMissingData());
    vm_->runForgetExecutePipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("credential-demo-32b"), {}, {});
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm_->forgetHasMissingDeletes());
}

// ── E. 跨用户操作拒绝 (C-D10 #3) ───────────────────────────────────────────

void TestD10CForgetting::crossUserMismatch_blockedAndFailed()
{
    // 请求 user_id=u1，响应 data.user_id=u2 → 客户端预检拒绝
    server_->setNextResponseData(buildPreviewSuccessData(kDemoAltUserId /*u2*/));
    vm_->runForgetPreviewPipeline(
        kDemoUserId /*u1*/, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm_->forgetCrossUserBlocked());
}

// ── F. Execute 必须基于 awaiting_confirmation ──────────────────────────────

void TestD10CForgetting::executeWithoutPreview_rejected()
{
    // idle 阶段直接 Execute → 拒绝
    // 先确保当前状态非 awaiting（重置：运行个非法 preview 回到 idle 再试更简单）
    // 直接调用：stage=idle → 必失败
    // 若当前 stage 恰好是 idle，则应立即失败；否则可能是之前测试遗留。
    // 策略：用一个 known 空 planId 发起 Preview 并强制回到 failed，再 Execute
    server_->setNextErrorResponse(error_codes::kInvalidRequest,
        QStringLiteral("plan not found"));
    vm_->runForgetPreviewPipeline(
        kDemoUserId, QStringLiteral("reset-plan-stage"),
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-x"), {}, {}, {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    // 现在 Execute（非 awaiting_confirmation）→ 应立即失败
    vm_->runForgetExecutePipeline(
        kDemoUserId, QStringLiteral("reset-plan-stage"),
        QStringLiteral("any-credential"), {}, {});
    QCOMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm_->forgetExecuteError().contains("prior successful forget.preview"));
}

// ── G. 独立 pending / 未连接拒绝 ────────────────────────────────────────────

void TestD10CForgetting::previewRejects_whenNotConnected()
{
    // 临时断开
    vm_->disconnectFromService();
    QTRY_COMPARE(vm_->connectionState(), QStringLiteral("disconnected"));
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QCOMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm_->forgetPreviewError().contains("not connected"));
    // 恢复连接（对下一 test 友好）
    vm_->connectToService();
    QTRY_COMPARE(vm_->connectionState(), QStringLiteral("connected"));
}

void TestD10CForgetting::previewAndExecuteBusy_flagsAreIndependent()
{
    // 发送 Preview（设置 busy）时 Execute 不应被视为 busy
    // 用一个 delayed response：先不设置 server_ response，模拟 in-flight
    // 简化测试：直接手动触发 Preview 检查初始状态
    QCOMPARE(vm_->forgetPreviewBusy(), false);
    QCOMPARE(vm_->forgetExecuteBusy(), false);
    // 启动 Preview 但 mock 延迟返回
    server_->delayNextResponse(200);
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    // 短时间窗口内 Preview busy 为 true，Execute busy 仍为 false
    QTest::qWait(30);
    QVERIFY(vm_->forgetPreviewBusy());
    QVERIFY(!vm_->forgetExecuteBusy());
    // 等待响应
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
}

// ── H. UNSUPPORTED_METHOD / error 路由到 failed ───────────────────────────

void TestD10CForgetting::unsupportedMethod_routesToFailed()
{
    // 生产 Gateway 默认不注册 forget.preview → UNSUPPORTED_METHOD
    server_->setNextErrorResponse(error_codes::kUnsupportedMethod,
        QStringLiteral("forget.preview: CANDIDATE / pending ADR."));
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    // 不得产生伪 selection_hash 或 affected_count（默认 0 或空）
    QVERIFY(vm_->forgetSelectionHash().isEmpty());
    QCOMPARE(vm_->forgetAffectedCount(), 0);
}

// ── I. full_reset 携带 target_* → 拒绝 ──────────────────────────────────────

void TestD10CForgetting::fullResetWithTargets_rejected()
{
    // full_reset + target_id = km-x → SEC-FORGET-03 客户端侧拒绝
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("full_reset"),
        QStringLiteral("all"),
        {}, QStringLiteral("km-1"), /*非法：携带 target_* */
        {}, {}, {}, true, false);
    QCOMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm_->forgetPreviewError().contains("full_reset mode must not carry"));
}

// ── J. Hard Delete fail-closed ──────────────────────────────────────────────

void TestD10CForgetting::hardDeleteFailClosed_noAutoDowngrade()
{
    // Preview OK
    server_->setNextResponseData(buildPreviewSuccessData());
    vm_->runForgetPreviewPipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("single_item"),
        QStringLiteral("knowledge"),
        {}, QStringLiteral("km-1"), {}, {}, {}, true, false);
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("awaiting_confirmation"));
    // Hard Delete Execute：服务端返回 error（ADR-016 可信输入来源未接线 → fail-closed）
    server_->setNextErrorResponse(error_codes::kInvalidRequest,
        QStringLiteral("Hard Delete Runtime fail-closed: ADR-016 input source not wired."));
    vm_->runForgetExecutePipeline(
        kDemoUserId, kDemoPlanId,
        QStringLiteral("cred-demo-hard"), {},
        QStringLiteral("hard"));
    QTRY_COMPARE(vm_->forgetStage(), QStringLiteral("failed"));
    QVERIFY(vm_->forgetExecuteError().contains("fail-closed"));
    // 不得报告 completed；executed_count 保持 -1 = 未执行
    QCOMPARE(vm_->forgetExecutedCount(), -1);
}

QTEST_MAIN(TestD10CForgetting)
#include "test_d10c_forgetting.moc"
