// test_production_source_resolver.cpp — Host mapping 任务卡 S2 L0 契约测试
//
// 范围（fixture SQLite 模拟宿主 Chat DB；生产注册仍 BLOCKED_BY_HOST_MAPPING）：
//   §A 只读打开与命中
//     A1 open() 成功 + isOpen
//     A2 resolve 命中：originalUserText（同 turn 用户消息）+ modelResponse
//        （终稿 assistant 消息）+ modelRequest 留空（不编造）
//     A3 与 TurnExtractionAdapter 集成：Extracted 状态、正文仅入
//        providerCandidate、ipcEvent 序列化不含正文（原文隔离红线）
//   §B 只读红线
//     B1 chmod 0444 只读文件仍可打开并命中（证明 QSQLITE_OPEN_READONLY
//        生效：若以读写模式打开 0444 文件会 SQLITE_CANTOPEN）[POSIX]
//     B2 resolve 前后 DB 文件 SHA-256 不变（绝不写宿主 DB）
//   §C fail-closed（一律 nullopt，禁止编造正文）
//     C1 未 open() 即 resolve
//     C2 DB 文件不存在 → open() false
//     C3 chmod 000 不可读 → open() false [POSIX，root 下跳过]
//     C4 表缺失（SQLite 惰性打开，open 成功但 resolve 未命中）
//     C5 行缺失（message_id 无对应行）
//     C6 同 turn 无用户消息
//     C7 用户消息正文为空串（NOT NULL 冻结语义）
//     C8 终稿消息 role 非 assistant（被误指为终稿的用户消息）
//     C9 非受控引用格式（空串/无前缀/错误前缀/空 id/大小写不符/前导空格）
//     C10 config 标识符非法（SQL 注入防御）→ open() false
//   §D schema 适配（VM 确认真实 schema 后经 config 覆盖，不改代码）
//     D1 自定义表/列/角色值命中
//
// 依赖：Qt5 Sql QSQLITE 驱动（CI 已装 libqt5sql5-sqlite；缺失时本测试
//       失败而非跳过——L0 全绿必须意味着只读/fail-closed 行为真实验证）。
//
// 注意：本测试仅为 S2 生产 resolver 的 L0 契约验证（fixture SQLite 模拟），
//       不声称真实宿主 Chat DB 已接入（生产状态保持 BLOCKED_BY_HOST_MAPPING，
//       真实 schema 在麒麟 VM 从 kylin-aiassistant 源码确认后经 config 适配）。

#include "adapters/memory_source_resolver.h"
#include "adapters/production_source_resolver.h"
#include "adapters/turn_extraction_adapter.h"

#include <QCryptographicHash>
#include <QFile>
#include <QJsonDocument>
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

// 默认 schema fixture（S2 假设默认值）：
//   chat_record(message_id, turn_id, role, content)
// 数据设计：
//   turn-1  完整命中（user + assistant 终稿）
//   turn-2  仅 assistant（无用户消息）→ C6
//   turn-3  用户消息正文空串 → C7
//   turn-4  用户消息被误指为终稿 → C8
constexpr const char kDefaultCreateSql[] =
    "CREATE TABLE chat_record ("
    "message_id TEXT PRIMARY KEY, turn_id TEXT, role TEXT, content TEXT)";
constexpr const char* kDefaultInsertSqls[] = {
    "INSERT INTO chat_record VALUES ('msg-user-1','turn-1','user','用户真实提问正文')",
    "INSERT INTO chat_record VALUES ('msg-asst-1','turn-1','assistant','助手终稿正文')",
    "INSERT INTO chat_record VALUES ('msg-asst-2','turn-2','assistant','无用户消息的终稿')",
    "INSERT INTO chat_record VALUES ('msg-user-3','turn-3','user','')",
    "INSERT INTO chat_record VALUES ('msg-asst-3','turn-3','assistant','空用户正文的终稿')",
    "INSERT INTO chat_record VALUES ('msg-user-4','turn-4','user','被误指为终稿的用户消息')",
    "INSERT INTO chat_record VALUES ('msg-user-5','turn-5','user','第二条完整turn的用户正文')",
    "INSERT INTO chat_record VALUES ('msg-asst-5','turn-5','assistant','第二条完整turn的终稿')",
};

// 用 QSQLITE 写模式创建 fixture（仅测试用；resolver 自身只读打开）。
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

}  // namespace

