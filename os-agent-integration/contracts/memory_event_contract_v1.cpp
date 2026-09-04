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

// Reads a KMA R-1 time alias: accepts both the canonical `captured_at` name and the
// legacy transport alias `collected_at` (TD-060). If both are present the canonical
// name wins (fail-closed: we don't silently merge two different timestamps). Returns
// the parsed timestamp, or an invalid QDateTime if neither key is present / parseable.
std::pair<QDateTime, QString /*effective_key*/> readCanonicalCapturedAt(
    const QJsonObject& object)
{
    const QString canonicalKey = QStringLiteral("captured_at");
    const QString legacyKey = QStringLiteral("collected_at");
    if (object.contains(canonicalKey)) {
        const QString raw = object.value(canonicalKey).toString();
        return {QDateTime::fromString(raw, Qt::ISODateWithMs), canonicalKey};
    }
    if (object.contains(legacyKey)) {
        const QString raw = object.value(legacyKey).toString();
        return {QDateTime::fromString(raw, Qt::ISODateWithMs), legacyKey};
    }
    return {{}, canonicalKey};
}

// Returns true if any of the provided keys is a JSON string member of `object`.
bool containsAnyOf(
    const QJsonObject& object, std::initializer_list<QString> keys)
{
    for (const QString& k : keys) {
        if (object.contains(k)) {
            return true;
        }
    }
    return false;
}

