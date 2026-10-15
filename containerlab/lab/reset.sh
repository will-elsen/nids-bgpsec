#!/usr/bin/env bash
# Put the lab back to its starting state without redeploying it.
#
#   ./reset.sh            back to Part A: no validation, no attack, no ROA
#   ./reset.sh b|c|d      back to that part, attack and ROA state cleared
#   ./reset.sh --hard     destroy and redeploy from scratch
#
# Use this when an exercise has left the lab somewhere confusing, or before
# handing the machine to the next student. `--hard` additionally rebuilds the
# RPKI trust chain, which is the right move if the CA or validator is the
# thing behaving strangely.
#
# Everything here also exists as labkit calls (`lab.reset()`, `lab.destroy()`)
# for use inside the notebook; this script is for when you are not in one.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ "${1:-}" = "--hard" ]; then
	python3 - <<-'PY'
	import labkit as lab
	lab.destroy()
	lab.deploy()
	PY
	exit 0
fi

PART="${1:-a}"
case "$PART" in
	a|b|c|d) ;;
	*) echo "usage: reset.sh [a|b|c|d|--hard]" >&2; exit 1 ;;
esac

python3 - "$PART" <<-'PY'
import sys
import labkit as lab

part = sys.argv[1]
try:
    lab.attack("stop")
except lab.LabError:
    pass                      # nothing announced, or the lab is not up yet
try:
    if lab.vrp_count():
        lab.remove_roa()
except lab.LabError:
    pass                      # no ROA, or the CA is not reachable
lab.set_part(part)
print(f"lab reset to part {part}: no attack, no ROA")
PY
