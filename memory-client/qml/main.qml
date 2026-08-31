// main.qml — Memory Client 主窗口（D4 骨架）
//
// 状态：L0 骨架；仅提供路由与 ViewModel 绑定演示。
// 真实业务字段（偏好/知识/冲突/遗忘）未在此处固化，待 E 轨业务 Schema 终审。
//
// 路由模型：StackView + 侧边 Drawer，page 通过 replace 切换。
// ViewModel：通过 C++ 注册的 kylin.memory.MemoryViewModel 类型由 QML 实例化。
//
// 兼容性：目标 Qt 5.12（不使用 5.15+ 内联 component / function 信号语法）。

import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0
import "pages"

ApplicationWindow {
    id: window
    visible: true
    width: 960
    height: 640
    title: qsTr("Kylin Memory Client — D4 Skeleton")

    // 公共 ViewModel（C++ 注册，全页面共享）
    // socketPath 不在此覆盖——走 C++ 构造函数默认值（$XDG_RUNTIME_DIR/kylin-memory/memory.sock，
    // FRZ-IPC-005 冻结路径）。如需测试 Mock Gateway，通过 ViewModel.setSocketPath() 设置。
    property MemoryViewModel viewModel: MemoryViewModel {}

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            Label {
                text: qsTr("Kylin Memory Client")
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Label {
                text: viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }
            Label { text: "  |  " }
            Label {
                text: viewModel.lastError
                color: "#c62828"
                Layout.maximumWidth: 320
                elide: Text.ElideRight
            }
            ToolButton {
                text: viewModel.busy ? qsTr("…") : qsTr("Health")
                enabled: !viewModel.busy && viewModel.connectionState === "connected"
                onClicked: viewModel.sendHealth()
            }
        }
    }

    StackView {
        id: stack
        anchors.fill: parent
        initialItem: statusPage
    }

    Drawer {
        id: navDrawer
        width: 240
        height: window.height
        edge: Qt.LeftEdge

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 4

            Label {
                text: qsTr("Navigation")
                font.bold: true
                Layout.bottomMargin: 8
            }

            Button {
                Layout.fillWidth: true
                flat: true
                text: qsTr("Status")
                onClicked: stack.replace(statusPage)
            }
            Button {
                Layout.fillWidth: true
                flat: true
                text: qsTr("Memory Query")
                onClicked: stack.replace(queryPage)
            }
            Button {
                Layout.fillWidth: true
                flat: true
                text: qsTr("Preferences")
                onClicked: stack.replace(prefPage)
            }
            // D5-C 首个真实垂直链路：Pre-Chat + Post-Turn + 原文隔离验证
            Button {
                Layout.fillWidth: true
                flat: true
                highlighted: true
                text: qsTr("D5 Vertical Link")
                onClicked: stack.replace(verticalLinkPage)
            }
            // D6-C 多源 Adapter Demo（Tool / Manual Config / Behavior）
            Button {
                Layout.fillWidth: true
                flat: true
                text: qsTr("D6 Tool Adapter")
                onClicked: stack.replace(toolAdapterPage)
            }
            Button {
                Layout.fillWidth: true
                flat: true
                text: qsTr("D6 Manual Config")
                onClicked: stack.replace(manualConfigPage)
            }
            Button {
                Layout.fillWidth: true
                flat: true
                text: qsTr("D6 Behavior Observe")
                onClicked: stack.replace(behaviorObservePage)
            }
            // D7-C 偏好版本管理 Demo（Commit / History / Rollback + 跨会话行为联调）
            Button {
                Layout.fillWidth: true
                flat: true
                highlighted: true
                text: qsTr("D7 Preference Version")
                onClicked: stack.replace(preferenceVersionPage)
            }
            Item { Layout.fillHeight: true }
            Button {
                Layout.fillWidth: true
                text: viewModel.connectionState === "connected"
                      ? qsTr("Disconnect")
                      : qsTr("Connect")
                highlighted: true
                onClicked: {
                    if (viewModel.connectionState === "connected") {
                        viewModel.disconnectFromService()
                    } else {
                        viewModel.connectToService()
                    }
                }
            }
        }
    }

    Component { id: statusPage; StatusPage { viewModel: window.viewModel } }
    Component { id: queryPage; MemoryQueryPage { viewModel: window.viewModel } }
    Component { id: prefPage; PreferenceEditorPage { viewModel: window.viewModel } }
    Component { id: verticalLinkPage; VerticalLinkPage { viewModel: window.viewModel } }
    // D6-C 多源 Adapter Demo 页面
    Component { id: toolAdapterPage; ToolAdapterPage { viewModel: window.viewModel } }
    Component { id: manualConfigPage; ManualConfigPage { viewModel: window.viewModel } }
    Component { id: behaviorObservePage; BehaviorObservePage { viewModel: window.viewModel } }
    // D7-C 偏好版本管理 Demo 页面
    Component { id: preferenceVersionPage; PreferenceVersionPage { viewModel: window.viewModel } }

    // 连接错误与请求失败统一弹出提示（不展示原始正文/凭据）。
    // Qt 5.12 风格：信号参数按名直接可见。
    Connections {
        target: viewModel
        onConnectionStateChanged: {
            statusToast.show(qsTr("Connection: ") + viewModel.connectionState)
        }
        onConnectionError: {
            statusToast.show(safeMessage)
        }
        onRequestFailed: {
            statusToast.show(errorCode + " — " + safeMessage)
        }
    }

    // 简单 Toast（L0 骨架：不引入额外依赖）
    Drawer {
        id: statusToast
        property string message: ""
        function show(msg) {
            message = msg
            open()
            toastTimer.restart()
        }
        edge: Qt.TopEdge
        height: 48
        width: window.width
        modal: false
        closePolicy: Popup.CloseOnEscape
        Label {
            anchors.centerIn: parent
            text: statusToast.message
        }
        Timer {
            id: toastTimer
            interval: 2200
            repeat: false
            onTriggered: statusToast.close()
        }
    }

    // 首次启动提示连接
    Component.onCompleted: statusToast.show(qsTr("Ready. Open drawer to connect."))
}
