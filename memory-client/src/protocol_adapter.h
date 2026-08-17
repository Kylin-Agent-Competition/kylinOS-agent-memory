#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QString>

#include <optional>
#include <vector>

namespace kylin::memory::client::v1 {

// ============================================================================
// 协议编解码（D 轨 IPC envelope 候选实现）
// ============================================================================
//
// 状态：PENDING_D_CONFIRMATION
//
// 本头实现 D 轨 UDS 长度前缀 JSON envelope 的客户端侧编解码候选。
// 协议格式对齐 memory-service/embedding/protocol.py（A 轨 Day5 已落地路径）：
//   每个消息 = 4 字节大端长度前缀 + UTF-8 JSON body
//   envelope = {
//     "protocol_version": "1.0",
//     "method": "memory.query" | "memory.health" | ...,
//     "payload": {...},
//     "request_id": "req_...",   // 可选
//     "trace_id": "trc_...",     // 可选
//     "deadline_ms": 5000        // 可选
//   }
//
// 注意：D 轨 envelope 未最终冻结（docs/day3/11_os_agent_event_contract_v1.md §10
// 标注 PENDING_D_CONFIRMATION）。本候选不得表述为最终 FROZEN；待 D 主审与
// E 补审关闭阻断后方可升级状态。
// ============================================================================

constexpr const char* kProtocolVersion = "1.0";
constexpr int kHeaderLen = 4;
constexpr int kMaxMessageLen = 4 * 1024 * 1024;  // 4 MiB 上限（防恶意超大包）

// 编解码错误码（不回显输入原文，固定安全消息）。
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

// 已知的客户端方法名（候选，不冻结）。
namespace methods {
extern const QString kMemoryQuery;
extern const QString kMemoryHealth;
extern const QString kMemoryRetrieve;
}  // namespace methods

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

// ── envelope 构造与解析 ────────────────────────────────────────────────────

// 构造请求 envelope（D 轨 IPC 候选）。
// method 必填；payload 为空时写入空对象 {}；可选字段仅在非空/有值时写入。
[[nodiscard]] QJsonObject buildEnvelope(
    const QString& method,
    const QJsonObject& payload,
    const QString& requestId = {},
    const QString& traceId = {},
    std::optional<int> deadlineMs = std::nullopt);

// 解析请求/响应 envelope。
// 失败返回非 None 的 ProtocolError；成功时 method/payload 必有值，
// 可选字段无值时为空字符串 / nullopt。
struct EnvelopeParts {
    QString method;
    QJsonObject payload;
    QString requestId;
    QString traceId;
    std::optional<int> deadlineMs;
};

[[nodiscard]] std::pair<std::optional<EnvelopeParts>, ProtocolError> parseEnvelope(
    const QJsonObject& envelope);

}  // namespace kylin::memory::client::v1
