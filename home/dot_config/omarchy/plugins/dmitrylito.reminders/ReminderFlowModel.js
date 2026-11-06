function validMinutes(value) {
  var minutes = String(value || "").trim()
  return /^[0-9]+$/.test(minutes) && Number(minutes) > 0 ? minutes : ""
}

function reminderArgs(minutes, message) {
  var valid = validMinutes(minutes)
  if (!valid) return []

  var args = [valid]
  var text = String(message || "")
  if (text.length > 0) args.push(text)
  return args
}

// --- when parsing ------------------------------------------------------------
// Kept in step with the same helpers in the omacom.notification-center plugin.
// The two cannot share a file: each plugin directory is its own QML import
// scope, so a change here has to be mirrored there by hand.
//
// omarchy-reminder only understands minutes from now, so a clock time has to be
// resolved against the current time before it is handed over.

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
  // Rounded up: omarchy-reminder starts its timer a moment after this runs, so
  // rounding down would fire a minute early.
  return Math.max(1, Math.ceil((target.getTime() - nowMs) / 60000))
}

function clockString(atMs) {
  var when = new Date(atMs)
  return ("0" + when.getHours()).slice(-2) + ":" + ("0" + when.getMinutes()).slice(-2)
}

function remainingLabel(atMs, nowMs) {
  var seconds = Math.round((atMs - nowMs) / 1000)
  if (seconds <= 0) return "due"
  if (seconds < 60) return seconds + "s"
  var minutes = Math.round(seconds / 60)
  if (minutes < 60) return minutes + "m"
  var hours = Math.floor(minutes / 60)
  var rest = minutes % 60
  return rest > 0 ? hours + "h " + rest + "m" : hours + "h"
}

function dayLabel(atMs, nowMs) {
  var when = new Date(atMs)
  var now = new Date(nowMs)
  var sameDay = when.getFullYear() === now.getFullYear()
    && when.getMonth() === now.getMonth()
    && when.getDate() === now.getDate()
  return sameDay ? "" : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][when.getDay()] + " "
}

// Echo of what parseWhen made of the input, so the prompt says when it will
// actually fire before the user commits to it.
function whenHint(text, nowMs) {
  if (String(text || "").trim().length === 0) return "45m · 2h30 · 14:30 · 9am"
  var minutes = parseWhen(text, nowMs)
  if (minutes === 0) return "Try 45m, 2h30, 14:30 or 9am"
  var at = nowMs + minutes * 60000
  return "fires " + dayLabel(at, nowMs) + clockString(at) + " · in " + remainingLabel(at, nowMs)
}

if (typeof module !== "undefined") {
  module.exports = {
    validMinutes: validMinutes,
    reminderArgs: reminderArgs,
    parseWhen: parseWhen,
    whenHint: whenHint
  }
}
