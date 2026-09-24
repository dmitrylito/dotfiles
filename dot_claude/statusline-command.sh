#!/usr/bin/env bash
# Claude Code status line: "<cwd> | 5h: N% | 7d: N%" on the left, model/effort/context
# right-aligned. Reads the status JSON on stdin (see `claude` statusLine settings).
input=$(cat)

model=$(echo "$input" | jq -r '.model.display_name // empty')
# Drop the trailing context-window note, e.g. "Claude Opus 4.8 (1M context)" -> "Claude Opus 4.8"
model="${model%% (*}"
effort=$(echo "$input" | jq -r '.effort.level // empty')
[ -n "$effort" ] && model="$model · $effort"
ctx_used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
[ -n "$ctx_used" ] && model="$model ($(printf '%.0f' "$ctx_used")%)"

five=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
five_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
week=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
week_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')

cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // empty')
[ -n "$cwd" ] && cwd="${cwd##*/}"

# Format a resets_at value (unix epoch or ISO 8601) with the given date format;
# prints nothing if the timestamp can't be parsed. GNU date takes -d; macOS BSD date
# has no -d, so fall back to an epoch (jq parses ISO) formatted with date -r.
fmt_reset() {
  local ts=$1 fmt=$2 out
  case "$ts" in
    '')         return ;;
    *[!0-9]*)   out=$(date -d "$ts" "$fmt" 2>/dev/null) ;;
    *)          out=$(date -d "@$ts" "$fmt" 2>/dev/null) ;;
  esac
  if [ -z "$out" ]; then
    case "$ts" in
      *[!0-9]*) ts=$(jq -rn --arg t "$ts" '$t | sub("\\.[0-9]+"; "") | fromdateiso8601' 2>/dev/null) ;;
    esac
    [ -n "$ts" ] && out=$(date -r "$ts" "$fmt" 2>/dev/null)
  fi
  [ -n "$out" ] && printf '%s' "${out# }"
}

join() {
  local acc=""
  for part in "$@"; do
    [ -z "$part" ] && continue
    [ -n "$acc" ] && acc="$acc | $part" || acc="$part"
  done
  printf '%s' "$acc"
}

five_short="" five_full=""
if [ -n "$five" ]; then
  five_short="5h: $(printf '%.0f' "$five")%"
  reset_str=$(fmt_reset "$five_reset" +%-l:%M%p)
  [ -n "$reset_str" ] && five_full="$five_short (resets $reset_str)" || five_full="$five_short"
fi
week_short="" week_full=""
if [ -n "$week" ]; then
  week_short="7d: $(printf '%.0f' "$week")%"
  reset_str=$(fmt_reset "$week_reset" '+%a %-l:%M%p')
  [ -n "$reset_str" ] && week_full="$week_short (resets $reset_str)" || week_full="$week_short"
fi

[ -z "$model" ] && [ -z "$cwd$five_short$week_short" ] && exit 0

# Claude Code normally supplies COLUMNS; use 80 when the hook has no terminal.
width="${COLUMNS:-80}"
# The status box is narrower than the terminal (border + padding). Padding out to the
# full width makes the line word-wrap inside the box, and the wrapped tail — the model,
# effort and context — is not displayed. Reserve enough columns that it never wraps.
margin="${CLAUDE_STATUSLINE_MARGIN:-6}"
usable=$(( width - margin ))
[ "$usable" -lt 20 ] && usable=20

# Give up detail on the left before ever losing the model block on the right.
left=""
for candidate in \
  "$(join "$cwd" "$five_full" "$week_full")" \
  "$(join "$cwd" "$five_short" "$week_short")" \
  "$cwd" \
  ""
do
  if [ -z "$candidate" ] || [ $(( ${#candidate} + 1 + ${#model} )) -le "$usable" ]; then
    left="$candidate"
    break
  fi
done

if [ -n "$model" ] && [ -n "$left" ]; then
  pad=$(( usable - ${#left} - ${#model} ))
  [ "$pad" -lt 1 ] && pad=1
  printf '%s%*s%s' "$left" "$pad" "" "$model"
elif [ -n "$model" ]; then
  printf '%s' "${model:0:$usable}"
else
  printf '%s' "${left:0:$usable}"
fi
