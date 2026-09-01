// KnowledgeDetailPage.qml — 知识详情 Pipeline（D8C，Demo / Prototype）
//
// 依赖：D8C 候选 IPC knowledge.detail（pending ADR）。
// 状态：本页仅渲染单条记忆的证据 / 适用条件投影；真实知识后端未接入。
// 兼容性：目标 Qt 5.12（不使用 5.15+ 语法）。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    function runDetail() {
        if (memoryIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 memory_id")
            return
        }
        viewModel.runKnowledgeDetailPipeline(
            memoryIdField.text.trim(),
            evidenceCheck.checked,
            conditionsCheck.checked)
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 8
            Layout.margins: 12

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.topMargin: 12
                Label {
                    text: qsTr("Knowledge Detail")
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
                    if (viewModel.knowledgeDetailBusy) parts.push(qsTr("busy: ") + viewModel.knowledgeDetailStage)
                    else parts.push(qsTr("stage: ") + viewModel.knowledgeDetailStage)
                    if (viewModel.knowledgeDetailError.length > 0) parts.push(qsTr("error: ") + viewModel.knowledgeDetailError)
                    return parts.join("  |  ")
                }
                color: viewModel.knowledgeDetailError.length > 0 ? "#c62828" : palette.text
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
                    id: evidenceCheck
                    checked: true
                    text: qsTr("include_evidence")
                }
                CheckBox {
                    id: conditionsCheck
                    checked: true
                    text: qsTr("include_conditions")
                }
                Button {
                    text: viewModel.knowledgeDetailBusy ? qsTr("…") : qsTr("查询")
                    enabled: viewModel.connectionState === "connected" && !viewModel.knowledgeDetailBusy
                    onClicked: runDetail()
                }
            }

            // 证据列表
            Label {
                text: qsTr("证据 (evidence)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: evidenceView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(160, evidenceView.count * 44 + 8)
                clip: true
                model: viewModel.knowledgeDetail.evidence || []
                delegate: Rectangle {
                    width: evidenceView.width
                    height: 40
                    color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                    radius: 4
                    Label {
                        anchors.fill: parent
                        anchors.margins: 8
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: modelData
                    }
                }
            }

            // 适用条件列表
            Label {
                text: qsTr("适用条件 (conditions)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: conditionsView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(120, conditionsView.count * 40 + 8)
                clip: true
                model: viewModel.knowledgeDetail.conditions || []
                delegate: Rectangle {
                    width: conditionsView.width
                    height: 36
                    color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                    radius: 4
                    Label {
                        anchors.fill: parent
                        anchors.margins: 8
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: modelData
                    }
                }
            }

            // 完整详情 JSON
            Label {
                text: qsTr("完整详情")
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
                text: JSON.stringify(viewModel.knowledgeDetail, null, 2)
            }
        }
    }
}
