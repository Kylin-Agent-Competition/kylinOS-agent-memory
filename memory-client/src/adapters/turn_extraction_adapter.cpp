// turn_extraction_adapter.cpp — TurnExtractionAdapter 实现（Host mapping 任务卡 S1 骨架）
//
// 生产状态：BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED（真实宿主 Chat 数据源
// 属 S2+）；本实现只依赖注入的受控 resolver，L0 用纯内存 resolver 验证契约。

#include "adapters/turn_extraction_adapter.h"

#include <QDateTime>
#include <QJsonArray>
#include <QUuid>

namespace kylin::memory::client::v1 {

namespace {

// 与 MemoryViewModel::nowIso8601UtcMs 同格式：ISO 8601 UTC 毫秒（.SSSZ）。
QString nowIso8601UtcMs()
{
    const QDateTime now = QDateTime::currentDateTimeUtc();
    QString base = now.toString(Qt::ISODate);
    const int ms = now.time().msec();
    if (base.endsWith(QLatin1Char('Z'))) base.chop(1);
    return QStringLiteral("%1.%2Z").arg(base).arg(ms, 3, 10, QLatin1Char('0'));
}

// 固定安全消息（fail-closed；不含 source_reference、不含正文，对齐
// 服务端 resolver「不记录非可信引用内容」口径）。
QString kResolverMissSafeError()
{
    return QStringLiteral(
        "turn extraction failed: controlled source resolver miss "
        "(fail-closed, no content fabricated)");
}

}  // namespace

TurnExtractionAdapter::TurnExtractionAdapter(const MemorySourceResolver* sourceResolver,
                                             const ToolResultResolver* toolResolver)
    : sourceResolver_(sourceResolver), toolResolver_(toolResolver)
{
}

QString TurnExtractionAdapter::buildSourceReference(const QString& finalMessageId,
                                                    const QString& turnId)
{
    return QStringLiteral("ref:chat-record:%1")
        .arg(finalMessageId.isEmpty() ? turnId : finalMessageId);
}

TurnExtractionOutcome TurnExtractionAdapter::extract(const TurnObservation& obs) const
{
    TurnExtractionOutcome out;

    // ── 公共标识与时间戳 ──────────────────────────────────────────────────
    const QString eventId = QStringLiteral("evt-turn-%1").arg(
        QUuid::createUuid().toString(QUuid::WithoutBraces));
    const QString idempotencyKey = QStringLiteral("turn-finalized:%1:%2")
                                       .arg(obs.sessionId, obs.turnId);
    const QString srcRef = buildSourceReference(obs.finalMessageId, obs.turnId);
    const QString collectedAt = nowIso8601UtcMs();
    // 边界 2：occurred_at 透传宿主时间；宿主缺失时回退采集时间（不编造宿主时间）。
    const QString occurredAt = obs.occurredAtIso.isEmpty() ? collectedAt : obs.occurredAtIso;

    // ── ① IPC 事件（ADR-010 映射；无正文，不依赖 resolver） ────────────────
    QJsonObject metadata{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("event_id"), eventId},
        {QStringLiteral("user_id"), obs.userId},
        {QStringLiteral("session_id"), obs.sessionId},
        {QStringLiteral("turn_id"), obs.turnId},
        {QStringLiteral("idempotency_key"), idempotencyKey},
        {QStringLiteral("occurred_at"), occurredAt},
        {QStringLiteral("collected_at"), collectedAt},
        {QStringLiteral("source_reference"), srcRef},
    };
    if (!obs.traceId.isEmpty()) metadata.insert(QStringLiteral("trace_id"), obs.traceId);
    if (!obs.retryOfTurnId.isEmpty())
        metadata.insert(QStringLiteral("retry_of_turn_id"), obs.retryOfTurnId);

    QJsonObject event;
    event.insert(QStringLiteral("metadata"), metadata);
    event.insert(QStringLiteral("is_final"), true);
    event.insert(QStringLiteral("finalized_at"), collectedAt);
    if (!obs.finalMessageId.isEmpty())
        event.insert(QStringLiteral("final_message_id"), obs.finalMessageId);
    if (!obs.finalizationReason.isEmpty())
        event.insert(QStringLiteral("finalization_reason"), obs.finalizationReason);
    if (!obs.stopReason.isEmpty())
        event.insert(QStringLiteral("stop_reason"), obs.stopReason);
    event.insert(QStringLiteral("tool_call_ids"), QJsonArray::fromStringList(obs.toolCallIds));
    out.ipcEvent = event;

    // ── ② Provider 候选骨架（边界 1+2：source_event_id 关联 + 元数据传递） ──
    QJsonObject candidate;
    candidate.insert(QStringLiteral("source_event_id"), eventId);
    candidate.insert(QStringLiteral("session_id"), obs.sessionId);
    candidate.insert(QStringLiteral("occurred_at"), occurredAt);
    candidate.insert(QStringLiteral("collected_at"), collectedAt);
    // 边界 2：真实来源类型（默认 "chat"，对齐 Provider source 字段）。
    candidate.insert(QStringLiteral("source"),
                     obs.sourceType.isEmpty() ? QStringLiteral("chat") : obs.sourceType);

    // ── ③ 正文解析（边界 3：只经受控 resolver；未命中 fail-closed） ─────────
    if (sourceResolver_ == nullptr) {
        out.status = TurnExtractionOutcome::Status::ResolverMiss;
        out.safeError = kResolverMissSafeError();
        return out;
    }
    const std::optional<ResolvedTurnContent> resolved = sourceResolver_->resolve(srcRef);
    // 防御：命中但 originalUserText 为空串 → 视为未命中
    // （turns.original_user_text NOT NULL 冻结语义，禁止空串替代）。
    if (!resolved.has_value() || resolved->originalUserText.isEmpty()) {
        out.status = TurnExtractionOutcome::Status::ResolverMiss;
        out.safeError = kResolverMissSafeError();
        return out;
    }

    out.status = TurnExtractionOutcome::Status::Extracted;
    // 正文仅进入 Provider 候选（不进入 ipcEvent / 日志 / 异常消息）。
    candidate.insert(QStringLiteral("user_text"), resolved->originalUserText);
    if (!resolved->modelResponse.isEmpty())
        candidate.insert(QStringLiteral("assistant_text"), resolved->modelResponse);

    // ── ④ tool_results 组装（边界 4：toolCallIds + 受控 Tool resolver） ─────
    QJsonArray toolResults;
    for (const QString& toolCallId : obs.toolCallIds) {
        const std::optional<ResolvedToolResult> tr =
            toolResolver_ ? toolResolver_->resolve(toolCallId) : std::nullopt;
        if (!tr.has_value()) {
            // 不编造：未命中的 tool_call_id 显式上抛，由调用方决定处置。
            out.missingToolCallIds.append(toolCallId);
            continue;
        }
        QJsonObject toolResult;
        toolResult.insert(QStringLiteral("tool_call_id"), toolCallId);
        toolResult.insert(QStringLiteral("tool_name"), tr->toolName);
        toolResult.insert(QStringLiteral("status"), tr->status);
        if (!tr->argumentsJson.isEmpty())
            toolResult.insert(QStringLiteral("arguments"), tr->argumentsJson);
        if (!tr->result.isEmpty())
            toolResult.insert(QStringLiteral("result"), tr->result);
        if (!tr->error.isEmpty())
            toolResult.insert(QStringLiteral("error"), tr->error);
        toolResults.append(toolResult);
    }
    candidate.insert(QStringLiteral("tool_results"), toolResults);

    out.providerCandidate = candidate;
    return out;
}

}  // namespace kylin::memory::client::v1
