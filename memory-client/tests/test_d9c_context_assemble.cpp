// test_d9c_context_assemble.cpp — D9C Memory Context 组装 L0 Mock 契约测试
//
// 范围（L0 Mock Gateway）：覆盖 MemoryViewModel 候选 IPC 方法 context.assemble 的
// payload 形状、响应路由、可解释字段投影与 Token 预算校验。
// 注意：本测试仅为 memory-client 侧 L0 契约验证，不代表真实银河麒麟 VM
//       宿主交互验收（L2 需在 VM 上另行执行）。context.assemble 为 CANDIDATE / pending ADR。
//
// 用例：
//   A1 组装成功 → assembledContext 填充（含 selected_memory_ids / injection_status=prepared）
//   A2 召回来源投影（recall_sources[]）
//   A3 记忆类型投影（memory_types[]）
//   A4 冲突提示投影（conflict_hints[]）
//   A5 不确定性提示投影（uncertainty_hints[]）
//   A6 Token 预算内 → budget_exceeded=false
//   A7 Token 超预算 → budget_exceeded=true（客户端独立计算）
//   A8 空 user_id → stage=failed
//   A9 空 query_text → stage=failed
//   A10 非正 token_budget → stage=failed
//   A11 candidates JSON 透传到 payload
//   E1 status=error → stage=failed + error + requestFailed
//   E2 UNSUPPORTED_METHOD → stage=failed
//   S1 injection_status=skipped → 防伪 Context（assembledContext 保持空）
//   S2 injection_status=failed → 防伪 Context
//   R1 与 D8C pipeline 独立 pending 不串台
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

class D9cContextAssembleTest final : public QObject {
    Q_OBJECT

private slots:
    void assembleSuccessPopulatesContext();               // A1
    void assembleProjectsRecallSources();                // A2
    void assembleProjectsMemoryTypes();                  // A3
    void assembleProjectsConflictHints();                // A4
    void assembleProjectsUncertaintyHints();             // A5
    void assembleWithinBudgetNotExceeded();              // A6
    void assembleOverBudgetExceeded();                   // A7
    void assembleEmptyUserIdRoutesToFailed();            // A8
    void assembleEmptyQueryTextRoutesToFailed();         // A9
    void assembleNonPositiveBudgetRoutesToFailed();     // A10
    void assembleForwardsCandidatesJson();               // A11
    void assembleErrorResponseRoutesToFailed();         // E1
    void assembleUnsupportedMethodRoutesToFailed();      // E2
    void assembleSkippedStatusKeepsContextEmpty();       // S1
    void assembleFailedStatusKeepsContextEmpty();        // S2
    void contextAssembleIndependentFromD8c();             // R1
    void contextAssembleRejectsWhenDisconnected();        // R2

private:
    QString uniqueSocketName(const QString& prefix);
};

QString D9cContextAssembleTest::uniqueSocketName(const QString& prefix)
{
    return QStringLiteral("/tmp/kylin-mock-d9c-%1-%2.sock")
        .arg(prefix)
        .arg(QCoreApplication::applicationPid());
}

// 构造一个标准非空 Context data（供多数成功用例复用）。
static QJsonObject makeSampleContextData()
{
    QJsonArray selectedIds;
    selectedIds.append(QStringLiteral("km-1"));
    selectedIds.append(QStringLiteral("km-2"));
    QJsonArray recallSources;
    recallSources.append(QStringLiteral("fts5"));
    recallSources.append(QStringLiteral("vector"));
    QJsonArray memoryTypes;
    memoryTypes.append(QJsonObject{
        {QStringLiteral("type"), QStringLiteral("fact")},
        {QStringLiteral("count"), 2}});
    QJsonArray conflictHints;
    conflictHints.append(QJsonObject{
        {QStringLiteral("memory_id"), QStringLiteral("km-1")},
        {QStringLiteral("conflict_state"), QStringLiteral("unresolved")}});
    QJsonArray uncertaintyHints;
    uncertaintyHints.append(QStringLiteral("vector_score_unverified"));
    return QJsonObject{
        {QStringLiteral("selected_memory_ids"), selectedIds},
        {QStringLiteral("context_version"), QStringLiteral("context-v1")},
        {QStringLiteral("recall_sources"), recallSources},
        {QStringLiteral("memory_types"), memoryTypes},
        {QStringLiteral("conflict_hints"), conflictHints},
        {QStringLiteral("uncertainty_hints"), uncertaintyHints},
        {QStringLiteral("token_budget"), 800},
        {QStringLiteral("actual_token_count"), 120},
        {QStringLiteral("budget_exceeded"), false},
        {QStringLiteral("injection_status"), QStringLiteral("prepared")},
    };
}

