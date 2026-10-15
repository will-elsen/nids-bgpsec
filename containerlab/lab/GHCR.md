# Hosting the lab images on GitHub Container Registry

The four `bgpsec/*` images the lab runs (see `IMAGES.md`) are currently
distributed as a single tarball attached to this repo's `lab-images` GitHub
release. That works, but it has real costs: the Codespace `postCreate` script
needs `gh` or a `GITHUB_TOKEN` API dance just to download it, there is no
per-image versioning — the tarball is replaced wholesale — and `docker pull`
cannot fetch the images directly.

This page is the runbook for hosting them on GitHub Container Registry
(GHCR, `ghcr.io`) instead. Nothing here has been done yet; when it has been,
update the status line below.

**Status: not yet published.** No packages exist under `ghcr.io/will-elsen`
for this lab.

## The one design decision: GHCR is distribution, `:local` stays the runtime tag

Everything in the lab — the topology files (`phase*/bgpsec-p*.clab.yml`),
`labkit.py`, both notebooks, the smoke test — references images as
`bgpsec/<name>:local`. Do not change that. GHCR is only where the bytes come
from; a fresh machine **pulls and retags**:

```bash
for img in quaggasrx gobgpsrx srx-server tal-share; do
    docker pull ghcr.io/will-elsen/bgpsec-$img:latest
    docker tag  ghcr.io/will-elsen/bgpsec-$img:latest bgpsec/$img:local
done
```

After that loop the lab deploys exactly as it does today, and no topology
file, notebook, or tool needs to know GHCR exists. Never push a `:local` tag —
it is the runtime contract, not a distribution artifact.

## Naming

GHCR image names must be lowercase. The mapping:

| Local tag | GHCR name |
|---|---|
| `bgpsec/quaggasrx:local` | `ghcr.io/will-elsen/bgpsec-quaggasrx` |
| `bgpsec/gobgpsrx:local` | `ghcr.io/will-elsen/bgpsec-gobgpsrx` |
| `bgpsec/srx-server:local` | `ghcr.io/will-elsen/bgpsec-srx-server` |
| `bgpsec/tal-share:local` | `ghcr.io/will-elsen/bgpsec-tal-share` |

Tag each push twice: a date tag (`:2026-07-31` — the rebuild date, matching
the provenance record in `IMAGES.md`) and a moving `:latest`. The date tag is
what makes "which images does this bundle contain" answerable after the fact,
which the release tarball never was.

## One-time setup: authentication

Pushing needs a token with the `write:packages` scope. Fine-grained PATs do
not cover GHCR; use a **classic** PAT
(github.com → Settings → Developer settings → Personal access tokens →
Tokens (classic)) with `write:packages` checked (`read:packages` comes with
it). Then:

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u will-elsen --password-stdin
```

Pulling needs no auth at all once the packages are public (below) — that is
most of the point.

## Publishing

From the machine that built the images (they are x86_64-only — see
`IMAGES.md`):

```bash
DATE=2026-07-31   # the rebuild date from IMAGES.md, not today's date
for img in quaggasrx gobgpsrx srx-server tal-share; do
    docker tag bgpsec/$img:local ghcr.io/will-elsen/bgpsec-$img:$DATE
    docker tag bgpsec/$img:local ghcr.io/will-elsen/bgpsec-$img:latest
    docker push ghcr.io/will-elsen/bgpsec-$img:$DATE
    docker push ghcr.io/will-elsen/bgpsec-$img:latest
done
```

## After the first push: visibility and repo linkage

New GHCR packages are **private by default**, and package visibility is
independent of repository visibility. Until this is done, every anonymous
pull fails with `denied` and the Codespace bootstrap falls back to a
20-minute source build:

1. github.com → your profile → **Packages** → select each `bgpsec-*` package
2. **Package settings → Danger Zone → Change visibility → Public**
3. While there: **Manage Actions access / Connect repository** → link the
   package to `will-elsen/bgpsec_module`, so it shows on the repo page
   and inherits its collaborators.

To make the repo linkage automatic on future pushes, add the source label to
each overlay Dockerfile (`lab/overlay/*.Dockerfile`) and to the three
upstream-built images via `--label` in `build-images.sh`:

```dockerfile
LABEL org.opencontainers.image.source=https://github.com/will-elsen/bgpsec_module
```

## Wiring it into the Codespace

`.devcontainer/postCreate.sh` currently tries, in order: images already
present → download the release tarball via `gh` → download it via the API →
build from source. Once the packages are public, replace the two download
branches with the pull-and-retag loop from the top of this page. Public
packages need no token, so the `GITHUB_TOKEN` branch disappears entirely.
Keep the build-from-source fallback — it is what makes the lab survivable
when the registry is unreachable.

The `lab-images` release can stay as an offline artifact, but it stops being
the primary path; regenerate it (or delete it) whenever the images change so
the two never disagree. `docs` that describe the release download —
`Task-bgpsec-lab.md`'s "Running it locally" section and `lab/README.md`'s
"Running it" section — should switch to the pull-and-retag loop at the same
time.

## Rebuilding and republishing

A rebuild is only worth publishing if the smoke test passes against it:

```bash
./build-images.sh
python3 tools/smoke_test.py
```

then push with a fresh date tag and move `:latest`. Before relying on CI for
this, note the constraint recorded in `IMAGES.md`: the upstream Dockerfiles
`git clone` the NIST sources **unpinned**, so an automated rebuild silently
picks up whatever is on master that day. Pin the SHAs in the Dockerfiles
first; until then, publishing should stay a deliberate, manual act by
someone who ran the smoke test. If CI is wanted afterwards, a
`workflow_dispatch`-only workflow with `permissions: {packages: write}` and
`docker/login-action` against `${{ secrets.GITHUB_TOKEN }}` is the standard
shape — do not trigger it on push.

## Gotchas

- **GHCR names must be lowercase** — hence `bgpsec-srx-server`, not
  `bgpsec/SRx-Server`.
- **The images are amd64-only.** Codespaces and typical Linux hosts are fine;
  Apple Silicon needs `docker pull --platform linux/amd64` and runs them
  under emulation.
- **403 from GHCR means "private or nonexistent"** — it deliberately does not
  distinguish. If a pull that should work returns `denied`, check package
  visibility before debugging auth.
- **The RPKI-plane images stay on Docker Hub, pinned**: `nlnetlabs/krill:v0.14.5`
  (the pin is load-bearing — see `IMAGES.md`), `nlnetlabs/routinator:v0.15.2`,
  `vimagick/rsyncd`. Mirroring them to GHCR is optional insurance against
  Docker Hub rate limits; if done, the topology files' `image:` lines are the
  only place to update.
