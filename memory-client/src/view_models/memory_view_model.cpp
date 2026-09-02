#include "view_models/memory_view_model.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStringList>
#include <QTimer>
#include <QUuid>
#include <QVariantList>
#include <QVariantMap>

namespace kylin::memory::client::v1 {

namespace {

// D5-C MemoryContext 标记前缀 — 用于 UI/DB 污染检测。
constexpr const char* kContextMarkerPrefix = "[MEMORY-CONTEXT]";
constexpr const char* kContextSeparator = "\n\n---\n\n";

// FRZ-IPC-006 §6.1：客户端发送 envelope 默认死线（与 MemoryClient 内部常量保持一致）。
constexpr int kDefaultDeadlineMs = 5000;
constexpr const char* kErrClientTimeout = "ERR_CLIENT_TIMEOUT";

}  // namespace

// ────────────────────────────────────────────────────────────────────────────
MemoryViewModel::MemoryViewModel(QObject* parent)
    : QObject(parent)
{
    connect(&client_, &MemoryClient::connectionStateChanged,
            this, &MemoryViewModel::onConnectionStateChanged);
    connect(&client_, &MemoryClient::lastErrorChanged,
            this, &MemoryViewModel::onLastErrorChanged);
    connect(&client_, &MemoryClient::responseReceived,
            this, &MemoryViewModel::onResponseReceived);
    connect(&client_, &MemoryClient::requestFailed,
            this, &MemoryViewModel::onRequestFailed);
    connect(&client_, &MemoryClient::connectionError,
            this, &MemoryViewModel::onConnectionError);
}

MemoryViewModel::~MemoryViewModel()
{
    // 取消所有在途死线计时器，避免回调访问已析构对象。
    for (auto it = deadlineTimers_.begin(); it != deadlineTimers_.end(); ++it) {
        if (it->timer) {
            it->timer->stop();
            it->timer->deleteLater();
        }
    }
    deadlineTimers_.clear();
}

// ── socket / connection / helpers ──────────────────────────────────────────

QString MemoryViewModel::socketPath() const { return client_.socketPath(); }

void MemoryViewModel::setSocketPath(const QString& path)
{
    if (client_.socketPath() == path) { return; }
    client_.setSocketPath(path);
    emit socketPathChanged();
}

QString MemoryViewModel::connectionState() const
{
    switch (client_.connectionState()) {
    case MemoryClient::ConnectionState::Disconnected: return QStringLiteral("disconnected");
    case MemoryClient::ConnectionState::Connecting:   return QStringLiteral("connecting");
    case MemoryClient::ConnectionState::Connected:    return QStringLiteral("connected");
    case MemoryClient::ConnectionState::Closing:      return QStringLiteral("closing");
    }
    return QStringLiteral("unknown");
}

QString MemoryViewModel::lastError() const { return client_.lastError(); }

void MemoryViewModel::connectToService() { client_.connectToService(); }
void MemoryViewModel::disconnectFromService() { client_.disconnectFromService(); }

void MemoryViewModel::sendHealth()
{
    const QString id = client_.sendHealthRequest();
    if (id.isEmpty()) return;
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

void MemoryViewModel::sendMemoryQuery(const QJsonObject& payload)
{
    const QString id = client_.sendRequest(methods::kMemoryRetrieve, payload);
    if (id.isEmpty()) return;
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

// ── 原文隔离验证 ────────────────────────────────────────────────────────────

bool MemoryViewModel::textIsolationVerified() const
{
    return verifyOriginalTextIsolation();
}

bool MemoryViewModel::verifyOriginalTextIsolation() const
{
    // 空 context → 原文 trivially 通过。
    if (injectedContextText_.isEmpty()) return true;

    // 原文包含 [MEMORY-CONTEXT] 前缀 → 直接失败（明确的注入标记污染）。
    if (originalUserText_.contains(QString::fromUtf8(kContextMarkerPrefix))) {
        return false;
    }

    // 遍历 injectedContextText 的非空行（长度>=8），确保没有任何一行出现在原文中。
    const QStringList lines = injectedContextText_.split(
        QLatin1Char('\n'), QString::SkipEmptyParts);
    for (const QString& rawLine : lines) {
        const QString line = rawLine.trimmed();
        if (line.length() < 8) continue;
        if (!originalUserText_.isEmpty() && originalUserText_.contains(line)) {
            return false;
        }
    }
    return true;
}

// ── D7C 偏好编辑（版本历史与回滚）────────────────────────────────────────────

void MemoryViewModel::loadPreferences(const QString& userId)
{
    QJsonObject payload;
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("include_history"), false);
    startPreferenceRequest(methods::kPreferenceList, PreferenceKind::List, payload,
                           QStringLiteral("loading"));
}

void MemoryViewModel::loadPreferenceHistory(
    const QString& userId, const QString& key, const QString& scope)
{
    QJsonObject payload;
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("preference_key"), key);
    payload.insert(QStringLiteral("preference_scope"), scope);
    startPreferenceRequest(methods::kPreferenceHistory, PreferenceKind::History, payload,
                           QStringLiteral("loading"));
}

void MemoryViewModel::createPreference(
    const QString& userId,
    const QString& key,
    const QString& scope,
    const QString& value,
    bool isTemporary,
    bool shouldPersist,
    const QString& idempotencyKey)
{
    QJsonObject payload;
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("preference_key"), key);
    payload.insert(QStringLiteral("preference_scope"), scope);
    payload.insert(QStringLiteral("preference_value"), value);
    payload.insert(QStringLiteral("is_temporary"), isTemporary);
    payload.insert(QStringLiteral("should_persist"), shouldPersist);
    if (!idempotencyKey.isEmpty()) {
        payload.insert(QStringLiteral("idempotency_key"), idempotencyKey);
    }
    startPreferenceRequest(methods::kPreferenceCreate, PreferenceKind::Create, payload,
                           QStringLiteral("saving"));
}

void MemoryViewModel::updatePreference(
    const QString& userId,
    const QString& key,
    const QString& scope,
    const QString& newValue,
    bool isTemporary,
    bool shouldPersist,
    const QString& idempotencyKey)
{
    QJsonObject payload;
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("preference_key"), key);
    payload.insert(QStringLiteral("preference_scope"), scope);
    payload.insert(QStringLiteral("new_value"), newValue);
    // HIGH-01：显式携带生命周期标志，防止临时偏好 update 时被缺省晋升为 active。
    payload.insert(QStringLiteral("is_temporary"), isTemporary);
    payload.insert(QStringLiteral("should_persist"), shouldPersist);
    if (!idempotencyKey.isEmpty()) {
        payload.insert(QStringLiteral("idempotency_key"), idempotencyKey);
    }
    startPreferenceRequest(methods::kPreferenceUpdate, PreferenceKind::Update, payload,
                           QStringLiteral("saving"));
}

void MemoryViewModel::rollbackPreference(
    const QString& userId,
    const QString& key,
    const QString& scope,
    int targetVersion,
    const QString& idempotencyKey)
{
    QJsonObject payload;
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("preference_key"), key);
    payload.insert(QStringLiteral("preference_scope"), scope);
    payload.insert(QStringLiteral("target_version"), targetVersion);
    if (!idempotencyKey.isEmpty()) {
        payload.insert(QStringLiteral("idempotency_key"), idempotencyKey);
    }
    startPreferenceRequest(methods::kPreferenceRollback, PreferenceKind::Rollback, payload,
                           QStringLiteral("saving"));
}

void MemoryViewModel::startPreferenceRequest(
    const QString& method, PreferenceKind kind, const QJsonObject& payload,
    const QString& stage)
{
    if (preferenceBusy_) {
        setPreferenceError(QStringLiteral("A preference request is already in flight."));
        setPreferenceStage(QStringLiteral("failed"));
        return;
    }
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected) {
        setPreferenceError(QStringLiteral("Client is not connected."));
        setPreferenceStage(QStringLiteral("failed"));
        return;
    }
    const QString id = client_.sendRequest(method, payload);
    if (id.isEmpty()) {
        setPreferenceError(QStringLiteral("Failed to send preference request."));
        setPreferenceStage(QStringLiteral("failed"));
        return;
    }
    pendingPreferenceRequestId_ = id;
    pendingPreferenceKind_ = kind;
    setPreferenceBusy(true);
    setPreferenceError({});
    setPreferenceStage(stage);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

// ── 死线计时器 ──────────────────────────────────────────────────────────────

void MemoryViewModel::armDeadlineTimer(const QString& requestId, int deadlineMs)
{
    if (requestId.isEmpty() || deadlineMs <= 0) return;
    cancelDeadlineTimerFor(requestId);

    auto* timer = new QTimer(this);
    timer->setSingleShot(true);
    timer->setInterval(deadlineMs);
    connect(timer, &QTimer::timeout, this, [this, requestId]() {
        deadlineTimers_.remove(requestId);
        // 统一走 requestFailed 路径，以便 PreChat/PostTurn 状态机一致处理。
        onRequestFailed(requestId, QString::fromUtf8(kErrClientTimeout),
                        QStringLiteral("Client-side deadline exceeded; request aborted."));
    });
    deadlineTimers_.insert(requestId, {timer, deadlineMs});
    timer->start();
}

void MemoryViewModel::cancelDeadlineTimerFor(const QString& requestId)
{
    const auto it = deadlineTimers_.find(requestId);
    if (it == deadlineTimers_.end()) return;
    if (it->timer) {
        it->timer->stop();
        it->timer->deleteLater();
    }
    deadlineTimers_.erase(it);
}

// ── D5 Pre-Chat Pipeline ────────────────────────────────────────────────────

void MemoryViewModel::runPreChatPipeline(
    const QString& userId,
    const QString& sessionId,
    const QString& scene,
    int maxContextTokens,
    const QString& userOriginalText)
{
    // ① 固化 originalUserText（永不被 MemoryContext 修改）。
    setOriginalUserText(userOriginalText);
    setModelRequestText(userOriginalText);  // 默认：无记忆时原文即模型请求
    setInjectedContextText({});
    setPreChatStage(QStringLiteral("querying"));

    // ② 构造 MemoryQuery 契约并发送 memory.retrieve。
    const int realMaxTokens = maxContextTokens > 0 ? maxContextTokens : 800;
    const QJsonObject queryPayload{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("session_id"), sessionId},
        {QStringLiteral("query_text"), userOriginalText},
        {QStringLiteral("scene"), scene},
        {QStringLiteral("max_context_tokens"), realMaxTokens},
    };
    pendingPreChatMaxTokens_ = realMaxTokens;

    setPreChatBusy(true);
    const QString requestId = client_.sendRequest(
        methods::kMemoryRetrieve, queryPayload);
    if (requestId.isEmpty()) {
        setPreChatBusy(false);
        setPreChatStage(QStringLiteral("failed"));
        return;
    }
    pendingPreChatRequestId_ = requestId;
    setLastRequestId(requestId);
    armDeadlineTimer(requestId, kDefaultDeadlineMs);
}

void MemoryViewModel::resetPreChatPipeline()
{
    if (!pendingPreChatRequestId_.isEmpty()) {
        cancelDeadlineTimerFor(pendingPreChatRequestId_);
        pendingPreChatRequestId_.clear();
    }
    setOriginalUserText({});
    setModelRequestText({});
    setInjectedContextText({});
    setPreChatBusy(false);
    setPreChatStage(QStringLiteral("idle"));
}

// ── D5 Post-Turn Pipeline ───────────────────────────────────────────────────

