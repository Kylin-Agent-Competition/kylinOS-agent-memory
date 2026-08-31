#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QVariantList>
#include <QDateTime>
#include <QTimer>

#include "memory_client.h"
#include "protocol_adapter.h"

namespace kylin::memory::client::v1 {

// ============================================================================
// MemoryViewModel — QML 公共 ViewModel（D5-C 垂直链路 Demo / Prototype 版）
// ============================================================================
//
// 状态：D5 memory-client Demo / Prototype（L0 可运行骨架）。
//
// ⚠️ 重要声明（路线 B — REWORK 修正）：
//   本实现仅为 memory-client 侧的 Pipeline Harness / Demo，用于在 L0 Mock
//   Gateway 或已部署的 Echo/D 轨 Gateway 上演示 Pre-Chat / Post-Turn 的
//   envelope / payload 形状。它 **尚未** 证明接入：真实 AI Assistant Hook、
//   真实 model request、真实 Chat DB / ChatRecord、真实 assistant final message。
//   因此本实现不关闭 C-D5，也不声称 SEC-CTX-01 已完成 Runtime 验证。
//
// 职责（Demo 范围）：
//   (1) Pre-Chat Demo：用户输入 → MemoryQuery → 按正式 MemoryContext 契约
//       解析 envelope.data.context → 注入模型请求文本；严格保证 originalUserText
//       与注入片段分离；空 context / error context 不产生伪 Context。
//   (2) Post-Turn Demo：构造 TurnFinalizedEvent（ADR-010 嵌套 metadata 结构）
//       并以 turn.finalized 发送；**业务** status=error（例如
//       UNSUPPORTED_METHOD）显式进入 failed 阶段。
//   (3) 原文隔离验证：三路独立 QString 提供给 QML。
//
// REWORK 关键修复（对照 Reviewer 4 类主问题）：
//   ✅ 问题1：onResponseReceived 首行解析业务 status，status=error 路由失败路径。
//   ✅ 问题2：MemoryContext 形状严格按 contracts/examples/memory_context.v1.json
//            的 query_id / selected_memory_ids / context_version / token_budget /
//            injection_status / actual_token_count 等正式字段；空 context、
//            error response、malformed context 均不得产生伪标记。
//   ✅ 问题3：头注释 + QML 面板明确降级为 Demo / Prototype，不声明真实链路完成。
//   ✅ 问题4：
//     - 新增 pendingPostTurnRequestId_，不用全局 lastRequestId_ 近似关联
//     - 新增 per-request deadline QTimer（kDefaultDeadlineMs=5000），超时失败
//     - 拆 busy_ → preChatBusy_ + postTurnBusy_，避免多请求竞态
//     - injection failure 落实 injection_status=failed（见 data.context 解析）
//     - sendTurnFinalizedEvent 按 ADR-010 路由 turn.finalized；payload 按
//       ADR-010 嵌套 metadata + 事件字段；移除旧 {event_type,event_body} wrapper；
//       trace_id 唯一真源：envelope.trace_id == metadata.trace_id；
//       memory.store 保持 UNSUPPORTED
//     - 移除超出 C-D5 范围的 sendToolExecutionEvent
// ============================================================================

class MemoryViewModel : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString socketPath READ socketPath WRITE setSocketPath
                   NOTIFY socketPathChanged)
    Q_PROPERTY(QString connectionState READ connectionState
                   NOTIFY connectionStateChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    Q_PROPERTY(QString lastRequestId READ lastRequestId NOTIFY lastRequestIdChanged)
    Q_PROPERTY(QJsonObject lastResponse READ lastResponse NOTIFY lastResponseChanged)
    Q_PROPERTY(bool preChatBusy READ preChatBusy NOTIFY preChatBusyChanged)
    Q_PROPERTY(bool postTurnBusy READ postTurnBusy NOTIFY postTurnBusyChanged)
    // HIGH 修复：向后兼容通用"any busy"属性。等价于 preChatBusy || postTurnBusy，
    // 避免旧页（main/Status/MemoryQuery）继续引用已不存在的全局 busy_。
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)

    // ── D5-C Pre-Chat 原文隔离三路口径 ─────────────────────────────────
    // ① UI / 聊天库展示：始终是用户原始输入文本，不含任何 Memory Context。
    Q_PROPERTY(QString originalUserText READ originalUserText
                   NOTIFY originalUserTextChanged)
    // ② 发送给模型的请求文本：用户原文 + Memory Context（仅当 context 合法非空）。
    Q_PROPERTY(QString modelRequestText READ modelRequestText
                   NOTIFY modelRequestTextChanged)
    // ③ 注入的 Memory Context 片段（纯诊断/验证用，便于 QML 校验 "不污染 UI/DB"）。
    Q_PROPERTY(QString injectedContextText READ injectedContextText
                   NOTIFY injectedContextTextChanged)
    // Pre-Chat 当前阶段：idle / querying / timeout / ready / failed
    Q_PROPERTY(QString preChatStage READ preChatStage NOTIFY preChatStageChanged)

    // ── D5-C Post-Turn 事件口径 ────────────────────────────────────────
    // 最近一次构造（或发送）的 TurnFinalizedEvent JSON 字符串（展示/审计）。
    Q_PROPERTY(QString lastTurnFinalizedEvent READ lastTurnFinalizedEvent
                   NOTIFY lastTurnFinalizedEventChanged)
    // Post-Turn 当前阶段：idle / sending / timeout / sent / failed
    Q_PROPERTY(QString postTurnStage READ postTurnStage NOTIFY postTurnStageChanged)

    // ── D5-C 原文隔离验证辅助 ───────────────────────────────────────────
    // 是否验证通过：originalUserText 不含 injectedContextText 任意标记子串。
    // 若 injectedContextText 为空（无记忆），该属性为 true。
    Q_PROPERTY(bool textIsolationVerified READ textIsolationVerified
                   NOTIFY textIsolationVerifiedChanged)

    // ── D6-C 多源 Adapter Pipeline（Demo / Prototype） ──────────────────
    // Tool Adapter
    Q_PROPERTY(QString lastToolEvent READ lastToolEvent
                   NOTIFY lastToolEventChanged)
    Q_PROPERTY(QString toolStage READ toolStage NOTIFY toolStageChanged)
    Q_PROPERTY(bool toolBusy READ toolBusy NOTIFY toolBusyChanged)
    // Manual Config
    Q_PROPERTY(QString lastManualConfigEvent READ lastManualConfigEvent
                   NOTIFY lastManualConfigEventChanged)
    Q_PROPERTY(QString manualConfigStage READ manualConfigStage
                   NOTIFY manualConfigStageChanged)
    Q_PROPERTY(bool manualConfigBusy READ manualConfigBusy
                   NOTIFY manualConfigBusyChanged)
    // Behavior Observe
    Q_PROPERTY(QString lastBehaviorEvent READ lastBehaviorEvent
                   NOTIFY lastBehaviorEventChanged)
    Q_PROPERTY(QString behaviorStage READ behaviorStage
                   NOTIFY behaviorStageChanged)
    Q_PROPERTY(bool behaviorBusy READ behaviorBusy NOTIFY behaviorBusyChanged)

    // ── D7-C 偏好版本管理 Pipeline（Demo / Prototype） ───────────────────
    // Preference Commit
    Q_PROPERTY(QString lastPreferenceCommitEvent READ lastPreferenceCommitEvent
                   NOTIFY lastPreferenceCommitEventChanged)
    Q_PROPERTY(QString preferenceCommitStage READ preferenceCommitStage
                   NOTIFY preferenceCommitStageChanged)
    Q_PROPERTY(bool preferenceCommitBusy READ preferenceCommitBusy
                   NOTIFY preferenceCommitBusyChanged)
    // Preference History
    Q_PROPERTY(QString lastPreferenceHistoryEvent READ lastPreferenceHistoryEvent
                   NOTIFY lastPreferenceHistoryEventChanged)
    Q_PROPERTY(QString preferenceHistoryStage READ preferenceHistoryStage
                   NOTIFY preferenceHistoryStageChanged)
    Q_PROPERTY(bool preferenceHistoryBusy READ preferenceHistoryBusy
                   NOTIFY preferenceHistoryBusyChanged)
    // Preference Rollback
    Q_PROPERTY(QString lastPreferenceRollbackEvent READ lastPreferenceRollbackEvent
                   NOTIFY lastPreferenceRollbackEventChanged)
    Q_PROPERTY(QString preferenceRollbackStage READ preferenceRollbackStage
                   NOTIFY preferenceRollbackStageChanged)
    Q_PROPERTY(bool preferenceRollbackBusy READ preferenceRollbackBusy
                   NOTIFY preferenceRollbackBusyChanged)

