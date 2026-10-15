#!/bin/sh
# PID 1 supervisor for the routing daemon.
#
# Why this exists: the curriculum moves the lab through four states (no
# validation -> ROV -> BGPsec -> partial deployment), and QuaggaSRx cannot
# turn BGPsec on or off on a live session. Verified on 2026-07-31: removing
# `neighbor X bgpsec both` from both ends of a session and clearing it leaves
# bgpd emitting BGPsec-shaped UPDATEs to a peer that no longer negotiated the
# capability — the peer rejects them with "Missing well-known attribute 3" and
# the session sits in Idle forever. The setting only takes effect at daemon
# start.
#
# Restarting the *container* would do it, but containerlab veths do not
# survive container recreation (see PHASE3.md in the nids-bgpsec-key repo), so that breaks the lab.
# With this as PID 1 the daemon can be restarted in place:
#
#   edit the bind-mounted config on the host, then
#   docker exec <node> pkill -x bgpd        (or gobgpd)
#
# The container, its interfaces, and its addresses all survive.
#
# The 1s floor keeps a config syntax error from spinning the CPU — a student
# who breaks the config sees the daemon flap once a second in `docker logs`
# rather than a silent container exit.
set -u
while true; do
	"$@"
	echo "[supervisor] $1 exited (status $?) — restarting in 1s" >&2
	sleep 1
done
