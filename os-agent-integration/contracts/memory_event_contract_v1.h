#pragma once

#include <QJsonObject>
#include <QDateTime>
#include <QList>
#include <QString>
#include <QStringList>

#include <optional>

namespace kylin::memory::contract::v1 {

struct ContractError {
    QString code;
    QString field;
    QString safeMessage;
};

struct ValidationResult {
    QList<ContractError> errors;

    [[nodiscard]] bool ok() const noexcept
    {
        return errors.isEmpty();
    }
};

template<typename T>
struct ParseResult {
    std::optional<T> value;
    QList<ContractError> errors;

    [[nodiscard]] bool ok() const noexcept
    {
        return value.has_value() && errors.isEmpty();
    }
};

struct MemoryQuery {
    QString schemaVersion;
    QString userId;
    QString sessionId;
    QString queryText;
    QString scene;
    int maxContextTokens = 0;
};

enum class InjectionStatus {
    Prepared,
    Injected,
    Failed,
    Skipped,
};

struct EventMetadata {
    QString schemaVersion;
    QString eventId;
    QString traceId;
    QString userId;
    QString sessionId;
    QString turnId;
    QDateTime occurredAt;
    QDateTime collectedAt;
    QString sourceReference;
    QString idempotencyKey;
};

struct MemoryContext {
    EventMetadata metadata;
    QString queryId;
    QStringList selectedMemoryIds;
    QString contextVersion;
    int tokenBudget = 0;
    int actualTokenCount = 0;
    int sensitiveExcludedCount = 0;
    int forgottenExcludedCount = 0;
    int conflictExcludedCount = 0;
    std::optional<InjectionStatus> injectionStatus;
};

enum class ToolExecutionStatus {
    Success,
    Partial,
    Failure,
    Cancelled,
    Timeout,
};

struct ToolExecutionEvent {
    EventMetadata metadata;
    QString toolCallId;
    QString toolName;
    QString argumentsRef;
    QDateTime startedAt;
    QDateTime finishedAt;
    std::optional<ToolExecutionStatus> executionStatus;
    QString resultRef;
    QString errorType;
    QString errorMessageSafe;
    std::optional<bool> sideEffect;
    bool rollbackRequired = false;
    QString rollbackStatus;
};

struct TurnFinalizedEvent {
    EventMetadata metadata;
    QString finalMessageId;
    std::optional<bool> isFinal;
    QString finalizationReason;
    QString stopReason;
    QString retryOfTurnId;
    QStringList toolCallIds;
    QDateTime finalizedAt;
};

[[nodiscard]] ValidationResult validateSchemaVersion(const QString& version);

[[nodiscard]] ValidationResult validate(const MemoryQuery& query);
[[nodiscard]] ParseResult<MemoryQuery> memoryQueryFromJson(const QJsonObject& object);
[[nodiscard]] QJsonObject toJson(const MemoryQuery& query);

[[nodiscard]] ParseResult<InjectionStatus> injectionStatusFromString(const QString& value);
[[nodiscard]] QString toString(InjectionStatus status);
[[nodiscard]] ValidationResult validate(const MemoryContext& context);
[[nodiscard]] ParseResult<MemoryContext> memoryContextFromJson(const QJsonObject& object);
[[nodiscard]] QJsonObject toJson(const MemoryContext& context);

[[nodiscard]] ParseResult<ToolExecutionStatus> toolExecutionStatusFromString(const QString& value);
[[nodiscard]] QString toString(ToolExecutionStatus status);
[[nodiscard]] ValidationResult validate(const ToolExecutionEvent& event);
[[nodiscard]] ParseResult<ToolExecutionEvent> toolExecutionEventFromJson(const QJsonObject& object);
[[nodiscard]] QJsonObject toJson(const ToolExecutionEvent& event);

[[nodiscard]] ValidationResult validate(const TurnFinalizedEvent& event);
[[nodiscard]] ParseResult<TurnFinalizedEvent> turnFinalizedEventFromJson(const QJsonObject& object);
[[nodiscard]] QJsonObject toJson(const TurnFinalizedEvent& event);

}
