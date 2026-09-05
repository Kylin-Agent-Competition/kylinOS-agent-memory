#include "adapters/production_source_resolver.h"

#include <QFileInfo>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QUuid>
#include <QVariant>

namespace kylin::memory::client::v1 {

namespace {

// 受控 source_reference 前缀（与 TurnExtractionAdapter::buildSourceReference
// 口径一致；变更须同步事件契约 v1 §7 与服务端 resolver）。
constexpr const char kSourceRefPrefix[] = "ref:chat-record:";

QString sourceRefPrefixQString()
{
    return QString::fromLatin1(kSourceRefPrefix);
}

}  // namespace

ProductionSourceResolver::ProductionSourceResolver(const ProductionSourceResolverConfig& config)
    : config_(config),
      connectionName_(QStringLiteral("kylin-memory-prod-resolver-")
                      + QUuid::createUuid().toString())
{
}

ProductionSourceResolver::~ProductionSourceResolver()
{
    if (opened_) {
        QSqlDatabase::removeDatabase(connectionName_);
    }
}

bool ProductionSourceResolver::isValidIdentifier(const QString& name)
{
    if (name.isEmpty()) {
        return false;
    }
    for (const QChar& ch : name) {
        const char16_t u = ch.unicode();
        const bool ok = (u >= u'a' && u <= u'z') || (u >= u'A' && u <= u'Z')
                        || (u >= u'0' && u <= u'9') || u == u'_';
        if (!ok) {
            return false;
        }
    }
    return true;
}

std::optional<QString> ProductionSourceResolver::parseMessageId(const QString& sourceReference)
{
    const QString prefix = sourceRefPrefixQString();
    if (!sourceReference.startsWith(prefix)) {
        return std::nullopt;
    }
    const QString messageId = sourceReference.mid(prefix.size());
    if (messageId.isEmpty()) {
        return std::nullopt;
    }
    return messageId;
}

bool ProductionSourceResolver::open()
{
    if (opened_) {
        return true;
    }
    // fail-closed 前置校验：路径 + 标识符（role 值走绑定参数，无需校验）。
    if (config_.databasePath.isEmpty() || !isValidIdentifier(config_.tableName)
        || !isValidIdentifier(config_.messageIdColumn)
        || !isValidIdentifier(config_.turnIdColumn) || !isValidIdentifier(config_.roleColumn)
        || !isValidIdentifier(config_.contentColumn)) {
        return false;
    }
    // 文件预检（双重防御）：不存在/不可读直接 fail-closed，不进入 SQLite 打开，
    // 确保任何 Qt 版本下都不会因驱动回退 READWRITE|CREATE 而在宿主侧建库
    // （Qt 5.15 实测：带值形式 "QSQLITE_OPEN_READONLY=TRUE" 不被识别，
    // 会以默认 READWRITE|CREATE 打开——不存在文件被创建，违反只读红线）。
    const QFileInfo dbInfo(config_.databasePath);
    if (!dbInfo.isFile() || !dbInfo.isReadable()) {
        return false;
    }

    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"), connectionName_);
        db.setDatabaseName(config_.databasePath);
        // 只读红线：必须使用裸选项 "QSQLITE_OPEN_READONLY"（Qt 5.15 实测带值
        // 形式不被识别）；生效后 sqlite3_open_v2(SQLITE_OPEN_READONLY) 不建库、
        // 不写库（journal/wal 亦不创建）。
        db.setConnectOptions(QStringLiteral("QSQLITE_OPEN_READONLY"));
        opened_ = db.open();
    }
    if (!opened_) {
        // db 局部对象已析构，此时移除连接安全（避免 "connection still in use"）。
        QSqlDatabase::removeDatabase(connectionName_);
    }
    return opened_;
}

std::optional<ResolvedTurnContent> ProductionSourceResolver::resolve(
    const QString& sourceReference) const
{
    if (!opened_) {
        return std::nullopt;  // fail-closed：未 open 或 open 失败
    }
    const std::optional<QString> messageId = parseMessageId(sourceReference);
    if (!messageId.has_value()) {
        return std::nullopt;  // 非受控引用格式（非可信输入，不记录）
    }
    const QSqlDatabase db = QSqlDatabase::database(connectionName_);
    if (!db.isOpen()) {
        return std::nullopt;
    }

    // ① 终稿消息行（assistant 角色 + 正文 + turn 关联键）。
    QSqlQuery finalQuery(db);
    finalQuery.setForwardOnly(true);
    const QString finalSql =
        QStringLiteral("SELECT %1, %2, %3 FROM %4 WHERE %5 = :message_id LIMIT 1")
            .arg(config_.roleColumn, config_.contentColumn, config_.turnIdColumn,
                 config_.tableName, config_.messageIdColumn);
    if (!finalQuery.prepare(finalSql)) {
        return std::nullopt;
    }
    finalQuery.bindValue(QStringLiteral(":message_id"), *messageId);
    if (!finalQuery.exec() || !finalQuery.next()) {
        return std::nullopt;  // 行缺失或 SQL 错误（含表缺失）
    }
    if (finalQuery.value(0).toString() != config_.assistantRoleValue) {
        return std::nullopt;  // 终稿消息须为 assistant 角色，否则 fail-closed
    }
    const QString modelResponse = finalQuery.value(1).toString();
    const QString turnKey = finalQuery.value(2).toString();
    if (turnKey.isEmpty()) {
        return std::nullopt;  // 无法关联同 turn 用户消息
    }

    // ② 同 turn 用户消息正文 → original_user_text（必填非空）。
    QSqlQuery userQuery(db);
    userQuery.setForwardOnly(true);
    const QString userSql = QStringLiteral("SELECT %1 FROM %2 WHERE %3 = :turn_id AND %4 = :role LIMIT 1")
                                .arg(config_.contentColumn, config_.tableName,
                                     config_.turnIdColumn, config_.roleColumn);
    if (!userQuery.prepare(userSql)) {
        return std::nullopt;
    }
    userQuery.bindValue(QStringLiteral(":turn_id"), turnKey);
    userQuery.bindValue(QStringLiteral(":role"), config_.userRoleValue);
    if (!userQuery.exec() || !userQuery.next()) {
        return std::nullopt;  // 同 turn 无用户消息
    }
    const QString originalUserText = userQuery.value(0).toString();
    if (originalUserText.isEmpty()) {
        return std::nullopt;  // 空串视为未命中（NOT NULL 冻结语义）
    }

    ResolvedTurnContent content;
    content.originalUserText = originalUserText;
    content.modelRequest.clear();  // 宿主 Chat DB 不提供模型请求侧原文，不编造
    content.modelResponse = modelResponse;
    return content;
}

}  // namespace kylin::memory::client::v1
