// VerticalLinkPage.qml — D5-C 垂直链路 Demo / Prototype 面板
//
// ⚠️ 重要声明（路线 B — REWORK 修正）：
//   本页仅为 memory-client 侧的 Pipeline Harness / Demo，用于在 L0 Mock
//   Gateway 或 Echo/D 轨 Gateway 上演示 Pre-Chat / Post-Turn envelope / payload
//   形状。它 **尚未** 证明接入：真实 AI Assistant Hook、真实 model request、
//   真实 Chat DB / ChatRecord、真实 assistant final message。
//   因此本 Demo 不关闭 C-D5，也不声称 SEC-CTX-01 已完成 Runtime 验证。
//
// 演示范围：
//   ① Pre-Chat Demo：用户输入 → memory.retrieve → 按正式 MemoryContext
//     契约 (memory_context.v1.json) 解析 envelope.data.context；
//     空 context / error / malformed 一律保持空注入，不产生伪 [MEMORY-CONTEXT]。
//     status=error (UNSUPPORTED_METHOD / TIMEOUT / …) → 明确 failed / timeout。
//   ② Post-Turn Demo：构造 TurnFinalizedEvent → memory.store 发送。
//     status=error → 明确 failed，不得将 UNSUPPORTED_METHOD 显示为 sent。
//   ③ 原文隔离面板：三路字符串对比 + PASS/FAIL 指示灯（仅 Demo 口径校验）。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    // 问题4/非阻断项：整个页面包一层 ScrollView，默认 960×640 不再溢出
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

            // =================================================================
            // 标题 + Demo 声明 + 连接状态
            // =================================================================
            Label {
                Layout.fillWidth: true
                text: qsTr("D5-C · Vertical Link Demo / Prototype（仅 memory-client Harness，不关闭 C-D5）")
                font.bold: true
                font.pointSize: 14
                color: "#6a1b9a"
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr(
                    "⚠️ 本面板仅展示 envelope / payload 形状（L0 Mock / Echo 可验证）。" +
                    "真实 AI Assistant Hook、Chat DB、ChatRecord、assistant final message 尚未集成。" +
                    "Pre/Post status=error / timeout 均进入明确 failed 阶段；" +
                    "空 MemoryContext 不产生伪 [MEMORY-CONTEXT] 标记。"
                )
                wrapMode: Text.WordWrap
                color: "#7b1fa2"
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Label {
                    text: qsTr("Gateway: ") + viewModel.connectionState
                    color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
                }
                Label {
                    text: qsTr("PreChat busy: ") + (viewModel.preChatBusy ? "yes" : "no")
                }
                Label {
                    text: qsTr("PostTurn busy: ") + (viewModel.postTurnBusy ? "yes" : "no")
                }
            }

            // =================================================================
            // ① Pre-Chat
            // =================================================================
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
                            color: {
                                const s = viewModel.preChatStage
                                if (s === "ready")   return "#2e7d32"
                                if (s === "failed" || s === "timeout") return "#c62828"
                                if (s === "querying") return "#f57c00"
                                return "#616161"
                            }
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            text: qsTr("Reset (取消在途请求)")
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
                        text: qsTr("用户原文 (originalUserText — Demo UI 展示口径)")
                        font.bold: true
                    }
                    TextArea {
                        id: userOriginalInput
                        Layout.fillWidth: true
                        Layout.minimumHeight: 60
                        wrapMode: TextArea.Wrap
                        placeholderText: qsTr("输入原文，例如：帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点")
                        text: qsTr("帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            text: (viewModel.preChatStage === "querying")
                                  ? qsTr("Running Pre-Chat…")
                                  : qsTr("⟶ Run Pre-Chat (memory.retrieve → Context)")
                            highlighted: true
                            enabled: viewModel.connectionState === "connected"
                                       && !viewModel.preChatBusy
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
                        Label {
                            text: qsTr("lastRequestId: ") + viewModel.lastRequestId
                            elide: Text.ElideMiddle
                            Layout.maximumWidth: 420
                        }
                    }

                    // 三路口径对比
                    Label {
                        text: qsTr("三路口径对比（原文隔离验证 · Demo 口径）")
                        font.bold: true
                        Layout.topMargin: 6
                    }

                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        Layout.minimumHeight: 260
                        columnSpacing: 10
                        rowSpacing: 6

                        Label {
                            text: qsTr("❶ UI/聊天库保存内容 (originalUserText)")
                            font.bold: true; color: "#1565c0"
                        }
                        Label {
                            text: qsTr("❷ 模型请求文本 (modelRequestText)")
                            font.bold: true; color: "#6a1b9a"
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
                            font.bold: true; color: "#4527a0"
                            Layout.columnSpan: 2
                        }
                        TextArea {
                            readOnly: true
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 100
                            wrapMode: TextArea.Wrap
                            text: viewModel.injectedContextText
                            font.family: "Consolas,Menlo,monospace"
                            background: Rectangle { color: "#ede7f6" }
                            placeholderText: qsTr(
                                "空/error/malformed context 保持空白，不产生伪标记。" +
                                "仅当 context 包含 schema_version/query_id/context_version" +
                                " 且 selected_memory_ids 或 actual_token_count 非空时填充")
                        }
                    }

                    // 原文隔离指示灯
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Label { text: qsTr("原文隔离（Demo 口径）："); font.bold: true }
                        Rectangle {
                            width: 24; height: 24; radius: 12
                            color: viewModel.textIsolationVerified ? "#43a047" : "#e53935"
                        }
                        Label {
                            text: viewModel.textIsolationVerified
                                   ? qsTr("PASS — originalUserText 不含任何 MemoryContext 标记片段")
                                   : qsTr("FAIL — 原文疑似被标记片段污染（检查 Demo 保存逻辑）")
                            color: viewModel.textIsolationVerified ? "#2e7d32" : "#c62828"
                            font.bold: true
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            // =================================================================
            // ② Post-Turn
            // =================================================================
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
                            color: {
                                const s = viewModel.postTurnStage
                                if (s === "sent")    return "#2e7d32"
                                if (s === "failed" || s === "timeout") return "#c62828"
                                if (s === "sending") return "#f57c00"
                                return "#616161"
                            }
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
                            // 非阻断项修复：去掉重复 Binding，仅作为默认值初始化为 preSessionId.text
                            text: preSessionId.text
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

                        Label { text: qsTr("final_message_id (Demo 参考，不写入真实 ChatRecord)") }
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
                        Label { text: "" }
                    }

                    Label {
                        text: qsTr("助手最终回答文本（仅 Demo 预览参考；未对接真实 final message）")
                        font.bold: true
                    }
                    TextArea {
                        id: assistantFinalText
                        Layout.fillWidth: true
                        Layout.minimumHeight: 50
                        wrapMode: TextArea.Wrap
                        text: qsTr(
                            "麒麟 OS Agent 记忆系统由用户侧 Hook (C)、记忆服务 Gateway (D)、业务层 (E) 三部分组成，" +
                            "采用短→中→长期三级记忆流转。")
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        // HIGH 修复：Preview 与 Send 复用同一 buildTurnFinalizedEventJson
                        // （ViewModel 内部按 key 缓存 event_id / timestamp，两者完全一致）。
                        // Preview 只写 previewHelper.previewDoc（纯状态）；postTurnPreview
                        // 通过 declarative binding 自动响应，绝不破坏 binding。
                        Button {
                            text: qsTr("Preview TurnFinalizedEvent (不发送 · 与 Send 共用同一 event_id)")
                            onClicked: {
                                const obj = viewModel.buildTurnFinalizedEventJson(
                                    postUserId.text, postSessionId.text,
                                    postTurnId.text, postTraceId.text,
                                    postMsgId.text, assistantFinalText.text,
                                    postReason.text, postStop.text)
                                previewHelper.previewDoc = JSON.stringify(obj, null, 2)
                            }
                        }

                        Button {
                            text: (viewModel.postTurnStage === "sending")
                                  ? qsTr("Sending…")
                                  : qsTr("⟶ Run Post-Turn (sendTurnFinalizedEvent → Gateway)")
                            highlighted: true
                            enabled: viewModel.connectionState === "connected"
                                       && !viewModel.postTurnBusy
                            onClicked: {
                                viewModel.runPostTurnPipeline(
                                    postUserId.text, postSessionId.text,
                                    postTurnId.text, postTraceId.text,
                                    postMsgId.text, assistantFinalText.text,
                                    postReason.text, postStop.text)
                                // ViewModel 已同步更新 lastTurnFinalizedEvent；
                                // postTurnPreview 使用 binding 自动刷新。
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Label {
                        text: qsTr("TurnFinalizedEvent（契约 v1 · Preview/Send 共用同一 event_id）")
                        font.bold: true
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.minimumHeight: 180
                        TextArea {
                            id: postTurnPreview
                            readOnly: true
                            wrapMode: TextArea.Wrap
                            // HIGH 修复：纯 declarative binding（优先级：
                            // 1) 最近已发送/发送中的 viewModel.lastTurnFinalizedEvent；
                            // 2) 否则 previewHelper.previewDoc（纯预览）。
                            // 绝不在 JS 中做 imperative .text = 赋值，避免移除 binding。
                            text: (viewModel.lastTurnFinalizedEvent.length > 0
                                   && viewModel.postTurnStage !== "idle")
                                      ? viewModel.lastTurnFinalizedEvent
                                      : previewHelper.previewDoc
                            font.family: "Consolas,Menlo,monospace"
                            background: Rectangle { color: "#fbe9e7" }
                        }
                    }

                    // HIGH 修复：Preview 辅助对象仅作为纯 QObject 状态承载；所有使用方
                    // 读取 previewDoc，不调用破坏 binding 的 imperative 赋值。
                    QtObject {
                        id: previewHelper
                        property string previewDoc: ""
                    }
                }
            }

            // =================================================================
            // ③ 最近响应 envelope
            // =================================================================
            Frame {
                Layout.fillWidth: true
                Layout.minimumHeight: 140
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
        }  // ColumnLayout
    }  // ScrollView
}
