// ContextAssemblePage.qml — Memory Context 组装 Pipeline（D9C，Demo / Prototype）
//
// 依赖：D9C 候选 IPC context.assemble（pending ADR）。
// 状态：本页渲染组装后的 MemoryContext 及其可解释字段（召回来源、记忆类型、
//       冲突/不确定性提示、Token 预算校验）；真实检索后端与 Context 注入未接入。
// 兼容性：目标 Qt 5.12（不使用 5.15+ 语法）。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    function runAssemble() {
        if (userIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 user_id")
            return
        }
        if (queryField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 query_text")
            return
        }
        var budget = parseInt(budgetField.text, 10)
        if (isNaN(budget) || budget <= 0) {
            statusText.text = qsTr("token_budget 必须为正整数")
            return
        }
        viewModel.runContextAssemblePipeline(
            userIdField.text.trim(),
            queryField.text.trim(),
            budget,
            sceneField.text.trim(),
            candidatesField.text.trim())
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
                    text: qsTr("Context Assemble")
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
                    if (viewModel.contextAssembleBusy) parts.push(qsTr("busy: ") + viewModel.contextAssembleStage)
                    else parts.push(qsTr("stage: ") + viewModel.contextAssembleStage)
                    parts.push(qsTr("injection: ") + viewModel.contextInjectionStatus)
                    if (viewModel.contextAssembleError.length > 0) parts.push(qsTr("error: ") + viewModel.contextAssembleError)
                    return parts.join("  |  ")
                }
                color: viewModel.contextAssembleError.length > 0 ? "#c62828" : palette.text
                wrapMode: Text.WordWrap
            }

            // Token 预算校验面板
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label {
                    text: qsTr("Token 预算")
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: viewModel.contextActualTokenCount + " / " + viewModel.contextTokenBudget
                }
                Label {
                    text: viewModel.contextBudgetExceeded ? qsTr(" (超预算)") : qsTr(" (预算内)")
                    color: viewModel.contextBudgetExceeded ? "#c62828" : "#2e7d32"
                    font.bold: true
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("user_id") }
                TextField {
                    id: userIdField
                    Layout.fillWidth: true
                    text: "u1"
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("query_text") }
                TextField {
                    id: queryField
                    Layout.fillWidth: true
                    text: "如何撰写项目周报"
                    placeholderText: qsTr("用户原始查询文本")
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("token_budget") }
                TextField {
                    id: budgetField
                    Layout.preferredWidth: 120
                    text: "800"
                    validator: IntValidator { bottom: 1 }
                }
                Label { text: qsTr("scene") }
                TextField {
                    id: sceneField
                    Layout.fillWidth: true
                    placeholderText: qsTr("可选场景")
                }
                Button {
                    text: viewModel.contextAssembleBusy ? qsTr("…") : qsTr("组装")
                    enabled: viewModel.connectionState === "connected" && !viewModel.contextAssembleBusy
                    onClicked: runAssemble()
                }
            }

            // 可选 candidates（B 轨 RetrievalCandidateSample[] JSON 字符串）
            Label {
                text: qsTr("candidates (可选，JSON 数组)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            TextArea {
                id: candidatesField
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: 80
                wrapMode: TextArea.Wrap
                font.family: "Consolas,Menlo,monospace"
                placeholderText: qsTr('[{"memory_id":"km-1","channels":["fts5","vector"]}]')
            }

            // 召回来源（通道）
            Label {
                text: qsTr("召回来源 (recall_sources)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: recallView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(120, recallView.count * 36 + 8)
                clip: true
                model: viewModel.contextRecallSources
                delegate: Rectangle {
                    width: recallView.width
                    height: 32
                    color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                    radius: 4
                    Label {
                        anchors.fill: parent
                        anchors.margins: 8
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: typeof modelData === "string"
                              ? modelData
                              : JSON.stringify(modelData)
                    }
                }
            }

            // 记忆类型分布
            Label {
                text: qsTr("记忆类型 (memory_types)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: typesView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(120, typesView.count * 36 + 8)
                clip: true
                model: viewModel.contextMemoryTypes
                delegate: Rectangle {
                    width: typesView.width
                    height: 32
                    color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                    radius: 4
                    Label {
                        anchors.fill: parent
                        anchors.margins: 8
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: typeof modelData === "string"
                              ? modelData
                              : JSON.stringify(modelData)
                    }
                }
            }

            // 冲突提示
            Label {
                text: qsTr("冲突提示 (conflict_hints)")
                font.bold: true
                color: viewModel.contextConflictHints.length > 0 ? "#c62828" : palette.text
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: conflictView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(120, conflictView.count * 36 + 8)
                clip: true
                model: viewModel.contextConflictHints
                delegate: Rectangle {
                    width: conflictView.width
                    height: 32
                    color: "#fff3e0"
                    radius: 4
                    Label {
                        anchors.fill: parent
                        anchors.margins: 8
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: typeof modelData === "string"
                              ? modelData
                              : JSON.stringify(modelData)
                    }
                }
            }

            // 不确定性提示
            Label {
                text: qsTr("不确定性提示 (uncertainty_hints)")
                font.bold: true
                color: viewModel.contextUncertaintyHints.length > 0 ? "#ef6c00" : palette.text
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: uncertaintyView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(120, uncertaintyView.count * 36 + 8)
                clip: true
                model: viewModel.contextUncertaintyHints
                delegate: Rectangle {
                    width: uncertaintyView.width
                    height: 32
                    color: "#fff8e1"
                    radius: 4
                    Label {
                        anchors.fill: parent
                        anchors.margins: 8
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                        text: typeof modelData === "string"
                              ? modelData
                              : JSON.stringify(modelData)
                    }
                }
            }

            // 组装结果完整 JSON
            Label {
                text: qsTr("组装结果 (assembled_context)")
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
                text: JSON.stringify(viewModel.assembledContext, null, 2)
            }
        }
    }
}
