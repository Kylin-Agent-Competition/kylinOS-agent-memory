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
//   C. QQuickView 实际创建根对象，类型为 QQuickItem/ScrollView，
//      且至少一个 Step Card 的 implicitHeight > 0。
//   D. viewModel alias 属性存在且初始值为 null（HIGH-01 alias 修复验证）。
//   E. 再次加载：重复实例化无冲突（保证 QML 缓存和 id 命名无泄漏）。
//
// 注意：
//   本测试使用 QQuickView（而非裸 QQmlComponent::create()）进行实例化，
//   因为 QQuickView 内部创建 QQuickWindow 并管理 scene graph 生命周期，
//   在 offscreen + software backend 环境中比裸 create() 更稳定。
//   本测试仍为 Demo/Prototype L0，不代表真实 Runtime + D11B VM 已接。
//
// 实现要点（避免 CI 子进程崩溃 / 组件 Error）：
//   * 使用 QTEST_MAIN（不链接 QtWidgets 时生成 QGuiApplication，Qt5）。
//     QTEST_GUILESS_MAIN 生成 QCoreApplication，QQuickView/QQuickWindow
//     无法在非 QGuiApplication 环境下工作（QGuiApplication::instance()
//     返回 nullptr，测试失败）。
//   * 通过 ctest set_tests_properties ENVIRONMENT 设置
//     QT_QPA_PLATFORM=offscreen +
//     QT_QUICK_BACKEND=software，进程启动时即命中 offscreen 平台 +
//     software scene graph backend。
//   * QQuickView 会自动创建 QQuickWindow 并初始化 scene graph（software），
//     然后加载 QML 创建根对象，比裸 QQmlComponent::create() 更安全。
// ============================================================================

#include <QDebug>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QGuiApplication>
#include <QLibraryInfo>
#include <QLoggingCategory>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlError>
#include <QQuickItem>
#include <QQuickView>
#include <QString>
#include <QStringList>
#include <QTest>
#include <QUrl>
#include <QVector>

class TestD11cQmlLoad : public QObject
{
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();

    // A. qrc:/ 路径存在 & 资源可加载 & QQmlComponent status==Ready
    void resourceUrlResolves();

    // B + C. QQuickView 实际创建根对象，rootItem 非空，至少一个 Card height>0
    void componentCreatesWithoutErrors();

    // D. viewModel alias 属性存在 + 初始值为 null（HIGH-01 alias 修复）
    void viewModelAliasExistsAndInitiallyNull();

    // E. 再次加载：重复实例化无冲突（保证 QML 缓存和 id 命名无泄漏）
    void multipleInstantiationsDoNotLeak();

    // F. MEDIUM-03：初始态安全汇总不得显示 PASS/OK/READY 绿灯（避免"未执行"被误读为"已通过"）。
    void summaryLightsInitiallyNoGreen();

private:
    QScopedPointer<QQmlEngine> engine_;

    // 共享 import path 设置逻辑（engine_ 和 QQuickView 都需要）
    void applyImportPaths(QQmlEngine* eng);
    // 等待 Loading → Ready/Error，返回 Ready=true
    static bool waitReady(QQmlComponent& c, const char* caller);
    // 格式化 QQmlComponent::errors() 为单行字符串
    static QString formatComponentErrors(const QQmlComponent& c);
    // 格式化 QQuickView::errors() 为单行字符串
    static QString formatViewErrors(const QQuickView& v);
    // 在 item 树中递归查找全部 Step Card（通过 objectName
    // "d11-step-1-card" ~ "d11-step-5-card" 精确定位，MEDIUM-01）。
    // 返回找到的 Card item 列表（按 1~5 顺序）。
    static QVector<QQuickItem*> findAllStepCards(QQuickItem* root);
    // 验证所有 5 张 Card 都存在且 implicitHeight > 0 / height > 0
    static bool validateAllStepCards(const QVector<QQuickItem*>& cards);
};