public:
    explicit MemoryViewModel(QObject* parent = nullptr);
    ~MemoryViewModel() override;

    MemoryViewModel(const MemoryViewModel&) = delete;
    MemoryViewModel& operator=(const MemoryViewModel&) = delete;

    [[nodiscard]] QString socketPath() const;
    void setSocketPath(const QString& path);

    [[nodiscard]] QString connectionState() const;
    [[nodiscard]] QString lastError() const;
    [[nodiscard]] QString lastRequestId() const { return lastRequestId_; }
    [[nodiscard]] QJsonObject lastResponse() const { return lastResponse_; }
    [[nodiscard]] bool preChatBusy() const { return preChatBusy_; }
    [[nodiscard]] bool postTurnBusy() const { return postTurnBusy_; }
    // D6-C / D7-C 扩展：八 busy 合并兼容属性
    // （PreChat / PostTurn / Tool / ManualConfig / Behavior /
    //  PreferenceCommit / PreferenceHistory / PreferenceRollback）
    [[nodiscard]] bool busy() const {
        return preChatBusy_ || postTurnBusy_
            || toolBusy_ || manualConfigBusy_ || behaviorBusy_
            || preferenceCommitBusy_ || preferenceHistoryBusy_
            || preferenceRollbackBusy_;
    }

    // D5-C Getter
    [[nodiscard]] QString originalUserText() const { return originalUserText_; }
    [[nodiscard]] QString modelRequestText() const { return modelRequestText_; }
    [[nodiscard]] QString injectedContextText() const { return injectedContextText_; }
    [[nodiscard]] QString preChatStage() const { return preChatStage_; }
    [[nodiscard]] QString lastTurnFinalizedEvent() const { return lastTurnFinalizedEvent_; }
    [[nodiscard]] QString postTurnStage() const { return postTurnStage_; }
    [[nodiscard]] bool textIsolationVerified() const;

    // ── D6-C 多源 Adapter getters ───────────────────────────────────────
    [[nodiscard]] QString lastToolEvent() const { return lastToolEvent_; }
    [[nodiscard]] QString toolStage() const { return toolStage_; }
    [[nodiscard]] bool toolBusy() const { return toolBusy_; }
    [[nodiscard]] QString lastManualConfigEvent() const { return lastManualConfigEvent_; }
    [[nodiscard]] QString manualConfigStage() const { return manualConfigStage_; }
    [[nodiscard]] bool manualConfigBusy() const { return manualConfigBusy_; }
    [[nodiscard]] QString lastBehaviorEvent() const { return lastBehaviorEvent_; }
    [[nodiscard]] QString behaviorStage() const { return behaviorStage_; }
    [[nodiscard]] bool behaviorBusy() const { return behaviorBusy_; }

    // ── D7-C 偏好版本管理 getters ──────────────────────────────────────
    [[nodiscard]] QString lastPreferenceCommitEvent() const { return lastPreferenceCommitEvent_; }
    [[nodiscard]] QString preferenceCommitStage() const { return preferenceCommitStage_; }
    [[nodiscard]] bool preferenceCommitBusy() const { return preferenceCommitBusy_; }
    [[nodiscard]] QString lastPreferenceHistoryEvent() const { return lastPreferenceHistoryEvent_; }
    [[nodiscard]] QString preferenceHistoryStage() const { return preferenceHistoryStage_; }
    [[nodiscard]] bool preferenceHistoryBusy() const { return preferenceHistoryBusy_; }
    [[nodiscard]] QString lastPreferenceRollbackEvent() const { return lastPreferenceRollbackEvent_; }
    [[nodiscard]] QString preferenceRollbackStage() const { return preferenceRollbackStage_; }
    [[nodiscard]] bool preferenceRollbackBusy() const { return preferenceRollbackBusy_; }

    // QML 可调用动作。
    Q_INVOKABLE void connectToService();
    Q_INVOKABLE void disconnectFromService();
    Q_INVOKABLE void sendHealth();
    // 发送 memory.retrieve 请求。payload 由调用方构造，本骨架不做业务校验。
    Q_INVOKABLE void sendMemoryQuery(const QJsonObject& payload);

    // ── D5-C Pre-Chat Pipeline ─────────────────────────────────────────
    Q_INVOKABLE void runPreChatPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& scene,
        int maxContextTokens,
        const QString& userOriginalText);

    // 手动重置 Pre-Chat（取消 in-flight 请求 + 清零三路口径）。
    Q_INVOKABLE void resetPreChatPipeline();

    // ── D5-C Post-Turn Pipeline ────────────────────────────────────────
    Q_INVOKABLE void runPostTurnPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& traceId,
        const QString& finalMessageId,
        const QString& finalAssistantText,
        const QString& finalizationReason,
        const QString& stopReason);

    // 构造 TurnFinalizedEvent JSON（可预览可发送复用；Preview→Send 走缓存）。
    // retryOfTurnId：finalization_reason=retry 时必须提供，显式注入 metadata.retry_of_turn_id。
    Q_INVOKABLE QJsonObject buildTurnFinalizedEventJson(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& traceId,
        const QString& finalMessageId,
        const QString& finalAssistantText,
        const QString& finalizationReason,
        const QString& stopReason,
        const QString& retryOfTurnId = {});

    // ── D6-C 多源 Adapter Pipeline ─────────────────────────────────────
    // Tool Adapter：executionStatus ∈ {"success","partial","failure",
    //                                    "cancelled","timeout"}
    // toolCallId / toolName / argumentsRef / resultRef 由调用方提供；
    // ViewModel 构造 ToolExecutionEvent JSON 并发送 tool.execution。
    Q_INVOKABLE void runToolPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& toolCallId,
        const QString& toolName,
        const QString& executionStatus,
        const QString& argumentsRef,
        const QString& resultRef,
        const QString& errorType,
        const QString& errorMessageSafe,
        bool sideEffect,
        bool rollbackRequired);

    // 构造 ToolExecutionEvent JSON（可预览可发送复用）。
    Q_INVOKABLE QJsonObject buildToolExecutionEventJson(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& toolCallId,
        const QString& toolName,
        const QString& executionStatus,
        const QString& argumentsRef,
        const QString& resultRef,
        const QString& errorType,
        const QString& errorMessageSafe,
        bool sideEffect,
        bool rollbackRequired);

    // 手动配置：scope / key / value；isTemporary / shouldPersist 控制生命周期；
    // sensitivityLevel ∈ {"none","low","medium","high","critical"}；
    // high/critical → 客户端侧预检拒绝发送，manualConfigStage=failed。
    Q_INVOKABLE void runManualConfigPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& scope,
        const QString& key,
        const QString& value,
        bool isTemporary,
        bool shouldPersist,
        const QString& sensitivityLevel,
        double confidence);

    // 行为观察：behaviorKind ∈ {"user_message","agent_response","system_message",
    //                            "user_action"}；actor ∈ {"user","agent","system"}；
    // mapping_status 固定 "PENDING_C_CONFIRMATION"（C 轨未冻结 behavior→source_type）。
    Q_INVOKABLE void runBehaviorPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& behaviorKind,
        const QString& observedAction,
        const QString& contextRef,
        const QString& actor);

    // ── D7-C 偏好版本管理 Pipeline ─────────────────────────────────────
    // Commit：scope / key / value / memory_status / sensitivity_level。
    // sensitivityLevel ∈ {"none","low","medium","high","critical"}；
    // high/critical → 客户端侧预检拒绝发送，preferenceCommitStage=failed。
    // 对齐 D7D save_preference_version（候选 IPC 方法 preference.version.commit）。
    Q_INVOKABLE void runPreferenceCommitPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& scope,
        const QString& key,
        const QString& value,
        bool isTemporary,
        bool shouldPersist,
        const QString& memoryStatus,
        const QString& sensitivityLevel,
        double confidence);

    // History：查询偏好版本链。
    // includeHistory=true 时返回含 superseded 的全版本链。
    // 对齐 D7D list_preference_versions（候选 IPC 方法 preference.version.history）。
    Q_INVOKABLE void runPreferenceHistoryPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& scope,
        const QString& key,
        bool includeHistory);

    // Rollback：回滚到目标历史版本。
    // targetVersionId 为 D7D memory_versions.id（int）；客户端以字符串传输，
    // 由服务端校验存在性 / 跨用户隔离 / 链内历史版本约束。
    // 对齐 D7D rollback_preference_version（候选 IPC 方法 preference.version.rollback）。
    Q_INVOKABLE void runPreferenceRollbackPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& scope,
        const QString& key,
        const QString& targetVersionId);

    // 原文隔离验证
    Q_INVOKABLE bool verifyOriginalTextIsolation() const;

