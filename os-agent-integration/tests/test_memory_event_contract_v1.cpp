#include "contracts/memory_event_contract_v1.h"

#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QtTest>

namespace contract = kylin::memory::contract::v1;

namespace {

QJsonObject knownMemoryQueryPayload()
{
    const QByteArray knownPayload = R"json(
{
  "schema_version": "1.0",
  "user_id": "local-user",
  "session_id": "session-001",
  "query_text": "继续昨天的任务",
  "scene": "software_development",
  "max_context_tokens": 800
}
)json";

    QJsonParseError syntaxError;
    const QJsonDocument document = QJsonDocument::fromJson(knownPayload, &syntaxError);
    Q_ASSERT(syntaxError.error == QJsonParseError::NoError);
    Q_ASSERT(document.isObject());
    return document.object();
}

QJsonObject knownMemoryContextPayload()
{
    const QByteArray knownPayload = R"json(
{
  "schema_version": "1.0",
  "event_id": "event-context-001",
  "trace_id": "trace-001",
  "user_id": "local-user",
  "session_id": "session-001",
  "turn_id": "turn-002",
  "occurred_at": "2026-08-14T04:59:59.900Z",
  "captured_at": "2026-08-14T05:00:00.000Z",
  "source_reference": "ref:context-build:001",
  "idempotency_key": "memory-context:query-001",
  "query_id": "query-001",
  "selected_memory_ids": ["memory-001", "memory-002"],
  "context_version": "context-v1",
  "token_budget": 800,
  "actual_token_count": 120,
  "sensitive_excluded_count": 1,
  "forgotten_excluded_count": 2,
  "conflict_excluded_count": 0,
  "injection_status": "prepared"
}
)json";

    QJsonParseError syntaxError;
    const QJsonDocument document = QJsonDocument::fromJson(knownPayload, &syntaxError);
    Q_ASSERT(syntaxError.error == QJsonParseError::NoError);
    Q_ASSERT(document.isObject());
    return document.object();
}

QJsonObject knownToolExecutionPayload()
{
    const QByteArray knownPayload = R"json(
{
  "schema_version": "1.0",
  "event_id": "event-tool-001",
  "trace_id": "trace-001",
  "user_id": "local-user",
  "session_id": "session-001",
  "turn_id": "turn-002",
  "occurred_at": "2026-08-14T05:00:00.150Z",
  "captured_at": "2026-08-14T05:00:00.200Z",
  "source_reference": "ref:tool-event:001",
  "idempotency_key": "tool-execution:tool-call-001",
  "tool_call_id": "tool-call-001",
  "tool_name": "calendar.lookup",
  "arguments_ref": "ref:tool-arguments:001",
  "started_at": "2026-08-14T05:00:00.000Z",
  "finished_at": "2026-08-14T05:00:00.150Z",
  "execution_status": "success",
  "result_ref": "ref:tool-result:001",
  "side_effect": false,
  "rollback_required": false,
  "rollback_status": "not_applicable"
}
)json";

    QJsonParseError syntaxError;
    const QJsonDocument document = QJsonDocument::fromJson(knownPayload, &syntaxError);
    Q_ASSERT(syntaxError.error == QJsonParseError::NoError);
    Q_ASSERT(document.isObject());
    return document.object();
}

QJsonObject knownTurnFinalizedPayload()
{
    const QByteArray knownPayload = R"json(
{
  "schema_version": "1.0",
  "event_id": "event-turn-002",
  "trace_id": "trace-001",
  "user_id": "local-user",
  "session_id": "session-001",
  "turn_id": "turn-002",
  "occurred_at": "2026-08-14T05:01:00.000Z",
  "captured_at": "2026-08-14T05:01:00.050Z",
  "source_reference": "ref:chat-record:message-003",
  "idempotency_key": "turn-finalized:session-001:turn-002",
  "final_message_id": "message-003",
  "is_final": true,
  "finalization_reason": "completed",
  "stop_reason": "stop",
  "retry_of_turn_id": "turn-001",
  "tool_call_ids": ["tool-call-001"],
  "finalized_at": "2026-08-14T05:01:00.000Z"
}
)json";

    QJsonParseError syntaxError;
    const QJsonDocument document = QJsonDocument::fromJson(knownPayload, &syntaxError);
    Q_ASSERT(syntaxError.error == QJsonParseError::NoError);
    Q_ASSERT(document.isObject());
    return document.object();
}

enum class ContractObjectKind {
    MemoryQuery,
    MemoryContext,
    ToolExecutionEvent,
    TurnFinalizedEvent,
};

struct ParseObservation {
    bool ok = false;
    QList<contract::ContractError> errors;
};

ParseObservation parseContractObject(ContractObjectKind kind, const QJsonObject& payload)
{
    switch (kind) {
    case ContractObjectKind::MemoryQuery: {
        const auto parsed = contract::memoryQueryFromJson(payload);
        return {parsed.ok(), parsed.errors};
    }
    case ContractObjectKind::MemoryContext: {
        const auto parsed = contract::memoryContextFromJson(payload);
        return {parsed.ok(), parsed.errors};
    }
    case ContractObjectKind::ToolExecutionEvent: {
        const auto parsed = contract::toolExecutionEventFromJson(payload);
        return {parsed.ok(), parsed.errors};
    }
    case ContractObjectKind::TurnFinalizedEvent: {
        const auto parsed = contract::turnFinalizedEventFromJson(payload);
        return {parsed.ok(), parsed.errors};
    }
    }
    return {};
}

}

