// test_production_source_resolver.cpp — Host mapping 任务卡 S2 L0 契约测试
//
// fixture 复刻 bacon VM 实测真实 schema（V3-R，2026-09-05，报告
// evidence/l2-kylin-vm/c_hm_bacon_vm_schema_and_regression_20260905.md §3）：
//
//   CREATE TABLE RECORD(ID, sessionID, msgIndex, message TEXT, operateTime)
//   message = JSON blob：$.author "User"|"Bot"、$.isEnd bool、$.message 正文
//   turn 配对：同 sessionID 内 User N / Bot 终稿 N+1（msgIndex 会话内序号）
//
// 范围（fixture SQLite 模拟宿主 Chat DB；生产注册仍 BLOCKED_BY_HOST_MAPPING）：
//   §A 只读打开与命中
//     A1 open() 成功 + isOpen
//     A2 resolve 命中：originalUserText（同 session 最近 User 行）+
//        modelResponse（Bot 终稿正文）+ modelRequest 留空（不编造）
//     A3 与 TurnExtractionAdapter 集成：Extracted 状态、正文仅入
//        providerCandidate、ipcEvent 序列化不含正文（原文隔离红线）
//     A4 终稿与 User 行之间存在 Bot 流式中间行（isEnd=false）：窗口扫描
//        跳过非 User 行仍命中最近 User 行
//   §B 只读红线
//     B1 chmod 0444 只读文件仍可打开并命中（证明 QSQLITE_OPEN_READONLY
//        生效：若以读写模式打开 0444 文件会 SQLITE_CANTOPEN）[POSIX]
//     B2 resolve 前后 DB 文件 SHA-256 不变（绝不写宿主 DB）
//   §C fail-closed（一律 nullopt，禁止编造正文）
//     C1  未 open() 即 resolve
//     C2  DB 文件不存在 → open() false（且不得建库）
//     C3  chmod 000 不可读 → open() false [POSIX，root 下跳过]
//     C4  表缺失（SQLite 惰性打开，open 成功但 resolve 未命中）
//     C5  行缺失（messageId 无对应行）
//     C6  同 session 无 User 行（其它 session 有 User 行 → 兼验 session 隔离）
//     C7  最近 User 行正文为空串（NOT NULL 冻结语义）
//     C8  终稿行 author 非 Bot（被误指为终稿的 User 行）
//     C9  非受控引用格式（空串/无前缀/错误前缀/空 id/大小写不符/前后缀污染）
//     C10 config 标识符非法（SQL 注入防御）→ open() false
//     C11 终稿行 message 非 JSON / JSON 非对象（数组/字符串/截断）
//     C12 终稿行 isEnd=false（Bot 流式/中间消息，非终稿）
//     C13 终稿行 JSON 字段缺失或类型错误（author 缺失/非字符串、
//         正文缺失/非字符串、isEnd 非布尔）
//     C14 回扫窗口内行 JSON 损坏（跳过损坏行可能配错 turn → fail-closed）
//     C15 最近 User 行超出 64 行回扫窗口（不扩大扫描配错 turn）
//   §D schema 适配（config 覆盖，不改代码）
//     D1 自定义表/列/JSON 字段名/角色值命中
//   §E 窗口边界
//     E1 User 行恰在窗口边界（回扫第 64 行）→ 命中
//
// 依赖：Qt5 Sql QSQLITE 驱动（CI 已装 libqt5sql5-sqlite；缺失时本测试
//       失败而非跳过——L0 全绿必须意味着只读/fail-closed 行为真实验证）。
//
// 注意：本测试仅为 S2 生产 resolver 的 L0 契约验证（fixture SQLite 模拟），
//       不声称真实宿主 Chat DB 已接入（生产状态保持 BLOCKED_BY_HOST_MAPPING；
//       真实 schema 已在 bacon VM 实测确认，经 config 默认值适配）。

#include "adapters/memory_source_resolver.h"
#include "adapters/production_source_resolver.h"
#include "adapters/turn_extraction_adapter.h"

#include <QCryptographicHash>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QtTest>
#include <QSqlDatabase>
#include <QSqlQuery>

#ifdef Q_OS_UNIX
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace client = kylin::memory::client::v1;

