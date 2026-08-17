// main.cpp — Memory Client QML 入口（D4 骨架）
//
// 职责：注册 kylin.memory 1.0 QML 模块，加载 qml/main.qml。
// 不内嵌业务逻辑；ViewModel 与 MemoryClient 在 C++ 侧定义。

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QtQml>

#include "memory_client.h"
#include "view_models/memory_view_model.h"

namespace client = kylin::memory::client::v1;

int main(int argc, char* argv[])
{
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationName(QStringLiteral("kylin-memory-client"));
    QGuiApplication::setApplicationVersion(QStringLiteral("0.1.0-d4-skeleton"));

    qmlRegisterType<client::MemoryViewModel>("kylin.memory", 1, 0, "MemoryViewModel");
    qmlRegisterUncreatableType<client::MemoryClient>(
        "kylin.memory", 1, 0, "MemoryClient",
        QStringLiteral("MemoryClient is created by MemoryViewModel internally."));

    QQmlApplicationEngine engine;
    engine.load(QUrl(QStringLiteral("qrc:/qt/qml/memory_client/qml/main.qml")));
    if (engine.rootObjects().isEmpty()) {
        return -1;
    }
    return QGuiApplication::exec();
}
