// LifecycleStatusPage.qml — 生命周期状态 Pipeline（D8C，Demo / Prototype）
//
// 依赖：D8C 候选 IPC lifecycle.status（pending ADR）。
// 状态：本页仅渲染按 user_id/memory_status 过滤的记忆条目；真实生命周期后端未接入。
// 兼容性：目标 Qt 5.12（不使用 5.15+ 语法）。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    function runStatus() {
        if (userIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 user_id")
            return
        }
        viewModel.runLifecycleStatusPipeline(
            userIdField.text.trim(),
            memoryIdField.text.trim(),
            statusCombo.currentText)
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.topMargin: 12
                Label {
                    text: qsTr("Lifecycle Status")
                    font.bold: true
                    font.pointSize: 16
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: qsTr("Connection: ") + viewModel.connectionState
                    color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
                }
            }

            Label {
                id: statusText
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                text: {
                    var parts = []
                    if (viewModel.lifecycleStatusBusy) parts.push(qsTr("busy: ") + viewModel.lifecycleStatusStage)
                    else parts.push(qsTr("stage: ") + viewModel.lifecycleStatusStage)
                    if (viewModel.lifecycleStatusError.length > 0) parts.push(qsTr("error: ") + viewModel.lifecycleStatusError)
                    return parts.join("  |  ")
                }
                color: viewModel.lifecycleStatusError.length > 0 ? "#c62828" : palette.text
                wrapMode: Text.WordWrap
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                columns: 4
                Label { text: qsTr("user_id") }
                TextField {
                    id: userIdField
                    Layout.fillWidth: true
                    text: "local-user"
                }
                Label { text: qsTr("memory_id") }
                TextField {
                    id: memoryIdField
                    Layout.fillWidth: true
                    placeholderText: qsTr("可选")
                }
                Label { text: qsTr("memory_status") }
                ComboBox {
                    id: statusCombo
                    Layout.fillWidth: true
                    model: ["", "active", "candidate", "superseded", "archived"]
                }
                Button {
                    text: viewModel.lifecycleStatusBusy ? qsTr("…") : qsTr("查询")
                    enabled: viewModel.connectionState === "connected" && !viewModel.lifecycleStatusBusy
                    onClicked: runStatus()
                }
            }

            Label {
                text: qsTr("生命周期条目 (%1)").arg(viewModel.lifecycleItems.length)
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: itemsView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(280, itemsView.count * 64 + 8)
                clip: true
                model: viewModel.lifecycleItems
                delegate: Rectangle {
                    width: itemsView.width
                    height: 60
                    color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                    radius: 4
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 2
                        Label {
                            text: qsTr("memory_id: %1  |  status: %2")
                                .arg(model.memory_id || "")
                                .arg(model.memory_status || "")
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Label {
                            text: qsTr("version: %1  |  updated_at: %2")
                                .arg(model.version !== undefined ? model.version : "")
                                .arg(model.updated_at || "")
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            // 条目 JSON 原文
            Label {
                text: qsTr("条目 JSON")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            TextArea {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.bottomMargin: 12
                readOnly: true
                wrapMode: TextArea.Wrap
                font.family: "Consolas,Menlo,monospace"
                text: JSON.stringify(viewModel.lifecycleItems, null, 2)
            }
        }
    }
}
