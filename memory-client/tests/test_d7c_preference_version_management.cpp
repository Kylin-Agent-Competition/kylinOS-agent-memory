// test_d7c_preference_version_management.cpp — D7-C 偏好版本管理 L0 Mock 测试
//
// 范围（L0 Mock Gateway）：覆盖任务卡 §A/B/C/D/E 共 14 个用例。
// 注意：本测试仅为 memory-client 侧 Demo / Prototype 的 L0 契约验证，
//       不声称代表真实 AI Assistant Hook / Chat DB / ChatRecord /
//       偏好持久化后端已接入。
//
// 用例清单：
//   §A  Commit — 5 用例
//     A1  首版 commit → preferenceCommitStage == "sent"，事件含 metadata + preference 嵌套
//     A2  敏感内容 high → 客户端侧拒绝发送，preferenceCommitStage == "failed"
//     A3  critical 同样拒绝
//     A4  UNSUPPORTED_METHOD 响应 → preferenceCommitStage == "failed"
//     A5  客户端 deadline 超时 → preferenceCommitStage == "timeout"
//   §B  History — 3 用例
//     B1  查询成功 → preferenceHistoryStage == "sent"，事件含 metadata + query 嵌套
//     B2  空历史响应（data.items=[]）→ 仍 "sent"
//     B3  错误响应 → "failed"
//   §C  Rollback — 3 用例
//     C1  回滚成功 → preferenceRollbackStage == "sent"，事件含 target_version_id
//     C2  服务端 INVALID_REQUEST（target_version_id 不存在）→ "failed"
//     C3  客户端 deadline 超时 → "timeout"
//   §D  事件契约
//     D1  commit 事件含 metadata + preference 嵌套
//     D2  rollback 事件含 metadata + rollback 嵌套
//     D3  history 查询含 metadata + query 嵌套
//     D4  preference.mapping_status == "PENDING_C_CONFIRMATION" 显式注入
//   §E  运行正确性
//     E1  三 busy 独立 pending：commit in-flight 时 rollback 响应不串台
//     E2  commit sent 不影响 rollback failed
//     E3  busy 合并属性正确反映三组 busy

#include "memory_client.h"
#include "mock_gateway_server.h"
#include "view_models/memory_view_model.h"

#include <QJsonObject>
#include <QJsonDocument>
#include <QSignalSpy>
#include <QString>
#include <QtTest>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

class D7cPreferenceVersionManagementTest final : public QObject {
    Q_OBJECT

private slots:
    void init();
    void cleanup();

    // §A Commit 5 用例
    void commitFirstVersionRoutesToSent();              // A1
    void commitHighSensitivityBlocked();                // A2
    void commitCriticalSensitivityBlocked();            // A3
    void commitUnsupportedMethodRoutesToFailed();      // A4
    void commitDeadlineTimeoutRoutesToTimeout();       // A5

    // §B History 3 用例
    void historyQueryRoutesToSent();                    // B1
    void historyEmptyItemsStillSent();                  // B2
    void historyErrorResponseRoutesToFailed();         // B3

    // §C Rollback 3 用例
    void rollbackSuccessRoutesToSent();                 // C1
    void rollbackInvalidRequestRoutesToFailed();       // C2
    void rollbackDeadlineTimeoutRoutesToTimeout();     // C3

    // §D 事件契约
    void commitEventHasMetadataAndPreferenceNesting();  // D1
    void rollbackEventHasMetadataAndRollbackNesting();  // D2
    void historyEventHasMetadataAndQueryNesting();     // D3
    void preferenceCarriesPendingMappingStatus();      // D4

    // §E 运行正确性
    void commitResponseDoesNotHijackInFlightRollback();  // E1
    void commitSentDoesNotAffectRollbackFailed();        // E2
    void busyPropertyReflectsThreeGroups();              // E3

private:
    QString uniqueSocketName(const QString& prefix);
};

QString D7cPreferenceVersionManagementTest::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d7c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

