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
    [[nodiscard]] bool busy() const { return preChatBusy_ || postTurnBusy_; }

    // D5-C Getter
    [[nodiscard]] QString originalUserText() const { return originalUserText_; }
    [[nodiscard]] QString modelRequestText() const { return modelRequestText_; }
    [[nodiscard]] QString injectedContextText() const { return injectedContextText_; }
    [[nodiscard]] QString preChatStage() const { return preChatStage_; }
    [[nodiscard]] QString lastTurnFinalizedEvent() const { return lastTurnFinalizedEvent_; }
    [[nodiscard]] QString postTurnStage() const { return postTurnStage_; }
    [[nodiscard]] bool textIsolationVerified() const;

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
    Q_INVOKABLE QJsonObject buildTurnFinalizedEventJson(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& traceId,
        const QString& finalMessageId,
        const QString& finalAssistantText,
        const QString& finalizationReason,
        const QString& stopReason);

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