class MemoryEventContractV1Test final : public QObject {
    Q_OBJECT

private slots:
    void memoryQueryRoundTripsKnownPayload();
    void memoryQueryValidationReportsMissingUserId();
    void memoryQueryJsonRejectsMissingUserId();
    void memoryContextRoundTripsKnownPayload();
    void memoryContextJsonRequiresEventId();
    void memoryContextJsonRequiresTrustedMetadata_data();
    void memoryContextJsonRequiresTrustedMetadata();
    void memoryContextValidationRequiresExplicitInjectionStatus();
    void memoryContextValidationRequiresTrustedMetadata_data();
    void memoryContextValidationRequiresTrustedMetadata();
    void memoryContextRejectsTokenCountAboveBudget();
    void memoryContextRejectsUnknownInjectionStatus();
    void toolExecutionStatusParsesKnownValues_data();
    void toolExecutionStatusParsesKnownValues();
    void toolExecutionStatusRejectsUnknownValue();
    void toolExecutionEventRoundTripsKnownPayload();
    void toolExecutionCanonicalJsonOmitsAbsentOrNonSuccessReferences();
    void toolExecutionJsonRequiresTrustedMetadata_data();
    void toolExecutionJsonRequiresTrustedMetadata();
    void toolExecutionValidationRequiresExplicitStatusAndSideEffect();
    void toolExecutionValidationRequiresTrustedMetadata();
    void turnFinalizedEventRoundTripsKnownPayload();
    void optionalEventMetadataIsOmittedFromCanonicalJson();
    void turnFinalizedJsonRequiresEventTimestamps_data();
    void turnFinalizedJsonRequiresEventTimestamps();
    void turnFinalizedValidationRequiresExplicitFinality();
    void turnFinalizedValidationRejectsFalseFinality();
    void turnFinalizedJsonRejectsFalseFinality();
    void turnFinalizedValidationRequiresResolvableContentReference();
    void turnFinalizedJsonRequiresResolvableContentReference();
    void turnFinalizedValidationRequiresCapturedAt();
    void turnFinalizedEventRejectsSelfRetry();
    void schemaVersionRejectsUnknownMajor_data();
    void schemaVersionRejectsUnknownMajor();
    void schemaVersionRejectsInvalidFormat();
    void schemaVersionAcceptsCompatibleMinor();
    void memoryQueryIgnoresUnknownOptionalField();
    void memoryQueryValidationReportsAllInvalidFields();
    void memoryContextRejectsNegativeCount();
    void memoryContextRejectsEmptyMemoryIdentifier();
    void toolExecutionEventRejectsInvalidTimeline();
    void toolExecutionEventSuccessRequiresResultReference();
    void turnFinalizedEventRejectsInvalidTimestamp();
    void turnFinalizedEventRejectsDuplicateToolIds();
    void packagedExamplesMatchKnownPayloads_data();
    void packagedExamplesMatchKnownPayloads();
    void requiredJsonKeysAreNotDefaulted_data();
    void requiredJsonKeysAreNotDefaulted();
    void wrongJsonTypesAreRejected_data();
    void wrongJsonTypesAreRejected();
    void eventMetadataWrongJsonTypesAreRejected_data();
    void eventMetadataWrongJsonTypesAreRejected();
    void idArraysRejectNonStringElements_data();
    void idArraysRejectNonStringElements();
    void integerFieldsRejectFractionalValues();
    void timestampsAcceptIsoWithoutMilliseconds();
};

void MemoryEventContractV1Test::memoryQueryRoundTripsKnownPayload()
{
    const QJsonObject expected = knownMemoryQueryPayload();
    const auto parsed = contract::memoryQueryFromJson(expected);

    QVERIFY2(parsed.ok(), "Known-good MemoryQuery payload must satisfy the public contract");
    QVERIFY(parsed.value.has_value());
    QCOMPARE(contract::toJson(*parsed.value), expected);
}

void MemoryEventContractV1Test::memoryQueryValidationReportsMissingUserId()
{
    const contract::MemoryQuery query{
        QStringLiteral("1.0"),
        {},
        QStringLiteral("session-001"),
        QStringLiteral("继续昨天的任务"),
        QStringLiteral("software_development"),
        800,
    };

    const auto validation = contract::validate(query);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().code, QStringLiteral("required"));
    QCOMPARE(validation.errors.first().field, QStringLiteral("user_id"));
    QCOMPARE(validation.errors.first().safeMessage, QStringLiteral("Required field is missing."));
}

void MemoryEventContractV1Test::memoryQueryJsonRejectsMissingUserId()
{
    QJsonObject payload{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("session_id"), QStringLiteral("session-001")},
        {QStringLiteral("query_text"), QStringLiteral("继续昨天的任务")},
        {QStringLiteral("scene"), QStringLiteral("software_development")},
        {QStringLiteral("max_context_tokens"), 800},
    };

    const auto parsed = contract::memoryQueryFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("user_id"));
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Required field is missing."));
}

void MemoryEventContractV1Test::memoryContextRoundTripsKnownPayload()
{
    const QJsonObject expected = knownMemoryContextPayload();

    const auto parsed = contract::memoryContextFromJson(expected);

    QVERIFY2(parsed.ok(), "Known-good MemoryContext payload must satisfy the public contract");
    QVERIFY(parsed.value.has_value());
    QCOMPARE(contract::toJson(*parsed.value), expected);
}

void MemoryEventContractV1Test::memoryContextJsonRequiresEventId()
{
    QJsonObject payload = knownMemoryContextPayload();
    payload.remove(QStringLiteral("event_id"));

    const auto parsed = contract::memoryContextFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("event_id"));
}

void MemoryEventContractV1Test::memoryContextJsonRequiresTrustedMetadata_data()
{
    QTest::addColumn<QString>("field");

    QTest::newRow("user_id") << QStringLiteral("user_id");
    QTest::newRow("session_id") << QStringLiteral("session_id");
    QTest::newRow("occurred_at") << QStringLiteral("occurred_at");
    // KMA R-1: Canonical captured_at required. Legacy alias collected_at also accepted
    // for INPUT (covered by eventMetadataAcceptsLegacyCollectedAtAlias test).
    QTest::newRow("captured_at") << QStringLiteral("captured_at");
    QTest::newRow("idempotency_key") << QStringLiteral("idempotency_key");
}