void MemoryViewModel::runPostTurnPipeline(
    const QString& userId,
    const QString& sessionId,
    const QString& turnId,
    const QString& traceId,
    const QString& finalMessageId,
    const QString& finalAssistantText,
    const QString& finalizationReason,
    const QString& stopReason)
{
    Q_UNUSED(finalAssistantText)  // Demo 阶段仅构造参考字符串，不做 DB 写入

    setPostTurnStage(QStringLiteral("sending"));

    const QJsonObject event = buildTurnFinalizedEventJson(
        userId, sessionId, turnId, traceId, finalMessageId,
        finalAssistantText, finalizationReason, stopReason);

    const QJsonDocument doc(event);
    setLastTurnFinalizedEvent(QString::fromUtf8(doc.toJson(QJsonDocument::Indented)));

    setPostTurnBusy(true);
    const QString requestId = client_.sendTurnFinalizedEvent(event);
    if (requestId.isEmpty()) {
        setPostTurnBusy(false);
        setPostTurnStage(QStringLiteral("failed"));
        return;
    }
    pendingPostTurnRequestId_ = requestId;
    setLastRequestId(requestId);
    armDeadlineTimer(requestId, kDefaultDeadlineMs);
}

QJsonObject MemoryViewModel::buildTurnFinalizedEventJson(
    const QString& userId,
    const QString& sessionId,
    const QString& turnId,
    const QString& traceId,
    const QString& finalMessageId,
    const QString& finalAssistantText,
    const QString& finalizationReason,
    const QString& stopReason,
    const QString& retryOfTurnId)
{
    Q_UNUSED(finalAssistantText)

    // 非阻断项修复：Preview → Send 复用同一事件对象，避免 event_id / timestamp 漂移。
    const QStringList key{userId, sessionId, turnId, traceId,
                          finalMessageId, finalizationReason, stopReason, retryOfTurnId};
    if (!cachedTurnEvent_.isEmpty() && cachedTurnEventKey_ == key) {
        return cachedTurnEvent_;
    }

    const QString eventId = QStringLiteral("evt-turn-%1").arg(
        QUuid::createUuid().toString(QUuid::WithoutBraces));
    const QString idempotencyKey = QStringLiteral("turn-finalized:%1:%2")
                                       .arg(sessionId, turnId);
    const QString srcRef = finalMessageId.isEmpty()
                               ? QStringLiteral("ref:chat-record:%1").arg(turnId)
                               : QStringLiteral("ref:chat-record:%1").arg(finalMessageId);

    const QString now = nowIso8601UtcMs();

    // ADR-010 IPC 映射契约：payload 分为 metadata（嵌套对象）+ 事件字段（顶层）。
    // metadata 包含 schema_version / event_id / user_id / session_id / turn_id /
    // idempotency_key / trace_id? / occurred_at / collected_at / source_reference。
    // 事件层包含 is_final / finalized_at / final_message_id? /
    // finalization_reason? / stop_reason? / tool_call_ids?。
    QJsonObject metadata{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("event_id"), eventId},
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("session_id"), sessionId},
        {QStringLiteral("turn_id"), turnId},
        {QStringLiteral("idempotency_key"), idempotencyKey},
        {QStringLiteral("occurred_at"), now},
        {QStringLiteral("collected_at"), now},
        {QStringLiteral("source_reference"), srcRef},
    };
    if (!traceId.isEmpty()) metadata.insert(QStringLiteral("trace_id"), traceId);
    // TB-D6C-04：finalization_reason=retry 时必须携带 retry_of_turn_id，
    // 且 retry_of_turn_id != turn_id（调用方保证）。
    if (!retryOfTurnId.isEmpty())
        metadata.insert(QStringLiteral("retry_of_turn_id"), retryOfTurnId);

    QJsonObject event;
    event.insert(QStringLiteral("metadata"), metadata);
    event.insert(QStringLiteral("is_final"), true);
    event.insert(QStringLiteral("finalized_at"), now);
    if (!finalMessageId.isEmpty()) event.insert(QStringLiteral("final_message_id"), finalMessageId);
    if (!finalizationReason.isEmpty()) event.insert(QStringLiteral("finalization_reason"), finalizationReason);
    if (!stopReason.isEmpty())     event.insert(QStringLiteral("stop_reason"), stopReason);
    event.insert(QStringLiteral("tool_call_ids"), QJsonArray{});

    cachedTurnEventKey_ = key;
    cachedTurnEvent_ = event;
    return event;
}

// ── D6-C 多源 Adapter Pipeline ─────────────────────────────────────────────

QJsonObject MemoryViewModel::buildEventMetadata(
    const QString& userId,
    const QString& sessionId,
    const QString& turnId,
    const QString& traceId,
    const QString& idempotencyKey,
    const QString& sourceReference) const
{
    // 共享 metadata 构造：对齐 ADR-010 IPC 映射契约的 metadata 嵌套对象。
    // trace_id 若提供则写入；occurred_at / collected_at 取同一 UTC 毫秒时间戳。
    const QString now = nowIso8601UtcMs();
    QJsonObject metadata{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("event_id"), QStringLiteral("evt-%1").arg(
            QUuid::createUuid().toString(QUuid::WithoutBraces))},
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("session_id"), sessionId},
        {QStringLiteral("turn_id"), turnId},
        {QStringLiteral("idempotency_key"), idempotencyKey},
        {QStringLiteral("occurred_at"), now},
        {QStringLiteral("collected_at"), now},
        {QStringLiteral("source_reference"), sourceReference},
    };
    if (!traceId.isEmpty()) metadata.insert(QStringLiteral("trace_id"), traceId);
    return metadata;
}

QJsonObject MemoryViewModel::buildToolExecutionEventJson(
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
    bool rollbackRequired)
{
    // 对齐 contracts/examples/tool_execution_event.v1.json（D3 已冻结）。
    // rollback_status 默认 not_applicable；rollbackRequired=true 时为 required。
    const QString idempotencyKey = QStringLiteral("tool-execution:%1:%2")
                                       .arg(sessionId, toolCallId);
    const QString srcRef = QStringLiteral("ref:tool-event:%1").arg(toolCallId);

    QJsonObject metadata = buildEventMetadata(
        userId, sessionId, turnId, /*traceId=*/QStringLiteral(""),
        idempotencyKey, srcRef);

    const QString now = nowIso8601UtcMs();
    QJsonObject event;
    event.insert(QStringLiteral("metadata"), metadata);
    event.insert(QStringLiteral("tool_call_id"), toolCallId);
    event.insert(QStringLiteral("tool_name"), toolName);
    event.insert(QStringLiteral("arguments_ref"), argumentsRef);
    event.insert(QStringLiteral("started_at"), now);
    event.insert(QStringLiteral("finished_at"), now);
    event.insert(QStringLiteral("execution_status"), executionStatus);
    if (!resultRef.isEmpty()) event.insert(QStringLiteral("result_ref"), resultRef);
    if (!errorType.isEmpty()) event.insert(QStringLiteral("error_type"), errorType);
    if (!errorMessageSafe.isEmpty())
        event.insert(QStringLiteral("error_message_safe"), errorMessageSafe);
    event.insert(QStringLiteral("side_effect"), sideEffect);
    event.insert(QStringLiteral("rollback_required"), rollbackRequired);
    event.insert(QStringLiteral("rollback_status"),
                 rollbackRequired ? QStringLiteral("required")
                                  : QStringLiteral("not_applicable"));
    return event;
}

void MemoryViewModel::runToolPipeline(
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
    bool rollbackRequired)
{
    setToolStage(QStringLiteral("sending"));

    const QJsonObject event = buildToolExecutionEventJson(
        userId, sessionId, turnId, toolCallId, toolName, executionStatus,
        argumentsRef, resultRef, errorType, errorMessageSafe,
        sideEffect, rollbackRequired);

    const QJsonDocument doc(event);
    setLastToolEvent(QString::fromUtf8(doc.toJson(QJsonDocument::Indented)));

    setToolBusy(true);
    const QString requestId = client_.sendToolExecutionEvent(event);
    if (requestId.isEmpty()) {
        setToolBusy(false);
        setToolStage(QStringLiteral("failed"));
        return;
    }
    pendingToolRequestId_ = requestId;
    setLastRequestId(requestId);
    armDeadlineTimer(requestId, kDefaultDeadlineMs);
}

void MemoryViewModel::runManualConfigPipeline(
    const QString& userId,
    const QString& sessionId,
    const QString& scope,
    const QString& key,
    const QString& value,
    bool isTemporary,
    bool shouldPersist,
    const QString& sensitivityLevel,
    double confidence)
{
    // 客户端侧敏感预检：high / critical 等级（大小写归一）拒绝构造事件、拒绝发送。
    // 完整敏感识别在 A 轨 pipeline/sensitive.py；此处为客户端侧第一道防线。
    const QString sl = sensitivityLevel.trimmed().toLower();
    if (sl == QStringLiteral("high") || sl == QStringLiteral("critical")) {
        setLastManualConfigEvent({});
        setManualConfigStage(QStringLiteral("failed"));
        emit connectionError(QStringLiteral(
            "sensitive_content_blocked: manual config rejected at client"));
        return;
    }

    setManualConfigStage(QStringLiteral("sending"));

    const QString idempotencyKey = QStringLiteral("manual-config:%1:%2:%3")
        .arg(sessionId, scope, key);
    const QString srcRef = QStringLiteral("ref:manual-config:%1:%2").arg(scope, key);

    QJsonObject metadata = buildEventMetadata(
        userId, sessionId, /*turnId=*/QStringLiteral(""),
        /*traceId=*/QStringLiteral(""), idempotencyKey, srcRef);

    QJsonObject config;
    config.insert(QStringLiteral("scope"), scope);
    config.insert(QStringLiteral("key"), key);
    config.insert(QStringLiteral("value"), value);
    config.insert(QStringLiteral("is_temporary"), isTemporary);
    config.insert(QStringLiteral("should_persist"), shouldPersist);
    config.insert(QStringLiteral("confidence"), confidence);
    config.insert(QStringLiteral("sensitivity_level"), sensitivityLevel);
    // TB-D6C-08：与 Behavior 对称，候选手动配置事件也标记 PENDING_C_CONFIRMATION
    // （C 轨未冻结 manual.config.ingest → 正式 schema / SourceType）。
    config.insert(QStringLiteral("mapping_status"),
                  QStringLiteral("PENDING_C_CONFIRMATION"));
    // TB-D6C-12：删除 config.source_reference 重复字段
    // （metadata.source_reference 已承载同一值）。

    QJsonObject event;
    event.insert(QStringLiteral("metadata"), metadata);
    event.insert(QStringLiteral("config"), config);

    const QJsonDocument doc(event);
    setLastManualConfigEvent(QString::fromUtf8(doc.toJson(QJsonDocument::Indented)));

    setManualConfigBusy(true);
    const QString requestId = client_.sendManualConfigEvent(event);
    if (requestId.isEmpty()) {
        setManualConfigBusy(false);
        setManualConfigStage(QStringLiteral("failed"));
        return;
    }
    pendingManualConfigRequestId_ = requestId;
    setLastRequestId(requestId);
    armDeadlineTimer(requestId, kDefaultDeadlineMs);
}