std::optional<ContractError> firstMissingRequiredField(
    const QJsonObject& object,
    std::initializer_list<QString> requiredFields)
{
    for (const QString& field : requiredFields) {
        // KMA R-1 alias: `captured_at` / `collected_at` either satisfies the
        // required field; the error reports the canonical name.
        if (field == QStringLiteral("captured_at")) {
            if (!containsAnyOf(object,
                    {QStringLiteral("captured_at"), QStringLiteral("collected_at")})) {
                return ContractError{
                    QStringLiteral("required"),
                    field,
                    QStringLiteral("Required field is missing."),
                };
            }
            continue;
        }
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

std::optional<ContractError> firstMissingRequiredEventMetadataField(
    const QJsonObject& object)
{
    return firstMissingRequiredField(
        object,
        {
            QStringLiteral("schema_version"),
            QStringLiteral("event_id"),
            QStringLiteral("user_id"),
            QStringLiteral("session_id"),
            QStringLiteral("occurred_at"),
            // KMA R-1 (TD-060): `captured_at` is the canonical name; legacy
            // transport alias `collected_at` is still accepted.
            QStringLiteral("captured_at"),
            QStringLiteral("idempotency_key"),
        });
}

std::optional<ContractError> firstInvalidEventMetadataJsonType(const QJsonObject& object)
{
    // KMA R-1 (TD-060, review MEDIUM-01): the event-metadata time key has a
    // transport alias pair — Canonical `captured_at` and legacy
    // `collected_at`. The semantic rule is "Canonical wins on INPUT", meaning:
    //   - If the payload carries BOTH keys, we only validate the Canonical
    //     one. A malformed legacy alias must NOT cause a rejection when the
    //     Canonical key is already well-formed. This matches the behaviour of
    //     `readCanonicalCapturedAt()` which ignores the legacy key in the
    //     "both present" path.
    //   - If ONLY the legacy key is present, we validate its type and surface
    //     the error under the **Canonical** field name so callers do not start
    //     depending on the legacy transport name in error surfaces.
    //   - If NEITHER is present, we skip the type check — the
    //     "firstMissingRequiredEventMetadataField" check handles the
    //     required-field gate separately.
    const bool hasCanonical = object.contains(QStringLiteral("captured_at"));
    const bool hasLegacy = object.contains(QStringLiteral("collected_at"));
    if (hasCanonical) {
        if (object.value(QStringLiteral("captured_at")).type() != QJsonValue::String) {
            return ContractError{
                QStringLiteral("invalid_type"),
                QStringLiteral("captured_at"),
                QStringLiteral("Field has an invalid JSON type."),
            };
        }
    } else if (hasLegacy) {
        // Legacy-only ingress — type-check it but report the Canonical name
        // (keeps the adapter-window "inputs are normalised to canonical names"
        // contract that downstream error handlers already depend on).
        if (object.value(QStringLiteral("collected_at")).type() != QJsonValue::String) {
            return ContractError{
                QStringLiteral("invalid_type"),
                QStringLiteral("captured_at"),
                QStringLiteral("Field has an invalid JSON type."),
            };
        }
    }
    // All other metadata fields — single canonical key, no aliases.
    return firstInvalidJsonType(
        object,
        {
            {QStringLiteral("schema_version"), QJsonValue::String},
            {QStringLiteral("event_id"), QJsonValue::String},
            {QStringLiteral("trace_id"), QJsonValue::String},
            {QStringLiteral("user_id"), QJsonValue::String},
            {QStringLiteral("session_id"), QJsonValue::String},
            {QStringLiteral("turn_id"), QJsonValue::String},
            {QStringLiteral("occurred_at"), QJsonValue::String},
            // `captured_at` / `collected_at` — handled above (aliased pair).
            {QStringLiteral("source_reference"), QJsonValue::String},
            {QStringLiteral("idempotency_key"), QJsonValue::String},
        });
}

EventMetadata eventMetadataFromJson(const QJsonObject& object)
{
    EventMetadata metadata;
    metadata.schemaVersion = object.value(QStringLiteral("schema_version")).toString();
    metadata.eventId = object.value(QStringLiteral("event_id")).toString();
    metadata.traceId = object.value(QStringLiteral("trace_id")).toString();
    metadata.userId = object.value(QStringLiteral("user_id")).toString();
    metadata.sessionId = object.value(QStringLiteral("session_id")).toString();
    metadata.turnId = object.value(QStringLiteral("turn_id")).toString();
    metadata.occurredAt = QDateTime::fromString(
        object.value(QStringLiteral("occurred_at")).toString(), Qt::ISODateWithMs);
    // KMA R-1: prefer canonical `captured_at`, fall back to legacy alias
    // `collected_at` (TD-060).
    const auto [captured, effectiveKey] = readCanonicalCapturedAt(object);
    metadata.collectedAt = captured;
    // (void) to mark "used" for the uncommon case that compilers warn on C++17
    // structured bindings with the same variable scope.
    Q_UNUSED(effectiveKey);
    metadata.sourceReference = object.value(QStringLiteral("source_reference")).toString();
    metadata.idempotencyKey = object.value(QStringLiteral("idempotency_key")).toString();
    return metadata;
}

QJsonObject eventMetadataToJson(const EventMetadata& metadata)
{
    QJsonObject object{
        {QStringLiteral("schema_version"), metadata.schemaVersion},
        {QStringLiteral("event_id"), metadata.eventId},
        {QStringLiteral("user_id"), metadata.userId},
        {QStringLiteral("session_id"), metadata.sessionId},
        {QStringLiteral("occurred_at"), metadata.occurredAt.toUTC().toString(Qt::ISODateWithMs)},
        // KMA R-1: always output canonical `captured_at`. Hosts still writing the
        // legacy `collected_at` transport alias can still parse via alias support
        // in `eventMetadataFromJson` (TD-060 adapter window).
        {QStringLiteral("captured_at"), metadata.collectedAt.toUTC().toString(Qt::ISODateWithMs)},
        {QStringLiteral("idempotency_key"), metadata.idempotencyKey},
    };

    if (!metadata.traceId.isEmpty()) {
        object.insert(QStringLiteral("trace_id"), metadata.traceId);
    }
    if (!metadata.turnId.isEmpty()) {
        object.insert(QStringLiteral("turn_id"), metadata.turnId);
    }
    if (!metadata.sourceReference.isEmpty()) {
        object.insert(QStringLiteral("source_reference"), metadata.sourceReference);
    }
    return object;
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

namespace {

ValidationResult validateEventMetadata(const EventMetadata& metadata)
{
    ValidationResult result = validateSchemaVersion(metadata.schemaVersion);
    if (metadata.eventId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("event_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (metadata.userId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("user_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (metadata.sessionId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("session_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (!metadata.occurredAt.isValid()) {
        result.errors.append({
            QStringLiteral("invalid_timestamp"),
            QStringLiteral("occurred_at"),
            QStringLiteral("Timestamp must be valid ISO 8601."),
        });
    }
    if (!metadata.collectedAt.isValid()) {
        // KMA R-1: report the canonical field name; legacy alias is accepted only
        // as a transport input.
        result.errors.append({
            QStringLiteral("invalid_timestamp"),
            QStringLiteral("captured_at"),
            QStringLiteral("Timestamp must be valid ISO 8601."),
        });
    }
    if (metadata.idempotencyKey.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("idempotency_key"),
            QStringLiteral("Required field is missing."),
        });
    }
    return result;
}

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
    const auto maxTokensValue = object.value(QStringLiteral("max_context_tokens"));
    if (!maxTokensValue.isDouble()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("max_context_tokens"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    const double maxTokensDouble = maxTokensValue.toDouble();
    if (maxTokensDouble != static_cast<double>(static_cast<qlonglong>(maxTokensDouble))) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_value"),
                QStringLiteral("max_context_tokens"),
                QStringLiteral("Field must be an integer."),
            }},
        };
    }
    query.maxContextTokens = static_cast<int>(maxTokensDouble);

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
    ValidationResult result = validateEventMetadata(context.metadata);
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
    if (!context.injectionStatus.has_value()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("injection_status"),
            QStringLiteral("Required field is missing."),
        });
    }
    for (const QString& memoryId : context.selectedMemoryIds) {
        if (memoryId.isEmpty()) {
            result.errors.append({
                QStringLiteral("invalid_value"),
                QStringLiteral("selected_memory_ids"),
                QStringLiteral("Memory identifiers must not be empty."),
            });
            break;
        }
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
    const auto missingMetadataField = firstMissingRequiredEventMetadataField(object);
    if (missingMetadataField.has_value()) {
        return {std::nullopt, {*missingMetadataField}};
    }

    const auto missingField = firstMissingRequiredField(
        object,
        {
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

    const auto invalidMetadataType = firstInvalidEventMetadataJsonType(object);
    if (invalidMetadataType.has_value()) {
        return {std::nullopt, {*invalidMetadataType}};
    }

    const auto invalidType = firstInvalidJsonType(
        object,
        {
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

    const auto selectedIdsValue = object.value(QStringLiteral("selected_memory_ids"));
    if (!selectedIdsValue.isArray()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("selected_memory_ids"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    const QJsonArray selectedIds = selectedIdsValue.toArray();
    QStringList selectedMemoryIds;
    selectedMemoryIds.reserve(selectedIds.size());
    for (const QJsonValue& selectedId : selectedIds) {
        if (!selectedId.isString()) {
            return {
                std::nullopt,
                {{
                    QStringLiteral("invalid_type"),
                    QStringLiteral("selected_memory_ids"),
                    QStringLiteral("Array elements must be strings."),
                }},
            };
        }
        selectedMemoryIds.append(selectedId.toString());
    }

    MemoryContext context;
    context.metadata = eventMetadataFromJson(object);
    context.queryId = object.value(QStringLiteral("query_id")).toString();
    context.selectedMemoryIds = selectedMemoryIds;
    context.contextVersion = object.value(QStringLiteral("context_version")).toString();

    const auto tokenBudgetValue = object.value(QStringLiteral("token_budget"));
    if (!tokenBudgetValue.isDouble()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("token_budget"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    context.tokenBudget = tokenBudgetValue.toInt();

    const auto actualCountValue = object.value(QStringLiteral("actual_token_count"));
    if (!actualCountValue.isDouble()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("actual_token_count"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    context.actualTokenCount = actualCountValue.toInt();

    const auto sensValue = object.value(QStringLiteral("sensitive_excluded_count"));
    if (!sensValue.isDouble()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("sensitive_excluded_count"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    context.sensitiveExcludedCount = sensValue.toInt();

    const auto forgotValue = object.value(QStringLiteral("forgotten_excluded_count"));
    if (!forgotValue.isDouble()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("forgotten_excluded_count"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    context.forgottenExcludedCount = forgotValue.toInt();

    const auto conflictValue = object.value(QStringLiteral("conflict_excluded_count"));
    if (!conflictValue.isDouble()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("conflict_excluded_count"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    context.conflictExcludedCount = conflictValue.toInt();
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

    QJsonObject object = eventMetadataToJson(context.metadata);
    object.insert(QStringLiteral("query_id"), context.queryId);
    object.insert(QStringLiteral("selected_memory_ids"), selectedMemoryIds);
    object.insert(QStringLiteral("context_version"), context.contextVersion);
    object.insert(QStringLiteral("token_budget"), context.tokenBudget);
    object.insert(QStringLiteral("actual_token_count"), context.actualTokenCount);
    object.insert(QStringLiteral("sensitive_excluded_count"), context.sensitiveExcludedCount);
    object.insert(QStringLiteral("forgotten_excluded_count"), context.forgottenExcludedCount);
    object.insert(QStringLiteral("conflict_excluded_count"), context.conflictExcludedCount);
    object.insert(
        QStringLiteral("injection_status"),
        context.injectionStatus.has_value() ? toString(*context.injectionStatus) : QString{});
    return object;
}

ParseResult<ToolExecutionStatus> toolExecutionStatusFromString(const QString& value)
{
    if (value == QStringLiteral("success")) {
        return {ToolExecutionStatus::Success, {}};
    }
    if (value == QStringLiteral("partial")) {
        return {ToolExecutionStatus::Partial, {}};
    }
    // KMA R-1 / DRIFT-003: Canonical event business result uses `failed`;
    // Host DTO `execution_status` alias `failure` is still accepted.
    if (value == QStringLiteral("failure") || value == QStringLiteral("failed")) {
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
    Q_UNREACHABLE();
    return {};
}

ParseResult<BusinessStatus> businessStatusFromString(const QString& value)
{
    // KMA R-6 canonical 8-value white-list. Canonical names ONLY.
    if (value == QStringLiteral("success"))   return {BusinessStatus::Success, {}};
    if (value == QStringLiteral("partial"))   return {BusinessStatus::Partial, {}};
    if (value == QStringLiteral("failed"))    return {BusinessStatus::Failed, {}};     // canonical; legacy "failure" NOT accepted
    if (value == QStringLiteral("cancelled")) return {BusinessStatus::Cancelled, {}};
    if (value == QStringLiteral("timeout"))   return {BusinessStatus::Timeout, {}};
    if (value == QStringLiteral("queued"))    return {BusinessStatus::Queued, {}};
    if (value == QStringLiteral("running"))   return {BusinessStatus::Running, {}};
    if (value == QStringLiteral("skipped"))   return {BusinessStatus::Skipped, {}};

    return {
        std::nullopt,
        {{
            QStringLiteral("invalid_enum"),
            QStringLiteral("source_business_status"),
            QStringLiteral("Unknown canonical business status (must be one of 8 KMA R-6 values)."),
        }},
    };
}

QString toString(BusinessStatus status)
{
    switch (status) {
    case BusinessStatus::Success:   return QStringLiteral("success");
    case BusinessStatus::Partial:   return QStringLiteral("partial");
    case BusinessStatus::Failed:    return QStringLiteral("failed");
    case BusinessStatus::Cancelled: return QStringLiteral("cancelled");
    case BusinessStatus::Timeout:   return QStringLiteral("timeout");
    case BusinessStatus::Queued:    return QStringLiteral("queued");
    case BusinessStatus::Running:   return QStringLiteral("running");
    case BusinessStatus::Skipped:   return QStringLiteral("skipped");
    }
    Q_UNREACHABLE();
    return {};
}

// KMA R-6 / DRIFT-002: consistency check between Host DTO status and canonical business status.
// Host DTO uses "failure" as alias but canonical business status MUST report "failed".
// Returns true when (executionStatus, businessStatus) is an allowed tuple.
static bool businessStatusConsistentWithExecution(
    ToolExecutionStatus executionStatus, BusinessStatus businessStatus)
{
    switch (businessStatus) {
    case BusinessStatus::Success:   return executionStatus == ToolExecutionStatus::Success;
    case BusinessStatus::Partial:   return executionStatus == ToolExecutionStatus::Partial;
    case BusinessStatus::Failed:    return executionStatus == ToolExecutionStatus::Failure; // "failure"/"failed" → Failure
    case BusinessStatus::Cancelled: return executionStatus == ToolExecutionStatus::Cancelled;
    case BusinessStatus::Timeout:   return executionStatus == ToolExecutionStatus::Timeout;
    case BusinessStatus::Queued:    // no direct Host DTO mapping — allowed (non-terminal states)
        [[fallthrough]];
    case BusinessStatus::Running:
        [[fallthrough]];
    case BusinessStatus::Skipped:
        return true;
    }
    Q_UNREACHABLE();
    return false;
}

ValidationResult validate(const ToolExecutionEvent& event)
{
    ValidationResult result = validateEventMetadata(event.metadata);
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
    if (!event.executionStatus.has_value()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("execution_status"),
            QStringLiteral("Required field is missing."),
        });
    }
    // KMA R-6 / DRIFT-002: canonical business status is REQUIRED
    if (!event.sourceBusinessStatus.has_value()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("source_business_status"),
            QStringLiteral("Required KMA R-6 canonical business status is missing."),
        });
    }
    if (!event.sideEffect.has_value()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("side_effect"),
            QStringLiteral("Required field is missing."),
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
    // KMA R-6 / DRIFT-002: Host DTO execution_status ↔ canonical business status consistency.
    // Catches contradictions like execution_status="failure" but source_business_status="success".
    if (event.executionStatus.has_value() && event.sourceBusinessStatus.has_value()) {
        if (!businessStatusConsistentWithExecution(*event.executionStatus, *event.sourceBusinessStatus)) {
            result.errors.append({
                QStringLiteral("inconsistent_value"),
                QStringLiteral("source_business_status"),
                QStringLiteral("source_business_status contradicts execution_status (e.g. Host failure → canonical failed)."),
            });
        }
    }
    return result;
}

ParseResult<ToolExecutionEvent> toolExecutionEventFromJson(const QJsonObject& object)
{
    const auto missingMetadataField = firstMissingRequiredEventMetadataField(object);
    if (missingMetadataField.has_value()) {
        return {std::nullopt, {*missingMetadataField}};
    }

    const auto missingField = firstMissingRequiredField(
        object,
        {
            QStringLiteral("tool_call_id"),
            QStringLiteral("tool_name"),
            QStringLiteral("started_at"),
            QStringLiteral("finished_at"),
            QStringLiteral("execution_status"),
            QStringLiteral("source_business_status"),
            QStringLiteral("side_effect"),
        });
    if (missingField.has_value()) {
        return {std::nullopt, {*missingField}};
    }

    const auto invalidMetadataType = firstInvalidEventMetadataJsonType(object);
    if (invalidMetadataType.has_value()) {
        return {std::nullopt, {*invalidMetadataType}};
    }

    const auto invalidType = firstInvalidJsonType(
        object,
        {
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
            {QStringLiteral("rollback_required"), QJsonValue::Bool},
            {QStringLiteral("rollback_status"), QJsonValue::String},
            {QStringLiteral("source_business_status"), QJsonValue::String},
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

    // KMA R-6: source_business_status MUST be a canonical 8-value enum.
    // Unknown values (e.g. legacy "succeeded"/"failure") are REJECTED outright.
    const auto biz = businessStatusFromString(
        object.value(QStringLiteral("source_business_status")).toString());
    if (!biz.ok()) {
        return {std::nullopt, biz.errors};
    }

    ToolExecutionEvent event;
    event.metadata = eventMetadataFromJson(object);
    event.toolCallId = object.value(QStringLiteral("tool_call_id")).toString();
    event.toolName = object.value(QStringLiteral("tool_name")).toString();
    event.argumentsRef = object.value(QStringLiteral("arguments_ref")).toString();
    event.startedAt = QDateTime::fromString(
        object.value(QStringLiteral("started_at")).toString(), Qt::ISODateWithMs);
    event.finishedAt = QDateTime::fromString(
        object.value(QStringLiteral("finished_at")).toString(), Qt::ISODateWithMs);
    event.executionStatus = *status.value;
    event.sourceBusinessStatus = *biz.value;
    event.resultRef = object.value(QStringLiteral("result_ref")).toString();
    event.errorType = object.value(QStringLiteral("error_type")).toString();
    event.errorMessageSafe = object.value(QStringLiteral("error_message_safe")).toString();

    const auto sideEffectValue = object.value(QStringLiteral("side_effect"));
    if (!sideEffectValue.isBool()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("side_effect"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    event.sideEffect = sideEffectValue.toBool();

    const auto rollbackRequiredValue = object.value(QStringLiteral("rollback_required"));
    // rollback_required is optional; when present it must be a boolean.
    if (!rollbackRequiredValue.isUndefined() && !rollbackRequiredValue.isNull()
        && !rollbackRequiredValue.isBool()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("rollback_required"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    event.rollbackRequired = rollbackRequiredValue.toBool();
    event.rollbackStatus = object.value(QStringLiteral("rollback_status")).toString();

    const ValidationResult validation = validate(event);
    if (!validation.ok()) {
        return {std::nullopt, validation.errors};
    }

    return {event, {}};
}

QJsonObject toJson(const ToolExecutionEvent& event)
{
    QJsonObject object = eventMetadataToJson(event.metadata);
    object.insert(QStringLiteral("tool_call_id"), event.toolCallId);
    object.insert(QStringLiteral("tool_name"), event.toolName);
    object.insert(
        QStringLiteral("started_at"), event.startedAt.toUTC().toString(Qt::ISODateWithMs));
    object.insert(
        QStringLiteral("finished_at"), event.finishedAt.toUTC().toString(Qt::ISODateWithMs));
    object.insert(
        QStringLiteral("execution_status"),
        event.executionStatus.has_value() ? toString(*event.executionStatus) : QString{});
    object.insert(QStringLiteral("side_effect"), event.sideEffect.value_or(false));
    object.insert(QStringLiteral("rollback_required"), event.rollbackRequired);

    if (!event.argumentsRef.isEmpty()) {
        object.insert(QStringLiteral("arguments_ref"), event.argumentsRef);
    }
    if (event.executionStatus == ToolExecutionStatus::Success && !event.resultRef.isEmpty()) {
        object.insert(QStringLiteral("result_ref"), event.resultRef);
    }
    if (!event.rollbackStatus.isEmpty()) {
        object.insert(QStringLiteral("rollback_status"), event.rollbackStatus);
    }

    if (!event.errorType.isEmpty()) {
        object.insert(QStringLiteral("error_type"), event.errorType);
    }
    if (!event.errorMessageSafe.isEmpty()) {
        object.insert(QStringLiteral("error_message_safe"), event.errorMessageSafe);
    }

    // KMA R-6 / DRIFT-002: canonical business result field (enum → canonical name).
    // Only emitted when has_value — serialize ALWAYS outputs canonical names via toString().
    if (event.sourceBusinessStatus.has_value()) {
        object.insert(
            QStringLiteral("source_business_status"),
            toString(*event.sourceBusinessStatus));
    }

    return object;
}

ValidationResult validate(const TurnFinalizedEvent& event)
{
    ValidationResult result = validateEventMetadata(event.metadata);
    if (event.metadata.turnId.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("turn_id"),
            QStringLiteral("Required field is missing."),
        });
    }
    if (event.metadata.sourceReference.isEmpty()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("source_reference"),
            QStringLiteral("Finalized turn requires a resolvable content reference."),
        });
    }
    if (!event.isFinal.has_value()) {
        result.errors.append({
            QStringLiteral("required"),
            QStringLiteral("is_final"),
            QStringLiteral("Required field is missing."),
        });
    } else if (!*event.isFinal) {
        result.errors.append({
            QStringLiteral("invalid_value"),
            QStringLiteral("is_final"),
            QStringLiteral("Turn finalized event must set is_final to true."),
        });
    }
    if (!event.finalizedAt.isValid()) {
        result.errors.append({
            QStringLiteral("invalid_timestamp"),
            QStringLiteral("finalized_at"),
            QStringLiteral("Timestamp must be valid ISO 8601."),
        });
    }
    if (!event.retryOfTurnId.isEmpty() && event.retryOfTurnId == event.metadata.turnId) {
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
    const auto missingMetadataField = firstMissingRequiredEventMetadataField(object);
    if (missingMetadataField.has_value()) {
        return {std::nullopt, {*missingMetadataField}};
    }

    const auto missingField = firstMissingRequiredField(
        object,
        {
            QStringLiteral("turn_id"),
            QStringLiteral("is_final"),
            QStringLiteral("finalized_at"),
        });
    if (missingField.has_value()) {
        return {std::nullopt, {*missingField}};
    }

    const auto invalidMetadataType = firstInvalidEventMetadataJsonType(object);
    if (invalidMetadataType.has_value()) {
        return {std::nullopt, {*invalidMetadataType}};
    }

    const auto invalidType = firstInvalidJsonType(
        object,
        {
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

    const auto toolIdsValue = object.value(QStringLiteral("tool_call_ids"));
    if (!toolIdsValue.isArray()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("tool_call_ids"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    const QJsonArray toolIds = toolIdsValue.toArray();
    QStringList toolCallIds;
    toolCallIds.reserve(toolIds.size());
    for (const QJsonValue& toolId : toolIds) {
        if (!toolId.isString()) {
            return {
                std::nullopt,
                {{
                    QStringLiteral("invalid_type"),
                    QStringLiteral("tool_call_ids"),
                    QStringLiteral("Array elements must be strings."),
                }},
            };
        }
        toolCallIds.append(toolId.toString());
    }

    TurnFinalizedEvent event;
    event.metadata = eventMetadataFromJson(object);
    event.finalMessageId = object.value(QStringLiteral("final_message_id")).toString();
    const auto isFinalValue = object.value(QStringLiteral("is_final"));
    if (!isFinalValue.isBool()) {
        return {
            std::nullopt,
            {{
                QStringLiteral("invalid_type"),
                QStringLiteral("is_final"),
                QStringLiteral("Field has an invalid JSON type."),
            }},
        };
    }
    event.isFinal = isFinalValue.toBool();
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

    QJsonObject object = eventMetadataToJson(event.metadata);
    object.insert(QStringLiteral("is_final"), event.isFinal.value_or(false));
    object.insert(QStringLiteral("tool_call_ids"), toolCallIds);
    object.insert(
        QStringLiteral("finalized_at"), event.finalizedAt.toUTC().toString(Qt::ISODateWithMs));

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
