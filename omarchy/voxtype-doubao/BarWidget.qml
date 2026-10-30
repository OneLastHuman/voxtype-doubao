import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "user.voxtype-doubao"

  property bool opened: false
  property var status: ({})
  property real wavePhase: 0

  readonly property bool online: !!(status && status.proxy && status.proxy.listening)
  readonly property bool loggedIn: !!(status && status.params && status.params.present)
  readonly property string phase: status && status.voxtype && status.voxtype.state ? String(status.voxtype.state) : "unknown"
  readonly property bool recording: phase === "recording"
  readonly property bool transcribing: phase === "transcribing"
  readonly property string statusText: !online ? "代理未运行" : !loggedIn ? "需要登录" : recording ? "录音中" : transcribing ? "转写中" : "空闲"

  readonly property color recordColor: "#e0223d"
  readonly property color signalColor: "#8ad9c1"
  readonly property color panelBg: "#0d1917"
  readonly property color panelText: "#eaf2ed"
  readonly property color panelMuted: "#9bb1a8"
  readonly property color panelLine: "#2a403a"

  function applyStatus(raw) {
    try {
      var parsed = JSON.parse(String(raw || "{}"))
      status = parsed && typeof parsed === "object" ? parsed : ({})
    } catch (e) {
      status = ({})
    }
  }

  function open() {
    opened = true
    if (!statusProc.running) statusProc.running = true
  }

  function close() {
    opened = false
  }

  function toggle() {
    opened ? close() : open()
  }

  Process {
    id: statusProc
    command: [Quickshell.env("HOME") + "/.local/bin/voxtype-doubao", "status", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyStatus(text)
    }
  }

  Timer {
    interval: 1000
    running: true
    repeat: true
    onTriggered: if (!statusProc.running) statusProc.running = true
  }

  Component.onCompleted: statusProc.running = true

  IpcHandler {
    target: "user.voxtype-doubao"
    function toggle(): void { root.toggle() }
    function open(): void { root.open() }
    function close(): void { root.close() }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.recording ? "󰍬 豆包" : root.transcribing ? "󰔟 豆包" : "󰍬 豆包"
    tooltipText: root.statusText
    active: root.recording || root.transcribing
    activeColor: root.recording ? root.recordColor : root.signalColor
    dimmed: !root.online
    onPressed: function(b) {
      if (b === Qt.LeftButton) root.toggle()
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  PanelWindow {
    id: panel
    visible: root.opened
    screen: root.QsWindow && root.QsWindow.window ? root.QsWindow.window.screen : null
    implicitWidth: 360
    implicitHeight: 476
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "voxtype-doubao-panel"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    anchors { top: true; right: true }
    margins { top: 44; right: 16 }

    Rectangle {
      anchors.fill: parent
      radius: 8
      color: root.panelBg
      border.width: 1
      border.color: root.panelLine
      clip: true

      ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        RowLayout {
          Layout.fillWidth: true
          spacing: 8

          Text {
            text: "语音链路"
            color: root.panelMuted
            font.family: Style.font.family
            font.pixelSize: 11
            font.letterSpacing: 1
          }

          Item { Layout.fillWidth: true }

          Rectangle {
            width: 7
            height: 7
            radius: 4
            color: !root.online ? "#5a6b66" : root.recording ? root.recordColor : root.signalColor
          }

          Text {
            text: root.statusText
            color: root.online ? root.panelText : root.panelMuted
            font.family: Style.font.family
            font.pixelSize: 11
          }

          Text {
            text: "×"
            color: root.panelMuted
            font.pixelSize: 18

            MouseArea {
              anchors.fill: parent
              anchors.margins: -6
              cursorShape: Qt.PointingHandCursor
              onClicked: root.close()
            }
          }
        }

        Rectangle {
          Layout.fillWidth: true
          Layout.preferredHeight: 88
          color: "#091310"
          border.width: 1
          border.color: root.panelLine
          radius: 3

          Canvas {
            id: scope
            anchors.fill: parent
            anchors.margins: 8
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()

            onPaint: {
              var ctx = getContext("2d")
              ctx.clearRect(0, 0, width, height)
              ctx.lineWidth = 1
              ctx.strokeStyle = "#1d332d"
              for (var x = 0; x < width; x += 20) {
                ctx.beginPath()
                ctx.moveTo(x, 0)
                ctx.lineTo(x, height)
                ctx.stroke()
              }
              for (var y = 0; y < height; y += 20) {
                ctx.beginPath()
                ctx.moveTo(0, y)
                ctx.lineTo(width, y)
                ctx.stroke()
              }

              var amp = root.recording ? 0.38 : (root.transcribing ? 0.24 : 0.12)
              ctx.beginPath()
              ctx.strokeStyle = root.panelText
              ctx.lineWidth = 1.4
              for (var px = 0; px <= width; px += 2) {
                var t = px / Math.max(1, width)
                var env = 0.45 + 0.55 * Math.abs(Math.sin(t * 9 + root.wavePhase))
                var py = height / 2 + Math.sin(t * 42 + root.wavePhase * 3) * height * amp * env
                if (px === 0) ctx.moveTo(px, py)
                else ctx.lineTo(px, py)
              }
              ctx.stroke()

              var playhead = width * 0.66
              ctx.beginPath()
              ctx.strokeStyle = root.recordColor
              ctx.lineWidth = 1
              ctx.moveTo(playhead, 4)
              ctx.lineTo(playhead, height - 4)
              ctx.stroke()
              ctx.beginPath()
              ctx.fillStyle = root.recordColor
              ctx.arc(playhead, height / 2, 3, 0, Math.PI * 2)
              ctx.fill()
            }

            Timer {
              interval: 90
              running: root.recording || root.transcribing
              repeat: true
              onTriggered: {
                root.wavePhase += 0.2
                scope.requestPaint()
              }
            }
          }
        }

        ColumnLayout {
          Layout.fillWidth: true
          spacing: 0

          Repeater {
            model: [
              { title: "麦克风", sub: "默认输入源" },
              { title: "本机代理", sub: "127.0.0.1" },
              { title: "豆包", sub: "网页版听写" },
              { title: "voxtype", sub: "当前光标" }
            ]

            delegate: RowLayout {
              id: stage
              required property int index
              required property var modelData

              Layout.fillWidth: true
              Layout.preferredHeight: 42
              spacing: 10

              readonly property bool stageActive: index === 0 ? root.recording : index === 1 ? root.online : index === 2 ? root.transcribing : root.online

              Rectangle {
                width: 30
                height: 30
                radius: 3
                color: "transparent"
                border.width: 1
                border.color: stage.stageActive ? root.signalColor : root.panelLine

                Text {
                  anchors.centerIn: parent
                  text: ["󰍬", "⇄", "☁", "⌨"][stage.index]
                  color: stage.stageActive ? root.signalColor : root.panelMuted
                  font.family: Style.font.family
                  font.pixelSize: 15
                }
              }

              ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                Text {
                  text: stage.modelData.title
                  color: root.panelText
                  font.family: Style.font.family
                  font.pixelSize: 12
                  font.bold: true
                }

                Text {
                  text: stage.modelData.sub
                  color: root.panelMuted
                  font.family: Style.font.family
                  font.pixelSize: 10
                }
              }
            }
          }
        }

        Item { Layout.fillHeight: true }

        RowLayout {
          Layout.fillWidth: true
          spacing: 8

          Text {
            text: "无需 API key"
            color: root.panelMuted
            font.family: Style.font.family
            font.pixelSize: 10
          }

          Item { Layout.fillWidth: true }

          Text {
            text: "音频 → 豆包"
            color: root.panelMuted
            font.family: Style.font.family
            font.pixelSize: 10
          }
        }
      }
    }
  }
}
