// test_turn_extraction_adapter.cpp — Host mapping 任务卡 S1 L0 Mock 契约测试
//
// 范围（L0 纯内存 resolver）：验证 TurnExtractionAdapter 骨架满足事件契约 v1
// §7 五边界（docs/day3/11 L237-244）：
//   §A 元数据与关联（边界 1+2）
//     A1 ipcEvent metadata/事件字段完整（ADR-010 映射，无正文）
//     A2 providerCandidate.source_event_id == metadata.event_id + 元数据传递
//     A3 occurred_at 透传宿主时间；缺失回退 collected_at（不编造）
//   §B 原文隔离（边界 3 红线）
//     B1 正文只出现在 providerCandidate，ipcEvent 序列化文本不含正文
//     B2 source_reference 生成规则（finalMessageId 优先 / turnId 回退）
//   §C fail-closed（边界 3）
//     C1 resolver 未命中 → ResolverMiss，候选无正文，safeError 不含引用/正文
//     C2 resolver 命中但 originalUserText 为空串 → 视为未命中（NOT NULL 语义）
//     C3 未注入 resolver（nullptr）→ fail-closed
//   §D tool_results 组装（边界 4）
//     D1 全部命中 → tool_results 数组完整（tool_name/status/arguments）
//     D2 部分未命中 → 不编造，missingToolCallIds 显式上抛
//     D3 无 tool_call_ids → tool_results 为空数组
//   §E 纯内存测试 resolver（边界 5）
//     E1 InMemorySourceResolver / InMemoryToolResultResolver 注册-解析往返
//   §F 事件标识一致性（与 MemoryViewModel 口径对齐）
//     F1 同 (session,turn) → idempotency_key 一致；event_id 每次不同
//
// 注意：本测试仅为 memory-client 侧 S1 骨架的 L0 契约验证（纯内存 resolver），
//       不声称真实 AI Assistant Hook / Chat DB / 正文通道已接入（生产状态保持
//       BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED，S2+ 接入真实宿主数据源）。

#include "adapters/memory_source_resolver.h"
#include "adapters/turn_extraction_adapter.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QtTest>

namespace client = kylin::memory::client::v1;

class TurnExtractionAdapterTest final : public QObject {
    Q_OBJECT

private slots:
    // §A 元数据与关联
    void ipcEventMetadataAndEventFieldsComplete();   // A1
    void providerCandidateAssociatesSourceEventId(); // A2
    void occurredAtPassthroughWithFallback();        // A3

    // §B 原文隔离
    void textOnlyInProviderCandidateNeverInIpcEvent();  // B1
    void sourceReferenceGenerationRules();              // B2

    // §C fail-closed
    void resolverMissFailsClosedWithoutFabrication();   // C1
    void resolverEmptyTextTreatedAsMiss();              // C2
    void nullResolverFailsClosed();                     // C3

    // §D tool_results 组装
    void toolResultsAssembledFromControlledResolver();  // D1
    void missingToolResultNotFabricated();              // D2
    void noToolCallsYieldsEmptyArray();                 // D3

    // §E 纯内存测试 resolver
    void inMemoryResolverRoundTrip();                   // E1

    // §F 事件标识一致性
    void idempotencyKeyStableEventIdFresh();            // F1

private:
    client::TurnObservation sampleObservation() const;
    client::InMemorySourceResolver makeRegisteredSourceResolver() const;
};

client::InMemorySourceResolver TurnExtractionAdapterTest::makeRegisteredSourceResolver() const
{
    // 预注册 sampleObservation() 对应的 source_reference（ref:chat-record:msg-hm-1）。
    client::InMemorySourceResolver src;
    src.registerContent(
        QStringLiteral("ref:chat-record:msg-hm-1"),
        client::ResolvedTurnContent{QStringLiteral("用户正文"), QString(),
                                    QStringLiteral("助手正文")});
    return src;
}

client::TurnObservation TurnExtractionAdapterTest::sampleObservation() const
{
    client::TurnObservation obs;
    obs.userId = QStringLiteral("user-l2");
    obs.sessionId = QStringLiteral("sess-hm-1");
    obs.turnId = QStringLiteral("turn-hm-1");
    obs.traceId = QStringLiteral("trace-hm-1");
    obs.finalMessageId = QStringLiteral("msg-hm-1");
    obs.finalizationReason = QStringLiteral("completed");
    obs.stopReason = QStringLiteral("stop");
    obs.retryOfTurnId.clear();
    obs.toolCallIds = QStringList{QStringLiteral("tool-call-1"), QStringLiteral("tool-call-2")};
    obs.occurredAtIso = QStringLiteral("2026-09-05T10:00:00.123Z");
    obs.sourceType = QStringLiteral("chat");
    return obs;
}

