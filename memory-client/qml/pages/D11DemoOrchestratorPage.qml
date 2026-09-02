// D11DemoOrchestratorPage.qml — D11 同一虚拟机全功能联调主演示编排器
//
// 状态：D11-C Demo / Prototype（L0 可运行编排骨架；CANDIDATE / pending ADR；
//        不关闭 C-D5 / C-D6 / C-D8 / C-D9 / C-D10；不声称真实 AI Assistant Hook /
//        Chat DB / ChatRecord / SourceResolver 已 Runtime 接线）。
//
// HIGH-01 修复：
//   - viewModel alias 直接绑定 id=orchestrator 的属性（不经过 var inner）。
//   - 本页由 L0 测试 test_d11c_qml_load 通过 QQmlComponent 真实实例化校验。
//   - 每张 Step Card Rectangle 设置 implicitHeight = 内容 ColumnLayout.implicitHeight + 20，
//     防止 anchors.fill: parent 造成的"父高度依赖 Layout/implicit size 而子又依赖父高度"的
//     循环依赖导致 Card 获得 0 或错误高度。
//
// HIGH-03 修复：
//   - 5 张 Step Card 为显式声明式实例（NOT createObject+快照），每张 Card 内部
//     直接绑定 viewModel.* Q_PROPERTY；状态变更自动刷新。
//   - 兼容 Qt 5.12：不使用 inline component / Qt 5.15 语法。
//
// MEDIUM-01 修复：
//   - "重置 5 步" 调用 viewModel.resetAllPipelines()，明确覆盖 6 条 Pipeline。
//
// HIGH-02 修复：
//   - Step 5 Execute 按钮使用 viewModel.forgetConfirmationCredential
//     （forget.preview 响应中的 confirmation_credential），非空才启用；
//     ViewModel runForgetExecutePipeline 内部再做 fail-closed 二次校验。

import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12

