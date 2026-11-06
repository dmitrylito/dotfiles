#!/bin/bash
# Bash fallback for the SUPER+U pop-out, bound to SUPER+SHIFT+U; the native Lua
# version lives in ~/.config/hypr/bindings.lua.
#
# Floating removes a window from the dwindle tree and un-floating re-inserts it
# by splitting whichever tiled window was last focused, so pop-out records the
# adjacent tiled neighbour and the side we sat on and restore re-focuses that
# neighbour first. Exact for a single-neighbour slot (incl. offset 2-window
# splits); best-effort when the neighbour is a subtree, which dwindle cannot
# rebuild from a re-inserted leaf.

MAX_W_FRAC=0.80
MAX_H_FRAC=0.82
RATIO=1.6         # 16:10
EDGE_TOL=100      # px: max gap between window edges still counted as "adjacent"

STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/hypr-popout"
mkdir -p "$STATE_DIR"

WIN=$(hyprctl activewindow -j)
ADDR=$(echo "$WIN" | jq -r '.address // empty')
[ -z "$ADDR" ] && exit 0
FLOAT=$(echo "$WIN" | jq -r '.floating')
STATE="$STATE_DIR/$ADDR"

# Emits "<neighbour-addr> <l|r|u|d>" for the adjacent tiled window sharing the
# longest edge, or "" if there is none. Args via --argjson ws / --arg a.
NEIGHBOR_JQ='
. as $c
| ($c[]|select(.address==$a)) as $p
| $p.at[0] as $px | $p.at[1] as $py
| ($p.at[0]+$p.size[0]) as $pr | ($p.at[1]+$p.size[1]) as $pb
| [ $c[]|select(.workspace.id==$ws and .floating==false and .address!=$a)
    | . as $n
    | $n.at[0] as $nx | $n.at[1] as $ny
    | ($n.at[0]+$n.size[0]) as $nr | ($n.at[1]+$n.size[1]) as $nb
    | (([$pb,$nb]|min)-([$py,$ny]|max)) as $vo
    | (([$pr,$nr]|min)-([$px,$nx]|max)) as $ho
    | [ {side:"l", gap:(($nx-$pr)|fabs), ov:$vo, ok:($vo>0)},
        {side:"r", gap:(($px-$nr)|fabs), ov:$vo, ok:($vo>0)},
        {side:"u", gap:(($ny-$pb)|fabs), ov:$ho, ok:($ho>0)},
        {side:"d", gap:(($py-$nb)|fabs), ov:$ho, ok:($ho>0)} ]
    | map(select(.ok and .gap<=$tol)) | sort_by(.gap) | .[0] // empty
    | {addr:$n.address, side:.side, ov:.ov} ]
| sort_by(-.ov) | .[0] // empty
| if . == null then "" else "\(.addr) \(.side)" end'

if [ "$FLOAT" = "true" ]; then
  [ -f "$STATE" ] || {
    hyprctl dispatch 'hl.dsp.window.float({ action = "toggle" })'
    exit 0
  }
  read -r NEIGHBOR SIDE TILED N2 LCW TCH < "$STATE"; rm -f "$STATE"
  WS=$(echo "$WIN" | jq -r '.workspace.id')

  # No recorded neighbour (window was alone), or the tiled set changed while
  # popped out (neighbour gone / windows opened/closed): the slot may not exist
  # any more, so just re-tile wherever dwindle wants and stop.
  CLIENTS=$(hyprctl clients -j)
  CUR_TILED=$(echo "$CLIENTS" | jq --argjson ws "$WS" \
    '[.[]|select(.workspace.id==$ws and .floating==false)]|length')
  HAVE_NEIGHBOR=$(echo "$CLIENTS" | jq --arg n "$NEIGHBOR" \
    '[.[]|select(.address==$n)]|length')
  if [ "$NEIGHBOR" = "-" ] || [ "$HAVE_NEIGHBOR" = "0" ] \
     || [ "$((CUR_TILED + 1))" != "$TILED" ]; then
    hyprctl dispatch 'hl.dsp.window.float({ action = "toggle" })'
    exit 0
  fi

  # Re-anchor on the neighbour so dwindle re-splits it back into our old slot.
  hyprctl dispatch "hl.dsp.focus({ window = \"address:$NEIGHBOR\" })" >/dev/null
  hyprctl dispatch "hl.dsp.window.float({ action = \"toggle\", window = \"address:$ADDR\" })" >/dev/null

  # force_split=2 always drops the re-inserted window to the neighbour's
  # right/bottom; if we belonged on the other side, one swap fixes it.
  read -r PX PY < <(hyprctl clients -j | jq -r --arg a "$ADDR" \
    '.[]|select(.address==$a)|"\(.at[0]) \(.at[1])"')
  read -r NX NY < <(hyprctl clients -j | jq -r --arg a "$NEIGHBOR" \
    '.[]|select(.address==$a)|"\(.at[0]) \(.at[1])"')
  hyprctl dispatch "hl.dsp.focus({ window = \"address:$ADDR\" })" >/dev/null
  case "$SIDE" in
    l) [ "$PX" -gt "$NX" ] && hyprctl dispatch 'hl.dsp.window.swap({ direction = "l" })' >/dev/null ;;
    r) [ "$PX" -lt "$NX" ] && hyprctl dispatch 'hl.dsp.window.swap({ direction = "r" })' >/dev/null ;;
    u) [ "$PY" -gt "$NY" ] && hyprctl dispatch 'hl.dsp.window.swap({ direction = "u" })' >/dev/null ;;
    d) [ "$PY" -lt "$NY" ] && hyprctl dispatch 'hl.dsp.window.swap({ direction = "d" })' >/dev/null ;;
  esac

  # For a plain 2-window split, re-apply the original divider (exact resize is
  # keyed on the left/top child's size), so an offset split stays offset.
  if [ "$N2" = "1" ]; then
    hyprctl dispatch "hl.dsp.window.resize({ x = $LCW, y = $TCH, relative = false })" >/dev/null
  fi
  hyprctl dispatch "hl.dsp.focus({ window = \"address:$ADDR\" })" >/dev/null

