// test_d8c_knowledge_conflict_lifecycle.cpp — D8C 知识详情 / 冲突对比 / 生命周期状态 L0 Mock 契约测试
//
// 范围（L0 Mock Gateway）：覆盖 MemoryViewModel 三个候选 IPC 方法
// （knowledge.detail / conflict.compare / lifecycle.status）的 payload 形状与响应路由。
// 注意：本测试仅为 memory-client 侧 L0 契约验证，不代表真实银河麒麟 VM
//       宿主交互验收（L2 需在 VM 上另行执行）。三个方法为 CANDIDATE / pending ADR。
//
// 用例：
//   K1 知识详情成功 → knowledgeDetail 填充（含 evidence/conditions）
//   K2 知识详情 evidence/conditions 投影
//   K3 知识详情空 memory_id → stage=failed
//   C1 冲突对比成功 → conflictCandidates 填充
//   C2 冲突对比默认 include_resolved=false
//   C3 冲突对比空候选 → 空数组不报错
//   L1 生命周期状态成功 → lifecycleItems 填充
//   L2 生命周期状态可选过滤透传
//   L3 生命周期状态空 user_id → stage=failed
//   E1 知识详情 status=error → stage=failed + error + requestFailed
//   E2 冲突对比 status=error → stage=failed
//   E3 生命周期状态 status=error → stage=failed
//   R1 三 pipeline 独立 pending 不串台
//   R2 未连接拒绝 → stage=failed

#include "memory_client.h"
#include "mock_gateway_server.h"
#include "view_models/memory_view_model.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QtTest>

namespace client = kylin::memory::client::v1;
namespace test_support = kylin::memory::client::v1::test_support;

class D8cKnowledgeConflictLifecycleTest final : public QObject {
    Q_OBJECT

private slots:
    void knowledgeDetailSuccessPopulatesDetail();              // K1
    void knowledgeDetailProjectsEvidenceAndConditions();       // K2
    void knowledgeDetailEmptyMemoryIdRoutesToFailed();         // K3
    void conflictCompareSuccessPopulatesCandidates();          // C1
    void conflictCompareDefaultsToUnresolvedOnly();            // C2
    void conflictCompareEmptyCandidatesIsSafe();               // C3
    void lifecycleStatusSuccessPopulatesItems();               // L1
    void lifecycleStatusForwardsOptionalFilters();             // L2
    void lifecycleStatusEmptyUserIdRoutesToFailed();           // L3
    void knowledgeDetailErrorResponseRoutesToFailed();         // E1
    void conflictCompareErrorResponseRoutesToFailed();         // E2
    void lifecycleStatusErrorResponseRoutesToFailed();         // E3
    void threePipelinesHaveIndependentPending();               // R1
    void pipelinesRejectWhenDisconnected();                    // R2

private:
    QString uniqueSocketName(const QString& prefix);
};

QString D8cKnowledgeConflictLifecycleTest::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d8c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

// ── K1 知识详情成功 ──────────────────────────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::knowledgeDetailSuccessPopulatesDetail()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kKnowledgeDetail) {
            if (parts.payload.value(QStringLiteral("memory_id")).toString()
                    != QStringLiteral("km-1")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad memory_id"));
            }
            QJsonArray evidence;
            evidence.append(QStringLiteral("evidence-1"));
            evidence.append(QStringLiteral("evidence-2"));
            QJsonArray conditions;
            conditions.append(QStringLiteral("cond-a"));
            QJsonObject data{
                {QStringLiteral("memory_id"), QStringLiteral("km-1")},
                {QStringLiteral("knowledge_type"), QStringLiteral("fact")},
                {QStringLiteral("content_summary"), QStringLiteral("示例知识")},
                {QStringLiteral("evidence"), evidence},
                {QStringLiteral("conditions"), conditions},
            };
            return client::buildSuccessResponse(parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("k1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runKnowledgeDetailPipeline(QStringLiteral("km-1"), true, true);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.knowledgeDetailStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.knowledgeDetail().value(QStringLiteral("memory_id")).toString(),
             QStringLiteral("km-1"));
    QVERIFY(!vm.knowledgeDetailBusy());
    QVERIFY(vm.knowledgeDetailError().isEmpty());

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kKnowledgeDetail);
    QCOMPARE(req.payload.value(QStringLiteral("include_evidence")).toBool(), true);
    QCOMPARE(req.payload.value(QStringLiteral("include_conditions")).toBool(), true);
    mock.close();
}

