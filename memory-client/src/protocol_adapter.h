#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QString>

#include <optional>
#include <vector>

namespace kylin::memory::client::v1 {

// ============================================================================
// 协议编解码（D 轨 IPC envelope — 已冻结 FRZ-IPC-001~007）
// ============================================================================
//
// 状态：FROZEN_ALIGNED（2026-08-20 对齐 D4_IPC_PROTOCOL_FORMAL_FREEZE_20260817）
//
// 本头实现 D 轨 UDS 长度前缀 JSON envelope 的客户端侧编解码。
// 协议格式对齐 D 冻结契约（deliverables/D4_IPC_PROTOCOL_FREEZE_20260807.md）：
//   每个消息 = 4 字节大端长度前缀 + UTF-8 JSON body
//   最大消息 = 65536 字节 (64KB)（FRZ-IPC-001）
//
// 请求 envelope（FRZ-IPC-006 §6.1）：
//   {
//     "protocol_version": "1.0",          // 必填
//     "request_id": "req_...",             // 必填
//     "trace_id": "trc_...",               // 必填
//     "method": "echo"|"health"|"memory.retrieve"|...,  // 必填
//     "deadline_ms": 5000,                 // 必填
//     "idempotency_key": "...",            // 可选（写操作建议）
//     "payload": {...}                      // 必填
//   }
//
// 响应 envelope（FRZ-IPC-006 §6.2）：
//   {
//     "protocol_version": "1.0",          // 必填
//     "request_id": "req_...",             // 必填（回显）
//     "trace_id": "trc_...",               // 必填（回显）
//     "status": "ok"|"error",              // 必填
//     "data": {...},                        // 必填（成功时）
//     "server_ts": "2026-08-20T...",       // 必填（ISO 8601 UTC）
//     "error_code": "...",                 // 仅 error 时
//     "message": "..."                     // 仅 error 时
//   }
// ============================================================================

constexpr const char* kProtocolVersion = "1.0";
constexpr int kHeaderLen = 4;
constexpr int kMaxMessageLen = 65536;  // 64KB（FRZ-IPC-001 冻结值）

// 编解码错误码（客户端侧协议层错误，不回显输入原文，固定安全消息）。
enum class ProtocolErrorKind {
    None,
    IncompletePacket,        // 缓冲区数据不足一个完整包（应继续收数据）
    DeclaredLengthTooLarge,  // 声明长度超过上限
    InvalidUtf8,             // body 非 UTF-8
    InvalidJson,             // JSON 解析失败
    EnvelopeNotObject,       // envelope 顶层不是 JSON 对象
    MissingProtocolVersion,  // envelope 缺少 protocol_version
    UnsupportedProtocolVersion,  // protocol_version 不兼容
    MissingOrInvalidMethod,  // method 缺失或类型错误
    PayloadNotObject,        // payload 不是 JSON 对象
    // 响应解析错误
    MissingStatus,           // 响应缺少 status 字段
    InvalidStatus,           // status 值不是 "ok"/"error"
    MissingRequestId,        // 响应/请求缺少 request_id（回显/必填）
    MissingTraceId,          // 响应/请求缺少 trace_id（回显/必填）
    MissingData,            // status=ok 时缺少 data 字段
    MissingServerTs,        // 响应缺少 server_ts
    MissingErrorCode,      // status=error 时缺少 error_code
    MissingErrorMessage,   // status=error 时缺少 message
    InvalidErrorCode,      // error_code 不是 FRZ-IPC-002 冻结的 5 项之一
    InvalidServerTs,       // server_ts 不是合法 ISO 8601 UTC
    // 请求解析错误（FRZ-IPC-006 §6.1 必填字段）
    MissingDeadlineMs,     // 请求缺少 deadline_ms
    InvalidDeadlineMs,      // deadline_ms 类型错误或负值
};

struct ProtocolError {
    ProtocolErrorKind kind = ProtocolErrorKind::None;
    QString safeMessage;  // 固定英文消息，不包含输入原文

