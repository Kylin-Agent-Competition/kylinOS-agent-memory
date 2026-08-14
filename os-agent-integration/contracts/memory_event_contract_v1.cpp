#include "contracts/memory_event_contract_v1.h"

#include <QJsonArray>
#include <QRegularExpression>
#include <QSet>

#include <initializer_list>
#include <cmath>
#include <limits>
#include <utility>

namespace kylin::memory::contract::v1 {

namespace {

std::optional<ContractError> firstMissingRequiredField(
    const QJsonObject& object,
    std::initializer_list<QString> requiredFields)
{
    for (const QString& field : requiredFields) {
        if (!object.contains(field)) {
            return ContractError{
                QStringLiteral("required"),
                field,
                QStringLiteral("Required field is missing."),
            };
        }
    }
    return std::nullopt;
}

std::optional<ContractError> firstInvalidJsonType(
    const QJsonObject& object,
    std::initializer_list<std::pair<QString, QJsonValue::Type>> fields)
{
    for (const auto& field : fields) {
        if (object.contains(field.first) && object.value(field.first).type() != field.second) {
            return ContractError{
                QStringLiteral("invalid_type"),
                field.first,
                QStringLiteral("Field has an invalid JSON type."),
            };
        }
    }
    return std::nullopt;
}

std::optional<ContractError> firstArrayWithNonStringElement(
    const QJsonObject& object,
    std::initializer_list<QString> arrayFields)
{
    for (const QString& field : arrayFields) {
        const QJsonArray values = object.value(field).toArray();
        for (const QJsonValue& value : values) {
            if (!value.isString()) {
                return ContractError{
                    QStringLiteral("invalid_type"),
                    field,
                    QStringLiteral("Array elements must be strings."),
                };
            }
        }
    }
    return std::nullopt;
}

std::optional<ContractError> firstNonIntegerNumber(
    const QJsonObject& object,
    std::initializer_list<QString> integerFields)
{
    for (const QString& field : integerFields) {
        if (!object.contains(field)) {
            continue;
        }
        const double value = object.value(field).toDouble();
        if (!std::isfinite(value) || std::floor(value) != value
            || value < std::numeric_limits<int>::min()
            || value > std::numeric_limits<int>::max()) {
            return ContractError{
                QStringLiteral("invalid_value"),
                field,
                QStringLiteral("Field must be an integer."),
            };
        }
    }
    return std::nullopt;
}

}

ValidationResult validateSchemaVersion(const QString& version)
{
    if (version.isEmpty()) {
        return {{
            {
                QStringLiteral("required"),
                QStringLiteral("schema_version"),
                QStringLiteral("Required field is missing."),
            },
        }};
    }

    static const QRegularExpression versionPattern(
        QStringLiteral("^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$"));
    const QRegularExpressionMatch match = versionPattern.match(version);
    bool majorIsInteger = false;
    const int major = match.hasMatch() ? match.captured(1).toInt(&majorIsInteger) : -1;
    if (!match.hasMatch() || !majorIsInteger) {
        return {{
            {
                QStringLiteral("invalid_version"),
                QStringLiteral("schema_version"),
                QStringLiteral("Schema version must use major.minor format."),
            },
        }};
    }

    if (major != 1) {
        return {{
            {
                QStringLiteral("unsupported_schema_version"),
                QStringLiteral("schema_version"),
                QStringLiteral("Unsupported schema major version."),
            },
        }};
    }

    return {};
}

ValidationResult validate(const MemoryQuery& query)
{
    ValidationResult result = validateSchemaVersion(query.schemaVersion);
    if (query.userId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("user_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (query.sessionId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("session_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (query.queryText.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("query_text"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (query.scene.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("scene"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (query.maxContextTokens <= 0) {
        result.errors.append({
            QStringLiteral("out_of_range"),
            QStringLiteral("max_context_tokens"),
            QStringLiteral("Value must be greater than zero."),
        });
    }
    return result;
}

ParseResult<MemoryQuery> memoryQueryFromJson(const QJsonObject& object)
{
    const auto missingField = firstMissingRequiredField(
        object,
        {
            QStringLiteral("schema_version"),
            QStringLiteral("user_id"),
            QStringLiteral("session_id"),
            QStringLiteral("query_text"),
            QStringLiteral("scene"),
            QStringLiteral("max_context_tokens"),
        });
    if (missingField.has_value()) {
        return {std::nullopt, {*missingField}};
    }

    const auto invalidType = firstInvalidJsonType(
        object,
        {
            {QStringLiteral("schema_version"), QJsonValue::String},
            {QStringLiteral("user_id"), QJsonValue::String},
            {QStringLiteral("session_id"), QJsonValue::String},
            {QStringLiteral("query_text"), QJsonValue::String},
            {QStringLiteral("scene"), QJsonValue::String},
            {QStringLiteral("max_context_tokens"), QJsonValue::Double},
        });
    if (invalidType.has_value()) {
        return {std::nullopt, {*invalidType}};
    }
    const auto nonInteger = firstNonIntegerNumber(
        object, {QStringLiteral("max_context_tokens")});
    if (nonInteger.has_value()) {
        return {std::nullopt, {*nonInteger}};
    }

    const ValidationResult versionValidation = validateSchemaVersion(
        object.value(QStringLiteral("schema_version")).toString());
    if (!versionValidation.ok()) {
        return {std::nullopt, versionValidation.errors};
    }

    MemoryQuery query;
    query.schemaVersion = object.value(QStringLiteral("schema_version")).toString();
    query.userId = object.value(QStringLiteral("user_id")).toString();
    query.sessionId = object.value(QStringLiteral("session_id")).toString();
    query.queryText = object.value(QStringLiteral("query_text")).toString();
    query.scene = object.value(QStringLiteral("scene")).toString();
    query.maxContextTokens = object.value(QStringLiteral("max_context_tokens")).toInt();

    const ValidationResult validation = validate(query);
    if (!validation.ok()) {
        return {std::nullopt, validation.errors};
    }

    return {query, {}};
}

QJsonObject toJson(const MemoryQuery& query)
{
    return {
        {QStringLiteral("schema_version"), query.schemaVersion},
        {QStringLiteral("user_id"), query.userId},
        {QStringLiteral("session_id"), query.sessionId},
        {QStringLiteral("query_text"), query.queryText},
        {QStringLiteral("scene"), query.scene},
        {QStringLiteral("max_context_tokens"), query.maxContextTokens},
    };
}

ParseResult<InjectionStatus> injectionStatusFromString(const QString& value)
{
    if (value == QStringLiteral("prepared")) {
        return {InjectionStatus::Prepared, {}};
    }
    if (value == QStringLiteral("injected")) {
        return {InjectionStatus::Injected, {}};
    }
    if (value == QStringLiteral("failed")) {
        return {InjectionStatus::Failed, {}};
    }
    if (value == QStringLiteral("skipped")) {
        return {InjectionStatus::Skipped, {}};
    }

    return {
        std::nullopt,
        {{
            QStringLiteral("invalid_enum"),
            QStringLiteral("injection_status"),
            QStringLiteral("Unknown injection status."),
        }},
    };
}

QString toString(InjectionStatus status)
{
    switch (status) {
    case InjectionStatus::Prepared:
        return QStringLiteral("prepared");
    case InjectionStatus::Injected:
        return QStringLiteral("injected");
    case InjectionStatus::Failed:
        return QStringLiteral("failed");
    case InjectionStatus::Skipped:
        return QStringLiteral("skipped");
    }
    return {};
}

ValidationResult validate(const MemoryContext& context)
{
    ValidationResult result = validateSchemaVersion(context.schemaVersion);
    if (context.queryId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("query_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (context.contextVersion.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("context_version"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (context.tokenBudget <= 0) {
        result.errors.append({
            QStringLiteral("out_of_range"),
            QStringLiteral("token_budget"),
            QStringLiteral("Value must be greater than zero."),
        });
    }
    if (context.actualTokenCount < 0) {
        result.errors.append({
            QStringLiteral("out_of_range"),
            QStringLiteral("actual_token_count"),
            QStringLiteral("Count must not be negative."),
        });
    }
    if (context.sensitiveExcludedCount < 0) {
        result.errors.append({
            QStringLiteral("out_of_range"),
            QStringLiteral("sensitive_excluded_count"),
            QStringLiteral("Count must not be negative."),
        });
    }
    if (context.forgottenExcludedCount < 0) {
        result.errors.append({
            QStringLiteral("out_of_range"),
            QStringLiteral("forgotten_excluded_count"),
            QStringLiteral("Count must not be negative."),
        });
    }
    if (context.conflictExcludedCount < 0) {
        result.errors.append({
            QStringLiteral("out_of_range"),
            QStringLiteral("conflict_excluded_count"),
            QStringLiteral("Count must not be negative."),
        });
    }
    if (context.actualTokenCount > context.tokenBudget) {
        result.errors.append({
            QStringLiteral("inconsistent_value"),
            QStringLiteral("actual_token_count"),
            QStringLiteral("Actual token count exceeds the declared budget."),
        });
    }
    return result;
}

ParseResult<MemoryContext> memoryContextFromJson(const QJsonObject& object)
{
    const auto missingField = firstMissingRequiredField(
        object,
        {
            QStringLiteral("schema_version"),
            QStringLiteral("query_id"),
            QStringLiteral("selected_memory_ids"),
            QStringLiteral("context_version"),
            QStringLiteral("token_budget"),
            QStringLiteral("actual_token_count"),
            QStringLiteral("injection_status"),
        });
    if (missingField.has_value()) {
        return {std::nullopt, {*missingField}};
    }

    const auto invalidType = firstInvalidJsonType(
        object,
        {
            {QStringLiteral("schema_version"), QJsonValue::String},
            {QStringLiteral("query_id"), QJsonValue::String},
            {QStringLiteral("selected_memory_ids"), QJsonValue::Array},
            {QStringLiteral("context_version"), QJsonValue::String},
            {QStringLiteral("token_budget"), QJsonValue::Double},
            {QStringLiteral("actual_token_count"), QJsonValue::Double},
            {QStringLiteral("sensitive_excluded_count"), QJsonValue::Double},
            {QStringLiteral("forgotten_excluded_count"), QJsonValue::Double},
            {QStringLiteral("conflict_excluded_count"), QJsonValue::Double},
            {QStringLiteral("injection_status"), QJsonValue::String},
        });
    if (invalidType.has_value()) {
        return {std::nullopt, {*invalidType}};
    }
    const auto invalidArray = firstArrayWithNonStringElement(
        object, {QStringLiteral("selected_memory_ids")});
    if (invalidArray.has_value()) {
        return {std::nullopt, {*invalidArray}};
    }
    const auto nonInteger = firstNonIntegerNumber(
        object,
        {
            QStringLiteral("token_budget"),
            QStringLiteral("actual_token_count"),
            QStringLiteral("sensitive_excluded_count"),
            QStringLiteral("forgotten_excluded_count"),
            QStringLiteral("conflict_excluded_count"),
        });
    if (nonInteger.has_value()) {
        return {std::nullopt, {*nonInteger}};
    }

    const ValidationResult versionValidation = validateSchemaVersion(
        object.value(QStringLiteral("schema_version")).toString());
    if (!versionValidation.ok()) {
        return {std::nullopt, versionValidation.errors};
    }

    const auto status = injectionStatusFromString(
        object.value(QStringLiteral("injection_status")).toString());
    if (!status.ok()) {
        return {std::nullopt, status.errors};
    }

    QStringList selectedMemoryIds;
    const QJsonArray selectedIds = object.value(QStringLiteral("selected_memory_ids")).toArray();
    selectedMemoryIds.reserve(selectedIds.size());
    for (const QJsonValue& selectedId : selectedIds) {
        selectedMemoryIds.append(selectedId.toString());
    }

    MemoryContext context;
    context.schemaVersion = object.value(QStringLiteral("schema_version")).toString();
    context.queryId = object.value(QStringLiteral("query_id")).toString();
    context.selectedMemoryIds = selectedMemoryIds;
    context.contextVersion = object.value(QStringLiteral("context_version")).toString();
    context.tokenBudget = object.value(QStringLiteral("token_budget")).toInt();
    context.actualTokenCount = object.value(QStringLiteral("actual_token_count")).toInt();
    context.sensitiveExcludedCount = object.value(QStringLiteral("sensitive_excluded_count")).toInt();
    context.forgottenExcludedCount = object.value(QStringLiteral("forgotten_excluded_count")).toInt();
    context.conflictExcludedCount = object.value(QStringLiteral("conflict_excluded_count")).toInt();
    context.injectionStatus = *status.value;

    const ValidationResult validation = validate(context);
    if (!validation.ok()) {
        return {std::nullopt, validation.errors};
    }

    return {context, {}};
}

QJsonObject toJson(const MemoryContext& context)
{
    QJsonArray selectedMemoryIds;
    for (const QString& selectedId : context.selectedMemoryIds) {
        selectedMemoryIds.append(selectedId);
    }

    return {
        {QStringLiteral("schema_version"), context.schemaVersion},
        {QStringLiteral("query_id"), context.queryId},
        {QStringLiteral("selected_memory_ids"), selectedMemoryIds},
        {QStringLiteral("context_version"), context.contextVersion},
        {QStringLiteral("token_budget"), context.tokenBudget},
        {QStringLiteral("actual_token_count"), context.actualTokenCount},
        {QStringLiteral("sensitive_excluded_count"), context.sensitiveExcludedCount},
        {QStringLiteral("forgotten_excluded_count"), context.forgottenExcludedCount},
        {QStringLiteral("conflict_excluded_count"), context.conflictExcludedCount},
        {QStringLiteral("injection_status"), toString(context.injectionStatus)},
    };
}

ParseResult<ToolExecutionStatus> toolExecutionStatusFromString(const QString& value)
{
    if (value == QStringLiteral("success")) {
        return {ToolExecutionStatus::Success, {}};
    }
    if (value == QStringLiteral("partial")) {
        return {ToolExecutionStatus::Partial, {}};
    }
    if (value == QStringLiteral("failure")) {
        return {ToolExecutionStatus::Failure, {}};
    }
    if (value == QStringLiteral("cancelled")) {
        return {ToolExecutionStatus::Cancelled, {}};
    }
    if (value == QStringLiteral("timeout")) {
        return {ToolExecutionStatus::Timeout, {}};
    }

    return {
        std::nullopt,
        {{
            QStringLiteral("invalid_enum"),
            QStringLiteral("execution_status"),
            QStringLiteral("Unknown tool execution status."),
        }},
    };
}

QString toString(ToolExecutionStatus status)
{
    switch (status) {
    case ToolExecutionStatus::Success:
        return QStringLiteral("success");
    case ToolExecutionStatus::Partial:
        return QStringLiteral("partial");
    case ToolExecutionStatus::Failure:
        return QStringLiteral("failure");
    case ToolExecutionStatus::Cancelled:
        return QStringLiteral("cancelled");
    case ToolExecutionStatus::Timeout:
        return QStringLiteral("timeout");
    }
    return {};
}

ValidationResult validate(const ToolExecutionEvent& event)
{
    ValidationResult result = validateSchemaVersion(event.schemaVersion);
    if (event.toolCallId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("tool_call_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (event.toolName.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("tool_name"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (!event.startedAt.isValid()) {
        result.errors.append({
            QStringLiteral("invalid_timestamp"),
            QStringLiteral("started_at"),
            QStringLiteral("Timestamp must be valid ISO 8601."),
        });
    }
    if (!event.finishedAt.isValid()) {
        result.errors.append({
            QStringLiteral("invalid_timestamp"),
            QStringLiteral("finished_at"),
            QStringLiteral("Timestamp must be valid ISO 8601."),
        });
    }
    if (event.startedAt.isValid() && event.finishedAt.isValid()
        && event.finishedAt < event.startedAt) {
        result.errors.append({
            QStringLiteral("inconsistent_value"),
            QStringLiteral("finished_at"),
            QStringLiteral("Tool finish time precedes its start time."),
        });
    }
    if (event.executionStatus == ToolExecutionStatus::Success && event.resultRef.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("result_ref"),
            QStringLiteral("Successful tool execution requires a result reference."),
        });
    }
    return result;
}

ParseResult<ToolExecutionEvent> toolExecutionEventFromJson(const QJsonObject& object)
{
    const auto missingField = firstMissingRequiredField(
        object,
        {
            QStringLiteral("schema_version"),
            QStringLiteral("tool_call_id"),
            QStringLiteral("tool_name"),
            QStringLiteral("started_at"),
            QStringLiteral("finished_at"),
            QStringLiteral("execution_status"),
            QStringLiteral("side_effect"),
        });
    if (missingField.has_value()) {
        return {std::nullopt, {*missingField}};
    }

    const auto invalidType = firstInvalidJsonType(
        object,
        {
            {QStringLiteral("schema_version"), QJsonValue::String},
            {QStringLiteral("tool_call_id"), QJsonValue::String},
            {QStringLiteral("tool_name"), QJsonValue::String},
            {QStringLiteral("arguments_ref"), QJsonValue::String},
            {QStringLiteral("started_at"), QJsonValue::String},
            {QStringLiteral("finished_at"), QJsonValue::String},
            {QStringLiteral("execution_status"), QJsonValue::String},
            {QStringLiteral("result_ref"), QJsonValue::String},
            {QStringLiteral("error_type"), QJsonValue::String},
            {QStringLiteral("error_message_safe"), QJsonValue::String},
            {QStringLiteral("side_effect"), QJsonValue::Bool},
            {QStringLiteral("user_confirmed"), QJsonValue::Bool},
            {QStringLiteral("rollback_required"), QJsonValue::Bool},
            {QStringLiteral("rollback_status"), QJsonValue::String},
            {QStringLiteral("source_trace_id"), QJsonValue::String},
        });
    if (invalidType.has_value()) {
        return {std::nullopt, {*invalidType}};
    }
    const ValidationResult versionValidation = validateSchemaVersion(
        object.value(QStringLiteral("schema_version")).toString());
    if (!versionValidation.ok()) {
        return {std::nullopt, versionValidation.errors};
    }

    const auto status = toolExecutionStatusFromString(
        object.value(QStringLiteral("execution_status")).toString());
    if (!status.ok()) {
        return {std::nullopt, status.errors};
    }

    ToolExecutionEvent event;
    event.schemaVersion = object.value(QStringLiteral("schema_version")).toString();
    event.toolCallId = object.value(QStringLiteral("tool_call_id")).toString();
    event.toolName = object.value(QStringLiteral("tool_name")).toString();
    event.argumentsRef = object.value(QStringLiteral("arguments_ref")).toString();
    event.startedAt = QDateTime::fromString(
        object.value(QStringLiteral("started_at")).toString(), Qt::ISODateWithMs);
    event.finishedAt = QDateTime::fromString(
        object.value(QStringLiteral("finished_at")).toString(), Qt::ISODateWithMs);
    event.executionStatus = *status.value;
    event.resultRef = object.value(QStringLiteral("result_ref")).toString();
    event.errorType = object.value(QStringLiteral("error_type")).toString();
    event.errorMessageSafe = object.value(QStringLiteral("error_message_safe")).toString();
    event.sideEffect = object.value(QStringLiteral("side_effect")).toBool();
    event.userConfirmed = object.value(QStringLiteral("user_confirmed")).toBool();
    event.rollbackRequired = object.value(QStringLiteral("rollback_required")).toBool();
    event.rollbackStatus = object.value(QStringLiteral("rollback_status")).toString();
    event.sourceTraceId = object.value(QStringLiteral("source_trace_id")).toString();

    const ValidationResult validation = validate(event);
    if (!validation.ok()) {
        return {std::nullopt, validation.errors};
    }

    return {event, {}};
}

QJsonObject toJson(const ToolExecutionEvent& event)
{
    QJsonObject object{
        {QStringLiteral("schema_version"), event.schemaVersion},
        {QStringLiteral("tool_call_id"), event.toolCallId},
        {QStringLiteral("tool_name"), event.toolName},
        {QStringLiteral("arguments_ref"), event.argumentsRef},
        {QStringLiteral("started_at"), event.startedAt.toUTC().toString(Qt::ISODateWithMs)},
        {QStringLiteral("finished_at"), event.finishedAt.toUTC().toString(Qt::ISODateWithMs)},
        {QStringLiteral("execution_status"), toString(event.executionStatus)},
        {QStringLiteral("result_ref"), event.resultRef},
        {QStringLiteral("side_effect"), event.sideEffect},
        {QStringLiteral("user_confirmed"), event.userConfirmed},
        {QStringLiteral("rollback_required"), event.rollbackRequired},
        {QStringLiteral("rollback_status"), event.rollbackStatus},
        {QStringLiteral("source_trace_id"), event.sourceTraceId},
    };

    if (!event.errorType.isEmpty()) {
        object.insert(QStringLiteral("error_type"), event.errorType);
    }
    if (!event.errorMessageSafe.isEmpty()) {
        object.insert(QStringLiteral("error_message_safe"), event.errorMessageSafe);
    }

    return object;
}

ValidationResult validate(const TurnFinalizedEvent& event)
{
    ValidationResult result = validateSchemaVersion(event.schemaVersion);
    if (event.eventId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("event_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (event.userId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("user_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (event.sessionId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("session_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (event.turnId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("turn_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (event.idempotencyKey.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("idempotency_key"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (!event.finalizedAt.isValid()) {
        result.errors.append({
            QStringLiteral("invalid_timestamp"),
            QStringLiteral("finalized_at"),
            QStringLiteral("Timestamp must be valid ISO 8601."),
        });
    }
    if (!event.retryOfTurnId.isEmpty() && event.retryOfTurnId == event.turnId) {
        result.errors.append({
            QStringLiteral("inconsistent_value"),
            QStringLiteral("retry_of_turn_id"),
            QStringLiteral("A finalized turn cannot retry itself."),
        });
    }

    QSet<QString> uniqueToolCallIds;
    for (const QString& toolCallId : event.toolCallIds) {
        if (uniqueToolCallIds.contains(toolCallId)) {
            result.errors.append({
                QStringLiteral("duplicate_value"),
                QStringLiteral("tool_call_ids"),
                QStringLiteral("Tool call identifiers must be unique within a turn."),
            });
            break;
        }
        uniqueToolCallIds.insert(toolCallId);
    }
    return result;
}

ParseResult<TurnFinalizedEvent> turnFinalizedEventFromJson(const QJsonObject& object)
{
    const auto missingField = firstMissingRequiredField(
        object,
        {
            QStringLiteral("schema_version"),
            QStringLiteral("event_id"),
            QStringLiteral("user_id"),
            QStringLiteral("session_id"),
            QStringLiteral("turn_id"),
            QStringLiteral("idempotency_key"),
            QStringLiteral("is_final"),
            QStringLiteral("finalized_at"),
        });
    if (missingField.has_value()) {
        return {std::nullopt, {*missingField}};
    }

    const auto invalidType = firstInvalidJsonType(
        object,
        {
            {QStringLiteral("schema_version"), QJsonValue::String},
            {QStringLiteral("event_id"), QJsonValue::String},
            {QStringLiteral("user_id"), QJsonValue::String},
            {QStringLiteral("session_id"), QJsonValue::String},
            {QStringLiteral("turn_id"), QJsonValue::String},
            {QStringLiteral("source_reference"), QJsonValue::String},
            {QStringLiteral("idempotency_key"), QJsonValue::String},
            {QStringLiteral("final_message_id"), QJsonValue::String},
            {QStringLiteral("is_final"), QJsonValue::Bool},
            {QStringLiteral("finalization_reason"), QJsonValue::String},
            {QStringLiteral("stop_reason"), QJsonValue::String},
            {QStringLiteral("retry_of_turn_id"), QJsonValue::String},
            {QStringLiteral("tool_call_ids"), QJsonValue::Array},
            {QStringLiteral("finalized_at"), QJsonValue::String},
        });
    if (invalidType.has_value()) {
        return {std::nullopt, {*invalidType}};
    }
    const auto invalidArray = firstArrayWithNonStringElement(
        object, {QStringLiteral("tool_call_ids")});
    if (invalidArray.has_value()) {
        return {std::nullopt, {*invalidArray}};
    }

    const ValidationResult versionValidation = validateSchemaVersion(
        object.value(QStringLiteral("schema_version")).toString());
    if (!versionValidation.ok()) {
        return {std::nullopt, versionValidation.errors};
    }

    QStringList toolCallIds;
    const QJsonArray toolIds = object.value(QStringLiteral("tool_call_ids")).toArray();
    toolCallIds.reserve(toolIds.size());
    for (const QJsonValue& toolId : toolIds) {
        toolCallIds.append(toolId.toString());
    }

    TurnFinalizedEvent event;
    event.schemaVersion = object.value(QStringLiteral("schema_version")).toString();
    event.eventId = object.value(QStringLiteral("event_id")).toString();
    event.userId = object.value(QStringLiteral("user_id")).toString();
    event.sessionId = object.value(QStringLiteral("session_id")).toString();
    event.turnId = object.value(QStringLiteral("turn_id")).toString();
    event.sourceReference = object.value(QStringLiteral("source_reference")).toString();
    event.idempotencyKey = object.value(QStringLiteral("idempotency_key")).toString();
    event.finalMessageId = object.value(QStringLiteral("final_message_id")).toString();
    event.isFinal = object.value(QStringLiteral("is_final")).toBool();
    event.finalizationReason = object.value(QStringLiteral("finalization_reason")).toString();
    event.stopReason = object.value(QStringLiteral("stop_reason")).toString();
    event.retryOfTurnId = object.value(QStringLiteral("retry_of_turn_id")).toString();
    event.toolCallIds = toolCallIds;
    event.finalizedAt = QDateTime::fromString(
        object.value(QStringLiteral("finalized_at")).toString(), Qt::ISODateWithMs);

    const ValidationResult validation = validate(event);
    if (!validation.ok()) {
        return {std::nullopt, validation.errors};
    }

    return {event, {}};
}

QJsonObject toJson(const TurnFinalizedEvent& event)
{
    QJsonArray toolCallIds;
    for (const QString& toolCallId : event.toolCallIds) {
        toolCallIds.append(toolCallId);
    }

    QJsonObject object{
        {QStringLiteral("schema_version"), event.schemaVersion},
        {QStringLiteral("event_id"), event.eventId},
        {QStringLiteral("user_id"), event.userId},
        {QStringLiteral("session_id"), event.sessionId},
        {QStringLiteral("turn_id"), event.turnId},
        {QStringLiteral("idempotency_key"), event.idempotencyKey},
        {QStringLiteral("is_final"), event.isFinal},
        {QStringLiteral("tool_call_ids"), toolCallIds},
        {QStringLiteral("finalized_at"), event.finalizedAt.toUTC().toString(Qt::ISODateWithMs)},
    };

    if (!event.sourceReference.isEmpty()) {
        object.insert(QStringLiteral("source_reference"), event.sourceReference);
    }
    if (!event.finalMessageId.isEmpty()) {
        object.insert(QStringLiteral("final_message_id"), event.finalMessageId);
    }
    if (!event.finalizationReason.isEmpty()) {
        object.insert(QStringLiteral("finalization_reason"), event.finalizationReason);
    }
    if (!event.stopReason.isEmpty()) {
        object.insert(QStringLiteral("stop_reason"), event.stopReason);
    }
    if (!event.retryOfTurnId.isEmpty()) {
        object.insert(QStringLiteral("retry_of_turn_id"), event.retryOfTurnId);
    }

    return object;
}

}