namespace {

// ── JSON blob 构造（QJsonDocument 保证合法 JSON；resolver 在 C++ 侧解析）──

QString blob(const QJsonObject& obj)
{
    return QString::fromUtf8(QJsonDocument(obj).toJson(QJsonDocument::Compact));
}

QString userMsg(const QString& text)
{
    QJsonObject obj;
    obj.insert(QStringLiteral("author"), QStringLiteral("User"));
    obj.insert(QStringLiteral("message"), text);
    return blob(obj);
}

QString botFinalMsg(const QString& text)
{
    QJsonObject obj;
    obj.insert(QStringLiteral("author"), QStringLiteral("Bot"));
    obj.insert(QStringLiteral("isEnd"), true);
    obj.insert(QStringLiteral("message"), text);
    return blob(obj);
}

QString botStreamMsg(const QString& text)
{
    QJsonObject obj;
    obj.insert(QStringLiteral("author"), QStringLiteral("Bot"));
    obj.insert(QStringLiteral("isEnd"), false);
    obj.insert(QStringLiteral("message"), text);
    return blob(obj);
}

// ── fixture：RECORD 表（真实 schema 复刻，参数绑定写入 JSON blob）──

struct RecordRow {
    qint64 id = 0;
    QString session;
    int msgIndex = 0;
    QString messageJson;  // JSON blob（可为损坏 JSON，供 fail-closed 用例）
};

bool createRecordDb(const QString& path, const QList<RecordRow>& rows)
{
    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"));
        db.setDatabaseName(path);
        if (!db.open()) {
            return false;
        }
        QSqlQuery q(db);
        if (!q.exec(QStringLiteral(
                "CREATE TABLE RECORD (ID INTEGER PRIMARY KEY, sessionID TEXT, "
                "msgIndex INTEGER, message TEXT, operateTime TEXT)"))) {
            return false;
        }
        QSqlQuery insert(db);
        if (!insert.prepare(QStringLiteral(
                "INSERT INTO RECORD (ID, sessionID, msgIndex, message, operateTime) "
                "VALUES (:id, :session, :idx, :msg, :time)"))) {
            return false;
        }
        for (const RecordRow& row : rows) {
            insert.bindValue(QStringLiteral(":id"), row.id);
            insert.bindValue(QStringLiteral(":session"), row.session);
            insert.bindValue(QStringLiteral(":idx"), row.msgIndex);
            insert.bindValue(QStringLiteral(":msg"), row.messageJson);
            insert.bindValue(QStringLiteral(":time"), QStringLiteral("2026-09-05 12:00:00"));
            if (!insert.exec()) {
                return false;
            }
        }
    }
    QSqlDatabase::removeDatabase(QSqlDatabase::defaultConnection);
    return true;
}

bool createIdNullRecordDb(const QString& path, const QList<RecordRow>& rows)
{
    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"));
        db.setDatabaseName(path);
        if (!db.open()) {
            return false;
        }
        QSqlQuery q(db);
        if (!q.exec(QStringLiteral(
                "CREATE TABLE RECORD("
                "ID INT AUTO_INCREMENT, sessionID VARCHAR(36), msgIndex INT, "
                "message TEXT, operateTime INTEGER, PRIMARY KEY (ID))"))) {
            return false;
        }
        QSqlQuery insert(db);
        if (!insert.prepare(QStringLiteral(
                "INSERT INTO RECORD (sessionID, msgIndex, message, operateTime) "
                "VALUES (:session, :idx, :msg, :time)"))) {
            return false;
        }
        for (const RecordRow& row : rows) {
            insert.bindValue(QStringLiteral(":session"), row.session);
            insert.bindValue(QStringLiteral(":idx"), row.msgIndex);
            insert.bindValue(QStringLiteral(":msg"), row.messageJson);
            insert.bindValue(QStringLiteral(":time"), 0);
            if (!insert.exec()) {
                return false;
            }
        }
    }
    QSqlDatabase::removeDatabase(QSqlDatabase::defaultConnection);
    return true;
}

// 通用 fixture（任意 SQL；C4 无关表 / D1 自定义 schema / C11 损坏 JSON 行用）。
bool createFixtureDb(const QString& path, const QString& createSql,
                     const QList<QString>& insertSqls)
{
    {
        QSqlDatabase db = QSqlDatabase::addDatabase(QStringLiteral("QSQLITE"));
        db.setDatabaseName(path);
        if (!db.open()) {
            return false;
        }
        QSqlQuery q(db);
        if (!q.exec(createSql)) {
            return false;
        }
        for (const QString& insert : insertSqls) {
            if (!q.exec(insert)) {
                return false;
            }
        }
    }
    QSqlDatabase::removeDatabase(QSqlDatabase::defaultConnection);
    return true;
}

QByteArray fileSha256(const QString& path)
{
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        return QByteArray();
    }
    return QCryptographicHash::hash(f.readAll(), QCryptographicHash::Sha256);
}

client::ProductionSourceResolverConfig defaultConfig(const QString& dbPath)
{
    client::ProductionSourceResolverConfig config;
    config.databasePath = dbPath;
    return config;
}

