// D11DemoOrchestratorPage.qml — D11 同一虚拟机全功能联调主演示编排器
//
// 状态：D11-C Demo / Prototype（L0 可运行编排骨架；CANDIDATE / pending ADR；
//        不关闭 C-D5 / C-D6 / C-D8 / C-D9 / C-D10；不声称真实 AI Assistant Hook /
//        Chat DB / ChatRecord / SourceResolver 已 Runtime 接线）。
//
// 职责：把 5 条主演示路径（D11B 文档 C1-1 ~ C1-5）串为单页 5-Step 编排，
//       方便 B/D 轨在 D11B 麒麟 VM（同一 Commit、同一 VM）内一键复跑：
//         Step 1 · 普通聊天（Pre-Chat 召回 + Post-Turn 落库 / turn.finalized）
//         Step 2 · 跨会话（跨 session，user 保持一致，召回持久化偏好+知识）
//         Step 3 · Tool 调用（Tool Result 入记忆 / 事件采集）
//         Step 4 · 冲突对比（知识生命周期）
//         Step 5 · 精准遗忘（Preview→Confirm→Execute 全流程）
//       编排器不添加任何超出各单页 Pipeline 的业务逻辑；它只
//         (a) 复用 D5/D6/D8/D9/D10 的既有 ViewModel 方法，
//         (b) 提供默认演示样例输入（与 D11B 回填文档 C1-1~C1-5 对齐），
//         (c) 汇总 5 条路径的阶段/错误/安全指示（3 绿/红灯板），
//         (d) 保证每一步的输入明文（selector / originalUserText 等）与
//             响应注入文本严格分离（沿用 D5 原文隔离 + D10 HIGH-01 明文清除）。
//
// 兼容性：Qt 5.12（不使用 5.15+ 语法）；ScrollView 防 960×640 溢出。

import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12