else
  WS=$(echo "$WIN" | jq -r '.workspace.id')
  CLIENTS=$(hyprctl clients -j)
  read -r NEIGHBOR SIDE < <(echo "$CLIENTS" \
    | jq -r --argjson ws "$WS" --arg a "$ADDR" --argjson tol "$EDGE_TOL" "$NEIGHBOR_JQ")
  [ -z "$NEIGHBOR" ] && NEIGHBOR="-" && SIDE="-"
  TILED=$(echo "$CLIENTS" | jq --argjson ws "$WS" \
    '[.[]|select(.workspace.id==$ws and .floating==false)]|length')

  # Offset restoration only applies to a plain 2-window split. Record the
  # left/top child's dimensions -- the value `resizeactive exact` keys on.
  N2=0; LCW=0; TCH=0
  if [ "$TILED" = "2" ] && [ "$NEIGHBOR" != "-" ]; then
    N2=1
    read -r PW PH < <(echo "$CLIENTS" | jq -r --arg a "$ADDR" \
      '.[]|select(.address==$a)|"\(.size[0]) \(.size[1])"')
    read -r NW NH < <(echo "$CLIENTS" | jq -r --arg a "$NEIGHBOR" \
      '.[]|select(.address==$a)|"\(.size[0]) \(.size[1])"')
    case "$SIDE" in
      l) LCW=$PW; TCH=$PH ;;   # horizontal split, we are the left child
      r) LCW=$NW; TCH=$PH ;;   # horizontal split, neighbour is the left child
      u) LCW=$PW; TCH=$PH ;;   # vertical split, we are the top child
      d) LCW=$PW; TCH=$NH ;;   # vertical split, neighbour is the top child
    esac
  fi
  echo "$NEIGHBOR $SIDE $TILED $N2 $LCW $TCH" > "$STATE"

  MON=$(echo "$WIN" | jq '.monitor')
  read -r MW MH < <(hyprctl monitors -j | jq -r --argjson m "$MON" \
    '.[] | select(.id == $m) | "\(.width / .scale) \(.height / .scale)"')
  read -r POPW POPH < <(awk -v w="$MW" -v h="$MH" -v wf="$MAX_W_FRAC" \
    -v hf="$MAX_H_FRAC" -v r="$RATIO" 'BEGIN{
      maxw = w*wf; maxh = h*hf; pw = maxw; ph = pw/r;
      if (ph > maxh) { ph = maxh; pw = ph*r; }
      printf "%d %d", pw, ph;
    }')
  [ -z "$POPW" ] && { POPW=2800; POPH=1750; }

  hyprctl dispatch 'hl.dsp.window.float({ action = "toggle" })'
  hyprctl dispatch "hl.dsp.window.resize({ x = $POPW, y = $POPH, relative = false })"
  hyprctl dispatch 'hl.dsp.window.center()'
fi
