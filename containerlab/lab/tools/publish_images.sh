#!/usr/bin/env bash
# Publish the lab's router-image bundle as this repo's `lab-images` release.
#
# One-time step after pushing the repo to a new GitHub remote. The Codespace
# bootstrap (.devcontainer/postCreate.sh) downloads the bundle from the
# `lab-images` release of the repo the Codespace runs from. Without that
# release, setup still works but falls back to a ~20-minute build from source.
#
#   bash containerlab/lab/tools/publish_images.sh [owner/repo]
#
# The repo defaults to the one `gh` resolves from this clone's remote. The
# bundle is taken from containerlab/lab/dist/ if present, otherwise saved from
# the local bgpsec/*:local images (needs Docker). Safe to re-run: an existing
# release just has its asset replaced.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."   # repo root

REPO="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
TAG="lab-images"
ASSET="bgpsec-lab-images.tar.gz"
DIST="containerlab/lab/dist"
IMAGES="bgpsec/quaggasrx:local bgpsec/gobgpsrx:local bgpsec/srx-server:local bgpsec/tal-share:local"

mkdir -p "$DIST"
if [ ! -f "$DIST/$ASSET" ]; then
    echo "no $DIST/$ASSET; saving it from the local images (a few minutes)"
    # shellcheck disable=SC2086
    docker save $IMAGES | gzip > "$DIST/$ASSET"
fi

echo "checking the bundle"
gzip -t "$DIST/$ASSET"
listed=$(tar -xzOf "$DIST/$ASSET" manifest.json | python3 -c \
    'import json,sys; print(" ".join(t for m in json.load(sys.stdin) for t in (m.get("RepoTags") or [])))')
for img in $IMAGES; do
    case " $listed " in
        *" $img "*) ;;
        *) echo "ERROR: the bundle does not contain $img"; exit 1 ;;
    esac
done

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
    gh release upload "$TAG" "$DIST/$ASSET" --repo "$REPO" --clobber
else
    gh release create "$TAG" "$DIST/$ASSET" --repo "$REPO" --title "Lab images" --notes \
"Prebuilt Docker images for the containerlab BGPsec lab: bgpsec/{quaggasrx,gobgpsrx,srx-server,tal-share}:local, x86_64, built per containerlab/lab/IMAGES.md. The Codespace devcontainer downloads and docker-loads this automatically; to load manually: docker load < $ASSET"
fi
echo "published $ASSET to $REPO, release $TAG"
