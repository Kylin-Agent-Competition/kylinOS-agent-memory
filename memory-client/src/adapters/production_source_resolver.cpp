#include "adapters/production_source_resolver.h"

#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QUuid>
#include <QVariant>

#include <cmath>

namespace kylin::memory::client::v1 {

namespace {

// 受控 source_reference 前缀（与 TurnExtractionAdapter::buildSourceReference
// 口径一致；变更须同步事件契约 v1 §7 与服务端 resolver）。
constexpr const char kSourceRefPrefix[] = "ref:chat-record:";

// User 行回扫窗口：从终稿 msgIndex-1 向前最多扫描 64 行寻找最近 User 行。
// 依据：实测 turn 为 User N / Bot 终稿 N+1 相邻配对；窗口容忍少量中间行
// （流式/刷新残留）。窗口内无 User 行 → fail-closed（不扩大扫描配错 turn）。
constexpr int kUserScanWindowLimit = 64;

QString sourceRefPrefixQString()
{
    return QString::fromLatin1(kSourceRefPrefix);
}

// JSON blob → QJsonObject；解析失败/非对象 → nullopt（fail-closed）。
std::optional<QJsonObject> parseJsonObject(const QString& blob)
{
    const QJsonDocument doc = QJsonDocument::fromJson(blob.toUtf8());
    if (!doc.isObject()) {
        return std::nullopt;
    }
    return doc.object();
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
    // fail-closed 前置校验：路径 + 表/列标识符（JSON 字段名与角色值仅进入
    // C++ 解析 / 绑定参数，无 SQL 注入面，无需标识符校验）。
    if (config_.databasePath.isEmpty() || !isValidIdentifier(config_.tableName)
        || !isValidIdentifier(config_.idColumn) || !isValidIdentifier(config_.sessionColumn)
        || !isValidIdentifier(config_.msgIndexColumn)
        || !isValidIdentifier(config_.messageColumn)) {
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

    // ① 终稿行（session 关联键 + 会话内序号 + JSON blob）。
    //    messageId 为数字串时按整数绑定（对齐 INTEGER 主键），否则按文本
    //    绑定（兼容 TEXT 主键的自定义 schema）。
    QSqlQuery finalQuery(db);
    finalQuery.setForwardOnly(true);
    const QString finalSql =
        QStringLiteral("SELECT %1, %2, %3 FROM %4 WHERE %5 = :message_id LIMIT 1")
            .arg(config_.sessionColumn, config_.msgIndexColumn, config_.messageColumn,
                 config_.tableName, config_.idColumn);
    if (!finalQuery.prepare(finalSql)) {
        return std::nullopt;
    }
    {
        bool numericId = false;
        const qlonglong idNum = messageId->toLongLong(&numericId);
        finalQuery.bindValue(QStringLiteral(":message_id"),
                             numericId ? QVariant(idNum) : QVariant(*messageId));
    }
    if (!finalQuery.exec() || !finalQuery.next()) {
        return std::nullopt;  // 行缺失或 SQL 错误（含表缺失）
    }
    const QVariant sessionVar = finalQuery.value(0);
    const QVariant msgIndexVar = finalQuery.value(1);
    if (sessionVar.toString().isEmpty()) {
        return std::nullopt;  // 无会话关联键，无法定位同 turn 用户消息
    }
    bool indexOk = false;
    const double finalIndex = msgIndexVar.toDouble(&indexOk);
    if (!indexOk || std::isnan(finalIndex) || finalIndex < 0) {
        return std::nullopt;  // 会话内序号缺失/非数值（无法配对）
    }

    // ② 终稿行 JSON 校验：author=Bot + isEnd=true + 正文为字符串。
    //    JSON 在 C++ 解析（QJsonDocument），不依赖 SQLite JSON1 扩展。
    const std::optional<QJsonObject> finalJson =
        parseJsonObject(finalQuery.value(2).toString());
    if (!finalJson.has_value()) {
        return std::nullopt;  // JSON 解析失败/非对象
    }
    {
        const QJsonValue author = finalJson->value(config_.authorField);
        if (!author.isString() || author.toString() != config_.assistantAuthorValue) {
            return std::nullopt;  // 非 Bot 行（如被误指为终稿的 User 行）
        }
        const QJsonValue isEnd = finalJson->value(config_.isEndField);
        if (!isEnd.isBool() || !isEnd.toBool()) {
            return std::nullopt;  // 非终稿（流式/中间消息 isEnd=false 或字段缺失）
        }
    }
    const QJsonValue responseValue = finalJson->value(config_.contentField);
    if (!responseValue.isString()) {
        return std::nullopt;  // 终稿正文字段缺失或非字符串
    }
    const QString modelResponse = responseValue.toString();

    // ③ 同 turn 用户消息：同 session 内从终稿序号-1 向前回扫最近 User 行
    //    （实测配对为 User N / Bot 终稿 N+1；窗口容忍少量中间行）。
    QSqlQuery userQuery(db);
    userQuery.setForwardOnly(true);
    const QString userSql =
        QStringLiteral("SELECT %1 FROM %2 WHERE %3 = :session_id AND %4 < :final_index "
                       "ORDER BY %4 DESC LIMIT %5")
            .arg(config_.messageColumn, config_.tableName, config_.sessionColumn,
                 config_.msgIndexColumn)
            .arg(kUserScanWindowLimit);
    if (!userQuery.prepare(userSql)) {
        return std::nullopt;
    }
    userQuery.bindValue(QStringLiteral(":session_id"), sessionVar);
    userQuery.bindValue(QStringLiteral(":final_index"), finalIndex);
    if (!userQuery.exec()) {
        return std::nullopt;
    }
    while (userQuery.next()) {
        // 窗口内任何行 JSON 损坏 → fail-closed：跳过损坏行可能把终稿配到
        // 更早 turn 的 User 消息（配错 turn 比漏检更不可接受）。
        const std::optional<QJsonObject> rowJson =
            parseJsonObject(userQuery.value(0).toString());
        if (!rowJson.has_value()) {
            return std::nullopt;
        }
        const QJsonValue author = rowJson->value(config_.authorField);
        if (author.isString() && author.toString() == config_.userAuthorValue) {
            // 最近 User 行即本 turn 用户消息：正文必填非空（NOT NULL 冻结语义）。
            const QJsonValue userText = rowJson->value(config_.contentField);
            if (!userText.isString() || userText.toString().isEmpty()) {
                return std::nullopt;  // 空串视为未命中，禁止空串替代
            }
            ResolvedTurnContent content;
            content.originalUserText = userText.toString();
            content.modelRequest.clear();  // 宿主 Chat DB 不提供模型请求侧原文，不编造
            content.modelResponse = modelResponse;
            return content;
        }

        if (author.isString() && author.toString() == config_.assistantAuthorValue) {
            const QJsonValue isEnd = rowJson->value(config_.isEndField);
            if (!isEnd.isBool() || isEnd.toBool()) {
                return std::nullopt;
            }
        }
    }
    return std::nullopt;  // 窗口内无 User 行（如模型未回复的 turn）→ fail-closed
}

}  // namespace kylin::memory::client::v1