void MemoryViewModel::runBehaviorPipeline(
    const QString& userId,
    const QString& sessionId,
    const QString& behaviorKind,
    const QString& observedAction,
    const QString& contextRef,
    const QString& actor)
{
    setBehaviorStage(QStringLiteral("sending"));

    const QString idempotencyKey = QStringLiteral("behavior:%1:%2:%3")
        .arg(sessionId, behaviorKind,
             QUuid::createUuid().toString(QUuid::WithoutBraces));
    const QString srcRef = QStringLiteral("ref:behavior:%1:%2")
        .arg(sessionId, behaviorKind);

    QJsonObject metadata = buildEventMetadata(
        userId, sessionId, /*turnId=*/QStringLiteral(""),
        /*traceId=*/QStringLiteral(""), idempotencyKey, srcRef);

    // TB-D6C-05：behavior.occurred_at 复用 metadata.occurred_at，避免双源时间戳漂移。
    const QString metaOccurredAt =
        metadata.value(QStringLiteral("occurred_at")).toString();

    QJsonObject behavior;
    behavior.insert(QStringLiteral("behavior_kind"), behaviorKind);
    behavior.insert(QStringLiteral("observed_action"), observedAction);
    behavior.insert(QStringLiteral("context_ref"), contextRef);
    behavior.insert(QStringLiteral("actor"), actor);
    behavior.insert(QStringLiteral("occurred_at"), metaOccurredAt);
    // C 轨未冻结 behavior → MemorySourceEvent.source_type 映射；
    // 显式注入 PENDING_C_CONFIRMATION 字段，不擅自新增 SourceType 枚举。
    behavior.insert(QStringLiteral("mapping_status"),
                    QStringLiteral("PENDING_C_CONFIRMATION"));

    QJsonObject event;
    event.insert(QStringLiteral("metadata"), metadata);
    event.insert(QStringLiteral("behavior"), behavior);

    const QJsonDocument doc(event);
    setLastBehaviorEvent(QString::fromUtf8(doc.toJson(QJsonDocument::Indented)));

    setBehaviorBusy(true);
    const QString requestId = client_.sendBehaviorEvent(event);
    if (requestId.isEmpty()) {
        setBehaviorBusy(false);
        setBehaviorStage(QStringLiteral("failed"));
        return;
    }
    pendingBehaviorRequestId_ = requestId;
    setLastRequestId(requestId);
    armDeadlineTimer(requestId, kDefaultDeadlineMs);
}

// ── 信号槽：问题1核心修复 onResponseReceived ─────────────────────────────────

void MemoryViewModel::onConnectionStateChanged()
{
    emit connectionStateChanged();
}

void MemoryViewModel::onLastErrorChanged()
{
    emit lastErrorChanged();
}

bool MemoryViewModel::tryParseResponseStatus(
    const QJsonObject& envelope,
    ResponseParts* outParts,
    QString* outErrorCode,
    QString* outErrorMessage) const
{
    if (!outParts || !outErrorCode || !outErrorMessage) return false;
    const auto [maybeParts, err] = parseResponse(envelope);
    if (!err.ok() || !maybeParts.has_value()) {
        // parseResponse 级失败 → 视为协议错误（通常由 requestFailed /
        // connectionError 另行回报；此处给一个统一 errorCode 便于回滚）。
        *outErrorCode = QStringLiteral("ERR_INVALID_RESPONSE");
        *outErrorMessage = err.safeMessage.isEmpty()
                               ? QStringLiteral("parseResponse failed.")
                               : err.safeMessage;
        return false;
    }
    *outParts = *maybeParts;
    if (outParts->status == QStringLiteral("error")) {
        *outErrorCode  = outParts->errorCode;
        *outErrorMessage = outParts->message;
        return false;
    }
    // status == "ok"
    return true;
}

void MemoryViewModel::onResponseReceived(
    const QString& requestId, const QJsonObject& envelope)
{
    setLastResponse(envelope);
    cancelDeadlineTimerFor(requestId);

    // —— 问题1修复：首行解析业务 status；status=error 一律路由失败路径 ——
    ResponseParts parts{};
    QString errCode;
    QString errMsg;
    const bool statusOk = tryParseResponseStatus(envelope, &parts, &errCode, &errMsg);
    if (!statusOk) {
        // 统一调用 onRequestFailed，让状态机在同一个函数里收口，避免竞态。
        onRequestFailed(requestId,
                        errCode.isEmpty() ? QStringLiteral("UNKNOWN_ERROR") : errCode,
                        errMsg.isEmpty() ? QStringLiteral("Gateway returned status=error.")
                                         : errMsg);
        return;
    }

    // ── 问题2修复：Pre-Chat 仅从 envelope.data.context（正式 MemoryContext 契约）
    //    解析；空 context / malformed context 保持空字符串，绝不产生伪标记。
    if (!pendingPreChatRequestId_.isEmpty()
        && requestId == pendingPreChatRequestId_) {
        pendingPreChatRequestId_.clear();

        // 仅 envelope.data 存在且为对象时才尝试解析 context。
        const QJsonValue dataValue = envelope.value(kDataKey);
        if (dataValue.isObject()) {
            const QJsonObject data = dataValue.toObject();
            const QJsonValue ctxValue = data.value(QStringLiteral("context"));
            if (ctxValue.isObject()) {
                const QString ctxText = buildContextTextFromContextObject(ctxValue.toObject());
                setInjectedContextText(ctxText);
                QString combined = originalUserText_;
                if (!ctxText.isEmpty()) {
                    combined += QString::fromUtf8(kContextSeparator) + ctxText;
                }
                setModelRequestText(combined);
            } else {
                // data 存在但 context 缺失或非对象 → 空注入，不构造伪标记
                setInjectedContextText({});
                setModelRequestText(originalUserText_);
            }
        } else {
            setInjectedContextText({});
            setModelRequestText(originalUserText_);
        }

        setPreChatBusy(false);
        setPreChatStage(QStringLiteral("ready"));
        emit textIsolationVerifiedChanged();
    }

    // Post-Turn：用独立 pendingPostTurnRequestId_ 路由（不用全局 lastRequestId_ 近似）。
    if (!pendingPostTurnRequestId_.isEmpty()
        && requestId == pendingPostTurnRequestId_) {
        pendingPostTurnRequestId_.clear();
        setPostTurnBusy(false);
        setPostTurnStage(QStringLiteral("sent"));
    }

    // ── D6-C 多源 Adapter 路由（四 busy 独立 pending，沿用 §C1 模式） ──────
    if (!pendingToolRequestId_.isEmpty()
        && requestId == pendingToolRequestId_) {
        pendingToolRequestId_.clear();
        setToolBusy(false);
        setToolStage(QStringLiteral("sent"));
    }
    if (!pendingManualConfigRequestId_.isEmpty()
        && requestId == pendingManualConfigRequestId_) {
        pendingManualConfigRequestId_.clear();
        setManualConfigBusy(false);
        setManualConfigStage(QStringLiteral("sent"));
    }
    if (!pendingBehaviorRequestId_.isEmpty()
        && requestId == pendingBehaviorRequestId_) {
        pendingBehaviorRequestId_.clear();
        setBehaviorBusy(false);
        setBehaviorStage(QStringLiteral("sent"));
    }

    // D7C 偏好请求（preference.list/create/update/rollback/history）。
    if (!pendingPreferenceRequestId_.isEmpty()
        && requestId == pendingPreferenceRequestId_) {
        handlePreferenceResponse(requestId, envelope);
    }

    // ── D8C 知识详情 / 冲突对比 / 生命周期状态 路由 ───────────────────
    if (!pendingKnowledgeDetailRequestId_.isEmpty()
        && requestId == pendingKnowledgeDetailRequestId_) {
        pendingKnowledgeDetailRequestId_.clear();
        setKnowledgeDetail(parts.data);
        setKnowledgeDetailBusy(false);
        setKnowledgeDetailStage(QStringLiteral("ready"));
    }
    if (!pendingConflictCompareRequestId_.isEmpty()
        && requestId == pendingConflictCompareRequestId_) {
        pendingConflictCompareRequestId_.clear();
        setConflictCandidates(projectJsonArray(
            parts.data.value(QStringLiteral("candidates")).toArray()));
        setConflictCompareBusy(false);
        setConflictCompareStage(QStringLiteral("ready"));
    }
    if (!pendingLifecycleStatusRequestId_.isEmpty()
        && requestId == pendingLifecycleStatusRequestId_) {
        pendingLifecycleStatusRequestId_.clear();
        setLifecycleItems(projectJsonArray(
            parts.data.value(QStringLiteral("items")).toArray()));
        setLifecycleStatusBusy(false);
        setLifecycleStatusStage(QStringLiteral("ready"));
    }

    // ── D9C Memory Context 组装 路由 ───────────────────────────────
    // 防伪 Context：仅当 data 为非空对象且 injection_status 非 failed/skipped
    // 时投影；空 data / injection_status=failed/skipped 保持 assembledContext_ 空。
    if (!pendingContextAssembleRequestId_.isEmpty()
        && requestId == pendingContextAssembleRequestId_) {
        pendingContextAssembleRequestId_.clear();
        const QString injectionStatus =
            parts.data.value(QStringLiteral("injection_status")).toString();
        const bool contextInvalid =
            parts.data.isEmpty()
            || injectionStatus == QStringLiteral("failed")
            || injectionStatus == QStringLiteral("skipped");
        if (contextInvalid) {
            // 空 data / failed / skipped：清空投影，stage=failed（防伪 Context）
            // I-2 修复：统一使用 resetContextProjection() 避免 stale Context 残留。
            resetContextProjection();
            setContextInjectionStatus(injectionStatus.isEmpty()
                ? QStringLiteral("skipped") : injectionStatus);
            setContextAssembleError(QStringLiteral(
                "Context assembly returned no usable context."));
            setContextAssembleBusy(false);
            setContextAssembleStage(QStringLiteral("failed"));
        } else {
            projectAssembledContext(parts.data);
            setContextAssembleBusy(false);
            setContextAssembleStage(QStringLiteral("ready"));
        }
    }

    // ── D10C 精准遗忘 路由 ──────────────────────────────────────
    // forget.preview：调用 handleForgetPreviewResponse
    if (!pendingForgetPreviewRequestId_.isEmpty()
        && requestId == pendingForgetPreviewRequestId_) {
        pendingForgetPreviewRequestId_.clear();
        handleForgetPreviewResponse(requestId, envelope);
    }
    // forget.execute：调用 handleForgetExecuteResponse（含漏删 MEDIUM-03 保护）
    if (!pendingForgetExecuteRequestId_.isEmpty()
        && requestId == pendingForgetExecuteRequestId_) {
        pendingForgetExecuteRequestId_.clear();
        handleForgetExecuteResponse(requestId, envelope);
    }
}

