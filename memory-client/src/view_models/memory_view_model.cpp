#include "view_models/memory_view_model.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStringList>
#include <QUuid>

namespace kylin::memory::client::v1 {

namespace {

QString stateToString(MemoryClient::ConnectionState state)
{
    switch (state) {
    case MemoryClient::ConnectionState::Disconnected:
        return QStringLiteral("disconnected");
    case MemoryClient::ConnectionState::Connecting:
        return QStringLiteral("connecting");
    case MemoryClient::ConnectionState::Connected:
        return QStringLiteral("connected");
    case MemoryClient::ConnectionState::Closing:
        return QStringLiteral("closing");
    }
    return QStringLiteral("unknown");
}

// D5-C MemoryContext 文本标记。UI/聊天库保存原文时，任何包含以下
// 标记前缀的内容都视为 "已被 MemoryContext 污染"。
constexpr const char* kContextMarkerPrefix = "[MEMORY-CONTEXT]";
constexpr const char* kContextSeparator = "\n\n---\n\n";

}  // namespace

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

MemoryViewModel::~MemoryViewModel() = default;

QString MemoryViewModel::socketPath() const
{
    return client_.socketPath();
}

void MemoryViewModel::setSocketPath(const QString& path)
{
    if (client_.socketPath() == path) {
        return;
    }
    client_.setSocketPath(path);
    emit socketPathChanged();
}

QString MemoryViewModel::connectionState() const
{
    return stateToString(client_.connectionState());
}

QString MemoryViewModel::lastError() const
{
    return client_.lastError();
}

void MemoryViewModel::connectToService()
{
    client_.connectToService();
}

void MemoryViewModel::disconnectFromService()
{
    client_.disconnectFromService();
}

void MemoryViewModel::sendHealth()
{
    setBusy(true);
    const QString id = client_.sendHealthRequest();
    if (id.isEmpty()) {
        setBusy(false);
        return;
    }
    setLastRequestId(id);
}

void MemoryViewModel::sendMemoryQuery(const QJsonObject& payload)
{
    setBusy(true);
    const QString id = client_.sendRequest(methods::kMemoryRetrieve, payload);
    if (id.isEmpty()) {
        setBusy(false);
        return;
    }
    setLastRequestId(id);
}

// ── D5-C 原文隔离验证 ────────────────────────────────────────────────────

bool MemoryViewModel::textIsolationVerified() const
{
    return verifyOriginalTextIsolation();
}

bool MemoryViewModel::verifyOriginalTextIsolation() const
{
    // 空 context 视为 trivially 通过。
    if (injectedContextText_.isEmpty()) {
        return true;
    }
    // originalUserText 若包含任何 context 标记 → 违规（原文污染）。
    if (originalUserText_.contains(QString::fromUtf8(kContextMarkerPrefix))) {
        return false;
    }
    // 逐条检查 injectedContextText 中的非空行标记片段是否落入原文
    const QStringList lines = injectedContextText_.split(
        QLatin1Char('\n'), QString::SkipEmptyParts);
    for (const QString& line : lines) {
        const QString trimmed = line.trimmed();
        if (trimmed.length() < 8) {
            continue;  // 跳过过短的行，避免误报
        }
        if (!originalUserText_.isEmpty() && originalUserText_.contains(trimmed)) {
            return false;
        }
    }
    return true;
}

// ── D5-C Pre-Chat Pipeline ────────────────────────────────────────────────

void MemoryViewModel::runPreChatPipeline(
    const QString& userId,
    const QString& sessionId,
    const QString& scene,
    int maxContextTokens,
    const QString& userOriginalText)
{
    // ① 先固化 originalUserText（永远不被 MemoryContext 修改）。
    setOriginalUserText(userOriginalText);
    // 为避免脏状态，先把合成文本清空为 "原文"，等响应回来后再注入 Context。
    setModelRequestText(userOriginalText);
    setInjectedContextText({});
    setPreChatStage(QStringLiteral("querying"));

    // ② 构造 MemoryQuery 契约并发送 memory.retrieve。
    const QJsonObject queryPayload{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("session_id"), sessionId},
        {QStringLiteral("query_text"), userOriginalText},
        {QStringLiteral("scene"), scene},
        {QStringLiteral("max_context_tokens"), maxContextTokens},
    };

