#!/usr/bin/env bash
# Codespace bootstrap for the containerlab BGPsec lab (Task 2).
#
# Two jobs: Python packages for the notebooks, and the four bgpsec/*:local
# Docker images the topology runs. Images come from this repo's `lab-images`
# release when it can be downloaded (a ~260 MB asset); otherwise they are
# built from the vendored source, which works but takes ~20 minutes.
#
# Safe to re-run at any time:  bash .devcontainer/postCreate.sh
# Every step is idempotent and a re-run picks up whatever is missing.
#
# Deliberately not `set -e`: a failed pull or download should leave a usable
# Codespace with a clear message, not a half-created one.
set -uo pipefail

# GITHUB_REPOSITORY is set inside a Codespace and tracks renames; the
# hardcoded fallback covers local dev containers, where it is unset.
REPO="${GITHUB_REPOSITORY:-will-elsen/bgpsec_module}"
TAG="lab-images"
ASSET="bgpsec-lab-images.tar.gz"
DIST="containerlab/lab/dist"

# The dind sidecar can still be starting when postCreate runs; everything
# below needs the daemon.
echo "=== waiting for the docker daemon ==="
for i in $(seq 1 30); do
    docker info >/dev/null 2>&1 && break
    [ "$i" -eq 30 ] && echo "WARNING: docker daemon not up after 60s — continuing anyway"
    sleep 2
done

echo "=== python packages for the notebooks ==="
if ! command -v pip3 >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y -qq python3-pip
fi
pip3 install --quiet ipykernel nbformat nbclient 2>/dev/null ||
    pip3 install --quiet --break-system-packages ipykernel nbformat nbclient

# Two independent download paths, because environments only guarantee one:
# `gh` (installed by the devcontainer github-cli feature; auto-authed by the
# Codespace token, keyring-authed on a local machine after `gh auth login`)
# and the raw REST API for anything that has only GITHUB_TOKEN.
download_asset() {
    if command -v gh >/dev/null 2>&1 &&
       gh release download "$TAG" --repo "$REPO" --pattern "$ASSET" \
           --dir "$DIST" --clobber 2>/dev/null; then
        echo "downloaded $ASSET via gh"
        return 0
    fi
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        local asset_url
        asset_url=$(curl -s --retry 3 -H "Authorization: Bearer $GITHUB_TOKEN" \
            "https://api.github.com/repos/$REPO/releases/tags/$TAG" |
            python3 -c "import sys,json;[print(a['url']) for a in json.load(sys.stdin).get('assets',[]) if a['name']=='$ASSET']" 2>/dev/null)
        if [ -n "${asset_url:-}" ]; then
            curl -sL --retry 3 -H "Authorization: Bearer $GITHUB_TOKEN" \
                 -H "Accept: application/octet-stream" \
                 -o "$DIST/$ASSET" "$asset_url" &&
                echo "downloaded $ASSET via API" && return 0
        fi
    fi
    return 1
}

echo "=== lab images ==="
if docker image inspect bgpsec/quaggasrx:local >/dev/null 2>&1; then
    echo "bgpsec/*:local already present"
else
    mkdir -p "$DIST"
    # A half-downloaded tarball from an earlier attempt must never reach
    # docker load.
    if [ -f "$DIST/$ASSET" ] && ! gzip -t "$DIST/$ASSET" 2>/dev/null; then
        echo "removing corrupt $ASSET left by an earlier attempt"
        rm -f "$DIST/$ASSET"
    fi
    if [ ! -f "$DIST/$ASSET" ]; then
        download_asset || { echo "download failed — retrying once"; sleep 10; download_asset; }
    fi
    if [ -f "$DIST/$ASSET" ] && gzip -t "$DIST/$ASSET" 2>/dev/null; then
        echo "loading image bundle (~1 minute)"
        docker load < "$DIST/$ASSET"
    else
        rm -f "$DIST/$ASSET"
        echo "no usable image bundle — building from source; this takes ~20 minutes"
        (cd containerlab/lab && bash build-images.sh)
    fi
fi

# The RPKI plane's pinned upstream images, pulled now so the first deploy()
# does not stall on Docker Hub. Krill MUST stay at v0.14.5 — see
# containerlab/CLAUDE.md for why.
echo "=== upstream images ==="
for img in nlnetlabs/krill:v0.14.5 nlnetlabs/routinator:v0.15.2 vimagick/rsyncd; do
    docker pull -q "$img" || { sleep 5; docker pull -q "$img"; } ||
        echo "WARNING: could not pull $img — the first lab.deploy() will retry"
done

# The key vault the topology bind-mounts is not committed (a deploy rewrites
# it and chowns its keys to root), so build it from the tracked keys now
# rather than on the first deploy. Idempotent.
echo "=== key vault ==="
bash containerlab/lab/tools/build_vault.sh ||
    echo "WARNING: key vault not built — lab.deploy() will retry it"

if docker image inspect bgpsec/quaggasrx:local >/dev/null 2>&1; then
    echo "=== done — open bgpsec_lab_exercise.ipynb and run it from the top ==="
else
    echo "=== setup did NOT complete: the bgpsec/*:local images are missing."
    echo "    Fix the network/auth issue, then re-run:  bash .devcontainer/postCreate.sh"
fi