ScrollView {
    id: root
    clip: true

    // HIGH-01：直接 alias 到 id=orchestrator 的 viewModel，避免中间 var inner
    property alias viewModel: orchestrator.viewModel

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
            Label { text: qsTr("连接：") }
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
                text: qsTr("重置 5 步 (全 Pipeline)")
                // HIGH-01 / Qt 5.12：Controls 2 Button 没有 "toolTip" 直接属性，
                // 必须使用 ToolTip 附加属性，否则 QQmlComponent 解析阶段
                // 就报 "Cannot assign to non-existent property \"toolTip\""
                // 导致 status 永远 Error。
                ToolTip.text: qsTr("重置 PreChat/PostTurn/Tool/Conflict/Lifecycle/Forget stage 和 busy（保留 forget 错误文案）")
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

        // ── Step 1 · 普通聊天（Pre-Chat + Post-Turn）─────────────────
        // HIGH-03：stageBinding/postBinding/isolationOk 均为 QML 原生绑定，
        // viewModel 的 NOTIFY 信号会自动触发刷新。
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Rectangle {
                objectName: "d11-step-1-card"
                Layout.fillWidth: true
                implicitHeight: step1Content.implicitHeight + 20
                border.color: "#bdbdbd"; border.width: 1; radius: 6; color: "#fafafa"
                ColumnLayout {
                    id: step1Content
                    anchors.fill: parent; anchors.margins: 10; spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("[1] Step 1 · 普通聊天 (Pre-Chat → Post-Turn)")
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: viewModel ? viewModel.preChatStage : ""
                            color: (viewModel && (viewModel.preChatStage === "ready"
                                     || viewModel.preChatStage === "sent"
                                     || viewModel.preChatStage === "completed"))
                                   ? "#2e7d32"
                                   : (viewModel && viewModel.preChatStage === "failed"
                                          ? "#c62828" : "#555")
                        }
                        Label {
                            text: " / " + (viewModel ? viewModel.postTurnStage : "")
                            color: (viewModel && (viewModel.postTurnStage === "ready"
                                     || viewModel.postTurnStage === "sent"
                                     || viewModel.postTurnStage === "completed"))
                                   ? "#2e7d32"
                                   : (viewModel && viewModel.postTurnStage === "failed"
                                          ? "#c62828" : "#555")
                        }
                    }
                    Label {
                        text: qsTr("D5 Vertical Link 主路径：Pre-Chat 召回上下文，三路原文隔离绿灯；Post-Turn 用 turn.finalized 发送 TurnFinalizedEvent，is_end=true。")
                        wrapMode: Text.Wrap; color: "#555"; Layout.fillWidth: true
                    }
                    RowLayout {
                        spacing: 8
                        Button {
                            text: qsTr("①-A Pre-Chat")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (viewModel) viewModel.runPreChatPipeline(
                                fUserId.text, fSession1.text, fScene.text,
                                fMaxTokens.value,
                                "帮我回忆昨天讨论的麒麟 OS Agent 记忆系统架构要点")
                        }
                        Button {
                            text: qsTr("①-B Post-Turn (turn.finalized)")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (viewModel) viewModel.runPostTurnPipeline(
                                fUserId.text, fSession1.text,
                                "turn-0001", "tr-demo-0001", "msg-final-0001",
                                "记忆系统含 Vector+FTS5 混合检索 + SQLite 结构化真源。",
                                "ended", "stop")
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: qsTr("原文隔离: ")
                                  + ((viewModel && viewModel.textIsolationVerified)
                                     ? qsTr("PASS ✓") : qsTr("—"))
                            color: (viewModel && viewModel.textIsolationVerified)
                                   ? "#2e7d32" : "#666"
                        }
                    }
                }
            }
        }

        // ── Step 2 · 跨会话召回持久化偏好+知识 ────────────────────────
        ColumnLayout {
            Layout.fillWidth: true; spacing: 4
            Rectangle {
                objectName: "d11-step-2-card"
                Layout.fillWidth: true
                implicitHeight: step2Content.implicitHeight + 20
                border.color: "#bdbdbd"; border.width: 1; radius: 6; color: "#fafafa"
                ColumnLayout {
                    id: step2Content
                    anchors.fill: parent; anchors.margins: 10; spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("[2] Step 2 · 跨会话召回 (同一 user / 不同 session)")
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: viewModel ? viewModel.preChatStage : ""
                            color: (viewModel && (viewModel.preChatStage === "ready"
                                     || viewModel.preChatStage === "sent"
                                     || viewModel.preChatStage === "completed"))
                                   ? "#2e7d32"
                                   : (viewModel && viewModel.preChatStage === "failed"
                                          ? "#c62828" : "#555")
                        }
                    }
                    Label {
                        text: qsTr("D5 Vertical Link，切换 session_id = session-demo-0002，期望 context[] 含持久化 preference/knowledge 条目（session 不回退）。")
                        wrapMode: Text.Wrap; color: "#555"; Layout.fillWidth: true
                    }
                    RowLayout {
                        spacing: 8
                        Button {
                            text: qsTr("Run Step 2 · Pre-Chat")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (viewModel) viewModel.runPreChatPipeline(
                                fUserId.text, fSession2.text, fScene.text,
                                fMaxTokens.value,
                                "提醒我上次提到的 Vector 删除一致性规则")
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: qsTr("原文隔离: ")
                                  + ((viewModel && viewModel.textIsolationVerified)
                                     ? qsTr("PASS ✓") : qsTr("—"))
                            color: (viewModel && viewModel.textIsolationVerified)
                                   ? "#2e7d32" : "#666"
                        }
                    }
                }
            }
        }

        // ── Step 3 · Tool 调用事件入记忆 ──────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true; spacing: 4
            Rectangle {
                objectName: "d11-step-3-card"
                Layout.fillWidth: true
                implicitHeight: step3Content.implicitHeight + 20
                border.color: "#bdbdbd"; border.width: 1; radius: 6; color: "#fafafa"
                ColumnLayout {
                    id: step3Content
                    anchors.fill: parent; anchors.margins: 10; spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("[3] Step 3 · Tool 调用 (Tool Result 入记忆 / 事件采集)")
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: viewModel ? viewModel.toolStage : ""
                            color: (viewModel && viewModel.toolStage === "sent")
                                   ? "#2e7d32"
                                   : (viewModel && viewModel.toolStage === "failed"
                                          ? "#c62828" : "#555")
                        }
                    }
                    Label {
                        text: qsTr("D6 Tool Adapter：tool_name=memory_search，execution_status=success；错误路径 safeMessage 只显 error_code，不泄露 tool_output 正文。")
                        wrapMode: Text.Wrap; color: "#555"; Layout.fillWidth: true
                    }
                    RowLayout {
                        spacing: 8
                        Button {
                            text: qsTr("Run Step 3 · Tool")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (viewModel) viewModel.runToolPipeline(
                                fUserId.text, fSession2.text,
                                "turn-0002", "tc-0001", "memory_search", "success",
                                "{\"query\":\"qlatent 向量召回阈值\"}",
                                "{\"hits\":5,\"threshold\":0.52}",
                                "", "", true, false)
                        }
                    }
                }
            }
        }

        // ── Step 4 · 冲突对比（知识生命周期） ──────────────────────────
        ColumnLayout {
            Layout.fillWidth: true; spacing: 4
            Rectangle {
                objectName: "d11-step-4-card"
                Layout.fillWidth: true
                implicitHeight: step4Content.implicitHeight + 20
                border.color: "#bdbdbd"; border.width: 1; radius: 6; color: "#fafafa"
                ColumnLayout {
                    id: step4Content
                    anchors.fill: parent; anchors.margins: 10; spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("[4] Step 4 · 冲突对比 (知识 Conflict / Lifecycle)")
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: viewModel ? viewModel.conflictCompareStage : ""
                            color: (viewModel && viewModel.conflictCompareStage === "ready")
                                   ? "#2e7d32"
                                   : (viewModel && viewModel.conflictCompareStage === "failed"
                                          ? "#c62828" : "#555")
                        }
                        Label {
                            text: " / " + (viewModel ? viewModel.lifecycleStatusStage : "")
                            color: (viewModel && viewModel.lifecycleStatusStage === "ready")
                                   ? "#2e7d32"
                                   : (viewModel && viewModel.lifecycleStatusStage === "failed"
                                          ? "#c62828" : "#555")
                        }
                    }
                    Label {
                        text: qsTr("D8-C conflict.compare(km-1, include_resolved=false) → 候选列表；lifecycle.status(km-1) → active/archived 版本流转。")
                        wrapMode: Text.Wrap; color: "#555"; Layout.fillWidth: true
                    }
                    RowLayout {
                        spacing: 8
                        Button {
                            text: qsTr("④-A Conflict Compare")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (viewModel)
                                viewModel.runConflictComparePipeline("km-1", false)
                        }
                        Button {
                            text: qsTr("④-B Lifecycle Status")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (viewModel)
                                viewModel.runLifecycleStatusPipeline(fUserId.text, "km-1", "")
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            visible: viewModel && viewModel.conflictCompareError && viewModel.conflictCompareError.length > 0
                            text: qsTr("错误: ") + (viewModel ? viewModel.conflictCompareError : "")
                            color: "#c62828"
                        }
                    }
                }
            }
        }

        // ── Step 5 · 精准遗忘 (Preview → Confirm → Execute) ──────────────
        ColumnLayout {
            Layout.fillWidth: true; spacing: 4
            Rectangle {
                objectName: "d11-step-5-card"
                Layout.fillWidth: true
                implicitHeight: step5Content.implicitHeight + 20
                border.color: "#bdbdbd"; border.width: 1; radius: 6; color: "#fafafa"
                ColumnLayout {
                    id: step5Content
                    anchors.fill: parent; anchors.margins: 10; spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("[5] Step 5 · 精准遗忘 (Preview → Confirm → Execute)")
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: viewModel ? viewModel.forgetStage : ""
                            color: (viewModel && (viewModel.forgetStage === "ready"
                                     || viewModel.forgetStage === "awaiting_confirmation"
                                     || viewModel.forgetStage === "completed"))
                                   ? "#2e7d32"
                                   : (viewModel && viewModel.forgetStage === "failed"
                                          ? "#c62828" : "#555")
                        }
                    }
                    Label {
                        text: qsTr("D10-C single_item+知识：Preview 生成 confirmation_credential（绑定 userId+forgetPlanId+selection_hash，TTL=300s），HIGH-01 立即清除 selector 明文；Execute 仅在携带同一 Preview 凭据时放行，凭据不匹配 / 过期 = fail-closed。")
                        wrapMode: Text.Wrap; color: "#555"; Layout.fillWidth: true
                    }
                    RowLayout {
                        spacing: 8
                        Button {
                            text: qsTr("⑤-A Run Preview")
                            enabled: viewModel !== null && !viewModel.busy
                            onClicked: if (viewModel) viewModel.runForgetPreviewPipeline(
                                fUserId.text, "plan-demo-001",
                                "single_item", "knowledge",
                                "关于 2026-08-20 向量阈值的那条记忆",
                                "km-1", "", "", "", true, false)
                        }
                        Button {
                            // HIGH-02：仅当 Preview 成功返回 credential 后才启用
                            text: (viewModel && viewModel.forgetConfirmationCredential
                                      && viewModel.forgetConfirmationCredential.length > 0)
                                  ? qsTr("⑤-B Execute (Preview 凭据, soft)")
                                  : qsTr("⑤-B Execute (请先完成 Preview)")
                            enabled: viewModel
                                     && viewModel.forgetStage === "awaiting_confirmation"
                                     && viewModel.forgetConfirmationCredential
                                     && viewModel.forgetConfirmationCredential.length > 0
                                     && !viewModel.busy
                            onClicked: if (viewModel) viewModel.runForgetExecutePipeline(
                                // HIGH-02：直接绑定 Preview 返回的凭据（ViewModel 再校验）
                                fUserId.text, "plan-demo-001",
                                viewModel.forgetConfirmationCredential,
                                "", "soft")
                        }
                        Item { Layout.fillWidth: true }
                        Label {
                            text: qsTr("Selector清除: ")
                                  + ((viewModel && viewModel.forgetSelectorCleared)
                                     ? qsTr("PASS ✓") : qsTr("—"))
                            color: (viewModel && viewModel.forgetSelectorCleared)
                                   ? "#2e7d32" : "#666"
                        }
                    }
                    Label {
                        visible: viewModel
                                 && viewModel.forgetStage === "failed"
                                 && ((viewModel.forgetPreviewError
                                        && viewModel.forgetPreviewError.length > 0)
                                     || (viewModel.forgetExecuteError
                                           && viewModel.forgetExecuteError.length > 0))
                        text: qsTr("错误: ")
                              + (viewModel ? (viewModel.forgetPreviewError
                                                || viewModel.forgetExecuteError) : "")
                        color: "#c62828"; Layout.fillWidth: true; wrapMode: Text.Wrap
                    }
                }
            }
        }

        // ── 5 步安全汇总（D11C 验收：三绿总览） ────────────────────────
        // MEDIUM-03：所有汇总灯必须 gate 到"对应 pipeline 已完成执行"之后；
        // 未执行/执行中不得显示 PASS/OK（避免初始态假阳性把"尚未验证"显示成"验证通过"）。
        GroupBox {
            Layout.fillWidth: true
            title: qsTr("安全 & 隔离汇总 (验收总览)")

            ColumnLayout {
                width: parent.width; spacing: 4

                Row {
                    Label { text: qsTr("原文隔离 (D5-C): ") }
                    Label {
                        text: {
                            if (!viewModel) return qsTr("—");
                            // Gate 到 Step1 preChat 完成：stage==ready 才允许给 PASS/FAIL
                            if (viewModel.preChatStage !== "ready") return qsTr("未执行 · —");
                            return viewModel.textIsolationVerified
                                   ? qsTr("PASS ✓") : qsTr("FAIL ✗");
                        }
                        color: {
                            if (!viewModel) return "#666";
                            if (viewModel.preChatStage !== "ready") return "#9e9e9e";
                            return viewModel.textIsolationVerified
                                   ? "#2e7d32" : "#c62828";
                        }
                        objectName: "d11-summary-text-isolation"
                    }
                }
                Row {
                    Label { text: qsTr("Selector 明文清除 (D10-C HIGH-01): ") }
                    Label {
                        text: {
                            if (!viewModel) return qsTr("—");
                            // Gate 到 Step5 forget 执行完成（completed / failed）后才显示
                            if (viewModel.forgetStage !== "completed"
                                && viewModel.forgetStage !== "failed")
                                return qsTr("未执行 · —");
                            return viewModel.forgetSelectorCleared
                                   ? qsTr("PASS ✓") : qsTr("FAIL ✗");
                        }
                        color: {
                            if (!viewModel) return "#666";
                            if (viewModel.forgetStage !== "completed"
                                && viewModel.forgetStage !== "failed")
                                return "#9e9e9e";
                            return viewModel.forgetSelectorCleared
                                   ? "#2e7d32" : "#c62828";
                        }
                        objectName: "d11-summary-selector-cleared"
                    }
                }
                Row {
                    Label { text: qsTr("凭据链闭合 (D11 Step5 HIGH-02): ") }
                    Label {
                        text: {
                            if (!viewModel) return qsTr("—");
                            if (viewModel.forgetStage === "completed")
                                return qsTr("PASS ✓ (Preview→Execute 同一凭据)");
                            if (viewModel.forgetStage === "awaiting_confirmation"
                                && viewModel.forgetConfirmationCredential
                                && viewModel.forgetConfirmationCredential.length > 0)
                                return qsTr("READY ✓ (等待 Execute)");
                            if (viewModel.forgetStage === "failed")
                                return qsTr("FAIL ✗ (凭据不匹配 / 过期)");
                            return qsTr("未执行 · —");
                        }
                        color: {
                            if (!viewModel) return "#666";
                            if (viewModel.forgetStage === "completed") return "#2e7d32";
                            if (viewModel.forgetStage === "awaiting_confirmation"
                                && viewModel.forgetConfirmationCredential
                                && viewModel.forgetConfirmationCredential.length > 0)
                                return "#2e7d32";
                            if (viewModel.forgetStage === "failed") return "#c62828";
                            return "#9e9e9e";
                        }
                        objectName: "d11-summary-credential-chain"
                    }
                }
                Row {
                    Label { text: qsTr("跨用户拦截 (D10-C #3): ") }
                    Label { text: qsTr("未触发 (默认)"); color: "#666" }
                }
                Row {
                    Label { text: qsTr("遗忘漏删一致性 (v0.3/MEDIUM-03): ") }
                    Label {
                        text: {
                            if (!viewModel) return qsTr("—");
                            // Gate 到 Step5 forget 已执行完成后才允许判定
                            if (viewModel.forgetStage !== "completed"
                                && viewModel.forgetStage !== "failed")
                                return qsTr("未执行 · —");
                            return !viewModel.forgetHasMissingDeletes
                                   ? qsTr("OK (无漏删)") : qsTr("WARNING (漏删)");
                        }
                        color: {
                            if (!viewModel) return "#666";
                            if (viewModel.forgetStage !== "completed"
                                && viewModel.forgetStage !== "failed")
                                return "#9e9e9e";
                            return !viewModel.forgetHasMissingDeletes
                                   ? "#2e7d32" : "#c62828";
                        }
                        objectName: "d11-summary-forget-missing"
                    }
                }
                Label {
                    text: qsTr("⚠️ 本页为客户端编排 Demo，未接入真实 AI 助手 Hook / Chat DB / 持久化后端；真实 Runtime 证据需 B/D 轨在 D11B 麒麟 VM (同一 Commit) 复测归档。")
                    color: "#b26a00"; wrapMode: Text.Wrap; Layout.fillWidth: true
                }
            }
        }

        function resetAllSteps() {
            if (!viewModel) return;
            // MEDIUM-01：使用 ViewModel.resetAllPipelines() 全量 reset
            // 覆盖 PreChat/PostTurn/Tool/Conflict/Lifecycle/Forget 的 stage/busy
            // 保留 forget*Error 文案（resetForgetProjection 契约不变）。
            viewModel.resetAllPipelines();
        }
    }
}
