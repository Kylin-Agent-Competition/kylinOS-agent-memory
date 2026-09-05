#pragma once

#include <QString>

#include <optional>

#include "adapters/memory_source_resolver.h"

// ============================================================================
// ProductionSourceResolver — 宿主 Chat DB 只读解析器（Host mapping 任务卡 S2/V3-R）
// ============================================================================
//
// 状态：L0 就绪（fixture SQLite 复刻真实 schema 验证）；生产注册仍
// BLOCKED_BY_HOST_MAPPING：
//   - 本类不接入 main.cpp / ViewModel，S5 麒麟 VM 全链路复测通过、
//     D 轨 ACTIVE 化评估前不升级生产状态（任务卡红线 §三.3）；
//   - memory-service 侧 PRODUCTION_RESOLVER_STATUS 属 D 轨，本文件不改。
//
// 真实 schema（V3-R，2026-09-05 bacon VM 实测确认，报告
// evidence/l2-kylin-vm/c_hm_bacon_vm_schema_and_regression_20260905.md §3）：
//
//   CREATE TABLE RECORD(ID, sessionID, msgIndex, message TEXT, operateTime)
//
//   message 列为 JSON blob（非规范化列），关键字段：
//     $.author  "User" | "Bot"        —— 角色在 JSON 内，非独立列
//     $.isEnd   bool                  —— Bot 终稿标记（流式/中间消息为 false）
//     $.message string                —— 正文
//   turn 配对：同 sessionID 内 User N / Bot 终稿 N+1（msgIndex 会话内序号）；
//   无 Bot 终稿的 turn（模型未回复）→ fail-closed。
//
// 受控路径语义（ADR-010 seam 生产实现，对齐服务端 source_resolver.py 口径）：
//   - 只读红线：QSQLITE_OPEN_READONLY 裸选项打开（SQLITE_OPEN_READONLY），
//     绝不写宿主 Chat DB（journal/wal 也不会创建）；
//   - source_reference 仅接受受控格式 ref:chat-record:{messageId}
//     （messageId = RECORD.ID 行主键，与 TurnExtractionAdapter::
//     buildSourceReference 口径一致），其余一律 nullopt；
//     source_reference 为非可信输入，不记录到日志/异常；
//   - fail-closed（一律 nullopt，禁止编造正文、禁止空串替代，
//     turns.original_user_text NOT NULL 冻结语义）：
//       未打开 / 引用格式不符 / 表缺失 / 行缺失 /
//       终稿行 JSON 解析失败或非对象 / author 非 Bot / isEnd 非 true /
//       正文/会话/序号字段缺失或类型不符 /
//       窗口内无 User 行 / 窗口内任何行 JSON 损坏（防止配错 turn）/
//       最近 User 行正文空串 / SQL 错误；
//   - JSON 解析在 C++（QJsonDocument）完成，不依赖 SQLite JSON1 扩展
//     （任意 SQLite 构建可用；服务端 json_extract SQL 已在 VM 实测，
//     客户端侧选择更可移植的等价实现）；
//   - 表/列名仅允许 [A-Za-z0-9_]（标识符校验，防御 config 注入；JSON
//     字段名与角色值仅进入 C++ 解析 / 绑定参数，无注入面）；
//   - modelRequest（模型请求侧原文）宿主 Chat DB 不提供，不编造，留空。
//
// 线程语义：QSqlDatabase 连接非线程安全；本类只在创建它的线程内使用
// （L0 单线程；VM 接线时由调用方保证）。
// ============================================================================

namespace kylin::memory::client::v1 {

// schema 映射配置 — 默认值即 bacon VM 实测真实 schema/字段/角色值。
struct ProductionSourceResolverConfig {
    QString databasePath;  // 宿主 Chat DB 文件路径（SQLite）

    // 表/列名（标识符字段，仅允许 [A-Za-z0-9_]）：
    QString tableName = QStringLiteral("RECORD");
    QString idColumn = QStringLiteral("ID");              // 行主键 = source_reference 的 messageId
    QString sessionColumn = QStringLiteral("sessionID");  // 会话关联键
    QString msgIndexColumn = QStringLiteral("msgIndex");  // 会话内消息序号（turn 配对）
    QString messageColumn = QStringLiteral("message");    // JSON blob 列

    // JSON blob 内字段名（C++ QJsonDocument 解析，非 SQL 标识符）：
    QString authorField = QStringLiteral("author");
    QString contentField = QStringLiteral("message");
    QString isEndField = QStringLiteral("isEnd");

    // 角色值（绑定参数/C++ 比较，无需标识符校验；bacon VM 实测 "User"/"Bot"）：
    QString userAuthorValue = QStringLiteral("User");
    QString assistantAuthorValue = QStringLiteral("Bot");
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
    //   originalUserText = 同 turn 最近 User 行正文（必填非空，空串视为未命中）
    //   modelResponse    = 终稿行（Bot + isEnd=true）正文
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
