// MemoryQueryPage.qml — memory.retrieve 请求构造（D4 骨架）
//
// 注意：payload 仅构造 MemoryQuery 契约的最小字段；真实业务校验在
// os-agent-integration/contracts 实现。本页面不固化未来未冻结字段。
import QtQuick 2.12
import QtQuick.Controls 2.12
import QtQuick.Layouts 1.12
import kylin.memory 1.0

Page {
    id: root
    property MemoryViewModel viewModel

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10

        Label {
            text: qsTr("Memory Query")
            font.bold: true
            font.pointSize: 16
        }
        Label {
            text: qsTr("Sends a memory.retrieve request envelope to the Gateway.")
            color: palette.placeholderText
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        GridLayout {
            columns: 2
            Layout.fillWidth: true

            Label { text: qsTr("user_id") }
            TextField { id: userId; Layout.fillWidth: true; text: "local-user" }
            Label { text: qsTr("session_id") }
            TextField { id: sessionId; Layout.fillWidth: true; text: "session-001" }
            Label { text: qsTr("scene") }
            TextField { id: scene; Layout.fillWidth: true; text: "software_development" }
            Label { text: qsTr("max_context_tokens") }
            SpinBox { id: maxTokens; from: 1; to: 8192; value: 800 }
            Label { text: qsTr("query_text") }
            TextArea {
                id: queryText
                Layout.fillWidth: true
                Layout.minimumHeight: 80
                wrapMode: TextArea.Wrap
                text: qsTr("继续昨天的任务")
            }
        }

        Button {
            text: viewModel.busy ? qsTr("Sending…") : qsTr("Send query")
            enabled: viewModel.connectionState === "connected" && !viewModel.busy
            onClicked: {
                const payload = {
                    "schema_version": "1.0",
                    "user_id": userId.text,
                    "session_id": sessionId.text,
                    "query_text": queryText.text,
                    "scene": scene.text,
                    "max_context_tokens": maxTokens.value
                }
                viewModel.sendMemoryQuery(payload)
            }
        }

        Label {
            text: qsTr("Last Response")
            font.bold: true
            Layout.topMargin: 8
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