void MemoryEventContractV1Test::memoryContextJsonRequiresTrustedMetadata()
{
    QFETCH(QString, field);
    QJsonObject payload = knownMemoryContextPayload();
    payload.remove(field);

    const auto parsed = contract::memoryContextFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, field);
}

void MemoryEventContractV1Test::memoryContextValidationRequiresExplicitInjectionStatus()
{
    contract::MemoryContext context;
    context.metadata.schemaVersion = QStringLiteral("1.0");
    context.metadata.eventId = QStringLiteral("event-context-001");
    context.metadata.userId = QStringLiteral("local-user");
    context.metadata.sessionId = QStringLiteral("session-001");
    context.metadata.occurredAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T04:59:59.900Z"), Qt::ISODateWithMs);
    context.metadata.collectedAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:00:00.000Z"), Qt::ISODateWithMs);
    context.metadata.idempotencyKey = QStringLiteral("memory-context:query-001");
    context.queryId = QStringLiteral("query-001");
    context.selectedMemoryIds = QStringList{QStringLiteral("memory-001")};
    context.contextVersion = QStringLiteral("context-v1");
    context.tokenBudget = 800;
    context.actualTokenCount = 120;

    const auto validation = contract::validate(context);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().code, QStringLiteral("required"));
    QCOMPARE(validation.errors.first().field, QStringLiteral("injection_status"));
}

void MemoryEventContractV1Test::memoryContextValidationRequiresTrustedMetadata_data()
{
    QTest::addColumn<QString>("field");

    QTest::newRow("event_id") << QStringLiteral("event_id");
    QTest::newRow("user_id") << QStringLiteral("user_id");
    QTest::newRow("session_id") << QStringLiteral("session_id");
    QTest::newRow("occurred_at") << QStringLiteral("occurred_at");
    // KMA R-1: the validation struct-level check still uses the collectedAt
    // member; report the canonical field name.
    QTest::newRow("captured_at") << QStringLiteral("captured_at");
    QTest::newRow("idempotency_key") << QStringLiteral("idempotency_key");
}

void MemoryEventContractV1Test::memoryContextValidationRequiresTrustedMetadata()
{
    QFETCH(QString, field);
    const auto parsed = contract::memoryContextFromJson(knownMemoryContextPayload());
    QVERIFY(parsed.ok());
    contract::MemoryContext context = *parsed.value;

    if (field == QStringLiteral("event_id")) {
        context.metadata.eventId.clear();
    } else if (field == QStringLiteral("user_id")) {
        context.metadata.userId.clear();
    } else if (field == QStringLiteral("session_id")) {
        context.metadata.sessionId.clear();
    } else if (field == QStringLiteral("occurred_at")) {
        context.metadata.occurredAt = {};
    } else if (field == QStringLiteral("captured_at")) {
        context.metadata.collectedAt = {};
    } else if (field == QStringLiteral("idempotency_key")) {
        context.metadata.idempotencyKey.clear();
    }

    const auto validation = contract::validate(context);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().field, field);
}

void MemoryEventContractV1Test::memoryContextRejectsTokenCountAboveBudget()
{
    QJsonObject payload = knownMemoryContextPayload();
    payload.insert(QStringLiteral("actual_token_count"), 801);

    const auto parsed = contract::memoryContextFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("inconsistent_value"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("actual_token_count"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Actual token count exceeds the declared budget."));
}

void MemoryEventContractV1Test::memoryContextRejectsUnknownInjectionStatus()
{
    QJsonObject payload = knownMemoryContextPayload();
    payload.insert(QStringLiteral("injection_status"), QStringLiteral("queued"));

    const auto parsed = contract::memoryContextFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_enum"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("injection_status"));
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Unknown injection status."));
}

void MemoryEventContractV1Test::toolExecutionStatusParsesKnownValues_data()
{
    QTest::addColumn<QString>("wireValue");
    QTest::addColumn<int>("expectedValue");

    QTest::newRow("success") << QStringLiteral("success")
                              << static_cast<int>(contract::ToolExecutionStatus::Success);
    QTest::newRow("partial") << QStringLiteral("partial")
                              << static_cast<int>(contract::ToolExecutionStatus::Partial);
    QTest::newRow("failure") << QStringLiteral("failure")
                              << static_cast<int>(contract::ToolExecutionStatus::Failure);
    // KMA R-1 / DRIFT-003: Canonical business-level `failed` alias accepted on INPUT.
    QTest::newRow("failed") << QStringLiteral("failed")
                             << static_cast<int>(contract::ToolExecutionStatus::Failure);
    QTest::newRow("cancelled") << QStringLiteral("cancelled")
                                << static_cast<int>(contract::ToolExecutionStatus::Cancelled);
    QTest::newRow("timeout") << QStringLiteral("timeout")
                              << static_cast<int>(contract::ToolExecutionStatus::Timeout);
}

void MemoryEventContractV1Test::toolExecutionStatusParsesKnownValues()
{
    QFETCH(QString, wireValue);
    QFETCH(int, expectedValue);

    const auto parsed = contract::toolExecutionStatusFromString(wireValue);

    QVERIFY(parsed.ok());
    QVERIFY(parsed.value.has_value());
    QCOMPARE(static_cast<int>(*parsed.value), expectedValue);
}

void MemoryEventContractV1Test::toolExecutionStatusRejectsUnknownValue()
{
    const auto parsed = contract::toolExecutionStatusFromString(QStringLiteral("succeeded"));

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_enum"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("execution_status"));
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Unknown tool execution status."));
}

void MemoryEventContractV1Test::toolExecutionEventRoundTripsKnownPayload()
{
    const QJsonObject expected = knownToolExecutionPayload();

    const auto parsed = contract::toolExecutionEventFromJson(expected);

    QVERIFY2(parsed.ok(), "Known-good ToolExecutionEvent payload must satisfy the public contract");
    QVERIFY(parsed.value.has_value());
    QCOMPARE(contract::toJson(*parsed.value), expected);
}

void MemoryEventContractV1Test::toolExecutionCanonicalJsonOmitsAbsentOrNonSuccessReferences()
{
    QJsonObject payload = knownToolExecutionPayload();
    payload.insert(QStringLiteral("execution_status"), QStringLiteral("failure"));
    payload.remove(QStringLiteral("arguments_ref"));
    payload.remove(QStringLiteral("rollback_status"));

    const auto parsed = contract::toolExecutionEventFromJson(payload);

    QVERIFY(parsed.ok());
    QJsonObject expected = payload;
    expected.remove(QStringLiteral("result_ref"));
    QCOMPARE(contract::toJson(*parsed.value), expected);
}

void MemoryEventContractV1Test::toolExecutionJsonRequiresTrustedMetadata_data()
{
    QTest::addColumn<QString>("field");

    QTest::newRow("event_id") << QStringLiteral("event_id");
    QTest::newRow("user_id") << QStringLiteral("user_id");
    QTest::newRow("session_id") << QStringLiteral("session_id");
    QTest::newRow("occurred_at") << QStringLiteral("occurred_at");
    // KMA R-1 Canonical key.
    QTest::newRow("captured_at") << QStringLiteral("captured_at");
    QTest::newRow("idempotency_key") << QStringLiteral("idempotency_key");
}

void MemoryEventContractV1Test::toolExecutionJsonRequiresTrustedMetadata()
{
    QFETCH(QString, field);
    QJsonObject payload = knownToolExecutionPayload();
    payload.remove(field);

    const auto parsed = contract::toolExecutionEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, field);
}

void MemoryEventContractV1Test::toolExecutionValidationRequiresExplicitStatusAndSideEffect()
{
    contract::ToolExecutionEvent event;
    event.metadata.schemaVersion = QStringLiteral("1.0");
    event.metadata.eventId = QStringLiteral("event-tool-001");
    event.metadata.userId = QStringLiteral("local-user");
    event.metadata.sessionId = QStringLiteral("session-001");
    event.metadata.occurredAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:00:00.150Z"), Qt::ISODateWithMs);
    event.metadata.collectedAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:00:00.200Z"), Qt::ISODateWithMs);
    event.metadata.idempotencyKey = QStringLiteral("tool-execution:tool-call-001");
    event.toolCallId = QStringLiteral("tool-call-001");
    event.toolName = QStringLiteral("calendar.lookup");
    event.startedAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:00:00.000Z"), Qt::ISODateWithMs);
    event.finishedAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:00:00.150Z"), Qt::ISODateWithMs);

    const auto validation = contract::validate(event);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 2);
    QCOMPARE(validation.errors.at(0).code, QStringLiteral("required"));
    QCOMPARE(validation.errors.at(0).field, QStringLiteral("execution_status"));
    QCOMPARE(validation.errors.at(1).code, QStringLiteral("required"));
    QCOMPARE(validation.errors.at(1).field, QStringLiteral("side_effect"));
}