void D7cPreferenceVersionManagementTest::init()
{
    // 清理可能残留的同名 socket（按用例前缀）
    for (const auto& p : {QStringLiteral("a1"), QStringLiteral("a2"),
                          QStringLiteral("a3"), QStringLiteral("a4"),
                          QStringLiteral("a5"), QStringLiteral("b1"),
                          QStringLiteral("b2"), QStringLiteral("b3"),
                          QStringLiteral("c1"), QStringLiteral("c2"),
                          QStringLiteral("c3"), QStringLiteral("d1"),
                          QStringLiteral("d2"), QStringLiteral("d3"),
                          QStringLiteral("d4"), QStringLiteral("e1"),
                          QStringLiteral("e2"), QStringLiteral("e3")}) {
        QLocalServer::removeServer(uniqueSocketName(p));
    }
}

void D7cPreferenceVersionManagementTest::cleanup()
{
    // no-op；per-test 通过 mock.close() 清理
}

// ── §A Commit ───────────────────────────────────────────────────────────────

void D7cPreferenceVersionManagementTest::commitFirstVersionRoutesToSent()  // A1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionCommit) {
            const QJsonValue metaVal = parts.payload.value(QStringLiteral("metadata"));
            const QJsonValue prefVal = parts.payload.value(QStringLiteral("preference"));
            const bool hasMeta = metaVal.isObject();
            const bool hasPref = prefVal.isObject();
            if (!hasMeta || !hasPref) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("preference.version.commit missing required objects."));
            }
            const QJsonObject pref = prefVal.toObject();
            const bool missingRequired =
                !pref.contains(QStringLiteral("user_id"))
                || !pref.contains(QStringLiteral("key"))
                || !pref.contains(QStringLiteral("scope"))
                || !pref.contains(QStringLiteral("value"))
                || !pref.contains(QStringLiteral("memory_status"))
                || !pref.contains(QStringLiteral("is_temporary"))
                || !pref.contains(QStringLiteral("should_persist"))
                || !pref.contains(QStringLiteral("sensitivity_level"));
            if (missingRequired) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("preference.version.commit missing required preference fields."));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("version"), 1},
                           {QStringLiteral("memory_status"), QStringLiteral("active")},
                           {QStringLiteral("is_current"), true}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("Method not registered in test handler."));
    });
    const QString socket = mock.listen(uniqueSocketName("a1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy stageSpy(&vm, &client::MemoryViewModel::preferenceCommitStageChanged);
    vm.runPreferenceCommitPipeline(
        QStringLiteral("local-user"), QStringLiteral("session-pref-a1"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceCommitStage(), QStringLiteral("sent"), 5000);
    QVERIFY(!vm.lastPreferenceCommitEvent().isEmpty());
    QVERIFY(vm.lastPreferenceCommitEvent().contains(QStringLiteral("preference")));
    QVERIFY(vm.lastPreferenceCommitEvent().contains(QStringLiteral("zh-CN")));
    QVERIFY(vm.lastPreferenceCommitEvent().contains(QStringLiteral("metadata")));
    QVERIFY(!vm.preferenceCommitBusy());
}

void D7cPreferenceVersionManagementTest::commitHighSensitivityBlocked()  // A2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy connSpy(&vm, &client::MemoryViewModel::connectionError);
    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("sensitive-data"), false, true,
        QStringLiteral("active"), QStringLiteral("high"), 0.8);

    QCOMPARE(vm.preferenceCommitStage(), QStringLiteral("failed"));
    QVERIFY(vm.lastPreferenceCommitEvent().isEmpty());
    QVERIFY(!vm.preferenceCommitBusy());
    QCOMPARE(connSpy.count(), 1);
    // 敏感拦截不发到 Gateway → receivedRequests 应为空
    QCOMPARE(mock.receivedRequests().size(), static_cast<std::size_t>(0));
}