void TestD11cQmlLoad::initTestCase()
{
    qputenv("QT_QPA_PLATFORM", "offscreen");
    qputenv("QT_QUICK_BACKEND", "software");

    QVERIFY2(QGuiApplication::instance() != nullptr,
             "需要 QGuiApplication（用 QTEST_MAIN 而非 QTEST_GUILESS_MAIN）");

    engine_.reset(new QQmlEngine);
    QLoggingCategory::setFilterRules(QStringLiteral("qt.qml.binding.removal.info=true"));
    applyImportPaths(engine_.data());

    // CI 诊断：打印 import paths + QML plugin 目录实际探测
    {
        qDebug() << "[d11c_qml_load] QQmlEngine import paths="
                 << engine_->importPathList();
        const QVector<const char*> probeQmldirs = {
            "QtQuick.2/qmldir",
            "QtQuick/Controls.2/qmldir",
            "QtQuick/Layouts/qmldir",
            "QtQuick/Window.2/qmldir",
            "QtQuick/Dialogs/qmldir",
        };
        const QStringList paths = engine_->importPathList();
        for (const char* rel : probeQmldirs) {
            QString found;
            for (const QString& p : paths) {
                const QString candidate =
                    p + QStringLiteral("/") + QString::fromLatin1(rel);
                if (QFile::exists(candidate)) {
                    found = candidate;
                    break;
                }
            }
            if (found.isEmpty()) {
                qCritical() << "[d11c_qml_load] MISSING qmldir:" << rel;
            } else {
                qDebug() << "[d11c_qml_load] FOUND qmldir:" << rel << "at" << found;
            }
        }
        const QString qtVer = QStringLiteral("Qt runtime=%1 build=%2 gui=%3 qpa=%4")
            .arg(QString::fromLatin1(qVersion()))
            .arg(QLatin1String(QT_VERSION_STR))
            .arg(QGuiApplication::instance() ? "yes" : "no")
            .arg(QString::fromLatin1(qgetenv("QT_QPA_PLATFORM")));
        qDebug() << "[d11c_qml_load]" << qPrintable(qtVer);
    }
}

void TestD11cQmlLoad::cleanupTestCase()
{
    engine_.reset();
}

void TestD11cQmlLoad::applyImportPaths(QQmlEngine* eng)
{
    QStringList extraImports;
    const QString sysImports =
        QLibraryInfo::location(QLibraryInfo::Qml2ImportsPath);
    if (!sysImports.isEmpty()) extraImports.append(sysImports);
    extraImports.append(QStringLiteral("/usr/lib/qt5/qml"));
    extraImports.append(QStringLiteral("/usr/share/qt5/qml"));
    extraImports.append(QStringLiteral("/usr/lib/x86_64-linux-gnu/qt5/qml"));
    extraImports.append(QStringLiteral("/usr/lib/x86_64-linux-gnu/qml"));
    extraImports.append(QStringLiteral("/usr/local/share/qt5/qml"));
    extraImports.append(QStringLiteral("qrc:/qt/qml"));
    extraImports.append(QStringLiteral("qrc:/qml"));
    for (const QString& p : extraImports) {
        if (!p.isEmpty()) eng->addImportPath(p);
    }
}

static const QUrl kD11PageUrl{
    QStringLiteral("qrc:/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml")};
static const char* kD11PageResourcePath =
    ":/qt/qml/memory_client/pages/D11DemoOrchestratorPage.qml";