void MemoryEventContractV1Test::toolExecutionValidationRequiresTrustedMetadata()
{
    const auto parsed = contract::toolExecutionEventFromJson(knownToolExecutionPayload());
    QVERIFY(parsed.ok());
    contract::ToolExecutionEvent event = *parsed.value;
    event.metadata.eventId.clear();

    const auto validation = contract::validate(event);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().code, QStringLiteral("required"));
    QCOMPARE(validation.errors.first().field, QStringLiteral("event_id"));
}

void MemoryEventContractV1Test::turnFinalizedEventRoundTripsKnownPayload()
{
    const QJsonObject expected = knownTurnFinalizedPayload();

    const auto parsed = contract::turnFinalizedEventFromJson(expected);

    QVERIFY2(parsed.ok(), "Known-good TurnFinalizedEvent payload must satisfy the public contract");
    QVERIFY(parsed.value.has_value());
    QCOMPARE(parsed.value->toolCallIds, QStringList{QStringLiteral("tool-call-001")});
    QCOMPARE(contract::toJson(*parsed.value), expected);
}

void MemoryEventContractV1Test::optionalEventMetadataIsOmittedFromCanonicalJson()
{
    QJsonObject memoryContextPayload = knownMemoryContextPayload();
    memoryContextPayload.remove(QStringLiteral("trace_id"));
    memoryContextPayload.remove(QStringLiteral("turn_id"));
    memoryContextPayload.remove(QStringLiteral("source_reference"));
    const auto memoryContext = contract::memoryContextFromJson(memoryContextPayload);
    QVERIFY(memoryContext.ok());
    QCOMPARE(contract::toJson(*memoryContext.value), memoryContextPayload);

    QJsonObject toolEventPayload = knownToolExecutionPayload();
    toolEventPayload.remove(QStringLiteral("trace_id"));
    toolEventPayload.remove(QStringLiteral("turn_id"));
    toolEventPayload.remove(QStringLiteral("source_reference"));
    const auto toolEvent = contract::toolExecutionEventFromJson(toolEventPayload);
    QVERIFY(toolEvent.ok());
    QCOMPARE(contract::toJson(*toolEvent.value), toolEventPayload);

    QJsonObject turnEventPayload = knownTurnFinalizedPayload();
    turnEventPayload.remove(QStringLiteral("trace_id"));
    const auto turnEvent = contract::turnFinalizedEventFromJson(turnEventPayload);
    QVERIFY(turnEvent.ok());
    QCOMPARE(contract::toJson(*turnEvent.value), turnEventPayload);
}

void MemoryEventContractV1Test::turnFinalizedJsonRequiresEventTimestamps_data()
{
    QTest::addColumn<QString>("field");

    QTest::newRow("occurred_at") << QStringLiteral("occurred_at");
    // KMA R-1 Canonical key.
    QTest::newRow("captured_at") << QStringLiteral("captured_at");
}

void MemoryEventContractV1Test::turnFinalizedJsonRequiresEventTimestamps()
{
    QFETCH(QString, field);
    QJsonObject payload = knownTurnFinalizedPayload();
    payload.remove(field);

    const auto parsed = contract::turnFinalizedEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, field);
}

