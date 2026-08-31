// test_d7c_preference_editor.cpp — D7C 偏好编辑 UI 的 L0 Mock 契约测试
//
// 范围（L0 Mock Gateway）：覆盖 MemoryViewModel 偏好 IPC 方法
// （preference.list/create/update/rollback/history）的 payload 形状与响应路由。
// 注意：本测试仅为 memory-client 侧 L0 契约验证，不代表真实银河麒麟 VM
//       宿主交互验收（L2 需在 VM 上另行执行）。
//
// 用例：
//   P1  loadPreferences → preference.list payload（user_id/include_history）
//       → preferenceItems 填充
//   P2  createPreference → preference.create payload 形状 → lastPreferenceAction
//   P3  updatePreference → preference.update payload（new_value）→ action=update
//   P4  rollbackPreference → preference.rollback payload（target_version）
//       → action=rollback + preferenceHistory 填充
//   P5  loadPreferenceHistory → preference.history payload → preferenceHistory 填充
//   P6  status=error → preferenceStage=failed + preferenceError + requestFailed

#include "memory_client.h"
#include "mock_gateway_server.h"
#include "view_models/memory_view_model.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QtTest>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

class D7cPreferenceEditorTest final : public QObject {
    Q_OBJECT

private slots:
    void loadPreferencesSendsListAndPopulatesItems();          // P1
    void createPreferenceSendsPayloadAndReportsAction();       // P2
    void updatePreferenceSendsNewValuePayload();               // P3
    void rollbackPreferenceSendsTargetVersionAndHistory();     // P4
    void loadHistorySendsKeyScopeAndPopulatesHistory();        // P5
    void errorResponseRoutesPreferenceToFailed();              // P6

private:
    QString uniqueSocketName(const QString& prefix);
};

QString D7cPreferenceEditorTest::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d7c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

void D7cPreferenceEditorTest::loadPreferencesSendsListAndPopulatesItems()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceList) {
            // 校验 payload 形状：user_id 必填，include_history 可选布尔
            if (parts.payload.value(QStringLiteral("user_id")).toString()
                    != QStringLiteral("u1")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad user_id"));
            }
            QJsonObject current{
                {QStringLiteral("preference_version_id"), 1},
                {QStringLiteral("version"), 1},
                {QStringLiteral("preference_value"), QStringLiteral("中文")},
                {QStringLiteral("memory_status"), QStringLiteral("active")},
                {QStringLiteral("is_current"), true},
            };
            QJsonArray items;
            items.append(QJsonObject{
                {QStringLiteral("memory_item_id"), 1},
                {QStringLiteral("preference_key"), QStringLiteral("response.language")},
                {QStringLiteral("preference_scope"), QStringLiteral("global")},
                {QStringLiteral("current"), current},
            });
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("items"), items}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("p1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.loadPreferences(QStringLiteral("u1"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.preferenceItems().size(), 1);
    const QVariantMap first = vm.preferenceItems().at(0).toMap();
    QCOMPARE(first.value(QStringLiteral("preference_key")).toString(),
             QStringLiteral("response.language"));

    // 服务端应收到带 include_history=false 的 preference.list 请求
    QVERIFY(!mock.receivedRequests().empty());
    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kPreferenceList);
    QCOMPARE(req.payload.value(QStringLiteral("include_history")).toBool(), false);
    mock.close();
}

void D7cPreferenceEditorTest::createPreferenceSendsPayloadAndReportsAction()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceCreate) {
            // payload 形状：key/scope/value + 临时/持久化标志 + 幂等键
            if (parts.payload.value(QStringLiteral("preference_key")).toString()
                    != QStringLiteral("response.language")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad key"));
            }
            if (!parts.payload.value(QStringLiteral("is_temporary")).toBool()
                || parts.payload.value(QStringLiteral("should_persist")).toBool()) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad temp flags"));
            }
            QJsonObject item{
                {QStringLiteral("preference_version_id"), 1},
                {QStringLiteral("version"), 1},
                {QStringLiteral("preference_value"), QStringLiteral("中文")},
                {QStringLiteral("memory_status"), QStringLiteral("candidate")},
                {QStringLiteral("is_current"), true},
            };
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{
                    {QStringLiteral("item"), item},
                    {QStringLiteral("created"), true},
                    {QStringLiteral("action"), QStringLiteral("create")},
                });
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("p2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.createPreference(QStringLiteral("u1"),
                        QStringLiteral("response.language"),
                        QStringLiteral("global"),
                        QStringLiteral("中文"),
                        true,   // isTemporary
                        false,  // shouldPersist
                        QStringLiteral("idem-1"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.lastPreferenceAction(), QStringLiteral("create"));
    QCOMPARE(vm.lastPreferenceItem().value(QStringLiteral("version")).toInt(), 1);

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kPreferenceCreate);
    QCOMPARE(req.payload.value(QStringLiteral("idempotency_key")).toString(),
             QStringLiteral("idem-1"));
    mock.close();
}