// ── A1 组装成功 ──────────────────────────────────────────────────────────────
void D9cContextAssembleTest::assembleSuccessPopulatesContext()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, makeSampleContextData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("如何撰写项目周报"),
        800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.assembledContext().value(
        QStringLiteral("injection_status")).toString(),
        QStringLiteral("prepared"));
    QCOMPARE(vm.assembledContext().value(
        QStringLiteral("context_version")).toString(),
        QStringLiteral("context-v1"));
    QVERIFY(!vm.contextAssembleBusy());
    QVERIFY(vm.contextAssembleError().isEmpty());

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.method, client::methods::kContextAssemble);
    QCOMPARE(req.payload.value(QStringLiteral("user_id")).toString(),
             QStringLiteral("u1"));
    QCOMPARE(req.payload.value(QStringLiteral("query_text")).toString(),
             QStringLiteral("如何撰写项目周报"));
    QCOMPARE(req.payload.value(QStringLiteral("token_budget")).toInt(), 800);
    mock.close();
}

// ── A2 召回来源投影 ──────────────────────────────────────────────────────────
void D9cContextAssembleTest::assembleProjectsRecallSources()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            auto data = makeSampleContextData();
            QJsonArray rs;
            rs.append(QStringLiteral("fts5"));
            rs.append(QStringLiteral("vector"));
            rs.append(QStringLiteral("rrf"));
            data[QStringLiteral("recall_sources")] = rs;
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.contextRecallSources().size(), 3);
    QCOMPARE(vm.contextRecallSources().at(0).toString(), QStringLiteral("fts5"));
    QCOMPARE(vm.contextRecallSources().at(2).toString(), QStringLiteral("rrf"));
    mock.close();
}

// ── A3 记忆类型投影 ──────────────────────────────────────────────────────────
void D9cContextAssembleTest::assembleProjectsMemoryTypes()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, makeSampleContextData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a3"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.contextMemoryTypes().size(), 1);
    QCOMPARE(vm.contextMemoryTypes().at(0).toMap()
                 .value(QStringLiteral("type")).toString(),
             QStringLiteral("fact"));
    QCOMPARE(vm.contextMemoryTypes().at(0).toMap()
                 .value(QStringLiteral("count")).toInt(), 2);
    mock.close();
}

// ── A4 冲突提示投影 ───────────────────────────────────────────────────────────
void D9cContextAssembleTest::assembleProjectsConflictHints()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, makeSampleContextData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a4"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.contextConflictHints().size(), 1);
    QCOMPARE(vm.contextConflictHints().at(0).toMap()
                 .value(QStringLiteral("memory_id")).toString(),
             QStringLiteral("km-1"));
    QCOMPARE(vm.contextConflictHints().at(0).toMap()
                 .value(QStringLiteral("conflict_state")).toString(),
             QStringLiteral("unresolved"));
    mock.close();
}

// ── A5 不确定性提示投影 ───────────────────────────────────────────────────────
void D9cContextAssembleTest::assembleProjectsUncertaintyHints()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, makeSampleContextData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a5"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.contextUncertaintyHints().size(), 1);
    QCOMPARE(vm.contextUncertaintyHints().at(0).toString(),
             QStringLiteral("vector_score_unverified"));
    mock.close();
}

// ── A6 Token 预算内 → budget_exceeded=false ──────────────────────────────────
void D9cContextAssembleTest::assembleWithinBudgetNotExceeded()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, makeSampleContextData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a6"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.contextTokenBudget(), 800);
    QCOMPARE(vm.contextActualTokenCount(), 120);
    QVERIFY(!vm.contextBudgetExceeded());
    mock.close();
}