void MemoryEventContractV1Test::turnFinalizedValidationRequiresExplicitFinality()
{
    contract::TurnFinalizedEvent event;
    event.metadata.schemaVersion = QStringLiteral("1.0");
    event.metadata.eventId = QStringLiteral("event-turn-002");
    event.metadata.userId = QStringLiteral("local-user");
    event.metadata.sessionId = QStringLiteral("session-001");
    event.metadata.turnId = QStringLiteral("turn-002");
    event.metadata.occurredAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:01:00.000Z"), Qt::ISODateWithMs);
    event.metadata.collectedAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:01:00.050Z"), Qt::ISODateWithMs);
    event.metadata.sourceReference = QStringLiteral("ref:chat-record:message-003");
    event.metadata.idempotencyKey = QStringLiteral("turn-finalized:session-001:turn-002");
    event.finalizedAt = QDateTime::fromString(
        QStringLiteral("2026-08-14T05:01:00.000Z"), Qt::ISODateWithMs);

    const auto validation = contract::validate(event);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().code, QStringLiteral("required"));
    QCOMPARE(validation.errors.first().field, QStringLiteral("is_final"));
}

void MemoryEventContractV1Test::turnFinalizedValidationRejectsFalseFinality()
{
    const auto parsed = contract::turnFinalizedEventFromJson(knownTurnFinalizedPayload());
    QVERIFY(parsed.ok());
    contract::TurnFinalizedEvent event = *parsed.value;
    event.isFinal = false;

    const auto validation = contract::validate(event);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().code, QStringLiteral("invalid_value"));
    QCOMPARE(validation.errors.first().field, QStringLiteral("is_final"));
    QCOMPARE(validation.errors.first().safeMessage,
             QStringLiteral("Turn finalized event must set is_final to true."));
}

void MemoryEventContractV1Test::turnFinalizedJsonRejectsFalseFinality()
{
    QJsonObject payload = knownTurnFinalizedPayload();
    payload.insert(QStringLiteral("is_final"), false);

    const auto parsed = contract::turnFinalizedEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_value"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("is_final"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Turn finalized event must set is_final to true."));
}

void MemoryEventContractV1Test::turnFinalizedValidationRequiresResolvableContentReference()
{
    const auto parsed = contract::turnFinalizedEventFromJson(knownTurnFinalizedPayload());
    QVERIFY(parsed.ok());
    contract::TurnFinalizedEvent event = *parsed.value;
    event.metadata.sourceReference.clear();

    const auto validation = contract::validate(event);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().code, QStringLiteral("required"));
    QCOMPARE(validation.errors.first().field, QStringLiteral("source_reference"));
    QCOMPARE(validation.errors.first().safeMessage,
             QStringLiteral("Finalized turn requires a resolvable content reference."));
}

void MemoryEventContractV1Test::turnFinalizedJsonRequiresResolvableContentReference()
{
    QJsonObject payload = knownTurnFinalizedPayload();
    payload.remove(QStringLiteral("source_reference"));
    payload.remove(QStringLiteral("final_message_id"));

    const auto parsed = contract::turnFinalizedEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("source_reference"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Finalized turn requires a resolvable content reference."));
}

void MemoryEventContractV1Test::turnFinalizedValidationRequiresCapturedAt()
{
    const auto parsed = contract::turnFinalizedEventFromJson(knownTurnFinalizedPayload());
    QVERIFY(parsed.ok());
    contract::TurnFinalizedEvent event = *parsed.value;
    event.metadata.collectedAt = {};

    const auto validation = contract::validate(event);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 1);
    QCOMPARE(validation.errors.first().code, QStringLiteral("invalid_timestamp"));
    // KMA R-1: error reports Canonical field name captured_at.
    QCOMPARE(validation.errors.first().field, QStringLiteral("captured_at"));
}