// ── §A 元数据与关联 ─────────────────────────────────────────────────────────

void TurnExtractionAdapterTest::ipcEventMetadataAndEventFieldsComplete()  // A1
{
    client::InMemorySourceResolver src = makeRegisteredSourceResolver();
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);

    const QJsonValue metaVal = out.ipcEvent.value(QStringLiteral("metadata"));
    QVERIFY2(metaVal.isObject(), "ipcEvent.metadata 必须是对象");
    const QJsonObject meta = metaVal.toObject();
    QCOMPARE(meta.value(QStringLiteral("schema_version")).toString(), QStringLiteral("1.0"));
    QVERIFY(!meta.value(QStringLiteral("event_id")).toString().isEmpty());
    QCOMPARE(meta.value(QStringLiteral("user_id")).toString(), QStringLiteral("user-l2"));
    QCOMPARE(meta.value(QStringLiteral("session_id")).toString(), QStringLiteral("sess-hm-1"));
    QCOMPARE(meta.value(QStringLiteral("turn_id")).toString(), QStringLiteral("turn-hm-1"));
    QVERIFY(!meta.value(QStringLiteral("idempotency_key")).toString().isEmpty());
    QCOMPARE(meta.value(QStringLiteral("trace_id")).toString(), QStringLiteral("trace-hm-1"));
    QCOMPARE(meta.value(QStringLiteral("occurred_at")).toString(),
             QStringLiteral("2026-09-05T10:00:00.123Z"));
    QVERIFY(!meta.value(QStringLiteral("collected_at")).toString().isEmpty());
    QCOMPARE(meta.value(QStringLiteral("source_reference")).toString(),
             QStringLiteral("ref:chat-record:msg-hm-1"));

    QCOMPARE(out.ipcEvent.value(QStringLiteral("is_final")).toBool(), true);
    QCOMPARE(out.ipcEvent.value(QStringLiteral("final_message_id")).toString(),
             QStringLiteral("msg-hm-1"));
    QCOMPARE(out.ipcEvent.value(QStringLiteral("finalization_reason")).toString(),
             QStringLiteral("completed"));
    QCOMPARE(out.ipcEvent.value(QStringLiteral("stop_reason")).toString(),
             QStringLiteral("stop"));
    const QJsonArray toolIds =
        out.ipcEvent.value(QStringLiteral("tool_call_ids")).toArray();
    QCOMPARE(toolIds.count(), 2);
    QCOMPARE(toolIds.at(0).toString(), QStringLiteral("tool-call-1"));

    // 原文隔离（边界 3 红线）：IPC 事件不携带任何正文字段。
    QVERIFY(!out.ipcEvent.contains(QStringLiteral("user_text")));
    QVERIFY(!out.ipcEvent.contains(QStringLiteral("assistant_text")));
    QVERIFY(!out.ipcEvent.contains(QStringLiteral("original_user_text")));
}

void TurnExtractionAdapterTest::providerCandidateAssociatesSourceEventId()  // A2
{
    client::InMemorySourceResolver src = makeRegisteredSourceResolver();
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);

    const QString eventId =
        out.ipcEvent.value(QStringLiteral("metadata")).toObject()
            .value(QStringLiteral("event_id")).toString();
    // 边界 1：source_event_id == C++ event_id（Provider 关联）。
    QCOMPARE(out.providerCandidate.value(QStringLiteral("source_event_id")).toString(), eventId);
    // 边界 2：session_id / occurred_at / collected_at / 真实来源类型传递。
    QCOMPARE(out.providerCandidate.value(QStringLiteral("session_id")).toString(),
             QStringLiteral("sess-hm-1"));
    QCOMPARE(out.providerCandidate.value(QStringLiteral("occurred_at")).toString(),
             QStringLiteral("2026-09-05T10:00:00.123Z"));
    QVERIFY(!out.providerCandidate.value(QStringLiteral("collected_at")).toString().isEmpty());
    QCOMPARE(out.providerCandidate.value(QStringLiteral("source")).toString(),
             QStringLiteral("chat"));
}

