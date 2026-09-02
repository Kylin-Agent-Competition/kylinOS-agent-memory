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
    // D12-C：重连统计 + Retry 按钮支持
    Q_PROPERTY(int reconnectAttempts READ reconnectAttempts
                   NOTIFY reconnectAttemptsChanged)
    Q_PROPERTY(bool autoReconnectEnabled READ autoReconnectEnabled
                   WRITE setAutoReconnectEnabled NOTIFY autoReconnectEnabledChanged)
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

    // ── D7C 偏好编辑（版本历史与回滚）────────────────────────────────
    // preference.list 结果：条目列表（每项含 current 版本投影）。
    Q_PROPERTY(QVariantList preferenceItems READ preferenceItems
                   NOTIFY preferenceItemsChanged)
    // preference.history 结果：单个 (key,scope) 的完整版本链（含 superseded）。
    Q_PROPERTY(QVariantList preferenceHistory READ preferenceHistory
                   NOTIFY preferenceHistoryChanged)
    Q_PROPERTY(bool preferenceBusy READ preferenceBusy
                   NOTIFY preferenceBusyChanged)
    Q_PROPERTY(QString preferenceError READ preferenceError
                   NOTIFY preferenceErrorChanged)
    // preference 阶段：idle / loading / saving / rolled_back / ready / failed
    Q_PROPERTY(QString preferenceStage READ preferenceStage
                   NOTIFY preferenceStageChanged)
    // 最近一次写响应 action：create / update / rollback / no_op / 空
    Q_PROPERTY(QString lastPreferenceAction READ lastPreferenceAction
                   NOTIFY lastPreferenceActionChanged)
    // 最近一次写响应 item（版本投影）。
    Q_PROPERTY(QJsonObject lastPreferenceItem READ lastPreferenceItem
                   NOTIFY lastPreferenceItemChanged)


    // ── D8C 知识详情 / 冲突对比 / 生命周期状态 Pipeline（Demo / Prototype）──
    // 知识详情：knowledge.detail 返回的单条记忆证据/适用条件投影
    Q_PROPERTY(bool knowledgeDetailBusy READ knowledgeDetailBusy
                   NOTIFY knowledgeDetailBusyChanged)
    Q_PROPERTY(QString knowledgeDetailStage READ knowledgeDetailStage
                   NOTIFY knowledgeDetailStageChanged)
    Q_PROPERTY(QJsonObject knowledgeDetail READ knowledgeDetail
                   NOTIFY knowledgeDetailChanged)
    Q_PROPERTY(QString knowledgeDetailError READ knowledgeDetailError
                   NOTIFY knowledgeDetailErrorChanged)
    // 冲突对比：conflict.compare 返回的候选列表投影
    Q_PROPERTY(bool conflictCompareBusy READ conflictCompareBusy
                   NOTIFY conflictCompareBusyChanged)
    Q_PROPERTY(QString conflictCompareStage READ conflictCompareStage
                   NOTIFY conflictCompareStageChanged)
    Q_PROPERTY(QVariantList conflictCandidates READ conflictCandidates
                   NOTIFY conflictCandidatesChanged)
    Q_PROPERTY(QString conflictCompareError READ conflictCompareError
                   NOTIFY conflictCompareErrorChanged)
    // 生命周期状态：lifecycle.status 返回的条目列表投影
    Q_PROPERTY(bool lifecycleStatusBusy READ lifecycleStatusBusy
                   NOTIFY lifecycleStatusBusyChanged)
    Q_PROPERTY(QString lifecycleStatusStage READ lifecycleStatusStage
                   NOTIFY lifecycleStatusStageChanged)
    Q_PROPERTY(QVariantList lifecycleItems READ lifecycleItems
                   NOTIFY lifecycleItemsChanged)
    Q_PROPERTY(QString lifecycleStatusError READ lifecycleStatusError
                   NOTIFY lifecycleStatusErrorChanged)

    // ── D9C Memory Context 组装 Pipeline（Demo / Prototype） ────────────
    // context.assemble 返回的组装 MemoryContext 投影（含可解释字段与 Token 预算校验）。
    // 注：响应严格按 envelope.data 解析；空 context / status=error / malformed
    // 一律不产生伪 assembledContext（沿用 D5 Pre-Chat 防伪 Context 模式）。
    Q_PROPERTY(bool contextAssembleBusy READ contextAssembleBusy
                   NOTIFY contextAssembleBusyChanged)
    Q_PROPERTY(QString contextAssembleStage READ contextAssembleStage
                   NOTIFY contextAssembleStageChanged)
    // 组装结果整体 JSON（含 selected_memory_ids / recall_sources / memory_types /
    // conflict_hints / uncertainty_hints / token_budget / actual_token_count /
    // budget_exceeded / injection_status）。
    Q_PROPERTY(QJsonObject assembledContext READ assembledContext
                   NOTIFY assembledContextChanged)
    // 召回来源（通道）列表：fts5 / vector / rrf 等。
    Q_PROPERTY(QVariantList contextRecallSources READ contextRecallSources
                   NOTIFY contextRecallSourcesChanged)
    // 记忆类型分布列表（每项为 type 字符串或 {type,count} 对象，由 Mock 提供形状）。
    Q_PROPERTY(QVariantList contextMemoryTypes READ contextMemoryTypes
                   NOTIFY contextMemoryTypesChanged)
    // 冲突提示列表（候选中带未解决/已解决冲突的 memory_id 与 conflict_state）。
    Q_PROPERTY(QVariantList contextConflictHints READ contextConflictHints
                   NOTIFY contextConflictHintsChanged)
    // 不确定性提示列表（降级通道 / 陈旧索引 / score_semantics 未验证等）。
    Q_PROPERTY(QVariantList contextUncertaintyHints READ contextUncertaintyHints
                   NOTIFY contextUncertaintyHintsChanged)
    // Token 预算校验：actual_token_count / token_budget / budget_exceeded。
    Q_PROPERTY(int contextTokenBudget READ contextTokenBudget
                   NOTIFY contextTokenBudgetChanged)
    Q_PROPERTY(int contextActualTokenCount READ contextActualTokenCount
                   NOTIFY contextActualTokenCountChanged)
    Q_PROPERTY(bool contextBudgetExceeded READ contextBudgetExceeded
                   NOTIFY contextBudgetExceededChanged)
    Q_PROPERTY(QString contextInjectionStatus READ contextInjectionStatus
                   NOTIFY contextInjectionStatusChanged)
    Q_PROPERTY(QString contextAssembleError READ contextAssembleError
                   NOTIFY contextAssembleErrorChanged)

    // ── D10C 精准遗忘 Pipeline（Demo / Prototype） ──────────────────────
    // forget.preview + forget.execute（CANDIDATE / pending ADR；业务契约已冻结，
    // Hard/Cascade/Full Reset Runtime Execute fail-closed 至跨轨闭环 + 麒麟L2）。
    // 状态机（v0.2 冻结）：idle → previewing → awaiting_confirmation → executing
    //                    → completed / failed / rolled_back
    // ⚠️  本 ViewModel 仅为客户端侧 Pipeline Harness，不实现：
    //     - D 轨 SQLite Forget 事务与确认令牌持久化
    //     - B 轨 Vector/FTS5 精确删除与残留率验证
    //     - E 轨 ForgetPlan 业务规则解析与安全 Gate
    //     因此本实现不关闭 C-D10，也不宣称完整精准遗忘能力已 Runtime 验证。
    Q_PROPERTY(bool forgetPreviewBusy READ forgetPreviewBusy
                   NOTIFY forgetPreviewBusyChanged)
    Q_PROPERTY(bool forgetExecuteBusy READ forgetExecuteBusy
                   NOTIFY forgetExecuteBusyChanged)
    Q_PROPERTY(QString forgetStage READ forgetStage NOTIFY forgetStageChanged)
    // Preview 结果：selection_hash + affected_count + credential_ttl_s + 敏感提示
    Q_PROPERTY(QString forgetSelectionHash READ forgetSelectionHash
                   NOTIFY forgetSelectionHashChanged)
    Q_PROPERTY(int forgetAffectedCount READ forgetAffectedCount
                   NOTIFY forgetAffectedCountChanged)
    Q_PROPERTY(int forgetCredentialTtlSeconds READ forgetCredentialTtlSeconds
                   NOTIFY forgetCredentialTtlSecondsChanged)
    // Preview 返回的一次性确认凭据（绑定 userId+forgetPlanId+selection_hash，具备TTL）。
    // Execute 必须传入与该值完全匹配的 confirmation_token，否则 fail-closed。
    Q_PROPERTY(QString forgetConfirmationCredential READ forgetConfirmationCredential
                   NOTIFY forgetConfirmationCredentialChanged)
    // 预览命中目标 ID 列表（Demo 展示影响范围；仅 ID 切片，不含正文）
    Q_PROPERTY(QVariantList forgetResolvedTargets READ forgetResolvedTargets
                   NOTIFY forgetResolvedTargetsChanged)
    // 当前计划 forget_mode / target_type / is_cascade（展示确认上下文）
    Q_PROPERTY(QString forgetMode READ forgetMode NOTIFY forgetModeChanged)
    Q_PROPERTY(QString forgetTargetType READ forgetTargetType
                   NOTIFY forgetTargetTypeChanged)
    Q_PROPERTY(bool forgetIsCascade READ forgetIsCascade NOTIFY forgetIsCascadeChanged)
    // 敏感提示：高敏感 / 批量 / full_reset / cascade 的显式警告
    Q_PROPERTY(QString forgetSensitivityWarning READ forgetSensitivityWarning
                   NOTIFY forgetSensitivityWarningChanged)
    // Execute 结果：executed_count / affected_count 一致性校验
    Q_PROPERTY(int forgetExecutedCount READ forgetExecutedCount
                   NOTIFY forgetExecutedCountChanged)
    // 执行是否漏删：executed_count != affected_count → 不得报 completed
    Q_PROPERTY(bool forgetHasMissingDeletes READ forgetHasMissingDeletes
                   NOTIFY forgetHasMissingDeletesChanged)
    // 完整 Preview / Execute 响应 JSON（诊断用）
    Q_PROPERTY(QJsonObject forgetPreviewResult READ forgetPreviewResult
                   NOTIFY forgetPreviewResultChanged)
    Q_PROPERTY(QJsonObject forgetExecuteResult READ forgetExecuteResult
                   NOTIFY forgetExecuteResultChanged)
    // 错误消息（不含正文/PII，safe message）
    Q_PROPERTY(QString forgetPreviewError READ forgetPreviewError
                   NOTIFY forgetPreviewErrorChanged)
    Q_PROPERTY(QString forgetExecuteError READ forgetExecuteError
                   NOTIFY forgetExecuteErrorChanged)
    // 跨用户操作拒绝标志：请求 user_id 与响应 user_id 不匹配时为 true
    // （用于 QML 展示「跨用户操作被拒绝」的验收断言）
    Q_PROPERTY(bool forgetCrossUserBlocked READ forgetCrossUserBlocked
                   NOTIFY forgetCrossUserBlockedChanged)
    // Preview 后 target_selector 明文清除状态（§四.8 安全验收）
    Q_PROPERTY(bool forgetSelectorCleared READ forgetSelectorCleared
                   NOTIFY forgetSelectorClearedChanged)

