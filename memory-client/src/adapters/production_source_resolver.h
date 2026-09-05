#pragma once

#include <QString>

#include <optional>

#include "adapters/memory_source_resolver.h"

// ============================================================================
// ProductionSourceResolver — 宿主 Chat DB 只读解析器（Host mapping 任务卡 S2）
// ============================================================================
//
// 状态：L0 就绪（fixture SQLite 验证）；生产注册仍 BLOCKED_BY_HOST_MAPPING：
//   - 真实宿主 Chat DB schema 须在麒麟 VM（S3/S5）从 kylin-aiassistant 源码
//     确认后经 config 适配（本类不接入 main.cpp / ViewModel，未经 VM 验证
//     不升级生产状态，对齐任务卡红线 §三.3）；
//   - memory-service 侧 PRODUCTION_RESOLVER_STATUS 属 D 轨，本文件不改。
//
// 受控路径语义（ADR-010 seam 生产实现，对齐服务端 source_resolver.py 口径）：
//   - 只读红线：QSQLITE_OPEN_READONLY 打开（SQLITE_OPEN_READONLY），
//     绝不写宿主 Chat DB（journal/wal 也不会创建）；
//   - source_reference 仅接受受控格式 ref:chat-record:{messageId}
//     （与 TurnExtractionAdapter::buildSourceReference 口径一致），
//     其余一律 nullopt；source_reference 为非可信输入，不记录到日志/异常；
//   - fail-closed：未打开 / 打开失败 / 引用格式不符 / 表缺失 / 行缺失 /
//     终稿消息非 assistant 角色 / 同 turn 用户消息缺失 / 正文空串 /
//     SQL 错误 → 一律 nullopt，禁止编造正文、禁止空串替代
//     （turns.original_user_text NOT NULL 冻结语义）；
//   - 表/列名仅允许 [A-Za-z0-9_]（标识符校验，防御 config 注入；config
//     虽受控，但生产可能来自配置文件）；
//   - modelRequest（模型请求侧原文）宿主 Chat DB 不提供，不编造，留空。
//
// 线程语义：QSqlDatabase 连接非线程安全；本类只在创建它的线程内使用
// （L0 单线程；VM 接线时由调用方保证）。
// ============================================================================

namespace kylin::memory::client::v1 {

// schema 映射配置 — 默认值为 S2 假设，真实值在 VM 内从宿主源码确认后覆盖。
struct ProductionSourceResolverConfig {
    QString databasePath;  // 宿主 Chat DB 文件路径（SQLite）

    // schema 映射（VM 确认前为假设默认值；仅允许 [A-Za-z0-9_] 标识符）：
    QString tableName = QStringLiteral("chat_record");
    QString messageIdColumn = QStringLiteral("message_id");
    QString turnIdColumn = QStringLiteral("turn_id");    // 同 turn 用户/助手消息关联键
    QString roleColumn = QStringLiteral("role");
    QString contentColumn = QStringLiteral("content");
    QString userRoleValue = QStringLiteral("user");           // 绑定参数，无需标识符校验
    QString assistantRoleValue = QStringLiteral("assistant"); // 绑定参数
};

class ProductionSourceResolver final : public MemorySourceResolver {
public:
    explicit ProductionSourceResolver(const ProductionSourceResolverConfig& config);
    ~ProductionSourceResolver() override;

    ProductionSourceResolver(const ProductionSourceResolver&) = delete;
    ProductionSourceResolver& operator=(const ProductionSourceResolver&) = delete;

    // 只读打开宿主 Chat DB。失败（路径空 / 文件不存在或不可读 / 标识符非法 /
    // QSQLITE 驱动缺失）返回 false；此后 resolve() 一律 nullopt（fail-closed）。
    // 不区分具体失败原因（避免路径/配置泄漏到调用方日志）。
    bool open();

    bool isOpen() const { return opened_; }

    // 按受控引用 ref:chat-record:{messageId} 解析：
    //   originalUserText = 同 turn 用户消息正文（必填非空，空串视为未命中）
    //   modelResponse    = 终稿（assistant）消息正文
    //   modelRequest     = 留空（宿主 Chat DB 不提供，不编造）
    // 任何失败 → nullopt。非可信输入：不记录引用/正文到日志或异常消息。
    std::optional<ResolvedTurnContent> resolve(const QString& sourceReference) const override;

    // 解析受控引用格式；非受控格式/空 id 返回 nullopt（不抛错、不记录输入）。
    static std::optional<QString> parseMessageId(const QString& sourceReference);

private:
    // 标识符校验：非空且仅 [A-Za-z0-9_]。
    static bool isValidIdentifier(const QString& name);

    ProductionSourceResolverConfig config_;
    QString connectionName_;  // QSqlDatabase 命名连接（析构时移除）
    bool opened_ = false;
};

}  // namespace kylin::memory::client::v1