void MemoryEventContractV1Test::turnFinalizedEventRejectsSelfRetry()
{
    QJsonObject payload = knownTurnFinalizedPayload();
    payload.insert(QStringLiteral("retry_of_turn_id"), QStringLiteral("turn-002"));

    const auto parsed = contract::turnFinalizedEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("inconsistent_value"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("retry_of_turn_id"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("A finalized turn cannot retry itself."));
}

void MemoryEventContractV1Test::schemaVersionRejectsUnknownMajor_data()
{
    QTest::addColumn<int>("objectKind");
    QTest::addColumn<QJsonObject>("payload");

    QJsonObject memoryQuery{
        {QStringLiteral("schema_version"), QStringLiteral("2.0")},
        {QStringLiteral("user_id"), QStringLiteral("local-user")},
        {QStringLiteral("session_id"), QStringLiteral("session-001")},
        {QStringLiteral("query_text"), QStringLiteral("继续昨天的任务")},
        {QStringLiteral("scene"), QStringLiteral("software_development")},
        {QStringLiteral("max_context_tokens"), 800},
    };
    QJsonObject memoryContext = knownMemoryContextPayload();
    memoryContext.insert(QStringLiteral("schema_version"), QStringLiteral("2.0"));
    QJsonObject toolEvent = knownToolExecutionPayload();
    toolEvent.insert(QStringLiteral("schema_version"), QStringLiteral("2.0"));
    QJsonObject turnEvent = knownTurnFinalizedPayload();
    turnEvent.insert(QStringLiteral("schema_version"), QStringLiteral("2.0"));

    QTest::newRow("MemoryQuery")
        << static_cast<int>(ContractObjectKind::MemoryQuery) << memoryQuery;
    QTest::newRow("MemoryContext")
        << static_cast<int>(ContractObjectKind::MemoryContext) << memoryContext;
    QTest::newRow("ToolExecutionEvent")
        << static_cast<int>(ContractObjectKind::ToolExecutionEvent) << toolEvent;
    QTest::newRow("TurnFinalizedEvent")
        << static_cast<int>(ContractObjectKind::TurnFinalizedEvent) << turnEvent;
}

void MemoryEventContractV1Test::schemaVersionRejectsUnknownMajor()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);

    const ParseObservation parsed = parseContractObject(
        static_cast<ContractObjectKind>(objectKind), payload);

    QVERIFY(!parsed.ok);
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("unsupported_schema_version"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("schema_version"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Unsupported schema major version."));
}

void MemoryEventContractV1Test::schemaVersionRejectsInvalidFormat()
{
    QJsonObject payload{
        {QStringLiteral("schema_version"), QStringLiteral("v1")},
        {QStringLiteral("user_id"), QStringLiteral("local-user")},
        {QStringLiteral("session_id"), QStringLiteral("session-001")},
        {QStringLiteral("query_text"), QStringLiteral("继续昨天的任务")},
        {QStringLiteral("scene"), QStringLiteral("software_development")},
        {QStringLiteral("max_context_tokens"), 800},
    };

    const auto parsed = contract::memoryQueryFromJson(payload);

    QVERIFY(!parsed.ok());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_version"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("schema_version"));
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Schema version must use major.minor format."));
}

void MemoryEventContractV1Test::schemaVersionAcceptsCompatibleMinor()
{
    QJsonObject payload{
        {QStringLiteral("schema_version"), QStringLiteral("1.7")},
        {QStringLiteral("user_id"), QStringLiteral("local-user")},
        {QStringLiteral("session_id"), QStringLiteral("session-001")},
        {QStringLiteral("query_text"), QStringLiteral("继续昨天的任务")},
        {QStringLiteral("scene"), QStringLiteral("software_development")},
        {QStringLiteral("max_context_tokens"), 800},
    };

    const auto parsed = contract::memoryQueryFromJson(payload);

    QVERIFY(parsed.ok());
    QVERIFY(parsed.value.has_value());
    QCOMPARE(parsed.value->schemaVersion, QStringLiteral("1.7"));
}

void MemoryEventContractV1Test::memoryQueryIgnoresUnknownOptionalField()
{
    QJsonObject payload{
        {QStringLiteral("schema_version"), QStringLiteral("1.0")},
        {QStringLiteral("user_id"), QStringLiteral("local-user")},
        {QStringLiteral("session_id"), QStringLiteral("session-001")},
        {QStringLiteral("query_text"), QStringLiteral("继续昨天的任务")},
        {QStringLiteral("scene"), QStringLiteral("software_development")},
        {QStringLiteral("max_context_tokens"), 800},
        {QStringLiteral("future_optional"), QStringLiteral("ignored")},
    };

    const auto parsed = contract::memoryQueryFromJson(payload);

    QVERIFY(parsed.ok());
    QVERIFY(parsed.value.has_value());
    QVERIFY(!contract::toJson(*parsed.value).contains(QStringLiteral("future_optional")));
}

void MemoryEventContractV1Test::memoryQueryValidationReportsAllInvalidFields()
{
    const contract::MemoryQuery query{
        QStringLiteral("1.0"),
        {},
        {},
        {},
        {},
        0,
    };

    const auto validation = contract::validate(query);

    QVERIFY(!validation.ok());
    QCOMPARE(validation.errors.size(), 5);
    QCOMPARE(validation.errors.at(0).field, QStringLiteral("user_id"));
    QCOMPARE(validation.errors.at(1).field, QStringLiteral("session_id"));
    QCOMPARE(validation.errors.at(2).field, QStringLiteral("query_text"));
    QCOMPARE(validation.errors.at(3).field, QStringLiteral("scene"));
    QCOMPARE(validation.errors.at(4).field, QStringLiteral("max_context_tokens"));
    QCOMPARE(validation.errors.at(4).code, QStringLiteral("out_of_range"));
}

void MemoryEventContractV1Test::memoryContextRejectsNegativeCount()
{
    QJsonObject payload = knownMemoryContextPayload();
    payload.insert(QStringLiteral("forgotten_excluded_count"), -1);

    const auto parsed = contract::memoryContextFromJson(payload);

    QVERIFY(!parsed.ok());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("out_of_range"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("forgotten_excluded_count"));
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Count must not be negative."));
}

void MemoryEventContractV1Test::memoryContextRejectsEmptyMemoryIdentifier()
{
    QJsonObject payload = knownMemoryContextPayload();
    payload.insert(QStringLiteral("selected_memory_ids"),
                   QJsonArray{QStringLiteral("memory-001"), QString{}});

    const auto parsed = contract::memoryContextFromJson(payload);

    QVERIFY(!parsed.ok());
    QVERIFY(!parsed.value.has_value());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_value"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("selected_memory_ids"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Memory identifiers must not be empty."));
}