public:
    explicit MemoryViewModel(QObject* parent = nullptr);
    ~MemoryViewModel() override;

    MemoryViewModel(const MemoryViewModel&) = delete;
    MemoryViewModel& operator=(const MemoryViewModel&) = delete;

    [[nodiscard]] QString socketPath() const;
    void setSocketPath(const QString& path);

    [[nodiscard]] QString connectionState() const;
    [[nodiscard]] QString lastError() const;
    // D12-C：重连相关
    [[nodiscard]] int reconnectAttempts() const;
    [[nodiscard]] bool autoReconnectEnabled() const;
    void setAutoReconnectEnabled(bool v);
    [[nodiscard]] QString lastRequestId() const { return lastRequestId_; }
    [[nodiscard]] QJsonObject lastResponse() const { return lastResponse_; }
    [[nodiscard]] bool preChatBusy() const { return preChatBusy_; }
    [[nodiscard]] bool postTurnBusy() const { return postTurnBusy_; }
    // D6-C 扩展：四 busy 合并兼容属性（PreChat / PostTurn / Tool / ManualConfig / Behavior）
    // D8-C 进一步扩展：包含 KnowledgeDetail / ConflictCompare / LifecycleStatus
    // D9-C 进一步扩展：包含 ContextAssemble
    // D10-C 进一步扩展：包含 ForgetPreview / ForgetExecute
    [[nodiscard]] bool busy() const {
        return preChatBusy_ || postTurnBusy_
            || toolBusy_ || manualConfigBusy_ || behaviorBusy_
            || knowledgeDetailBusy_ || conflictCompareBusy_ || lifecycleStatusBusy_
            || contextAssembleBusy_
            || forgetPreviewBusy_ || forgetExecuteBusy_;
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


    // ── D8C getters ─────────────────────────────────────────────────────
    [[nodiscard]] bool knowledgeDetailBusy() const { return knowledgeDetailBusy_; }
    [[nodiscard]] QString knowledgeDetailStage() const { return knowledgeDetailStage_; }
    [[nodiscard]] QJsonObject knowledgeDetail() const { return knowledgeDetail_; }
    [[nodiscard]] QString knowledgeDetailError() const { return knowledgeDetailError_; }
    [[nodiscard]] bool conflictCompareBusy() const { return conflictCompareBusy_; }
    [[nodiscard]] QString conflictCompareStage() const { return conflictCompareStage_; }
    [[nodiscard]] QVariantList conflictCandidates() const { return conflictCandidates_; }
    [[nodiscard]] QString conflictCompareError() const { return conflictCompareError_; }
    [[nodiscard]] bool lifecycleStatusBusy() const { return lifecycleStatusBusy_; }
    [[nodiscard]] QString lifecycleStatusStage() const { return lifecycleStatusStage_; }
    [[nodiscard]] QVariantList lifecycleItems() const { return lifecycleItems_; }
    [[nodiscard]] QString lifecycleStatusError() const { return lifecycleStatusError_; }

    // ── D9C getters ─────────────────────────────────────────────────────
    [[nodiscard]] bool contextAssembleBusy() const { return contextAssembleBusy_; }
    [[nodiscard]] QString contextAssembleStage() const { return contextAssembleStage_; }
    [[nodiscard]] QJsonObject assembledContext() const { return assembledContext_; }
    [[nodiscard]] QVariantList contextRecallSources() const { return contextRecallSources_; }
    [[nodiscard]] QVariantList contextMemoryTypes() const { return contextMemoryTypes_; }
    [[nodiscard]] QVariantList contextConflictHints() const { return contextConflictHints_; }
    [[nodiscard]] QVariantList contextUncertaintyHints() const { return contextUncertaintyHints_; }
    [[nodiscard]] int contextTokenBudget() const { return contextTokenBudget_; }
    [[nodiscard]] int contextActualTokenCount() const { return contextActualTokenCount_; }
    [[nodiscard]] bool contextBudgetExceeded() const { return contextBudgetExceeded_; }
    [[nodiscard]] QString contextInjectionStatus() const { return contextInjectionStatus_; }
    [[nodiscard]] QString contextAssembleError() const { return contextAssembleError_; }

    // ── D10C getters ────────────────────────────────────────────────────
    [[nodiscard]] bool forgetPreviewBusy() const { return forgetPreviewBusy_; }
    [[nodiscard]] bool forgetExecuteBusy() const { return forgetExecuteBusy_; }
    [[nodiscard]] QString forgetStage() const { return forgetStage_; }
    [[nodiscard]] QString forgetSelectionHash() const { return forgetSelectionHash_; }
    [[nodiscard]] int forgetAffectedCount() const { return forgetAffectedCount_; }
    [[nodiscard]] int forgetCredentialTtlSeconds() const { return forgetCredentialTtlSeconds_; }
    [[nodiscard]] QString forgetConfirmationCredential() const { return forgetConfirmationCredential_; }
    [[nodiscard]] QVariantList forgetResolvedTargets() const { return forgetResolvedTargets_; }
    [[nodiscard]] QString forgetMode() const { return forgetMode_; }
    [[nodiscard]] QString forgetTargetType() const { return forgetTargetType_; }
    [[nodiscard]] bool forgetIsCascade() const { return forgetIsCascade_; }
    [[nodiscard]] QString forgetSensitivityWarning() const { return forgetSensitivityWarning_; }
    [[nodiscard]] int forgetExecutedCount() const { return forgetExecutedCount_; }
    [[nodiscard]] bool forgetHasMissingDeletes() const {
        // v0.3/MEDIUM-03：漏删不得报完成
        return forgetAffectedCount_ > 0
               && forgetExecutedCount_ >= 0
               && forgetExecutedCount_ != forgetAffectedCount_;
    }
    [[nodiscard]] QJsonObject forgetPreviewResult() const { return forgetPreviewResult_; }
    [[nodiscard]] QJsonObject forgetExecuteResult() const { return forgetExecuteResult_; }
    [[nodiscard]] QString forgetPreviewError() const { return forgetPreviewError_; }
    [[nodiscard]] QString forgetExecuteError() const { return forgetExecuteError_; }
    [[nodiscard]] bool forgetCrossUserBlocked() const { return forgetCrossUserBlocked_; }
    [[nodiscard]] bool forgetSelectorCleared() const { return forgetSelectorCleared_; }

    // D7C Getter
    [[nodiscard]] QVariantList preferenceItems() const { return preferenceItems_; }
    [[nodiscard]] QVariantList preferenceHistory() const { return preferenceHistory_; }
    [[nodiscard]] bool preferenceBusy() const { return preferenceBusy_; }
    [[nodiscard]] QString preferenceError() const { return preferenceError_; }
    [[nodiscard]] QString preferenceStage() const { return preferenceStage_; }
    [[nodiscard]] QString lastPreferenceAction() const { return lastPreferenceAction_; }
    [[nodiscard]] QJsonObject lastPreferenceItem() const { return lastPreferenceItem_; }

    // QML 可调用动作。
    Q_INVOKABLE void connectToService();
    Q_INVOKABLE void disconnectFromService();
    // D12-C：显式 Retry（Stop+Cleanup+Connect），供 UI "Retry" 按钮使用
    Q_INVOKABLE void retryConnectService();
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
    // 手动重置 Post-Turn 阶段与 busy 标志。
    Q_INVOKABLE void resetPostTurnPipeline();
    // 手动重置 Tool Adapter 阶段与 busy 标志。
    Q_INVOKABLE void resetToolPipeline();
    // 手动重置 Conflict Compare 阶段与 busy 标志。
    Q_INVOKABLE void resetConflictComparePipeline();
    // 手动重置 Lifecycle Status 阶段与 busy 标志。
    Q_INVOKABLE void resetLifecycleStatusPipeline();
    // D11 编排器：一键重置全部 5 条 Pipeline（Pre/Post/Tool/Conflict/Lifecycle/Forget）。
    // 语义：取消所有 in-flight 请求，全部 stage 回到 idle，三路口径清零；
    // 明确不清除 forget*Error 文案（与 resetForgetProjection 契约一致）。
    Q_INVOKABLE void resetAllPipelines();

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

    // ── D7C 偏好编辑（版本历史与回滚）────────────────────────────────
    // 加载当前用户偏好列表（preference.list）。
    Q_INVOKABLE void loadPreferences(const QString& userId);
    // 加载单个 (key,scope) 的完整版本链（preference.history）。
    Q_INVOKABLE void loadPreferenceHistory(
        const QString& userId, const QString& key, const QString& scope);
    // 创建/追加偏好版本（preference.create）。
    Q_INVOKABLE void createPreference(
        const QString& userId,
        const QString& key,
        const QString& scope,
        const QString& value,
        bool isTemporary,
        bool shouldPersist,
        const QString& idempotencyKey);
    // 更新偏好值（preference.update）。
    // isTemporary/shouldPersist 为临时/持久化生命周期标志，必须显式携带：
    // 防止临时偏好因字段缺省在 update 时错误晋升为 active（D3 §7.9，HIGH-01）。
    Q_INVOKABLE void updatePreference(
        const QString& userId,
        const QString& key,
        const QString& scope,
        const QString& newValue,
        bool isTemporary,
        bool shouldPersist,
        const QString& idempotencyKey);
    // 回滚到历史版本（preference.rollback）。
    Q_INVOKABLE void rollbackPreference(
        const QString& userId,
        const QString& key,
        const QString& scope,
        int targetVersion,
        const QString& idempotencyKey);


    // ── D8C 知识详情 / 冲突对比 / 生命周期状态 Pipeline ─────────────────
    // 知识详情：memory_id 必填；include_evidence/include_conditions 默认 true。
    // 响应投影到 knowledgeDetail（含 evidence/conditions 列表）。
    Q_INVOKABLE void runKnowledgeDetailPipeline(
        const QString& memoryId,
        bool includeEvidence,
        bool includeConditions);

    // 冲突对比：memory_id 必填；include_resolved 默认 false（仅未解决冲突）。
    // 响应投影到 conflictCandidates。
    Q_INVOKABLE void runConflictComparePipeline(
        const QString& memoryId,
        bool includeResolved);

    // 生命周期状态：user_id 必填；memory_id/memory_status 可选过滤。
    // 响应投影到 lifecycleItems。
    Q_INVOKABLE void runLifecycleStatusPipeline(
        const QString& userId,
        const QString& memoryId,
        const QString& memoryStatus);

    // ── D9C Memory Context 组装 Pipeline ──────────────────────────────
    // context.assemble：userId + queryText 必填；tokenBudget 必填且 > 0；
    // scene / candidatesJson（B 轨 RetrievalCandidateSample[] 的 JSON 字符串）
    // 由调用方提供；ViewModel 构造 context.assemble payload 并发送。
    // 响应投影到 assembledContext 及子字段（recall_sources / memory_types /
    // conflict_hints / uncertainty_hints / token_budget / actual_token_count /
    // budget_exceeded / injection_status）。
    // 预算校验：actual_token_count > token_budget → budget_exceeded=true，
    //           injection_status=degraded（Mock 决定截断策略；客户端不伪造截断）。
    // 防伪 Context：空 data / status=error / injection_status=failed/skipped
    //              一律不填充 assembledContext（保持空对象）。
    Q_INVOKABLE void runContextAssemblePipeline(
        const QString& userId,
        const QString& queryText,
        int tokenBudget,
        const QString& scene,
        const QString& candidatesJson);

    // ── D10C 精准遗忘 Pipeline（Demo / Prototype） ──────────────────────
    // forget.preview：构造 ForgetPlan payload 并发送 forget.preview。
    // 必填校验：userId / forgetPlanId / forgetMode / targetType；
    // 模式互斥（SEC-FORGET-03）：按 forgetMode 只接受对应 target_*，
    //   single_item→targetId, session→targetSessionId, topic→targetTopic,
    //   time_window→targetTimeRange, full_reset→无任何 target_*（携带拒绝）。
    // 跨用户拦截（客户端预检）：若请求携带的 selectorUserId 与响应
    //   data.user_id 不匹配 → forgetCrossUserBlocked=true，stage=failed。
    // 客户端侧明文清除（§四.8 HIGH-01）：Preview 成功后清空本 ViewModel
    //   保存的 targetSelector / targetTopic（若为 Demo 态存储），
    //   并将 forgetSelectorCleared=true（展示清除状态）。
    Q_INVOKABLE void runForgetPreviewPipeline(
        const QString& userId,
        const QString& forgetPlanId,
        const QString& forgetMode,
        const QString& targetType,
        const QString& targetSelector,
        const QString& targetId,
        const QString& targetSessionId,
        const QString& targetTopic,
        const QString& targetTimeRange,
        bool requiresConfirmation,
        bool isCascade);

    // forget.execute：携带 forgetPlanId + confirmationToken（一次性确认凭据）
    // 执行遗忘。idempotencyKey 可选（复用 FRZ-IPC-005 三元组）；
    // deleteMode ∈ {soft,hard}（hard 在 ADR-016 可信输入接线前 fail-closed）。
    // 漏删保护（v0.3/MEDIUM-03）：Execute 返回 executed_count 与
    //   affected_count 不一致 → forgetHasMissingDeletes=true，stage 进入
    //   failed（不得报 completed，闭合「漏删不得报完成」）。
    Q_INVOKABLE void runForgetExecutePipeline(
        const QString& userId,
        const QString& forgetPlanId,
        const QString& confirmationToken,
        const QString& idempotencyKey,
        const QString& deleteMode);

    // 原文隔离验证
    Q_INVOKABLE bool verifyOriginalTextIsolation() const;

signals:
    void socketPathChanged();
    void connectionStateChanged();
    void lastErrorChanged();
    // D12-C：重连相关信号
    void reconnectAttemptsChanged();
    void autoReconnectEnabledChanged();
    // D12-C MEDIUM-02：转发 reconnectFinished 事件（成功 or 达到上限），便于 QML 弹 toast / 结束动画
    void reconnectFinished(bool success, int attempts);
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

    // D7C 信号
    void preferenceItemsChanged();
    void preferenceHistoryChanged();
    void preferenceBusyChanged();
    void preferenceErrorChanged();
    void preferenceStageChanged();
    void lastPreferenceActionChanged();
    void lastPreferenceItemChanged();

    // D8C 信号
    void knowledgeDetailBusyChanged();
    void knowledgeDetailStageChanged();
    void knowledgeDetailChanged();
    void knowledgeDetailErrorChanged();
    void conflictCompareBusyChanged();
    void conflictCompareStageChanged();
    void conflictCandidatesChanged();
    void conflictCompareErrorChanged();
    void lifecycleStatusBusyChanged();
    void lifecycleStatusStageChanged();
    void lifecycleItemsChanged();
    void lifecycleStatusErrorChanged();

    // D9C 信号
    void contextAssembleBusyChanged();
    void contextAssembleStageChanged();
    void assembledContextChanged();
    void contextRecallSourcesChanged();
    void contextMemoryTypesChanged();
    void contextConflictHintsChanged();
    void contextUncertaintyHintsChanged();
    void contextTokenBudgetChanged();
    void contextActualTokenCountChanged();
    void contextBudgetExceededChanged();
    void contextInjectionStatusChanged();
    void contextAssembleErrorChanged();

    // D10C 信号
    void forgetPreviewBusyChanged();
    void forgetExecuteBusyChanged();
    void forgetStageChanged();
    void forgetSelectionHashChanged();
    void forgetAffectedCountChanged();
    void forgetCredentialTtlSecondsChanged();
    void forgetConfirmationCredentialChanged();
    void forgetResolvedTargetsChanged();
    void forgetModeChanged();
    void forgetTargetTypeChanged();
    void forgetIsCascadeChanged();
    void forgetSensitivityWarningChanged();
    void forgetExecutedCountChanged();
    void forgetHasMissingDeletesChanged();
    void forgetPreviewResultChanged();
    void forgetExecuteResultChanged();
    void forgetPreviewErrorChanged();
    void forgetExecuteErrorChanged();
    void forgetCrossUserBlockedChanged();
    void forgetSelectorClearedChanged();

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


    // D8C 私有 setter
    void setKnowledgeDetailBusy(bool value);
    void setKnowledgeDetailStage(const QString& value);
    void setKnowledgeDetail(const QJsonObject& value);
    void setKnowledgeDetailError(const QString& value);
    void setConflictCompareBusy(bool value);
    void setConflictCompareStage(const QString& value);
    void setConflictCandidates(const QVariantList& value);
    void setConflictCompareError(const QString& value);
    void setLifecycleStatusBusy(bool value);
    void setLifecycleStatusStage(const QString& value);
    void setLifecycleItems(const QVariantList& value);
    void setLifecycleStatusError(const QString& value);

    // D9C 私有 setter
    void setContextAssembleBusy(bool value);
    void setContextAssembleStage(const QString& value);
    void setAssembledContext(const QJsonObject& value);
    void setContextRecallSources(const QVariantList& value);
    void setContextMemoryTypes(const QVariantList& value);
    void setContextConflictHints(const QVariantList& value);
    void setContextUncertaintyHints(const QVariantList& value);
    void setContextTokenBudget(int value);
    void setContextActualTokenCount(int value);
    void setContextBudgetExceeded(bool value);
    void setContextInjectionStatus(const QString& value);
    void setContextAssembleError(const QString& value);
    // D9C 响应投影：把 data 解析为 assembledContext + 子字段。
    void projectAssembledContext(const QJsonObject& data);
    // D9C 防伪 Context 统一清空（失败路径 / 请求前置调用，I-2 修复）。
    void resetContextProjection();

    // D10C 私有 setter
    void setForgetPreviewBusy(bool value);
    void setForgetExecuteBusy(bool value);
    void setForgetStage(const QString& value);
    void setForgetSelectionHash(const QString& value);
    void setForgetAffectedCount(int value);
    void setForgetCredentialTtlSeconds(int value);
    void setForgetConfirmationCredential(const QString& value);
    void setForgetResolvedTargets(const QVariantList& value);
    void setForgetMode(const QString& value);
    void setForgetTargetType(const QString& value);
    void setForgetIsCascade(bool value);
    void setForgetSensitivityWarning(const QString& value);
    void setForgetExecutedCount(int value);
    void setForgetPreviewResult(const QJsonObject& value);
    void setForgetExecuteResult(const QJsonObject& value);
    void setForgetPreviewError(const QString& value);
    void setForgetExecuteError(const QString& value);
    void setForgetCrossUserBlocked(bool value);
    void setForgetSelectorCleared(bool value);
    // D10C 响应路由与投影
    void handleForgetPreviewResponse(const QString& requestId, const QJsonObject& envelope);
    void handleForgetExecuteResponse(const QString& requestId, const QJsonObject& envelope);
    // D10C forget.preview 响应 data 投影到子属性
    void projectForgetPreview(const QJsonObject& data);
    // D10C forget.execute 响应 data 投影
    void projectForgetExecute(const QJsonObject& data);
    // D10C 统一重置（失败路径 / Pipeline 前置调用）
    void resetForgetProjection();

    // D8C 响应投影辅助
    [[nodiscard]] QVariantList projectJsonArray(const QJsonArray& items) const;
    // D9C 响应投影辅助：保留字符串与对象元素（recall_sources / uncertainty_hints
    // 契约允许字符串元素如 "fts5" / "vector_score_unverified"；C-1 修复）。
    [[nodiscard]] QVariantList projectJsonArrayMixed(const QJsonArray& items) const;

    // D7C 偏好请求类型（响应路由用）
    enum class PreferenceKind { None, List, History, Create, Update, Rollback };

    // D7C 私有 setter
    void setPreferenceItems(const QVariantList& value);
    void setPreferenceHistory(const QVariantList& value);
    void setPreferenceBusy(bool value);
    void setPreferenceError(const QString& value);
    void setPreferenceStage(const QString& value);
    void setLastPreferenceAction(const QString& value);
    void setLastPreferenceItem(const QJsonObject& value);

    // D7C 响应路由与投影
    void startPreferenceRequest(const QString& method, PreferenceKind kind,
                                const QJsonObject& payload, const QString& stage);
    void handlePreferenceResponse(const QString& requestId, const QJsonObject& envelope);
    [[nodiscard]] QVariantList projectPreferenceItems(const QJsonArray& items) const;
    [[nodiscard]] QVariantList projectPreferenceHistory(const QJsonArray& items) const;

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

    // ── D7C 偏好编辑状态 ─────────────────────────────────────────────
    QVariantList preferenceItems_;
    QVariantList preferenceHistory_;
    bool preferenceBusy_ = false;
    QString preferenceError_;
    QString preferenceStage_ = QStringLiteral("idle");
    QString lastPreferenceAction_;
    QJsonObject lastPreferenceItem_;
    QString pendingPreferenceRequestId_;
    PreferenceKind pendingPreferenceKind_ = PreferenceKind::None;


    // ── D8C 知识详情 / 冲突对比 / 生命周期状态 ───────────────────────
    bool knowledgeDetailBusy_ = false;
    QString knowledgeDetailStage_ = QStringLiteral("idle");
    QJsonObject knowledgeDetail_;
    QString knowledgeDetailError_;
    QString pendingKnowledgeDetailRequestId_;

    bool conflictCompareBusy_ = false;
    QString conflictCompareStage_ = QStringLiteral("idle");
    QVariantList conflictCandidates_;
    QString conflictCompareError_;
    QString pendingConflictCompareRequestId_;

    bool lifecycleStatusBusy_ = false;
    QString lifecycleStatusStage_ = QStringLiteral("idle");
    QVariantList lifecycleItems_;
    QString lifecycleStatusError_;
    QString pendingLifecycleStatusRequestId_;

    // ── D9C Memory Context 组装 ───────────────────────────────────────
    bool contextAssembleBusy_ = false;
    QString contextAssembleStage_ = QStringLiteral("idle");
    QJsonObject assembledContext_;
    QVariantList contextRecallSources_;
    QVariantList contextMemoryTypes_;
    QVariantList contextConflictHints_;
    QVariantList contextUncertaintyHints_;
    int contextTokenBudget_ = 0;
    int contextActualTokenCount_ = 0;
    bool contextBudgetExceeded_ = false;
    QString contextInjectionStatus_;
    QString contextAssembleError_;
    QString pendingContextAssembleRequestId_;
    // M-2 修复：记录本次请求的 token_budget，响应缺失时回退（避免显示 250/0）。
    int requestedTokenBudget_ = 0;

    // ── D10C 精准遗忘 ───────────────────────────────────────────────────
    bool forgetPreviewBusy_ = false;
    bool forgetExecuteBusy_ = false;
    QString forgetStage_ = QStringLiteral("idle");
    QString forgetSelectionHash_;
    int forgetAffectedCount_ = 0;
    int forgetCredentialTtlSeconds_ = 0;
    QString forgetConfirmationCredential_;
    // HIGH-01: Preview 成功时记录 credential 的 wall-clock deadline
    // （ms since epoch）= current + forgetCredentialTtlSeconds_ * 1000。
    // Execute 前校验：非空 + 匹配 + 当前时刻 < deadline。
    // 过期 credential = fail-closed（不发送 forget.execute）。
    // TD-058: 非 monotonic 时钟，不抗系统时间回拨。关闭前防回拨不作为正式安全承诺。
    qint64 forgetCredentialDeadlineMs_ = 0;  // HIGH-01: credential wall-clock 过期时间戳 (ms since epoch)。TD-058: 非 monotonic，不抗系统时间回拨。
    QVariantList forgetResolvedTargets_;
    QString forgetMode_;
    QString forgetTargetType_;
    bool forgetIsCascade_ = false;
    QString forgetSensitivityWarning_;
    int forgetExecutedCount_ = -1;  // -1 = 未执行
    QJsonObject forgetPreviewResult_;
    QJsonObject forgetExecuteResult_;
    QString forgetPreviewError_;
    QString forgetExecuteError_;
    bool forgetCrossUserBlocked_ = false;
    bool forgetSelectorCleared_ = false;
    // 独立 pending request_id（避免 Preview↔Execute 竞态，沿用 D5 REWORK 模式）
    QString pendingForgetPreviewRequestId_;
    QString pendingForgetExecuteRequestId_;
    // 暂存 Preview 请求参数（用于客户端侧 selector 明文清除 + 跨用户校验）
    QString pendingForgetPreviewUserId_;
    QString pendingForgetPreviewSelector_;   // target_selector（明文清除前临时）
    QString pendingForgetPreviewTopic_;      // target_topic（含正文，清除前临时）
    QString pendingForgetPlanId_;            // 供 execute 关联确认
    QString pendingForgetSelectionHash_;     // 供 execute 绑定目标快照
    int pendingForgetAffectedCount_ = 0;     // 供 execute 校验漏删

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