    pendingPreChatMaxTokens_ = maxContextTokens > 0 ? maxContextTokens : 800;

    setBusy(true);
    const QString requestId = client_.sendRequest(
        methods::kMemoryRetrieve, queryPayload);
    if (requestId.isEmpty()) {
        setBusy(false);
        setPreChatStage(QStringLiteral("failed"));
        return;
    }
    pendingPreChatRequestId_ = requestId;
    setLastRequestId(requestId);
}

void MemoryViewModel::resetPreChatPipeline()
{
    pendingPreChatRequestId_.clear();
    setOriginalUserText({});
    setModelRequestText({});
    setInjectedContextText({});
    setPreChatStage(QStringLiteral("idle"));
}

// ── D5-C Post-Turn Pipeline ───────────────────────────────────────────────

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
    Q_UNUSED(finalAssistantText)

    setPostTurnStage(QStringLiteral("sending"));

    // 构造 TurnFinalizedEvent JSON（契约按 os-agent-integration/contracts）
    const QJsonObject event = buildTurnFinalizedEventJson(
        userId, sessionId, turnId, traceId, finalMessageId,
        finalAssistantText, finalizationReason, stopReason);

    const QJsonDocument doc(event);
    setLastTurnFinalizedEvent(QString::fromUtf8(doc.toJson(QJsonDocument::Indented)));

    setBusy(true);
    const QString requestId = client_.sendTurnFinalizedEvent(event);
    if (requestId.isEmpty()) {
        setBusy(false);
        setPostTurnStage(QStringLiteral("failed"));
        return;
    }
    setLastRequestId(requestId);
    // 发送成功不代表服务端已经 ack；responseReceived 回调会把 stage 改为 sent。
    // 但 sendTurnFinalizedEvent 只是发出去，先标记为 sending，等响应。
    // 若用户开启了 Gateway，服务端会正常回执；未开启则保持 sending 合理。
}

QJsonObject MemoryViewModel::buildTurnFinalizedEventJson(
    const QString& userId,
    const QString& sessionId,
    const QString& turnId,
    const QString& traceId,
    const QString& finalMessageId,
    const QString& finalAssistantText,
    const QString& finalizationReason,
    const QString& stopReason)
{
    Q_UNUSED(finalAssistantText)

    const QString eventId = QStringLiteral("evt-turn-%1").arg(
        QUuid::createUuid().toString(QUuid::WithoutBraces));
    const QString idempotencyKey = QStringLiteral("turn-finalized:%1:%2")
                                       .arg(sessionId, turnId);
    const QString srcRef = finalMessageId.isEmpty()
                               ? QStringLiteral("ref:chat-record:%1").arg(turnId)
                               : QStringLiteral("ref:chat-record:%1").arg(finalMessageId);

    // 时间戳
    const QString now = nowIso8601UtcMs();

    // TurnFinalizedEvent 元数据 + 必填字段（contracts v1）
    QJsonObject event{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("event_id"), eventId},
        {QStringLiteral("user_id"), userId},
        {QStringLiteral("session_id"), sessionId},
        {QStringLiteral("turn_id"), turnId},
        {QStringLiteral("occurred_at"), now},
        {QStringLiteral("collected_at"), now},
        {QStringLiteral("source_reference"), srcRef},
        {QStringLiteral("idempotency_key"), idempotencyKey},
        {QStringLiteral("is_final"), true},
        {QStringLiteral("finalized_at"), now},
    };
    if (!traceId.isEmpty()) {
        event.insert(QStringLiteral("trace_id"), traceId);
    }
    if (!finalMessageId.isEmpty()) {
        event.insert(QStringLiteral("final_message_id"), finalMessageId);
    }
    if (!finalizationReason.isEmpty()) {
        event.insert(QStringLiteral("finalization_reason"), finalizationReason);
    }
    if (!stopReason.isEmpty()) {
        event.insert(QStringLiteral("stop_reason"), stopReason);
    }
    // tool_call_ids 缺省为空数组（Post-Turn 观察基线不强制 Tool）
    event.insert(QStringLiteral("tool_call_ids"), QJsonArray{});

    return event;
}