// 默认 fixture 数据（真实 schema：RECORD + JSON blob）：
//   sess-1  完整 turn（User 1 / Bot 终稿 2 相邻配对）→ A2/A3/B1/B2 命中
//   sess-2  仅 Bot 终稿（其它 session 均有 User 行）→ C6（兼验 session 隔离：
//           扫描必须限定同 sessionID，不得命中 sess-1 的 User 行）
//   sess-3  User 正文空串 → C7
//   sess-4  User 行被误指为终稿 → C8
//   sess-5  第二条完整 turn → B2 第二次命中
QList<RecordRow> defaultRecordRows()
{
    return {
        {101, QStringLiteral("sess-1"), 1, userMsg(QStringLiteral("用户真实提问正文"))},
        {102, QStringLiteral("sess-1"), 2, botFinalMsg(QStringLiteral("助手终稿正文"))},
        {201, QStringLiteral("sess-2"), 1, botFinalMsg(QStringLiteral("无用户消息的终稿"))},
        {301, QStringLiteral("sess-3"), 1, userMsg(QString())},
        {302, QStringLiteral("sess-3"), 2, botFinalMsg(QStringLiteral("空用户正文的终稿"))},
        {401, QStringLiteral("sess-4"), 1, userMsg(QStringLiteral("被误指为终稿的用户消息"))},
        {501, QStringLiteral("sess-5"), 1, userMsg(QStringLiteral("第二条完整turn的用户正文"))},
        {502, QStringLiteral("sess-5"), 2, botFinalMsg(QStringLiteral("第二条完整turn的终稿"))},
    };
}

bool createDefaultRecordDb(const QString& path)
{
    return createRecordDb(path, defaultRecordRows());
}

}  // namespace

class ProductionSourceResolverTest final : public QObject {
    Q_OBJECT

private slots:
    // §A 只读打开与命中
    void openSucceedsOnReadableDatabase();          // A1
    void resolveHitsReturnsTurnContent();           // A2
    void resolveThroughTurnExtractionAdapter();     // A3
    void resolveSkipsIntermediateBotRows();         // A4
    void failClosedAtPreviousFinalizedBotBoundary(); // A5
    void resolveMultiTurnReturnsCurrentUser();      // A6

    // §B 只读红线
    void readonlyOpenWorksOnWriteProtectedFile();   // B1
    void resolveDoesNotModifyDatabaseFile();        // B2

    // §C fail-closed
    void failClosedWhenNotOpened();                 // C1
    void failClosedOnMissingDatabaseFile();         // C2
    void failClosedOnUnreadableFile();              // C3
    void failClosedOnMissingTable();                // C4
    void failClosedOnMissingRow();                  // C5
    void failClosedWhenTurnHasNoUserMessage();      // C6
    void failClosedOnEmptyUserText();               // C7
    void failClosedWhenFinalMessageNotBot();        // C8
    void failClosedOnNonControlledReferenceFormats();  // C9
    void invalidIdentifierConfigFailsOpen();        // C10
    void failClosedOnMalformedFinalRowJson();       // C11
    void failClosedOnNonFinalBotMessage();          // C12
    void failClosedOnInvalidJsonFields();           // C13
    void failClosedOnCorruptedRowInScanWindow();    // C14
    void failClosedWhenUserRowBeyondScanWindow();   // C15

    // §D schema 适配
    void customSchemaConfigResolves();              // D1

    // §E 窗口边界
    void resolveHitsAtWindowBoundaryEdge();         // E1
    void defaultIdColumnFailsClosedOnIdNullRows();  // E2
    void rowidOverrideResolvesIdNullRowsReadOnly(); // E3

private:
    QTemporaryDir tempDir_;
};

// ── §A 只读打开与命中 ────────────────────────────────────────────────────────

void ProductionSourceResolverTest::openSucceedsOnReadableDatabase()  // A1
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a1.db"));
    QVERIFY(createDefaultRecordDb(dbPath));
    QVERIFY(QFile::exists(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY(resolver.isOpen());
    // 重复 open 幂等。
    QVERIFY(resolver.open());
}

void ProductionSourceResolverTest::resolveHitsReturnsTurnContent()  // A2
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a2.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());

    // sess-1：User msgIndex=1 / Bot 终稿 msgIndex=2（VM 实测相邻配对形态）。
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:102"));
    QVERIFY2(hit.has_value(), "受控引用应命中");
    QCOMPARE(hit->originalUserText, QStringLiteral("用户真实提问正文"));
    QCOMPARE(hit->modelResponse, QStringLiteral("助手终稿正文"));
    QCOMPARE(hit->modelRequest, QString());  // 宿主 Chat DB 不提供，不编造
}

