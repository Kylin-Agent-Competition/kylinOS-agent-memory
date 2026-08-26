#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QVariantList>
#include <QDateTime>

#include "memory_client.h"

namespace kylin::memory::client::v1 {

// ============================================================================
// MemoryViewModel — QML 公共 ViewModel（D5-C 垂直链路扩展版）
// ============================================================================
//
// 状态：D5 首个真实垂直链路（L0 骨架 → L1 链路）
//
// D5-C 新增职责：
//   (1) Pre-Chat 链路：用户输入 → MemoryQuery → MemoryContext 注入模型请求，
//       同时严格保证 UI/聊天库保存原文，不保存 Memory Context（原文隔离）。
//   (2) Post-Turn 链路：最终回答 → TurnFinalizedEvent → Gateway 观察。
//   (3) 原文隔离验证：暴露 3 路独立字符串，便于 QML 断言 UI/DB 文本不含
//       MemoryContext 的标记字段。
//
// D5-C 新增 Pipeline 流程：
//   PreChat  阶段：runPreChatPipeline()  保存 originalUserText → 发 memory.retrieve
//          → 响应回来后组装 injectedContextText → 合成 modelRequestText
//          → originalUserText 始终不变（用于 UI/DB 展示）。
//   PostTurn 阶段：runPostTurnPipeline()  从助手 finalMessage 构造
//          TurnFinalizedEvent JSON → sendTurnFinalizedEvent() → Gateway 持久化。
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
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)

    // ── D5-C Pre-Chat 原文隔离三路口径 ─────────────────────────────────
    // ① UI / 聊天库展示：始终是用户原始输入文本，不含任何 Memory Context。
    Q_PROPERTY(QString originalUserText READ originalUserText
                   NOTIFY originalUserTextChanged)
    // ② 发送给模型的请求文本：用户原文 + Memory Context（按 FRZ-CTX-001 拼接）。
    Q_PROPERTY(QString modelRequestText READ modelRequestText
                   NOTIFY modelRequestTextChanged)
    // ③ 注入的 Memory Context 片段（纯诊断/验证用，便于 QML 校验 "不污染 UI/DB"）。
    Q_PROPERTY(QString injectedContextText READ injectedContextText
                   NOTIFY injectedContextTextChanged)
    // Pre-Chat 当前阶段：idle / querying / ready / failed
    Q_PROPERTY(QString preChatStage READ preChatStage NOTIFY preChatStageChanged)

    // ── D5-C Post-Turn 事件口径 ────────────────────────────────────────
    // 最近一次构造（或发送）的 TurnFinalizedEvent JSON 字符串（展示/审计）。
    Q_PROPERTY(QString lastTurnFinalizedEvent READ lastTurnFinalizedEvent
                   NOTIFY lastTurnFinalizedEventChanged)
    // Post-Turn 当前阶段：idle / sending / sent / failed
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
    [[nodiscard]] bool busy() const { return busy_; }

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
    // 执行完整 Pre-Chat：保存 originalUserText → 发 memory.retrieve
    // → 收到响应后组装 modelRequestText。
    // userId/sessionId/scene 用于构造 MemoryQuery 契约；queryText = 用户原文。
    // 成功后：originalUserText / modelRequestText / injectedContextText 三路就绪。
    Q_INVOKABLE void runPreChatPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& scene,
        int maxContextTokens,
        const QString& userOriginalText);

    // 手动重置 Pre-Chat 三路口径与阶段（D5 UI 按钮使用）。
    Q_INVOKABLE void resetPreChatPipeline();

    // ── D5-C Post-Turn Pipeline ────────────────────────────────────────
    // 构造并发送 TurnFinalizedEvent（Post-Turn 观察）。
    // 参数按 memory_event_contract_v1 TurnFinalizedEvent 必填字段提供；
    // 时间戳缺省时按客户端当前 UTC 时间填充。
    Q_INVOKABLE void runPostTurnPipeline(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& traceId,
        const QString& finalMessageId,
        const QString& finalAssistantText,
        const QString& finalizationReason,
        const QString& stopReason);

    // 构造 TurnFinalizedEvent JSON（返回 QJsonObject，便于 QML 预览）。
    Q_INVOKABLE QJsonObject buildTurnFinalizedEventJson(
        const QString& userId,
        const QString& sessionId,
        const QString& turnId,
        const QString& traceId,
        const QString& finalMessageId,
        const QString& finalAssistantText,
        const QString& finalizationReason,
        const QString& stopReason);

    // 原文隔离验证：返回 originalUserText 中不包含 injectedContextText 中
    // 任何一条关键标记行（以换行切分），若 injectedContextText 为空返回 true。
    Q_INVOKABLE bool verifyOriginalTextIsolation() const;

signals:
    void socketPathChanged();
    void connectionStateChanged();
    void lastErrorChanged();
    void lastRequestIdChanged();
    void lastResponseChanged();
    void busyChanged();

    // D5-C 信号
    void originalUserTextChanged();
    void modelRequestTextChanged();
    void injectedContextTextChanged();
    void preChatStageChanged();
    void lastTurnFinalizedEventChanged();
    void postTurnStageChanged();
    void textIsolationVerifiedChanged();

    // 请求失败时向 QML 报告固定安全消息（不含原文）。
    void requestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);

    // 连接级错误（转发 MemoryClient::connectionError，供 QML 绑定）。
    void connectionError(const QString& safeMessage);

private slots:
    void onConnectionStateChanged();
    void onLastErrorChanged();
    void onResponseReceived(const QString& requestId, const QJsonObject& envelope);
    void onRequestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);
    void onConnectionError(const QString& safeMessage);

private:
    void setBusy(bool value);
    void setLastRequestId(const QString& id);
    void setLastResponse(const QJsonObject& envelope);

    // D5-C 私有 setter
    void setOriginalUserText(const QString& value);
    void setModelRequestText(const QString& value);
    void setInjectedContextText(const QString& value);
    void setPreChatStage(const QString& value);
    void setLastTurnFinalizedEvent(const QString& value);
    void setPostTurnStage(const QString& value);

    // 从 memory.retrieve 的响应 envelope.data 中抽取 MemoryContext 的
    // 展示字符串版本（用于 injectedContextText / modelRequestText 合成）。
    QString buildContextTextFromResponse(const QJsonObject& envelope) const;

    // 生成 ISO 8601 UTC with ms
    QString nowIso8601UtcMs() const;

    MemoryClient client_;
    QString lastRequestId_;
    QJsonObject lastResponse_;
    bool busy_ = false;

    // D5-C 成员（Pre-Chat 三路）
    QString originalUserText_;
    QString modelRequestText_;
    QString injectedContextText_;
    QString preChatStage_ = QStringLiteral("idle");

    // D5-C 成员（Post-Turn）
    QString lastTurnFinalizedEvent_;
    QString postTurnStage_ = QStringLiteral("idle");

    // D5-C 关联：preChat 的 requestId → pipeline 标记，以便 onResponseReceived
    // 中将正确的响应路由到 Pre-Chat 组装逻辑（而不是普通 sendMemoryQuery）。
    QString pendingPreChatRequestId_;
    // Pre-Chat 触发时缓存 maxContextTokens，用于展示。
    int pendingPreChatMaxTokens_ = 800;
};

}  // namespace kylin::memory::client::v1
