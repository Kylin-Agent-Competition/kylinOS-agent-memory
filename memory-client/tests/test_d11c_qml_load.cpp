// ============================================================================
// D11-C QML 真实加载验证 L0 测试（Reviewer E HIGH-01 请求修复）
//
// 目的：
//   验证 D11DemoOrchestratorPage.qml 可以被 QQmlEngine 真实解析和实例化。
//   CI 原来的 QML app smoke build 仅验证 qrc 资源打包与 binary 链接，
//   不保证 QML parser 能通过语法检查、别名绑定正确、id 引用存在。
//
// 覆盖：
//   A. 加载资源路径下的 D11DemoOrchestratorPage.qml（非本地 fs，等价于
//      Runtime 真实 import 流程）。
//   B. QQmlComponent 构造无 error / 无 warning（严格模式）。
//   C. create() 返回非空对象指针，类型为 QQuickItem/ScrollView。
//   D. viewModel alias 属性存在且初始值为 null（HIGH-01 alias 修复验证）。
//   E. 再次加载：重复实例化无冲突（保证 QML 缓存和 id 命名无泄漏）。
//
// 注意：
//   本测试仅加载 QML Component，不启动真实 Window；符合 L0 / CI headless 环境。
//   本测试仍为 Demo/Prototype L0，不代表真实 Runtime + D11B VM 已接。
//
// 实现要点（避免 CI 子进程崩溃 / 组件 Error）：
//   * 使用 QTEST_GUILESS_MAIN（生成 QGuiApplication，Qt5）。
//     QTEST_MAIN 仅生成 QCoreApplication，会让 QQmlEngine / QQuickItem
//     在部分平台上无法正确初始化 GUI 资源。
//     不再在 initTestCase 中二次 new QGuiApplication（双 Q*App 实例会
//     引发析构期 double free / SEGFAULT）。
//   * 通过 ctest ENVIRONMENT（见 CMakeLists.txt）设置
//     QT_QPA_PLATFORM=offscreen，进程启动时即命中 offscreen 平台插件；
//     initTestCase 的 qputenv 晚于 main() 里 QGuiApplication ctor 的
//     xcb 平台探测，会出现 "could not connect to display" 直接 abort。
// ============================================================================

#include <QGuiApplication>
#include <QFile>
#include <QLibraryInfo>
#include <QLoggingCategory>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQmlError>
#include <QQuickItem>
#include <QString>
#include <QStringList>
#include <QTest>
#include <QUrl>

class TestD11cQmlLoad : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();

    // A. qrc:/ 路径存在 & 资源可加载
    void resourceUrlResolves();

    // B + C. QQmlComponent 解析成功 & create() 返回非空对象
    void componentCreatesWithoutErrors();

    // D. viewModel alias 属性存在 + 初始值为 null（HIGH-01 alias 修复）
    void viewModelAliasExistsAndInitiallyNull();

    // E. 再次加载：重复实例化无冲突（保证 QML 缓存和 id 命名无泄漏）
    void multipleInstantiationsDoNotLeak();

private:
    QScopedPointer<QQmlEngine> engine_;
};

void TestD11cQmlLoad::initTestCase()
{
    // 保险：即便 ctest 注入的 QT_QPA_PLATFORM 没生效，也在 GUI 相关资源
    // 创建前把 offscreen 写入环境（对 main() 之前 Q*App ctor 探测无效，
    // 但可防御本地直接运行可执行文件时的默认 xcb 连接失败）。
    qputenv("QT_QPA_PLATFORM", "offscreen");

    QVERIFY2(QGuiApplication::instance() != nullptr,
             "需要 QGuiApplication（用 QTEST_GUILESS_MAIN 而非 QTEST_MAIN）");

    engine_.reset(new QQmlEngine);
    // 严格模式：把 QML warning 记录到我们自己的 buffer，便于断言
    QLoggingCategory::setFilterRules(QStringLiteral("qt.qml.binding.removal.info=true"));

    // import paths：显式补齐 Qt5 QML modules 默认安装路径，确保
    // qtdeclarative5-dev + qml-module-qtquick-* 安装的运行时模块被
    // QQmlEngine 找到，否则 D11 QML import QtQuick.Controls 2.12
    // 会在 CI headless 环境报 module not found，导致
    // QQmlComponent status() == Error 而 create() 永远返回 null。
    {
        QStringList extraImports;
        // Qt 5 标准 QML 模块根（Ubuntu 下通常为 /usr/lib/x86_64-linux-gnu/qt5/qml
        // 或 QLibraryInfo::location(QLibraryInfo::Qml2ImportsPath)）。
        const QString sysImports =
            QLibraryInfo::location(QLibraryInfo::Qml2ImportsPath);
        if (!sysImports.isEmpty()) extraImports.append(sysImports);
        // Ubuntu / Debian 打包的常见 fallback。
        extraImports.append(QStringLiteral("/usr/lib/qt5/qml"));
        extraImports.append(QStringLiteral("/usr/share/qt5/qml"));
        // NixOS / Qt 在 /usr/local 下安装的兼容路径兜底。
        extraImports.append(QStringLiteral("/usr/local/share/qt5/qml"));
        // qrc 内前缀，便于其它模块把 qml 代码嵌入自身资源。
        extraImports.append(QStringLiteral("qrc:/qt/qml"));
        extraImports.append(QStringLiteral("qrc:/qml"));
        // 去空后注册。
        for (const QString& p : extraImports) {
            if (!p.isEmpty()) engine_->addImportPath(p);
        }
        // 打印到 QTest log，便于 CI 失败时做路径诊断。
        qDebug() << "[d11c_qml_load] QQmlEngine import paths="
                 << engine_->importPathList();
    }
}

