// PreferenceEditorPage.qml — 偏好编辑 UI、版本历史与回滚（D7C，B 轨代 C 轨）
//
// 验收口径：docs/day7/day7-e-ui-version-acceptance-v1.md（CREATE / COEXIST /
// UPDATE / NO_OP / ROLLBACK + 临时偏好 + 跨用户隔离 5.1–5.7）。
// 依赖：D7C 偏好 IPC（preference.list/create/update/rollback/history，本 PR 实现）
//       + D7D #90 偏好版本持久化。
// 状态：本页仅渲染当前用户（user_id 输入框）的偏好；跨用户历史由服务端
//       Repository user_id 强制过滤 + 本页只请求当前用户，双层落实验收 5.7。
// 兼容性：目标 Qt 5.12（不使用 5.15+ 语法）。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    // 当前选中查看历史的 (key, scope)
    property string historyKey: ""
    property string historyScope: ""

    function refreshList() {
        if (userIdField.text.trim().length === 0) return
        viewModel.loadPreferences(userIdField.text.trim())
    }

    function refreshHistory(key, scope) {
        if (userIdField.text.trim().length === 0) return
        historyKey = key
        historyScope = scope
        viewModel.loadPreferenceHistory(userIdField.text.trim(), key, scope)
    }

    function createNew() {
        if (userIdField.text.trim().length === 0
                || keyField.text.trim().length === 0
                || valueField.text.length === 0) {
            statusText.text = qsTr("请填写 user_id / key / value")
            return
        }
        viewModel.createPreference(
            userIdField.text.trim(),
            keyField.text.trim(),
            scopeCombo.currentText,
            valueField.text,
            tempCheck.checked,
            persistCheck.checked,
            idemField.text.trim())
    }

    function updateCurrent() {
        if (userIdField.text.trim().length === 0
                || keyField.text.trim().length === 0
                || valueField.text.length === 0) {
            statusText.text = qsTr("请填写 user_id / key / value")
            return
        }
        viewModel.updatePreference(
            userIdField.text.trim(),
            keyField.text.trim(),
            scopeCombo.currentText,
            valueField.text,
            idemField.text.trim())
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Label {
                text: qsTr("Preference Editor")
                font.bold: true
                font.pointSize: 16
            }
            Item { Layout.fillWidth: true }
            Label {
                text: qsTr("Connection: ") + viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }
        }

        // 状态行
        Label {
            id: statusText
            text: {
                var parts = []
                if (viewModel.preferenceBusy) parts.push(qsTr("busy: ") + viewModel.preferenceStage)
                else parts.push(qsTr("stage: ") + viewModel.preferenceStage)
                if (viewModel.preferenceError.length > 0) parts.push(qsTr("error: ") + viewModel.preferenceError)
                if (viewModel.lastPreferenceAction.length > 0) parts.push(qsTr("last action: ") + viewModel.lastPreferenceAction)
                return parts.join("  |  ")
            }
            color: viewModel.preferenceError.length > 0 ? "#c62828" : palette.text
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        // 用户与刷新
        RowLayout {
            Layout.fillWidth: true
            Label { text: qsTr("user_id") }
            TextField {
                id: userIdField
                Layout.fillWidth: true
                text: "local-user"
            }
            Button {
                text: viewModel.preferenceBusy ? qsTr("…") : qsTr("刷新")
                enabled: viewModel.connectionState === "connected" && !viewModel.preferenceBusy
                onClicked: refreshList()
            }
        }

        // 偏好条目列表（preference.list）
        Label { text: qsTr("当前偏好") ; font.bold: true; Layout.topMargin: 6 }
        ListView {
            id: itemsView
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(220, itemsView.count * 56 + 8)
            clip: true
            model: viewModel.preferenceItems
            delegate: Rectangle {
                width: itemsView.width
                height: 52
                color: index % 2 === 0 ? "#f5f5f5" : "#ffffff"
                radius: 4
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            text: qsTr("%1  [%2]").arg(model.preference_key).arg(model.preference_scope)
                            font.bold: true
                        }
                        Label {
                            text: {
                                if (model.current !== undefined && model.current !== null) {
                                    return qsTr("v%1: %2  (%3)").arg(
                                        model.current.version).arg(model.current.preference_value)
                                        .arg(model.current.memory_status)
                                }
                                return qsTr("（无当前版本）")
                            }
                            elide: Text.ElideRight
                        }
                    }
                    Button {
                        text: qsTr("历史")
                        enabled: viewModel.connectionState === "connected" && !viewModel.preferenceBusy
                        onClicked: refreshHistory(model.preference_key, model.preference_scope)
                    }
                }
            }
        }

        // 添加 / 编辑表单
        Label { text: qsTr("添加 / 编辑偏好") ; font.bold: true; Layout.topMargin: 6 }
        GridLayout {
            columns: 4
            Layout.fillWidth: true
            Label { text: qsTr("key") }
            TextField { id: keyField; Layout.fillWidth: true; text: "response.language" }
            Label { text: qsTr("scope") }
            ComboBox {
                id: scopeCombo
                Layout.fillWidth: true
                model: ["global", "topic", "tool", "session", "time_window"]
            }
            Label { text: qsTr("value") }
            TextField {
                id: valueField
                Layout.fillWidth: true
                Layout.columnSpan: 3
                text: "中文"
            }
            Label { text: qsTr("临时偏好") }
            CheckBox { id: tempCheck; text: qsTr("is_temporary") }
            Label { text: qsTr("持久化") }
            CheckBox { id: persistCheck; checked: true; text: qsTr("should_persist") }
            Label { text: qsTr("幂等键") }
            TextField {
                id: idemField
                Layout.fillWidth: true
                Layout.columnSpan: 3
                placeholderText: qsTr("可选，重试同一操作时复用")
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Button {
                text: qsTr("创建 (preference.create)")
                enabled: viewModel.connectionState === "connected" && !viewModel.preferenceBusy
                onClicked: createNew()
            }
            Button {
                text: qsTr("更新 (preference.update)")
                enabled: viewModel.connectionState === "connected" && !viewModel.preferenceBusy
                onClicked: updateCurrent()
            }
        }

        // 历史版本链（preference.history）
        Label {
            text: qsTr("版本历史：%1 [%2]").arg(historyKey).arg(historyScope)
            font.bold: true
            Layout.topMargin: 6
        }
        ListView {
            id: historyView
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(200, historyView.count * 52 + 8)
            clip: true
            model: viewModel.preferenceHistory
            delegate: Rectangle {
                width: historyView.width
                height: 48
                color: model.is_current ? "#e3f2fd" : (index % 2 === 0 ? "#fafafa" : "#ffffff")
                radius: 4
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Label {
                            text: qsTr("v%1 %2").arg(model.version)
                                .arg(model.is_current ? qsTr("（当前）") : "")
                            font.bold: true
                        }
                        Label {
                            text: qsTr("%1  (%2)").arg(model.preference_value).arg(model.memory_status)
                            elide: Text.ElideRight
                        }
                    }
                    Button {
                        text: qsTr("回滚到此版本")
                        enabled: !model.is_current
                                 && viewModel.connectionState === "connected"
                                 && !viewModel.preferenceBusy
                        onClicked: viewModel.rollbackPreference(
                            userIdField.text.trim(),
                            historyKey,
                            historyScope,
                            model.version,
                            idemField.text.trim())
                    }
                }
            }
        }

        // 最近一次写响应
        Label { text: qsTr("最近一次写响应") ; font.bold: true; Layout.topMargin: 6 }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            TextArea {
                readOnly: true
                wrapMode: TextArea.Wrap
                font.family: "Consolas,Menlo,monospace"
                text: JSON.stringify(viewModel.lastPreferenceItem, null, 2)
            }
        }
    }

    onVisibleChanged: {
        if (visible) refreshList()
    }
}