signals:
    void socketPathChanged();
    void connectionStateChanged();
    void lastErrorChanged();
    void lastRequestIdChanged();
    void lastResponseChanged();
    void preChatBusyChanged();
    void postTurnBusyChanged();
    void busyChanged();

    // D5-C 信号
    void originalUserTextChanged();
    void modelRequestTextChanged();
    void injectedContextTextChanged();
    void preChatStageChanged();
    void lastTurnFinalizedEventChanged();
    void postTurnStageChanged();
    void textIsolationVerifiedChanged();

    // D6-C 多源 Adapter 信号
    void lastToolEventChanged();
    void toolStageChanged();
    void toolBusyChanged();
    void lastManualConfigEventChanged();
    void manualConfigStageChanged();
    void manualConfigBusyChanged();
    void lastBehaviorEventChanged();
    void behaviorStageChanged();
    void behaviorBusyChanged();

    // D7-C 偏好版本管理信号
    void lastPreferenceCommitEventChanged();
    void preferenceCommitStageChanged();
    void preferenceCommitBusyChanged();
    void lastPreferenceHistoryEventChanged();
    void preferenceHistoryStageChanged();
    void preferenceHistoryBusyChanged();
    void lastPreferenceRollbackEventChanged();
    void preferenceRollbackStageChanged();
    void preferenceRollbackBusyChanged();

    void requestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);
    void connectionError(const QString& safeMessage);

