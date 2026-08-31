#include "view_models/memory_view_model.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStringList>
#include <QTimer>
#include <QUuid>

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

}  // namespace kylin::memory::client::v1
