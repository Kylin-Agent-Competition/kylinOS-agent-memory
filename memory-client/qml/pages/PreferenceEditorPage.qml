// PreferenceEditorPage.qml — 偏好编辑占位（D4 骨架）
//
// 状态：L0 占位；偏好业务 Schema（类别/scope/confidence/explicitness）未在 E 轨终审，
// 此处不固化具体字段，仅提供 UI 骨架与导航返回。
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
            text: qsTr("Preference Editor")
            font.bold: true
            font.pointSize: 16
        }
        Label {
            text: qsTr("Preference business schema (category / scope / confidence / "
                       + "explicitness / is_temporary / should_persist) is pending "
                       + "E-track final review. This page is a placeholder skeleton.")
            color: palette.placeholderText
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Label {
            text: qsTr("Connection: ") + viewModel.connectionState
            color: viewModel.connectionState === "connected" ? "#2e7d32" : "#c62828"
        }
        Item { Layout.fillHeight: true }
    }
}