// ── K2 知识详情 evidence/conditions 投影 ────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::knowledgeDetailProjectsEvidenceAndConditions()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kKnowledgeDetail) {
            QJsonArray evidence;
            evidence.append(QStringLiteral("e-1"));
            QJsonArray conditions;
            conditions.append(QStringLiteral("c-1"));
            conditions.append(QStringLiteral("c-2"));
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{
                    {QStringLiteral("memory_id"), parts.payload.value(QStringLiteral("memory_id"))},
                    {QStringLiteral("evidence"), evidence},
                    {QStringLiteral("conditions"), conditions},
                });
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("k2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runKnowledgeDetailPipeline(QStringLiteral("km-2"), true, false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.knowledgeDetailStage(), QStringLiteral("ready"), 5000);

    const QJsonObject detail = vm.knowledgeDetail();
    QCOMPARE(detail.value(QStringLiteral("evidence")).toArray().size(), 1);
    QCOMPARE(detail.value(QStringLiteral("conditions")).toArray().size(), 2);

    // include_conditions=false 应透传到 payload
    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.payload.value(QStringLiteral("include_conditions")).toBool(), false);
    mock.close();
}

// ── K3 知识详情空 memory_id → stage=failed ──────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::knowledgeDetailEmptyMemoryIdRoutesToFailed()
{
    client::MemoryViewModel vm;
    // 不连接，但空 memory_id 优先在参数校验阶段失败（先于连接检查）。
    vm.runKnowledgeDetailPipeline(QString(), true, true);
    QCOMPARE(vm.knowledgeDetailStage(), QStringLiteral("failed"));
    QVERIFY(!vm.knowledgeDetailError().isEmpty());
    QVERIFY(!vm.knowledgeDetailBusy());
}

// ── C1 冲突对比成功 ──────────────────────────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::conflictCompareSuccessPopulatesCandidates()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kConflictCompare) {
            QJsonArray candidates;
            candidates.append(QJsonObject{
                {QStringLiteral("memory_id"), QStringLiteral("km-1")},
                {QStringLiteral("conflict_state"), QStringLiteral("unresolved")},
                {QStringLiteral("score"), 0.92},
            });
            candidates.append(QJsonObject{
                {QStringLiteral("memory_id"), QStringLiteral("km-3")},
                {QStringLiteral("conflict_state"), QStringLiteral("unresolved")},
                {QStringLiteral("score"), 0.71},
            });
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("candidates"), candidates}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runConflictComparePipeline(QStringLiteral("km-1"), false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.conflictCompareStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.conflictCandidates().size(), 2);
    QCOMPARE(vm.conflictCandidates().at(0).toMap()
                 .value(QStringLiteral("memory_id")).toString(),
             QStringLiteral("km-1"));
    QVERIFY(vm.conflictCompareError().isEmpty());

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kConflictCompare);
    QCOMPARE(req.payload.value(QStringLiteral("memory_id")).toString(),
             QStringLiteral("km-1"));
    mock.close();
}

// ── C2 冲突对比默认 include_resolved=false ───────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::conflictCompareDefaultsToUnresolvedOnly()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kConflictCompare) {
            // 校验 include_resolved 透传
            QJsonArray candidates;
            if (!parts.payload.value(QStringLiteral("include_resolved")).toBool()) {
                candidates.append(QJsonObject{
                    {QStringLiteral("memory_id"), QStringLiteral("km-1")},
                    {QStringLiteral("conflict_state"), QStringLiteral("unresolved")},
                });
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("candidates"), candidates}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runConflictComparePipeline(QStringLiteral("km-1"), false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.conflictCompareStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.conflictCandidates().size(), 1);

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.payload.value(QStringLiteral("include_resolved")).toBool(), false);
    mock.close();
}