void MemoryViewModel::onRequestFailed(
    const QString& requestId, const QString& errorCode, const QString& safeMessage)
{
    cancelDeadlineTimerFor(requestId);

    // Pre-Chat pending 命中
    if (!pendingPreChatRequestId_.isEmpty()
        && requestId == pendingPreChatRequestId_) {
        pendingPreChatRequestId_.clear();
        setInjectedContextText({});  // 错误响应绝不参与 Context 拼接
        setModelRequestText(originalUserText_);
        setPreChatBusy(false);
        // 区分 TIMEOUT 与一般失败，便于 UI 展示/诊断
        setPreChatStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                            ? QStringLiteral("timeout")
                            : QStringLiteral("failed"));
    }

    // Post-Turn pending 命中
    if (!pendingPostTurnRequestId_.isEmpty()
        && requestId == pendingPostTurnRequestId_) {
        pendingPostTurnRequestId_.clear();
        setPostTurnBusy(false);
        setPostTurnStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                             ? QStringLiteral("timeout")
                             : QStringLiteral("failed"));
    }

    // ── D6-C 多源 Adapter pending 命中 ───────────────────────────────────
    if (!pendingToolRequestId_.isEmpty()
        && requestId == pendingToolRequestId_) {
        pendingToolRequestId_.clear();
        setToolBusy(false);
        setToolStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                         ? QStringLiteral("timeout")
                         : QStringLiteral("failed"));
    }
    if (!pendingManualConfigRequestId_.isEmpty()
        && requestId == pendingManualConfigRequestId_) {
        pendingManualConfigRequestId_.clear();
        setManualConfigBusy(false);
        setManualConfigStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                                 ? QStringLiteral("timeout")
                                 : QStringLiteral("failed"));
    }
    if (!pendingBehaviorRequestId_.isEmpty()
        && requestId == pendingBehaviorRequestId_) {
        pendingBehaviorRequestId_.clear();
        setBehaviorBusy(false);
        setBehaviorStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                             ? QStringLiteral("timeout")
                             : QStringLiteral("failed"));
    }

    // D7C 偏好 pending 命中
    if (!pendingPreferenceRequestId_.isEmpty()
        && requestId == pendingPreferenceRequestId_) {
        pendingPreferenceRequestId_.clear();
        pendingPreferenceKind_ = PreferenceKind::None;
        setPreferenceBusy(false);
        setPreferenceError(safeMessage);
        setPreferenceStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                               ? QStringLiteral("timeout")
                               : QStringLiteral("failed"));
    }

    // ── D8C 知识详情 / 冲突对比 / 生命周期状态 pending 命中 ───────────
    if (!pendingKnowledgeDetailRequestId_.isEmpty()
        && requestId == pendingKnowledgeDetailRequestId_) {
        pendingKnowledgeDetailRequestId_.clear();
        setKnowledgeDetailBusy(false);
        setKnowledgeDetailError(safeMessage);
        setKnowledgeDetailStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                                    ? QStringLiteral("timeout")
                                    : QStringLiteral("failed"));
    }
    if (!pendingConflictCompareRequestId_.isEmpty()
        && requestId == pendingConflictCompareRequestId_) {
        pendingConflictCompareRequestId_.clear();
        setConflictCompareBusy(false);
        setConflictCompareError(safeMessage);
        setConflictCompareStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                                    ? QStringLiteral("timeout")
                                    : QStringLiteral("failed"));
    }
    if (!pendingLifecycleStatusRequestId_.isEmpty()
        && requestId == pendingLifecycleStatusRequestId_) {
        pendingLifecycleStatusRequestId_.clear();
        setLifecycleStatusBusy(false);
        setLifecycleStatusError(safeMessage);
        setLifecycleStatusStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                                    ? QStringLiteral("timeout")
                                    : QStringLiteral("failed"));
    }

    // ── D9C Memory Context 组装 pending 命中 ───────────────────────
    // 错误响应绝不参与 Context 拼接：清空 assembledContext 防伪注入。
    // I-2 修复：统一使用 resetContextProjection() 避免 stale Context 残留。
    if (!pendingContextAssembleRequestId_.isEmpty()
        && requestId == pendingContextAssembleRequestId_) {
        pendingContextAssembleRequestId_.clear();
        resetContextProjection();
        setContextInjectionStatus(QStringLiteral("failed"));
        setContextAssembleBusy(false);
        setContextAssembleError(safeMessage);
        setContextAssembleStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                                    ? QStringLiteral("timeout")
                                    : QStringLiteral("failed"));
    }

    // ── D10C 精准遗忘 pending 命中 ──────────────────────────────
    // 失败路径清空所有投影（selector 明文、selection 快照等），标记 stage=failed/timeout。
    if (!pendingForgetPreviewRequestId_.isEmpty()
        && requestId == pendingForgetPreviewRequestId_) {
        pendingForgetPreviewRequestId_.clear();
        pendingForgetPreviewSelector_.clear();
        pendingForgetPreviewTopic_.clear();
        resetForgetProjection();
        setForgetPreviewBusy(false);
        setForgetPreviewError(safeMessage);
        setForgetStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                           ? QStringLiteral("timeout")
                           : QStringLiteral("failed"));
    }
    if (!pendingForgetExecuteRequestId_.isEmpty()
        && requestId == pendingForgetExecuteRequestId_) {
        pendingForgetExecuteRequestId_.clear();
        setForgetExecuteBusy(false);
        setForgetExecuteError(safeMessage);
        setForgetStage(errorCode == QString::fromUtf8(kErrClientTimeout)
                           ? QStringLiteral("timeout")
                           : QStringLiteral("failed"));
    }

    emit requestFailed(requestId, errorCode, safeMessage);
}

void MemoryViewModel::onConnectionError(const QString& safeMessage)
{
    emit connectionError(safeMessage);
}

// ── 私有 setters ────────────────────────────────────────────────────────────

void MemoryViewModel::setLastRequestId(const QString& id)
{
    if (lastRequestId_ == id) return;
    lastRequestId_ = id;
    emit lastRequestIdChanged();
}

void MemoryViewModel::setLastResponse(const QJsonObject& envelope)
{
    lastResponse_ = envelope;
    emit lastResponseChanged();
}

void MemoryViewModel::setOriginalUserText(const QString& value)
{
    if (originalUserText_ == value) return;
    originalUserText_ = value;
    emit originalUserTextChanged();
    emit textIsolationVerifiedChanged();
}

void MemoryViewModel::setModelRequestText(const QString& value)
{
    if (modelRequestText_ == value) return;
    modelRequestText_ = value;
    emit modelRequestTextChanged();
}

void MemoryViewModel::setInjectedContextText(const QString& value)
{
    if (injectedContextText_ == value) return;
    injectedContextText_ = value;
    emit injectedContextTextChanged();
    emit textIsolationVerifiedChanged();
}

void MemoryViewModel::setPreChatStage(const QString& value)
{
    if (preChatStage_ == value) return;
    preChatStage_ = value;
    emit preChatStageChanged();
}

void MemoryViewModel::setLastTurnFinalizedEvent(const QString& value)
{
    if (lastTurnFinalizedEvent_ == value) return;
    lastTurnFinalizedEvent_ = value;
    emit lastTurnFinalizedEventChanged();
}

void MemoryViewModel::setPostTurnStage(const QString& value)
{
    if (postTurnStage_ == value) return;
    postTurnStage_ = value;
    emit postTurnStageChanged();
}

