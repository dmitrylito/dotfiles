#!/usr/bin/env bash
# One-time switch of a server from systemd-networkd to NetworkManager, the
# stack Cockpit manages (DLCO-1/2 already use it).
#
# Usage, as root on the target host:  server-networkmanager-cutover.sh IFACE
#
# The switch runs in a transient unit (nm-cutover) so a dropped SSH session
# cannot stop it halfway. A rollback timer (nm-cutover-rollback) re-enables
# networkd after 5 minutes unless the post-switch checks pass: the interface
# gets back its current IPv4 address, a default route and a reachable gateway.
# Follow it with:  journalctl -fu nm-cutover
# Keeps systemd-resolved (resolv.conf becomes its stub symlink, as on DLCO-1)
# and restarts the keepalived container so it re-adds its VIP.

set -euo pipefail

run=
if [[ ${1:-} == --run ]]; then
  run=1
  shift
fi
iface=${1:?usage: server-networkmanager-cutover.sh IFACE}
(( EUID == 0 )) || { printf 'run as root\n' >&2; exit 1; }
[[ -e /sys/class/net/$iface ]] || { printf 'no interface %s\n' "$iface" >&2; exit 1; }

rollback_cmd='systemctl disable --now NetworkManager NetworkManager-wait-online;
systemctl enable --now systemd-networkd.socket systemd-networkd systemd-networkd-wait-online;
docker restart caddy-keepalived-1 >/dev/null 2>&1 || true'

if [[ -z $run ]]; then
  systemctl is-enabled -q systemd-networkd || { printf 'systemd-networkd is not enabled; nothing to cut over\n' >&2; exit 1; }
  expected=$(ip -4 -o addr show dev "$iface" scope global | awk '{ sub(/\/.*/, "", $4); print $4; exit }')
  [[ -n $expected ]] || { printf '%s has no IPv4 address\n' "$iface" >&2; exit 1; }

  if [[ ! -L /etc/resolv.conf ]]; then
    cp -a /etc/resolv.conf "/etc/resolv.conf.bak.$(date +%Y%m%d%H%M%S)"
    ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
  fi

  systemd-run --unit=nm-cutover-rollback --on-active=300 --timer-property=AccuracySec=1s \
    /bin/sh -c "$rollback_cmd"
  systemd-run --unit=nm-cutover --collect "$(realpath "$0")" --run "$iface" "$expected"
  printf 'Started. Expecting %s back on %s. Follow: journalctl -fu nm-cutover\n' "$expected" "$iface"
  printf 'Rollback fires in 5 minutes unless the checks pass (stop it early: systemctl stop nm-cutover-rollback.timer).\n'
  exit 0
fi

expected=${2:?}
install -d -m 0700 /etc/NetworkManager/system-connections
keyfile="/etc/NetworkManager/system-connections/$iface.nmconnection"
cat >"$keyfile" <<EOF
[connection]
id=$iface
type=ethernet
interface-name=$iface
zone=public
autoconnect=true

[ipv4]
method=auto

[ipv6]
method=auto
addr-gen-mode=eui64
EOF
chmod 0600 "$keyfile"
install -d /etc/NetworkManager/conf.d
printf '[main]\ndns=systemd-resolved\n' >/etc/NetworkManager/conf.d/dns.conf

systemctl disable --now systemd-networkd.socket systemd-networkd systemd-networkd-wait-online || true
systemctl enable --now NetworkManager
systemctl enable NetworkManager-wait-online

ok=
for _ in $(seq 60); do
  gateway=$(ip route show default dev "$iface" 2>/dev/null | awk '{ print $3; exit }')
  if ip -4 -o addr show dev "$iface" | grep -q " $expected/" && [[ -n $gateway ]] && ping -c1 -W2 "$gateway" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done

docker restart caddy-keepalived-1 >/dev/null 2>&1 || true

if [[ -n $ok ]]; then
  systemctl stop nm-cutover-rollback.timer
  printf 'NetworkManager owns %s with %s via %s; rollback cancelled.\n' "$iface" "$expected" "$gateway"
  nmcli -t -f DEVICE,STATE,CONNECTION device status
else
  printf 'Checks failed; nm-cutover-rollback will restore systemd-networkd.\n' >&2
  exit 1
fi
