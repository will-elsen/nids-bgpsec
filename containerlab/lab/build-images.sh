#!/usr/bin/env bash
# Phase 0 — build the four images the lab needs.
#
# The three daemon images are built twice: once from the pristine SIDN testbed
# Dockerfile (:upstream), then through a thin overlay (:local) that adds
# tcpdump and a supervisor as PID 1. The supervisor is what lets the
# curriculum restart a daemon against an edited config without recreating the
# container — containerlab's veths would not survive that. The lab only ever
# runs :local tags.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESTBED="$ROOT/bgpsec-testbed"
OVERLAY="$ROOT/lab/overlay"

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

step "tal_share -> bgpsec/tal-share:local"
docker build -t bgpsec/tal-share:local "$TESTBED/docker_images/tal_share"

step "srx_server -> bgpsec/srx-server:upstream"
docker build -t bgpsec/srx-server:upstream "$TESTBED/docker_images/srx_server"

step "srx_server overlay -> bgpsec/srx-server:local"
docker build -t bgpsec/srx-server:local -f "$OVERLAY/srx-server.Dockerfile" "$OVERLAY"

step "quaggasrx -> bgpsec/quaggasrx:upstream"
docker build -t bgpsec/quaggasrx:upstream "$TESTBED/docker_images/quaggasrx"

step "quaggasrx overlay -> bgpsec/quaggasrx:local"
docker build -t bgpsec/quaggasrx:local -f "$OVERLAY/quaggasrx.Dockerfile" "$OVERLAY"

step "gobgpsrx -> bgpsec/gobgpsrx:upstream"
docker build -t bgpsec/gobgpsrx:upstream "$TESTBED/docker_images/gobgpsrx"

step "gobgpsrx overlay -> bgpsec/gobgpsrx:local"
docker build -t bgpsec/gobgpsrx:local -f "$OVERLAY/gobgpsrx.Dockerfile" "$OVERLAY"

step "done"
docker images --filter=reference='bgpsec/*' \
  --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'
