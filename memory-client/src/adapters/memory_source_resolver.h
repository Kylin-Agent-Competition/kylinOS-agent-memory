#pragma once

#include <QHash>
#include <QString>

#include <optional>

// ============================================================================
// MemorySourceResolver — ADR-010 source resolver seam 的客户端侧接口
// ============================================================================
//
// 状态：接口冻结（对齐服务端 memory-service/service/source_resolver.py seam）；
//       生产实现 BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED（Host mapping 任务卡 S2 交付
//       production resolver；S1 仅交付接口 + 纯内存测试 resolver）。
//
// 契约要点（ADR-010 / docs/day3/11_os_agent_event_contract_v1.md §7）：
//   - resolve(sourceReference) 命中 → 返回 ResolvedTurnContent；
//   - 未命中 / 无权限 / 宿主不可读 → 返回 std::nullopt（fail-closed），
//     调用方按 INTERNAL_ERROR（safe）处理，禁止编造正文、禁止以空串替代
//     （turns.original_user_text NOT NULL 冻结语义）；
//   - source_reference 是非可信输入：实现不得将其记录到日志/异常消息
//     （引用本身可能承载 PII，对齐服务端 resolver 口径）；
//   - 正文只经本受控通道进入 Provider 候选落库路径，不进入 C++ 事件、
//     普通日志或临时 JSON（原文隔离红线）。
// ============================================================================

namespace kylin::memory::client::v1 {

// 解析结果 — 字段对齐服务端 source_resolver.py ResolvedContent
// （original_user_text / model_request / model_response）。
struct ResolvedTurnContent {
    QString originalUserText;  // 必填：命中时必须非空（空串视为未命中）
    QString modelRequest;      // 可选：模型请求侧正文
    QString modelResponse;     // 可选：模型响应侧正文（→ Provider assistant_text）
};

class MemorySourceResolver {
public:
    virtual ~MemorySourceResolver() = default;

    // 按受控引用解析原文。无法解析返回 std::nullopt（调用方按 INTERNAL_ERROR
    // 处理，禁止编造正文）。const：解析为只读语义，允许适配器以 const 持有。
    virtual std::optional<ResolvedTurnContent> resolve(const QString& sourceReference) const = 0;
};

// ============================================================================
// ToolResultResolver — 受控 Tool Result resolver（事件契约 v1 §7 边界 4）
// ============================================================================
//
// 通过 tool_call_id 取得真实 Tool 执行结果；模型自述不得作为真实执行结果。
// 生产实现同样 BLOCKED_BY_HOST_MAPPING（依赖 Hook 观察点 / Tool Result 通道）。
// ============================================================================

// 解析结果 — 字段对齐服务端 Provider ToolResult dataclass
// （tool_name / arguments / status / result / error）。
struct ResolvedToolResult {
    QString toolName;      // 必填
    QString argumentsJson; // 受控 arguments（JSON 字符串；可为空）
    QString status;        // success | failure | cancelled
    QString result;        // 可选（success/partial）
    QString error;         // 可选（failure）
};

class ToolResultResolver {
public:
    virtual ~ToolResultResolver() = default;

    // 按 tool_call_id 解析真实执行结果；无法解析返回 std::nullopt（不编造）。
    virtual std::optional<ResolvedToolResult> resolve(const QString& toolCallId) const = 0;
};

// ============================================================================
// InMemorySourceResolver / InMemoryToolResultResolver — 纯内存测试 resolver
// ============================================================================
//
// 用途：L0 契约测试 / test profile 显式注入（对齐服务端 InMemorySourceResolver
// 口径：production 不注册，不声称真实正文通道已支持）。
// 生产状态：BLOCKED_BY_HOST_MAPPING / NOT_IMPLEMENTED 不变。
// ============================================================================

class InMemorySourceResolver final : public MemorySourceResolver {
public:
    void registerContent(const QString& sourceReference, const ResolvedTurnContent& content)
    {
        mapping_.insert(sourceReference, content);
    }

    std::optional<ResolvedTurnContent> resolve(const QString& sourceReference) const override
    {
        const auto it = mapping_.constFind(sourceReference);
        if (it == mapping_.constEnd()) {
            // 非可信输入：不记录引用内容，仅返回未命中。
            return std::nullopt;
        }
        return it.value();
    }

private:
    QHash<QString, ResolvedTurnContent> mapping_;
};

class InMemoryToolResultResolver final : public ToolResultResolver {
public:
    void registerResult(const QString& toolCallId, const ResolvedToolResult& result)
    {
        mapping_.insert(toolCallId, result);
    }

    std::optional<ResolvedToolResult> resolve(const QString& toolCallId) const override
    {
        const auto it = mapping_.constFind(toolCallId);
        if (it == mapping_.constEnd()) {
            return std::nullopt;
        }
        return it.value();
    }

private:
    QHash<QString, ResolvedToolResult> mapping_;
};

}  // namespace kylin::memory::client::v1