void TurnExtractionAdapterTest::occurredAtPassthroughWithFallback()  // A3
{
    client::InMemorySourceResolver src = makeRegisteredSourceResolver();
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    // 宿主时间缺失 → 回退采集时间（不编造宿主时间）。
    client::TurnObservation obs = sampleObservation();
    obs.occurredAtIso.clear();
    const client::TurnExtractionOutcome out = adapter.extract(obs);
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);

    const QString occurredAt = out.providerCandidate.value(QStringLiteral("occurred_at")).toString();
    const QString collectedAt =
        out.providerCandidate.value(QStringLiteral("collected_at")).toString();
    QVERIFY(!occurredAt.isEmpty());
    QCOMPARE(occurredAt, collectedAt);
}

// ── §B 原文隔离 ─────────────────────────────────────────────────────────────

void TurnExtractionAdapterTest::textOnlyInProviderCandidateNeverInIpcEvent()  // B1
{
    const QString userText = QStringLiteral("L0-ISOLATION-用户正文标记-唯一");
    const QString assistantText = QStringLiteral("L0-ISOLATION-助手正文标记-唯一");

    client::InMemorySourceResolver src;
    src.registerContent(
        QStringLiteral("ref:chat-record:msg-hm-1"),
        client::ResolvedTurnContent{userText, QString(), assistantText});
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);

    // 正文只出现在 providerCandidate。
    QCOMPARE(out.providerCandidate.value(QStringLiteral("user_text")).toString(), userText);
    QCOMPARE(out.providerCandidate.value(QStringLiteral("assistant_text")).toString(),
             assistantText);

    // 红线：ipcEvent 序列化全文不包含正文（不限于顶层字段——任何嵌套位置都不允许）。
    const QString ipcStr = QString::fromUtf8(
        QJsonDocument(out.ipcEvent).toJson(QJsonDocument::Compact));
    QVERIFY2(!ipcStr.contains(userText), "ipcEvent 不得复制用户正文（任何嵌套位置）");
    QVERIFY2(!ipcStr.contains(assistantText), "ipcEvent 不得复制助手正文（任何嵌套位置）");

    // safeError 同样不携带正文。
    QVERIFY(!out.safeError.contains(userText));
}

void TurnExtractionAdapterTest::sourceReferenceGenerationRules()  // B2
{
    // finalMessageId 非空 → ref:chat-record:{finalMessageId}
    QCOMPARE(client::TurnExtractionAdapter::buildSourceReference(
                 QStringLiteral("msg-1"), QStringLiteral("turn-1")),
             QStringLiteral("ref:chat-record:msg-1"));
    // finalMessageId 空 → 回退 turnId
    QCOMPARE(client::TurnExtractionAdapter::buildSourceReference(
                 QString(), QStringLiteral("turn-1")),
             QStringLiteral("ref:chat-record:turn-1"));

    // 端到端：观察数据缺 finalMessageId 时事件内回退生效。
    client::InMemorySourceResolver src;
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    client::TurnObservation obs = sampleObservation();
    obs.finalMessageId.clear();
    const client::TurnExtractionOutcome out = adapter.extract(obs);
    const QString srcRef = out.ipcEvent.value(QStringLiteral("metadata")).toObject()
                               .value(QStringLiteral("source_reference")).toString();
    QCOMPARE(srcRef, QStringLiteral("ref:chat-record:turn-hm-1"));
}

// ── §C fail-closed ──────────────────────────────────────────────────────────

void TurnExtractionAdapterTest::resolverMissFailsClosedWithoutFabrication()  // C1
{
    // resolver 未注册任何内容 → 未命中。
    client::InMemorySourceResolver src;
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::ResolverMiss);

    // 候选无正文（不编造、不以空串替代落库语义）。
    QVERIFY(out.providerCandidate.value(QStringLiteral("user_text")).isUndefined());
    QVERIFY(out.providerCandidate.value(QStringLiteral("assistant_text")).isUndefined());
    // safeError 非空且为固定安全消息：不含 source_reference、不含正文。
    QVERIFY(!out.safeError.isEmpty());
    QVERIFY(!out.safeError.contains(QStringLiteral("ref:chat-record")));
    QVERIFY(!out.safeError.contains(QStringLiteral("msg-hm-1")));
    // ipcEvent 仍然完整构造（不依赖 resolver；服务端可按 source_reference 自行解析）。
    QVERIFY(out.ipcEvent.contains(QStringLiteral("metadata")));
}

