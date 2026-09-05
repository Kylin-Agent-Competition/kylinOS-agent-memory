#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>

#include "adapters/memory_source_resolver.h"

// ============================================================================
// TurnExtractionAdapter — C++ 元数据事件 ↔ Python Provider 桥接（骨架 S1）
// ============================================================================
//
// 状态：S1 骨架（L0 Mock resolver 契约测试）；
//       真实宿主 Chat 数据源 / Hook 观察点接入属 S2+，生产状态保持
//       BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED，不声称真实正文通道已支持。
//
// 职责（事件契约 v1 §7 五边界，docs/day3/11 L237-244）：
//   1. 以 C++ event_id 生成 Provider 候选的 source_event_id 关联；
//   2. 传递 session_id、occurred_at、collected_at 及真实来源类型；
//   3. 只通过受控 source_reference resolver 取得用户/助手正文，
//      不在 C++ 事件、普通日志或临时 JSON 复制正文（原文隔离红线）；
//   4. 通过 tool_call_ids 和受控 Tool Result resolver 组装 Provider
//      tool_results，不把模型自述当真实执行结果；
//   5. 提供生产 resolver 与纯内存测试 resolver 的注入位，
//      不修改 memory-service Provider 契约。
//
// 输出两个对象：
//   - ipcEvent：turn.finalized IPC 事件（ADR-010 映射：metadata + 事件字段，
//     无正文），经 MemoryClient 发送，服务端按 source_reference 自行解析；
//   - providerCandidate：Provider 候选（source_event_id + 正文 + tool_results），
//     正文仅经受控 resolver 进入本对象。
//
// fail-closed 语义：resolver 未命中 → status=ResolverMiss，providerCandidate
// 不含正文（禁止编造、禁止空串替代），safeError 为固定安全消息（不含引用/正文）。
// ============================================================================

namespace kylin::memory::client::v1 {

// 宿主侧 Turn 观察数据 — 仅元数据，不含正文。
// 由 Hook 观察点 / 宿主 Chat 数据源产出（S2+ 接入）。
struct TurnObservation {
    QString userId;
    QString sessionId;
    QString turnId;
    QString traceId;            // 可选
    QString finalMessageId;     // 可选（source_reference 优先键）
    QString finalizationReason; // completed | stop | retry | ...
    QString stopReason;         // 可选
    QString retryOfTurnId;      // 可选（retry 场景；须 != turnId，调用方保证）
    QStringList toolCallIds;    // 可选（本 turn 的 Tool 调用引用）
    QString occurredAtIso;      // 宿主发生时间（ISO 8601 UTC 毫秒）；空则取采集时间
    QString sourceType;         // 真实来源类型 → Provider source 字段（"chat" 等）
};

struct TurnExtractionOutcome {
    enum class Status {
        Extracted,     // resolver 命中，正文已注入 providerCandidate
        ResolverMiss,  // fail-closed：resolver 未命中，providerCandidate 不含正文
    };

    Status status = Status::ResolverMiss;
    QJsonObject ipcEvent;           // turn.finalized IPC 事件（无正文；不依赖 resolver）
    QJsonObject providerCandidate;  // Provider 候选（仅 Extracted 时含正文）
    QStringList missingToolCallIds; // Tool resolver 未命中的调用 id（不编造，显式上抛）
    QString safeError;              // ResolverMiss 时的固定安全消息（不含引用/正文）
};

class TurnExtractionAdapter {
public:
    // resolver 允许为 nullptr（未接线）：extract() 一律 fail-closed。
    TurnExtractionAdapter(const MemorySourceResolver* sourceResolver,
                          const ToolResultResolver* toolResolver);

    // 提取一次 Turn：构造 IPC 事件 + Provider 候选。
    // 红线：正文只出现在 providerCandidate；ipcEvent / 日志 / 异常消息不复制正文。
    TurnExtractionOutcome extract(const TurnObservation& obs) const;

    // source_reference 生成规则（与 MemoryViewModel 口径一致）：
    // finalMessageId 非空 → ref:chat-record:{finalMessageId}；否则回退 turnId。
    static QString buildSourceReference(const QString& finalMessageId, const QString& turnId);

private:
    const MemorySourceResolver* sourceResolver_;
    const ToolResultResolver* toolResolver_;
};

}  // namespace kylin::memory::client::v1