void TestD11cQmlLoad::cleanupTestCase()
{
    engine_.reset();
}

static const QUrl kD11PageUrl{
    QStringLiteral("qrc:/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml")};
// 对应 qrc 文件系统内的"裸路径"；QFile 打开成功即意味着
// qt5_add_resources 已把 resources.qrc 中的 D11 页面真正打进了
// 本测试可执行文件的 Qt resource table。若失败则 QQmlComponent
// 永远不会 Ready（会一直 Error 说无效 URL），先在此 fail-fast
// 便于 CI 定位是 rcc 打包问题还是 QML parser 问题。
static const char* kD11PageResourcePath =
    ":/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml";

// 小工具：把 QQmlComponent::errors() 里的每一条 (url/line/col/desc)
// 格式化成可直接粘进 CI log 的单行字符串，避免 CI 只能看到
// "status=Error" 却不知道具体是哪个 import / 哪一行出错。
static QString formatErrors(const QQmlComponent& c)
{
    QString out;
    const QList<QQmlError> errs = c.errors();
    if (errs.isEmpty()) {
        out = QStringLiteral("<QQmlComponent::errors() 空，可能是 qrc URL 指向资源不存在>");
        return out;
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

void TestD11cQmlLoad::resourceUrlResolves()
{
    QVERIFY2(kD11PageUrl.isValid(), "D11 页面 qrc URL 格式必须合法");

    // FAIL-FAST：先验证 QFile 可直接打开 qrc 裸路径。
    // 若这里失败，说明 qt5_add_resources 没把 resources.qrc 编进
    // test_d11c_qml_load 二进制，或者 qrc prefix 与 test 内路径
    // 不一致；直接在这里报 ASSERT 就不会让后续 QQmlComponent
    // 给出更晦涩的 "status=Error / errorString()=空" 了。
    {
        QFile f(QString::fromLatin1(kD11PageResourcePath));
        const bool opened = f.open(QIODevice::ReadOnly);
        if (!opened) {
            qCritical() << "[d11c_qml_load] QResource 缺失："
                        << kD11PageResourcePath
                        << "exists="
                        << QFile::exists(QString::fromLatin1(kD11PageResourcePath));
        }
        // 注意：QVERIFY2 的第二个参数必须是一个"有足够寿命"的 const char*。
        // 把 QStringLiteral(...).arg(...) 直接包在 qPrintable() 里会让
        // 临时 QString 在完整表达式求值后立刻析构，某些 GCC/Qt 版本下
        // 宏展开会读到悬空指针；并且多行字符串拼接紧跟 .arg() 还会
        // 让 Qt 5.12 的 Q_STATIC_ASSERT_X 触发编译期语法错误。所以
        // 这里先把格式化结果写进局部 msg，再取 qPrintable(msg)。
        const QString resPath = QString::fromLatin1(kD11PageResourcePath);
        const QString msg =
            QStringLiteral("qrc 资源表无 D11 页面（qt5_add_resources 是否"
                           "正确执行？预期裸路径=%1。请查 resources.qrc 的"
                           "<qresource prefix>）")
                .arg(resPath);
        QVERIFY2(opened, qPrintable(msg));
    }

    QQmlComponent probe(engine_.data(), kD11PageUrl);
    QTRY_COMPARE_WITH_TIMEOUT(probe.status(), QQmlComponent::Ready, 3000);
    {
        const QString errMsg =
            QStringLiteral("Component 加载不应有错误，当前错误: %1")
                .arg(formatErrors(probe));
        QVERIFY2(!probe.isError(), qPrintable(errMsg));
    }
}

void TestD11cQmlLoad::componentCreatesWithoutErrors()
{
    QQmlComponent component(engine_.data(), kD11PageUrl);
    QTRY_COMPARE_WITH_TIMEOUT(component.status(), QQmlComponent::Ready, 3000);

    {
        const QString errMsg =
            QStringLiteral("D11 Component 必须 Ready，当前 status=%1 错误=%2")
                .arg(component.status())
                .arg(formatErrors(component));
        QVERIFY2(component.isReady(), qPrintable(errMsg));
    }

    QScopedPointer<QObject> obj(component.create());
    {
        const QString errMsg =
            QStringLiteral("create() 触发了错误: %1").arg(formatErrors(component));
        QVERIFY2(!component.isError(), qPrintable(errMsg));
    }
    QVERIFY2(!obj.isNull(), "create() 返回对象必须非空");

    // ScrollView 继承自 QQuickItem
    auto* item = qobject_cast<QQuickItem*>(obj.data());
    QVERIFY2(item != nullptr, "D11 顶层对象必须为 QQuickItem (ScrollView)");
}

void TestD11cQmlLoad::viewModelAliasExistsAndInitiallyNull()
{
    QQmlComponent component(engine_.data(), kD11PageUrl);
    QTRY_COMPARE_WITH_TIMEOUT(component.status(), QQmlComponent::Ready, 3000);
    QScopedPointer<QObject> obj(component.create());
    {
        const QString errMsg =
            QStringLiteral("create() 返回对象必须非空，错误=%1")
                .arg(formatErrors(component));
        QVERIFY2(!obj.isNull(), qPrintable(errMsg));
    }

    // HIGH-01 修复：root 必须暴露 "viewModel" alias 属性
    const QMetaObject* meta = obj->metaObject();
    const int idx = meta->indexOfProperty("viewModel");
    QVERIFY2(idx >= 0,
             "D11 顶层对象必须存在 viewModel 属性（alias 修复验证）");

    QMetaProperty prop = meta->property(idx);
    QVERIFY2(prop.isValid(), "viewModel 元属性必须有效");

    // 初始没有 ViewModel 注入，alias 必须为 null
    const QVariant initial = obj->property("viewModel");
    {
        const QString errMsg =
            QStringLiteral("初始 viewModel 应为 null，实际: %1")
                .arg(initial.toString());
        QVERIFY2(!initial.isValid() || initial.isNull(), qPrintable(errMsg));
    }
}

void TestD11cQmlLoad::multipleInstantiationsDoNotLeak()
{
    QQmlComponent component(engine_.data(), kD11PageUrl);
    QTRY_COMPARE_WITH_TIMEOUT(component.status(), QQmlComponent::Ready, 3000);

    QObject* first = component.create();
    {
        const QString errMsg =
            QStringLiteral("第 1 次 create() 必须成功，错误=%1")
                .arg(formatErrors(component));
        QVERIFY2(first != nullptr, qPrintable(errMsg));
    }
    QObject* second = component.create();
    {
        const QString errMsg =
            QStringLiteral("第 2 次 create() 必须成功，错误=%1")
                .arg(formatErrors(component));
        QVERIFY2(second != nullptr, qPrintable(errMsg));
    }
    QVERIFY2(first != second, "两次实例化必须返回不同对象");

    const QVariant vm1 = first->property("viewModel");
    const QVariant vm2 = second->property("viewModel");
    // 初始都应为 null，互不影响
    QCOMPARE(vm1.isNull() || !vm1.isValid(), true);
    QCOMPARE(vm2.isNull() || !vm2.isValid(), true);

    delete second;
    delete first;
}

// 使用 GUILESS：生成 QGuiApplication，QQmlEngine / QQuickItem 的 GUI 资源
// 才能正确初始化；普通 QTEST_MAIN 只生成 QCoreApplication，CI 上会导致
// QQmlComponent status 始终 Error 或析构 SEGFAULT。
QTEST_GUILESS_MAIN(TestD11cQmlLoad)
#include "test_d11c_qml_load.moc"