void ProductionSourceResolverTest::resolveThroughTurnExtractionAdapter()  // A3
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a3.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());

    client::TurnObservation obs;
    obs.userId = QStringLiteral("user-l0");
    obs.sessionId = QStringLiteral("sess-1");
    obs.turnId = QStringLiteral("turn-1");
    obs.finalMessageId = QStringLiteral("102");  // → ref:chat-record:102
    obs.finalizationReason = QStringLiteral("completed");
    obs.occurredAtIso = QStringLiteral("2026-09-05T12:00:00.456Z");
    obs.sourceType = QStringLiteral("chat");

    const client::TurnExtractionAdapter adapter(&resolver, nullptr);
    const client::TurnExtractionOutcome out = adapter.extract(obs);

    QCOMPARE(out.status, client::TurnExtractionOutcome::Status::Extracted);
    const QJsonObject candidate = out.providerCandidate;
    QCOMPARE(candidate.value(QStringLiteral("user_text")).toString(),
             QStringLiteral("用户真实提问正文"));
    QCOMPARE(candidate.value(QStringLiteral("assistant_text")).toString(),
             QStringLiteral("助手终稿正文"));

    // 原文隔离红线：ipcEvent 序列化全文不含正文。
    const QString ipcEventText =
        QString::fromUtf8(QJsonDocument(out.ipcEvent).toJson(QJsonDocument::Compact));
    QVERIFY2(!ipcEventText.contains(QStringLiteral("用户真实提问正文")),
             "ipcEvent 不得包含用户正文");
    QVERIFY2(!ipcEventText.contains(QStringLiteral("助手终稿正文")),
             "ipcEvent 不得包含助手正文");
}

