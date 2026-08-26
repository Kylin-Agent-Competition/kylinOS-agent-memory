// VerticalLinkPage.qml — D5-C 首个真实垂直链路演示
//
// 目标（台账 D5-C，完成定义：AI 助手最小 Pre/Post 链路在虚拟机真实工作）：
//   ① 打通 用户输入 → Pre-Chat (memory.retrieve → MemoryContext) → 模型请求
//   ② 打通 最终回答 → Post-Turn (TurnFinalizedEvent → memory.store) → 观察
//   ③ 验证 UI/聊天库保存原文，不保存 Memory Context（三路口径隔离面板）
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // ====================================================================
        // 标题 + 连接状态
        // ====================================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Label {
                text: qsTr("D5-C · Vertical Link (Pre-Chat ⇄ Post-Turn)")
                font.bold: true
                font.pointSize: 15
            }
            Item { Layout.fillWidth: true }
            Label {
                text: qsTr("Gateway: ") + viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }
            Label { text: "  |  Busy: " + (viewModel.busy ? "yes" : "no") }
        }

        // ====================================================================
        // Tab 1：Pre-Chat 链路
        // ====================================================================
        Frame {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: qsTr("① Pre-Chat Pipeline")
                        font.bold: true
                        font.pointSize: 12
                    }
                    Label {
                        text: qsTr("Stage: ") + viewModel.preChatStage
                        color: (viewModel.preChatStage === "ready")
                               ? "#2e7d32"
                               : (viewModel.preChatStage === "failed" ? "#c62828" : "#616161")
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: qsTr("Reset")
                        onClicked: viewModel.resetPreChatPipeline()
                    }
                }

                GridLayout {
                    columns: 2
                    Layout.fillWidth: true
                    columnSpacing: 10
                    rowSpacing: 6

                    Label { text: qsTr("user_id") }
                    TextField {
                        id: preUserId
                        Layout.fillWidth: true
                        text: "local-user"
                    }
                    Label { text: qsTr("session_id") }
                    TextField {
                        id: preSessionId
                        Layout.fillWidth: true
                        text: "session-demo-" + Math.floor(Math.random() * 1000)
                    }
                    Label { text: qsTr("scene") }
                    TextField {
                        id: preScene
                        Layout.fillWidth: true
                        text: "software_development"
                    }
                    Label { text: qsTr("max_context_tokens") }
                    SpinBox {
                        id: preMaxTokens
                        from: 1; to: 8192; value: 800
                    }
                }

                Label {
                    text: qsTr("用户原文 (originalUserText — 用于 UI/聊天库保存)")
                    font.bold: true
                }
                TextArea {
                    id: userOriginalInput
                    Layout.fillWidth: true
                    Layout.minimumHeight: 70
                    wrapMode: TextArea.Wrap
                    placeholderText: qsTr("输入原文，例如：帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点")
                    text: qsTr("帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点")
                }

                RowLayout {
                    Layout.fillWidth: true
                    Button {
                        text: viewModel.busy
                              ? qsTr("Running Pre-Chat…")
                              : qsTr("⟶ Run Pre-Chat (memory.retrieve → Context)")
                        highlighted: true
                        enabled: viewModel.connectionState === "connected" && !viewModel.busy
                        onClicked: {
                            viewModel.runPreChatPipeline(
                                preUserId.text,
                                preSessionId.text,
                                preScene.text,
                                preMaxTokens.value,
                                userOriginalInput.text)
                        }
                    }
                    Item { Layout.fillWidth: true }
                    Label { text: qsTr("lastRequestId: ") + viewModel.lastRequestId
                            elide: Text.ElideMiddle; Layout.maximumWidth: 420 }
                }

                // ── Pre-Chat 三路口径对比 ──────────────────────────────
                Label {
                    text: qsTr("三路口径对比（原文隔离验证）")
                    font.bold: true
                    Layout.topMargin: 6
                }

                GridLayout {
                    columns: 2
                    rows: 3
                    Layout.fillWidth: true
                    Layout.minimumHeight: 320
                    columnSpacing: 10
                    rowSpacing: 6

                    Label {
                        text: qsTr("❶ UI/聊天库保存内容 (originalUserText)")
                        font.bold: true
                        color: "#1565c0"
                    }
                    Label {
                        text: qsTr("❷ 模型请求文本 (modelRequestText)")
                        font.bold: true
                        color: "#6a1b9a"
                    }

                    TextArea {
                        readOnly: true
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        wrapMode: TextArea.Wrap
                        text: viewModel.originalUserText
                        background: Rectangle { color: "#e3f2fd" }
                    }
                    TextArea {
                        readOnly: true
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        wrapMode: TextArea.Wrap
                        text: viewModel.modelRequestText
                        font.family: "Consolas,Menlo,monospace"
                        background: Rectangle { color: "#f3e5f5" }
                    }

                    Label {
                        text: qsTr("❸ 注入的 Memory Context 片段 (诊断用)")
                        font.bold: true
                        color: "#4527a0"
                        Layout.columnSpan: 2
                    }
                    TextArea {
                        readOnly: true
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 120
                        wrapMode: TextArea.Wrap
                        text: viewModel.injectedContextText
                        font.family: "Consolas,Menlo,monospace"
                        background: Rectangle { color: "#ede7f6" }
                    }
                }

                // ── 原文隔离验证结论 ────────────────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Label {
                        text: qsTr("原文隔离验证：")
                        font.bold: true
                    }
                    Rectangle {
                        width: 24
                        height: 24
                        radius: 12
                        color: viewModel.textIsolationVerified ? "#43a047" : "#e53935"
                    }
                    Label {
                        text: viewModel.textIsolationVerified
                               ? qsTr("PASS — originalUserText 不含任何 Memory Context 标记片段")
                               : qsTr("FAIL — 原文疑似被 MemoryContext 污染！（请检查 UI/DB 保存逻辑）")
                        color: viewModel.textIsolationVerified ? "#2e7d32" : "#c62828"
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }

        // ====================================================================
        // Tab 2：Post-Turn 链路
        // ====================================================================
        Frame {
            Layout.fillWidth: true
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: qsTr("② Post-Turn Pipeline")
                        font.bold: true
                        font.pointSize: 12
                    }
                    Label {
                        text: qsTr("Stage: ") + viewModel.postTurnStage
                        color: (viewModel.postTurnStage === "sent")
                               ? "#2e7d32"
                               : (viewModel.postTurnStage === "failed" ? "#c62828" : "#616161")
                    }
                }

                GridLayout {
                    columns: 4
                    Layout.fillWidth: true
                    columnSpacing: 10
                    rowSpacing: 6

                    Label { text: qsTr("user_id") }
                    TextField {
                        id: postUserId
                        Layout.fillWidth: true
                        text: "local-user"
                    }
                    Label { text: qsTr("session_id") }
                    TextField {
                        id: postSessionId
                        Layout.fillWidth: true
                        text: preSessionId.text  // 默认与 Pre-Chat 同会话
                        Binding on text { value: preSessionId.text; when: true }
                    }

                    Label { text: qsTr("turn_id") }
                    TextField {
                        id: postTurnId
                        Layout.fillWidth: true
                        text: "turn-d5c-001"
                    }
                    Label { text: qsTr("trace_id") }
                    TextField {
                        id: postTraceId
                        Layout.fillWidth: true
                        text: "trace-d5c-" + Math.floor(Math.random() * 10000)
                    }

                    Label { text: qsTr("final_message_id") }
                    TextField {
                        id: postMsgId
                        Layout.fillWidth: true
                        text: "msg-d5c-003"
                    }
                    Label { text: qsTr("finalization_reason") }
                    TextField {
                        id: postReason
                        Layout.fillWidth: true
                        text: "completed"
                    }

                    Label { text: qsTr("stop_reason") }
                    TextField {
                        id: postStop
                        Layout.fillWidth: true
                        text: "stop"
                    }
                    Label { text: "" } // 4th col spacer
                }

                Label {
                    text: qsTr("助手最终回答文本 (仅用于预览展示，不写入事件正文)")
                    font.bold: true
                }
                TextArea {
                    id: assistantFinalText
                    Layout.fillWidth: true
                    Layout.minimumHeight: 60
                    wrapMode: TextArea.Wrap
                    text: qsTr("麒麟 OS Agent 记忆系统由用户侧 Hook (C)、记忆服务 Gateway (D)、业务层 (E) 三部分组成，采用短→中→长期三级记忆流转。")
                }

                RowLayout {
                    Layout.fillWidth: true
                    Button {
                        text: qsTr("Preview TurnFinalizedEvent JSON (不发送)")
                        onClicked: {
                            const obj = viewModel.buildTurnFinalizedEventJson(
                                postUserId.text, postSessionId.text,
                                postTurnId.text, postTraceId.text,
                                postMsgId.text, assistantFinalText.text,
                                postReason.text, postStop.text)
                            postTurnPreview.text = JSON.stringify(obj, null, 2)
                        }
                    }
                    Button {
                        text: viewModel.busy
                              ? qsTr("Sending…")
                              : qsTr("⟶ Run Post-Turn (sendTurnFinalizedEvent → Gateway)")
                        highlighted: true
                        enabled: viewModel.connectionState === "connected" && !viewModel.busy
                        onClicked: {
                            viewModel.runPostTurnPipeline(
                                postUserId.text, postSessionId.text,
                                postTurnId.text, postTraceId.text,
                                postMsgId.text, assistantFinalText.text,
                                postReason.text, postStop.text)
                            // 同步刷新预览（viewModel.lastTurnFinalizedEvent 会变化）
                        }
                    }
                    Item { Layout.fillWidth: true }
                }

                Label {
                    text: qsTr("TurnFinalizedEvent（契约 v1，实际发送到 Gateway 的 payload）")
                    font.bold: true
                }
                ScrollView {
                    Layout.fillWidth: true
                    Layout.minimumHeight: 200
                    TextArea {
                        id: postTurnPreview
                        readOnly: true
                        wrapMode: TextArea.Wrap
                        text: viewModel.lastTurnFinalizedEvent
                        font.family: "Consolas,Menlo,monospace"
                        background: Rectangle { color: "#fbe9e7" }
                    }
                }
            }
        }

        // ====================================================================
        // Tab 3：最近响应 envelope
        // ====================================================================
        Frame {
            Layout.fillWidth: true
            Layout.minimumHeight: 160
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Label {
                    text: qsTr("③ 最近 Gateway 响应 Envelope (原始 JSON)")
                    font.bold: true
                }
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    TextArea {
                        readOnly: true
                        wrapMode: TextArea.Wrap
                        text: JSON.stringify(viewModel.lastResponse, null, 2)
                        font.family: "Consolas,Menlo,monospace"
                    }
                }
            }
        }
    }
}