// ── 信号槽 ────────────────────────────────────────────────────────────────

void MemoryViewModel::onConnectionStateChanged()
{
    emit connectionStateChanged();
    if (client_.connectionState() != MemoryClient::ConnectionState::Connected
        && busy_) {
        // 连接断开/未连接时，in-flight 请求会由 requestFailed 单独回报；
        // busy 在那里清零，此处不重复清。
    }
}

void MemoryViewModel::onLastErrorChanged()
{
    emit lastErrorChanged();
}

void MemoryViewModel::onResponseReceived(
    const QString& requestId, const QJsonObject& envelope)
{
    setLastResponse(envelope);

    // ── D5-C 路由：若响应匹配 pendingPreChatRequestId_ → Pre-Chat 组装
    if (!pendingPreChatRequestId_.isEmpty()
        && requestId == pendingPreChatRequestId_) {
        pendingPreChatRequestId_.clear();

        const QString ctxText = buildContextTextFromResponse(envelope);
        setInjectedContextText(ctxText);

        // 合成 modelRequestText：严格区分 "原文" vs "模型请求"。
        // UI/聊天库仅用 originalUserText；模型请求用两者拼接。
        QString combined = originalUserText_;
        if (!ctxText.isEmpty()) {
            combined += QString::fromUtf8(kContextSeparator) + ctxText;
        }
        setModelRequestText(combined);
        setPreChatStage(QStringLiteral("ready"));

        // 原文隔离信号：值可能从 true→上下文后仍需确认。
        emit textIsolationVerifiedChanged();
    }

    // 任何时候响应回来，若当前 Post-Turn 是 sending 且 requestId 匹配
    // 最后发送的请求（用 lastRequestId_ 近似判断，因为 Post-Turn 未
    // 专用 pending 变量）→ 标记 sent。
    if (postTurnStage_ == QStringLiteral("sending")
        && requestId == lastRequestId_
        && pendingPreChatRequestId_.isEmpty()) {
        setPostTurnStage(QStringLiteral("sent"));
    }

    setBusy(false);
}

void MemoryViewModel::onRequestFailed(
    const QString& requestId, const QString& errorCode, const QString& safeMessage)
{
    if (!pendingPreChatRequestId_.isEmpty()
        && requestId == pendingPreChatRequestId_) {
        pendingPreChatRequestId_.clear();
        setPreChatStage(QStringLiteral("failed"));
    }
    if (postTurnStage_ == QStringLiteral("sending")
        && requestId == lastRequestId_) {
        setPostTurnStage(QStringLiteral("failed"));
    }

    if (requestId == lastRequestId_ || requestId.isEmpty()) {
        setBusy(false);
    }
    emit requestFailed(requestId, errorCode, safeMessage);
}

void MemoryViewModel::onConnectionError(const QString& safeMessage)
{
    emit connectionError(safeMessage);
}

// ── 私有 setter / helper ─────────────────────────────────────────────────

void MemoryViewModel::setBusy(bool value)
{
    if (busy_ == value) {
        return;
    }
    busy_ = value;
    emit busyChanged();
}

void MemoryViewModel::setLastRequestId(const QString& id)
{
    if (lastRequestId_ == id) {
        return;
    }
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
    if (originalUserText_ == value) {
        return;
    }
    originalUserText_ = value;
    emit originalUserTextChanged();
    emit textIsolationVerifiedChanged();
}

void MemoryViewModel::setModelRequestText(const QString& value)
{
    if (modelRequestText_ == value) {
        return;
    }
    modelRequestText_ = value;
    emit modelRequestTextChanged();
}