void TurnExtractionAdapterTest::resolverEmptyTextTreatedAsMiss()  // C2
{
    // 命中但 originalUserText 为空串 → 视为未命中
    // （turns.original_user_text NOT NULL 冻结语义，禁止空串替代）。
    client::InMemorySourceResolver src;
    src.registerContent(
        QStringLiteral("ref:chat-record:msg-hm-1"),
        client::ResolvedTurnContent{QString(), QString(), QStringLiteral("assistant-only")});
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::ResolverMiss);
    QVERIFY(out.providerCandidate.value(QStringLiteral("assistant_text")).isUndefined());
    QVERIFY(!out.safeError.isEmpty());
}

void TurnExtractionAdapterTest::nullResolverFailsClosed()  // C3
{
    // 未注入 resolver（S2 前的生产状态）→ 一律 fail-closed，不崩溃。
    const client::TurnExtractionAdapter adapter(nullptr, nullptr);
    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::ResolverMiss);
    QVERIFY(!out.safeError.isEmpty());
    QVERIFY(out.providerCandidate.isEmpty());
}

// ── §D tool_results 组装 ────────────────────────────────────────────────────

void TurnExtractionAdapterTest::toolResultsAssembledFromControlledResolver()  // D1
{
    client::InMemorySourceResolver src = makeRegisteredSourceResolver();
    client::InMemoryToolResultResolver tools;
    // ResolvedToolResult 字段序：toolName, argumentsJson, status, result, error。
    tools.registerResult(
        QStringLiteral("tool-call-1"),
        client::ResolvedToolResult{QStringLiteral("calendar.lookup"),
                                   QStringLiteral("{\"query\":\"today\"}"),
                                   QStringLiteral("success"), QString(), QString()});
    tools.registerResult(
        QStringLiteral("tool-call-2"),
        client::ResolvedToolResult{QStringLiteral("file.read"), QString(),
                                   QStringLiteral("failure"), QString(),
                                   QStringLiteral("IOError")});
    const client::TurnExtractionAdapter adapter(&src, &tools);

    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);

    const QJsonArray toolResults =
        out.providerCandidate.value(QStringLiteral("tool_results")).toArray();
    QCOMPARE(toolResults.count(), 2);
    QVERIFY(out.missingToolCallIds.isEmpty());

    const QJsonObject tr1 = toolResults.at(0).toObject();
    QCOMPARE(tr1.value(QStringLiteral("tool_call_id")).toString(),
             QStringLiteral("tool-call-1"));
    QCOMPARE(tr1.value(QStringLiteral("tool_name")).toString(), QStringLiteral("calendar.lookup"));
    QCOMPARE(tr1.value(QStringLiteral("status")).toString(), QStringLiteral("success"));
    QCOMPARE(tr1.value(QStringLiteral("arguments")).toString(),
             QStringLiteral("{\"query\":\"today\"}"));
    // success 路径不携带 error 字段。
    QVERIFY(tr1.value(QStringLiteral("error")).isUndefined());

    const QJsonObject tr2 = toolResults.at(1).toObject();
    QCOMPARE(tr2.value(QStringLiteral("status")).toString(), QStringLiteral("failure"));
    QCOMPARE(tr2.value(QStringLiteral("error")).toString(), QStringLiteral("IOError"));
    // failure 路径不携带 result 字段（不把模型自述当真实执行结果）。
    QVERIFY(tr2.value(QStringLiteral("result")).isUndefined());
}

void TurnExtractionAdapterTest::missingToolResultNotFabricated()  // D2
{
    client::InMemorySourceResolver src;
    src.registerContent(
        QStringLiteral("ref:chat-record:msg-hm-1"),
        client::ResolvedTurnContent{QStringLiteral("用户正文"), QString(), QString()});
    client::InMemoryToolResultResolver tools;
    // 只注册 tool-call-1；tool-call-2 未命中。
    tools.registerResult(
        QStringLiteral("tool-call-1"),
        client::ResolvedToolResult{QStringLiteral("calendar.lookup"), QString(),
                                   QStringLiteral("success"), QString(), QString()});
    const client::TurnExtractionAdapter adapter(&src, &tools);

    const client::TurnExtractionOutcome out = adapter.extract(sampleObservation());
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);

    const QJsonArray toolResults =
        out.providerCandidate.value(QStringLiteral("tool_results")).toArray();
    QCOMPARE(toolResults.count(), 1);
    // 未命中的 tool_call_id 显式上抛（不编造）。
    QCOMPARE(out.missingToolCallIds, QStringList{QStringLiteral("tool-call-2")});
}