// ── A7 Token 超预算 → budget_exceeded=true（客户端独立计算）─────────────────────
void D9cContextAssembleTest::assembleOverBudgetExceeded()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            auto data = makeSampleContextData();
            data[QStringLiteral("token_budget")] = 100;
            data[QStringLiteral("actual_token_count")] = 250;
            // 服务端遗漏 budget_exceeded 字段 → 客户端必须独立计算为 true
            data.remove(QStringLiteral("budget_exceeded"));
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a7"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 100, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QCOMPARE(vm.contextTokenBudget(), 100);
    QCOMPARE(vm.contextActualTokenCount(), 250);
    QVERIFY(vm.contextBudgetExceeded());
    mock.close();
}

// ── A8 空 user_id → stage=failed ─────────────────────────────────────────────
void D9cContextAssembleTest::assembleEmptyUserIdRoutesToFailed()
{
    client::MemoryViewModel vm;
    vm.runContextAssemblePipeline(
        QString(), QStringLiteral("q"), 800, QString(), QString());
    QCOMPARE(vm.contextAssembleStage(), QStringLiteral("failed"));
    QVERIFY(!vm.contextAssembleError().isEmpty());
    QVERIFY(!vm.contextAssembleBusy());
}

// ── A9 空 query_text → stage=failed ──────────────────────────────────────────
void D9cContextAssembleTest::assembleEmptyQueryTextRoutesToFailed()
{
    client::MemoryViewModel vm;
    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QString(), 800, QString(), QString());
    QCOMPARE(vm.contextAssembleStage(), QStringLiteral("failed"));
    QVERIFY(!vm.contextAssembleError().isEmpty());
    QVERIFY(!vm.contextAssembleBusy());
}

// ── A10 非正 token_budget → stage=failed ─────────────────────────────────────
void D9cContextAssembleTest::assembleNonPositiveBudgetRoutesToFailed()
{
    client::MemoryViewModel vm;
    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 0, QString(), QString());
    QCOMPARE(vm.contextAssembleStage(), QStringLiteral("failed"));
    QVERIFY(!vm.contextAssembleError().isEmpty());
    QVERIFY(!vm.contextAssembleBusy());

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), -5, QString(), QString());
    QCOMPARE(vm.contextAssembleStage(), QStringLiteral("failed"));
}

// ── A11 candidates JSON 透传到 payload ────────────────────────────────────────
void D9cContextAssembleTest::assembleForwardsCandidatesJson()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, makeSampleContextData());
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("a11"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    const QString candidates = QStringLiteral(
        "[{\"memory_id\":\"km-1\",\"channels\":[\"fts5\",\"vector\"]}]");
    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800,
        QStringLiteral("office"), candidates);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);

    const auto& req = mock.receivedRequests().back();
    QCOMPARE(req.payload.value(QStringLiteral("scene")).toString(),
             QStringLiteral("office"));
    const QJsonArray cands = req.payload.value(
        QStringLiteral("candidates")).toArray();
    QCOMPARE(cands.size(), 1);
    QCOMPARE(cands.at(0).toObject().value(
        QStringLiteral("memory_id")).toString(), QStringLiteral("km-1"));
    mock.close();
}

// ── E1 status=error → stage=failed ────────────────────────────────────────────
void D9cContextAssembleTest::assembleErrorResponseRoutesToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kInternalError,
            QStringLiteral("context assembly backend failure"));
    });
    const QString socket = mock.listen(uniqueSocketName("e1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    QSignalSpy reqFailedSpy(&vm, &client::MemoryViewModel::requestFailed);
    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.contextAssembleError().isEmpty());
    QVERIFY(!vm.contextAssembleBusy());
    QVERIFY(reqFailedSpy.count() >= 1);
    // 错误响应绝不参与 Context 拼接
    QVERIFY(vm.assembledContext().isEmpty());
    QCOMPARE(vm.contextInjectionStatus(), QStringLiteral("failed"));
    mock.close();
}