class ProductionSourceResolverTest final : public QObject {
    Q_OBJECT

private slots:
    // §A 只读打开与命中
    void openSucceedsOnReadableDatabase();          // A1
    void resolveHitsReturnsTurnContent();           // A2
    void resolveThroughTurnExtractionAdapter();     // A3

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
    void failClosedWhenFinalMessageNotAssistant();  // C8
    void failClosedOnNonControlledReferenceFormats();  // C9
    void invalidIdentifierConfigFailsOpen();        // C10

    // §D schema 适配
    void customSchemaConfigResolves();              // D1

private:
    QTemporaryDir tempDir_;
};

// ── §A 只读打开与命中 ────────────────────────────────────────────────────────

void ProductionSourceResolverTest::openSucceedsOnReadableDatabase()  // A1
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a1.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));
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
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());

    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1"));
    QVERIFY2(hit.has_value(), "受控引用应命中");
    QCOMPARE(hit->originalUserText, QStringLiteral("用户真实提问正文"));
    QCOMPARE(hit->modelResponse, QStringLiteral("助手终稿正文"));
    QCOMPARE(hit->modelRequest, QString());  // 宿主 Chat DB 不提供，不编造
}

void ProductionSourceResolverTest::resolveThroughTurnExtractionAdapter()  // A3
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-a3.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());

    client::TurnObservation obs;
    obs.userId = QStringLiteral("user-l0");
    obs.sessionId = QStringLiteral("sess-s2-1");
    obs.turnId = QStringLiteral("turn-1");
    obs.finalMessageId = QStringLiteral("msg-asst-1");  // → ref:chat-record:msg-asst-1
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

// ── §B 只读红线 ─────────────────────────────────────────────────────────────

void ProductionSourceResolverTest::readonlyOpenWorksOnWriteProtectedFile()  // B1
{
#ifdef Q_OS_UNIX
    if (::getuid() == 0) {
        QSKIP("root 用户下 chmod 权限位不生效，无法验证只读打开语义");
    }
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-b1.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));
    QVERIFY(::chmod(dbPath.toUtf8().constData(), 0444) == 0);

    // 0444 文件：只读打开必须成功（写保护不阻碍受控读取）。
    // 注：SQLite 对写保护文件存在 OS 层只读回退，故本用例不能单独证明
    // READONLY 标志本身——标志的回归证明是 C2 的"失败后不建库"断言
    // 与 B2 的"resolve 前后文件哈希不变"。
    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY2(resolver.open(), "只读模式应可打开 0444 文件（受控读取不受写保护阻碍）");
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1"));
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
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    const QByteArray hashBefore = fileSha256(dbPath);
    QVERIFY(!hashBefore.isEmpty());

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY(resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1")).has_value());
    QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:no-such")).has_value());
    QVERIFY(resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-5")).has_value());

    QCOMPARE(fileSha256(dbPath), hashBefore);  // 绝不写宿主 DB（含 journal/wal）
}

// ── §C fail-closed ──────────────────────────────────────────────────────────

void ProductionSourceResolverTest::failClosedWhenNotOpened()  // C1
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c1.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(!resolver.isOpen());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1")).has_value(),
             "未 open() 必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnMissingDatabaseFile()  // C2
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("nonexistent.db"));
    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY2(!resolver.open(), "文件不存在时 open() 必须失败");
    QVERIFY(!resolver.isOpen());
    QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1")).has_value());
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
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));
    QVERIFY(::chmod(dbPath.toUtf8().constData(), 0000) == 0);

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY2(!resolver.open(), "chmod 000 不可读文件 open() 必须失败（无权限 fail-closed）");
    QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1")).has_value());

    ::chmod(dbPath.toUtf8().constData(), 0644);  // 恢复，便于临时目录清理
#else
    QSKIP("chmod 不可读权限位验证仅限 POSIX（Unix）平台");
#endif
}

void ProductionSourceResolverTest::failClosedOnMissingTable()  // C4
{
    // SQLite 惰性打开：无表的 DB 文件 open() 成功，resolve 时表缺失 → fail-closed。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c4.db"));
    QVERIFY(createFixtureDb(dbPath, QStringLiteral("CREATE TABLE unrelated (x TEXT)"),
                            {QStringLiteral("INSERT INTO unrelated VALUES ('y')")}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());  // 文件合法 SQLite，打开成功
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1")).has_value(),
             "表缺失必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnMissingRow()  // C5
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c5.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:no-such-msg")).has_value(),
             "行缺失必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedWhenTurnHasNoUserMessage()  // C6
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c6.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    // turn-2 仅有 assistant 消息，无同 turn 用户消息。
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-2")).has_value(),
             "同 turn 无用户消息必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnEmptyUserText()  // C7
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c7.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    // turn-3 用户消息正文为空串 → 视为未命中（NOT NULL 冻结语义，禁止空串替代）。
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-3")).has_value(),
             "用户正文空串必须视为未命中");
}