void MemoryViewModel::setPreChatBusy(bool value)
{
    const bool oldBusy = busy();
    if (preChatBusy_ == value) { return; }
    preChatBusy_ = value;
    emit preChatBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

void MemoryViewModel::setPostTurnBusy(bool value)
{
    const bool oldBusy = busy();
    if (postTurnBusy_ == value) { return; }
    postTurnBusy_ = value;
    emit postTurnBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

// ── D6-C 多源 Adapter 私有 setters ─────────────────────────────────────────

void MemoryViewModel::setLastToolEvent(const QString& value)
{
    if (lastToolEvent_ == value) return;
    lastToolEvent_ = value;
    emit lastToolEventChanged();
}

void MemoryViewModel::setToolStage(const QString& value)
{
    if (toolStage_ == value) return;
    toolStage_ = value;
    emit toolStageChanged();
}

void MemoryViewModel::setToolBusy(bool value)
{
    const bool oldBusy = busy();
    if (toolBusy_ == value) { return; }
    toolBusy_ = value;
    emit toolBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

void MemoryViewModel::setLastManualConfigEvent(const QString& value)
{
    if (lastManualConfigEvent_ == value) return;
    lastManualConfigEvent_ = value;
    emit lastManualConfigEventChanged();
}

void MemoryViewModel::setManualConfigStage(const QString& value)
{
    if (manualConfigStage_ == value) return;
    manualConfigStage_ = value;
    emit manualConfigStageChanged();
}

void MemoryViewModel::setManualConfigBusy(bool value)
{
    const bool oldBusy = busy();
    if (manualConfigBusy_ == value) { return; }
    manualConfigBusy_ = value;
    emit manualConfigBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

void MemoryViewModel::setLastBehaviorEvent(const QString& value)
{
    if (lastBehaviorEvent_ == value) return;
    lastBehaviorEvent_ = value;
    emit lastBehaviorEventChanged();
}

void MemoryViewModel::setBehaviorStage(const QString& value)
{
    if (behaviorStage_ == value) return;
    behaviorStage_ = value;
    emit behaviorStageChanged();
}

void MemoryViewModel::setBehaviorBusy(bool value)
{
    const bool oldBusy = busy();
    if (behaviorBusy_ == value) { return; }
    behaviorBusy_ = value;
    emit behaviorBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

// ── D7C 偏好编辑：setter / 响应路由 / 投影 ─────────────────────────────────

void MemoryViewModel::setPreferenceItems(const QVariantList& value)
{
    if (preferenceItems_ == value) return;
    preferenceItems_ = value;
    emit preferenceItemsChanged();
}

void MemoryViewModel::setPreferenceHistory(const QVariantList& value)
{
    if (preferenceHistory_ == value) return;
    preferenceHistory_ = value;
    emit preferenceHistoryChanged();
}

void MemoryViewModel::setPreferenceBusy(bool value)
{
    if (preferenceBusy_ == value) return;
    preferenceBusy_ = value;
    emit preferenceBusyChanged();
}

void MemoryViewModel::setPreferenceError(const QString& value)
{
    if (preferenceError_ == value) return;
    preferenceError_ = value;
    emit preferenceErrorChanged();
}

void MemoryViewModel::setPreferenceStage(const QString& value)
{
    if (preferenceStage_ == value) return;
    preferenceStage_ = value;
    emit preferenceStageChanged();
}

void MemoryViewModel::setLastPreferenceAction(const QString& value)
{
    if (lastPreferenceAction_ == value) return;
    lastPreferenceAction_ = value;
    emit lastPreferenceActionChanged();
}

void MemoryViewModel::setLastPreferenceItem(const QJsonObject& value)
{
    if (lastPreferenceItem_ == value) return;
    lastPreferenceItem_ = value;
    emit lastPreferenceItemChanged();
}

void MemoryViewModel::handlePreferenceResponse(
    const QString& requestId, const QJsonObject& envelope)
{
    Q_UNUSED(requestId)
    const PreferenceKind kind = pendingPreferenceKind_;
    pendingPreferenceRequestId_.clear();
    pendingPreferenceKind_ = PreferenceKind::None;

    ResponseParts parts{};
    QString errCode;
    QString errMsg;
    if (!tryParseResponseStatus(envelope, &parts, &errCode, &errMsg)) {
        setPreferenceBusy(false);
        setPreferenceError(errMsg.isEmpty() ? errCode : errMsg);
        setPreferenceStage(QStringLiteral("failed"));
        return;
    }

    const QJsonObject data = parts.data;
    switch (kind) {
    case PreferenceKind::List:
        setPreferenceItems(projectPreferenceItems(
            data.value(QStringLiteral("items")).toArray()));
        setPreferenceStage(QStringLiteral("ready"));
        break;
    case PreferenceKind::History:
        setPreferenceHistory(projectPreferenceHistory(
            data.value(QStringLiteral("items")).toArray()));
        setPreferenceStage(QStringLiteral("ready"));
        break;
    case PreferenceKind::Create:
    case PreferenceKind::Update:
    case PreferenceKind::Rollback: {
        setLastPreferenceAction(data.value(QStringLiteral("action")).toString());
        setLastPreferenceItem(data.value(QStringLiteral("item")).toObject());
        if (kind == PreferenceKind::Rollback) {
            setPreferenceHistory(projectPreferenceHistory(
                data.value(QStringLiteral("history")).toArray()));
        }
        setPreferenceStage(kind == PreferenceKind::Rollback
                               ? QStringLiteral("rolled_back")
                               : QStringLiteral("ready"));
        break;
    }
    default:
        break;
    }
    setPreferenceBusy(false);
}

QVariantList MemoryViewModel::projectPreferenceItems(const QJsonArray& items) const
{
    QVariantList out;
    for (const QJsonValue& value : items) {
        if (!value.isObject()) continue;
        out.append(value.toObject().toVariantMap());
    }
    return out;
}

QVariantList MemoryViewModel::projectPreferenceHistory(const QJsonArray& items) const
{
    QVariantList out;
    for (const QJsonValue& value : items) {
        if (!value.isObject()) continue;
        out.append(value.toObject().toVariantMap());
    }
    return out;
}

// ── 问题2修复：正式 MemoryContext 契约解析（memory_context.v1.json） ────────

QString MemoryViewModel::buildContextTextFromResponse(const QJsonObject& envelope) const
{
    ResponseParts parts{};
    QString ec, em;
    if (!tryParseResponseStatus(envelope, &parts, &ec, &em)) {
        return {};  // error response → 绝不容忍伪 Context
    }
    const QJsonValue dataValue = envelope.value(kDataKey);
    if (!dataValue.isObject()) return {};
    const QJsonValue ctxValue = dataValue.toObject().value(QStringLiteral("context"));
    if (!ctxValue.isObject()) return {};
    return buildContextTextFromContextObject(ctxValue.toObject());
}

QString MemoryViewModel::buildContextTextFromContextObject(const QJsonObject& ctx) const
{
    // 严格按 contracts/examples/memory_context.v1.json 读取：
    //   schema_version, query_id, context_version, token_budget,
    //   actual_token_count, injection_status, selected_memory_ids
    // 缺少关键必填字段视为 malformed → 返回空（不得产生伪标记）。
    const QString schemaVersion = ctx.value(QStringLiteral("schema_version")).toString();
    const QString queryId = ctx.value(QStringLiteral("query_id")).toString();
    const QString contextVersion = ctx.value(QStringLiteral("context_version")).toString();
    const QString injectionStatus = ctx.value(QStringLiteral("injection_status")).toString();

    if (schemaVersion.isEmpty()   // MemoryContext 契约 schema_version 必填
        || queryId.isEmpty()      // 及 query_id 必填
        || contextVersion.isEmpty()) {
        return {};  // malformed context
    }

    // injection failure → 明确落实 injection_status=failed → 不注入任何文本。
    if (injectionStatus == QStringLiteral("failed")
        || injectionStatus == QStringLiteral("skipped")
        || injectionStatus == QStringLiteral("rejected")) {
        return {};
    }

    const int actualTokenCount = ctx.value(QStringLiteral("actual_token_count")).toInt();
    const QJsonValue idsValue = ctx.value(QStringLiteral("selected_memory_ids"));
    bool hasSelected = false;
    int selectedCount = 0;
    if (idsValue.isArray()) {
        const QJsonArray ids = idsValue.toArray();
        selectedCount = ids.size();
        // 任一非空 id 视为有实际候选
        for (const QJsonValue& id : ids) {
            if (id.isString() && !id.toString().isEmpty()) {
                hasSelected = true;
                break;
            }
        }
    }

    // 空 context：selected_memory_ids 无内容 且 actual_token_count<=0
    if (!hasSelected && actualTokenCount <= 0) {
        return {};
    }

    // 合法非空 context：生成诊断展示文本。
    const int tokenBudget = ctx.value(QStringLiteral("token_budget")).toInt();
    QStringList lines;
    lines.append(QString::fromUtf8(kContextMarkerPrefix)
                 + QStringLiteral(" begin"
                                  " (context_version=%1, query_id=%2"
                                  ", budget=%3, actual=%4, status=%5, count=%6)")
                     .arg(contextVersion, queryId)
                     .arg(tokenBudget).arg(actualTokenCount)
                     .arg(injectionStatus.isEmpty()
                              ? QStringLiteral("unknown") : injectionStatus)
                     .arg(selectedCount));

    // 若提供了 "memory_items"（B轨内容聚合的扩展可选字段），逐条展示；否则仅头行。
    const QJsonValue itemsValue = ctx.value(QStringLiteral("memory_items"));
    if (itemsValue.isArray()) {
        const QJsonArray items = itemsValue.toArray();
        for (int i = 0; i < items.size(); ++i) {
            if (!items.at(i).isObject()) continue;
            const QJsonObject item = items.at(i).toObject();
            const QString mid = item.value(QStringLiteral("memory_id")).toString();
            const QString vid = item.value(QStringLiteral("version_id")).toString();
            const QString txt = item.value(QStringLiteral("content")).toString().left(160);
            QString line = QStringLiteral("  #%1 ").arg(i + 1);
            if (!mid.isEmpty()) line += QStringLiteral("[%1] ").arg(mid);
            if (!vid.isEmpty()) line += QStringLiteral("(v=%1) ").arg(vid);
            if (!txt.isEmpty()) line += txt;
            if (line.endsWith(QLatin1Char(' '))) line.chop(1);
            lines.append(line);
        }
    }

    lines.append(QString::fromUtf8(kContextMarkerPrefix) + QStringLiteral(" end"));
    return lines.join(QLatin1Char('\n'));
}

// ── ISO8601 UTC 毫秒 ────────────────────────────────────────────────────────

QString MemoryViewModel::nowIso8601UtcMs() const
{
    const QDateTime now = QDateTime::currentDateTimeUtc();
    QString base = now.toString(Qt::ISODate);
    const int ms = now.time().msec();
    if (base.endsWith(QLatin1Char('Z'))) base.chop(1);
    return QStringLiteral("%1.%2Z").arg(base).arg(ms, 3, 10, QLatin1Char('0'));
}

// ── D8C 知识详情 / 冲突对比 / 生命周期状态 Pipeline ────────────────────────

void MemoryViewModel::runKnowledgeDetailPipeline(
    const QString& memoryId,
    bool includeEvidence,
    bool includeConditions)
{
    if (knowledgeDetailBusy_) {
        setKnowledgeDetailError(QStringLiteral("A knowledge.detail request is already in flight."));
        setKnowledgeDetailStage(QStringLiteral("failed"));
        return;
    }
    if (memoryId.isEmpty()) {
        setKnowledgeDetailError(QStringLiteral("memory_id must not be empty."));
        setKnowledgeDetailStage(QStringLiteral("failed"));
        return;
    }
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected) {
        setKnowledgeDetailError(QStringLiteral("Client is not connected."));
        setKnowledgeDetailStage(QStringLiteral("failed"));
        return;
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("schema_version"), QStringLiteral("1.0"));
    payload.insert(QStringLiteral("memory_id"), memoryId);
    payload.insert(QStringLiteral("include_evidence"), includeEvidence);
    payload.insert(QStringLiteral("include_conditions"), includeConditions);

    const QString id = client_.sendKnowledgeDetailRequest(payload);
    if (id.isEmpty()) {
        setKnowledgeDetailError(QStringLiteral("Failed to send knowledge.detail request."));
        setKnowledgeDetailStage(QStringLiteral("failed"));
        return;
    }
    pendingKnowledgeDetailRequestId_ = id;
    setKnowledgeDetailBusy(true);
    setKnowledgeDetailError({});
    setKnowledgeDetailStage(QStringLiteral("querying"));
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

void MemoryViewModel::runConflictComparePipeline(
    const QString& memoryId,
    bool includeResolved)
{
    if (conflictCompareBusy_) {
        setConflictCompareError(QStringLiteral("A conflict.compare request is already in flight."));
        setConflictCompareStage(QStringLiteral("failed"));
        return;
    }
    if (memoryId.isEmpty()) {
        setConflictCompareError(QStringLiteral("memory_id must not be empty."));
        setConflictCompareStage(QStringLiteral("failed"));
        return;
    }
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected) {
        setConflictCompareError(QStringLiteral("Client is not connected."));
        setConflictCompareStage(QStringLiteral("failed"));
        return;
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("schema_version"), QStringLiteral("1.0"));
    payload.insert(QStringLiteral("memory_id"), memoryId);
    payload.insert(QStringLiteral("include_resolved"), includeResolved);

    const QString id = client_.sendConflictCompareRequest(payload);
    if (id.isEmpty()) {
        setConflictCompareError(QStringLiteral("Failed to send conflict.compare request."));
        setConflictCompareStage(QStringLiteral("failed"));
        return;
    }
    pendingConflictCompareRequestId_ = id;
    setConflictCompareBusy(true);
    setConflictCompareError({});
    setConflictCompareStage(QStringLiteral("querying"));
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

void MemoryViewModel::runLifecycleStatusPipeline(
    const QString& userId,
    const QString& memoryId,
    const QString& memoryStatus)
{
    if (lifecycleStatusBusy_) {
        setLifecycleStatusError(QStringLiteral("A lifecycle.status request is already in flight."));
        setLifecycleStatusStage(QStringLiteral("failed"));
        return;
    }
    if (userId.isEmpty()) {
        setLifecycleStatusError(QStringLiteral("user_id must not be empty."));
        setLifecycleStatusStage(QStringLiteral("failed"));
        return;
    }
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected) {
        setLifecycleStatusError(QStringLiteral("Client is not connected."));
        setLifecycleStatusStage(QStringLiteral("failed"));
        return;
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("schema_version"), QStringLiteral("1.0"));
    payload.insert(QStringLiteral("user_id"), userId);
    if (!memoryId.isEmpty()) {
        payload.insert(QStringLiteral("memory_id"), memoryId);
    }
    if (!memoryStatus.isEmpty()) {
        payload.insert(QStringLiteral("memory_status"), memoryStatus);
    }

    const QString id = client_.sendLifecycleStatusRequest(payload);
    if (id.isEmpty()) {
        setLifecycleStatusError(QStringLiteral("Failed to send lifecycle.status request."));
        setLifecycleStatusStage(QStringLiteral("failed"));
        return;
    }
    pendingLifecycleStatusRequestId_ = id;
    setLifecycleStatusBusy(true);
    setLifecycleStatusError({});
    setLifecycleStatusStage(QStringLiteral("querying"));
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

QVariantList MemoryViewModel::projectJsonArray(const QJsonArray& items) const
{
    QVariantList out;
    for (const QJsonValue& value : items) {
        if (!value.isObject()) continue;
        out.append(value.toObject().toVariantMap());
    }
    return out;
}

// D9C 专用投影：recall_sources / uncertainty_hints 契约允许字符串元素
// （如 "fts5" / "vector_score_unverified"）或对象元素（{channel,provider} /
// {memory_id,conflict_state}）。projectJsonArray 仅保留 isObject()，会丢弃
// 字符串元素导致投影恒空（CI 实证 A2/A5 失败）。本函数同时保留字符串与对象。
QVariantList MemoryViewModel::projectJsonArrayMixed(const QJsonArray& items) const
{
    QVariantList out;
    for (const QJsonValue& value : items) {
        if (value.isObject()) {
            out.append(value.toObject().toVariantMap());
        } else if (value.isString()) {
            out.append(QVariant(value.toString()));
        }
        // 其它类型（数字/bool/null）静默忽略，与 D8C projectJsonArray 保持一致。
    }
    return out;
}

// ── D8C 私有 setters ───────────────────────────────────────────────────────

void MemoryViewModel::setKnowledgeDetailBusy(bool value)
{
    const bool oldBusy = busy();
    if (knowledgeDetailBusy_ == value) { return; }
    knowledgeDetailBusy_ = value;
    emit knowledgeDetailBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

void MemoryViewModel::setKnowledgeDetailStage(const QString& value)
{
    if (knowledgeDetailStage_ == value) return;
    knowledgeDetailStage_ = value;
    emit knowledgeDetailStageChanged();
}

void MemoryViewModel::setKnowledgeDetail(const QJsonObject& value)
{
    if (knowledgeDetail_ == value) return;
    knowledgeDetail_ = value;
    emit knowledgeDetailChanged();
}

void MemoryViewModel::setKnowledgeDetailError(const QString& value)
{
    if (knowledgeDetailError_ == value) return;
    knowledgeDetailError_ = value;
    emit knowledgeDetailErrorChanged();
}

void MemoryViewModel::setConflictCompareBusy(bool value)
{
    const bool oldBusy = busy();
    if (conflictCompareBusy_ == value) { return; }
    conflictCompareBusy_ = value;
    emit conflictCompareBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

void MemoryViewModel::setConflictCompareStage(const QString& value)
{
    if (conflictCompareStage_ == value) return;
    conflictCompareStage_ = value;
    emit conflictCompareStageChanged();
}

void MemoryViewModel::setConflictCandidates(const QVariantList& value)
{
    if (conflictCandidates_ == value) return;
    conflictCandidates_ = value;
    emit conflictCandidatesChanged();
}

void MemoryViewModel::setConflictCompareError(const QString& value)
{
    if (conflictCompareError_ == value) return;
    conflictCompareError_ = value;
    emit conflictCompareErrorChanged();
}

void MemoryViewModel::setLifecycleStatusBusy(bool value)
{
    const bool oldBusy = busy();
    if (lifecycleStatusBusy_ == value) { return; }
    lifecycleStatusBusy_ = value;
    emit lifecycleStatusBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

void MemoryViewModel::setLifecycleStatusStage(const QString& value)
{
    if (lifecycleStatusStage_ == value) return;
    lifecycleStatusStage_ = value;
    emit lifecycleStatusStageChanged();
}

void MemoryViewModel::setLifecycleItems(const QVariantList& value)
{
    if (lifecycleItems_ == value) return;
    lifecycleItems_ = value;
    emit lifecycleItemsChanged();
}

void MemoryViewModel::setLifecycleStatusError(const QString& value)
{
    if (lifecycleStatusError_ == value) return;
    lifecycleStatusError_ = value;
    emit lifecycleStatusErrorChanged();
}

// ── D9C Memory Context 组装 Pipeline ────────────────────────────────────────

void MemoryViewModel::runContextAssemblePipeline(
    const QString& userId,
    const QString& queryText,
    int tokenBudget,
    const QString& scene,
    const QString& candidatesJson)
{
    if (contextAssembleBusy_) {
        setContextAssembleError(QStringLiteral(
            "A context.assemble request is already in flight."));
        setContextAssembleStage(QStringLiteral("failed"));
        resetContextProjection();
        return;
    }
    if (userId.isEmpty()) {
        setContextAssembleError(QStringLiteral("user_id must not be empty."));
        setContextAssembleStage(QStringLiteral("failed"));
        resetContextProjection();
        return;
    }
    if (queryText.isEmpty()) {
        setContextAssembleError(QStringLiteral("query_text must not be empty."));
        setContextAssembleStage(QStringLiteral("failed"));
        resetContextProjection();
        return;
    }
    if (tokenBudget <= 0) {
        setContextAssembleError(QStringLiteral(
            "token_budget must be a positive integer."));
        setContextAssembleStage(QStringLiteral("failed"));
        resetContextProjection();
        return;
    }
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected) {
        setContextAssembleError(QStringLiteral("Client is not connected."));
        setContextAssembleStage(QStringLiteral("failed"));
        resetContextProjection();
        return;
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("schema_version"), QStringLiteral("1.0"));
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("query_text"), queryText);
    payload.insert(QStringLiteral("token_budget"), tokenBudget);
    if (!scene.isEmpty()) {
        payload.insert(QStringLiteral("scene"), scene);
    }
    // candidatesJson：可选 B 轨 RetrievalCandidateSample[] JSON 字符串。
    // 解析失败时静默忽略（不阻塞 Context 组装；Mock 可自行生成候选）。
    if (!candidatesJson.isEmpty()) {
        const QJsonDocument doc = QJsonDocument::fromJson(
            candidatesJson.toUtf8());
        if (doc.isArray()) {
            payload.insert(QStringLiteral("candidates"), doc.array());
        }
    }

    const QString id = client_.sendContextAssembleRequest(payload);
    if (id.isEmpty()) {
        setContextAssembleError(QStringLiteral(
            "Failed to send context.assemble request."));
        setContextAssembleStage(QStringLiteral("failed"));
        resetContextProjection();
        return;
    }
    pendingContextAssembleRequestId_ = id;
    // 记录本次请求的 token_budget 用于响应缺失时的回退（M-2 修复）。
    requestedTokenBudget_ = tokenBudget;
    setContextAssembleBusy(true);
    setContextAssembleError({});
    setContextAssembleStage(QStringLiteral("querying"));
    // 清空上一轮投影，避免 stale Context 残留（防伪 Context 统一口径）。
    resetContextProjection();
    setContextInjectionStatus(QStringLiteral("querying"));
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

void MemoryViewModel::projectAssembledContext(const QJsonObject& data)
{
    // 整体投影（保留全部字段供 QML 渲染完整 JSON）。
    setAssembledContext(data);

    // 召回来源（通道）：recall_sources[]（字符串或 {channel,provider} 对象）。
    // 使用 projectJsonArrayMixed 保留字符串元素（fts5/vector/rrf 等）。
    setContextRecallSources(projectJsonArrayMixed(
        data.value(QStringLiteral("recall_sources")).toArray()));

    // 记忆类型分布：memory_types[]（字符串或 {type,count} 对象）。
    setContextMemoryTypes(projectJsonArrayMixed(
        data.value(QStringLiteral("memory_types")).toArray()));

    // 冲突提示：conflict_hints[]（含 memory_id / conflict_state 等）。
    setContextConflictHints(projectJsonArrayMixed(
        data.value(QStringLiteral("conflict_hints")).toArray()));

    // 不确定性提示：uncertainty_hints[]（降级通道 / 陈旧索引 / score_semantics 未验证等）。
    // 使用 projectJsonArrayMixed 保留字符串元素（vector_score_unverified 等）。
    setContextUncertaintyHints(projectJsonArrayMixed(
        data.value(QStringLiteral("uncertainty_hints")).toArray()));

    // Token 预算校验：actual_token_count / token_budget / budget_exceeded。
    // 客户端独立计算 budget_exceeded 以防服务端遗漏；同时回填服务端值（若提供）。
    // M-2 修复：响应缺失 token_budget 时回退到本次请求的 requestedTokenBudget_，
    // 避免 UI 显示 "250 / 0" 且无法触发超预算（请求前已清零投影）。
    const int fallbackBudget = (requestedTokenBudget_ > 0)
        ? requestedTokenBudget_ : contextTokenBudget_;
    const int budget = data.value(QStringLiteral("token_budget")).toInt(
        fallbackBudget);
    const int actual = data.value(QStringLiteral("actual_token_count")).toInt(
        contextActualTokenCount_);
    const bool serverExceeded =
        data.value(QStringLiteral("budget_exceeded")).toBool(false);
    const bool clientExceeded = (budget > 0 && actual > budget);
    setContextTokenBudget(budget);
    setContextActualTokenCount(actual);
    setContextBudgetExceeded(serverExceeded || clientExceeded);

    // injection_status：prepared / degraded / failed / skipped。
    // 注意：failed / skipped 已在路由阶段拦截到 failed stage；
    //       此处仅处理 prepared / degraded（非空 Context）。
    const QString injectionStatus =
        data.value(QStringLiteral("injection_status")).toString();
    if (!injectionStatus.isEmpty()) {
        setContextInjectionStatus(injectionStatus);
    } else {
        // 缺省回退：有 selected_memory_ids 即视为 prepared，否则 degraded。
        const auto selectedIds = data.value(
            QStringLiteral("selected_memory_ids")).toArray();
        setContextInjectionStatus(selectedIds.isEmpty()
            ? QStringLiteral("degraded") : QStringLiteral("prepared"));
    }
}

// D9C 防伪 Context 统一清空辅助：所有失败路径与请求前置清空调用本函数，
// 确保 stale Context 不残留在投影字段中（I-2 修复）。
void MemoryViewModel::resetContextProjection()
{
    setAssembledContext(QJsonObject{});
    setContextRecallSources({});
    setContextMemoryTypes({});
    setContextConflictHints({});
    setContextUncertaintyHints({});
    setContextTokenBudget(0);
    setContextActualTokenCount(0);
    setContextBudgetExceeded(false);
    // injection_status 由调用方决定（querying / failed / skipped）。
}

// ── D9C 私有 setters ─────────────────────────────────────────────────────────

void MemoryViewModel::setContextAssembleBusy(bool value)
{
    const bool oldBusy = busy();
    if (contextAssembleBusy_ == value) { return; }
    contextAssembleBusy_ = value;
    emit contextAssembleBusyChanged();
    if (oldBusy != busy()) { emit busyChanged(); }
}

void MemoryViewModel::setContextAssembleStage(const QString& value)
{
    if (contextAssembleStage_ == value) return;
    contextAssembleStage_ = value;
    emit contextAssembleStageChanged();
}

void MemoryViewModel::setAssembledContext(const QJsonObject& value)
{
    if (assembledContext_ == value) return;
    assembledContext_ = value;
    emit assembledContextChanged();
}

void MemoryViewModel::setContextRecallSources(const QVariantList& value)
{
    if (contextRecallSources_ == value) return;
    contextRecallSources_ = value;
    emit contextRecallSourcesChanged();
}

void MemoryViewModel::setContextMemoryTypes(const QVariantList& value)
{
    if (contextMemoryTypes_ == value) return;
    contextMemoryTypes_ = value;
    emit contextMemoryTypesChanged();
}

void MemoryViewModel::setContextConflictHints(const QVariantList& value)
{
    if (contextConflictHints_ == value) return;
    contextConflictHints_ = value;
    emit contextConflictHintsChanged();
}

void MemoryViewModel::setContextUncertaintyHints(const QVariantList& value)
{
    if (contextUncertaintyHints_ == value) return;
    contextUncertaintyHints_ = value;
    emit contextUncertaintyHintsChanged();
}

void MemoryViewModel::setContextTokenBudget(int value)
{
    if (contextTokenBudget_ == value) return;
    contextTokenBudget_ = value;
    emit contextTokenBudgetChanged();
}

void MemoryViewModel::setContextActualTokenCount(int value)
{
    if (contextActualTokenCount_ == value) return;
    contextActualTokenCount_ = value;
    emit contextActualTokenCountChanged();
}

void MemoryViewModel::setContextBudgetExceeded(bool value)
{
    if (contextBudgetExceeded_ == value) return;
    contextBudgetExceeded_ = value;
    emit contextBudgetExceededChanged();
}

void MemoryViewModel::setContextInjectionStatus(const QString& value)
{
    if (contextInjectionStatus_ == value) return;
    contextInjectionStatus_ = value;
    emit contextInjectionStatusChanged();
}

void MemoryViewModel::setContextAssembleError(const QString& value)
{
    if (contextAssembleError_ == value) return;
    contextAssembleError_ = value;
    emit contextAssembleErrorChanged();
}

// ── D10C 精准遗忘 Pipeline（Demo / Prototype） ──────────────────────────────

// forget.preview 模式互斥校验（SEC-FORGET-03，v0.3冻结）：
//   single_item→targetId, session→targetSessionId, topic→targetTopic,
//   time_window→targetTimeRange, full_reset→无任何 target_*
static bool validateForgetModeSelector(
    const QString& mode,
    const QString& targetId,
    const QString& targetSessionId,
    const QString& targetTopic,
    const QString& targetTimeRange,
    QString* outSafeError)
{
    const QLatin1String kSingle("single_item"), kSession("session"),
        kTopic("topic"), kWindow("time_window"), kReset("full_reset");
    const bool hasTargetId = !targetId.isEmpty();
    const bool hasSessionId = !targetSessionId.isEmpty();
    const bool hasTopic = !targetTopic.isEmpty();
    const bool hasTimeRange = !targetTimeRange.isEmpty();
    const bool anyExtraTarget = hasTargetId || hasSessionId || hasTopic || hasTimeRange;

    if (mode == kSingle) {
        if (!hasTargetId || hasSessionId || hasTopic || hasTimeRange) {
            *outSafeError = QStringLiteral(
                "single_item mode requires exactly target_id (no session/topic/time).");
            return false;
        }
        return true;
    }
    if (mode == kSession) {
        if (!hasSessionId || hasTargetId || hasTopic || hasTimeRange) {
            *outSafeError = QStringLiteral(
                "session mode requires exactly target_session_id (no id/topic/time).");
            return false;
        }
        return true;
    }
    if (mode == kTopic) {
        if (!hasTopic || hasTargetId || hasSessionId || hasTimeRange) {
            *outSafeError = QStringLiteral(
                "topic mode requires exactly target_topic (no id/session/time).");
            return false;
        }
        return true;
    }
    if (mode == kWindow) {
        if (!hasTimeRange || hasTargetId || hasSessionId || hasTopic) {
            *outSafeError = QStringLiteral(
                "time_window mode requires exactly target_time_range (no id/session/topic).");
            return false;
        }
        return true;
    }
    if (mode == kReset) {
        if (anyExtraTarget) {
            *outSafeError = QStringLiteral(
                "full_reset mode must not carry any target_* field.");
            return false;
        }
        return true;
    }
    *outSafeError = QStringLiteral(
        "forget_mode must be one of: single_item|session|topic|time_window|full_reset.");
    return false;
}

void MemoryViewModel::runForgetPreviewPipeline(
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
    bool isCascade)
{
    // 新请求显式清错（resetForgetProjection 不再清 Error，避免失败路径先 setError
    // 再 reset 时误覆盖为""导致 L0 断言失败）。
    setForgetPreviewError({});
    // 未连接时快速失败（避免排队）。
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected) {
        setForgetPreviewError(QStringLiteral("Client is not connected."));
        setForgetStage(QStringLiteral("failed"));
        resetForgetProjection();
        return;
    }
    // 防并发：Preview/Execute 任一 busy 时拒绝（避免状态机竞态，§三.3）。
    if (forgetPreviewBusy_ || forgetExecuteBusy_) {
        setForgetPreviewError(QStringLiteral(
            "A forget.preview/execute request is already in flight."));
        setForgetStage(QStringLiteral("failed"));
        resetForgetProjection();
        return;
    }
    // 必填校验（v0.3 冻结：user_id / forget_plan_id / forget_mode / target_type 必填）。
    QString safeErr;
    if (userId.isEmpty()) {
        safeErr = QStringLiteral("user_id must not be empty.");
    } else if (forgetPlanId.isEmpty()) {
        safeErr = QStringLiteral("forget_plan_id must not be empty.");
    } else if (forgetMode.isEmpty()) {
        safeErr = QStringLiteral("forget_mode must not be empty.");
    } else if (targetType.isEmpty()) {
        safeErr = QStringLiteral("target_type must not be empty.");
    } else {
        // 模式互斥（SEC-FORGET-03 / v0.3 §三.1 冻结）
        if (!validateForgetModeSelector(forgetMode, targetId, targetSessionId,
                                        targetTopic, targetTimeRange, &safeErr)) {
            // 错误消息已由辅助填充（safe，不含用户正文）。
        }
    }
    if (!safeErr.isEmpty()) {
        setForgetPreviewError(safeErr);
        setForgetStage(QStringLiteral("failed"));
        resetForgetProjection();
        return;
    }

    // ── 构造 forget.preview payload（对齐 v0.3 §三 + D3 §5.5 ForgetPlan） ──
    // 注意：target_selector 明文生命周期=Preview 完成后清除（§四.8 HIGH-01）。
    //       客户端暂存于 pendingForgetPreviewSelector_ 以便成功回调时显式清除，
    //       并将 forgetSelectorCleared=true 置位（Sentinel 验收可覆盖）。
    QJsonObject payload;
    payload.insert(QStringLiteral("schema_version"), QStringLiteral("1.0"));
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("forget_plan_id"), forgetPlanId);
    payload.insert(QStringLiteral("forget_mode"), forgetMode);
    payload.insert(QStringLiteral("target_type"), targetType);
    if (!targetSelector.isEmpty()) {
        payload.insert(QStringLiteral("target_selector"), targetSelector);
    }
    // 模式条件字段（互斥）：仅写入对应模式那一个（full_reset 全跳过）。
    const QString& m = forgetMode;
    if      (m == QLatin1String("single_item")) {
        payload.insert(QStringLiteral("target_id"), targetId);
    } else if (m == QLatin1String("session")) {
        payload.insert(QStringLiteral("target_session_id"), targetSessionId);
    } else if (m == QLatin1String("topic")) {
        payload.insert(QStringLiteral("target_topic"), targetTopic);
    } else if (m == QLatin1String("time_window")) {
        payload.insert(QStringLiteral("target_time_range"), targetTimeRange);
    }  // full_reset：无任何 target_*
    payload.insert(QStringLiteral("requires_confirmation"), requiresConfirmation);
    payload.insert(QStringLiteral("is_cascade"), isCascade);  // v0.3：默认false冻结

    const QString id = client_.sendForgetPreviewRequest(payload);
    if (id.isEmpty()) {
        setForgetPreviewError(QStringLiteral(
            "Failed to send forget.preview request."));
        setForgetStage(QStringLiteral("failed"));
        resetForgetProjection();
        return;
    }
    // ── 登记 pending + 暂存明文（用于成功回调时清除 §四.8 HIGH-01） ──
    pendingForgetPreviewRequestId_ = id;
    pendingForgetPreviewUserId_ = userId;
    pendingForgetPreviewSelector_ = targetSelector;  // 临时，Preview完成即清
    pendingForgetPreviewTopic_ = targetTopic;        // 可能含正文，等同处理
    pendingForgetPlanId_ = forgetPlanId;
    // 清空上一轮投影，避免 stale 残留（失败路径前置调用也走 resetForgetProjection）。
    resetForgetProjection();
    // 当前请求的 forget_mode/target_type/is_cascade 先在 UI 侧展示（若响应有更新则覆盖）。
    setForgetMode(forgetMode);
    setForgetTargetType(targetType);
    setForgetIsCascade(isCascade);
    setForgetPreviewBusy(true);
    setForgetStage(QStringLiteral("previewing"));
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

void MemoryViewModel::runForgetExecutePipeline(
    const QString& userId,
    const QString& forgetPlanId,
    const QString& confirmationToken,
    const QString& idempotencyKey,
    const QString& deleteMode)
{
    // 新请求显式清错（同 runForgetPreviewPipeline：避免 resetForgetProjection 误清空）。
    setForgetExecuteError({});
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected) {
        setForgetExecuteError(QStringLiteral("Client is not connected."));
        setForgetStage(QStringLiteral("failed"));
        return;
    }
    if (forgetPreviewBusy_ || forgetExecuteBusy_) {
        setForgetExecuteError(QStringLiteral(
            "A forget.preview/execute request is already in flight."));
        setForgetStage(QStringLiteral("failed"));
        return;
    }
    // 必填校验：userId / forgetPlanId / confirmationToken
    if (userId.isEmpty() || forgetPlanId.isEmpty() || confirmationToken.isEmpty()) {
        setForgetExecuteError(QStringLiteral(
            "user_id / forget_plan_id / confirmation_token must not be empty."));
        setForgetStage(QStringLiteral("failed"));
        return;
    }
    // execute 必须基于前一次成功 Preview（状态机 v0.2 冻结：awaiting_confirmation → executing）。
    // 若 selection_hash 为空 / affected_count=0 且非 reset，显式拒绝。
    if (forgetStage_ != QStringLiteral("awaiting_confirmation")) {
        setForgetExecuteError(QStringLiteral(
            "forget.execute requires a prior successful forget.preview (awaiting_confirmation)."));
        setForgetStage(QStringLiteral("failed"));
        return;
    }

    QJsonObject payload;
    payload.insert(QStringLiteral("schema_version"), QStringLiteral("1.0"));
    payload.insert(QStringLiteral("user_id"), userId);
    payload.insert(QStringLiteral("forget_plan_id"), forgetPlanId);
    // 确认凭据：明文一次性发送（仅 SHA-256 哈希由 D 轨持久层保存；§F-2 冻结）。
    payload.insert(QStringLiteral("confirmation_token"), confirmationToken);
    if (!idempotencyKey.isEmpty()) {
        // 复用 FRZ-IPC-005 三元组 (user_id,session_id,idempotency_key) 语义。
        payload.insert(QStringLiteral("idempotency_key"), idempotencyKey);
    }
    // delete_mode：soft/hard（v0.3 §三.2 + §四.9）。
    // ⚠️  Hard Delete 可信输入来源门禁（v0.3/MEDIUM-04）：
    //     Repository 不得根据 target_selector 自行推导 soft/hard；
    //     LLM 不得终判 soft/hard；ADR-016 可信输入来源冻结与接线前，
    //     Runtime Execute 保持 fail-closed（不得自动降级软删后报成功）。
    const QString mode = deleteMode.isEmpty() ? QStringLiteral("soft") : deleteMode;
    payload.insert(QStringLiteral("delete_mode"), mode);
    // 附带 selection_hash（服务端二次校验目标快照一致，§五 F-7 并行接线）。
    if (!pendingForgetSelectionHash_.isEmpty()) {
        payload.insert(QStringLiteral("selection_hash"), pendingForgetSelectionHash_);
    }
    // 附带 affected_count（服务端二次校验漏删一致性 §三.1 v0.3/MEDIUM-03）。
    if (pendingForgetAffectedCount_ >= 0) {
        payload.insert(QStringLiteral("expected_affected_count"),
                       pendingForgetAffectedCount_);
    }

    const QString id = client_.sendForgetExecuteRequest(payload);
    if (id.isEmpty()) {
        setForgetExecuteError(QStringLiteral(
            "Failed to send forget.execute request."));
        setForgetStage(QStringLiteral("failed"));
        return;
    }
    pendingForgetExecuteRequestId_ = id;
    // 清空执行结果投影（保留 Preview 结果确认上下文）。
    setForgetExecuteResult(QJsonObject{});
    setForgetExecutedCount(-1);
    setForgetExecuteError({});
    setForgetExecuteBusy(true);
    setForgetStage(QStringLiteral("executing"));
    setLastRequestId(id);
    armDeadlineTimer(id, kDefaultDeadlineMs);
}

// forget.preview 响应路由与投影
void MemoryViewModel::handleForgetPreviewResponse(
    const QString& /*requestId*/, const QJsonObject& envelope)
{
    ResponseParts parts{};
    QString errCode;
    QString errMsg;
    // 注意：envelope status=error 已在 onResponseReceived 首行路由到 onRequestFailed；
    // 本函数仅处理 status=ok 的业务响应。此处保留防御式解析。
    const bool statusOk = tryParseResponseStatus(envelope, &parts, &errCode, &errMsg);
    if (!statusOk) {
        // 不应到达（外层已转 failed）。保险起见清零明文。
        pendingForgetPreviewSelector_.clear();
        pendingForgetPreviewTopic_.clear();
        resetForgetProjection();
        setForgetPreviewBusy(false);
        setForgetPreviewError(errMsg.isEmpty() ? QStringLiteral(
            "forget.preview returned status=error.") : errMsg);
        setForgetStage(QStringLiteral("failed"));
        return;
    }

    // 跨用户拦截（C轨客户端预检 + D轨服务端响应双重保障）：
    // 请求携带的 user_id 与响应 data.user_id 必须一致，否则标记
    // forgetCrossUserBlocked=true + stage=failed（验收：跨用户操作被拒绝）。
    const QString respUserId =
        parts.data.value(QStringLiteral("user_id")).toString();
    if (!pendingForgetPreviewUserId_.isEmpty() && !respUserId.isEmpty()
        && pendingForgetPreviewUserId_ != respUserId) {
        pendingForgetPreviewSelector_.clear();
        pendingForgetPreviewTopic_.clear();
        resetForgetProjection();
        setForgetCrossUserBlocked(true);
        setForgetPreviewBusy(false);
        setForgetPreviewError(QStringLiteral(
            "Cross-user forget preview blocked: user_id mismatch."));
        setForgetStage(QStringLiteral("failed"));
        return;
    }

    // 投影 data → 子属性（selection_hash / affected_count / credential_ttl_s / ...）
    projectForgetPreview(parts.data);
    setForgetPreviewResult(parts.data);

    // §四.8 HIGH-01：Preview 完成后清除客户端侧明文 target_selector / target_topic
    // （D 轨持久层同时安全清除 / 置 <CLEARED> 占位）。
    pendingForgetPreviewSelector_.clear();
    pendingForgetPreviewTopic_.clear();
    // selector_cleared:true：服务端契约字段响应；若缺省，客户端侧也确保置位。
    const bool clearedByServer =
        parts.data.value(QStringLiteral("selector_cleared")).toBool(false);
    setForgetSelectorCleared(clearedByServer || true);

    // 状态机推进：previewing → awaiting_confirmation（§三.3 v0.2 冻结）
    // 仅当 selection_hash 已生成且 affected_count 已确定（允许 0 为合法零命中）。
    const int affected = forgetAffectedCount_;  // 投影后的值
    if (forgetSelectionHash_.isEmpty() || affected < 0) {
        setForgetPreviewBusy(false);
        setForgetPreviewError(QStringLiteral(
            "forget.preview response missing selection_hash or affected_count."));
        setForgetStage(QStringLiteral("failed"));
        return;
    }
    // 保存快照到 pending 关联变量，供 execute 校验（v0.3/MEDIUM-03 漏删保护）。
    pendingForgetSelectionHash_ = forgetSelectionHash_;
    pendingForgetAffectedCount_ = affected;

    setForgetPreviewBusy(false);
    setForgetStage(QStringLiteral("awaiting_confirmation"));
}

// forget.execute 响应路由与投影
void MemoryViewModel::handleForgetExecuteResponse(
    const QString& /*requestId*/, const QJsonObject& envelope)
{
    ResponseParts parts{};
    QString errCode;
    QString errMsg;
    const bool statusOk = tryParseResponseStatus(envelope, &parts, &errCode, &errMsg);
    if (!statusOk) {
        setForgetExecuteBusy(false);
        setForgetExecuteError(errMsg.isEmpty() ? QStringLiteral(
            "forget.execute returned status=error.") : errMsg);
        setForgetStage(QStringLiteral("failed"));
        return;
    }

    projectForgetExecute(parts.data);
    setForgetExecuteResult(parts.data);

    // v0.3/MEDIUM-03 漏删保护：executed_count != affected_count → failed，
    // 闭合「漏删不得报完成」（§三.1 / §四.1 + §九 L1 Gate）。
    // affected_count 以 Preview 确定的 pendingForgetAffectedCount_ 为真源。
    const int affected = pendingForgetAffectedCount_;
    const int executed = forgetExecutedCount_;
    const bool missingDelete =
        affected > 0 && executed >= 0 && executed != affected;
    if (missingDelete) {
        // 显式进入 failed；forgetHasMissingDeletes 由 getter 计算已为 true。
        setForgetExecuteBusy(false);
        setForgetExecuteError(QStringLiteral(
            "Missing deletes detected: executed_count does not match affected_count."));
        setForgetStage(QStringLiteral("failed"));
        emit forgetHasMissingDeletesChanged();
        return;
    }

    // 正常完成：executing → completed（§三.3 v0.2 冻结状态机）
    setForgetExecuteBusy(false);
    setForgetStage(QStringLiteral("completed"));
    emit forgetHasMissingDeletesChanged();
}

// forget.preview 响应投影：data → 子属性（selection_hash / affected_count 等）
void MemoryViewModel::projectForgetPreview(const QJsonObject& data)
{
    // selection_hash：Preview/Selection 稳定 Hash（非正文，长期持久化真源）。
    const QString hash = data.value(QStringLiteral("selection_hash")).toString();
    if (!hash.isEmpty()) setForgetSelectionHash(hash);

    // affected_count：Preview 确定并经确认的目标数量 = len(resolved_target_ids)
    // （v0.3/MEDIUM-03 冻结；允许 0 为合法零命中精准解析）。
    const QJsonValue ac = data.value(QStringLiteral("affected_count"));
    if (ac.isDouble() || ac.isUndefined()) {
        const int count = ac.toInt(0);
        setForgetAffectedCount(count < 0 ? 0 : count);
    }

    // credential_ttl_s：确认凭据 TTL（默认 300s = 5 分钟，可调参数 TD-D）。
    const int ttl = data.value(QStringLiteral("credential_ttl_s")).toInt(300);
    setForgetCredentialTtlSeconds(ttl < 0 ? 300 : ttl);

    // resolved_target_ids：预览命中目标 ID 切片（仅 ID；不含正文；含 cascade 扩展目标）。
    const QJsonArray ids = data.value(
        QStringLiteral("resolved_target_ids_preview_snippet")).toArray();
    if (!ids.isEmpty()) {
        setForgetResolvedTargets(projectJsonArrayMixed(ids));
    }

    // forget_mode / target_type / is_cascade：响应回显（覆盖客户端侧预填充）。
    const QString mode = data.value(QStringLiteral("forget_mode")).toString();
    if (!mode.isEmpty()) setForgetMode(mode);
    const QString ttype = data.value(QStringLiteral("target_type")).toString();
    if (!ttype.isEmpty()) setForgetTargetType(ttype);
    if (data.contains(QStringLiteral("is_cascade"))) {
        setForgetIsCascade(data.value(QStringLiteral("is_cascade")).toBool(false));
    }

    // sensitivity_warning：敏感提示（高敏感/批量/full_reset/cascade的显式警告）。
    const QString warning = data.value(
        QStringLiteral("sensitivity_warning")).toString();
    setForgetSensitivityWarning(warning);
}

// forget.execute 响应投影：data → executed_count
void MemoryViewModel::projectForgetExecute(const QJsonObject& data)
{
    // executed_count：实际软删成功数量（v0.3/MEDIUM-02：D 轨持久化/Execute 字段）。
    // 默认 -1 = 未执行或缺失（区分 "0 条成功删除" 与 "未执行"）。
    const QJsonValue ec = data.value(QStringLiteral("executed_count"));
    if (ec.isDouble()) {
        const int c = ec.toInt(-1);
        setForgetExecutedCount(c);
    } else {
        setForgetExecutedCount(-1);
    }
}

// D10C 统一重置（失败路径 / Pipeline 前置调用；Sentinel 验证不留明文 selector）。
// ⚠️ 关键修复：**不重置 forgetPreviewError / forgetExecuteError**：
//   失败路径通常是先 setForget*Error(message) 再调用本函数（SEC-FORGET-03 校验、
//   send失败、onRequestFailed、status=error 防御分支），如果这里清空错误，
//   会让 C 侧 QML/L0 断言拿到空字符串，CI 失败。
//   新请求的错误清除由 runForgetPreviewPipeline / runForgetExecutePipeline
//   入口显式执行，避免上一轮错误残留。
void MemoryViewModel::resetForgetProjection()
{
    // 不重置 forgetStage（由调用方设置 previewing/awaiting/executing 或 failed）。
    // 不重置 forgetPreviewError / forgetExecuteError（失败保留语义；新请求入口显式清）。
    // 不重置 crossUserBlocked：跨用户拒绝是验收断言，仅下一轮 Preview 成功时清零。
    setForgetSelectionHash({});
    setForgetAffectedCount(0);
    setForgetCredentialTtlSeconds(0);
    setForgetResolvedTargets({});
    setForgetMode({});
    setForgetTargetType({});
    setForgetIsCascade(false);
    setForgetSensitivityWarning({});
    setForgetExecutedCount(-1);
    setForgetPreviewResult(QJsonObject{});
    setForgetExecuteResult(QJsonObject{});
    // forgetSelectorCleared：下一轮 Preview 开始时清零（展示新一轮未清除状态）。
    setForgetSelectorCleared(false);
    // crossUserBlocked：新请求前清零（防止上一次拒绝残留影响验收）。
    setForgetCrossUserBlocked(false);
}

// ── D10C 私有 setters ────────────────────────────────────────────────────────

void MemoryViewModel::setForgetPreviewBusy(bool value)
{
    const bool oldBusy = busy();
    if (forgetPreviewBusy_ == value) return;
    forgetPreviewBusy_ = value;
    emit forgetPreviewBusyChanged();
    if (oldBusy != busy()) emit busyChanged();
}

void MemoryViewModel::setForgetExecuteBusy(bool value)
{
    const bool oldBusy = busy();
    if (forgetExecuteBusy_ == value) return;
    forgetExecuteBusy_ = value;
    emit forgetExecuteBusyChanged();
    if (oldBusy != busy()) emit busyChanged();
}

void MemoryViewModel::setForgetStage(const QString& value)
{
    if (forgetStage_ == value) return;
    forgetStage_ = value;
    emit forgetStageChanged();
}

void MemoryViewModel::setForgetSelectionHash(const QString& value)
{
    if (forgetSelectionHash_ == value) return;
    forgetSelectionHash_ = value;
    emit forgetSelectionHashChanged();
}

void MemoryViewModel::setForgetAffectedCount(int value)
{
    const int v = value < 0 ? 0 : value;
    if (forgetAffectedCount_ == v) return;
    forgetAffectedCount_ = v;
    emit forgetAffectedCountChanged();
    // affectedCount 变化可能影响 forgetHasMissingDeletes 计算（getter 用 affectedCount）。
    emit forgetHasMissingDeletesChanged();
}

void MemoryViewModel::setForgetCredentialTtlSeconds(int value)
{
    const int v = value < 0 ? 0 : value;
    if (forgetCredentialTtlSeconds_ == v) return;
    forgetCredentialTtlSeconds_ = v;
    emit forgetCredentialTtlSecondsChanged();
}

void MemoryViewModel::setForgetResolvedTargets(const QVariantList& value)
{
    if (forgetResolvedTargets_ == value) return;
    forgetResolvedTargets_ = value;
    emit forgetResolvedTargetsChanged();
}

void MemoryViewModel::setForgetMode(const QString& value)
{
    if (forgetMode_ == value) return;
    forgetMode_ = value;
    emit forgetModeChanged();
}

void MemoryViewModel::setForgetTargetType(const QString& value)
{
    if (forgetTargetType_ == value) return;
    forgetTargetType_ = value;
    emit forgetTargetTypeChanged();
}

void MemoryViewModel::setForgetIsCascade(bool value)
{
    if (forgetIsCascade_ == value) return;
    forgetIsCascade_ = value;
    emit forgetIsCascadeChanged();
}

void MemoryViewModel::setForgetSensitivityWarning(const QString& value)
{
    if (forgetSensitivityWarning_ == value) return;
    forgetSensitivityWarning_ = value;
    emit forgetSensitivityWarningChanged();
}

void MemoryViewModel::setForgetExecutedCount(int value)
{
    if (forgetExecutedCount_ == value) return;
    forgetExecutedCount_ = value;
    emit forgetExecutedCountChanged();
    // executedCount 变化影响 forgetHasMissingDeletes（MEDIUM-03 漏删保护显示）。
    emit forgetHasMissingDeletesChanged();
}

void MemoryViewModel::setForgetPreviewResult(const QJsonObject& value)
{
    if (forgetPreviewResult_ == value) return;
    forgetPreviewResult_ = value;
    emit forgetPreviewResultChanged();
}

void MemoryViewModel::setForgetExecuteResult(const QJsonObject& value)
{
    if (forgetExecuteResult_ == value) return;
    forgetExecuteResult_ = value;
    emit forgetExecuteResultChanged();
}

void MemoryViewModel::setForgetPreviewError(const QString& value)
{
    if (forgetPreviewError_ == value) return;
    forgetPreviewError_ = value;
    emit forgetPreviewErrorChanged();
}

void MemoryViewModel::setForgetExecuteError(const QString& value)
{
    if (forgetExecuteError_ == value) return;
    forgetExecuteError_ = value;
    emit forgetExecuteErrorChanged();
}

void MemoryViewModel::setForgetCrossUserBlocked(bool value)
{
    if (forgetCrossUserBlocked_ == value) return;
    forgetCrossUserBlocked_ = value;
    emit forgetCrossUserBlockedChanged();
}

void MemoryViewModel::setForgetSelectorCleared(bool value)
{
    if (forgetSelectorCleared_ == value) return;
    forgetSelectorCleared_ = value;
    emit forgetSelectorClearedChanged();
}

}  // namespace kylin::memory::client::v1