void ProductionSourceResolverTest::resolveSkipsIntermediateBotRows()  // A4
{
    // 真实形态：User 与终稿之间存在 Bot 流式中间行（isEnd=false），
    // 窗口扫描须跳过非 User 行命中最近 User 行（不因中间行 fail-closed）。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a4.db"));
    QVERIFY(createRecordDb(dbPath, {
        {11, QStringLiteral("sess-a4"), 1, userMsg(QStringLiteral("流式场景的用户正文"))},
        {12, QStringLiteral("sess-a4"), 2, botStreamMsg(QStringLiteral("流式中间片段1"))},
        {13, QStringLiteral("sess-a4"), 3, botStreamMsg(QStringLiteral("流式中间片段2"))},
        {14, QStringLiteral("sess-a4"), 4, botFinalMsg(QStringLiteral("流式场景的终稿正文"))},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:14"));
    QVERIFY2(hit.has_value(), "中间流式行不应阻断配对");
    QCOMPARE(hit->originalUserText, QStringLiteral("流式场景的用户正文"));
    QCOMPARE(hit->modelResponse, QStringLiteral("流式场景的终稿正文"));
}

void ProductionSourceResolverTest::failClosedAtPreviousFinalizedBotBoundary()  // A5
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a5.db"));
    QVERIFY(createRecordDb(dbPath, {
        {21, QStringLiteral("sess-a5"), 1, userMsg(QStringLiteral("previous-user"))},
        {22, QStringLiteral("sess-a5"), 2, botFinalMsg(QStringLiteral("previous-final"))},
        {23, QStringLiteral("sess-a5"), 3, botFinalMsg(QStringLiteral("current-final"))},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:23")).has_value(),
             "previous BotFinal must stop the backward scan");
}

void ProductionSourceResolverTest::resolveMultiTurnReturnsCurrentUser()  // A6
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a6.db"));
    QVERIFY(createRecordDb(dbPath, {
        {31, QStringLiteral("sess-a6"), 1, userMsg(QStringLiteral("turn-A user"))},
        {32, QStringLiteral("sess-a6"), 2, botFinalMsg(QStringLiteral("turn-A final"))},
        {33, QStringLiteral("sess-a6"), 3, userMsg(QStringLiteral("turn-B user"))},
        {34, QStringLiteral("sess-a6"), 4, botStreamMsg(QStringLiteral("turn-B stream"))},
        {35, QStringLiteral("sess-a6"), 5, botFinalMsg(QStringLiteral("turn-B final"))},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:35"));
    QVERIFY2(hit.has_value(), "current turn user must resolve");
    QCOMPARE(hit->originalUserText, QStringLiteral("turn-B user"));
    QCOMPARE(hit->modelResponse, QStringLiteral("turn-B final"));
}

// ── §B 只读红线 ─────────────────────────────────────────────────────────────

void ProductionSourceResolverTest::readonlyOpenWorksOnWriteProtectedFile()  // B1
{
#ifdef Q_OS_UNIX
    if (::getuid() == 0) {
        QSKIP("root 用户下 chmod 权限位不生效，无法验证只读打开语义");
    }
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-b1.db"));
    QVERIFY(createDefaultRecordDb(dbPath));
    QVERIFY(::chmod(dbPath.toUtf8().constData(), 0444) == 0);

    // 0444 文件：只读打开必须成功（写保护不阻碍受控读取）。
    // 注：SQLite 对写保护文件存在 OS 层只读回退，故本用例不能单独证明
    // READONLY 标志本身——标志的回归证明是 C2 的"失败后不建库"断言
    // 与 B2 的"resolve 前后文件哈希不变"。
    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY2(resolver.open(), "只读模式应可打开 0444 文件（受控读取不受写保护阻碍）");
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:102"));
    QVERIFY2(hit.has_value(), "只读打开后应能命中");
    QCOMPARE(hit->originalUserText, QStringLiteral("用户真实提问正文"));

    ::chmod(dbPath.toUtf8().constData(), 0644);  // 恢复，便于临时目录清理
#else
    QSKIP("chmod 只读权限位验证仅限 POSIX（Unix）平台");
#endif
}

void ProductionSourceResolverTest::resolveDoesNotModifyDatabaseFile()  // B2
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-b2.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    const QByteArray hashBefore = fileSha256(dbPath);
    QVERIFY(!hashBefore.isEmpty());

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY(resolver.resolve(QStringLiteral("ref:chat-record:102")).has_value());
    QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:999")).has_value());
    QVERIFY(resolver.resolve(QStringLiteral("ref:chat-record:502")).has_value());

    QCOMPARE(fileSha256(dbPath), hashBefore);  // 绝不写宿主 DB（含 journal/wal）
}

// ── §C fail-closed ──────────────────────────────────────────────────────────

void ProductionSourceResolverTest::failClosedWhenNotOpened()  // C1
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c1.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(!resolver.isOpen());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:102")).has_value(),
             "未 open() 必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnMissingDatabaseFile()  // C2
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("nonexistent.db"));
    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY2(!resolver.open(), "文件不存在时 open() 必须失败");
    QVERIFY(!resolver.isOpen());
    QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:102")).has_value());
    // 只读红线回归：失败后不得在宿主侧创建 DB 文件（Qt 5.15 实测带值形式
    // "QSQLITE_OPEN_READONLY=TRUE" 不被识别，会以 READWRITE|CREATE 建库）。
    QVERIFY2(!QFile::exists(dbPath), "open() 失败不得创建数据库文件（绝不写宿主）");
}

void ProductionSourceResolverTest::failClosedOnUnreadableFile()  // C3
{
#ifdef Q_OS_UNIX
    if (::getuid() == 0) {
        QSKIP("root 用户下 chmod 权限位不生效，无法验证不可读语义");
    }
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c3.db"));
    QVERIFY(createDefaultRecordDb(dbPath));
    QVERIFY(::chmod(dbPath.toUtf8().constData(), 0000) == 0);

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY2(!resolver.open(), "chmod 000 不可读文件 open() 必须失败（无权限 fail-closed）");
    QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:102")).has_value());

    ::chmod(dbPath.toUtf8().constData(), 0644);  // 恢复，便于临时目录清理
#else
    QSKIP("chmod 不可读权限位验证仅限 POSIX（Unix）平台");
#endif
}

void ProductionSourceResolverTest::failClosedOnMissingTable()  // C4
{
    // SQLite 惰性打开：无 RECORD 表的 DB 文件 open() 成功，resolve 时表缺失
    // → fail-closed。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c4.db"));
    QVERIFY(createFixtureDb(dbPath, QStringLiteral("CREATE TABLE unrelated (x TEXT)"),
                            {QStringLiteral("INSERT INTO unrelated VALUES ('y')")}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());  // 文件合法 SQLite，打开成功
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:102")).has_value(),
             "表缺失必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnMissingRow()  // C5
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c5.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:999")).has_value(),
             "行缺失必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedWhenTurnHasNoUserMessage()  // C6
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c6.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    // sess-2 仅 Bot 终稿；其它 session 均有 User 行——本用例兼验扫描的
    // session 隔离：不得把 sess-1/sess-5 的 User 行配给 sess-2 的终稿。
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:201")).has_value(),
             "同 session 无 User 行必须 fail-closed（不得跨 session 配对）");
}

void ProductionSourceResolverTest::failClosedOnEmptyUserText()  // C7
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c7.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    // sess-3 最近 User 行正文为空串 → 视为未命中（NOT NULL 冻结语义，
    // 禁止空串替代）。
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:302")).has_value(),
             "用户正文空串必须视为未命中");
}

void ProductionSourceResolverTest::failClosedWhenFinalMessageNotBot()  // C8
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c8.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    // 401 是 User 行（JSON author="User"）：不得作为终稿解析（fail-closed，
    // 不编造）。
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:401")).has_value(),
             "终稿行 author 非 Bot 必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnNonControlledReferenceFormats()  // C9
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c9.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());

    const QStringList nonControlledRefs = {
        QString(),                                        // 空串
        QStringLiteral("102"),                            // 无前缀
        QStringLiteral("ref://turn/102"),                 // 非受控前缀（test profile 格式）
        QStringLiteral("ref:chat-record:"),               // 前缀后空 id
        QStringLiteral("REF:CHAT-RECORD:102"),            // 大小写不符（大小写敏感）
        QStringLiteral(" ref:chat-record:102"),           // 前导空格
        QStringLiteral("ref:chat-record:102 extra"),      // 后缀污染
        QStringLiteral("ref:chat-record:10 2"),           // id 中间空格（文本绑定亦无此行）
    };
    for (const QString& ref : nonControlledRefs) {
        QVERIFY2(!resolver.resolve(ref).has_value(),
                 "非受控引用格式必须 fail-closed（引用本身不记录）");
    }
}

