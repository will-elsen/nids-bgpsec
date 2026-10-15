#!/usr/bin/env bash
# Move the running lab to one of the curriculum's four states.
#
#   set_part.sh <phase4-dir> a|b|c|d
#
# Copies configs/<part>/ over configs/active/ (which the topology binds) and
# restarts each routing daemon in place with `pkill`. The containers, their
# veth links and their addresses all survive — recreating a container would
# destroy the containerlab links and silently break the lab
# (see phase3/PHASE3.md).
#
# This is a restart, not a reload: BGPsec cannot be switched on or off on a
# live session, so every part boundary requires the daemon to come up fresh.
# Sessions drop and re-establish, which takes ~20-30s to reconverge.
#
# RPKI-side state (ROAs in Krill, router certificates) is untouched — a ROA
# issued during Part B is still there in Part C, which the narrative depends on.
set -euo pipefail

PHASE4="${1:?usage: set_part.sh <phase4-dir> a|b|c|d}"
PART="${2:?usage: set_part.sh <phase4-dir> a|b|c|d}"
SRC="$PHASE4/configs/$PART"
ACTIVE="$PHASE4/configs/active"
PREFIX="clab-bgpsec-p4"

[ -d "$SRC" ] || { echo "no such part: $PART (expected $SRC)" >&2; exit 1; }

mkdir -p "$ACTIVE"
cp "$SRC"/*.conf "$ACTIVE"/

# The validation engine goes first, and alone. Its client table is keyed by
# proxy ID and outlives the routers that registered; a router restarting into
# its own stale entry never completes the SRx handshake, gets `undefined` for
# every validation, and then drops the route because `srx policy origin ignore
# undefined` is a QuaggaSRx default. The symptom is a lab that deploys
# cleanly and has no routes, which is a miserable thing to debug at minute
# five of an exercise. Restarting srx_server first gives every router an empty
# table to register into.
docker exec "$PREFIX-srx_server" pkill -x srx_server || true
sleep 4

# Staggered, not all at once: five simultaneous proxy handshakes was enough to
# make one of them lose the race even against a clean table.
for asn in 64601 64602 64603 64604 64666; do
	docker exec "$PREFIX-as$asn" pkill -x bgpd || true
	sleep 2
done
docker exec "$PREFIX-as64605" pkill -x gobgpd || true

echo "part $PART active; daemons restarting"