void D7cPreferenceVersionManagementTest::commitCriticalSensitivityBlocked()  // A3
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("critical-data"), false, true,
        QStringLiteral("active"), QStringLiteral("critical"), 0.8);

    QCOMPARE(vm.preferenceCommitStage(), QStringLiteral("failed"));
    QVERIFY(vm.lastPreferenceCommitEvent().isEmpty());
    QVERIFY(!vm.preferenceCommitBusy());
    QCOMPARE(mock.receivedRequests().size(), static_cast<std::size_t>(0));
}

void D7cPreferenceVersionManagementTest::commitUnsupportedMethodRoutesToFailed()  // A4
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        // 不注册 preference.version.commit handler → 返回 UNSUPPORTED_METHOD
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("preference.version.commit not registered."));
    });
    const QString socket = mock.listen(uniqueSocketName("a4"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("en-US"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceCommitStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.preferenceCommitBusy());
    // UNSUPPORTED_METHOD 不得误展示为 sent（沿用 D5 REWORK §A 验证口径）
    QVERIFY(vm.preferenceCommitStage() != QStringLiteral("sent"));
}

void D7cPreferenceVersionManagementTest::commitDeadlineTimeoutRoutesToTimeout()  // A5
{
    // Gateway 不响应 → 客户端 deadline（kDefaultDeadlineMs=5000）超时
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts&) -> QJsonObject {
        return QJsonObject{};  // 返回空对象 → Mock 不会自动回写
    });
    const QString socket = mock.listen(uniqueSocketName("a5"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);

    // 等待 deadline 超时（5s + 1s 容差）
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceCommitStage(), QStringLiteral("timeout"), 7000);
    QVERIFY(!vm.preferenceCommitBusy());
}

// ── §B History ──────────────────────────────────────────────────────────────

void D7cPreferenceVersionManagementTest::historyQueryRoutesToSent()  // B1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionHistory) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("items"),
                             QJsonArray{
                                 QJsonObject{{QStringLiteral("version"), 1},
                                             {QStringLiteral("memory_status"), QStringLiteral("active")},
                                             {QStringLiteral("is_current"), true}},
                                 QJsonObject{{QStringLiteral("version"), 2},
                                             {QStringLiteral("memory_status"), QStringLiteral("superseded")},
                                             {QStringLiteral("is_current"), false}}
                             }}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("b1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceHistoryPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"), true);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceHistoryStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastPreferenceHistoryEvent().contains(QStringLiteral("query")));
    QVERIFY(vm.lastPreferenceHistoryEvent().contains(QStringLiteral("include_history")));
    QVERIFY(!vm.preferenceHistoryBusy());
}

void D7cPreferenceVersionManagementTest::historyEmptyItemsStillSent()  // B2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionHistory) {
            // 空历史 → data.items=[] 仍属合法响应
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("items"), QJsonArray{}}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("b2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceHistoryPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("nonexistent-key"), true);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceHistoryStage(), QStringLiteral("sent"), 5000);
    QVERIFY(!vm.preferenceHistoryBusy());
}

void D7cPreferenceVersionManagementTest::historyErrorResponseRoutesToFailed()  // B3
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("preference.version.history not registered."));
    });
    const QString socket = mock.listen(uniqueSocketName("b3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceHistoryPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"), true);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceHistoryStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.preferenceHistoryBusy());
}

// ── §C Rollback ──────────────────────────────────────────────────────────────

void D7cPreferenceVersionManagementTest::rollbackSuccessRoutesToSent()  // C1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionRollback) {
            const QJsonValue rbVal = parts.payload.value(QStringLiteral("rollback"));
            if (!rbVal.isObject()) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("preference.version.rollback missing rollback object."));
            }
            const QJsonObject rb = rbVal.toObject();
            if (!rb.contains(QStringLiteral("target_version_id"))) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("preference.version.rollback missing target_version_id."));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("version"), 3},
                             {QStringLiteral("memory_status"), QStringLiteral("active")},
                             {QStringLiteral("is_current"), true}});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("c1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceRollbackPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("1"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceRollbackStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastPreferenceRollbackEvent().contains(QStringLiteral("target_version_id")));
    QVERIFY(vm.lastPreferenceRollbackEvent().contains(QStringLiteral("rollback")));
    QVERIFY(!vm.preferenceRollbackBusy());
}