void TurnExtractionAdapterTest::noToolCallsYieldsEmptyArray()  // D3
{
    client::InMemorySourceResolver src;
    src.registerContent(
        QStringLiteral("ref:chat-record:msg-hm-1"),
        client::ResolvedTurnContent{QStringLiteral("用户正文"), QString(), QString()});
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    client::TurnObservation obs = sampleObservation();
    obs.toolCallIds.clear();
    const client::TurnExtractionOutcome out = adapter.extract(obs);
    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);

    const QJsonArray toolResults =
        out.providerCandidate.value(QStringLiteral("tool_results")).toArray();
    QCOMPARE(toolResults.count(), 0);
    QVERIFY(out.missingToolCallIds.isEmpty());
}

// ── §E 纯内存测试 resolver ──────────────────────────────────────────────────

void TurnExtractionAdapterTest::inMemoryResolverRoundTrip()  // E1
{
    // InMemorySourceResolver：注册 → 命中；未注册 → 未命中。
    client::InMemorySourceResolver src;
    const client::ResolvedTurnContent content{
        QStringLiteral("注册过的用户正文"), QStringLiteral("req"), QStringLiteral("resp")};
    src.registerContent(QStringLiteral("ref:chat-record:known"), content);
    const auto hit = src.resolve(QStringLiteral("ref:chat-record:known"));
    QVERIFY(hit.has_value());
    QCOMPARE(hit->originalUserText, QStringLiteral("注册过的用户正文"));
    QCOMPARE(hit->modelRequest, QStringLiteral("req"));
    QCOMPARE(hit->modelResponse, QStringLiteral("resp"));
    QVERIFY(!src.resolve(QStringLiteral("ref:chat-record:unknown")).has_value());

    // InMemoryToolResultResolver：注册 → 命中；未注册 → 未命中。
    client::InMemoryToolResultResolver tools;
    const client::ResolvedToolResult tr{QStringLiteral("shell.exec"), QString(),
                                        QStringLiteral("cancelled"), QString(), QString()};
    tools.registerResult(QStringLiteral("tool-known"), tr);
    const auto trHit = tools.resolve(QStringLiteral("tool-known"));
    QVERIFY(trHit.has_value());
    QCOMPARE(trHit->status, QStringLiteral("cancelled"));
    QVERIFY(!tools.resolve(QStringLiteral("tool-unknown")).has_value());
}

// ── §F 事件标识一致性 ───────────────────────────────────────────────────────

void TurnExtractionAdapterTest::idempotencyKeyStableEventIdFresh()  // F1
{
    client::InMemorySourceResolver src = makeRegisteredSourceResolver();
    client::InMemoryToolResultResolver tools;
    const client::TurnExtractionAdapter adapter(&src, &tools);

    // 同一 (session, turn) 提取两次：
    // idempotency_key 一致（(session,turn) 派生）；event_id 每次新生成。
    const client::TurnExtractionOutcome out1 = adapter.extract(sampleObservation());
    const client::TurnExtractionOutcome out2 = adapter.extract(sampleObservation());

    const QJsonObject meta1 = out1.ipcEvent.value(QStringLiteral("metadata")).toObject();
    const QJsonObject meta2 = out2.ipcEvent.value(QStringLiteral("metadata")).toObject();
    QCOMPARE(meta1.value(QStringLiteral("idempotency_key")).toString(),
             meta2.value(QStringLiteral("idempotency_key")).toString());
    QVERIFY(meta1.value(QStringLiteral("event_id")).toString()
            != meta2.value(QStringLiteral("event_id")).toString());
    // Provider 关联随 event_id 同步刷新（source_event_id 每次对应新的 event_id）。
    QCOMPARE(out1.providerCandidate.value(QStringLiteral("source_event_id")).toString(),
             meta1.value(QStringLiteral("event_id")).toString());
    QCOMPARE(out2.providerCandidate.value(QStringLiteral("source_event_id")).toString(),
             meta2.value(QStringLiteral("event_id")).toString());
}

QTEST_APPLESS_MAIN(TurnExtractionAdapterTest)
#include "test_turn_extraction_adapter.moc"