// ── C3 冲突对比空候选 ────────────────────────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::conflictCompareEmptyCandidatesIsSafe()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kConflictCompare) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("candidates"), QJsonArray{}}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("c3"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runConflictComparePipeline(QStringLiteral("km-9"), false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.conflictCompareStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.conflictCandidates().size(), 0);
    QVERIFY(vm.conflictCompareError().isEmpty());
    mock.close();
}

// ── L1 生命周期状态成功 ──────────────────────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::lifecycleStatusSuccessPopulatesItems()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kLifecycleStatus) {
            if (parts.payload.value(QStringLiteral("user_id")).toString()
                    != QStringLiteral("u1")) {
                return client::buildErrorResponse(
                    parts.requestId, parts.traceId,
                    client::error_codes::kInvalidRequest,
                    QStringLiteral("bad user_id"));
            }
            QJsonArray items;
            items.append(QJsonObject{
                {QStringLiteral("memory_id"), QStringLiteral("km-1")},
                {QStringLiteral("memory_status"), QStringLiteral("active")},
                {QStringLiteral("version"), 3},
                {QStringLiteral("updated_at"), QStringLiteral("2026-08-31T10:00:00Z")},
            });
            items.append(QJsonObject{
                {QStringLiteral("memory_id"), QStringLiteral("km-2")},
                {QStringLiteral("memory_status"), QStringLiteral("superseded")},
                {QStringLiteral("version"), 1},
                {QStringLiteral("updated_at"), QStringLiteral("2026-08-30T10:00:00Z")},
            });
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("items"), items}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("l1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runLifecycleStatusPipeline(QStringLiteral("u1"), QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.lifecycleStatusStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.lifecycleItems().size(), 2);
    QCOMPARE(vm.lifecycleItems().at(0).toMap()
                 .value(QStringLiteral("memory_status")).toString(),
             QStringLiteral("active"));
    QVERIFY(vm.lifecycleStatusError().isEmpty());

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kLifecycleStatus);
    QCOMPARE(req.payload.value(QStringLiteral("user_id")).toString(),
             QStringLiteral("u1"));
    mock.close();
}

// ── L2 生命周期状态可选过滤透传 ──────────────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::lifecycleStatusForwardsOptionalFilters()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kLifecycleStatus) {
            // 仅返回匹配 memory_status=active 的条目
            const QString status = parts.payload.value(QStringLiteral("memory_status")).toString();
            QJsonArray items;
            if (status == QStringLiteral("active")) {
                items.append(QJsonObject{
                    {QStringLiteral("memory_id"), QStringLiteral("km-1")},
                    {QStringLiteral("memory_status"), QStringLiteral("active")},
                });
            }
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("items"), items}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("l2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runLifecycleStatusPipeline(
        QStringLiteral("u1"), QStringLiteral("km-1"), QStringLiteral("active"));
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.lifecycleStatusStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.lifecycleItems().size(), 1);

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.payload.value(QStringLiteral("memory_id")).toString(),
             QStringLiteral("km-1"));
    QCOMPARE(req.payload.value(QStringLiteral("memory_status")).toString(),
             QStringLiteral("active"));
    mock.close();
}

// ── L3 生命周期状态空 user_id → stage=failed ─────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::lifecycleStatusEmptyUserIdRoutesToFailed()
{
    client::MemoryViewModel vm;
    vm.runLifecycleStatusPipeline(QString(), QString(), QString());
    QCOMPARE(vm.lifecycleStatusStage(), QStringLiteral("failed"));
    QVERIFY(!vm.lifecycleStatusError().isEmpty());
    QVERIFY(!vm.lifecycleStatusBusy());
}

// ── E1 知识详情 status=error → stage=failed ──────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::knowledgeDetailErrorResponseRoutesToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("knowledge.detail not implemented"));
    });
    const QString socket = mock.listen(uniqueSocketName("e1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy reqFailedSpy(&vm, &client::MemoryViewModel::requestFailed);
    vm.runKnowledgeDetailPipeline(QStringLiteral("km-1"), true, true);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.knowledgeDetailStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.knowledgeDetailError().isEmpty());
    QVERIFY(!vm.knowledgeDetailBusy());
    QVERIFY(reqFailedSpy.count() >= 1);
    mock.close();
}

