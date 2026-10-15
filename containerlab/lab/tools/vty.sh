#!/usr/bin/env bash
# Drive a QuaggaSRx bgpd VTY from the host, without sudo and without vtysh
# (the image ships neither vtysh nor a unix socket — see PHASE1.md).
#
#   vty.sh <node> <command> [<command> ...]
#
#   vty.sh clab-bgpsec-p4-as64604 "show ip bgp"
#   vty.sh clab-bgpsec-p4-as64666 -c "network 10.64.2.0/24"
#
# With -c, commands are run inside `configure terminal; router bgp <ASN>`,
# with the ASN read from the node's running config. Output is trimmed to
# just the command results.
#
# Destined for labkit.py — this is the shell prototype of that wrapper.
set -euo pipefail

NODE="${1:?usage: vty.sh <node> [-c] <command> ...}"; shift
CONFIG=0
if [ "${1:-}" = "-c" ]; then CONFIG=1; shift; fi

script='echo zebra; sleep 1;'
if [ "$CONFIG" -eq 1 ]; then
  asn="${NODE##*-as}"
  script+=' echo enable; sleep 1; echo "configure terminal"; sleep 1;'
  script+=" echo \"router bgp $asn\"; sleep 1;"
else
  script+=' echo enable; sleep 1;'
fi
for cmd in "$@"; do
  script+=" echo \"$cmd\"; sleep 2;"
done
[ "$CONFIG" -eq 1 ] && script+=' echo end; sleep 1;'
script+=' sleep 1'

docker exec "$NODE" bash -c "($script) | telnet localhost 2605" 2>&1 \
  | sed -n '/^bgpd[>#]/,$p'