void ProductionSourceResolverTest::invalidIdentifierConfigFailsOpen()  // C10
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c10.db"));
    QVERIFY(createDefaultRecordDb(dbPath));

    const QList<QString> maliciousIdentifiers = {
        QStringLiteral("RECORD; DROP TABLE RECORD"),  // SQL 注入
        QStringLiteral("chat-record"),                // 连字符
        QStringLiteral("`RECORD`"),                   // 反引号
        QStringLiteral("RE\"CORD"),                   // 引号
        QStringLiteral(""),                           // 空表名
    };
    for (const QString& bad : maliciousIdentifiers) {
        client::ProductionSourceResolverConfig config = defaultConfig(dbPath);
        config.tableName = bad;
        client::ProductionSourceResolver resolver(config);
        QVERIFY2(!resolver.open(), "非法表名 config 必须 open() 失败（fail-closed）");
        QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:102")).has_value());
    }
    // 列名同样受标识符校验（至少覆盖一个列字段）。
    {
        client::ProductionSourceResolverConfig config = defaultConfig(dbPath);
        config.msgIndexColumn = QStringLiteral("msgIndex; --");
        client::ProductionSourceResolver resolver(config);
        QVERIFY2(!resolver.open(), "非法列名 config 必须 open() 失败（fail-closed）");
    }
}