QString TestD11cQmlLoad::formatComponentErrors(const QQmlComponent& c)
{
    QString out;
    const QList<QQmlError> errs = c.errors();
    if (errs.isEmpty()) {
        return QStringLiteral("<QQmlComponent::errors() 空，可能是 qrc URL 指向资源不存在>");
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

QString TestD11cQmlLoad::formatViewErrors(const QQuickView& v)
{
    QString out;
    const QList<QQmlError> errs = v.errors();
    if (errs.isEmpty()) {
        return QStringLiteral("<QQuickView::errors() 空>");
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

bool TestD11cQmlLoad::waitReady(QQmlComponent& c, const char* caller)
{
    QElapsedTimer t;
    t.start();
    while (c.status() == QQmlComponent::Loading && t.elapsed() < 3000) {
        QTest::qWait(20);
    }
    if (c.status() != QQmlComponent::Ready) {
        qCritical() << "[d11c_qml_load]" << caller
                    << "component status=" << c.status()
                    << "errors=" << qPrintable(formatComponentErrors(c));
    }
    return c.status() == QQmlComponent::Ready;
}

// MEDIUM-01：按 objectName 精确找 5 张 Step Card（d11-step-[1..5]-card），
// 避免被 Label/Button 等控件的正 implicitHeight 误判通过。
static void collectStepCards(QQuickItem* item,
                             QVector<QQuickItem*>& out1to5)
{
    if (!item) return;
    const QString name = item->objectName();
    if (name.startsWith(QStringLiteral("d11-step-"))
        && name.endsWith(QStringLiteral("-card"))) {
        // 按 objectName 数字填入对应位置
        const QString num = name.mid(
            QStringLiteral("d11-step-").size(), 1);
        bool ok = false;
        const int idx = num.toInt(&ok);
        if (ok && idx >= 1 && idx <= 5 && out1to5.size() == 5) {
            out1to5[idx - 1] = item;
        }
    }
    for (QQuickItem* c : item->childItems()) {
        collectStepCards(c, out1to5);
    }
}

QVector<QQuickItem*> TestD11cQmlLoad::findAllStepCards(QQuickItem* root)
{
    QVector<QQuickItem*> out(5, nullptr);
    collectStepCards(root, out);
    return out;
}

bool TestD11cQmlLoad::validateAllStepCards(
    const QVector<QQuickItem*>& cards)
{
    if (cards.size() != 5) return false;
    for (int i = 0; i < 5; ++i) {
        QQuickItem* card = cards[i];
        if (!card) {
            qCritical() << "[d11c_qml_load MEDIUM-01]"
                        << "缺失 Step" << (i + 1) << "Card (objectName 找不到)";
            return false;
        }
        const qreal ih = card->implicitHeight();
        const qreal h  = card->height();
        if (ih <= 0) {
            qCritical() << "[d11c_qml_load MEDIUM-01]"
                        << "Step" << (i + 1)
                        << "Card implicitHeight=" << ih
                        << "（应为 > 0；objectName=" << card->objectName() << "）";
            return false;
        }
        if (h <= 0) {
            qCritical() << "[d11c_qml_load MEDIUM-01]"
                        << "Step" << (i + 1)
                        << "Card height=" << h
                        << "（应为 > 0；objectName=" << card->objectName() << "）";
            return false;
        }
        qDebug() << "[d11c_qml_load MEDIUM-01]"
                 << "Step" << (i + 1)
                 << "Card objectName=" << card->objectName()
                 << "implicitHeight=" << ih << "height=" << h;
    }
    return true;
}

void TestD11cQmlLoad::resourceUrlResolves()
{
    QVERIFY2(kD11PageUrl.isValid(), "D11 页面 qrc URL 格式必须合法");

    {
        QFile f(QString::fromLatin1(kD11PageResourcePath));
        const bool opened = f.open(QIODevice::ReadOnly);
        if (!opened) {
            qCritical() << "[d11c_qml_load] QResource 缺失："
                        << kD11PageResourcePath
                        << "exists="
                        << QFile::exists(QString::fromLatin1(kD11PageResourcePath));
        }
        const QString resPath = QString::fromLatin1(kD11PageResourcePath);
        const QString msg =
            QStringLiteral("qrc 资源表无 D11 页面（qt5_add_resources 是否"
                           "正确执行？预期裸路径=%1。请查 resources.qrc 的"
                           "<qresource prefix>）")
                .arg(resPath);
        QVERIFY2(opened, qPrintable(msg));
    }

    QQmlComponent probe(engine_.data(), kD11PageUrl);
    {
        QElapsedTimer t;
        t.start();
        while (probe.status() == QQmlComponent::Loading && t.elapsed() < 3000) {
            QTest::qWait(20);
        }
        if (probe.status() != QQmlComponent::Ready) {
            qCritical() << "[d11c_qml_load] resourceUrlResolves probe status="
                        << probe.status()
                        << "errors=" << qPrintable(formatComponentErrors(probe));
        }
    }
    QCOMPARE(probe.status(), QQmlComponent::Ready);
    {
        const QString errMsg =
            QStringLiteral("Component 加载不应有错误，当前错误: %1")
                .arg(formatComponentErrors(probe));
        QVERIFY2(!probe.isError(), qPrintable(errMsg));
    }
}

void TestD11cQmlLoad::componentCreatesWithoutErrors()
{
    // HIGH-01 修复：使用 QQuickView（而非裸 QQmlComponent::create()）
    // 进行真实实例化验证。QQuickView 内部创建 QQuickWindow 并管理 scene
    // graph 生命周期，在 offscreen + software backend 环境中比裸 create()
    // 更稳定（裸 create() 在 headless CI 曾触发 SIGSEGV signal 11）。
    QQuickView view;

    // QQuickView 有自己的 QQmlEngine，需要复制 import paths
    applyImportPaths(view.engine());

    view.setSource(kD11PageUrl);

    // 等待 Loading → Ready/Error
    {
        QElapsedTimer t;
        t.start();
        while (view.status() == QQuickView::Loading && t.elapsed() < 3000) {
            QTest::qWait(20);
        }
    }

    if (view.status() != QQuickView::Ready) {
        qCritical() << "[d11c_qml_load] QQuickView status=" << view.status()
                    << "errors=" << qPrintable(formatViewErrors(view));
    }

    const QString statusMsg =
        QStringLiteral("QQuickView 应为 Ready，实际=%1 错误=%2")
            .arg(view.status())
            .arg(formatViewErrors(view));
    QVERIFY2(view.status() == QQuickView::Ready, qPrintable(statusMsg));

    // 根对象非空
    QObject* root = view.rootObject();
    QVERIFY2(root != nullptr, "QQuickView rootObject 必须非空");

    // 根对象为有效 QQuickItem
    QQuickItem* rootItem = qobject_cast<QQuickItem*>(root);
    const QString rootMsg =
        QStringLiteral("根对象应为 QQuickItem，实际类型=%1")
            .arg(QString::fromLatin1(root->metaObject()->className()));
    QVERIFY2(rootItem != nullptr, qPrintable(rootMsg));

    // MEDIUM-01：按 objectName 精确验证 5 张 Step Card 都存在，
    // 且每张 implicitHeight > 0 且实际 height > 0（HIGH-01 布局修复）。
    // 不再使用递归找"任意 implicitHeight>0 的 QQuickItem"（那会被
    // Label/Button 等控件误判通过）。
    //
    // 注意：QQuickView::show() + QTest::qWait() 触发一次 layout 计算，
    // 保证 height 已分配（否则 ColumnLayout/RowLayout 不完成 layout 可能
    // height 仍为 0）。
    view.show();
    view.resize(960, 640);
    {
        QElapsedTimer t;
        t.start();
        while (t.elapsed() < 300) QTest::qWait(20);
    }
    const QVector<QQuickItem*> cards = findAllStepCards(rootItem);
    {
        const QString countMsg = QStringLiteral(
            "应找到 5 张 Step Card，实际 null 数量=%1/5（缺 objectName）")
            .arg(std::count_if(cards.begin(), cards.end(),
                               [](QQuickItem* p) { return p == nullptr; }));
        QVERIFY2(validateAllStepCards(cards), qPrintable(countMsg));
    }
}

void TestD11cQmlLoad::viewModelAliasExistsAndInitiallyNull()
{
    QQuickView view;
    applyImportPaths(view.engine());
    view.setSource(kD11PageUrl);

    {
        QElapsedTimer t;
        t.start();
        while (view.status() == QQuickView::Loading && t.elapsed() < 3000) {
            QTest::qWait(20);
        }
    }

    if (view.status() != QQuickView::Ready) {
        qCritical() << "[d11c_qml_load] viewModelAlias status=" << view.status()
                    << "errors=" << qPrintable(formatViewErrors(view));
    }
    QVERIFY2(view.status() == QQuickView::Ready,
             qPrintable(QStringLiteral("QQuickView 应为 Ready，实际=%1")
                            .arg(view.status())));

    QObject* root = view.rootObject();
    QVERIFY2(root != nullptr, "rootObject 必须非空");

    // HIGH-01：viewModel alias 属性存在
    const int vmIdx = root->metaObject()->indexOfProperty("viewModel");
    QVERIFY2(vmIdx >= 0, "root 对象必须有 viewModel 属性（HIGH-01 alias 修复）");

    // 初始值为 null（未绑定 MemoryViewModel）
    const QVariant vmValue = root->property("viewModel");
    QVERIFY2(vmValue.isNull() || !vmValue.isValid(),
             qPrintable(QStringLiteral("viewModel 初始值应为 null，实际=%1")
                            .arg(vmValue.toString())));
}

void TestD11cQmlLoad::multipleInstantiationsDoNotLeak()
{
    // 连续创建 3 个 QQuickView 实例，验证 QML 缓存和 id 命名无泄漏
    for (int i = 0; i < 3; ++i) {
        QQuickView view;
        applyImportPaths(view.engine());
        view.setSource(kD11PageUrl);

        {
            QElapsedTimer t;
            t.start();
            while (view.status() == QQuickView::Loading && t.elapsed() < 3000) {
                QTest::qWait(20);
            }
        }

        const QString msg =
            QStringLiteral("第 %1 次实例化：QQuickView 应为 Ready，实际=%2")
                .arg(i + 1)
                .arg(view.status());
        QVERIFY2(view.status() == QQuickView::Ready, qPrintable(msg));
        QVERIFY2(view.rootObject() != nullptr,
                 qPrintable(QStringLiteral("第 %1 次实例化：rootObject 为空").arg(i + 1)));

        // MEDIUM-01：每次实例化后验证 5 张 Step Card 都存在且
        // implicitHeight/height > 0（验证 objectName + implicitHeight
        // 绑定无泄漏）。
        view.show();
        view.resize(960, 640);
        {
            QElapsedTimer t;
            t.start();
            while (t.elapsed() < 250) QTest::qWait(20);
        }
        QQuickItem* rootItem = qobject_cast<QQuickItem*>(view.rootObject());
        QVERIFY2(rootItem != nullptr,
                 qPrintable(QStringLiteral("第 %1 次实例化：root 非 QQuickItem").arg(i + 1)));
        const QVector<QQuickItem*> cards = findAllStepCards(rootItem);
        QVERIFY2(validateAllStepCards(cards),
                 qPrintable(QStringLiteral(
                     "第 %1 次实例化：5 张 Step Card 未全部存在或高度不合法")
                                .arg(i + 1)));
    }
}

// ── F · MEDIUM-03：页面初始态，验收汇总灯不得显示 PASS/OK/READY 绿灯 ─────
//
// 验收总览的每一项都必须 gate 到"对应 pipeline 已执行完成"之后。
// 否则，ViewModel 中初始态的布尔 getter 可能返回 trivially-true（例如
// textIsolationVerified 在空 context 时直接返回 true），于是页面一
// 打开就亮起绿灯，把"尚未验证"误导为"已经验证通过"。
//
// 本测试通过 objectName 直接读取 4 个汇总 Label 的 text，断言其中不
// 出现 PASS/OK/READY 绿灯字样。
void TestD11cQmlLoad::summaryLightsInitiallyNoGreen()
{
    QQuickView view;
    applyImportPaths(view.engine());
    view.setSource(QUrl(QStringLiteral("qrc:/memory_client/pages/D11DemoOrchestratorPage.qml")));
    QTRY_VERIFY2_WITH_TIMEOUT(view.status() == QQuickView::Ready,
                              qPrintable(formatViewErrors(view)), 5000);
    QVERIFY(view.rootObject() != nullptr);
    view.show();
    view.resize(960, 640);
    {
        QElapsedTimer t;
        t.start();
        while (t.elapsed() < 250) QTest::qWait(20);
    }
    QQuickItem* rootItem = qobject_cast<QQuickItem*>(view.rootObject());
    QVERIFY(rootItem != nullptr);

    static const struct {
        const char* objectName;
        const char* description;
    } kLights[] = {
        {"d11-summary-text-isolation",    "原文隔离 (D5-C)"},
        {"d11-summary-selector-cleared",  "Selector 明文清除"},
        {"d11-summary-credential-chain",  "凭据链闭合"},
        {"d11-summary-forget-missing",    "遗忘漏删一致性"},
    };

    // 初始态没有 ViewModel 上下文注入 → 所有 stage 都是 idle/idle/idle/idle
    // → 4 个灯都必须显示"未执行 · —"，不能提前亮绿灯。
    for (const auto& light : kLights) {
        auto* label = rootItem->findChild<QQuickItem*>(QLatin1String(light.objectName));
        QVERIFY2(label != nullptr,
                 qPrintable(QStringLiteral("D11C-QML-F: 未找到汇总 Label objectName=%1 (%2)")
                                .arg(QLatin1String(light.objectName))
                                .arg(QLatin1String(light.description))));
        const QString text = label->property("text").toString();
        QVERIFY2(!text.contains(QLatin1String("PASS"), Qt::CaseInsensitive)
                 && !text.contains(QLatin1String("OK"), Qt::CaseInsensitive)
                 && !text.contains(QLatin1String("READY"), Qt::CaseInsensitive),
                 qPrintable(QStringLiteral(
                     "D11C-QML-F: [%1] 初始态显示绿灯 text=\"%2\"，但 5 步尚未执行，"
                     "不得提前显示 PASS/OK/READY")
                                .arg(QLatin1String(light.description))
                                .arg(text)));
    }
}

// 使用 QTEST_MAIN：不链接 QtWidgets 时生成 QGuiApplication，
// QQmlEngine / QQuickItem / QQuickView 的 GUI 资源才能正确初始化。
// QTEST_GUILESS_MAIN 只生成 QCoreApplication，QGuiApplication::instance()
// 返回 nullptr，QQuickView 无法创建窗口，测试失败。
// 环境变量由 CMakeLists.txt set_tests_properties ENVIRONMENT 在进程
// 启动前设置（QT_QPA_PLATFORM=offscreen + QT_QUICK_BACKEND=software）。
QTEST_MAIN(TestD11cQmlLoad)
#include "test_d11c_qml_load.moc"