// ── E2 UNSUPPORTED_METHOD → stage=failed ──────────────────────────────────────
void D9cContextAssembleTest::assembleUnsupportedMethodRoutesToFailed()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        return client::buildErrorResponse(
            parts.requestId, parts.traceId,
            client::error_codes::kUnsupportedMethod,
            QStringLiteral("context.assemble not implemented"));
    });
    const QString socket = mock.listen(uniqueSocketName("e2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("failed"), 5000);
    QVERIFY(!vm.contextAssembleError().isEmpty());
    QVERIFY(vm.assembledContext().isEmpty());
    mock.close();
}

// ── S1 injection_status=skipped → 防伪 Context（assembledContext 保持空）──────
void D9cContextAssembleTest::assembleSkippedStatusKeepsContextEmpty()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            // 非空 data 但 injection_status=skipped → 客户端不得产生伪 Context
            auto data = makeSampleContextData();
            data[QStringLiteral("injection_status")] = QStringLiteral("skipped");
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("s1"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("failed"), 5000);
    // 防伪 Context：skipped 一律清空
    QVERIFY(vm.assembledContext().isEmpty());
    QCOMPARE(vm.contextRecallSources().size(), 0);
    QCOMPARE(vm.contextConflictHints().size(), 0);
    QCOMPARE(vm.contextInjectionStatus(), QStringLiteral("skipped"));
    QVERIFY(!vm.contextAssembleError().isEmpty());
    mock.close();
}

// ── S2 injection_status=failed → 防伪 Context ─────────────────────────────────
void D9cContextAssembleTest::assembleFailedStatusKeepsContextEmpty()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            auto data = makeSampleContextData();
            data[QStringLiteral("injection_status")] = QStringLiteral("failed");
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, data);
        }
        return client::buildSuccessResponse(
            parts.requestId, parts.traceId, QJsonObject{});
    });
    const QString socket = mock.listen(uniqueSocketName("s2"));
    QVERIFY(!socket.isEmpty());

    client::MemoryViewModel vm;
    vm.setSocketPath(socket);
    vm.connectToService();
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.connectionState(), QStringLiteral("connected"), 5000);

    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("failed"), 5000);
    QVERIFY(vm.assembledContext().isEmpty());
    QCOMPARE(vm.contextInjectionStatus(), QStringLiteral("failed"));
    QVERIFY(!vm.contextAssembleError().isEmpty());
    mock.close();
}

// ── R1 与 D8C pipeline 独立 pending 不串台 ────────────────────────────────────
void D9cContextAssembleTest::contextAssembleIndependentFromD8c()
{
    test_support::MockGatewayServer mock;
    mock.setHandler([](const client::EnvelopeParts& parts) -> QJsonObject {
        if (parts.method == client::methods::kContextAssemble) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId, makeSampleContextData());
        }
        if (parts.method == client::methods::kKnowledgeDetail) {
            return client::buildSuccessResponse(
                parts.requestId, parts.traceId,
                QJsonObject{{QStringLiteral("memory_id"),
                             parts.payload.value(QStringLiteral("memory_id"))}});
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

    // 依次发起 D9C + D8C 请求，互不干扰
    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    vm.runKnowledgeDetailPipeline(QStringLiteral("km-1"), true, true);

    QTRY_COMPARE_WITH_TIMEOUT(
        vm.contextAssembleStage(), QStringLiteral("ready"), 5000);
    QTRY_COMPARE_WITH_TIMEOUT(
        vm.knowledgeDetailStage(), QStringLiteral("ready"), 5000);

    // 两个 pipeline 各自命中，无串台
    QCOMPARE(vm.assembledContext().value(
        QStringLiteral("injection_status")).toString(),
        QStringLiteral("prepared"));
    QCOMPARE(vm.knowledgeDetail().value(
        QStringLiteral("memory_id")).toString(),
        QStringLiteral("km-1"));
    QVERIFY(!vm.contextAssembleBusy());
    QVERIFY(!vm.knowledgeDetailBusy());

    QCOMPARE(mock.receivedRequests().size(), 2);
    QCOMPARE(mock.receivedRequests().at(0).method,
             client::methods::kContextAssemble);
    QCOMPARE(mock.receivedRequests().at(1).method,
             client::methods::kKnowledgeDetail);
    mock.close();
}

// ── R2 未连接拒绝 → stage=failed ──────────────────────────────────────────────
void D9cContextAssembleTest::contextAssembleRejectsWhenDisconnected()
{
    client::MemoryViewModel vm;
    vm.runContextAssemblePipeline(
        QStringLiteral("u1"), QStringLiteral("q"), 800, QString(), QString());
    QCOMPARE(vm.contextAssembleStage(), QStringLiteral("failed"));
    QVERIFY(vm.contextAssembleError().contains(QStringLiteral("connect"),
                                                Qt::CaseInsensitive));
}

QTEST_MAIN(D9cContextAssembleTest)
#include "test_d9c_context_assemble.moc"