void MemoryEventContractV1Test::toolExecutionEventRejectsInvalidTimeline()
{
    QJsonObject payload = knownToolExecutionPayload();
    payload.insert(QStringLiteral("finished_at"), QStringLiteral("2026-08-14T04:59:59.000Z"));

    const auto parsed = contract::toolExecutionEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("inconsistent_value"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("finished_at"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Tool finish time precedes its start time."));
}

void MemoryEventContractV1Test::toolExecutionEventSuccessRequiresResultReference()
{
    QJsonObject payload = knownToolExecutionPayload();
    payload.remove(QStringLiteral("result_ref"));

    const auto parsed = contract::toolExecutionEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("result_ref"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Successful tool execution requires a result reference."));
}

void MemoryEventContractV1Test::turnFinalizedEventRejectsInvalidTimestamp()
{
    QJsonObject payload = knownTurnFinalizedPayload();
    payload.insert(QStringLiteral("finalized_at"), QStringLiteral("not-a-time"));

    const auto parsed = contract::turnFinalizedEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_timestamp"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("finalized_at"));
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Timestamp must be valid ISO 8601."));
}

void MemoryEventContractV1Test::turnFinalizedEventRejectsDuplicateToolIds()
{
    QJsonObject payload = knownTurnFinalizedPayload();
    payload.insert(QStringLiteral("tool_call_ids"),
                   QJsonArray{QStringLiteral("tool-call-001"), QStringLiteral("tool-call-001")});

    const auto parsed = contract::turnFinalizedEventFromJson(payload);

    QVERIFY(!parsed.ok());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("duplicate_value"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("tool_call_ids"));
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Tool call identifiers must be unique within a turn."));
}

void MemoryEventContractV1Test::packagedExamplesMatchKnownPayloads_data()
{
    QTest::addColumn<QString>("fileName");
    QTest::addColumn<QJsonObject>("expected");

    QTest::newRow("MemoryQuery")
        << QStringLiteral("memory_query.v1.json") << knownMemoryQueryPayload();
    QTest::newRow("MemoryContext")
        << QStringLiteral("memory_context.v1.json") << knownMemoryContextPayload();
    QTest::newRow("ToolExecutionEvent")
        << QStringLiteral("tool_execution_event.v1.json") << knownToolExecutionPayload();
    QTest::newRow("TurnFinalizedEvent")
        << QStringLiteral("turn_finalized_event.v1.json") << knownTurnFinalizedPayload();
}

void MemoryEventContractV1Test::packagedExamplesMatchKnownPayloads()
{
    QFETCH(QString, fileName);
    QFETCH(QJsonObject, expected);

    QFile file(QDir(QStringLiteral(CONTRACT_EXAMPLE_DIR)).filePath(fileName));
    QVERIFY2(file.open(QIODevice::ReadOnly), qPrintable(file.errorString()));

    QJsonParseError syntaxError;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &syntaxError);
    QCOMPARE(syntaxError.error, QJsonParseError::NoError);
    QVERIFY(document.isObject());
    QCOMPARE(document.object(), expected);
}

void MemoryEventContractV1Test::requiredJsonKeysAreNotDefaulted_data()
{
    QTest::addColumn<int>("objectKind");
    QTest::addColumn<QJsonObject>("payload");
    QTest::addColumn<QString>("removedKey");

    QJsonObject memoryQuery = knownMemoryQueryPayload();
    memoryQuery.remove(QStringLiteral("max_context_tokens"));
    QJsonObject contextIds = knownMemoryContextPayload();
    contextIds.remove(QStringLiteral("selected_memory_ids"));
    QJsonObject contextCount = knownMemoryContextPayload();
    contextCount.remove(QStringLiteral("actual_token_count"));
    QJsonObject contextStatus = knownMemoryContextPayload();
    contextStatus.remove(QStringLiteral("injection_status"));
    QJsonObject toolEvent = knownToolExecutionPayload();
    toolEvent.remove(QStringLiteral("side_effect"));
    QJsonObject turnEvent = knownTurnFinalizedPayload();
    turnEvent.remove(QStringLiteral("is_final"));

    QTest::newRow("MemoryQuery.max_context_tokens")
        << static_cast<int>(ContractObjectKind::MemoryQuery)
        << memoryQuery << QStringLiteral("max_context_tokens");
    QTest::newRow("MemoryContext.selected_memory_ids")
        << static_cast<int>(ContractObjectKind::MemoryContext)
        << contextIds << QStringLiteral("selected_memory_ids");
    QTest::newRow("MemoryContext.actual_token_count")
        << static_cast<int>(ContractObjectKind::MemoryContext)
        << contextCount << QStringLiteral("actual_token_count");
    QTest::newRow("MemoryContext.injection_status")
        << static_cast<int>(ContractObjectKind::MemoryContext)
        << contextStatus << QStringLiteral("injection_status");
    QTest::newRow("ToolExecutionEvent.side_effect")
        << static_cast<int>(ContractObjectKind::ToolExecutionEvent)
        << toolEvent << QStringLiteral("side_effect");
    QTest::newRow("TurnFinalizedEvent.is_final")
        << static_cast<int>(ContractObjectKind::TurnFinalizedEvent)
        << turnEvent << QStringLiteral("is_final");
}

void MemoryEventContractV1Test::requiredJsonKeysAreNotDefaulted()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);
    QFETCH(QString, removedKey);

    const ParseObservation parsed = parseContractObject(
        static_cast<ContractObjectKind>(objectKind), payload);

    QVERIFY(!parsed.ok);
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("required"));
    QCOMPARE(parsed.errors.first().field, removedKey);
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Required field is missing."));
}

void MemoryEventContractV1Test::wrongJsonTypesAreRejected_data()
{
    QTest::addColumn<int>("objectKind");
    QTest::addColumn<QJsonObject>("payload");
    QTest::addColumn<QString>("invalidField");

    QJsonObject memoryQuery = knownMemoryQueryPayload();
    memoryQuery.insert(QStringLiteral("max_context_tokens"), QStringLiteral("800"));
    QJsonObject memoryContext = knownMemoryContextPayload();
    memoryContext.insert(QStringLiteral("selected_memory_ids"), QStringLiteral("memory-001"));
    QJsonObject toolEvent = knownToolExecutionPayload();
    toolEvent.insert(QStringLiteral("side_effect"), QStringLiteral("false"));
    QJsonObject turnEvent = knownTurnFinalizedPayload();
    turnEvent.insert(QStringLiteral("is_final"), QStringLiteral("true"));

    QTest::newRow("MemoryQuery.max_context_tokens")
        << static_cast<int>(ContractObjectKind::MemoryQuery)
        << memoryQuery << QStringLiteral("max_context_tokens");
    QTest::newRow("MemoryContext.selected_memory_ids")
        << static_cast<int>(ContractObjectKind::MemoryContext)
        << memoryContext << QStringLiteral("selected_memory_ids");
    QTest::newRow("ToolExecutionEvent.side_effect")
        << static_cast<int>(ContractObjectKind::ToolExecutionEvent)
        << toolEvent << QStringLiteral("side_effect");
    QTest::newRow("TurnFinalizedEvent.is_final")
        << static_cast<int>(ContractObjectKind::TurnFinalizedEvent)
        << turnEvent << QStringLiteral("is_final");
}