void D7cPreferenceEditorTest::updatePreferenceSendsNewValuePayload()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceUpdate) {
            if (parts.payload.value(QStringLiteral("new_value")).toString()
                    != QStringLiteral("英文")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad new_value"));
            }
            // HIGH-01：update payload 必须显式携带生命周期标志，防止临时偏好缺省晋升 active。
            if (!parts.payload.value(QStringLiteral("is_temporary")).isBool()
                || !parts.payload.value(QStringLiteral("should_persist")).isBool()) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("missing lifecycle flags"));
            }
            QJsonObject item{
                {QStringLiteral("preference_version_id"), 2},
                {QStringLiteral("version"), 2},
                {QStringLiteral("preference_value"), QStringLiteral("英文")},
                {QStringLiteral("memory_status"), QStringLiteral("active")},
                {QStringLiteral("is_current"), true},
            };
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{
                    {QStringLiteral("item"), item},
                    {QStringLiteral("created"), true},
                    {QStringLiteral("action"), QStringLiteral("update")},
                });
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("p3"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.updatePreference(QStringLiteral("u1"),
                        QStringLiteral("response.language"),
                        QStringLiteral("global"),
                        QStringLiteral("英文"),
                        false,   // isTemporary
                        true,    // shouldPersist
                        QStringLiteral("idem-2"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.lastPreferenceAction(), QStringLiteral("update"));

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kPreferenceUpdate);
    QCOMPARE(req.payload.value(QStringLiteral("new_value")).toString(),
             QStringLiteral("英文"));
    QCOMPARE(req.payload.value(QStringLiteral("is_temporary")).toBool(), false);
    QCOMPARE(req.payload.value(QStringLiteral("should_persist")).toBool(), true);
    mock.close();
}

void D7cPreferenceEditorTest::rollbackPreferenceSendsTargetVersionAndHistory()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceRollback) {
            if (parts.payload.value(QStringLiteral("target_version")).toInt() != 1) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad target_version"));
            }
            QJsonObject item{
                {QStringLiteral("preference_version_id"), 3},
                {QStringLiteral("version"), 3},
                {QStringLiteral("preference_value"), QStringLiteral("中文")},
                {QStringLiteral("memory_status"), QStringLiteral("active")},
                {QStringLiteral("is_current"), true},
            };
            QJsonArray history;
            history.append(QJsonObject{
                {QStringLiteral("version"), 1},
                {QStringLiteral("preference_value"), QStringLiteral("中文")},
                {QStringLiteral("is_current"), false},
            });
            history.append(QJsonObject{
                {QStringLiteral("version"), 2},
                {QStringLiteral("preference_value"), QStringLiteral("英文")},
                {QStringLiteral("is_current"), false},
            });
            history.append(QJsonObject{
                {QStringLiteral("version"), 3},
                {QStringLiteral("preference_value"), QStringLiteral("中文")},
                {QStringLiteral("is_current"), true},
            });
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{
                    {QStringLiteral("item"), item},
                    {QStringLiteral("created"), true},
                    {QStringLiteral("action"), QStringLiteral("rollback")},
                    {QStringLiteral("history"), history},
                });
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("p4"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.rollbackPreference(QStringLiteral("u1"),
                          QStringLiteral("response.language"),
                          QStringLiteral("global"),
                          1,
                          QStringLiteral("idem-3"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceStage(), QStringLiteral("rolled_back"), 5000);
    QCOMPARE(vm.lastPreferenceAction(), QStringLiteral("rollback"));
    QCOMPARE(vm.preferenceHistory().size(), 3);

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kPreferenceRollback);
    QCOMPARE(req.payload.value(QStringLiteral("target_version")).toInt(), 1);
    mock.close();
}

void D7cPreferenceEditorTest::loadHistorySendsKeyScopeAndPopulatesHistory()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kPreferenceHistory) {
            if (parts.payload.value(QStringLiteral("preference_key")).toString()
                    != QStringLiteral("response.language")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad key"));
            }
            QJsonArray items;
            items.append(QJsonObject{
                {QStringLiteral("version"), 1},
                {QStringLiteral("preference_value"), QStringLiteral("中文")},
                {QStringLiteral("memory_status"), QStringLiteral("superseded")},
                {QStringLiteral("is_current"), false},
            });
            items.append(QJsonObject{
                {QStringLiteral("version"), 2},
                {QStringLiteral("preference_value"), QStringLiteral("英文")},
                {QStringLiteral("memory_status"), QStringLiteral("active")},
                {QStringLiteral("is_current"), true},
            });
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("items"), items}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("p5"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.loadPreferenceHistory(QStringLiteral("u1"),
                             QStringLiteral("response.language"),
                             QStringLiteral("global"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.preferenceHistory().size(), 2);

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kPreferenceHistory);
    QCOMPARE(req.payload.value(QStringLiteral("preference_scope")).toString(),
             QStringLiteral("global"));
    mock.close();
}

void D7cPreferenceEditorTest::errorResponseRoutesPreferenceToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("preference.* not implemented"));
    });
    const QString socket = mock.listen(uniqueSocketName("p6"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy reqFailedSpy(&vm, &client::MemoryViewModel::requestFailed);
    vm.loadPreferences(QStringLiteral("u1"));
    QTRY_COMPARE_WITH_TIMEOUT(vm.preferenceStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.preferenceError().isEmpty());
    QVERIFY(!vm.preferenceBusy());
    QVERIFY(reqFailedSpy.count() >= 1);
    mock.close();
}

QTEST_MAIN(D7cPreferenceEditorTest)
#include "test_d7c_preference_editor.moc"
