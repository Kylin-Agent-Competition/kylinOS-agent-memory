// ToolAdapterPage.qml — D6-C 多源 Adapter Demo / Prototype：Tool Adapter 面板
//
// ⚠️ Demo 声明（沿用 D5-C Route B）：
//   本页仅为 memory-client 侧的 Pipeline Harness / Demo，用于演示
//   ToolExecutionEvent 的构造与发送。**尚未** 证明接入真实 AI Assistant
//   Hook / sendToolMessage 路径。C-D5 保持 OPEN；本 Demo 不关闭 C-D6。
//
// 演示范围：
//   ① 五状态 Tool 事件构造（success / partial / failure / cancelled / timeout）
//   ② tool.execution 候选 IPC 方法发送（生产 Gateway 默认未注册 → UNSUPPORTED_METHOD）
//   ③ 状态机展示：idle / sending / timeout / sent / failed
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    ScrollView {
        anchors.fill: parent
        clip: true

        ColumnLayout {
            width: root.width
            spacing: 8
            leftPadding: 12
            rightPadding: 12
            topPadding: 12
            bottomPadding: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("D6-C · Tool Adapter Demo / Prototype（候选 IPC 方法 tool.execution）")
                font.bold: true
                font.pointSize: 14
                color: "#6a1b9a"
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("⚠️ 生产 Gateway 默认未注册 tool.execution handler → UNSUPPORTED_METHOD（符合预期）。")
                color: "#c62828"
                wrapMode: Text.WordWrap
            }
            Label {
                text: qsTr("Connection: ") + viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }

            // ── Tool 事件构造表单 ──────────────────────────────────────────
            GroupBox {
                title: qsTr("Tool Execution Event")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    RowLayout {
                        Label { text: qsTr("User ID:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolUserId; Layout.fillWidth: true
                            text: "local-user"; placeholderText: "user id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Session ID:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolSessionId; Layout.fillWidth: true
                            text: "session-tool-demo"; placeholderText: "session id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Turn ID:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolTurnId; Layout.fillWidth: true
                            text: "turn-tool-001"; placeholderText: "turn id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Tool Call ID:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolCallId; Layout.fillWidth: true
                            text: "tool-call-001"; placeholderText: "tool call id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Tool Name:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolName; Layout.fillWidth: true
                            text: "calendar.lookup"; placeholderText: "tool name"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Execution Status:"); Layout.preferredWidth: 110 }
                        ComboBox {
                            id: toolStatus
                            Layout.fillWidth: true
                            model: ["success", "partial", "failure", "cancelled", "timeout"]
                            currentIndex: 0
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Arguments Ref:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolArgsRef; Layout.fillWidth: true
                            text: "ref:tool-arguments:001"; placeholderText: "arguments ref"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Result Ref:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolResultRef; Layout.fillWidth: true
                            text: "ref:tool-result:001"; placeholderText: "result ref"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Error Type:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolErrorType; Layout.fillWidth: true
                            placeholderText: "留空（success/无错误时）"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Error Message:"); Layout.preferredWidth: 110 }
                        TextField {
                            id: toolErrorMsg; Layout.fillWidth: true
                            placeholderText: "安全消息（不回显原文）"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Side Effect:"); Layout.preferredWidth: 110 }
                        Switch { id: toolSideEffect; checked: false }
                    }
                    RowLayout {
                        Label { text: qsTr("Rollback Required:"); Layout.preferredWidth: 110 }
                        Switch { id: toolRollback; checked: false }
                    }

                    Button {
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        text: viewModel.toolBusy ? qsTr("Sending…") : qsTr("Send tool.execution")
                        highlighted: true
                        enabled: !viewModel.toolBusy
                                  && viewModel.connectionState === "connected"
                        onClicked: viewModel.runToolPipeline(
                            toolUserId.text, toolSessionId.text, toolTurnId.text,
                            toolCallId.text, toolName.text, toolStatus.currentText,
                            toolArgsRef.text, toolResultRef.text,
                            toolErrorType.text, toolErrorMsg.text,
                            toolSideEffect.checked, toolRollback.checked)
                    }
                }
            }

            // ── 状态 + 事件预览 ─────────────────────────────────────────────
            GroupBox {
                title: qsTr("Stage & Event")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        text: qsTr("toolStage: ") + viewModel.toolStage
                        color: viewModel.toolStage === "sent" ? "#2e7d32"
                               : (viewModel.toolStage === "failed" || viewModel.toolStage === "timeout"
                                  ? "#c62828" : "#1565c0")
                    }
                    Label {
                        text: qsTr("toolBusy: ") + (viewModel.toolBusy ? "true" : "false")
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Last ToolExecutionEvent JSON:")
                        font.bold: true
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 240
                        TextArea {
                            readOnly: true
                            text: viewModel.lastToolEvent
                            font.family: "Consolas, Menlo, monospace"
                            wrapMode: Text.WrapAnywhere
                            background: Rectangle { color: "#fafafa"; border.color: "#ddd" }
                        }
                    }
                }
            }
        }
    }
}