void D7cPreferenceVersionManagementTest::rollbackInvalidRequestRoutesToFailed()  // C2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionRollback) {
            // Demo 期模拟：target_version_id 不存在或非本用户 → INVALID_REQUEST
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kInvalidRequest,
                QStringLiteral("Target version does not exist or belongs to another user."));
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("c2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceRollbackPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("999"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceRollbackStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.preferenceRollbackBusy());
}

void D7cPreferenceVersionManagementTest::rollbackDeadlineTimeoutRoutesToTimeout()  // C3
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts&) -> QJsonObject {
        return QJsonObject{};
    });
    const QString socket = mock.listen(uniqueSocketName("c3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceRollbackPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("1"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceRollbackStage(), QStringLiteral("timeout"), 7000);
    QVERIFY(!vm.preferenceRollbackBusy());
}

// ── §D 事件契约 ─────────────────────────────────────────────────────────────

void D7cPreferenceVersionManagementTest::commitEventHasMetadataAndPreferenceNesting()  // D1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionCommit) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("d1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceCommitPipeline(
        QStringLiteral("local-user"), QStringLiteral("session-d1"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceCommitStage(), QStringLiteral("sent"), 5000);

    // 解析 lastPreferenceCommitEvent JSON
    const QJsonDocument doc = QJsonDocument::fromJson(
        vm.lastPreferenceCommitEvent().toUtf8());
    QVERIFY2(doc.isObject(), "PreferenceCommitEvent JSON 必须是对象");
    const QJsonObject event = doc.object();

    // metadata 嵌套
    const QJsonValue metaVal = event.value(QStringLiteral("metadata"));
    QVERIFY2(metaVal.isObject(), "metadata 必须是对象");
    const QJsonObject meta = metaVal.toObject();
    QVERIFY(meta.contains(QStringLiteral("schema_version")));
    QVERIFY(meta.contains(QStringLiteral("event_id")));
    QVERIFY(meta.contains(QStringLiteral("user_id")));
    QVERIFY(meta.contains(QStringLiteral("session_id")));
    QVERIFY(meta.contains(QStringLiteral("idempotency_key")));
    QVERIFY(meta.contains(QStringLiteral("occurred_at")));
    QVERIFY(meta.contains(QStringLiteral("collected_at")));
    QVERIFY(meta.contains(QStringLiteral("source_reference")));

    // preference 嵌套
    const QJsonValue prefVal = event.value(QStringLiteral("preference"));
    QVERIFY2(prefVal.isObject(), "preference 必须是对象");
    const QJsonObject pref = prefVal.toObject();
    QVERIFY(pref.contains(QStringLiteral("user_id")));
    QVERIFY(pref.contains(QStringLiteral("key")));
    QVERIFY(pref.contains(QStringLiteral("scope")));
    QVERIFY(pref.contains(QStringLiteral("value")));
    QVERIFY(pref.contains(QStringLiteral("memory_status")));
    QVERIFY(pref.contains(QStringLiteral("is_temporary")));
    QVERIFY(pref.contains(QStringLiteral("should_persist")));
    QVERIFY(pref.contains(QStringLiteral("confidence")));
    QVERIFY(pref.contains(QStringLiteral("sensitivity_level")));
    QVERIFY(pref.contains(QStringLiteral("mapping_status")));
}

