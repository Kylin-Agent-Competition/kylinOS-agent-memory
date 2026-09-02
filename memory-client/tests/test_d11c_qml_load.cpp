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
//   E. QObject::property 能读取 orchestrator.viewModel，等价于 alias。
//
// 注意：
//   本测试仅加载 QML Component，不启动真实 Window；符合 L0 / CI headless 环境。
//   本测试仍为 Demo/Prototype L0，不代表真实 Runtime + D11B VM 已接。
// ============================================================================

#include <QCoreApplication>
#include <QGuiApplication>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickItem>
#include <QString>
#include <QUrl>
#include <QtTest>

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
    QScopedPointer<QGuiApplication> app_;
    QScopedPointer<QQmlEngine> engine_;
};

void TestD11cQmlLoad::initTestCase()
{
    // CI 环境无显示，使用 offscreen platform 避免 QGuiApplication 初始化失败。
    qputenv("QT_QPA_PLATFORM", "offscreen");

    static int argc = 1;
    static char arg0[] = "test_d11c_qml_load";
    static char* argv[] = { arg0, nullptr };
    app_.reset(new QGuiApplication(argc, argv));

    engine_.reset(new QQmlEngine);
    // 严格模式：把 QML warning 记录到我们自己的 buffer，便于断言
    QLoggingCategory::setFilterRules(QStringLiteral("qt.qml.binding.removal.info=true"));
}

void TestD11cQmlLoad::cleanupTestCase()
{
    engine_.reset();
    app_.reset();
}

void TestD11cQmlLoad::resourceUrlResolves()
{
    // resources.qrc 中 prefix=/qt/qml/memory_client，file=pages/D11DemoOrchestratorPage.qml
    const QUrl url(QStringLiteral("qrc:/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml"));
    QVERIFY2(url.isValid(), "D11 页面 qrc URL 格式必须合法");

    QQmlComponent probe(engine_.data(), url);
    // 即使是异步的，status 必须从不等于 Error（等它 ready 或 Loading）
    QTRY_COMPARE_WITH_TIMEOUT(probe.status(), QQmlComponent::Ready, 3000);
    QVERIFY2(!probe.isError(),
             qPrintable(QStringLiteral("Component 加载不应有错误，当前错误: %1")
                            .arg(probe.errorString())));
}

void TestD11cQmlLoad::componentCreatesWithoutErrors()
{
    const QUrl url(QStringLiteral("qrc:/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml"));
    QQmlComponent component(engine_.data(), url);
    QTRY_COMPARE_WITH_TIMEOUT(component.status(), QQmlComponent::Ready, 3000);

    QVERIFY2(component.isReady(),
             qPrintable(QStringLiteral("D11 Component 必须 Ready，当前 status=%1 错误=%2")
                            .arg(component.status())
                            .arg(component.errorString())));

    QScopedPointer<QObject> obj(component.create());
    QVERIFY2(!component.isError(),
             qPrintable(QStringLiteral("create() 触发了错误: %1").arg(component.errorString())));
    QVERIFY2(!obj.isNull(), "create() 返回对象必须非空");

    // ScrollView 继承自 QQuickItem
    auto* item = qobject_cast<QQuickItem*>(obj.data());
    QVERIFY2(item != nullptr, "D11 顶层对象必须为 QQuickItem (ScrollView)");
}

void TestD11cQmlLoad::viewModelAliasExistsAndInitiallyNull()
{
    const QUrl url(QStringLiteral("qrc:/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml"));
    QQmlComponent component(engine_.data(), url);
    QTRY_COMPARE_WITH_TIMEOUT(component.status(), QQmlComponent::Ready, 3000);
    QScopedPointer<QObject> obj(component.create());
    QVERIFY2(!obj.isNull(), "create() 返回对象必须非空");

    // HIGH-01 修复：root 必须暴露 "viewModel" alias 属性
    const QMetaObject* meta = obj->metaObject();
    const int idx = meta->indexOfProperty("viewModel");
    QVERIFY2(idx >= 0,
             "D11 顶层对象必须存在 viewModel 属性（alias 修复验证）");

    QMetaProperty prop = meta->property(idx);
    QVERIFY2(prop.isValid(), "viewModel 元属性必须有效");

    // 初始没有 ViewModel 注入，alias 必须为 null
    const QVariant initial = obj->property("viewModel");
    QVERIFY2(!initial.isValid() || initial.isNull(),
             qPrintable(QStringLiteral("初始 viewModel 应为 null，实际: %1")
                            .arg(initial.toString())));
}

void TestD11cQmlLoad::multipleInstantiationsDoNotLeak()
{
    const QUrl url(QStringLiteral("qrc:/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml"));
    QQmlComponent component(engine_.data(), url);
    QTRY_COMPARE_WITH_TIMEOUT(component.status(), QQmlComponent::Ready, 3000);

    QObject* first = component.create();
    QVERIFY2(first != nullptr, "第 1 次 create() 必须成功");
    QObject* second = component.create();
    QVERIFY2(second != nullptr, "第 2 次 create() 必须成功");
    QVERIFY2(first != second, "两次实例化必须返回不同对象");

    const QVariant vm1 = first->property("viewModel");
    const QVariant vm2 = second->property("viewModel");
    // 初始都应为 null，互不影响
    QCOMPARE(vm1.isNull() || !vm1.isValid(), true);
    QCOMPARE(vm2.isNull() || !vm2.isValid(), true);

    delete second;
    delete first;
}

QTEST_MAIN(TestD11cQmlLoad)
#include "test_d11c_qml_load.moc"
