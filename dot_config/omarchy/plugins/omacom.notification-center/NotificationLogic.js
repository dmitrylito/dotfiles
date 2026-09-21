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

// Which window a history row should focus, as a case-insensitive regex for
// omarchy-hyprland-focus-app. A Chromium PWA notifies as plain "Chromium"
// while its window class is chrome-<host>__<path>-Profile_N, so the bare app
// name matches the wrong window; the origin Chromium prepends to the body
// names the right one.
function focusPattern(app, appIcon, body) {
  var name = String(app || "")
  if (!isChromiumDerived(app, appIcon)) return name

  var host = /(?:^|[">\s])(?:https?:\/\/)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[:/"<\s]|$)/i
             .exec(String(body || ""))
  return host ? host[1] : name
}

// --- reminders ---------------------------------------------------------------
// `omarchy reminder show --json` emits {count, active, tooltip, reminders: [...]}.
// Each entry carries `unit` (the transient systemd unit stem, without the
// .timer/.service suffix), `message` (empty for an unlabeled timer) and `at`
// (fire time in epoch SECONDS, not ms).

function parseReminders(raw) {
  var rows = []
  try {
    var data = JSON.parse(String(raw || ""))
    var list = (data && data.reminders) ? data.reminders : []
    for (var i = 0; i < list.length; i++) {
      var entry = list[i]
      rows.push({
        unit: String(entry.unit || ""),
        message: String(entry.message || ""),
        label: String(entry.label || entry.message || ""),
        minutes: Number(entry.minutes || 0),
        at: Number(entry.at || 0)
      })
    }
  } catch (err) {
    // No systemd user bus, or a CLI failure — treat as "no reminders known"
    // rather than clearing a list the user is looking at for a parse error.
  }
  rows.sort(function(a, b) { return a.at - b.at })
  return rows
}

// omarchy-reminder only accepts a whole number of minutes > 0; anything else
// must not reach it, because `systemd-run --on-active` would build a unit that
// never fires. Returns 0 for invalid input.
function validMinutes(value) {
  var text = String(value === undefined || value === null ? "" : value).trim()
  if (!/^[0-9]+$/.test(text)) return 0
  var minutes = Number(text)
  return minutes > 0 ? minutes : 0
}

// Everything the user types for "when" funnels through here, because minutes
// from now is the only thing omarchy-reminder understands. Accepts a bare
// count of minutes (45), a duration (45m, 2h, 2h30, 1h 30m) or a clock time
// (14:30, 2:30pm, 9am). A clock time that has already passed today rolls to
// tomorrow. Returns 0 when nothing valid was typed.
//
// A bare number is always minutes, never a clock time: "230" is 230 minutes,
// and "2:30" is half past two.
function parseWhen(text, nowMs) {
  var input = String(text || "").trim().toLowerCase().replace(/^(?:in|at)\s+/, "")
  if (input.length === 0) return 0

  var clock = /^([0-9]{1,2})(?::([0-9]{2}))?\s*(am|pm)$/.exec(input)
    || /^([0-9]{1,2}):([0-9]{2})$/.exec(input)
  if (clock) return minutesUntilClock(Number(clock[1]), Number(clock[2] || 0), clock[3] || "", nowMs)

  return parseDuration(input)
}

function parseDuration(input) {
  var parts = /^(?:([0-9]+)\s*h(?:ours?|rs?)?)?\s*(?:([0-9]+)\s*(?:m(?:in(?:ute)?s?)?)?)?$/.exec(input)
  if (!parts) return 0
  var total = Number(parts[1] || 0) * 60 + Number(parts[2] || 0)
  return total > 0 ? total : 0
}

function minutesUntilClock(hour, minute, meridiem, nowMs) {
  if (minute > 59) return 0
  if (meridiem === "am" || meridiem === "pm") {
    if (hour < 1 || hour > 12) return 0
    hour = hour % 12
    if (meridiem === "pm") hour += 12
  } else if (hour > 23) {
    return 0
  }

  var target = new Date(nowMs)
  target.setHours(hour, minute, 0, 0)
  if (target.getTime() <= nowMs) target.setDate(target.getDate() + 1)
  // Rounded up: omarchy-reminder starts its timer a moment after we compute
  // this, so rounding down would fire a minute early.
  return Math.max(1, Math.ceil((target.getTime() - nowMs) / 60000))
}

// Echo of what parseWhen made of the input, so the field says when it will
// actually fire before the user commits to it.
function whenHint(text, nowMs) {
  if (String(text || "").trim().length === 0) return "45m · 2h30 · 14:30 · 9am"
  var minutes = parseWhen(text, nowMs)
  if (minutes === 0) return "Try 45m, 2h30, 14:30 or 9am"
  var at = (nowMs + minutes * 60000) / 1000
  return "fires " + reminderTimeLabel(at, nowMs) + " · in " + remainingLabel(at, nowMs)
}

function remainingLabel(at, nowMs) {
  var seconds = Math.round(Number(at || 0) - nowMs / 1000)
  if (seconds <= 0) return "due"
  if (seconds < 60) return seconds + "s"
  var minutes = Math.round(seconds / 60)
  if (minutes < 60) return minutes + "m"
  var hours = Math.floor(minutes / 60)
  var rest = minutes % 60
  return rest > 0 ? hours + "h " + rest + "m" : hours + "h"
}

function clockString(at) {
  var when = new Date(Number(at || 0) * 1000)
  return ("0" + when.getHours()).slice(-2) + ":" + ("0" + when.getMinutes()).slice(-2)
}

function reminderTimeLabel(at, nowMs) {
  var when = new Date(Number(at || 0) * 1000)
  var now = new Date(nowMs)
  var sameDay = when.getFullYear() === now.getFullYear()
    && when.getMonth() === now.getMonth()
    && when.getDate() === now.getDate()
  if (sameDay) return clockString(at)
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][when.getDay()] + " " + clockString(at)
}
