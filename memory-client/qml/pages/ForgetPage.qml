// ForgetPage.qml — D10C 精准遗忘 Pipeline（Demo / Prototype）
//
// 依赖：D10C 候选 IPC forget.preview / forget.execute（pending ADR）。
// 业务契约：v0.3 冻结（docs/day10/16_d10d_forget_contract_plan_v0.3.md）。
// ⚠️  Demo / Prototype 声明（与 C-D5 / D8C / D9C 一致）：
//     本页仅为 QML Pipeline Harness，不证明 D 轨 SQLite Forget 事务、
//     B 轨 Vector/FTS5 物理删除、E 轨 ForgetPlan 业务规则已真实接入。
//     Hard Delete / Cascade / Full Reset Runtime 保持 fail-closed。
//     因此本实现不关闭 C-D10，也不宣称完整精准遗忘能力已 Runtime 验证。
// 兼容性：目标 Qt 5.12（不使用 5.15+ 语法）。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    // 遗忘模式枚举（§三.1 v0.3 冻结五值 + selector 互斥）
    //   single_item → targetId / session → targetSessionId /
    //   topic → targetTopic / time_window → targetTimeRange /
    //   full_reset → 无任何 target_*
    readonly property var forgetModes: [
        {label: qsTr("单条 (single_item)"), value: "single_item"},
        {label: qsTr("会话 (session)"),     value: "session"},
        {label: qsTr("主题 (topic)"),        value: "topic"},
        {label: qsTr("时间窗 (time_window)"),value: "time_window"},
        {label: qsTr("全量重置 (full_reset)"), value: "full_reset"}
    ]
    readonly property var targetTypes: [
        {label: qsTr("知识 (knowledge)"),   value: "knowledge"},
        {label: qsTr("偏好 (preference)"),  value: "preference"},
        {label: qsTr("事件 (event)"),        value: "event"},
        {label: qsTr("全部 (all)"),          value: "all"}
    ]

    function selectedModeValue() {
        var idx = modeCombo.currentIndex
        return idx >= 0 ? forgetModes[idx].value : ""
    }
    function selectedTypeValue() {
        var idx = typeCombo.currentIndex
        return idx >= 0 ? targetTypes[idx].value : ""
    }

    // 当前模式下显示哪些 target_* 输入字段（SEC-FORGET-03 互斥）
    function showTargetId()    { return selectedModeValue() === "single_item" }
    function showSessionId()   { return selectedModeValue() === "session" }
    function showTopic()       { return selectedModeValue() === "topic" }
    function showTimeRange()   { return selectedModeValue() === "time_window" }
    function showNoTargets()   { return selectedModeValue() === "full_reset" }

    function runPreview() {
        // 基础必填校验（其余校验在 ViewModel 层 + D 轨服务端双重执行）
        if (userIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 user_id")
            return
        }
        if (planIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 forget_plan_id")
            return
        }
        if (modeCombo.currentIndex < 0) {
            statusText.text = qsTr("请选择 forget_mode")
            return
        }
        if (typeCombo.currentIndex < 0) {
            statusText.text = qsTr("请选择 target_type")
            return
        }
        viewModel.runForgetPreviewPipeline(
            userIdField.text.trim(),
            planIdField.text.trim(),
            selectedModeValue(),
            selectedTypeValue(),
            selectorField.text.trim(),
            targetIdField.text.trim(),
            sessionIdField.text.trim(),
            topicField.text.trim(),
            timeRangeField.text.trim(),
            requiresConfirmCheck.checked,
            cascadeCheck.checked)
    }

    function runExecute() {
        if (viewModel.forgetStage !== "awaiting_confirmation") {
            statusText.text = qsTr("必须先完成 Preview（状态为 awaiting_confirmation）")
            return
        }
        if (userIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 user_id")
            return
        }
        if (planIdField.text.trim().length === 0) {
            statusText.text = qsTr("请填写 forget_plan_id")
            return
        }
        if (tokenField.text.trim().length === 0) {
            statusText.text = qsTr("请填写确认凭据 (confirmation_token)")
            return
        }
        viewModel.runForgetExecutePipeline(
            userIdField.text.trim(),
            planIdField.text.trim(),
            tokenField.text.trim(),
            idemKeyField.text.trim(),
            deleteModeCombo.currentIndex === 1 ? "hard" : "soft")
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 8
            Layout.margins: 12

            // ── 标题 & 连接状态 ────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.topMargin: 12
                Label {
                    text: qsTr("精准遗忘 (Forget)")
                    font.bold: true
                    font.pointSize: 16
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: qsTr("Connection: ") + viewModel.connectionState
                    color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
                }
            }

            // ── Demo / Prototype 声明（与 D5/D8/D9 一致，避免假宣称） ──
            Label {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                wrapMode: Text.WordWrap
                text: qsTr("⚠️  Demo / Prototype：本页仅演示遗忘客户端 Pipeline（Preview→确认→Execute 状态机、影响范围、敏感提示、失败重试、selector 明文清除）。"
                          +"尚未证明接入 D 轨 SQLite 事务、B 轨 Vector/FTS5 物理删除、E 轨业务 Gate。Hard Delete / Cascade / Full Reset Runtime 在跨轨闭环与麒麟 L2 证据前保持 fail-closed。")
                color: "#ef6c00"
                font.pointSize: 9
            }

            // ── 状态条（stage + busy + 错误 + 跨用户拒绝 + 漏删 + selector 清除） ──
            Label {
                id: statusText
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                wrapMode: Text.WordWrap
                text: {
                    var parts = []
                    parts.push(qsTr("stage: ") + viewModel.forgetStage)
                    if (viewModel.forgetPreviewBusy)  parts.push(qsTr("previewing…"))
                    if (viewModel.forgetExecuteBusy)  parts.push(qsTr("executing…"))
                    if (viewModel.forgetCrossUserBlocked) parts.push(qsTr("[跨用户操作已拒绝]"))
                    if (viewModel.forgetHasMissingDeletes)     parts.push(qsTr("[漏删检测: 不一致]"))
                    if (viewModel.forgetSelectorCleared)       parts.push(qsTr("[selector 已清除]"))
                    if (viewModel.forgetPreviewError.length > 0) parts.push(qsTr("err(P): ")+viewModel.forgetPreviewError)
                    if (viewModel.forgetExecuteError.length > 0) parts.push(qsTr("err(E): ")+viewModel.forgetExecuteError)
                    if (parts.length === 1) {
                        // 仅 stage：附加提示文案
                        if (viewModel.forgetStage === "idle")
                            parts.push(qsTr("填写参数后点击 Preview。"))
                        else if (viewModel.forgetStage === "awaiting_confirmation")
                            parts.push(qsTr("Preview 完成，请确认并 Execute。"))
                        else if (viewModel.forgetStage === "completed")
                            parts.push(qsTr("遗忘执行完成。"))
                    }
                    return parts.join("  |  ")
                }
                color: (viewModel.forgetCrossUserBlocked
                        || viewModel.forgetHasMissingDeletes
                        || viewModel.forgetPreviewError.length > 0
                        || viewModel.forgetExecuteError.length > 0)
                       ? "#c62828" : palette.text
            }

            // ── 基础输入区 ────────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("user_id") }
                TextField {
                    id: userIdField
                    Layout.fillWidth: true
                    text: "u1"
                    placeholderText: qsTr("强制隔离键，禁止模型生成")
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("forget_plan_id") }
                TextField {
                    id: planIdField
                    Layout.fillWidth: true
                    text: "fp-20260901-001"
                    placeholderText: qsTr("遗忘计划唯一 ID")
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("forget_mode") }
                ComboBox {
                    id: modeCombo
                    Layout.preferredWidth: 260
                    model: forgetModes
                    textRole: "label"
                    currentIndex: 0
                }
                Label { text: qsTr("target_type") }
                ComboBox {
                    id: typeCombo
                    Layout.fillWidth: true
                    model: targetTypes
                    textRole: "label"
                    currentIndex: 0
                }
            }

            // ── 自然语言选择器（明文生命周期：Preview 完成后清除 §四.8 HIGH-01） ──
            Label {
                text: qsTr("target_selector（自然语言遗忘描述，仅短期存在）")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            TextArea {
                id: selectorField
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: 56
                wrapMode: TextArea.Wrap
                placeholderText: qsTr("示例：删除关于项目周报格式的过时偏好")
            }

            // ── 模式条件字段（互斥：按 forget_mode 仅显示一个） ──
            Label {
                text: qsTr("模式条件字段（按 forget_mode 互斥，SEC-FORGET-03）")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            RowLayout { visible: showTargetId();
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                Label { text: qsTr("target_id (single_item)") }
                TextField { id: targetIdField; Layout.fillWidth: true
                    placeholderText: qsTr("km-xxx") } }
            RowLayout { visible: showSessionId();
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                Label { text: qsTr("target_session_id (session)") }
                TextField { id: sessionIdField; Layout.fillWidth: true
                    placeholderText: qsTr("sess-xxx") } }
            RowLayout { visible: showTopic();
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                Label { text: qsTr("target_topic (topic)") }
                TextField { id: topicField; Layout.fillWidth: true
                    placeholderText: qsTr("可能含正文，Preview后清除") } }
            RowLayout { visible: showTimeRange();
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                Label { text: qsTr("target_time_range") }
                TextField { id: timeRangeField; Layout.fillWidth: true
                    placeholderText: qsTr("DEFERRED: 待 D/E 书面冻结 canonical 口径") } }
            Label { visible: showNoTargets();
                Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 12
                text: qsTr("⚠️  full_reset 模式：重置当前 user_id 在 Agent Memory 自有数据域全部记忆对象；需要最高级确认；Runtime Execute 在跨轨闭环前 fail-closed。")
                color: "#c62828"; wrapMode: Text.WordWrap }

            // ── 复选：要求确认 / 级联 ─────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                CheckBox {
                    id: requiresConfirmCheck
                    checked: true
                    text: qsTr("requires_confirmation (禁止模型生成)")
                }
                Item { Layout.fillWidth: true }
                CheckBox {
                    id: cascadeCheck
                    checked: false
                    text: qsTr("is_cascade (默认 false = 安全语义)")
                }
            }

            // ── Preview / Execute 按钮 ────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Button {
                    text: viewModel.forgetPreviewBusy ? qsTr("Preview…") : qsTr("1. Preview (预览影响范围)")
                    enabled: viewModel.connectionState === "connected"
                             && !viewModel.forgetPreviewBusy && !viewModel.forgetExecuteBusy
                    highlighted: true
                    onClicked: runPreview()
                }
                Button {
                    text: viewModel.forgetExecuteBusy ? qsTr("Execute…") : qsTr("2. Execute (执行遗忘)")
                    enabled: viewModel.connectionState === "connected"
                             && !viewModel.forgetPreviewBusy && !viewModel.forgetExecuteBusy
                             && viewModel.forgetStage === "awaiting_confirmation"
                    highlighted: viewModel.forgetStage === "awaiting_confirmation"
                    onClicked: runExecute()
                }
            }

            // ── Execute 辅助输入：确认凭据 / 幂等 / 删除模式 ──────────
            Label {
                text: qsTr("Execute 参数（确认凭据一次性；§五 冻结）")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("confirmation_token") }
                TextField {
                    id: tokenField
                    Layout.fillWidth: true
                    placeholderText: qsTr("Preview 返回 data.credential 明文（Demo mock）")
                    echoMode: TextField.PasswordEchoOnEdit
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("idempotency_key") }
                TextField {
                    id: idemKeyField
                    Layout.preferredWidth: 260
                    placeholderText: qsTr("可选；复用 FRZ-IPC-005")
                }
                Label { text: qsTr("delete_mode") }
                ComboBox {
                    id: deleteModeCombo
                    Layout.fillWidth: true
                    model: [
                        {label: qsTr("soft (软删优先 / 默认安全路径)"), value: "soft"},
                        {label: qsTr("hard (硬删 / Runtime fail-closed 至跨轨闭环)"), value: "hard"}
                    ]
                    textRole: "label"
                    currentIndex: 0
                }
            }

            // ── 敏感提示面板（sensitivity_warning） ───────────────────
            Label {
                visible: viewModel.forgetSensitivityWarning.length > 0
                text: qsTr("⚠️  敏感提示: ") + viewModel.forgetSensitivityWarning
                color: "#c62828"
                font.bold: true
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                wrapMode: Text.WordWrap
            }

            // ── Preview 结果：影响范围面板 ────────────────────────────
            Label {
                text: qsTr("影响范围 (Preview)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label {
                    text: qsTr("affected_count: ") + viewModel.forgetAffectedCount
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: qsTr("凭据 TTL: ") + viewModel.forgetCredentialTtlSeconds + qsTr("s")
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: qsTr("selection_hash: ")
                }
                Label {
                    text: viewModel.forgetSelectionHash.length === 0
                          ? qsTr("(待生成)") : viewModel.forgetSelectionHash
                    font.family: "Consolas,Menlo,monospace"
                    Layout.maximumWidth: 260
                    elide: Text.ElideMiddle
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label { text: qsTr("forget_mode: ") + viewModel.forgetMode }
                Item { Layout.fillWidth: true }
                Label { text: qsTr("target_type: ") + viewModel.forgetTargetType }
                Item { Layout.fillWidth: true }
                Label { text: qsTr("cascade: ") + (viewModel.forgetIsCascade ? qsTr("true") : qsTr("false")) }
            }
            Label {
                text: qsTr("resolved_target_ids (预览命中 ID 切片)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            ListView {
                id: targetsView
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: Math.min(140, Math.max(0, targetsView.count) * 32 + 8)
                clip: true
                model: viewModel.forgetResolvedTargets
                delegate: Rectangle {
                    width: targetsView.width
                    height: 28
                    color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                    radius: 4
                    Label {
                        anchors.fill: parent
                        anchors.margins: 6
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideMiddle
                        font.family: "Consolas,Menlo,monospace"
                        text: typeof modelData === "string"
                              ? modelData
                              : JSON.stringify(modelData)
                    }
                }
            }

            // ── Execute 结果：执行一致性校验 ───────────────────────────
            Label {
                text: qsTr("Execute 结果")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label {
                    text: qsTr("executed / affected: ")
                         + (viewModel.forgetExecutedCount < 0 ? qsTr("-") : String(viewModel.forgetExecutedCount))
                         + " / " + viewModel.forgetAffectedCount
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: viewModel.forgetHasMissingDeletes
                          ? qsTr("❌ 漏删不一致！不得进入 completed")
                          : qsTr("✓ 执行数量一致")
                    color: viewModel.forgetHasMissingDeletes ? "#c62828" : "#2e7d32"
                    font.bold: true
                }
            }

            // ── 安全验收状态：selector 清除 / 跨用户拒绝 ─────────────
            Label {
                text: qsTr("安全验收")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Label {
                    text: viewModel.forgetSelectorCleared
                          ? qsTr("✓ selector 明文已清除 (§四.8 HIGH-01)")
                          : qsTr("○ selector 明文未清除 (Preview 完成前)")
                    color: viewModel.forgetSelectorCleared ? "#2e7d32" : palette.text
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: viewModel.forgetCrossUserBlocked
                          ? qsTr("✓ 跨用户操作已拒绝 (C-D10 #3)")
                          : qsTr("○ 未触发跨用户场景")
                    color: viewModel.forgetCrossUserBlocked ? "#2e7d32" : palette.text
                }
            }

            // ── 原始响应 JSON（诊断） ──────────────────────────────────
            Label {
                text: qsTr("Preview 响应 (forget.preview)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            TextArea {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.preferredHeight: 120
                readOnly: true
                wrapMode: TextArea.Wrap
                font.family: "Consolas,Menlo,monospace"
                text: JSON.stringify(viewModel.forgetPreviewResult, null, 2)
            }
            Label {
                text: qsTr("Execute 响应 (forget.execute)")
                font.bold: true
                Layout.leftMargin: 12
                Layout.topMargin: 6
            }
            TextArea {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.bottomMargin: 12
                Layout.preferredHeight: 90
                readOnly: true
                wrapMode: TextArea.Wrap
                font.family: "Consolas,Menlo,monospace"
                text: JSON.stringify(viewModel.forgetExecuteResult, null, 2)
            }
        }
    }
}