// ── E2 冲突对比 status=error → stage=failed ──────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::conflictCompareErrorResponseRoutesToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("conflict.compare not implemented"));
    });
    const QString socket = mock.listen(uniqueSocketName("e2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runConflictComparePipeline(QStringLiteral("km-1"), false);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.conflictCompareStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.conflictCompareError().isEmpty());
    QVERIFY(!vm.conflictCompareBusy());
    mock.close();
}

// ── E3 生命周期状态 status=error → stage=failed ──────────────────────────────
void D8cKnowledgeConflictLifecycleTest::lifecycleStatusErrorResponseRoutesToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("lifecycle.status not implemented"));
    });
    const QString socket = mock.listen(uniqueSocketName("e3"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runLifecycleStatusPipeline(QStringLiteral("u1"), QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.lifecycleStatusStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.lifecycleStatusError().isEmpty());
    QVERIFY(!vm.lifecycleStatusBusy());
    mock.close();
}

// ── R1 三 pipeline 独立 pending 不串台 ───────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::threePipelinesHaveIndependentPending()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kKnowledgeDetail) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("memory_id"),
                             parts.payload.value(QStringLiteral("memory_id"))}});
        }
        if (parts.method == client::methods::kConflictCompare) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("candidates"), QJsonArray{}}});
        }
        if (parts.method == client::methods::kLifecycleStatus) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("items"), QJsonArray{}}});
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("r1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    // 依次发起三个请求，互不干扰
    vm.runKnowledgeDetailPipeline(QStringLiteral("km-1"), true, true);
    vm.runConflictComparePipeline(QStringLiteral("km-1"), false);
    vm.runLifecycleStatusPipeline(QStringLiteral("u1"), QString(), QString());

    QTRY_COMPARE_WITH_TIMEOUT(
        vm.knowledgeDetailStage(), QStringLiteral("ready"), 5000);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.conflictCompareStage(), QStringLiteral("ready"), 5000);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.lifecycleStatusStage(), QStringLiteral("ready"), 5000);

    // 三个 pipeline 各自命中，无串台
    QCOMPARE(vm.knowledgeDetail().value(QStringLiteral("memory_id")).toString(),
             QStringLiteral("km-1"));
    QCOMPARE(vm.conflictCandidates().size(), 0);
    QCOMPARE(vm.lifecycleItems().size(), 0);
    QVERIFY(!vm.knowledgeDetailBusy());
    QVERIFY(!vm.conflictCompareBusy());
    QVERIFY(!vm.lifecycleStatusBusy());

    // 服务端应收到三个不同方法的请求
    QCOMPARE(mock.receivedRequests().size(), 3);
    mock.close();
}

// ── R2 未连接拒绝 → stage=failed ──────────────────────────────────────────────
void D8cKnowledgeConflictLifecycleTest::pipelinesRejectWhenDisconnected()
{
    client::MemoryViewModel vm;
    // 不连接，参数合法但连接检查失败
    vm.runKnowledgeDetailPipeline(QStringLiteral("km-1"), true, true);
    QCOMPARE(vm.knowledgeDetailStage(), QStringLiteral("failed"));
    QVERIFY(vm.knowledgeDetailError().contains(QStringLiteral("connect"),
                                                Qt::CaseInsensitive));

    vm.runConflictComparePipeline(QStringLiteral("km-1"), false);
    QCOMPARE(vm.conflictCompareStage(), QStringLiteral("failed"));
    QVERIFY(vm.conflictCompareError().contains(QStringLiteral("connect"),
                                               Qt::CaseInsensitive));

    vm.runLifecycleStatusPipeline(QStringLiteral("u1"), QString(), QString());
    QCOMPARE(vm.lifecycleStatusStage(), QStringLiteral("failed"));
    QVERIFY(vm.lifecycleStatusError().contains(QStringLiteral("connect"),
                                               Qt::CaseInsensitive));
}

QTEST_MAIN(D8cKnowledgeConflictLifecycleTest)
#include "test_d8c_knowledge_conflict_lifecycle.moc"