    [[nodiscard]] bool ok() const noexcept
    {
        return kind == ProtocolErrorKind::None;
    }
};

// 常量：协议版本字符串与 envelope 必填字段名。
extern const QString kProtocolVersionQString;
extern const QString kMethodKey;
extern const QString kPayloadKey;
extern const QString kProtocolVersionKey;
extern const QString kRequestIdKey;
extern const QString kTraceIdKey;
extern const QString kDeadlineMsKey;
extern const QString kIdempotencyKeyKey;
// 响应字段名（FRZ-IPC-006 §6.2）
extern const QString kStatusKey;
extern const QString kDataKey;
extern const QString kServerTsKey;
extern const QString kErrorCodeKey;
extern const QString kMessageKey;

// D 冻结方法路由表（FRZ-IPC-007，2026-08-17 已签署更正版 + ADR-010 2026-08-27）。
// 活跃方法仅 3 项：echo / health / memory.retrieve。
// evidence.record 已按 P0-4 移除（PR21_R3），memory.store 尚未实现（服务端返回
// UNSUPPORTED_METHOD）；turn.finalized 按 ADR-010 作为写链路候选方法新增
// （CANDIDATE / BLOCKED_BY_HOST_MAPPING，生产默认不注册，Demo 客户端可调用）。
namespace methods {
extern const QString kEcho;              // "echo"
extern const QString kHealth;            // "health"
extern const QString kMemoryRetrieve;   // "memory.retrieve"
extern const QString kMemoryStore;      // "memory.store"（未实现，服务端返回 UNSUPPORTED_METHOD）
extern const QString kTurnFinalized;    // "turn.finalized"（ADR-010 新增，写链路）
// D7C 偏好 IPC 方法（D 轨契约变更，随 D7C PR #87 落地）
extern const QString kPreferenceList;     // "preference.list"
extern const QString kPreferenceCreate;   // "preference.create"
extern const QString kPreferenceUpdate;   // "preference.update"
extern const QString kPreferenceRollback; // "preference.rollback"
extern const QString kPreferenceHistory;  // "preference.history"
// D6-C 候选写方法（不冻结，登记在 methods 命名空间以便客户端 / Mock 复用）
extern const QString kToolExecution;        // "tool.execution"
extern const QString kManualConfigIngest;   // "manual.config.ingest"
extern const QString kBehaviorObserve;      // "behavior.observe"
// D8C 候选 IPC 方法（CANDIDATE / pending ADR；生产默认不注册）
extern const QString kKnowledgeDetail;    // "knowledge.detail"
extern const QString kConflictCompare;    // "conflict.compare"
extern const QString kLifecycleStatus;    // "lifecycle.status"
// D9C 候选 IPC 方法（CANDIDATE / pending ADR；生产默认不注册）。
// context.assemble：把召回候选（B 轨混合检索输出）组装为受 Token 预算控制的
// MemoryContext，返回可解释字段（召回来源、记忆类型、冲突/不确定性提示）。
extern const QString kContextAssemble;   // "context.assemble"
}  // namespace methods

// D 冻结服务端错误码枚举（FRZ-IPC-002，5 项）。
namespace error_codes {
extern const QString kUnsupportedMethod;  // "UNSUPPORTED_METHOD"
extern const QString kInvalidRequest;    // "INVALID_REQUEST"
extern const QString kProtocolError;     // "PROTOCOL_ERROR"
extern const QString kInternalError;     // "INTERNAL_ERROR"
extern const QString kTimeout;            // "TIMEOUT"
}  // namespace error_codes

// ── 字节流编解码 ──────────────────────────────────────────────────────────

// 把 envelope dict 编码为长度前缀 JSON 字节流。
// 失败（body 过大、JSON 序列化失败）返回 nullopt。
[[nodiscard]] std::optional<QByteArray> encodeEnvelope(const QJsonObject& envelope);

// 流式解码结果。kind==IncompletePacket 表示需要继续收数据；其他非 None 值
// 表示不可恢复错误。consumed 表示本次消费的字节数（含包头与 body）。
struct DecodeResult {
    ProtocolError error;
    std::optional<QJsonObject> envelope;
    int consumed = 0;  // 已消费字节数
};

// 从缓冲区尝试解码一个完整包。
// 返回 DecodeResult：error.ok() 且 envelope 有值表示成功；consumed 表示已消费
// 字节数（成功时含包头+body，失败时为 0 以便调用方保留原始缓冲）。
// IncompletePacket 时 consumed=0，调用方应继续接收数据后重试。
[[nodiscard]] DecodeResult decodePacket(const QByteArray& buffer);

// ── 请求 envelope 构造与解析 ──────────────────────────────────────────────

// 构造请求 envelope（FRZ-IPC-006 §6.1）。
// method/payload 必填；requestId/traceId/deadlineMs 在 D 冻结中为必填，
// 但本函数保留可选参数以兼容测试——sendRequest 会始终填充这三个字段。
// 注意：parseEnvelope() 会严格校验这三个字段为必填。
[[nodiscard]] QJsonObject buildEnvelope(
    const QString& method,
    const QJsonObject& payload,
    const QString& requestId = {},
    const QString& traceId = {},
    std::optional<int> deadlineMs = std::nullopt);

// 解析请求 envelope（FRZ-IPC-006 §6.1）。
// 必填字段：protocol_version, method, payload, request_id, trace_id, deadline_ms。
// 失败返回非 None 的 ProtocolError；成功时所有字段必有值。
struct EnvelopeParts {
    QString method;
    QJsonObject payload;
    QString requestId;
    QString traceId;
    std::optional<int> deadlineMs;
};

[[nodiscard]] std::pair<std::optional<EnvelopeParts>, ProtocolError> parseEnvelope(
    const QJsonObject& envelope);

// ── 响应 envelope 解析（FRZ-IPC-006 §6.2）─────────────────────────────────

// 解析响应 envelope。
// 成功时 status/data/serverTs 必有值；status=="error" 时 errorCode/message 有值。
struct ResponseParts {
    QString status;       // "ok" 或 "error"
    QJsonObject data;     // 成功时的方法返回值
    QString serverTs;     // ISO 8601 UTC 时间戳
    QString requestId;    // 回显的请求 ID
    QString traceId;      // 回显的追踪 ID
    QString errorCode;    // 仅 status=="error" 时有值
    QString message;      // 仅 status=="error" 时有值
};

[[nodiscard]] std::pair<std::optional<ResponseParts>, ProtocolError> parseResponse(
    const QJsonObject& envelope);

// ── 响应 envelope 构造（FRZ-IPC-006 §6.2，供 Mock Gateway 与测试使用）─────

// 构造成功响应 envelope。
[[nodiscard]] QJsonObject buildSuccessResponse(
    const QString& requestId,
    const QString& traceId,
    const QJsonObject& data,
    const QString& serverTs = QStringLiteral("2026-08-20T00:00:00Z"));

// 构造错误响应 envelope。errorCode 必须为 error_codes 中的已知值。
[[nodiscard]] QJsonObject buildErrorResponse(
    const QString& requestId,
    const QString& traceId,
    const QString& errorCode,
    const QString& message,
    const QString& serverTs = QStringLiteral("2026-08-20T00:00:00Z"));

// 校验 error_code 是否为 FRZ-IPC-002 冻结的 5 项之一。
[[nodiscard]] bool isValidErrorCode(const QString& code);

}  // namespace kylin::memory::client::v1
