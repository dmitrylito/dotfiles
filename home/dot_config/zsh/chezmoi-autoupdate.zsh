# Apply already-fetched dotfile updates synchronously, then let the helper own
# its detached and throttled network update.
#
# Both helper runs are no-ops in the common case but cost ~35ms of bash and git
# forks. Skip them when the applied marker already matches the source HEAD and
# the throttle stamp is fresh. Anything unexpected (packed or detached ref,
# missing file) falls through to the helper, which stays the authority.
_chezmoi_autoupdate_idle() {
  local cache=${XDG_CACHE_HOME:-$HOME/.cache} src head dir ref
  local -i max_min=$(( ${CHEZMOI_AUTOUPDATE_MAX_AGE:-14400} / 60 ))
  local -a fresh=( $cache/chezmoi-autoupdate.stamp(Nmm-$max_min) )
  (( $#fresh )) || return 1
  [[ -r $cache/chezmoi-autoupdate.applied ]] || return 1
  IFS=$'\t' read -r src head < $cache/chezmoi-autoupdate.applied || return 1
  dir=$src
  while [[ $dir != / && ! -d $dir/.git ]]; do dir=${dir:h}; done
  [[ -r $dir/.git/HEAD ]] || return 1
  ref=$(<$dir/.git/HEAD)
  [[ $ref == 'ref: '* && -r $dir/.git/${ref#ref: } ]] || return 1
  [[ $(<$dir/.git/${ref#ref: }) == $head ]]
}

if [[ -x "$HOME/.local/bin/chezmoi-autoupdate" ]]; then
  if [[ -n ${CHEZMOI_AUTOUPDATE_FORCE:-} ]]; then
    "$HOME/.local/bin/chezmoi-autoupdate" --local
    unset CHEZMOI_AUTOUPDATE_FORCE
    "$HOME/.local/bin/chezmoi-autoupdate" --force
  elif ! _chezmoi_autoupdate_idle; then
    "$HOME/.local/bin/chezmoi-autoupdate" --local
    "$HOME/.local/bin/chezmoi-autoupdate"
  fi
fi
unfunction _chezmoi_autoupdate_idle
