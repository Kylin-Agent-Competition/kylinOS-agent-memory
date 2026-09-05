// ManualConfigPage.qml — D6-C 多源 Adapter Demo / Prototype：手动配置面板
//
// ⚠️ Demo 声明（沿用 D5-C Route B）：
//   本页仅为 memory-client 侧的 Pipeline Harness / Demo，用于演示
//   ManualConfigEvent 的构造与发送。**尚未** 接入真实配置持久化后端。
//   C-D5 保持 OPEN；本 Demo 不关闭 C-D6。
//
// 演示范围：
//   ① 长期偏好 / 临时设置 / 安全相关配置 / 敏感内容边界表单
//   ② manual.config.ingest 候选 IPC 方法发送
//   ③ 客户端侧敏感预检：high / critical → manualConfigStage=failed，拒绝发送
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
            // 兼容性：QtQuick.Layouts 的 padding 属性自 Qt 5.15 起才有，
            // 麒麟 VM（Qt 5.12）QML 加载即退出 255（pr151_vm_test_report_20260905）。
            // 改用 x/y/width 实现等效 12px 留白，底部留白由末尾 spacer 补足。
            x: 12
            y: 12
            width: root.width - 24
            spacing: 8

            Label {
                Layout.fillWidth: true
                text: qsTr("D6-C · Manual Config Demo / Prototype（候选 IPC 方法 manual.config.ingest）")
                font.bold: true
                font.pointSize: 14
                color: "#6a1b9a"
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("⚠️ 生产 Gateway 默认未注册 manual.config.ingest handler → UNSUPPORTED_METHOD。\n"
                          + "⚠️ high / critical 敏感等级客户端侧直接拒绝发送（不进入 Gateway）。")
                color: "#c62828"
                wrapMode: Text.WordWrap
            }
            Label {
                text: qsTr("Connection: ") + viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }

            GroupBox {
                title: qsTr("Manual Config Event")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    RowLayout {
                        Label { text: qsTr("User ID:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: mcUserId; Layout.fillWidth: true
                            text: "local-user"; placeholderText: "user id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Session ID:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: mcSessionId; Layout.fillWidth: true
                            text: "session-mc-demo"; placeholderText: "session id"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Scope:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: mcScope; Layout.fillWidth: true
                            text: "preference"; placeholderText: "scope"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Key:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: mcKey; Layout.fillWidth: true
                            text: "language"; placeholderText: "config key"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Value:"); Layout.preferredWidth: 130 }
                        TextField {
                            id: mcValue; Layout.fillWidth: true
                            text: "zh-CN"; placeholderText: "config value"
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Is Temporary:"); Layout.preferredWidth: 130 }
                        Switch { id: mcTemporary; checked: false }
                    }
                    RowLayout {
                        Label { text: qsTr("Should Persist:"); Layout.preferredWidth: 130 }
                        Switch { id: mcPersist; checked: true }
                    }
                    RowLayout {
                        Label { text: qsTr("Sensitivity Level:"); Layout.preferredWidth: 130 }
                        ComboBox {
                            id: mcSensitivity
                            Layout.fillWidth: true
                            model: ["none", "low", "medium", "high", "critical"]
                            currentIndex: 0
                        }
                    }
                    RowLayout {
                        Label { text: qsTr("Confidence:"); Layout.preferredWidth: 130 }
                        SpinBox {
                            id: mcConfidence; Layout.fillWidth: true
                            from: 0; to: 100; value: 80
                        }
                        // 兼容性：QtQuick.Controls 2（Qt 5.x）的 SpinBox 无
                        // suffix 属性（Controls 1 / Qt 6 才有，加载即报
                        // "Cannot assign to non-existent property"），
                        // 单位由独立 Label 呈现。
                        Label { text: qsTr("%") }
                    }

                    Button {
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        text: viewModel.manualConfigBusy
                              ? qsTr("Sending…")
                              : qsTr("Send manual.config.ingest")
                        highlighted: true
                        enabled: !viewModel.manualConfigBusy
                                  && viewModel.connectionState === "connected"
                        onClicked: viewModel.runManualConfigPipeline(
                            mcUserId.text, mcSessionId.text,
                            mcScope.text, mcKey.text, mcValue.text,
                            mcTemporary.checked, mcPersist.checked,
                            mcSensitivity.currentText,
                            mcConfidence.value / 100.0)
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
                        text: qsTr("manualConfigStage: ") + viewModel.manualConfigStage
                        color: viewModel.manualConfigStage === "sent" ? "#2e7d32"
                               : (viewModel.manualConfigStage === "failed"
                                  || viewModel.manualConfigStage === "timeout"
                                  ? "#c62828" : "#1565c0")
                    }
                    Label {
                        text: qsTr("manualConfigBusy: ")
                              + (viewModel.manualConfigBusy ? "true" : "false")
                    }
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Last ManualConfigEvent JSON:")
                        font.bold: true
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 220
                        TextArea {
                            readOnly: true
                            text: viewModel.lastManualConfigEvent
                            font.family: "Consolas, Menlo, monospace"
                            wrapMode: Text.WrapAnywhere
                            background: Rectangle { color: "#fafafa"; border.color: "#ddd" }
                        }
                    }
                }
            }

            // 底部留白（替代 bottomPadding，兼容 Qt 5.12 Layouts）
            Item { Layout.preferredHeight: 12 }
        }
    }
}
