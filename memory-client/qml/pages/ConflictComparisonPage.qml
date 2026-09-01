// ConflictComparisonPage.qml — 冲突对比 Pipeline（D8C，Demo / Prototype）
//
// 依赖：D8C 候选 IPC conflict.compare（pending ADR）。
// 状态：本页仅渲染冲突候选列表；真实冲突仲裁后端未接入。
// 兼容性：目标 Qt 5.12（不使用 5.15+ 语法）。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    function runCompare() {
        if (memoryIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 memory_id")
            return
        }
        viewModel.runConflictComparePipeline(
            memoryIdField.text.trim(),
            resolvedCheck.checked)
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
                    text: qsTr("Conflict Comparison")
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
                    if (viewModel.conflictCompareBusy) parts.push(qsTr("busy: ") + viewModel.conflictCompareStage)
                    else parts.push(qsTr("stage: ") + viewModel.conflictCompareStage)
                    if (viewModel.conflictCompareError.length > 0) parts.push(qsTr("error: ") + viewModel.conflictCompareError)
                    return parts.join("  |  ")
                }
                color: viewModel.conflictCompareError.length > 0 ? "#c62828" : palette.text
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("memory_id") }
                TextField {
                    id: memoryIdField
                    Layout.fillWidth: true
                    text: "km-1"
                }
                CheckBox {
                    id: resolvedCheck
                    checked: false
                    text: qsTr("include_resolved")
                }
                Button {
                    text: viewModel.conflictCompareBusy ? qsTr("…") : qsTr("对比")
                    enabled: viewModel.connectionState === "connected" && !viewModel.conflictCompareBusy
                    onClicked: runCompare()
                }
            }

            Label {
                text: qsTr("冲突候选 (%1)").arg(viewModel.conflictCandidates.length)
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: candidatesView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(280, candidatesView.count * 64 + 8)
                clip: true
                model: viewModel.conflictCandidates
                delegate: Rectangle {
                    width: candidatesView.width
                    height: 60
                    color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                    radius: 4
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 2
                        Label {
                            text: qsTr("memory_id: %1").arg(model.memory_id || "")
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Label {
                            text: qsTr("conflict_state: %1  |  score: %2")
                                .arg(model.conflict_state || "")
                                .arg(model.score !== undefined ? model.score : "")
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            // 候选 JSON 原文
            Label {
                text: qsTr("候选 JSON")
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
                text: JSON.stringify(viewModel.conflictCandidates, null, 2)
            }
        }
    }
}