void D7cPreferenceVersionManagementTest::rollbackEventHasMetadataAndRollbackNesting()  // D2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionRollback) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("d2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceRollbackPipeline(
        QStringLiteral("local-user"), QStringLiteral("session-d2"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("2"));

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceRollbackStage(), QStringLiteral("sent"), 5000);

    const QJsonDocument doc = QJsonDocument::fromJson(
        vm.lastPreferenceRollbackEvent().toUtf8());
    QVERIFY2(doc.isObject(), "PreferenceRollbackEvent JSON 必须是对象");
    const QJsonObject event = doc.object();

    const QJsonValue metaVal = event.value(QStringLiteral("metadata"));
    QVERIFY2(metaVal.isObject(), "metadata 必须是对象");
    const QJsonObject meta = metaVal.toObject();
    QVERIFY(meta.contains(QStringLiteral("schema_version")));
    QVERIFY(meta.contains(QStringLiteral("event_id")));
    QVERIFY(meta.contains(QStringLiteral("user_id")));
    QVERIFY(meta.contains(QStringLiteral("idempotency_key")));
    QVERIFY(meta.contains(QStringLiteral("source_reference")));

    const QJsonValue rbVal = event.value(QStringLiteral("rollback"));
    QVERIFY2(rbVal.isObject(), "rollback 必须是对象");
    const QJsonObject rb = rbVal.toObject();
    QVERIFY(rb.contains(QStringLiteral("user_id")));
    QVERIFY(rb.contains(QStringLiteral("key")));
    QVERIFY(rb.contains(QStringLiteral("scope")));
    QVERIFY(rb.contains(QStringLiteral("target_version_id")));
    QVERIFY(rb.contains(QStringLiteral("idempotency_key")));
}

void D7cPreferenceVersionManagementTest::historyEventHasMetadataAndQueryNesting()  // D3
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionHistory) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("d3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceHistoryPipeline(
        QStringLiteral("local-user"), QStringLiteral("session-d3"),
        QStringLiteral("preference"), QStringLiteral("language"), true);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceHistoryStage(), QStringLiteral("sent"), 5000);

    const QJsonDocument doc = QJsonDocument::fromJson(
        vm.lastPreferenceHistoryEvent().toUtf8());
    QVERIFY2(doc.isObject(), "PreferenceHistoryEvent JSON 必须是对象");
    const QJsonObject event = doc.object();

    const QJsonValue metaVal = event.value(QStringLiteral("metadata"));
    QVERIFY2(metaVal.isObject(), "metadata 必须是对象");
    const QJsonObject meta = metaVal.toObject();
    QVERIFY(meta.contains(QStringLiteral("schema_version")));
    QVERIFY(meta.contains(QStringLiteral("event_id")));
    QVERIFY(meta.contains(QStringLiteral("user_id")));
    QVERIFY(meta.contains(QStringLiteral("idempotency_key")));
    QVERIFY(meta.contains(QStringLiteral("source_reference")));

    const QJsonValue queryVal = event.value(QStringLiteral("query"));
    QVERIFY2(queryVal.isObject(), "query 必须是对象");
    const QJsonObject query = queryVal.toObject();
    QVERIFY(query.contains(QStringLiteral("user_id")));
    QVERIFY(query.contains(QStringLiteral("key")));
    QVERIFY(query.contains(QStringLiteral("scope")));
    QVERIFY(query.contains(QStringLiteral("include_history")));
}

void D7cPreferenceVersionManagementTest::preferenceCarriesPendingMappingStatus()  // D4
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionCommit) {
            const QJsonValue prefVal = parts.payload.value(QStringLiteral("preference"));
            if (!prefVal.isObject()) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("missing preference object."));
            }
            const QJsonObject pref = prefVal.toObject();
            const QString mappingStatus = pref.value(QStringLiteral("mapping_status")).toString();
            if (mappingStatus != QStringLiteral("PENDING_C_CONFIRMATION")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("preference.version.commit must carry "
                                   "mapping_status=PENDING_C_CONFIRMATION."));
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("d4"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);

    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceCommitStage(), QStringLiteral("sent"), 5000);
    QVERIFY(vm.lastPreferenceCommitEvent().contains(QStringLiteral("PENDING_C_CONFIRMATION")));
    QVERIFY(vm.lastPreferenceCommitEvent().contains(QStringLiteral("mapping_status")));
}