void MemoryViewModel::setInjectedContextText(const QString& value)
{
    if (injectedContextText_ == value) {
        return;
    }
    injectedContextText_ = value;
    emit injectedContextTextChanged();
    emit textIsolationVerifiedChanged();
}

void MemoryViewModel::setPreChatStage(const QString& value)
{
    if (preChatStage_ == value) {
        return;
    }
    preChatStage_ = value;
    emit preChatStageChanged();
}

void MemoryViewModel::setLastTurnFinalizedEvent(const QString& value)
{
    if (lastTurnFinalizedEvent_ == value) {
        return;
    }
    lastTurnFinalizedEvent_ = value;
    emit lastTurnFinalizedEventChanged();
}

void MemoryViewModel::setPostTurnStage(const QString& value)
{
    if (postTurnStage_ == value) {
        return;
    }
    postTurnStage_ = value;
    emit postTurnStageChanged();
}

QString MemoryViewModel::buildContextTextFromResponse(const QJsonObject& envelope) const
{
    // 从 envelope → data → context_items 或等价字段构造展示文本。
    // 服务端 data 契约示例：
    //   { "context_version": "1.0", "query_id": "...", "items": [...] }
    // 降级策略：缺失字段时不抛错，返回空字符串（超时/无记忆时不阻塞聊天）。
    const QJsonValue dataValue = envelope.value(QStringLiteral("data"));
    if (!dataValue.isObject()) {
        return {};
    }
    const QJsonObject data = dataValue.toObject();

    QStringList lines;
    lines.append(QString::fromUtf8(kContextMarkerPrefix)
                 + QStringLiteral(" begin (context_version=")
                 + data.value(QStringLiteral("context_version")).toString()
                 + QStringLiteral(")"));

    const QJsonValue itemsValue = data.value(QStringLiteral("items"));
    if (itemsValue.isArray()) {
        const QJsonArray items = itemsValue.toArray();
        for (int i = 0; i < items.size(); ++i) {
            const QJsonValue item = items.at(i);
            if (!item.isObject()) {
                continue;
            }
            const QJsonObject obj = item.toObject();
            const QString title = obj.value(QStringLiteral("title")).toString();
            const QString snippet = obj.value(QStringLiteral("snippet")).toString();
            const QString type = obj.value(QStringLiteral("type")).toString();
            QString line = QStringLiteral("  #%1 [%2] ").arg(i + 1).arg(
                type.isEmpty() ? QStringLiteral("memory") : type);
            if (!title.isEmpty()) {
                line += title + QStringLiteral(" — ");
            }
            if (!snippet.isEmpty()) {
                line += snippet;
            }
            lines.append(line);
        }
    } else {
        // items 缺失：降级为把整个 data JSON 扁平化展示
        const QJsonDocument doc(data);
        const QString flat = QString::fromUtf8(doc.toJson(QJsonDocument::Compact));
        if (flat.length() > 160) {
            lines.append(QStringLiteral("  (memory summary, %1 bytes)").arg(flat.length()));
        } else {
            lines.append(QStringLiteral("  ") + flat);
        }
    }

    lines.append(QString::fromUtf8(kContextMarkerPrefix) + QStringLiteral(" end"));

    return lines.join(QLatin1Char('\n'));
}

QString MemoryViewModel::nowIso8601UtcMs() const
{
    const QDateTime now = QDateTime::currentDateTimeUtc();
    // Qt 5.12 兼容：使用 Qt::ISODate，手动补毫秒部分
    QString base = now.toString(Qt::ISODate);
    const int ms = now.time().msec();
    // ISODate 形如 2026-08-26T03:15:42Z — 把 "Z" 替换为 ".msZ"
    if (base.endsWith(QLatin1Char('Z'))) {
        base.chop(1);
    }
    return QStringLiteral("%1.%2Z").arg(base).arg(ms, 3, 10, QLatin1Char('0'));
}

}  // namespace kylin::memory::client::v1