void MemoryEventContractV1Test::wrongJsonTypesAreRejected()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);
    QFETCH(QString, invalidField);

    const ParseObservation parsed = parseContractObject(
        static_cast<ContractObjectKind>(objectKind), payload);

    QVERIFY(!parsed.ok);
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_type"));
    QCOMPARE(parsed.errors.first().field, invalidField);
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Field has an invalid JSON type."));
}

void MemoryEventContractV1Test::eventMetadataWrongJsonTypesAreRejected_data()
{
    QTest::addColumn<int>("objectKind");
    QTest::addColumn<QJsonObject>("payload");
    QTest::addColumn<QString>("invalidField");

    QJsonObject memoryContext = knownMemoryContextPayload();
    memoryContext.insert(QStringLiteral("trace_id"), 42);
    QJsonObject toolEvent = knownToolExecutionPayload();
    toolEvent.insert(QStringLiteral("event_id"), 42);
    QJsonObject turnEvent = knownTurnFinalizedPayload();
    // KMA R-1: overwrite captured_at (Canonical) with a non-string to trigger
    // invalid_type rejection.
    turnEvent.insert(QStringLiteral("captured_at"), 42);

    QTest::newRow("MemoryContext.trace_id")
        << static_cast<int>(ContractObjectKind::MemoryContext)
        << memoryContext << QStringLiteral("trace_id");
    QTest::newRow("ToolExecutionEvent.event_id")
        << static_cast<int>(ContractObjectKind::ToolExecutionEvent)
        << toolEvent << QStringLiteral("event_id");
    QTest::newRow("TurnFinalizedEvent.captured_at")
        << static_cast<int>(ContractObjectKind::TurnFinalizedEvent)
        << turnEvent << QStringLiteral("captured_at");
}

void MemoryEventContractV1Test::eventMetadataWrongJsonTypesAreRejected()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);
    QFETCH(QString, invalidField);

    const ParseObservation parsed = parseContractObject(
        static_cast<ContractObjectKind>(objectKind), payload);

    QVERIFY(!parsed.ok);
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_type"));
    QCOMPARE(parsed.errors.first().field, invalidField);
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Field has an invalid JSON type."));
}

void MemoryEventContractV1Test::idArraysRejectNonStringElements_data()
{
    QTest::addColumn<int>("objectKind");
    QTest::addColumn<QJsonObject>("payload");
    QTest::addColumn<QString>("invalidField");

    QJsonObject memoryContext = knownMemoryContextPayload();
    memoryContext.insert(QStringLiteral("selected_memory_ids"), QJsonArray{42});
    QJsonObject turnEvent = knownTurnFinalizedPayload();
    turnEvent.insert(QStringLiteral("tool_call_ids"), QJsonArray{true});

    QTest::newRow("MemoryContext.selected_memory_ids")
        << static_cast<int>(ContractObjectKind::MemoryContext)
        << memoryContext << QStringLiteral("selected_memory_ids");
    QTest::newRow("TurnFinalizedEvent.tool_call_ids")
        << static_cast<int>(ContractObjectKind::TurnFinalizedEvent)
        << turnEvent << QStringLiteral("tool_call_ids");
}

void MemoryEventContractV1Test::idArraysRejectNonStringElements()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);
    QFETCH(QString, invalidField);

    const ParseObservation parsed = parseContractObject(
        static_cast<ContractObjectKind>(objectKind), payload);

    QVERIFY(!parsed.ok);
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_type"));
    QCOMPARE(parsed.errors.first().field, invalidField);
    QCOMPARE(parsed.errors.first().safeMessage,
             QStringLiteral("Array elements must be strings."));
}

void MemoryEventContractV1Test::integerFieldsRejectFractionalValues()
{
    QJsonObject payload = knownMemoryQueryPayload();
    payload.insert(QStringLiteral("max_context_tokens"), 800.5);

    const auto parsed = contract::memoryQueryFromJson(payload);

    QVERIFY(!parsed.ok());
    QCOMPARE(parsed.errors.size(), 1);
    QCOMPARE(parsed.errors.first().code, QStringLiteral("invalid_value"));
    QCOMPARE(parsed.errors.first().field, QStringLiteral("max_context_tokens"));
    QCOMPARE(parsed.errors.first().safeMessage, QStringLiteral("Field must be an integer."));
}

void MemoryEventContractV1Test::timestampsAcceptIsoWithoutMilliseconds()
{
    QJsonObject toolPayload = knownToolExecutionPayload();
    toolPayload.insert(QStringLiteral("started_at"), QStringLiteral("2026-08-14T05:00:00Z"));
    toolPayload.insert(QStringLiteral("finished_at"), QStringLiteral("2026-08-14T05:00:01Z"));
    const auto toolEvent = contract::toolExecutionEventFromJson(toolPayload);

    QVERIFY(toolEvent.ok());
    QVERIFY(toolEvent.value.has_value());
    QCOMPARE(contract::toJson(*toolEvent.value).value(QStringLiteral("started_at")).toString(),
             QStringLiteral("2026-08-14T05:00:00.000Z"));

    QJsonObject turnPayload = knownTurnFinalizedPayload();
    turnPayload.insert(QStringLiteral("finalized_at"), QStringLiteral("2026-08-14T05:01:00Z"));
    const auto turnEvent = contract::turnFinalizedEventFromJson(turnPayload);

    QVERIFY(turnEvent.ok());
    QVERIFY(turnEvent.value.has_value());
    QCOMPARE(contract::toJson(*turnEvent.value).value(QStringLiteral("finalized_at")).toString(),
             QStringLiteral("2026-08-14T05:01:00.000Z"));
}

QTEST_APPLESS_MAIN(MemoryEventContractV1Test)

#include "test_memory_event_contract_v1.moc"
