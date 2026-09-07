// ============================================================================
// 全 QML 文件编译加载 L0 测试（PR151 麒麟 VM 回归配套）
//
// 背景（evidence/l2-kylin-vm/pr151_vm_test_report_20260905.md）：
//   VerticalLinkPage.qml 在麒麟 VM（Qt 5.12）上因 ColumnLayout 的
//   bottomPadding（QtQuick.Layouts padding 自 Qt 5.15 起才有）导致
//   QML 加载失败、应用退出码 255；而 CI（Ubuntu 22.04, Qt 5.15.3）
//   全绿——因为 d11c_qml_load 仅覆盖 D11DemoOrchestratorPage.qml，
//   其余 13 个 QML 文件没有任何 QQmlComponent 加载覆盖。
//
// 覆盖：
//   qrc 内全部 14 个 QML 文件（main.qml + 13 个页面）逐个
//   QQmlComponent 编译加载，断言 status == Ready 且 errors() 为空。
//   "Cannot assign to non-existent property"（padding 类错误）、
//   语法错误、import 缺失、QML 类型未注册均会在此阶段暴露。
//
// 已知局限（如实声明，不夸大覆盖面）：
//   * CI 的 Qt 版本（5.15）高于麒麟 VM（5.12），5.15 才有的 QML 特性
//     在 CI 上合法、在 VM 上失败——本测试无法消除该差异，
//     Qt 版本兼容性结论仍以麒麟 VM L2 回归为准（红线：L2 证据
//     必须麒麟 VM 真实链路）。
//   * 本测试仅做编译期验证（不 create()、不执行绑定），
//     运行时绑定错误由各页面既有 L0 套件与 d11c_qml_load 深度用例覆盖。
//
// 实现要点（与 test_d11c_qml_load 一致）：
//   * QTEST_MAIN（生成 QGuiApplication，QQuickView/QQmlEngine 必需）；
//   * ctest set_tests_properties ENVIRONMENT 在进程启动前设置
//     QT_QPA_PLATFORM=offscreen + QT_QUICK_BACKEND=software；
//   * 与 src/main.cpp 相同的 kylin.memory 1.0 注册
//     （页面声明 property MemoryViewModel viewModel、
//      main.qml 实例化 MemoryViewModel {}，未注册则编译失败）；
//   * qt5_add_resources 把 qml/resources.qrc 显式编进测试二进制
//     （L0 测试不链接 kylin_memory_client_app，qrc 不会自动带过来）。
// ============================================================================

#include <QGuiApplication>
#include <QLibraryInfo>
#include <QObject>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQmlError>
#include <QScopedPointer>
#include <QString>
#include <QStringList>
#include <QTest>
#include <QUrl>
#include <QtQml>

#include "memory_client.h"
#include "view_models/memory_view_model.h"

namespace client = kylin::memory::client::v1;

class TestQmlPagesLoad : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();

    // 数据驱动：qrc 内全部 14 个 QML 文件逐个编译加载
    void qmlFileCompiles_data();
    void qmlFileCompiles();

private:
    QScopedPointer<QQmlEngine> engine_;

    // 与 test_d11c_qml_load 相同的 import path 补充逻辑
    static QStringList importPaths();
    // 格式化 QQmlComponent::errors() 为单行字符串（失败信息可读）
    static QString formatErrors(const QQmlComponent& c);
};

void TestQmlPagesLoad::initTestCase()
{
    qputenv("QT_QPA_PLATFORM", "offscreen");
    qputenv("QT_QUICK_BACKEND", "software");

    QVERIFY2(QGuiApplication::instance() != nullptr,
             "需要 QGuiApplication（用 QTEST_MAIN 而非 QTEST_GUILESS_MAIN）");

    // 与 src/main.cpp 完全一致的 kylin.memory 1.0 类型注册。
    // 页面文件声明 property MemoryViewModel viewModel、
    // main.qml 实例化 MemoryViewModel {}——未注册时 QQmlComponent
    // 直接编译失败（"MemoryViewModel is not a type"）。
    qmlRegisterType<client::MemoryViewModel>(
        "kylin.memory", 1, 0, "MemoryViewModel");
    qmlRegisterUncreatableType<client::MemoryClient>(
        "kylin.memory", 1, 0, "MemoryClient",
        QStringLiteral("MemoryClient is created by MemoryViewModel internally."));

    engine_.reset(new QQmlEngine);
    for (const QString& p : importPaths()) {
        if (!p.isEmpty()) engine_->addImportPath(p);
    }
}