private slots:
    void onConnectionStateChanged();
    void onLastErrorChanged();
    void onResponseReceived(const QString& requestId, const QJsonObject& envelope);
    void onRequestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);
    void onConnectionError(const QString& safeMessage);

private:
    void setLastRequestId(const QString& id);
    void setLastResponse(const QJsonObject& envelope);

    // D5-C 私有 setter
    void setOriginalUserText(const QString& value);
    void setModelRequestText(const QString& value);
    void setInjectedContextText(const QString& value);
    void setPreChatStage(const QString& value);
    void setLastTurnFinalizedEvent(const QString& value);
    void setPostTurnStage(const QString& value);
    void setPreChatBusy(bool value);
    void setPostTurnBusy(bool value);

    // D6-C 私有 setter
    void setLastToolEvent(const QString& value);
    void setToolStage(const QString& value);
    void setToolBusy(bool value);
    void setLastManualConfigEvent(const QString& value);
    void setManualConfigStage(const QString& value);
    void setManualConfigBusy(bool value);
    void setLastBehaviorEvent(const QString& value);
    void setBehaviorStage(const QString& value);
    void setBehaviorBusy(bool value);

    // D7-C 私有 setter
    void setLastPreferenceCommitEvent(const QString& value);
    void setPreferenceCommitStage(const QString& value);
    void setPreferenceCommitBusy(bool value);
    void setLastPreferenceHistoryEvent(const QString& value);
    void setPreferenceHistoryStage(const QString& value);
    void setPreferenceHistoryBusy(bool value);
    void setLastPreferenceRollbackEvent(const QString& value);
    void setPreferenceRollbackStage(const QString& value);
    void setPreferenceRollbackBusy(bool value);

    // D6-C 共享：构造 metadata 嵌套对象（schema_version/event_id/.../source_reference）。
    QJsonObject buildEventMetadata(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& traceId,
        const QString& idempotencyKey,
        const QString& sourceReference) const;

    // 问题1修复：解析 envelope → ResponseParts；若 status=="error"，提取
    // errorCode/message 并返回 false。输出参数返回 parseResponse 结果引用。
    [[nodiscard]] bool tryParseResponseStatus(const QJsonObject& envelope,
                                              ResponseParts* outParts,
                                              QString* outErrorCode,
                                              QString* outErrorMessage) const;

    // 问题2修复：严格按 memory_context.v1.json 正式契约解析 context 对象。
    // 仅当 context 完整且 injection_status 非 "failed" / "skipped" 且
    // selected_memory_ids 非空（或 actual_token_count > 0）时生成展示文本，
    // 空 context / error context / malformed context 一律返回空串。
    QString buildContextTextFromContextObject(const QJsonObject& context) const;

    // 旧的 envelope 版辅助保留（仅内部转发到 tryParseResponseStatus + buildContextTextFromContextObject）
    QString buildContextTextFromResponse(const QJsonObject& envelope) const;

    QString nowIso8601UtcMs() const;

    // 启动/取消 per-request 死线计时器
    void armDeadlineTimer(const QString& requestId, int deadlineMs);
    void cancelDeadlineTimerFor(const QString& requestId);

    MemoryClient client_;
    QString lastRequestId_;
    QJsonObject lastResponse_;

    // 问题4修复：拆分为双 busy + 独立 pendingRequestId，避免 Reset / 多请求竞态
    bool preChatBusy_ = false;
    bool postTurnBusy_ = false;

    QString originalUserText_;
    QString modelRequestText_;
    QString injectedContextText_;
    QString preChatStage_ = QStringLiteral("idle");

    QString lastTurnFinalizedEvent_;
    QString postTurnStage_ = QStringLiteral("idle");

    QString pendingPreChatRequestId_;
    QString pendingPostTurnRequestId_;  // 问题4修复：独立 PostTurn pending
    int pendingPreChatMaxTokens_ = 800;

    // ── D6-C 多源 Adapter 状态（四 busy 独立 pending，沿用 D5 REWORK §C1 模式） ─
    bool toolBusy_ = false;
    bool manualConfigBusy_ = false;
    bool behaviorBusy_ = false;

    QString lastToolEvent_;
    QString toolStage_ = QStringLiteral("idle");
    QString lastManualConfigEvent_;
    QString manualConfigStage_ = QStringLiteral("idle");
    QString lastBehaviorEvent_;
    QString behaviorStage_ = QStringLiteral("idle");

    QString pendingToolRequestId_;
    QString pendingManualConfigRequestId_;
    QString pendingBehaviorRequestId_;

    // ── D7-C 偏好版本管理状态（三 busy 独立 pending，沿用 D6-C §C1 模式） ──
    bool preferenceCommitBusy_ = false;
    bool preferenceHistoryBusy_ = false;
    bool preferenceRollbackBusy_ = false;

    QString lastPreferenceCommitEvent_;
    QString preferenceCommitStage_ = QStringLiteral("idle");
    QString lastPreferenceHistoryEvent_;
    QString preferenceHistoryStage_ = QStringLiteral("idle");
    QString lastPreferenceRollbackEvent_;
    QString preferenceRollbackStage_ = QStringLiteral("idle");

    QString pendingPreferenceCommitRequestId_;
    QString pendingPreferenceHistoryRequestId_;
    QString pendingPreferenceRollbackRequestId_;

    // 问题4修复：per-request deadline timer（超时→ requestFailed TIMEOUT）
    // key = requestId；超时后由单例 QTimer 回调，统一在 onRequestFailed 路径处理。
    struct DeadlineRecord {
        QTimer* timer = nullptr;  // owned by this object
        int deadlineMs = 0;
    };
    QHash<QString, DeadlineRecord> deadlineTimers_;

    // 非阻断项修复：Preview / Send 复用同一事件对象缓存，避免 event_id 漂移。
    // key = 规范化参数哈希（此处简单用 "user+session+turn+trace+msg+reason+stop"）。
    QJsonObject cachedTurnEvent_;
    QStringList cachedTurnEventKey_;
};

}  // namespace kylin::memory::client::v1