ScrollView {
    id: root
    clip: true

    property alias viewModel: inner.viewModel
    property var inner: orchestrator

    ColumnLayout {
        id: orchestrator
        property var viewModel: null

        width: root.width ? root.width - 24 : 960 - 24
        spacing: 12
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.rightMargin: 12

        // ── 标题 + 连通性 ───────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label {
                text: qsTr("D11 End-to-End Demo Orchestrator (同一 Commit / 同一 VM)")
                font.bold: true
                font.pixelSize: 16
            }
            Item { Layout.fillWidth: true }
            Label {
                text: qsTr("连接：")
            }
            Label {
                text: viewModel ? viewModel.connectionState : "—"
                color: (viewModel && viewModel.connectionState === "connected")
                       ? "#2e7d32" : "#c62828"
            }
            Button {
                text: (viewModel && viewModel.connectionState === "connected")
                      ? qsTr("断开") : qsTr("连接服务")
                onClicked: {
                    if (!viewModel) return;
                    if (viewModel.connectionState === "connected")
                        viewModel.disconnectFromService();
                    else viewModel.connectToService();
                }
            }
            Button {
                text: qsTr("重置 5 步")
                onClicked: resetAllSteps()
            }
        }

        // ── 公共输入（与 D11B 回填 C1-1~C1-5 对齐）────────────────────
        GroupBox {
            Layout.fillWidth: true
            title: qsTr("公共演示参数 (C1-1~C1-5 样例)")

            GridLayout {
                columns: 2
                width: parent.width
                columnSpacing: 16
                rowSpacing: 6

                Label { text: qsTr("user_id") }
                TextField {
                    id: fUserId
                    text: "local-user"
                    Layout.fillWidth: true
                }
                Label { text: qsTr("session_id (Step1)") }
                TextField {
                    id: fSession1
                    text: "session-demo-0001"
                    Layout.fillWidth: true
                }
                Label { text: qsTr("session_id (Step2 跨会话)") }
                TextField {
                    id: fSession2
                    text: "session-demo-0002"
                    Layout.fillWidth: true
                }
                Label { text: qsTr("scene") }
                TextField {
                    id: fScene
                    text: "software_development"
                    Layout.fillWidth: true
                }
                Label { text: qsTr("max_context_tokens") }
                SpinBox {
                    id: fMaxTokens
                    from: 100; to: 16384; value: 800
                    Layout.fillWidth: true
                }
            }
        }

        // ── Step 1 · 普通聊天（Pre-Chat + Post-Turn） ─────────────────
        stepCardComponent.createObject(orchestrator, {
            "stepIndex": 1,
            "stepTitle": qsTr("Step 1 · 普通聊天 (Pre-Chat → Post-Turn)"),
            "stepDescription": qsTr("D5 Vertical Link 主路径：Pre-Chat 召回上下文，三路原文隔离绿灯；Post-Turn 用 turn.finalized 发送 TurnFinalizedEvent，is_end=true。"),
            "stageBinding": viewModel ? viewModel.preChatStage : "",
            "postBinding": viewModel ? viewModel.postTurnStage : "",
            "isolationOk": viewModel ? viewModel.textIsolationVerified : false,
            "errorBinding": "",
            "runAction": function() {
                if (!viewModel) return;
                viewModel.runPreChatPipeline(
                    fUserId.text, fSession1.text, fScene.text,
                    fMaxTokens.value,
                    "帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点");
            },
            "runPost": function() {
                if (!viewModel) return;
                viewModel.runPostTurnPipeline(
                    fUserId.text, fSession1.text,
                    "turn-0001" /* turnId */,
                    "tr-demo-0001" /* traceId */,
                    "msg-final-0001" /* finalMessageId */,
                    "记忆系统含 Vector+FTS5 混合检索 + SQLite 结构化真源。" /* finalAssistantText */,
                    "ended" /* finalizationReason */,
                    "stop" /* stopReason */);
            }
        })

        // ── Step 2 · 跨会话召回持久化偏好+知识 ────────────────────────
        stepCardComponent.createObject(orchestrator, {
            "stepIndex": 2,
            "stepTitle": qsTr("Step 2 · 跨会话召回 (同一 user / 不同 session)"),
            "stepDescription": qsTr("D5 Vertical Link，切换 session_id，期望 context[] 中含持久化 preference/knowledge 条目（session 不回退）。"),
            "stageBinding": viewModel ? viewModel.preChatStage : "",
            "postBinding": "",
            "isolationOk": viewModel ? viewModel.textIsolationVerified : false,
            "errorBinding": "",
            "runAction": function() {
                if (!viewModel) return;
                viewModel.runPreChatPipeline(
                    fUserId.text, fSession2.text, fScene.text,
                    fMaxTokens.value,
                    "提醒我上次提到的 Vector 删除一致性规则");
            },
            "runPost": null
        })

        // ── Step 3 · Tool 调用事件入记忆 ──────────────────────────────
        stepCardComponent.createObject(orchestrator, {
            "stepIndex": 3,
            "stepTitle": qsTr("Step 3 · Tool 调用 (Tool Result 入记忆 / 事件采集)"),
            "stepDescription": qsTr("D6 Tool Adapter：tool_name=memory_search，status=success；tool_output 仅在展示区显示，错误路径只回 safeMessage，不泄露原文。"),
            "stageBinding": viewModel ? viewModel.toolStage : "",
            "postBinding": "",
            "isolationOk": false,
            "errorBinding": "",
            "runAction": function() {
                if (!viewModel) return;
                viewModel.runToolPipeline(
                    fUserId.text, fSession2.text,
                    "turn-0002" /* turnId */,
                    "tc-0001" /* toolCallId */,
                    "memory_search" /* toolName */,
                    "success" /* executionStatus */,
                    "{\"query\":\"qlatent 向量召回阈值\"}" /* argumentsRef */,
                    "{\"hits\":5,\"threshold\":0.52}" /* resultRef */,
                    "" /* errorType */,
                    "" /* errorMessageSafe */,
                    true /* sideEffect */,
                    false /* rollbackRequired */);
            },
            "runPost": null
        })

        // ── Step 4 · 冲突对比（知识生命周期） ──────────────────────────
        stepCardComponent.createObject(orchestrator, {
            "stepIndex": 4,
            "stepTitle": qsTr("Step 4 · 冲突对比 (知识 Conflict / Lifecycle)"),
            "stepDescription": qsTr("D8-C conflict.compare(km-1, include_resolved=false)；冲突候选展示区仅展示摘要 entry_summary，不展示脱敏原文。"),
            "stageBinding": viewModel ? viewModel.conflictCompareStage : "",
            "postBinding": viewModel ? viewModel.lifecycleStatusStage : "",
            "isolationOk": false,
            "errorBinding": viewModel ? viewModel.conflictCompareError : "",
            "runAction": function() {
                if (!viewModel) return;
                viewModel.runConflictComparePipeline("km-1", false /* includeResolved */);
            },
            "runPost": function() {
                if (!viewModel) return;
                viewModel.runLifecycleStatusPipeline(
                    fUserId.text, "km-1", "" /* memoryStatus */);
            }
        })

        // ── Step 5 · 精准遗忘 (Preview→Confirm→Execute) ──────────────
        stepCardComponent.createObject(orchestrator, {
            "stepIndex": 5,
            "stepTitle": qsTr("Step 5 · 精准遗忘 (Preview → Confirm → Execute)"),
            "stepDescription": qsTr("D10-C single_item+知识：Preview 立即清除 selector 明文（HIGH-01），三绿安全灯（selector_cleared / cross-user / missing_deletes）。"),
            "stageBinding": viewModel ? viewModel.forgetStage : "",
            "postBinding": "",
            "isolationOk": viewModel ? (viewModel ? viewModel.forgetSelectorCleared : false) : false,
            "errorBinding": "",
            "runAction": function() {
                if (!viewModel) return;
                viewModel.runForgetPreviewPipeline(
                    fUserId.text,
                    "plan-demo-001" /* forgetPlanId */,
                    "single_item" /* forgetMode */,
                    "knowledge" /* targetType */,
                    "关于 2026-08-20 向量阈值的那条记忆" /* targetSelector */,
                    "km-1" /* targetId */,
                    "" /* targetSessionId */,
                    "" /* targetTopic */,
                    "" /* targetTimeRange */,
                    true /* requiresConfirmation */,
                    false /* isCascade */);
            },
            "runPost": function() {
                if (!viewModel) return;
                viewModel.runForgetExecutePipeline(
                    fUserId.text,
                    "plan-demo-001" /* forgetPlanId */,
                    "credential-demo-32b" /* confirmationToken */,
                    "" /* idempotencyKey */,
                    "soft" /* deleteMode */);
            }
        })

        // ── 5 步安全汇总（D11C 验收：三绿总览） ────────────────────────
        GroupBox {
            Layout.fillWidth: true
            title: qsTr("安全 & 隔离汇总 (验收总览)")

            ColumnLayout {
                width: parent.width
                spacing: 4

                Row {
                    Label {
                        text: qsTr("原文隔离 (D5-C): ")
                    }
                    Label {
                        text: (viewModel && viewModel.textIsolationVerified)
                              ? qsTr("PASS ✓") : qsTr("—")
                        color: (viewModel && viewModel.textIsolationVerified)
                               ? "#2e7d32" : "#666"
                    }
                }
                Row {
                    Label { text: qsTr("Selector 明文清除 (D10-C HIGH-01): ") }
                    Label {
                        text: (viewModel && viewModel.forgetSelectorCleared)
                              ? qsTr("PASS ✓") : qsTr("—")
                        color: (viewModel && viewModel.forgetSelectorCleared)
                               ? "#2e7d32" : "#666"
                    }
                }
                Row {
                    Label { text: qsTr("跨用户拦截 (D10-C #3): ") }
                    Label {
                        text: qsTr("未触发 (默认)")
                    }
                }
                Row {
                    Label { text: qsTr("遗忘漏删一致性 (v0.3/MEDIUM-03): ") }
                    Label {
                        text: (viewModel && !viewModel.forgetHasMissingDeletes)
                              ? qsTr("OK (无漏删)") : qsTr("WARNING")
                        color: (viewModel && !viewModel.forgetHasMissingDeletes)
                               ? "#2e7d32" : "#c62828"
                    }
                }
                Label {
                    text: qsTr("⚠️ 本页为客户端编排 Demo，未接入真实 AI 助手 Hook / Chat DB / 持久化后端；")
                          + qsTr("真实 Runtime 证据需 B/D 轨在 D11B 麒麟 VM (同一 Commit) 复测归档。")
                    color: "#b26a00"
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        function resetAllSteps() {
            if (!viewModel) return;
            viewModel.resetPreChatPipeline();
            viewModel.resetForgetProjection();
            // D5 resetPreChat 已清零三路口径；D10 resetForgetProjection 保留错误文案
            // (L0 测试契约要求：错误不得被 reset 清空，但明文 projection 已清)。
        }
    }

    // ── Step Card 组件（Qt 5.12 兼容：在 ScrollView 根作用域声明 Component）──
    Component {
        id: stepCardComponent

        ColumnLayout {
            property int stepIndex: 1
            property string stepTitle: ""
            property string stepDescription: ""
            property string stageBinding: ""
            property string postBinding: ""
            property bool isolationOk: false
            property string errorBinding: ""
            // 两个可选动作按钮回调：主按钮=runAction；
            // 当 Step 含第二动作（Post-Turn / Lifecycle / Execute）时使用 runPost。
            property var runAction: null
            property var runPost: null

            Layout.fillWidth: true
            spacing: 4

            Rectangle {
                Layout.fillWidth: true
                border.color: "#bdbdbd"
                border.width: 1
                radius: 6
                color: "#fafafa"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("[%1] %2").arg(stepIndex).arg(stepTitle)
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: stageBinding
                            color: (stageBinding === "ready"
                                    || stageBinding === "sent"
                                    || stageBinding === "awaiting_confirmation"
                                    || stageBinding === "completed")
                                   ? "#2e7d32" : (stageBinding === "failed"
                                                  ? "#c62828" : "#555")
                        }
                        Label {
                            visible: postBinding !== ""
                            text: " / " + postBinding
                            color: (postBinding === "ready"
                                    || postBinding === "sent"
                                    || postBinding === "completed")
                                   ? "#2e7d32" : (postBinding === "failed"
                                                  ? "#c62828" : "#555")
                        }
                    }
                    Label {
                        text: stepDescription
                        wrapMode: Text.Wrap
                        color: "#555"
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        spacing: 8
                        Button {
                            text: (stepIndex === 5) ? qsTr("⑤-A Run Preview") :
                                  (stepIndex === 1) ? qsTr("①-A Pre-Chat") :
                                  (stepIndex === 4) ? qsTr("④-A Conflict Compare") :
                                  qsTr("Run Step %1").arg(stepIndex)
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (runAction) runAction()
                        }
                        Button {
                            visible: stepIndex === 1 || stepIndex === 4 || stepIndex === 5
                            text: (stepIndex === 1) ? qsTr("①-B Post-Turn (turn.finalized)") :
                                  (stepIndex === 4) ? qsTr("④-B Lifecycle Status") :
                                                      qsTr("⑤-B Run Execute (soft)")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (runPost) runPost()
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            visible: stepIndex === 1 || stepIndex === 2
                            text: qsTr("原文隔离: ")
                                  + (isolationOk ? qsTr("PASS ✓") : qsTr("—"))
                            color: isolationOk ? "#2e7d32" : "#666"
                        }
                        Label {
                            visible: stepIndex === 5
                            text: qsTr("Selector清除: ")
                                  + (isolationOk ? qsTr("PASS ✓") : qsTr("—"))
                            color: isolationOk ? "#2e7d32" : "#666"
                        }
                    }
                    Label {
                        visible: errorBinding !== ""
                        text: qsTr("错误: ") + errorBinding
                        color: "#c62828"
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
}