void ProductionSourceResolverTest::failClosedOnMalformedFinalRowJson()  // C11
{
    // 终稿行 message 列非合法 JSON / JSON 非对象（数组、字符串）→ fail-closed。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c11.db"));
    QVERIFY(createRecordDb(dbPath, {
        // 正常 User 行（证明失败归因于终稿行 JSON 本身）。
        {21, QStringLiteral("sess-c11a"), 1, userMsg(QStringLiteral("截断JSON前的用户正文"))},
        {22, QStringLiteral("sess-c11a"), 2, QStringLiteral("{\"author\":\"Bot\",\"isEnd\":tr")},
        {31, QStringLiteral("sess-c11b"), 1, userMsg(QStringLiteral("数组JSON前的用户正文"))},
        {32, QStringLiteral("sess-c11b"), 2, QStringLiteral("[1,2,3]")},
        {41, QStringLiteral("sess-c11c"), 1, userMsg(QStringLiteral("字符串JSON前的用户正文"))},
        {42, QStringLiteral("sess-c11c"), 2, QStringLiteral("\"just a string\"")},
        {51, QStringLiteral("sess-c11d"), 1, userMsg(QStringLiteral("非JSON文本前的用户正文"))},
        {52, QStringLiteral("sess-c11d"), 2, QStringLiteral("not-json at all")},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    for (const char* id : {"22", "32", "42", "52"}) {
        QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:") + QLatin1String(id))
                      .has_value(),
                 "终稿行 message 非 JSON 对象必须 fail-closed");
    }
}

void ProductionSourceResolverTest::failClosedOnNonFinalBotMessage()  // C12
{
    // Bot 流式/中间消息（isEnd=false）不是终稿 → fail-closed（模型未完成回复）。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c12.db"));
    QVERIFY(createRecordDb(dbPath, {
        {61, QStringLiteral("sess-c12"), 1, userMsg(QStringLiteral("流式未完成turn的用户正文"))},
        {62, QStringLiteral("sess-c12"), 2, botStreamMsg(QStringLiteral("流式中间消息"))},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:62")).has_value(),
             "isEnd=false 的 Bot 行必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnInvalidJsonFields()  // C13
{
    // 终稿行 JSON 字段缺失/类型错误（各 sub-case 独立 session，均带正常
    // User 行，证明失败归因于终稿行字段校验）。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c13.db"));
    QVERIFY(createRecordDb(dbPath, {
        // author 字段缺失。
        {71, QStringLiteral("sess-c13a"), 1, userMsg(QStringLiteral("author缺失前的用户正文"))},
        {72, QStringLiteral("sess-c13a"), 2,
         blob(QJsonObject{{QStringLiteral("isEnd"), true},
                          {QStringLiteral("message"), QStringLiteral("author缺失的终稿")}})},
        // author 非字符串。
        {81, QStringLiteral("sess-c13b"), 1, userMsg(QStringLiteral("author非串前的用户正文"))},
        {82, QStringLiteral("sess-c13b"), 2,
         blob(QJsonObject{{QStringLiteral("author"), 123},
                          {QStringLiteral("isEnd"), true},
                          {QStringLiteral("message"), QStringLiteral("author非串的终稿")}})},
        // isEnd 字段缺失。
        {91, QStringLiteral("sess-c13c"), 1, userMsg(QStringLiteral("isEnd缺失前的用户正文"))},
        {92, QStringLiteral("sess-c13c"), 2,
         blob(QJsonObject{{QStringLiteral("author"), QStringLiteral("Bot")},
                          {QStringLiteral("message"), QStringLiteral("isEnd缺失的终稿")}})},
        // isEnd 非布尔（字符串 "true"）。
        {111, QStringLiteral("sess-c13d"), 1, userMsg(QStringLiteral("isEnd非布尔前的用户正文"))},
        {112, QStringLiteral("sess-c13d"), 2,
         blob(QJsonObject{{QStringLiteral("author"), QStringLiteral("Bot")},
                          {QStringLiteral("isEnd"), QStringLiteral("true")},
                          {QStringLiteral("message"), QStringLiteral("isEnd非布尔的终稿")}})},
        // 正文字段缺失。
        {121, QStringLiteral("sess-c13e"), 1, userMsg(QStringLiteral("正文缺失前的用户正文"))},
        {122, QStringLiteral("sess-c13e"), 2,
         blob(QJsonObject{{QStringLiteral("author"), QStringLiteral("Bot")},
                          {QStringLiteral("isEnd"), true}})},
        // 正文非字符串。
        {131, QStringLiteral("sess-c13f"), 1, userMsg(QStringLiteral("正文非串前的用户正文"))},
        {132, QStringLiteral("sess-c13f"), 2,
         blob(QJsonObject{{QStringLiteral("author"), QStringLiteral("Bot")},
                          {QStringLiteral("isEnd"), true},
                          {QStringLiteral("message"), 42}})},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    for (const char* id : {"72", "82", "92", "112", "122", "132"}) {
        QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:") + QLatin1String(id))
                      .has_value(),
                 "终稿行 JSON 字段缺失/类型错误必须 fail-closed");
    }
}

void ProductionSourceResolverTest::failClosedOnCorruptedRowInScanWindow()  // C14
{
    // 回扫窗口内行 JSON 损坏：本 turn 的 User 行本身损坏时，"跳过损坏行"
    // 的错误实现会继续扫到更早 turn 的 User 行（配错 turn 比漏检更不可
    // 接受）→ 窗口内任何行损坏即整体 fail-closed。
    // 布局：更早 turn User 1 / 终稿 2；本 turn User 行 3 损坏 / 终稿 4。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c14.db"));
    QVERIFY(createRecordDb(dbPath, {
        {141, QStringLiteral("sess-c14"), 1, userMsg(QStringLiteral("更早turn的用户正文"))},
        {142, QStringLiteral("sess-c14"), 2, botFinalMsg(QStringLiteral("更早turn的终稿"))},
        {143, QStringLiteral("sess-c14"), 3, QStringLiteral("{corrupted json")},
        {144, QStringLiteral("sess-c14"), 4, botFinalMsg(QStringLiteral("本turn的终稿"))},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:144"));
    QVERIFY2(!hit.has_value(), "窗口内 JSON 损坏必须 fail-closed（不得跳过损坏行配错 turn）");
}

void ProductionSourceResolverTest::failClosedWhenUserRowBeyondScanWindow()  // C15
{
    // 最近 User 行距终稿 65 行（窗口 64 行装不下）→ fail-closed，
    // 不扩大扫描（扩大可能配错 turn）。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c15.db"));
    QList<RecordRow> rows;
    rows.append({161, QStringLiteral("sess-c15"), 1, userMsg(QStringLiteral("超出窗口的用户正文"))});
    for (int i = 2; i <= 65; ++i) {  // 64 行 Bot 中间行（合法 JSON，author=Bot）
        rows.append({160 + i, QStringLiteral("sess-c15"), i,
                     botStreamMsg(QStringLiteral("中间行%1").arg(i))});
    }
    rows.append({226, QStringLiteral("sess-c15"), 66, botFinalMsg(QStringLiteral("超出窗口的终稿"))});
    QVERIFY(createRecordDb(dbPath, rows));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:226")).has_value(),
             "User 行超出 64 行窗口必须 fail-closed");
}

// ── §D schema 适配 ──────────────────────────────────────────────────────────

void ProductionSourceResolverTest::customSchemaConfigResolves()  // D1
{
    // 自定义表/列/JSON 字段名/角色值（config 覆盖，不改代码）：模拟其它
    // 宿主 Chat DB 方言。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-d1.db"));
    QVERIFY(createFixtureDb(
        dbPath,
        QStringLiteral("CREATE TABLE chat_msg (mid INTEGER PRIMARY KEY, conv TEXT, "
                       "seq INTEGER, payload TEXT, ts TEXT)"),
        {QStringLiteral("INSERT INTO chat_msg VALUES (901,'conv-9',1,"
                        "'{\"role\":\"human\",\"text\":\"自定义schema的用户正文\"}','2026-09-05 12:00:00')"),
         QStringLiteral("INSERT INTO chat_msg VALUES (902,'conv-9',2,"
                        "'{\"role\":\"ai\",\"final\":true,\"text\":\"自定义schema的终稿正文\"}','2026-09-05 12:00:01')")}));

    client::ProductionSourceResolverConfig config = defaultConfig(dbPath);
    config.tableName = QStringLiteral("chat_msg");
    config.idColumn = QStringLiteral("mid");
    config.sessionColumn = QStringLiteral("conv");
    config.msgIndexColumn = QStringLiteral("seq");
    config.messageColumn = QStringLiteral("payload");
    config.authorField = QStringLiteral("role");
    config.contentField = QStringLiteral("text");
    config.isEndField = QStringLiteral("final");
    config.userAuthorValue = QStringLiteral("human");
    config.assistantAuthorValue = QStringLiteral("ai");

    client::ProductionSourceResolver resolver(config);
    QVERIFY(resolver.open());
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:902"));
    QVERIFY2(hit.has_value(), "自定义 schema 应命中");
    QCOMPARE(hit->originalUserText, QStringLiteral("自定义schema的用户正文"));
    QCOMPARE(hit->modelResponse, QStringLiteral("自定义schema的终稿正文"));
}

// ── §E 窗口边界 ─────────────────────────────────────────────────────────────

void ProductionSourceResolverTest::resolveHitsAtWindowBoundaryEdge()  // E1
{
    // User 行恰为回扫第 64 行（终稿 msgIndex=65，User msgIndex=1，
    // 中间 63 行 Bot）：LIMIT 64 恰好覆盖 User 行 → 命中。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-e1.db"));
    QList<RecordRow> rows;
    rows.append({231, QStringLiteral("sess-e1"), 1, userMsg(QStringLiteral("窗口边界的用户正文"))});
    for (int i = 2; i <= 64; ++i) {  // 63 行 Bot 中间行
        rows.append({230 + i, QStringLiteral("sess-e1"), i,
                     botStreamMsg(QStringLiteral("边界中间行%1").arg(i))});
    }
    rows.append({296, QStringLiteral("sess-e1"), 65, botFinalMsg(QStringLiteral("窗口边界的终稿"))});
    QVERIFY(createRecordDb(dbPath, rows));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:296"));
    QVERIFY2(hit.has_value(), "User 行恰在窗口边界（第 64 行）应命中");
    QCOMPARE(hit->originalUserText, QStringLiteral("窗口边界的用户正文"));
    QCOMPARE(hit->modelResponse, QStringLiteral("窗口边界的终稿"));
}

void ProductionSourceResolverTest::defaultIdColumnFailsClosedOnIdNullRows()  // E2
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-e2.db"));
    QVERIFY(createIdNullRecordDb(dbPath, {
        {0, QStringLiteral("sess-e2"), 1, userMsg(QStringLiteral("id-null user"))},
        {0, QStringLiteral("sess-e2"), 2, botFinalMsg(QStringLiteral("id-null final"))},
    }));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:2")).has_value(),
             "default ID must not treat SQLite rowid as RECORD.ID");
}

void ProductionSourceResolverTest::rowidOverrideResolvesIdNullRowsReadOnly()  // E3
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-e3.db"));
    QVERIFY(createIdNullRecordDb(dbPath, {
        {0, QStringLiteral("sess-e3"), 1, userMsg(QStringLiteral("rowid user"))},
        {0, QStringLiteral("sess-e3"), 2, botFinalMsg(QStringLiteral("rowid final"))},
    }));
    const QByteArray hashBefore = fileSha256(dbPath);
    QVERIFY(!hashBefore.isEmpty());

    client::ProductionSourceResolverConfig config = defaultConfig(dbPath);
    config.idColumn = QStringLiteral("rowid");
    client::ProductionSourceResolver resolver(config);
    QVERIFY(resolver.open());
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:2"));
    QVERIFY2(hit.has_value(), "explicit rowid override must resolve ID=NULL rows");
    QCOMPARE(hit->originalUserText, QStringLiteral("rowid user"));
    QCOMPARE(hit->modelResponse, QStringLiteral("rowid final"));
    QCOMPARE(fileSha256(dbPath), hashBefore);
}

QTEST_MAIN(ProductionSourceResolverTest)
#include "test_production_source_resolver.moc"
