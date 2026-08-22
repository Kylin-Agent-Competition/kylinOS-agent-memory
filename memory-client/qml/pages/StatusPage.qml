// StatusPage.qml — 连接状态与最近响应展示（D4 骨架）
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
        spacing: 12

        Label {
            text: qsTr("Connection Status")
            font.bold: true
            font.pointSize: 16
        }

        GridLayout {
            columns: 2
            Layout.fillWidth: true
            Label { text: qsTr("Socket path:") }
            Label { text: viewModel.socketPath; Layout.fillWidth: true; elide: Text.ElideRight }
            Label { text: qsTr("State:") }
            Label {
                text: viewModel.connectionState
                color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
            }
            Label { text: qsTr("Last error:") }
            Label {
                text: viewModel.lastError.length > 0 ? viewModel.lastError : qsTr("(none)")
                color: viewModel.lastError.length > 0 ? "#c62828" : palette.text
                Layout.fillWidth: true; elide: Text.ElideRight
            }
            Label { text: qsTr("Last request id:") }
            Label { text: viewModel.lastRequestId; Layout.fillWidth: true; elide: Text.ElideRight }
            Label { text: qsTr("Busy:") }
            Label { text: viewModel.busy ? qsTr("yes") : qsTr("no") }
        }

        Label {
            text: qsTr("Last Response")
            font.bold: true
            font.pointSize: 14
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

        RowLayout {
            Layout.fillWidth: true
            Button {
                text: viewModel.connectionState === "connected"
                      ? qsTr("Disconnect")
                      : qsTr("Connect")
                enabled: !viewModel.busy
                onClicked: {
                    if (viewModel.connectionState === "connected") {
                        viewModel.disconnectFromService()
                    } else {
                        viewModel.connectToService()
                    }
                }
            }
            Button {
                text: qsTr("Send health")
                enabled: viewModel.connectionState === "connected" && !viewModel.busy
                onClicked: viewModel.sendHealth()
            }
        }
    }
}
