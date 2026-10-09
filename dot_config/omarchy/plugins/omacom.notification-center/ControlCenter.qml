// Control-center block at the top of the notification-center popup: Wi-Fi,
// Bluetooth, DND and night-light tiles, output/input volume, and now playing.
// It stands in for the separate network, Bluetooth and audio bar buttons, so a
// tile's chevron expands an inline list rather than opening those panels: a
// bar-widget panel can only be summoned while its widget sits on the bar.
//
// No Repeater here holds a PipeWire, BlueZ or NetworkManager object. Rows are
// primitive snapshots refreshed on a timer, and every action looks the live
// object up again at click time. A delegate still bound to a PwNode that
// PipeWire removed mid-signal segfaults the shell (see the first-party audio
// panel), and the same discipline costs nothing for the other two.

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Bluetooth
import Quickshell.Networking
import Quickshell.Services.Mpris
import Quickshell.Services.Pipewire
import qs.Commons
import qs.Commons as Commons
import qs.Ui

ColumnLayout {
  id: cc

  property QtObject bar: null
  property bool open: false
  property bool dnd: false
  signal dndToggleRequested()

  property color colForeground: Commons.Color.foreground
  property color colDim: Qt.darker(Commons.Color.foreground, 1.4)
  property color colBorder: Style.normalBorderFor(Commons.Color.foreground, Commons.Color.accent)
  property color colSurface: Style.normalFillFor(Commons.Color.foreground, Commons.Color.accent)
  property color colAccent: Commons.Color.accent
  property int cardRadius: Style.cornerRadius
  readonly property string fontFamily: bar ? bar.fontFamily : ""

  // "", "network", "bluetooth", "output" or "input".
  property string expanded: ""
  // The popup's key catcher must stand down while the passphrase field has focus.
  readonly property bool editing: passwordSsid !== ""

  spacing: Style.space(8)

  onOpenChanged: {
    if (!open) {
      expanded = ""
      passwordSsid = ""
    } else {
      refreshMute()
      refreshNight()
      resolveVolumeSink()
    }
    syncScanner()
  }
  onExpandedChanged: {
    passwordSsid = ""
    syncScanner()
    refreshLists()
  }

  function toggleExpanded(name) { expanded = expanded === name ? "" : name }

  function refreshLists() {
    if (expanded === "network") snapshotWifi()
    else if (expanded === "bluetooth") snapshotBluetooth()
    else if (expanded === "output" || expanded === "input") {
      if (!deviceProc.running) deviceProc.running = true
    }
  }

  Timer {
    interval: 2000
    repeat: true
    running: cc.open
    onTriggered: {
      cc.refreshMute()
      cc.refreshNight()
      cc.refreshLists()
    }
  }

  // ------------------------------------------------------------- network

  readonly property var netDevices: Networking.devices ? Networking.devices.values : []
  readonly property var wifiDevice: findDevice(DeviceType.Wifi)
  readonly property var wiredDevice: findDevice(DeviceType.Wired)
  readonly property bool wifiOn: Networking.wifiEnabled
  readonly property var wifiNetworks: wifiDevice && wifiDevice.networks ? wifiDevice.networks.values : []
  readonly property string connectedSsid: {
    for (var i = 0; i < wifiNetworks.length; i++) {
      if (wifiNetworks[i] && wifiNetworks[i].connected) return wifiNetworks[i].name || ""
    }
    return ""
  }
  readonly property bool wiredUp: !!wiredDevice && wiredDevice.connected
  readonly property string networkLabel: {
    var parts = []
    if (wiredUp) parts.push("Ethernet")
    if (connectedSsid !== "") parts.push(connectedSsid)
    if (parts.length > 0) return parts.join(" · ")
    if (!wifiDevice) return "Disconnected"
    return wifiOn ? "Not connected" : "Off"
  }

  function findDevice(type) {
    var fallback = null
    for (var i = 0; i < netDevices.length; i++) {
      var d = netDevices[i]
      if (!d || d.type !== type) continue
      if (d.connected) return d
      if (!fallback) fallback = d
    }
    return fallback
  }

  function networkFor(ssid) {
    for (var i = 0; i < wifiNetworks.length; i++) {
      if (wifiNetworks[i] && wifiNetworks[i].name === ssid) return wifiNetworks[i]
    }
    return null
  }

  function needsPassphrase(net) {
    return net.security !== WifiSecurityType.Open && net.security !== WifiSecurityType.Owe
  }

  property var wifiRows: []
  property string passwordSsid: ""

  function snapshotWifi() {
    var seen = ({})
    var rows = []
    for (var i = 0; i < wifiNetworks.length; i++) {
      var n = wifiNetworks[i]
      if (!n || !n.name || seen[n.name]) continue
      seen[n.name] = true
      rows.push({
        ssid: String(n.name),
        connected: !!n.connected,
        known: !!n.known,
        secured: needsPassphrase(n),
        strength: Math.round((n.signalStrength || 0) * 100)
      })
    }
    rows.sort(function(a, b) {
      if (a.connected !== b.connected) return a.connected ? -1 : 1
      if (a.known !== b.known) return a.known ? -1 : 1
      return b.strength - a.strength
    })
    wifiRows = rows
  }

  // scannerEnabled lives on the shared WifiDevice; only release the device this
  // block switched on, so a first-party network panel open elsewhere keeps its scan.
  property var scannerDevice: null
  function syncScanner() {
    var want = open && expanded === "network" && wifiOn ? wifiDevice : null
    if (scannerDevice && scannerDevice !== want) scannerDevice.scannerEnabled = false
    if (want) want.scannerEnabled = true
    scannerDevice = want
  }
  onWifiOnChanged: syncScanner()
  onWifiDeviceChanged: syncScanner()

  function activateWifi(row) {
    var net = networkFor(row.ssid)
    if (!net) return
    if (net.connected) { net.disconnect(); return }
    if (net.known || !needsPassphrase(net)) { net.connect(); return }
    passwordSsid = row.ssid
    Qt.callLater(function() { passField.text = ""; passField.forceActiveFocus() })
  }

  function submitPassphrase() {
    var net = networkFor(passwordSsid)
    if (net && passField.text !== "") net.connectWithPsk(passField.text)
    passwordSsid = ""
  }

  // ----------------------------------------------------------- bluetooth

  readonly property var adapter: Bluetooth.defaultAdapter
  readonly property bool btOn: !!adapter && adapter.enabled
  readonly property var btDevices: Bluetooth.devices ? Bluetooth.devices.values : []
  readonly property string btLabel: {
    if (!adapter) return "Unavailable"
    if (!btOn) return "Off"
    var names = []
    for (var i = 0; i < btDevices.length; i++) {
      var d = btDevices[i]
      if (d && d.connected) names.push(d.name || d.deviceName || d.address)
    }
    return names.length > 0 ? names.join(", ") : "On"
  }
  property var btRows: []

  function snapshotBluetooth() {
    var rows = []
    for (var i = 0; i < btDevices.length; i++) {
      var d = btDevices[i]
      if (!d || !(d.paired || d.bonded || d.trusted)) continue
      rows.push({
        address: String(d.address || ""),
        name: String(d.name || d.deviceName || d.address || ""),
        connected: !!d.connected,
        battery: d.batteryAvailable ? Math.round(d.battery * 100) : -1
      })
    }
    rows.sort(function(a, b) {
      if (a.connected !== b.connected) return a.connected ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    btRows = rows
  }

  // rfkill, not adapter.enabled: BlueZ's Powered is not persisted across boots
  // (same reasoning as the first-party Bluetooth panel).
  function toggleBluetooth() {
    if (!adapter) return
    Quickshell.execDetached(["omarchy-bluetooth-power", adapter.enabled ? "off" : "on"])
  }

  function activateBluetooth(row) {
    if (!row.address) return
    Quickshell.execDetached(["omarchy-bluetooth-device", row.connected ? "disconnect" : "connect", row.address])
  }

  // --------------------------------------------------------- night light

  // omarchy hands its first-party service proxies (night light, media) only to
  // kind "bar" plugins, never to a bar-widget, so night light goes through the
  // service's IPC target and media through MPRIS directly.
  property bool nightKnown: false
  property bool nightOn: false
  // The service applies the temperature asynchronously, so a status poll right
  // after a toggle still reports the old state.
  property double nightHoldUntil: 0

  function refreshNight() {
    if (nightProc.running || Date.now() < nightHoldUntil) return
    nightProc.running = true
  }

  function toggleNight() {
    nightOn = !nightOn
    nightHoldUntil = Date.now() + 1500
    Quickshell.execDetached(["omarchy-shell", "-q", "nightlight", nightOn ? "enable" : "disable"])
  }

  Process {
    id: nightProc
    command: ["omarchy-shell", "nightlight", "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (Date.now() < cc.nightHoldUntil) return
        try {
          cc.nightOn = !!JSON.parse(text).enabled
          cc.nightKnown = true
        } catch (e) {
          cc.nightKnown = false
        }
      }
    }
  }

  // --------------------------------------------------------------- audio

  readonly property var pwNodes: Pipewire.nodes ? Pipewire.nodes.values : []
  readonly property var sink: Pipewire.defaultAudioSink
  readonly property var source: Pipewire.defaultAudioSource

  // omarchy-audio-output-sink resolves the default output through any tuning
  // filter to the physical sink whose volume the keys and OSD use.
  property string volumeSinkName: ""
  readonly property var volumeSink: {
    if (volumeSinkName === "" || !sink) return sink
    if (volumeSinkName === String(sink.name)) return sink
    for (var i = 0; i < pwNodes.length; i++) {
      var n = pwNodes[i]
      if (n && n.isSink && !n.isStream && String(n.name) === volumeSinkName && n.audio) return n
    }
    return sink
  }
  onSinkChanged: resolveVolumeSink()

  PwObjectTracker {
    objects: [cc.volumeSink, cc.source].filter(function(n) { return !!n })
  }

  readonly property real outputVolume: volumeSink && volumeSink.audio ? volumeSink.audio.volume : 0
  readonly property real inputVolume: source && source.audio ? source.audio.volume : 0

  // Mute state comes from the audio server, not the PwNodes: Quickshell can keep
  // unbound nodes around after a USB reconnect (see dmitrylito.audio).
  readonly property string masterControl: Quickshell.env("HOME") + "/.config/omarchy/plugins/dmitrylito.audio/audio-master-control"
  property bool outputMuted: false
  property bool inputMuted: false

  function refreshMute() { if (!muteProc.running) muteProc.running = true }
  function resolveVolumeSink() { if (!volumeSinkProc.running) volumeSinkProc.running = true }

  function runMute(action) {
    muteProc.command = [masterControl, action]
    muteProc.running = true
  }
  function toggleOutputMute() { if (!muteProc.running) runMute("sink-toggle") }
  function toggleInputMute() { if (!muteProc.running) runMute("source-toggle") }

  function setOutputVolume(v) {
    if (volumeSink && volumeSink.audio) volumeSink.audio.volume = Math.max(0, Math.min(1, v))
  }
  function setInputVolume(v) {
    if (source && source.audio) source.audio.volume = Math.max(0, Math.min(1, v))
  }

  function outputGlyph() {
    if (outputMuted || outputVolume <= 0) return "󰝟"
    if (outputVolume < 0.34) return "󰕿"
    if (outputVolume < 0.67) return "󰖀"
    return "󰕾"
  }

  property var sinkRows: []
  property var sourceRows: []
  property string defaultSinkName: ""
  property string defaultSourceName: ""

  function loadDevices(raw) {
    var parts = String(raw || "").split("\n@@\n")
    var sinks = [], sources = []
    try {
      JSON.parse(parts[0] || "[]").forEach(function(s) {
        sinks.push({ id: String(s.properties["object.id"] || ""), name: s.name, label: s.description || s.name })
      })
      JSON.parse(parts[1] || "[]").forEach(function(s) {
        if (s.properties["device.class"] === "monitor") return
        sources.push({ id: String(s.properties["object.id"] || ""), name: s.name, label: s.description || s.name })
      })
    } catch (e) {
      return
    }
    defaultSinkName = String(parts[2] || "").trim()
    defaultSourceName = String(parts[3] || "").trim()
    sinkRows = sinks
    sourceRows = sources
  }

  function selectDevice(kind, row) {
    if (!row.id || !row.name) return
    Quickshell.execDetached([kind === "output" ? "omarchy-audio-output-set-default" : "omarchy-audio-input-set-default", row.id, row.name])
    if (kind === "output") defaultSinkName = row.name
    else defaultSourceName = row.name
  }

  Process {
    id: muteProc
    command: [cc.masterControl, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var f = String(text).trim().split(/\s+/)
        if (f.length < 3) return
        cc.outputMuted = f[1] !== "1"
        cc.inputMuted = f[2] !== "1"
      }
    }
    onExited: command = [cc.masterControl, "status"]
  }

  Process {
    id: volumeSinkProc
    command: ["omarchy-audio-output-sink"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: cc.volumeSinkName = String(text).trim()
    }
  }

  Process {
    id: deviceProc
    command: ["bash", "-c", "pactl -f json list sinks; printf '\\n@@\\n'; pactl -f json list sources; printf '\\n@@\\n'; pactl get-default-sink; printf '\\n@@\\n'; pactl get-default-source"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: cc.loadDevices(text)
    }
  }

  // --------------------------------------------------------------- media

  readonly property var players: Mpris.players ? Mpris.players.values : []
  readonly property var player: {
    var fallback = null
    for (var i = 0; i < players.length; i++) {
      var p = players[i]
      if (!p || !(p.trackTitle || p.trackArtist)) continue
      if (p.isPlaying) return p
      if (!fallback) fallback = p
    }
    return fallback
  }
  readonly property bool hasMedia: !!player
  readonly property bool playing: hasMedia && player.isPlaying

  // ---------------------------------------------------------- components

  component Glyph: Text {
    font.family: cc.fontFamily
    font.pixelSize: Style.font.body
    color: cc.colForeground
    verticalAlignment: Text.AlignVCenter
  }

  component IconButton: BorderSurface {
    id: ib
    property string glyph: ""
    property real glyphSize: Style.font.body
    signal clicked()
    implicitWidth: Style.space(26)
    implicitHeight: Style.space(26)
    radius: Math.min(Style.space(6), cc.cardRadius)
    color: ibArea.containsMouse ? cc.colBorder : "transparent"
    Glyph {
      anchors.centerIn: parent
      text: ib.glyph
      font.pixelSize: ib.glyphSize
    }
    MouseArea {
      id: ibArea
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: ib.clicked()
    }
  }

  component Tile: BorderSurface {
    id: tile
    property string glyph: ""
    property string title: ""
    property string subtitle: ""
    property bool active: false
    property bool expandable: false
    property bool isExpanded: false
    signal toggled()
    signal expandToggled()

    Layout.fillWidth: true
    Layout.preferredHeight: Style.space(48)
    radius: Math.min(Style.space(12), cc.cardRadius + Style.space(6))
    color: active ? cc.colAccent : (tileArea.containsMouse ? cc.colBorder : cc.colSurface)
    borderSpec: Border.flat(active ? cc.colAccent : cc.colBorder, Style.normalBorderWidth)

    readonly property color ink: active ? Commons.Color.background : cc.colForeground

    MouseArea {
      id: tileArea
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: tile.toggled()
    }

    RowLayout {
      anchors.fill: parent
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(4)
      spacing: Style.space(8)

      Glyph {
        text: tile.glyph
        color: tile.ink
        font.pixelSize: Style.font.title
      }

      ColumnLayout {
        Layout.fillWidth: true
        spacing: 0
        Text {
          Layout.fillWidth: true
          text: tile.title
          font.family: cc.fontFamily
          font.pixelSize: Style.font.bodySmall
          font.bold: true
          color: tile.ink
          elide: Text.ElideRight
        }
        Text {
          Layout.fillWidth: true
          text: tile.subtitle
          visible: text !== ""
          font.family: cc.fontFamily
          font.pixelSize: Style.font.caption
          color: tile.active ? Commons.Color.background : cc.colDim
          elide: Text.ElideRight
        }
      }

      Item {
        visible: tile.expandable
        Layout.preferredWidth: Style.space(26)
        Layout.fillHeight: true
        Glyph {
          anchors.centerIn: parent
          text: tile.isExpanded ? "󰅃" : "󰅀"
          color: tile.ink
        }
        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: tile.expandToggled()
        }
      }
    }
  }

  component ListRow: BorderSurface {
    id: lr
    property string glyph: ""
    property string label: ""
    property string detail: ""
    property bool current: false
    signal clicked()
    Layout.fillWidth: true
    implicitHeight: Style.space(28)
    radius: Math.min(Style.space(6), cc.cardRadius)
    color: lrArea.containsMouse ? cc.colBorder : "transparent"

    RowLayout {
      anchors.fill: parent
      anchors.leftMargin: Style.space(8)
      anchors.rightMargin: Style.space(8)
      spacing: Style.space(8)
      Glyph {
        text: lr.glyph
        visible: text !== ""
        color: lr.current ? cc.colAccent : cc.colDim
      }
      Text {
        Layout.fillWidth: true
        text: lr.label
        font.family: cc.fontFamily
        font.pixelSize: Style.font.bodySmall
        font.bold: lr.current
        color: lr.current ? cc.colAccent : cc.colForeground
        elide: Text.ElideRight
      }
      Text {
        text: lr.detail
        visible: text !== ""
        font.family: cc.fontFamily
        font.pixelSize: Style.font.caption
        color: cc.colDim
      }
    }
    MouseArea {
      id: lrArea
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: lr.clicked()
    }
  }

  component ListBox: BorderSurface {
    default property alias rows: rowsColumn.data
    Layout.fillWidth: true
    implicitHeight: Math.min(rowsColumn.implicitHeight + Style.space(8), Style.space(180))
    radius: Math.min(Style.space(8), cc.cardRadius)
    color: "transparent"
    borderSpec: Border.flat(cc.colBorder, Style.normalBorderWidth)
    clip: true
    Flickable {
      anchors.fill: parent
      anchors.margins: Style.space(4)
      contentHeight: rowsColumn.implicitHeight
      boundsBehavior: Flickable.StopAtBounds
      ColumnLayout {
        id: rowsColumn
        width: parent.width
        spacing: 0
      }
    }
  }

  component VolumeRow: RowLayout {
    id: vr
    property string glyph: ""
    property real value: 0
    property bool muted: false
    property bool available: true
    property bool isExpanded: false
    signal moved(real v)
    signal muteToggled()
    signal expandToggled()
    Layout.fillWidth: true
    spacing: Style.space(6)

    IconButton {
      glyph: vr.glyph
      opacity: vr.muted ? 0.5 : 1
      onClicked: vr.muteToggled()
    }
    PanelSlider {
      bar: cc.bar
      Layout.fillWidth: true
      Layout.preferredHeight: Style.space(24)
      minimum: 0
      maximum: 1
      step: 0.05
      value: vr.value
      enabled: vr.available
      opacity: vr.muted ? 0.5 : 1
      onMoved: function(v) { vr.moved(v) }
      onRightClicked: vr.muteToggled()
    }
    Text {
      Layout.preferredWidth: Style.space(34)
      horizontalAlignment: Text.AlignRight
      text: vr.muted ? "Muted" : Math.round(vr.value * 100) + "%"
      font.family: cc.fontFamily
      font.pixelSize: Style.font.caption
      color: cc.colDim
    }
    IconButton {
      glyph: vr.isExpanded ? "󰅃" : "󰅀"
      onClicked: vr.expandToggled()
    }
  }

  // -------------------------------------------------------------- layout

  GridLayout {
    Layout.fillWidth: true
    columns: 2
    columnSpacing: Style.space(8)
    rowSpacing: Style.space(8)

    Tile {
      glyph: cc.wiredUp && cc.connectedSsid === "" ? "󰈀" : (cc.wifiOn ? "󰖩" : "󰖪")
      title: "Wi-Fi"
      subtitle: cc.networkLabel
      active: cc.wifiOn
      expandable: true
      isExpanded: cc.expanded === "network"
      onToggled: Networking.wifiEnabled = !Networking.wifiEnabled
      onExpandToggled: cc.toggleExpanded("network")
    }

    Tile {
      glyph: !cc.btOn ? "󰂲" : (cc.btLabel !== "On" ? "󰂱" : "󰂯")
      title: "Bluetooth"
      subtitle: cc.btLabel
      active: cc.btOn
      expandable: true
      isExpanded: cc.expanded === "bluetooth"
      onToggled: cc.toggleBluetooth()
      onExpandToggled: cc.toggleExpanded("bluetooth")
    }

    Tile {
      glyph: cc.dnd ? "󰂛" : "󰂚"
      title: "Do Not Disturb"
      subtitle: cc.dnd ? "On" : "Off"
      active: cc.dnd
      onToggled: cc.dndToggleRequested()
    }

    Tile {
      glyph: "󰔎"
      title: "Night Light"
      subtitle: !cc.nightKnown ? "Unavailable" : (cc.nightOn ? "On" : "Off")
      active: cc.nightOn
      onToggled: if (cc.nightKnown) cc.toggleNight()
    }
  }

  ListBox {
    visible: cc.expanded === "network"

    ListRow {
      visible: cc.wifiRows.length === 0
      label: !cc.wifiDevice ? "No Wi-Fi adapter" : (cc.wifiOn ? "Scanning…" : "Wi-Fi is off")
    }

    Repeater {
      model: cc.wifiRows
      delegate: ListRow {
        required property var modelData
        glyph: modelData.connected ? "󰄬" : (modelData.secured && !modelData.known ? "󰌾" : "󰤨")
        label: modelData.ssid
        detail: modelData.connected ? "Connected" : (modelData.known ? "Saved" : modelData.strength + "%")
        current: modelData.connected
        onClicked: cc.activateWifi(modelData)
      }
    }

    RowLayout {
      visible: cc.passwordSsid !== ""
      Layout.fillWidth: true
      Layout.margins: Style.space(4)
      spacing: Style.space(6)

      TextField {
        id: passField
        Layout.fillWidth: true
        password: true
        placeholderText: "Passphrase for " + cc.passwordSsid
        foreground: cc.colForeground
        accent: cc.colAccent
        font.pixelSize: Style.font.bodySmall
        verticalPadding: Style.spacing.xs
        onAccepted: cc.submitPassphrase()
        Keys.onEscapePressed: cc.passwordSsid = ""
      }
      Button {
        text: "Join"
        bordered: true
        foreground: cc.colForeground
        accent: cc.colAccent
        fontFamily: cc.fontFamily
        fontSize: Style.font.caption
        verticalPadding: Style.spacing.xs
        onClicked: cc.submitPassphrase()
      }
    }
  }

  ListBox {
    visible: cc.expanded === "bluetooth"

    ListRow {
      visible: cc.btRows.length === 0
      label: cc.btOn ? "No paired devices" : "Bluetooth is off"
    }

    Repeater {
      model: cc.btRows
      delegate: ListRow {
        required property var modelData
        glyph: modelData.connected ? "󰂱" : "󰂯"
        label: modelData.name
        detail: (modelData.battery >= 0 ? modelData.battery + "% · " : "") + (modelData.connected ? "Disconnect" : "Connect")
        current: modelData.connected
        onClicked: cc.activateBluetooth(modelData)
      }
    }
  }

  VolumeRow {
    glyph: cc.outputGlyph()
    value: cc.outputVolume
    muted: cc.outputMuted
    available: !!cc.volumeSink
    isExpanded: cc.expanded === "output"
    onMoved: function(v) { cc.setOutputVolume(v) }
    onMuteToggled: cc.toggleOutputMute()
    onExpandToggled: cc.toggleExpanded("output")
  }

  ListBox {
    visible: cc.expanded === "output"
    Repeater {
      model: cc.sinkRows
      delegate: ListRow {
        required property var modelData
        glyph: "󰓃"
        label: modelData.label
        current: modelData.name === cc.defaultSinkName
        onClicked: cc.selectDevice("output", modelData)
      }
    }
  }

  VolumeRow {
    glyph: cc.inputMuted ? "󰍭" : "󰍬"
    value: cc.inputVolume
    muted: cc.inputMuted
    available: !!cc.source
    isExpanded: cc.expanded === "input"
    onMoved: function(v) { cc.setInputVolume(v) }
    onMuteToggled: cc.toggleInputMute()
    onExpandToggled: cc.toggleExpanded("input")
  }

  ListBox {
    visible: cc.expanded === "input"
    Repeater {
      model: cc.sourceRows
      delegate: ListRow {
        required property var modelData
        glyph: "󰍬"
        label: modelData.label
        current: modelData.name === cc.defaultSourceName
        onClicked: cc.selectDevice("input", modelData)
      }
    }
  }

  BorderSurface {
    visible: cc.hasMedia
    Layout.fillWidth: true
    implicitHeight: Style.space(56)
    radius: Math.min(Style.space(12), cc.cardRadius + Style.space(6))
    color: cc.colSurface
    borderSpec: Border.flat(cc.colBorder, Style.normalBorderWidth)

    RowLayout {
      anchors.fill: parent
      anchors.margins: Style.space(8)
      spacing: Style.space(10)

      Item {
        Layout.preferredWidth: Style.space(40)
        Layout.preferredHeight: Style.space(40)
        Image {
          id: art
          anchors.fill: parent
          source: cc.hasMedia ? (cc.player.trackArtUrl || "") : ""
          fillMode: Image.PreserveAspectCrop
          asynchronous: true
          sourceSize.width: Style.space(80)
          sourceSize.height: Style.space(80)
          visible: status === Image.Ready
        }
        Glyph {
          anchors.centerIn: parent
          visible: art.status !== Image.Ready
          text: "󰝚"
          font.pixelSize: Style.font.title
          color: cc.colDim
        }
      }

      ColumnLayout {
        Layout.fillWidth: true
        spacing: 0
        Text {
          Layout.fillWidth: true
          text: cc.hasMedia ? (cc.player.trackTitle || cc.player.identity || "") : ""
          font.family: cc.fontFamily
          font.pixelSize: Style.font.bodySmall
          font.bold: true
          color: cc.colForeground
          elide: Text.ElideRight
        }
        Text {
          Layout.fillWidth: true
          text: cc.hasMedia ? (cc.player.trackArtist || "") : ""
          visible: text !== ""
          font.family: cc.fontFamily
          font.pixelSize: Style.font.caption
          color: cc.colDim
          elide: Text.ElideRight
        }
      }

      IconButton {
        glyph: "󰒮"
        opacity: cc.hasMedia && cc.player.canGoPrevious ? 1 : 0.4
        onClicked: if (cc.hasMedia && cc.player.canGoPrevious) cc.player.previous()
      }
      IconButton {
        glyph: cc.playing ? "󰏤" : "󰐊"
        glyphSize: Style.font.title
        opacity: cc.hasMedia && cc.player.canTogglePlaying ? 1 : 0.4
        onClicked: if (cc.hasMedia && cc.player.canTogglePlaying) cc.player.togglePlaying()
      }
      IconButton {
        glyph: "󰒭"
        opacity: cc.hasMedia && cc.player.canGoNext ? 1 : 0.4
        onClicked: if (cc.hasMedia && cc.player.canGoNext) cc.player.next()
      }
    }
  }
}