QStringList TestQmlPagesLoad::importPaths()
{
    QStringList paths;
    const QString sysImports =
        QLibraryInfo::location(QLibraryInfo::Qml2ImportsPath);
    if (!sysImports.isEmpty()) paths.append(sysImports);
    paths.append(QStringLiteral("/usr/lib/qt5/qml"));
    paths.append(QStringLiteral("/usr/share/qt5/qml"));
    paths.append(QStringLiteral("/usr/lib/x86_64-linux-gnu/qt5/qml"));
    paths.append(QStringLiteral("/usr/lib/x86_64-linux-gnu/qml"));
    paths.append(QStringLiteral("/usr/local/share/qt5/qml"));
    paths.append(QStringLiteral("qrc:/qt/qml"));
    paths.append(QStringLiteral("qrc:/qml"));
    return paths;
}

void TestQmlPagesLoad::qmlFileCompiles_data()
{
    QTest::addColumn<QString>("qmlUrl");
    QTest::addColumn<QString>("qmlName");

    // qrc:/qt/qml/memory_client/ 前缀（qml/resources.qrc 定义）。
    // 列表与 resources.qrc 的 <file> 条目一一对应，新增页面须同步两处。
    const QString base = QStringLiteral("qrc:/qt/qml/memory_client/");

    QTest::newRow("main.qml")
        << base + QStringLiteral("main.qml")
        << QStringLiteral("main.qml");

    const char* pages[] = {
        "StatusPage.qml",
        "MemoryQueryPage.qml",
        "PreferenceEditorPage.qml",
        "VerticalLinkPage.qml",
        "ToolAdapterPage.qml",
        "ManualConfigPage.qml",
        "BehaviorObservePage.qml",
        "KnowledgeDetailPage.qml",
        "ConflictComparisonPage.qml",
        "LifecycleStatusPage.qml",
        "ContextAssemblePage.qml",
        "ForgetPage.qml",
        "D11DemoOrchestratorPage.qml",
    };
    for (const char* p : pages) {
        QTest::newRow(p)
            << base + QStringLiteral("pages/") + QString::fromLatin1(p)
            << QString::fromLatin1(p);
    }
}

void TestQmlPagesLoad::qmlFileCompiles()
{
    QFETCH(QString, qmlUrl);
    QFETCH(QString, qmlName);

    QQmlComponent c(engine_.data(), QUrl(qmlUrl));

    // qrc URL 加载通常同步完成；防御性等待异步 Loading → 终态。
    if (c.status() == QQmlComponent::Loading) {
        QTRY_COMPARE_WITH_TIMEOUT(c.status(), QQmlComponent::Ready, 5000);
    }

    QVERIFY2(c.status() == QQmlComponent::Ready,
             qPrintable(QStringLiteral("%1 编译加载失败（status != Ready）: %2")
                            .arg(qmlName, formatErrors(c))));
    QVERIFY2(c.errors().isEmpty(),
             qPrintable(QStringLiteral("%1 编译加载存在 errors: %2")
                            .arg(qmlName, formatErrors(c))));
}

QString TestQmlPagesLoad::formatErrors(const QQmlComponent& c)
{
    QString out;
    const QList<QQmlError> errs = c.errors();
    if (errs.isEmpty()) {
        return QStringLiteral("<errors() 为空；可能 qrc URL 指向的资源不存在>");
    }
    for (int i = 0; i < errs.size(); ++i) {
        if (!out.isEmpty()) out += QStringLiteral(" || ");
        out += QStringLiteral("[%1] %2:%3:%4: %5")
                   .arg(i)
                   .arg(errs.at(i).url().toString())
                   .arg(errs.at(i).line())
                   .arg(errs.at(i).column())
                   .arg(errs.at(i).description());
    }
    return out;
}

QTEST_MAIN(TestQmlPagesLoad)
#include "test_qml_pages_load.moc"
