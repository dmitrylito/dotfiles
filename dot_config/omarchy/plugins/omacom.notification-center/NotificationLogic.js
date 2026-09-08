// Helpers for the omacom.notification-center bar widget.
// parseHistoryFiles consumes the Omarchy 4 notifications service's on-disk
// history format: one JSON object per file under
// ~/.local/state/omarchy/notifications/history/, streamed to the widget as
// "<fileName>\t<json>" lines (see the history Process in BarWidget.qml).

function isChromiumDerived(app, appIcon) {
  var source = (String(app || "") + "\n" + String(appIcon || "")).toLowerCase()
  return source.indexOf("chrom") >= 0 || source.indexOf("brave") >= 0 ||
         source.indexOf("vivaldi") >= 0 || source.indexOf("microsoft-edge") >= 0 ||
         source.indexOf("opera") >= 0
}

function sanitizeBody(body, app, appIcon) {
  var text = String(body || "").replace(/<img[^>]*>/gi, "")
  if (!isChromiumDerived(app, appIcon)) return text

  return text
    .replace(/^\s*<a\b[^>]*>\s*(?:https?:\/\/|www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:\/[^<\s]*)?\s*<\/a>\s*/i, "")
    .replace(/^\s*(?:https?:\/\/|www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:\/\S*)?\s+/i, "")
}

function parseHistoryFiles(raw) {
  var lines = String(raw || "").split("\n")
  var rows = []
  for (var i = 0; i < lines.length; i++) {
    var tab = lines[i].indexOf("\t")
    if (tab <= 0) continue
    try {
      var e = JSON.parse(lines[i].slice(tab + 1))
      rows.push({
        fileName: lines[i].slice(0, tab),
        app: String(e.app || ""),
        appIcon: String(e.appIcon || ""),
        summary: String(e.summary || ""),
        body: String(e.body || ""),
        image: String(e.image || ""),
        glyph: String(e.glyph || ""),
        urgency: typeof e.urgency === "number" ? e.urgency : 1,
        timestamp: Number(e.timestamp || 0)
      })
    } catch (err) {
      // A half-written or corrupt file shouldn't hide the rest of history.
    }
  }
  rows.sort(function(a, b) { return b.timestamp - a.timestamp })
  return rows
}

function relativeTime(timestamp, now) {
  var seconds = Math.max(0, Math.round((now - Number(timestamp || 0)) / 1000))
  if (seconds < 60) return "now"
  var minutes = Math.round(seconds / 60)
  if (minutes < 60) return minutes + "m"
  var hours = Math.round(minutes / 60)
  if (hours < 24) return hours + "h"
  return Math.round(hours / 24) + "d"
}
