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
  "tool_call_id": "tool-call-001",
  "tool_name": "calendar.lookup",
  "arguments_ref": "ref:tool-arguments:001",
  "started_at": "2026-08-14T05:00:00.000Z",
  "finished_at": "2026-08-14T05:00:00.150Z",
  "execution_status": "success",
  "result_ref": "ref:tool-result:001",
  "side_effect": false,
  "user_confirmed": true,
  "rollback_required": false,
  "rollback_status": "not_applicable",
  "source_trace_id": "trace-001"
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
  "user_id": "local-user",
  "session_id": "session-001",
  "turn_id": "turn-002",
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

}

class MemoryEventContractV1Test final : public QObject {
    Q_OBJECT

private slots:
    void memoryQueryRoundTripsKnownPayload();
    void memoryQueryValidationReportsMissingUserId();
    void memoryQueryJsonRejectsMissingUserId();
    void memoryContextRoundTripsKnownPayload();
    void memoryContextRejectsTokenCountAboveBudget();
    void memoryContextRejectsUnknownInjectionStatus();
    void toolExecutionStatusParsesKnownValues_data();
    void toolExecutionStatusParsesKnownValues();
    void toolExecutionStatusRejectsUnknownValue();
    void toolExecutionEventRoundTripsKnownPayload();
    void turnFinalizedEventRoundTripsKnownPayload();
    void turnFinalizedEventRejectsSelfRetry();
    void schemaVersionRejectsUnknownMajor_data();
    void schemaVersionRejectsUnknownMajor();
    void schemaVersionRejectsInvalidFormat();
    void schemaVersionAcceptsCompatibleMinor();
    void memoryQueryIgnoresUnknownOptionalField();
    void memoryQueryValidationReportsAllInvalidFields();
    void memoryContextRejectsNegativeCount();
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

void MemoryEventContractV1Test::turnFinalizedEventRoundTripsKnownPayload()
{
    const QJsonObject expected = knownTurnFinalizedPayload();

    const auto parsed = contract::turnFinalizedEventFromJson(expected);

    QVERIFY2(parsed.ok(), "Known-good TurnFinalizedEvent payload must satisfy the public contract");
    QVERIFY(parsed.value.has_value());
    QCOMPARE(parsed.value->toolCallIds, QStringList{QStringLiteral("tool-call-001")});
    QCOMPARE(contract::toJson(*parsed.value), expected);
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

    QTest::newRow("MemoryQuery") << 0 << memoryQuery;
    QTest::newRow("MemoryContext") << 1 << memoryContext;
    QTest::newRow("ToolExecutionEvent") << 2 << toolEvent;
    QTest::newRow("TurnFinalizedEvent") << 3 << turnEvent;
}

void MemoryEventContractV1Test::schemaVersionRejectsUnknownMajor()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);

    bool ok = false;
    QList<contract::ContractError> errors;
    switch (objectKind) {
    case 0: {
        const auto parsed = contract::memoryQueryFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 1: {
        const auto parsed = contract::memoryContextFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 2: {
        const auto parsed = contract::toolExecutionEventFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 3: {
        const auto parsed = contract::turnFinalizedEventFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    default:
        QFAIL("Unexpected object kind");
    }

    QVERIFY(!ok);
    QCOMPARE(errors.size(), 1);
    QCOMPARE(errors.first().code, QStringLiteral("unsupported_schema_version"));
    QCOMPARE(errors.first().field, QStringLiteral("schema_version"));
    QCOMPARE(errors.first().safeMessage, QStringLiteral("Unsupported schema major version."));
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
        << 0 << memoryQuery << QStringLiteral("max_context_tokens");
    QTest::newRow("MemoryContext.selected_memory_ids")
        << 1 << contextIds << QStringLiteral("selected_memory_ids");
    QTest::newRow("MemoryContext.actual_token_count")
        << 1 << contextCount << QStringLiteral("actual_token_count");
    QTest::newRow("MemoryContext.injection_status")
        << 1 << contextStatus << QStringLiteral("injection_status");
    QTest::newRow("ToolExecutionEvent.side_effect")
        << 2 << toolEvent << QStringLiteral("side_effect");
    QTest::newRow("TurnFinalizedEvent.is_final")
        << 3 << turnEvent << QStringLiteral("is_final");
}

void MemoryEventContractV1Test::requiredJsonKeysAreNotDefaulted()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);
    QFETCH(QString, removedKey);

    bool ok = false;
    QList<contract::ContractError> errors;
    switch (objectKind) {
    case 0: {
        const auto parsed = contract::memoryQueryFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 1: {
        const auto parsed = contract::memoryContextFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 2: {
        const auto parsed = contract::toolExecutionEventFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 3: {
        const auto parsed = contract::turnFinalizedEventFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    default:
        QFAIL("Unexpected object kind");
    }

    QVERIFY(!ok);
    QCOMPARE(errors.size(), 1);
    QCOMPARE(errors.first().code, QStringLiteral("required"));
    QCOMPARE(errors.first().field, removedKey);
    QCOMPARE(errors.first().safeMessage, QStringLiteral("Required field is missing."));
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
        << 0 << memoryQuery << QStringLiteral("max_context_tokens");
    QTest::newRow("MemoryContext.selected_memory_ids")
        << 1 << memoryContext << QStringLiteral("selected_memory_ids");
    QTest::newRow("ToolExecutionEvent.side_effect")
        << 2 << toolEvent << QStringLiteral("side_effect");
    QTest::newRow("TurnFinalizedEvent.is_final")
        << 3 << turnEvent << QStringLiteral("is_final");
}

void MemoryEventContractV1Test::wrongJsonTypesAreRejected()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);
    QFETCH(QString, invalidField);

    bool ok = false;
    QList<contract::ContractError> errors;
    switch (objectKind) {
    case 0: {
        const auto parsed = contract::memoryQueryFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 1: {
        const auto parsed = contract::memoryContextFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 2: {
        const auto parsed = contract::toolExecutionEventFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    case 3: {
        const auto parsed = contract::turnFinalizedEventFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
        break;
    }
    default:
        QFAIL("Unexpected object kind");
    }

    QVERIFY(!ok);
    QCOMPARE(errors.size(), 1);
    QCOMPARE(errors.first().code, QStringLiteral("invalid_type"));
    QCOMPARE(errors.first().field, invalidField);
    QCOMPARE(errors.first().safeMessage, QStringLiteral("Field has an invalid JSON type."));
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
        << 0 << memoryContext << QStringLiteral("selected_memory_ids");
    QTest::newRow("TurnFinalizedEvent.tool_call_ids")
        << 1 << turnEvent << QStringLiteral("tool_call_ids");
}

void MemoryEventContractV1Test::idArraysRejectNonStringElements()
{
    QFETCH(int, objectKind);
    QFETCH(QJsonObject, payload);
    QFETCH(QString, invalidField);

    bool ok = false;
    QList<contract::ContractError> errors;
    if (objectKind == 0) {
        const auto parsed = contract::memoryContextFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
    } else {
        const auto parsed = contract::turnFinalizedEventFromJson(payload);
        ok = parsed.ok();
        errors = parsed.errors;
    }

    QVERIFY(!ok);
    QCOMPARE(errors.size(), 1);
    QCOMPARE(errors.first().code, QStringLiteral("invalid_type"));
    QCOMPARE(errors.first().field, invalidField);
    QCOMPARE(errors.first().safeMessage, QStringLiteral("Array elements must be strings."));
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
