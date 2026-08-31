// PreferenceVersionPage.qml — D7-C 偏好版本管理 Demo / Prototype
//
// ⚠️ Demo 声明（沿用 D5-C Route B / D6-C Demo）：
//   本页仅为 memory-client 侧的 Pipeline Harness / Demo，用于演示
//   preference.version.commit / history / rollback 三个候选 IPC 方法的
//   构造与发送。**尚未** 接入真实偏好持久化后端（D7D Repository 已在
//   origin/main@c1ee840 合入，但 Gateway 未注册 preference.version.* handler
//   → 生产默认返回 UNSUPPORTED_METHOD）。
//   C-D7 保持 OPEN；本 Demo 不关闭 C-D7。
//
// ⚠️ 关键边界（C-D / C-E 接口）：
//   preference.version.* → MemorySourceEvent.source_type 映射未冻结；本页
//   显式标注 mapping_status="PENDING_C_CONFIRMATION"。不擅自新增
//   SourceType 枚举。
//
// 演示范围：
//   ① Commit：长期偏好 / 临时设置 / 安全相关配置 / 敏感内容边界表单
//   ② History：当前版本 + 历史版本链查询（include_history）
//   ③ Rollback：回滚到指定 target_version_id（Demo 期可手动填写）
//   ④ 跨会话行为联调：从 Behavior Pipeline 复用 sessionId 触发偏好事件
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
                text: qsTr("D7-C · Preference Version Management Demo / Prototype")
                font.bold: true
                font.pointSize: 14
                color: "#6a1b9a"
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("⚠️ 候选 IPC 方法 preference.version.commit / history / rollback（不冻结）。\n"
                          + "⚠️ 生产 Gateway 默认未注册 handler → UNSUPPORTED_METHOD。\n"
                          + "⚠️ high / critical 敏感等级客户端侧直接拒绝发送（不进入 Gateway）。\n"
                          + "⚠️ preference.version.* → source_type 映射 PENDING_C_CONFIRMATION。")
                color: "#c62828"
                wrapMode: Text.WordWrap
            }
            Label {
                text: qsTr("Connection: ") + viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }

            // ── 跨会话行为联调：复用 D6-C Behavior Pipeline 的 sessionId ──
            GroupBox {
                title: qsTr("Cross-Session Behavior Linkage")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("复用 D6-C Behavior Observe 的 sessionId 触发偏好事件。"
                                  + "点击下方按钮将使用上方 sessionId 同时发起一次 behavior.observe，"
                                  + "用于演示跨会话行为 → 偏好版本管理的链路联调。")
                        color: "#1565c0"
                        wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        Label { text: qsTr("Behavior Kind:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: linkBehaviorKind
                            Layout.fillWidth: true
                            model: ["user_message", "agent_response",
                                    "system_message", "user_action"]
                            currentIndex: 0
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Observed Action:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: linkAction; Layout.fillWidth: true
                            text: "user_confirmed_preference"; placeholderText: "observed action"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Actor:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: linkActor
                            Layout.fillWidth: true
                            model: ["user", "agent", "system"]
                            currentIndex: 0
                        }
                    }
                    Button {
                        Layout.fillWidth: true
                        text: qsTr("Trigger behavior.observe (link to current session)")
                        enabled: !viewModel.behaviorBusy
                                 && viewModel.connectionState === "connected"
                        onClicked: viewModel.runBehaviorPipeline(
                            pvUserId.text, pvSessionId.text,
                            linkBehaviorKind.currentText, linkAction.text,
                            "ref:preference-version-link", linkActor.currentText)
                    }
                }
            }

            // ── ① Commit Pipeline ──────────────────────────────────────
            GroupBox {
                title: qsTr("① Preference Commit (preference.version.commit)")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    RowLayout {
                        Label { text: qsTr("User ID:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvUserId; Layout.fillWidth: true
                            text: "local-user"; placeholderText: "user id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Session ID:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvSessionId; Layout.fillWidth: true
                            text: "session-preference-demo"; placeholderText: "session id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Scope:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: pvScope
                            Layout.fillWidth: true
                            model: ["global", "topic", "tool", "session", "time_window"]
                            currentIndex: 0
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Key:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvKey; Layout.fillWidth: true
                            text: "language"; placeholderText: "preference key"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Value:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvValue; Layout.fillWidth: true
                            text: "zh-CN"; placeholderText: "preference value"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Memory Status:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: pvMemoryStatus
                            Layout.fillWidth: true
                            model: ["active", "superseded", "deprecated",
                                    "expired", "removed", "candidate"]
                            currentIndex: 0
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Is Temporary:"); Layout.preferredWidth: 130 }
                        Switch { id: pvTemporary; checked: false }
                    }
                    RowLayout {
                        Label { text: qsTr("Should Persist:"); Layout.preferredWidth: 130 }
                        Switch { id: pvPersist; checked: true }
                    }
                    RowLayout {
                        Label { text: qsTr("Sensitivity Level:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: pvSensitivity
                            Layout.fillWidth: true
                            model: ["none", "low", "medium", "high", "critical"]
                            currentIndex: 0
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Confidence:"); Layout.preferredWidth: 130 }
                        SpinBox {
                            id: pvConfidence; Layout.fillWidth: true
                            from: 0; to: 100; value: 80
                            suffix: " %"
                        }
                    }

                    Button {
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        text: viewModel.preferenceCommitBusy
                              ? qsTr("Sending…")
                              : qsTr("Send preference.version.commit")
                        highlighted: true
                        enabled: !viewModel.preferenceCommitBusy
                                 && viewModel.connectionState === "connected"
                        onClicked: viewModel.runPreferenceCommitPipeline(
                            pvUserId.text, pvSessionId.text,
                            pvScope.currentText, pvKey.text, pvValue.text,
                            pvTemporary.checked, pvPersist.checked,
                            pvMemoryStatus.currentText,
                            pvSensitivity.currentText,
                            pvConfidence.value / 100.0)
                    }
                }
            }

            // ── ② History Pipeline（当前版本 + 历史版本链查询） ──────────
            GroupBox {
                title: qsTr("② Preference History (preference.version.history)")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("当前版本与历史版本由服务端按版本链返回。Demo 期 Gateway 默认返回 "
                                  + "UNSUPPORTED_METHOD；Mock Gateway 测试态可注入 handler 返回 items[]。")
                        color: "#1565c0"
                        wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        Label { text: qsTr("Scope:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvHistoryScope; Layout.fillWidth: true
                            text: pvScope.currentText; placeholderText: "scope"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Key:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvHistoryKey; Layout.fillWidth: true
                            text: pvKey.text; placeholderText: "preference key"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Include History:"); Layout.preferredWidth: 130 }
                        Switch { id: pvIncludeHistory; checked: true }
                    }
                    Button {
                        Layout.fillWidth: true
                        text: viewModel.preferenceHistoryBusy
                              ? qsTr("Querying…")
                              : qsTr("Send preference.version.history")
                        enabled: !viewModel.preferenceHistoryBusy
                                 && viewModel.connectionState === "connected"
                        onClicked: viewModel.runPreferenceHistoryPipeline(
                            pvUserId.text, pvSessionId.text,
                            pvHistoryScope.text, pvHistoryKey.text,
                            pvIncludeHistory.checked)
                    }
                }
            }

            // ── ③ Rollback Pipeline（回滚入口） ─────────────────────────
            GroupBox {
                title: qsTr("③ Preference Rollback (preference.version.rollback)")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("⚠️ Demo 期由调用方手动填写 target_version_id。生产环境应由 "
                                  + "History 查询返回的版本链中选择，禁止跨用户 / 跨版本链回滚。")
                        color: "#c62828"
                        wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        Label { text: qsTr("Scope:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvRollbackScope; Layout.fillWidth: true
                            text: pvScope.currentText; placeholderText: "scope"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Key:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvRollbackKey; Layout.fillWidth: true
                            text: pvKey.text; placeholderText: "preference key"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Target Version ID:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: pvTargetVersionId; Layout.fillWidth: true
                            text: "1"; placeholderText: "target version id (integer)"
                        }
                    }
                    Button {
                        Layout.fillWidth: true
                        text: viewModel.preferenceRollbackBusy
                              ? qsTr("Rolling back…")
                              : qsTr("Send preference.version.rollback")
                        enabled: !viewModel.preferenceRollbackBusy
                                 && viewModel.connectionState === "connected"
                        onClicked: viewModel.runPreferenceRollbackPipeline(
                            pvUserId.text, pvSessionId.text,
                            pvRollbackScope.text, pvRollbackKey.text,
                            pvTargetVersionId.text)
                    }
                }
            }

            // ── Stage & Event 展示（三组 Pipeline 共用） ────────────────
            GroupBox {
                title: qsTr("Stage & Event (Commit / History / Rollback)")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        text: qsTr("preferenceCommitStage: ") + viewModel.preferenceCommitStage
                        color: viewModel.preferenceCommitStage === "sent" ? "#2e7d32"
                               : (viewModel.preferenceCommitStage === "failed"
                                  || viewModel.preferenceCommitStage === "timeout"
                                  ? "#c62828" : "#1565c0")
                    }
                    Label {
                        text: qsTr("preferenceCommitBusy: ")
                              + (viewModel.preferenceCommitBusy ? "true" : "false")
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Last PreferenceCommitEvent JSON:")
                        font.bold: true
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 180
                        TextArea {
                            readOnly: true
                            text: viewModel.lastPreferenceCommitEvent
                            font.family: "Consolas, Menlo, monospace"
                            wrapMode: Text.WrapAnywhere
                            background: Rectangle { color: "#fafafa"; border.color: "#ddd" }
                        }
                    }

                    Label {
                        Layout.topMargin: 6
                        text: qsTr("preferenceHistoryStage: ") + viewModel.preferenceHistoryStage
                        color: viewModel.preferenceHistoryStage === "sent" ? "#2e7d32"
                               : (viewModel.preferenceHistoryStage === "failed"
                                  || viewModel.preferenceHistoryStage === "timeout"
                                  ? "#c62828" : "#1565c0")
                    }
                    Label {
                        text: qsTr("preferenceHistoryBusy: ")
                              + (viewModel.preferenceHistoryBusy ? "true" : "false")
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Last PreferenceHistoryEvent JSON:")
                        font.bold: true
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 180
                        TextArea {
                            readOnly: true
                            text: viewModel.lastPreferenceHistoryEvent
                            font.family: "Consolas, Menlo, monospace"
                            wrapMode: Text.WrapAnywhere
                            background: Rectangle { color: "#fafafa"; border.color: "#ddd" }
                        }
                    }

                    Label {
                        Layout.topMargin: 6
                        text: qsTr("preferenceRollbackStage: ") + viewModel.preferenceRollbackStage
                        color: viewModel.preferenceRollbackStage === "sent" ? "#2e7d32"
                               : (viewModel.preferenceRollbackStage === "failed"
                                  || viewModel.preferenceRollbackStage === "timeout"
                                  ? "#c62828" : "#1565c0")
                    }
                    Label {
                        text: qsTr("preferenceRollbackBusy: ")
                              + (viewModel.preferenceRollbackBusy ? "true" : "false")
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Last PreferenceRollbackEvent JSON:")
                        font.bold: true
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 180
                        TextArea {
                            readOnly: true
                            text: viewModel.lastPreferenceRollbackEvent
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
