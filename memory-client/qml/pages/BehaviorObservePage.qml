// BehaviorObservePage.qml — D6-C 多源 Adapter Demo / Prototype：行为观察面板
//
// ⚠️ Demo 声明（沿用 D5-C Route B）：
//   本页仅为 memory-client 侧的 Pipeline Harness / Demo，用于演示
//   BehaviorEvent 的构造与发送。**尚未** 接入真实 AI Assistant Hook。
//   C-D5 保持 OPEN；本 Demo 不关闭 C-D6。
//
// ⚠️ 关键边界（C-E 接口）：
//   behavior → MemorySourceEvent.source_type 映射未冻结；本页显式标注
//   mapping_status="PENDING_C_CONFIRMATION"。不擅自新增 SourceType 枚举。
//   暂用现有 chat 枚举承载 behavior 候选；待 E 轨审查 + ADR 后正式冻结。
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
                text: qsTr("D6-C · Behavior Observe Demo / Prototype（候选 IPC 方法 behavior.observe）")
                font.bold: true
                font.pointSize: 14
                color: "#6a1b9a"
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("⚠️ 生产 Gateway 默认未注册 behavior.observe handler → UNSUPPORTED_METHOD。\n"
                          + "⚠️ behavior → source_type 映射 PENDING_C_CONFIRMATION（C 轨未冻结）。")
                color: "#c62828"
                wrapMode: Text.WordWrap
            }
            Label {
                text: qsTr("Connection: ") + viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }

            GroupBox {
                title: qsTr("Behavior Observe Event")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    RowLayout {
                        Label { text: qsTr("User ID:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: bhUserId; Layout.fillWidth: true
                            text: "local-user"; placeholderText: "user id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Session ID:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: bhSessionId; Layout.fillWidth: true
                            text: "session-behavior-demo"; placeholderText: "session id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Behavior Kind:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: bhKind
                            Layout.fillWidth: true
                            model: ["user_message", "agent_response",
                                    "system_message", "user_action"]
                            currentIndex: 0
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Observed Action:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: bhAction; Layout.fillWidth: true
                            text: "user_clicked_send"; placeholderText: "observed action"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Context Ref:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: bhContextRef; Layout.fillWidth: true
                            text: "ref:behavior:turn-001"; placeholderText: "context ref"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Actor:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: bhActor
                            Layout.fillWidth: true
                            model: ["user", "agent", "system"]
                            currentIndex: 0
                        }
                    }

                    Button {
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        text: viewModel.behaviorBusy
                              ? qsTr("Sending…")
                              : qsTr("Send behavior.observe")
                        highlighted: true
                        enabled: !viewModel.behaviorBusy
                                  && viewModel.connectionState === "connected"
                        onClicked: viewModel.runBehaviorPipeline(
                            bhUserId.text, bhSessionId.text,
                            bhKind.currentText, bhAction.text,
                            bhContextRef.text, bhActor.currentText)
                    }
                }
            }

            GroupBox {
                title: qsTr("Stage & Event")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        text: qsTr("behaviorStage: ") + viewModel.behaviorStage
                        color: viewModel.behaviorStage === "sent" ? "#2e7d32"
                               : (viewModel.behaviorStage === "failed"
                                  || viewModel.behaviorStage === "timeout"
                                  ? "#c62828" : "#1565c0")
                    }
                    Label {
                        text: qsTr("behaviorBusy: ")
                              + (viewModel.behaviorBusy ? "true" : "false")
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Last BehaviorEvent JSON:")
                        font.bold: true
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 220
                        TextArea {
                            readOnly: true
                            text: viewModel.lastBehaviorEvent
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