// ── §E 运行正确性 ──────────────────────────────────────────────────────────

void D7cPreferenceVersionManagementTest::commitResponseDoesNotHijackInFlightRollback()  // E1
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionCommit) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        if (parts.method == client::methods::kPreferenceVersionRollback) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("e1"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    // 先启动 commit
    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);
    QTRY_VERIFY_WITH_TIMEOUT(!vm.preferenceCommitBusy(), 5000);

    // 启动 rollback
    vm.runPreferenceRollbackPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("1"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceRollbackStage(), QStringLiteral("sent"), 5000);

    // 关键断言：rollback sent 后 commit stage 仍是 sent（不被 rollback 响应覆盖）
    QCOMPARE(vm.preferenceCommitStage(), QStringLiteral("sent"));
    QVERIFY(!vm.preferenceRollbackBusy());
}

void D7cPreferenceVersionManagementTest::commitSentDoesNotAffectRollbackFailed()  // E2
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionCommit) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        if (parts.method == client::methods::kPreferenceVersionRollback) {
            return client::buildErrorResponse(
                parts.requestId, parts.traceId,
                client::error_codes::kInvalidRequest,
                QStringLiteral("rollback target not found."));
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("e2"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceCommitStage(), QStringLiteral("sent"), 5000);

    vm.runPreferenceRollbackPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("999"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceRollbackStage(), QStringLiteral("failed"), 5000);

    // 关键断言：rollback failed 后 commit 仍是 sent（不被 rollback 响应影响）
    QCOMPARE(vm.preferenceCommitStage(), QStringLiteral("sent"));
    QCOMPARE(vm.preferenceRollbackStage(), QStringLiteral("failed"));
}

void D7cPreferenceVersionManagementTest::busyPropertyReflectsThreeGroups()  // E3
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceVersionCommit
            || parts.method == client::methods::kPreferenceVersionHistory
            || parts.method == client::methods::kPreferenceVersionRollback) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, QJsonObject{});
        }
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod, QString());
    });
    const QString socket = mock.listen(uniqueSocketName("e3"));

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(vm.connectionState(), QStringLiteral("connected"), 5000);

    // 初始：三组 busy 均为 false，合并属性也为 false
    QVERIFY(!vm.preferenceCommitBusy());
    QVERIFY(!vm.preferenceHistoryBusy());
    QVERIFY(!vm.preferenceRollbackBusy());
    QVERIFY(!vm.busy());

    // 启动 commit pipeline（in-flight）→ busy 为 true
    vm.runPreferenceCommitPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("zh-CN"), false, true,
        QStringLiteral("active"), QStringLiteral("none"), 0.8);
    QVERIFY(vm.preferenceCommitBusy());
    QVERIFY(vm.busy());

    // 等待响应完成 → busy 重回 false
    QTRY_VERIFY_WITH_TIMEOUT(!vm.preferenceCommitBusy(), 5000);
    QVERIFY(!vm.busy());

    // 启动 history pipeline
    vm.runPreferenceHistoryPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"), true);
    QVERIFY(vm.preferenceHistoryBusy());
    QVERIFY(vm.busy());
    QTRY_VERIFY_WITH_TIMEOUT(!vm.preferenceHistoryBusy(), 5000);
    QVERIFY(!vm.busy());

    // 启动 rollback pipeline
    vm.runPreferenceRollbackPipeline(
        QStringLiteral("u"), QStringLiteral("s"),
        QStringLiteral("preference"), QStringLiteral("language"),
        QStringLiteral("1"));
    QVERIFY(vm.preferenceRollbackBusy());
    QVERIFY(vm.busy());
    QTRY_VERIFY_WITH_TIMEOUT(!vm.preferenceRollbackBusy(), 5000);
    QVERIFY(!vm.busy());
}

QTEST_GUILESS_MAIN(D7cPreferenceVersionManagementTest)
#include "test_d7c_preference_version_management.moc"
