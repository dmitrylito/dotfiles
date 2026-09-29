#!/usr/bin/env bash
# Review this Omarchy host's package drift against the hand-edited lists in
# packages/omarchy/ and record the decisions. `czu` runs it between pulling and
# applying; run it directly any time. Without a TTY it prints a one-line summary.
# Needs gum (Omarchy base) and expac.
#
#   common/{pacman,aur}.txt          installed on every Omarchy host
#   <host>/{pacman,aur}.txt          installed on this host too
#   removed.txt, <host>/removed.txt  uninstalled everywhere / here; never installed
#   <host>/ignored.txt               installed here, untracked, never asked about
#
# "Removed here" means pacman.log's last event for a declared package is a
# removal. The playbook skips those as well, so an apply never reinstalls a
# package you removed before you decide here. Changed lists are committed and
# pushed; Esc or Ctrl-C at any prompt aborts without changing anything.

set -euo pipefail

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="$(hostname -s 2>/dev/null || uname -n)"
PKG="$SRC/packages/omarchy"
HOST_DIR="$PKG/$HOST"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/omarchy-packages.XXXXXXXX")"
trap 'rm -rf -- "$TMP"' EXIT

names() { cat -- "$@" 2>/dev/null | sed 's/#.*//; s/[[:space:]]//g; /^$/d' | sort -u; }

names "$PKG/common/pacman.txt" "$PKG/common/aur.txt" \
    <(awk '/^    common_linux_packages:/{f=1; next} f && /^      - /{print $2; next} f{exit}' "$SRC/playbook.yml") \
    > "$TMP/shared"
names "$TMP/shared" "$HOST_DIR/pacman.txt" "$HOST_DIR/aur.txt" > "$TMP/declared"
names "$PKG/removed.txt" "$HOST_DIR/removed.txt" > "$TMP/removed"
names "$HOST_DIR/ignored.txt" > "$TMP/ignored"
names /usr/share/omarchy/install/omarchy-base.packages /usr/share/omarchy/install/omarchy-other.packages > "$TMP/omarchy"
pacman -Qq | sort > "$TMP/installed"
pacman -Qmq | sort > "$TMP/foreign"
# Explicit packages nothing hard-depends on. Optional dependencies still count as
# choices: `pacman -Qet` hides them, which dropped 7zip because yazi lists it.
expac -Q '%w|%n|%N' | awk -F'|' '$1 == "explicit" && $3 == "" {print $2}' | grep -v -- '-debug$' | sort > "$TMP/chosen"
awk '/\[ALPM\] (installed|removed|upgraded|reinstalled|downgraded) /{a[$4]=$3}
     END{for (p in a) if (a[p] == "removed") print p}' /var/log/pacman.log | sort > "$TMP/gone"

comm -23 "$TMP/chosen" "$TMP/declared" | comm -23 - "$TMP/removed" | comm -23 - "$TMP/ignored" \
    | comm -23 - "$TMP/omarchy" > "$TMP/new"
comm -23 "$TMP/declared" "$TMP/installed" | comm -12 - "$TMP/gone" | comm -23 - "$TMP/removed" > "$TMP/dropped"

n_new=$(wc -l < "$TMP/new")
n_dropped=$(wc -l < "$TMP/dropped")
(( n_new + n_dropped )) || exit 0

if [[ ! -t 0 || ! -t 1 ]]; then
    printf 'packages: %d undeclared, %d removed here; run %s in a terminal\n' "$n_new" "$n_dropped" "$0"
    exit 0
fi

# gum exits 1 on Esc and 130 on Ctrl-C; Enter with nothing toggled selects nothing.
pick() {
    [[ -s $2 ]] || return 0
    gum choose --no-limit --height 20 --header "$1 (x/tab toggles, ctrl+a all, enter confirms, esc aborts)" < "$2"
}
rest() { comm -23 "$1" <(sort "$2"); }

pick "Installed here, not declared: install on ALL machines" "$TMP/new" | sort > "$TMP/add_all" || exit 0
rest "$TMP/new" "$TMP/add_all" > "$TMP/new2"
pick "Keep on THIS machine ($HOST) only; the rest are ignored" "$TMP/new2" | sort > "$TMP/add_host" || exit 0
rest "$TMP/new2" "$TMP/add_host" > "$TMP/ignore"

pick "Removed here: remove from ALL machines" "$TMP/dropped" | sort > "$TMP/rm_all" || exit 0
rest "$TMP/dropped" "$TMP/rm_all" > "$TMP/dropped2"
pick "Remove on THIS machine ($HOST) only; the rest are reinstalled" "$TMP/dropped2" | sort > "$TMP/rm_host" || exit 0
rest "$TMP/dropped2" "$TMP/rm_host" > "$TMP/reinstall"

changed=()
add() { # file, names...
    local f=$1; shift
    (( $# )) || return 0
    mkdir -p "$(dirname -- "$f")"
    { names "$f"; printf '%s\n' "$@"; } | sort -u > "$TMP/edit"
    cp -- "$TMP/edit" "$f"
    changed+=("$f")
}
drop() { # file, names...
    local f=$1; shift
    [[ -f $f ]] || return 0
    printf '%s\n' "$@" > "$TMP/drop"
    grep -vxFf "$TMP/drop" "$f" > "$TMP/edit" || true
    cmp -s "$TMP/edit" "$f" && return 0
    cp -- "$TMP/edit" "$f"
    changed+=("$f")
}
split_add() { # dir, names file: foreign packages go to aur.txt, the rest to pacman.txt
    add "$1/aur.txt" $(comm -12 "$2" "$TMP/foreign")
    add "$1/pacman.txt" $(comm -23 "$2" "$TMP/foreign")
}

split_add "$PKG/common" "$TMP/add_all"
split_add "$HOST_DIR" "$TMP/add_host"
add "$HOST_DIR/ignored.txt" $(cat "$TMP/ignore")

mapfile -t rm_all < "$TMP/rm_all"
if (( ${#rm_all[@]} )); then
    add "$PKG/removed.txt" "${rm_all[@]}"
    for f in "$PKG"/*/pacman.txt "$PKG"/*/aur.txt; do drop "$f" "${rm_all[@]}"; done
fi
mapfile -t rm_host < "$TMP/rm_host"
if (( ${#rm_host[@]} )); then
    drop "$HOST_DIR/pacman.txt" "${rm_host[@]}"
    drop "$HOST_DIR/aur.txt" "${rm_host[@]}"
    # Still declared for every host, so only a host removal keeps it off here.
    add "$HOST_DIR/removed.txt" $(comm -12 "$TMP/rm_host" "$TMP/shared")
fi

if [[ -s $TMP/reinstall ]]; then
    printf 'Reinstalling: %s\n' "$(tr '\n' ' ' < "$TMP/reinstall")"
    yay -S --needed --noconfirm $(cat "$TMP/reinstall") || printf 'Reinstall failed; the lists are unchanged for these.\n' >&2
fi

(( ${#changed[@]} )) || exit 0
mapfile -t changed < <(printf '%s\n' "${changed[@]}" | sort -u)
git -C "$SRC" add -- "${changed[@]}"
git -C "$SRC" commit -q -m "Update Omarchy package lists from $HOST" -- "${changed[@]}"
git -C "$SRC" push -q || printf 'Push failed; the commit is local.\n' >&2
printf 'Package lists updated: %d file(s)\n' "${#changed[@]}"