void ProductionSourceResolverTest::failClosedWhenFinalMessageNotAssistant()  // C8
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c8.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());
    // msg-user-4 是 user 角色行：不得作为终稿消息解析（fail-closed，不编造）。
    QVERIFY2(!resolver.resolve(QStringLiteral("ref:chat-record:msg-user-4")).has_value(),
             "终稿消息 role 非 assistant 必须 fail-closed");
}

void ProductionSourceResolverTest::failClosedOnNonControlledReferenceFormats()  // C9
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c9.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    client::ProductionSourceResolver resolver(defaultConfig(dbPath));
    QVERIFY(resolver.open());

    const QStringList nonControlledRefs = {
        QString(),                                            // 空串
        QStringLiteral("msg-asst-1"),                         // 无前缀
        QStringLiteral("ref://turn/msg-asst-1"),              // 非受控前缀（test profile 格式）
        QStringLiteral("ref:chat-record:"),                   // 前缀后空 id
        QStringLiteral("REF:CHAT-RECORD:msg-asst-1"),         // 大小写不符（大小写敏感）
        QStringLiteral(" ref:chat-record:msg-asst-1"),        // 前导空格
        QStringLiteral("ref:chat-record:msg-asst-1 extra"),   // 后缀污染
    };
    for (const QString& ref : nonControlledRefs) {
        QVERIFY2(!resolver.resolve(ref).has_value(),
                 "非受控引用格式必须 fail-closed（引用本身不记录）");
    }
}

void ProductionSourceResolverTest::invalidIdentifierConfigFailsOpen()  // C10
{
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-c10.db"));
    QVERIFY(createFixtureDb(dbPath, QString::fromLatin1(kDefaultCreateSql),
                            QList<QString>{std::begin(kDefaultInsertSqls), std::end(kDefaultInsertSqls)}));

    const QList<QString> maliciousIdentifiers = {
        QStringLiteral("chat_record; DROP TABLE chat_record"),  // SQL 注入
        QStringLiteral("chat-record"),                          // 连字符
        QStringLiteral("`chat_record`"),                        // 反引号
        QStringLiteral("chat\"record"),                         // 引号
        QStringLiteral(""),                                     // 空表名
    };
    for (const QString& bad : maliciousIdentifiers) {
        client::ProductionSourceResolverConfig config = defaultConfig(dbPath);
        config.tableName = bad;
        client::ProductionSourceResolver resolver(config);
        QVERIFY2(!resolver.open(), "非法标识符 config 必须 open() 失败（fail-closed）");
        QVERIFY(!resolver.resolve(QStringLiteral("ref:chat-record:msg-asst-1")).has_value());
    }
}

// ── §D schema 适配 ──────────────────────────────────────────────────────────

void ProductionSourceResolverTest::customSchemaConfigResolves()  // D1
{
    // 模拟 VM 确认后的真实 schema：表/列名与角色值均与默认假设不同。
    const QString dbPath = tempDir_.filePath(QStringLiteral("chat-d1.db"));
    QVERIFY(createFixtureDb(
        dbPath,
        QStringLiteral("CREATE TABLE messages (mid TEXT PRIMARY KEY, tid TEXT, role TEXT, body TEXT)"),
        {QStringLiteral("INSERT INTO messages VALUES ('u-9','t-9','human','自定义schema的用户正文')"),
         QStringLiteral("INSERT INTO messages VALUES ('a-9','t-9','ai','自定义schema的终稿正文')")}));

    client::ProductionSourceResolverConfig config = defaultConfig(dbPath);
    config.tableName = QStringLiteral("messages");
    config.messageIdColumn = QStringLiteral("mid");
    config.turnIdColumn = QStringLiteral("tid");
    config.roleColumn = QStringLiteral("role");
    config.contentColumn = QStringLiteral("body");
    config.userRoleValue = QStringLiteral("human");
    config.assistantRoleValue = QStringLiteral("ai");

    client::ProductionSourceResolver resolver(config);
    QVERIFY(resolver.open());
    const std::optional<client::ResolvedTurnContent> hit =
        resolver.resolve(QStringLiteral("ref:chat-record:a-9"));
    QVERIFY2(hit.has_value(), "自定义 schema 应命中");
    QCOMPARE(hit->originalUserText, QStringLiteral("自定义schema的用户正文"));
    QCOMPARE(hit->modelResponse, QStringLiteral("自定义schema的终稿正文"));
}

QTEST_MAIN(ProductionSourceResolverTest)
#include "test_production_source_resolver.moc"
